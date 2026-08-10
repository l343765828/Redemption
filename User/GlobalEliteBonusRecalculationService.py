import json
import logging
import time
import uuid
from decimal import Decimal, ROUND_DOWN
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from dask.distributed import Client
from redis_om import NotFoundError

from Model.User.EliteBonusStats import EliteBonusStats
from Common.AmountModelAdapter import build_factory_amount_fields
from Redishelper.PVAmountConfigProvider import (
    PVAmountConfigProvider,
    PVAmountRunConfig,
    PVAmountRunSession,
)
from User.UserStatsService import SCHEDULE_ADDRESS

logger = logging.getLogger(__name__)


class GlobalEliteBonusRecalculationService:
    """
    Elite Bonus 全量结算服务（生产最终版 + 落库）

    架构与安全规约：
    1. 【图谱防错机制】：强制在重算前进行全局图谱完整性校验，阻断因环路或断裂拓扑导致的静默计算错误。
    2. 【自下而上遍历】：从最深叶子层（max_depth）层层递推至根节点（0），确保下级的贡献优先固化。
    3. 【事务发件箱与原子性】：全面采用 transaction=True 管道，状态更新、溯源归账、运行期缓存清理同生共死。
    4. 【幽灵节点中和 & 输入保护】：绝不物理删除 EliteBonusStats（死保 pv_pcs）。期初通过批量复位派生字段使历史幽灵节点自然失效。
    5. 【大表扫描防漂移】：在全表 Reset 和 Cleanup 的游标扫描中加入锁续期，防止超大网体下锁 TTL 过期。
    6. 【运行期动态内存回收】：子节点未吸收业绩上推并被父节点读取后，立即销毁临时键；期末回收根节点残余，防止内存泄漏。
    7. 【正式产出落库】：重算完成后，把本期 EliteBonusStats(gpv_real>0 且 estimated_bonus>0) 写入 AR_CALC_BONUS_E，
       把 eb_source 写入 AR_CALC_BONUS_E_SOURCE。该步骤【复用增量版 EliteBonusService.snapshot_period_to_db】，
       确保全量与增量的 "Redis → 关系库" 落库口径 100% 一致，不产生两套实现的漂移。
       - 提供 db_executor 时：settle_period 在进程内、持锁状态、发哨兵前完成落库（自包含模式），哨兵 persisted=True。
       - 不提供 db_executor 时：settle_period 仅重建 Redis 派生态与 eb_source（"重算阶段"模式），
         落库交由 SETTLEMENT_PERIOD_DONE 的下游消费者执行，哨兵 persisted=False。

    ──────────────────────────────────────────────────────────────────────────
    两个调用前必须知晓的口径前提（不在本服务内部决定，须由业务/调用方锁死）：

    [前提 A · 溯源口径] 本服务采用 "最近合格吸收者" 口径：未合格节点把未吸收 source 往上存，
      遇到第一个合格祖先时写 eb_source；若链路到顶仍无任何合格祖先，则不写无奖金 SOURCE。
      这与增量版 EliteBonusService 已声明的修订口径一致，但【不完全等同原 CALC_BE_E.sql】
      （SQL 会把无奖金归属也写到顶端非合格节点；且 SQL 取 BONUS_LAYER=TOP_DEEP 最小，方向与本实现的
      "离源头代数最小=最近吸收人" 相反）。本实现的好处是 BONUS_USER_ID 必为真实得奖人（满足验收点 9）。
      若硬性要求 100% 复刻 SQL，需在 _process_parent_batch 末尾对 depth=0 仍未被吸收的 source
      补一条归属到顶端非合格节点的 fallback —— 这会重新引入 "归属到没奖金的人"，属口径倒退，须业务拍板。

    [前提 B · 输入口径] 本服务【不从 AR_PERF_MONTH 重铺底】，而是基于 Redis 中既有的
      EliteBonusStats.pv_pcs 重算派生态（与参考实现 GlobalRecalculationService 保留 node.pv 的"全量"定义一致）。
      因此调用 settle_period 前，Redis 里的 pv_pcs 必须已按【最终确认的】业务口径准备好。
      若 "全量" 的目标是 "从库原始业绩完全重建当期结果"，则需另加一个从 AR_PERF_MONTH 读取并过滤的输入阶段，
      而这一步绕不开先解决需求文档里悬而未决的 PV_PCS / PV_PSS 过滤口径矛盾。
    ──────────────────────────────────────────────────────────────────────────
    """

    GLOBAL_RECALC_LOCK_KEY = "system:global_eb_recalc_lock"
    OUTBOX_STREAM_KEY = "system:recalc_outbox_stream"
    ELITE_MARK = 1000

    STATUS_RUNNING = "RUNNING"
    STATUS_DONE = "DONE"
    STATUS_FAILED = "FAILED"

    LOCK_TTL_SECONDS = 60 * 60
    DASK_RESULT_TIMEOUT_SECONDS = 30 * 60

    PARENT_PAGE_SIZE = 5000
    CHILD_PAGE_SIZE = 2000

    MAX_PARENT_PAGES_PER_DEPTH = 100_000
    MAX_CHILD_PAGES_PER_PARENT = 100_000

    SOURCE_TTL_SECONDS = 60 * 60 * 24 * 90  # 溯源记录 90 天底线过期

    def __init__(
        self,
        elite_rate: float = 0.15,
        *,
        calc_month: Optional[int] = None,
        db_executor: Optional[Callable[[str, List[Dict[str, Any]]], None]] = None,
        user_info_resolver: Optional[Callable[[List[str]], Dict[str, Dict[str, Any]]]] = None,
    ):
        """
        :param elite_rate: 需由调用方从 AR_CONFIG 锁定传入，Decimal 转换避开二进制浮点误差。
        :param calc_month: IV_CALC_MONTH，写入 AR_CALC_BONUS_E / _SOURCE 的 CALC_MONTH。
            仅当提供 db_executor（自包含落库模式）时必填。
        :param db_executor: 关系库事务批量插入回调，签名 db_executor(table_name, rows)。
            与增量版 EliteBonusService 的 DbExecutor 契约完全一致，两张表的 INSERT 应在同一事务中。
            ⚠️ 全量【重跑】会向两张表 INSERT 新行：覆盖语义须由 db_executor 自行实现（按 PERIOD_NUM 先删后插），
               或由调用方在 settle_period 前清理对应期数的 AR_CALC_BONUS_E / _SOURCE，否则重复发奖。
               参见需求文档 §5.2 疑点5。
        :param user_info_resolver: 落库时批量解析用户姓名/国家/父级/层数的回调；
            不提供则 SOURCE / BONUS_E 表的姓名/国家/父级等关联字段为空。
        """
        self.elite_rate = Decimal(str(elite_rate))
        self.calc_month = calc_month
        self.db_executor = db_executor
        self.user_info_resolver = user_info_resolver

    @classmethod
    def _status_key(cls, period: str) -> str:
        return f"system:global_eb_recalc_status:{period}"

    def settle_period(self, period: str) -> None:
        """单期全量 Elite Bonus 结算重算主入口"""
        period = str(period)
        # region 加载并冻结本次业务运行配置
        redis_conn = EliteBonusStats.db()
        run_config = PVAmountRunSession.start(
            PVAmountConfigProvider(redis_conn)
        ).config
        # endregion

        run_id = str(uuid.uuid4())
        status_key = self._status_key(period)

        lock = redis_conn.lock(
            self.GLOBAL_RECALC_LOCK_KEY,
            timeout=self.LOCK_TTL_SECONDS,
            blocking_timeout=0,
            thread_local=True,
        )

        if not lock.acquire(blocking=False):
            raise RuntimeError(f"Elite Bonus 全局结算锁被持有，阻断 {period} 的重算任务。")

        client: Optional[Client] = None

        try:
            logger.info("=== 开始 Elite Bonus 单期全量重算 period=%s run_id=%s ===", period, run_id)
            self._set_period_settlement_status(redis_conn, status_key, self.STATUS_RUNNING, run_id)

            client = Client(SCHEDULE_ADDRESS)
            graph_actor = self._await_actor_result(client.get_dataset("graph_actor"))
            if not graph_actor:
                raise RuntimeError("未在 Dask 集群中检索到合法的 graph_actor 实例")

            # 1. 强制执行全局图完整性校验
            logger.info("执行全局推荐网拓扑架构完整性审计...")
            self._refresh_global_lock(lock)
            self._await_actor_result(graph_actor.validate_graph_integrity())

            max_depth = int(self._await_actor_result(graph_actor.get_max_root_depth()))
            logger.info("拓扑审计通过。网体最大深度: %d", max_depth)

            # 2. 期初数据纯净度保障 (绝不删除 EliteBonusStats 本身，传 lock 进去续期)
            logger.info("开始执行重算期初派生字段复位与临时环境清理...")
            self._reset_all_derived_stats(redis_conn, period, lock)
            self._cleanup_temp_and_source_data(redis_conn, period, lock)

            # 3. 自下而上拓扑分层遍历结算
            for depth in range(max_depth, -1, -1):
                logger.info("开始处理分层架构 depth=%d period=%s", depth, period)
                parent_cursor: Optional[Any] = None
                parent_page_count = 0

                while True:
                    parent_page_count += 1
                    if parent_page_count > self.MAX_PARENT_PAGES_PER_DEPTH:
                        raise RuntimeError(f"depth={depth} 遍历因游标不收敛阻断，疑似底层分页契约破坏。")

                    self._refresh_global_lock(lock)

                    page = self._await_actor_result(
                        graph_actor.get_nodes_at_depth_page(depth, parent_cursor, self.PARENT_PAGE_SIZE)
                    )
                    batch_parent_ids, next_parent_cursor = self._parse_page_result(page)
                    batch_parent_ids = [str(x) for x in batch_parent_ids]

                    if not batch_parent_ids:
                        break

                    self._process_parent_batch(
                        graph_actor=graph_actor,
                        parent_ids=batch_parent_ids,
                        period=period,
                        run_id=run_id,
                        redis_conn=redis_conn,
                        run_config=run_config,
                        lock=lock
                    )

                    self._set_period_settlement_status(redis_conn, status_key, self.STATUS_RUNNING, run_id, {
                        "phase": "recalculating",
                        "max_depth": max_depth,
                        "current_depth": depth,
                        "parent_page_count": parent_page_count,
                    })

                    parent_cursor = next_parent_cursor
                    if parent_cursor is None:
                        break

            # 4. 正式产出落库 (规约 7)：复用增量 snapshot 口径写 AR_CALC_BONUS_E / _SOURCE
            #    必须在持锁状态、发哨兵之前完成；失败会落 FAILED 并可整轮重跑（Redis 态未清，可重读）。
            persisted = False
            persist_stats: Dict[str, int] = {}
            if self.db_executor is not None:
                logger.info("开始期末快照落库 AR_CALC_BONUS_E / AR_CALC_BONUS_E_SOURCE ...")
                self._refresh_global_lock(lock)
                persist_stats = self._persist_to_db(period, run_config)
                persisted = True
                logger.info(
                    "落库完成 bonus_rows=%s source_rows=%s",
                    persist_stats.get("bonus_count"), persist_stats.get("source_count"),
                )
            else:
                logger.warning(
                    "未提供 db_executor：本次仅完成 Redis 重算阶段，"
                    "AR_CALC_BONUS_E / _SOURCE 尚未落库；须由 SETTLEMENT_PERIOD_DONE 的下游消费者执行 snapshot 落库。"
                )

            # 5. 期末原子化收尾 (只清 eb_unabsorbed，保留 eb_source 供已落库后追溯/下游消费)
            logger.info("回收根层临时键并发布完工哨兵...")
            self._cleanup_temp_and_source_data(redis_conn, period, lock, clean_source=False)
            self._emit_settlement_done(
                redis_conn, status_key, period, run_id, max_depth,
                persisted=persisted, persist_stats=persist_stats,
            )

            logger.info("=== Elite Bonus 全量期末重算圆满成功 period=%s run_id=%s persisted=%s ===",
                        period, run_id, persisted)

        except Exception as e:
            logger.exception("致命错误：Elite Bonus 全量重算流程崩塌 period=%s run_id=%s", period, run_id)
            try:
                self._set_period_settlement_status(redis_conn, status_key, self.STATUS_FAILED, run_id, {"error": repr(e)})
            except Exception as set_err:
                logger.error("标记 FAILED 状态失败: %s", set_err)
            raise
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            try:
                if lock.owned():
                    lock.release()
            except Exception:
                pass

    def _process_parent_batch(
        self,
        graph_actor,
        parent_ids: List[str],
        period: str,
        run_id: str,
        redis_conn,
        run_config: PVAmountRunConfig,
        lock,
    ) -> None:
        """批处理同层父节点，自下而上进行 GPV 归集、路径判定、奖金算定与业绩吸收流转。"""
        if not parent_ids:
            return

        parent_lookup = self._mget_stats_with_exists(parent_ids, period, redis_conn, run_config)
        models_to_save: List[EliteBonusStats] = []
        pipe = redis_conn.pipeline(transaction=True)
        consumed_child_keys: List[str] = []

        for pid in parent_ids:
            self._refresh_global_lock(lock)
            p_node, _ = parent_lookup[pid]

            # 在图内计算的节点，基于其保留的 pv_pcs 复位其派生字段
            p_node.gpv = p_node.pv_pcs or 0
            p_node.qualified_downlines = set()
            p_node.contrib_to_parent = 0
            p_node.gpv_real = 0
            p_node.is_qualified = False
            p_node.qualifying_path = None
            p_node.estimated_bonus = 0.0

            unabsorbed_sources: Dict[str, int] = {}
            if (p_node.pv_pcs or 0) > 0:
                unabsorbed_sources[pid] = 0

            child_cursor: Optional[Any] = None
            child_page_count = 0

            while True:
                child_page_count += 1
                if child_page_count > self.MAX_CHILD_PAGES_PER_PARENT:
                    raise RuntimeError(f"parent_id={pid} 的子树分支页数超限，中断计算。")

                self._refresh_global_lock(lock)

                page = self._await_actor_result(
                    graph_actor.get_direct_children_page(pid, child_cursor, self.CHILD_PAGE_SIZE)
                )
                child_ids, next_child_cursor = self._parse_page_result(page)
                child_ids = [str(x) for x in child_ids]

                if not child_ids:
                    break

                child_lookup = self._mget_stats_with_exists(child_ids, period, redis_conn, run_config)

                for cid in child_ids:
                    c_node, _ = child_lookup[cid]

                    # 汇总未合格子节点继续上贡的 GPV
                    if (c_node.contrib_to_parent or 0) > 0:
                        p_node.gpv += c_node.contrib_to_parent

                        child_unabsorbed_key = f"eb_unabsorbed:{period}:{cid}"
                        child_sources = redis_conn.hgetall(child_unabsorbed_key)

                        for src_bytes, layer_bytes in child_sources.items():
                            src_str = src_bytes.decode() if isinstance(src_bytes, bytes) else src_bytes
                            layer_int = int(layer_bytes)
                            unabsorbed_sources[src_str] = layer_int + 1

                        consumed_child_keys.append(child_unabsorbed_key)

                    # 记录直属合格下线
                    if c_node.is_qualified:
                        p_node.qualified_downlines.add(cid)

                child_cursor = next_child_cursor
                if child_cursor is None:
                    break

            self._evaluate_node(p_node)
            models_to_save.append(p_node)

            if p_node.is_qualified:
                for src_id, layer_dist in unabsorbed_sources.items():
                    # ⚠️ 传入裸 uid：p_node.user_id
                    self._track_bonus_source(redis_conn, period, src_id, p_node.user_id, layer_dist, pipe)
            else:
                if unabsorbed_sources:
                    unabsorbed_key = f"eb_unabsorbed:{period}:{pid}"
                    pipe.hset(unabsorbed_key, mapping=unabsorbed_sources)
                    pipe.expire(unabsorbed_key, self.SOURCE_TTL_SECONDS)

        # 彻底清理已被吸收完毕的下级溯源临时键
        if consumed_child_keys:
            pipe.delete(*set(consumed_child_keys))

        if models_to_save:
            for model in models_to_save:
                model.save(pipeline=pipe)

        pipe.execute()

    def _evaluate_node(self, node: EliteBonusStats) -> None:
        """双路径合格判定状态机与财务截断计算"""
        if (node.gpv or 0) >= self.ELITE_MARK:
            node.is_qualified = True
            node.qualifying_path = 'A'
        elif len(node.qualified_downlines) > 0:
            node.is_qualified = True
            node.qualifying_path = 'B'
        else:
            node.is_qualified = False
            node.qualifying_path = None

        node.gpv_real = node.gpv if node.is_qualified else 0
        node.contrib_to_parent = 0 if node.is_qualified else node.gpv

        if (node.gpv_real or 0) > 0:
            gpv_real_dec = Decimal(str(node.gpv_real))
            bonus_dec = (gpv_real_dec * self.elite_rate).quantize(
                Decimal('0.01'), rounding=ROUND_DOWN,
            )
            node.estimated_bonus = float(bonus_dec)
        else:
            node.estimated_bonus = 0.0

    def _track_bonus_source(self, redis_conn, period: str, source_user_id: str, bonus_user_id: str, layer: int, pipe) -> None:
        """
        记录离源头最近的合格吸收祖先（layer=距离源头的代数）。
        由于自下而上层层截断，每个溯源实质上只会被最近的合格祖先吸收一次，这里的比对仅作兜底保障。
        """
        redis_key = f"eb_source:{period}:{source_user_id}"

        current_min = redis_conn.hget(redis_key, "layer")
        if current_min is not None and isinstance(current_min, bytes):
            current_min = current_min.decode()

        if current_min is None or layer < int(current_min):
            pipe.hset(redis_key, mapping={
                "layer": layer,
                "bonus_user_id": bonus_user_id,
            })
            pipe.expire(redis_key, self.SOURCE_TTL_SECONDS)

    def _mget_stats_with_exists(
        self,
        user_ids: Iterable[str],
        period: str,
        redis_conn,
        run_config: PVAmountRunConfig,
    ) -> Dict[str, Tuple[EliteBonusStats, bool]]:
        out: Dict[str, Tuple[EliteBonusStats, bool]] = {}
        uid_list = [str(uid) for uid in user_ids]
        if not uid_list:
            return out

        keys = [EliteBonusStats.make_key(f"{period}:{uid}") for uid in uid_list]
        try:
            raw_results = redis_conn.json().mget(keys, ".")
            if raw_results is None:
                raise RuntimeError("MGET 结果集返回空指针")
        except Exception as e:
            logger.warning("JSON.MGET 发生阻断，平滑降级至单键兜底模式: %s", e)
            return self._fallback_single_get(uid_list, period, run_config)

        for uid, raw_data in zip(uid_list, raw_results):
            expected_pk = f"{period}:{uid}"

            if raw_data is None:
                out[uid] = (self._new_blank_stats(uid, period, run_config), False)
                continue

            try:
                if "pk" in raw_data and raw_data["pk"] != expected_pk:
                    raise ValueError(f"PK 冲突 expected={expected_pk}, actual={raw_data['pk']}")
                raw_data["pk"] = expected_pk

                if "period_num" in raw_data and str(raw_data["period_num"]) != period:
                    raise ValueError(f"周期错位 expected={period}, actual={raw_data['period_num']}")
                raw_data["period_num"] = int(period)

                if "user_id" in raw_data and str(raw_data["user_id"]) != uid:
                    raise ValueError(f"UID 不匹配 expected={uid}, actual={raw_data['user_id']}")
                raw_data["user_id"] = uid

                node = EliteBonusStats(**raw_data)
                out[uid] = (node, True)
            except Exception as check_err:
                logger.error("数据损坏：反序列化拦截阻止脏数据静默参算 period=%s, user_id=%s, err=%s", period, uid, check_err)
                raise RuntimeError(f"结算核心链路受损阻断：{check_err}") from check_err

        return out

    def _fallback_single_get(
        self,
        uid_list: List[str],
        period: str,
        run_config: PVAmountRunConfig,
    ) -> Dict[str, Tuple[EliteBonusStats, bool]]:
        out = {}
        for uid in uid_list:
            try:
                node = EliteBonusStats.get(f"{period}:{uid}")
                out[uid] = (node, True)
            except NotFoundError:
                out[uid] = (self._new_blank_stats(uid, period, run_config), False)
        return out

    def _new_blank_stats(self, uid: str, period: str, run_config: PVAmountRunConfig) -> EliteBonusStats:
        return EliteBonusStats(
            pk=f"{period}:{uid}", id=f"{period}:{uid}", user_id=uid, period_num=int(period),
            pv_pcs=0, gpv=0, gpv_real=0, contrib_to_parent=0,
            **build_factory_amount_fields(
                run_config.state,
                include_bonus_cents=True,
            ),
        )

    # ==========================================
    # 正式产出落库 (复用增量 snapshot，保证两套实现口径一致)
    # ==========================================

    def _persist_to_db(self, period: str, run_config: PVAmountRunConfig) -> Dict[str, int]:
        """
        把本期 Redis 结果固化到关系库 AR_CALC_BONUS_E / AR_CALC_BONUS_E_SOURCE。

        实现策略：直接复用增量服务 EliteBonusService.snapshot_period_to_db，
        确保全量与增量的 "Redis → 关系库" 落库口径 100% 一致，杜绝两套实现漂移。

        正确性依赖：期初 _reset_all_derived_stats 已把图外幽灵节点的 gpv_real / estimated_bonus 清零，
        因此 snapshot 的 find(period_num) + (gpv_real>0 且 estimated_bonus>0) 过滤只会捞到本期真实得奖人，
        不会误发已不在当前图中的历史幽灵节点。

        :return: {"bonus_count": N, "source_count": M}
        """
        if self.calc_month is None:
            raise RuntimeError("提供了 db_executor 但未提供 calc_month，无法写入 AR_CALC_BONUS_E / _SOURCE。")

        # 懒导入，避免顶层 import 路径耦合导致整模块加载失败；路径以实际工程为准。
        from User.EliteBonusService import EliteBonusService

        locked_rate = self.elite_rate  # 锁定期初比例，避免闭包捕获到后续被改写的引用
        snapshot_svc = EliteBonusService(
            period_num=int(period),
            calc_month=self.calc_month,
            elite_rate_loader=lambda: locked_rate,
            user_info_resolver=self.user_info_resolver,
        )
        return snapshot_svc._snapshot_period_to_db(self.db_executor, run_config)

    # ==========================================
    # 环境清理与纯净度保障 (含大表锁续期)
    # ==========================================

    def _reset_all_derived_stats(self, redis_conn, period: str, lock) -> None:
        """
        幽灵节点拦截器：将全网所有 Stats 派生字段归零，绝不动 pv_pcs。
        通过大表分批操作和全局锁保护机制，确保图外幽灵节点在期末 Snapshot 时被安全抛弃。

        注：保留图内节点会被写入两次的代价（Reset 覆盖一次 + 自下而上图层覆盖一次），
        以换取 Snapshot 侧逻辑解耦和纯粹性。
        """
        stats_prefix = EliteBonusStats.make_key(f"{period}:*")
        # 采用 redis_conn.json().pipeline() 标准化写法缓冲 JSON.SET 命令
        pipe = redis_conn.json().pipeline(transaction=False)
        batch_size = 0

        for key in redis_conn.scan_iter(match=stats_prefix, count=2000):
            # 通过 JSON.SET 直接修改底层值，绕开读取和 save，安全保留 pv_pcs 和原始 ID
            pipe.set(key, "$.gpv_real", 0)
            pipe.set(key, "$.estimated_bonus", 0.0)
            pipe.set(key, "$.is_qualified", False)
            pipe.set(key, "$.contrib_to_parent", 0)
            pipe.set(key, "$.qualifying_path", None)
            pipe.set(key, "$.qualified_downlines", [])

            batch_size += 1

            # 每批次提交并触发锁续期，防止全网节点扫描耗时引发漂移
            if batch_size >= 1000:
                pipe.execute()
                self._refresh_global_lock(lock)
                # 重新初始化 pipeline，避免复用隐患
                pipe = redis_conn.json().pipeline(transaction=False)
                batch_size = 0

        if batch_size > 0:
            pipe.execute()
            self._refresh_global_lock(lock)

    def _cleanup_temp_and_source_data(self, redis_conn, period: str, lock, clean_source: bool = True) -> None:
        """
        仅清理溯源追踪产生的运行期临时键和最终溯源键。
        扫描时加入锁续期保护。
        """
        patterns = [f"eb_unabsorbed:{period}:*"]
        if clean_source:
            patterns.append(f"eb_source:{period}:*")

        for pattern in patterns:
            keys_to_delete = []
            for key in redis_conn.scan_iter(match=pattern, count=2000):
                keys_to_delete.append(key)
                if len(keys_to_delete) >= 1000:
                    redis_conn.delete(*keys_to_delete)
                    self._refresh_global_lock(lock)
                    keys_to_delete.clear()

            if keys_to_delete:
                redis_conn.delete(*keys_to_delete)
                self._refresh_global_lock(lock)

    # ==========================================
    # 状态哨兵与运维人工干预防线
    # ==========================================

    def _set_period_settlement_status(self, redis_conn, status_key: str, status: str, run_id: str, extra: Dict = None) -> None:
        payload = {"status": status, "run_id": run_id, "updated_at": int(time.time())}
        if extra:
            payload.update(extra)
        redis_conn.set(status_key, json.dumps(payload, ensure_ascii=False, default=str))

    def _emit_settlement_done(
        self, redis_conn, status_key: str, period: str, run_id: str, max_depth: int,
        persisted: bool = False, persist_stats: Optional[Dict[str, int]] = None,
    ) -> None:
        persist_stats = persist_stats or {}
        done_status_payload = {
            "status": self.STATUS_DONE,
            "run_id": run_id,
            "updated_at": int(time.time()),
            "persisted": bool(persisted),
        }
        sentinel_event = {
            "event_type": "SETTLEMENT_PERIOD_DONE",
            "bonus_type": "ELITE_BONUS",
            "period": period,
            "run_id": run_id,
            "max_depth": int(max_depth),
            # persisted=True：本进程已写 AR_CALC_BONUS_E / _SOURCE；
            # persisted=False：仅完成 Redis 重算，待下游消费者执行 snapshot 落库。
            "persisted": bool(persisted),
            "bonus_count": int(persist_stats.get("bonus_count", 0)),
            "source_count": int(persist_stats.get("source_count", 0)),
            "timestamp": int(time.time()),
        }

        pipe = redis_conn.pipeline(transaction=True)
        pipe.set(status_key, json.dumps(done_status_payload, ensure_ascii=False, default=str))
        pipe.xadd(
            name=self.OUTBOX_STREAM_KEY,
            fields={"payload": json.dumps(sentinel_event, ensure_ascii=False, default=str)},
            maxlen=100000,
            approximate=True
        )
        pipe.execute()

    def _refresh_global_lock(self, lock) -> None:
        if not lock.owned():
            raise RuntimeError("全局系统算力独占锁发生漂移或意外丢失，禁止继续写操作。")
        lock.extend(self.LOCK_TTL_SECONDS, replace_ttl=True)

    @classmethod
    def get_period_settlement_status(cls, period: str, redis_conn=None) -> Optional[Dict[str, Any]]:
        """读取全局重算状态"""
        if redis_conn is None:
            redis_conn = EliteBonusStats.db()
        raw = redis_conn.get(cls._status_key(period))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {"status": str(raw), "raw": str(raw)}

    @classmethod
    def assert_period_settlement_available(cls, period: str) -> None:
        """业务入口保护：传入 period 检查，用于阻断订单消费等写入"""
        redis_conn = EliteBonusStats.db()
        if redis_conn.exists(cls.GLOBAL_RECALC_LOCK_KEY):
            raise RuntimeError("Elite Bonus 结算锁被持有，禁止订单、拓扑变更及结算读取。")
        payload = cls.get_period_settlement_status(period, redis_conn)
        if payload and payload.get("status") in {cls.STATUS_RUNNING, cls.STATUS_FAILED}:
            raise RuntimeError(f"period={period} EB 结算状态为 {payload.get('status')}，阻断继续。")

    @classmethod
    def clear_period_settlement_failed(cls, period: str, *, by: str, reason: str) -> None:
        """手工解除 FAILED 阻塞"""
        if not by or not reason:
            raise ValueError("清除 FAILED 状态必须提供 by 和 reason。")
        redis_conn = EliteBonusStats.db()
        status_key = cls._status_key(period)
        payload = cls.get_period_settlement_status(period, redis_conn)

        if payload and payload.get("status") != cls.STATUS_FAILED:
            raise RuntimeError(f"当前 EB 状态非 FAILED，禁止清除。payload={payload}")

        logger.warning("手工清除 EB FAILED 状态 period=%s by=%s reason=%s", period, by, reason)
        redis_conn.delete(status_key)

    @classmethod
    def mark_stuck_running_as_failed(cls, period: str, *, by: str, reason: str) -> None:
        """将卡死的 RUNNING 标记为 FAILED"""
        redis_conn = EliteBonusStats.db()
        status_key = cls._status_key(period)
        probe_value = f"probe:{uuid.uuid4()}"

        if not redis_conn.set(cls.GLOBAL_RECALC_LOCK_KEY, probe_value, nx=True, ex=5):
            raise RuntimeError("EB 全局锁仍被持有，可能确实有进程在运行，禁止强行标记 FAILED。")

        try:
            payload = cls.get_period_settlement_status(period, redis_conn)
            if not payload or payload.get("status") != cls.STATUS_RUNNING:
                raise RuntimeError(f"当前 EB 状态非 RUNNING，禁止处理。payload={payload}")

            logger.warning("将卡死的 EB RUNNING 标记为 FAILED period=%s by=%s reason=%s", period, by, reason)
            payload.update({"status": cls.STATUS_FAILED, "phase": "failed_by_manual_recovery", "by": by, "reason": reason})
            redis_conn.set(status_key, json.dumps(payload, ensure_ascii=False, default=str))
        finally:
            current = redis_conn.get(cls.GLOBAL_RECALC_LOCK_KEY)
            if isinstance(current, bytes):
                current = current.decode("utf-8")
            if current == probe_value:
                redis_conn.delete(cls.GLOBAL_RECALC_LOCK_KEY)

    def _await_actor_result(self, future_or_value):
        if hasattr(future_or_value, "result"):
            return future_or_value.result(timeout=self.DASK_RESULT_TIMEOUT_SECONDS)
        return future_or_value

    @staticmethod
    def _parse_page_result(page) -> Tuple[List[Any], Optional[Any]]:
        if page is None:
            return [], None
        if isinstance(page, dict):
            return list(page.get("items") or []), page.get("next_cursor")
        if isinstance(page, tuple) and len(page) == 2:
            return list(page[0] or []), page[1]
        if isinstance(page, list):
            return page, None
        return [], None