"""
EliteBonusService - Elite Bonus 增量结算服务 (v4)

对应原 SQL CALC_BE_E.sql,但改为事件驱动 / 增量模型。

【职责分层】
1. 增量入口  update_elite_bonus_incremental(user_id, pv_delta)
   单笔订单触发,沿推荐链冒泡,实时维护本期 EliteBonusStats 与溯源记录。
2. 期末入口  snapshot_period_to_db(db_executor)
   把 Redis 中的预估奖金固化到关系型库的 AR_CALC_BONUS_E / _SOURCE。
3. 期末清理  cleanup_period()
   ⚠️ 必须在 snapshot 落盘且事务提交成功后才能调。

【三档关键设计】
- 双路径合格(A:GPV>=1000;B:任一直属下线已合格)统一在 _evaluate_node。
- 财务精度: Decimal + ROUND_DOWN,严格对齐 SQL TRUNCATE(.., 2)。
- 并发: 源用户 + BFS 路径上每个祖先都加 Redis 锁;锁顺序在树结构上单调,
  不会形成环路死锁;锁 TTL=30s 给深树留余量,容忍锁过期 release。

【与 SQL 的一处口径差异(需业务确认后锁死)】
当源用户产 PV、但链路上 *无任何合格祖先* 时:
  - SQL: 沿链路传到顶端非合格节点,写一条 SOURCE 记录(归属到没奖金的人)
  - 本实现: 不写入(只追踪有奖金的归属)
若业务要求与 SQL 完全对齐,在 _propagate_upward 末尾补 fallback 即可。
"""

from decimal import Decimal, ROUND_DOWN
from typing import Tuple, Optional, Callable, Dict, List, Any, Iterable
import time
import logging

from dask.distributed import Client
from redis_om import NotFoundError
from Model.User.EliteBonusStats import EliteBonusStats

logger = logging.getLogger(__name__)

# ---------- 业务常量 ----------
ELITE_MARK = 1000  # 合格小组业绩阈值(SQL 的 VV_ARRIVE_PV1)

# ---------- 基础设施常量 ----------
DEFAULT_DASK_ADDRESS = "tcp://127.0.0.1:8786"
LOCK_TIMEOUT = 30          # 锁自动释放(秒);深树 + Redis RTT 留出余量
LOCK_BLOCKING_TIMEOUT = 5  # 锁等待(秒);超时则上抛,由调用方决定重试或入死信
SOURCE_TTL_SECONDS = 60 * 60 * 24 * 90  # 溯源记录 90 天兜底过期


# ---------- 可注入接口 ----------
# 用户信息批量解析器
# 入参: user_ids 列表
# 出参: dict[user_id] -> {"user_name", "real_name", "country_id", "parent_uid", "top_deep"}
UserInfoResolver = Callable[[List[str]], Dict[str, Dict[str, Any]]]

# 比例加载器: 期初锁定 elite_rate
EliteRateLoader = Callable[[], Decimal]

# 落盘执行器: db_executor(table_name, rows) 由调用方提供事务与批量 INSERT
DbExecutor = Callable[[str, List[Dict[str, Any]]], None]


def _default_user_info_resolver(user_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """默认占位 - 生产必须替换,否则快照表里的姓名/国家/父级字段全空"""
    logger.warning("使用 _default_user_info_resolver 占位,生产环境需注入真实实现!")
    return {
        uid: {
            "user_name": "",
            "real_name": "",
            "country_id": "-1",
            "parent_uid": "0",
            "top_deep": 0,
        }
        for uid in user_ids
    }


class EliteBonusService:
    """单个 (period_num, calc_month) 内 Elite Bonus 的全生命周期服务"""

    def __init__(
        self,
        period_num: int,
        calc_month: int,
        elite_rate_loader: Optional[EliteRateLoader] = None,
        user_info_resolver: Optional[UserInfoResolver] = None,
        dask_address: str = DEFAULT_DASK_ADDRESS,
    ):
        """
        :param period_num:  IV_PERIOD_NUM
        :param calc_month:  IV_CALC_MONTH
        :param elite_rate_loader:
            从 AR_CONFIG 读取比例的函数,期初调用一次锁定,期内不刷新。
            生产实现示例:
                def loader():
                    raw = db.execute(
                        "SELECT MIN(VALUE) FROM AR_CONFIG "
                        "WHERE CONFIG_NAME='eliteRate' AND TYPE='bonus'"
                    ).scalar()
                    return Decimal(str(raw or 15)) / Decimal('100')
        :param user_info_resolver:
            期末快照时批量解析用户信息(姓名/国家/父级/层数)的回调。
            生产必须传入,否则 SOURCE / BONUS_E 表关联字段全空。
        :param dask_address: Dask 调度器地址
        """
        from Redishelper.BaseRedisModel import redis_conn
        self.period_num = period_num
        self.calc_month = calc_month
        self.redis_conn = redis_conn
        self._dask_client: Optional[Client] = None
        self._dask_address = dask_address
        self._user_info_resolver = user_info_resolver or _default_user_info_resolver

        # 期初锁定 elite_rate(必填,默认占位会出 WARN)
        if elite_rate_loader is not None:
            self.elite_rate = elite_rate_loader()
            logger.info("Period %s 期初锁定 elite_rate = %s", period_num, self.elite_rate)
        else:
            logger.warning(
                "elite_rate_loader 未提供,使用占位值 0.15。"
                "生产环境必须传入从 AR_CONFIG 读取的 loader!"
            )
            self.elite_rate = Decimal('0.15')

    # =================================================================
    # 基础设施: Dask 懒加载
    # =================================================================

    @property
    def dask_client(self) -> Client:
        if self._dask_client is None:
            try:
                self._dask_client = Client(self._dask_address)
            except Exception as e:
                raise RuntimeError(f"无法连接 Dask 调度器 {self._dask_address}: {e}") from e
        return self._dask_client

    # =================================================================
    # 状态机: 资格判定 + 计奖 GPV + 向上贡献 delta
    # =================================================================

    def _evaluate_node(self, node: EliteBonusStats) -> Tuple[int, bool]:
        """
        重新评定节点的资格、计奖口径、向上贡献量。
        返回 (delta_contrib, status_changed):
          delta_contrib  = 本节点 contrib_to_parent 的变化量(用于向上传导)
          status_changed = 资格 / 路径 / 合格下线集合任一变化(用于安全停止判定)
        """
        # region 记录当前节点的值
        prev_qualified = node.is_qualified
        prev_contrib = node.contrib_to_parent or 0
        prev_path = node.qualifying_path
        prev_q_count = len(node.qualified_downlines)
        # endregion

        # region 判断资格状态以及哪种方式获取的
        if (node.gpv or 0) >= ELITE_MARK:
            node.is_qualified = True
            node.qualifying_path = 'A'
        elif len(node.qualified_downlines) > 0:
            node.is_qualified = True
            node.qualifying_path = 'B'
        else:
            node.is_qualified = False
            node.qualifying_path = None
        # endregion

        # region ---- 截断与计奖 ----
        # 合格 → 业绩转入 gpv_real,向上贡献置 0
        # 不合格 → gpv_real=0,全部 gpv 继续向上贡献
        node.gpv_real = node.gpv if node.is_qualified else 0
        node.contrib_to_parent = 0 if node.is_qualified else node.gpv
        # endregion

        # 计算贡献差值
        delta_contrib = (node.contrib_to_parent or 0) - prev_contrib

        # region 计算奖金 财务精度: 严格 TRUNCATE(.., 2)
        if (node.gpv_real or 0) > 0:
            gpv_real_dec = Decimal(str(node.gpv_real))
            bonus_dec = (gpv_real_dec * self.elite_rate).quantize(
                Decimal('0.01'), rounding=ROUND_DOWN,
            )
            node.estimated_bonus = float(bonus_dec)
        else:
            node.estimated_bonus = 0.0
        # endregion

        status_changed = (
            prev_qualified != node.is_qualified
            or prev_path != node.qualifying_path
            or prev_q_count != len(node.qualified_downlines)
        )
        return delta_contrib, status_changed

    # =================================================================
    # 溯源记录: O(1) 写入,自动保留最小 layer
    # =================================================================

    def _track_bonus_source(
        self,
        source_user_id: str,
        bonus_user_id: str,
        layer: int,
    ) -> None:
        """
        以 source_user_id 为 key,只保留最小 layer 的归属。
        对齐 SQL: ROW_NUMBER() OVER (PARTITION BY SOURCE_USER_ID ORDER BY BONUS_LAYER) = 1
        """
        # region 获取当前用户的layer
        redis_key = f"eb_source:{self.period_num}:{source_user_id}"
        current_min = self.redis_conn.hget(redis_key, "layer")
        # endregion

        # current_min 可能是 bytes(取决于连接配置),统一兼容处理
        # region 对比参数和redis中的layer哪个最小，保留最小的更新到redis中
        if current_min is not None and isinstance(current_min, bytes):
            current_min = current_min.decode()
        if current_min is None or layer < int(current_min):
            self.redis_conn.hset(redis_key, mapping={
                "layer": layer,
                "bonus_user_id": bonus_user_id,
            })
            self.redis_conn.expire(redis_key, SOURCE_TTL_SECONDS)
        # endregion

    # =================================================================
    # 增量主入口
    # =================================================================

    def update_elite_bonus_incremental(self, user_id: str, pv_delta: int) -> None:
        """
        单笔订单触发的增量计算与传导。pv_delta 可正可负(负数 = 退单)。

        并发: 源用户 + BFS 路径上每个祖先都加锁。树结构保证锁顺序单调,无环路死锁。
        异常: 锁等待超时 / Dask 失败 → 上抛,由调用方决定重试或入死信。
        """
        acquired_locks: List[Any] = []
        try:

            # region 锁源用户
            src_lock = self.redis_conn.lock(
                f"eb_lock:{self.period_num}:{user_id}",
                timeout=LOCK_TIMEOUT,
                blocking_timeout=LOCK_BLOCKING_TIMEOUT,
            )
            if not src_lock.acquire():
                raise RuntimeError(f"获取源用户分布式锁失败: {user_id}")
            acquired_locks.append(src_lock)
            # endregion

            # region 从redis中获取源用户
            current_user = self._get_or_create_node(user_id)
            # endregion

            # region 边界保护: 防退单 / 重复退单导致 pv 穿透到负
            if (current_user.pv_pcs or 0) + pv_delta < 0:
                logger.warning(
                    "用户 %s pv_pcs 穿透负值(当前 %s, 增量 %s),本次跳过",
                    user_id, current_user.pv_pcs, pv_delta,
                )
                return
            # endregion

            # region 计算gpv
            current_user.pv_pcs = (current_user.pv_pcs or 0) + pv_delta
            current_user.gpv = (current_user.gpv or 0) + pv_delta
            # endregion

            # 获取贡献差值和状态是否改变
            delta_update, status_changed = self._evaluate_node(current_user)

            # 自归属: 本人合格且有个人消费 → 记 layer=0,压过任何祖先记录
            if current_user.is_qualified and (current_user.pv_pcs or 0) > 0:
                self._track_bonus_source(user_id, user_id, layer=0)

            models_to_save: List[EliteBonusStats] = [current_user]
            processed_nodes: Dict[str, EliteBonusStats] = {user_id: current_user}

            # 完全自消化(delta=0 且无状态变化) → 无需冒泡
            if not (delta_update == 0 and not status_changed):
                self._propagate_upward(
                    user_id=user_id,
                    initial_delta=delta_update,
                    pv_delta=pv_delta,
                    processed_nodes=processed_nodes,
                    models_to_save=models_to_save,
                    acquired_locks=acquired_locks,
                )

            # ---- 统一原子化写入 ----
            self._batch_save(models_to_save)

        finally:
            # 逆序释放;锁可能因超时被自动释放,故全部 try/except
            for lock in reversed(acquired_locks):
                try:
                    lock.release()
                except Exception:
                    pass

    def _propagate_upward(
        self,
        user_id: str,
        initial_delta: int,
        pv_delta: int,
        processed_nodes: Dict[str, EliteBonusStats],
        models_to_save: List[EliteBonusStats],
        acquired_locks: List[Any],
    ) -> None:
        """沿祖先链 BFS 冒泡,逐层加锁、读、改、加入待写"""
        # region 通过图获取该用户所有层级的祖先
        actor = self.dask_client.get_dataset("graph_actor").result()
        df_bfs = actor.get_allparent(user_id).result()
        pdf = df_bfs.sort_values("level", ascending=True)
        ancestors_info = pdf[["descendant", "predecessor", "level"]].astype(str).to_dict("records")

        delta_update = initial_delta
        # endregion

        for row in ancestors_info:
            # region 初始化
            ancestor_id = row["descendant"]
            # leg_id 是 ancestor 的直属下级分支来源
            leg_id = row["predecessor"]
            layer_distance = int(row["level"])
            # endregion

            # region ---- 祖先级锁 ----
            anc_lock = self.redis_conn.lock(
                f"eb_lock:{self.period_num}:{ancestor_id}",
                timeout=LOCK_TIMEOUT,
                blocking_timeout=LOCK_BLOCKING_TIMEOUT,
            )
            if not anc_lock.acquire():
                raise RuntimeError(f"获取祖先节点分布式锁失败: {ancestor_id}")
            acquired_locks.append(anc_lock)
            # endregion

            # region 计算父级的gpv
            ancestor = self._get_or_create_node(ancestor_id)
            ancestor.gpv = (ancestor.gpv or 0) + delta_update
            # endregion

            # region 获取leg_node
            leg_node = processed_nodes.get(leg_id)
            if leg_node is None:
                try:
                    leg_node = EliteBonusStats.get(f"{self.period_num}:{leg_id}")
                except NotFoundError:
                    leg_node = self._build_blank_node(leg_id)
            # endregion

            # region 维护"已合格直属下线"集合
            if leg_node.is_qualified:
                ancestor.qualified_downlines.add(leg_id)
            else:
                ancestor.qualified_downlines.discard(leg_id)
            # endregion

            # 获取ancestor的贡献差值和状态是否改变
            next_delta, anc_status_changed = self._evaluate_node(ancestor)

            # region 业绩被合格祖先吸收 → 记录归属
            if ancestor.is_qualified and pv_delta > 0:
                self._track_bonus_source(user_id, ancestor_id, layer=layer_distance)
            # endregion

            processed_nodes[ancestor_id] = ancestor
            models_to_save.append(ancestor)
            delta_update = next_delta

            # 安全停止: delta=0 且 祖先状态(资格/路径/合格下线集合)未变
            if delta_update == 0 and not anc_status_changed:
                break

    # =================================================================
    # 节点工厂
    # =================================================================

    def _get_or_create_node(self, user_id: str) -> EliteBonusStats:
        node_id = f"{self.period_num}:{user_id}"
        try:
            return EliteBonusStats.get(node_id)
        except NotFoundError:
            return self._build_blank_node(user_id)

    def _build_blank_node(self, user_id: str) -> EliteBonusStats:
        return EliteBonusStats(
            id=f"{self.period_num}:{user_id}",
            user_id=user_id,
            period_num=self.period_num,
        )

    def _batch_save(self, models: List[EliteBonusStats]) -> None:
        if not models:
            return
        db = EliteBonusStats.db()
        pipe = db.pipeline()
        for m in models:
            m.save(pipeline=pipe)
        pipe.execute()

    # =================================================================
    # 期末快照: Redis → 关系型库
    # =================================================================

    def snapshot_period_to_db(self, db_executor: DbExecutor) -> Dict[str, int]:
        """
        本期结束后调用一次,把所有 estimated_bonus > 0 的节点固化到 AR_CALC_BONUS_E,
        把 eb_source 链路固化到 AR_CALC_BONUS_E_SOURCE。

        :param db_executor: 调用方实现的事务批量插入函数,签名:
              def db_executor(table_name: str, rows: List[Dict]) -> None
            两张表的 INSERT 应在同一个事务中。事务提交后再调 cleanup_period。
        :return: {"bonus_count": N, "source_count": M}

        ⚠️ 性能提示: 期内总用户数百万级时,find().all() 应改为分页;
          此处实现为一次性拉全量,适合中等量级(10w 以下)。
        """
        # ---- 1. 拉本期所有合格记录 ----
        all_records = list(
            EliteBonusStats.find(
                EliteBonusStats.period_num == self.period_num
            ).all()
        )
        bonus_records = [
            r for r in all_records
            if (r.gpv_real or 0) > 0 and (r.estimated_bonus or 0) > 0
        ]

        # 收集所有需要 JOIN 用户信息的 user_id
        user_ids_to_resolve = {r.user_id for r in bonus_records}

        # ---- 2. 拉本期所有溯源记录 ----
        source_pairs: List[Tuple[str, str, int]] = []  # (source_uid, bonus_uid, layer)
        for key in self._scan_keys(f"eb_source:{self.period_num}:*"):
            data = self._safe_hgetall(key)
            if not data:
                continue
            key_str = key.decode() if isinstance(key, bytes) else key
            src_uid = key_str.rsplit(':', 1)[-1]
            bonus_uid = data.get('bonus_user_id', '')
            try:
                layer = int(data.get('layer', 0))
            except (TypeError, ValueError):
                continue
            if not bonus_uid:
                continue
            source_pairs.append((src_uid, bonus_uid, layer))
            user_ids_to_resolve.add(src_uid)
            user_ids_to_resolve.add(bonus_uid)

        # ---- 3. 一次性批量解析用户信息 ----
        user_info_map = self._user_info_resolver(list(user_ids_to_resolve))

        # ---- 4. 解析非合格 source 用户的 pv_pcs(用于 SOURCE_PV) ----
        source_pv_map: Dict[str, int] = {r.user_id: (r.pv_pcs or 0) for r in all_records}

        # ---- 5. 组装 AR_CALC_BONUS_E 行 ----
        time_str = time.strftime('%Y%m%d%H%M%S')
        bonus_rows: List[Dict[str, Any]] = []
        for idx, r in enumerate(bonus_records, start=1):
            info = user_info_map.get(r.user_id, {})
            bonus_rows.append({
                "id": f"{time_str}{str(idx).zfill(8)}",  # 14 + 8 对齐 SQL 编码
                "period_num": self.period_num,
                "calc_month": self.calc_month,
                "user_id": r.user_id,
                "parent_uid": info.get("parent_uid", "0"),
                "top_deep": info.get("top_deep", 0),
                "gpv_real": r.gpv_real,
                "e_rate": float(self.elite_rate),
                "bonus_e": r.estimated_bonus,
                "country_id": info.get("country_id", "-1"),
            })

        # ---- 6. 组装 AR_CALC_BONUS_E_SOURCE 行 ----
        source_rows: List[Dict[str, Any]] = []
        for src_uid, bonus_uid, layer in source_pairs:
            src_info = user_info_map.get(src_uid, {})
            bn_info = user_info_map.get(bonus_uid, {})
            source_rows.append({
                "period_num": self.period_num,
                "calc_month": self.calc_month,
                "bonus_user_id": bonus_uid,
                "bonus_user_name": bn_info.get("user_name", ""),
                "bonus_real_name": bn_info.get("real_name", ""),
                "source_user_id": src_uid,
                "source_user_name": src_info.get("user_name", ""),
                "source_real_name": src_info.get("real_name", ""),
                "source_pv": source_pv_map.get(src_uid, 0),
                "bonus_layer": layer,
            })

        # ---- 7. 调用方批量落盘(事务由调用方控制) ----
        if bonus_rows:
            db_executor("AR_CALC_BONUS_E", bonus_rows)
        if source_rows:
            db_executor("AR_CALC_BONUS_E_SOURCE", source_rows)

        logger.info(
            "Period %s 快照完成: bonus_rows=%d source_rows=%d",
            self.period_num, len(bonus_rows), len(source_rows),
        )
        return {
            "bonus_count": len(bonus_rows),
            "source_count": len(source_rows),
        }

    # =================================================================
    # 期末清理
    # =================================================================

    def cleanup_period(self) -> int:
        """
        清理本期所有 Redis 资源。⚠️ 必须在 snapshot 落盘并事务提交成功后才调!
        :return: 清理的 key 总数
        """
        total = 0
        patterns = [
            f"elite_bonus_stats*:{self.period_num}:*",
            f"eb_source:{self.period_num}:*",
            f"eb_lock:{self.period_num}:*",
        ]
        for pattern in patterns:
            total += self._unlink_pattern(pattern, batch_size=1000)
        logger.info("Period %s 清理完成: 释放 %d 个 key", self.period_num, total)
        return total

    # =================================================================
    # Redis 工具
    # =================================================================

    def _scan_keys(self, pattern: str, count: int = 500) -> Iterable:
        """SCAN 分页迭代,避免 KEYS 阻塞主线程"""
        return self.redis_conn.scan_iter(match=pattern, count=count)

    def _safe_hgetall(self, key: Any) -> Dict[str, str]:
        """兼容 decode_responses 开/关两种连接配置,统一返回 str dict"""
        raw = self.redis_conn.hgetall(key)
        if not raw:
            return {}
        return {
            (k.decode() if isinstance(k, bytes) else k):
            (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }

    def _unlink_pattern(self, pattern: str, batch_size: int = 1000) -> int:
        """SCAN + UNLINK 异步删除,不阻塞 Redis 主线程"""
        total = 0
        pipe = self.redis_conn.pipeline()
        batch = 0
        for key in self._scan_keys(pattern, count=batch_size):
            pipe.unlink(key)
            batch += 1
            total += 1
            if batch >= batch_size:
                pipe.execute()
                pipe = self.redis_conn.pipeline()
                batch = 0
        if batch > 0:
            pipe.execute()
        return total
