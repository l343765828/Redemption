import logging
import time
import json
from typing import Dict, List, Optional, Set, Any, Tuple
import redis
from dask.distributed import Client
from redis_om import NotFoundError
import Model.User.UserLevel as UserLevel
from Model.User.UserStats import UserStats
from Common.AmountModelAdapter import build_factory_amount_fields
from Redishelper.PVAmountConfigProvider import (
    PVAmountConfigProvider,
    PVAmountRunConfig,
    PVAmountRunSession,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [UserStatsService] %(message)s'
)
logger = logging.getLogger(__name__)

ELITE_MARK = 1000
VIRTUAL_MARK = 2000
SCHEDULE_ADDRESS = "tcp://127.0.0.1:8786"

# ---------- 锁配置 ----------
LOCK_TIMEOUT = 300
LOCK_BLOCKING_TIMEOUT = 10
LOCK_MAX_RETRIES = 5
LOCK_RETRY_BASE_SLEEP = 0.2
LOCK_REFRESH_INTERVAL = 50


# =====================================================================
# 异常分类
# =====================================================================
class BusyLockError(RuntimeError):
    """获取锁失败 (争用), 可重试。"""


class StaleLockError(RuntimeError):
    """锁已经丢失/过期, 可重试。"""


class UserStatsService:
    """
    ⚠️【架构前提声明】:
    由于无锁查图 (Dask BFS) 与获取 Redis 锁之间存在时间差, 本模块假设:
    父子树状关系变更 (如跳线、团队重组) 属于低频高优操作。
    业务系统必须在全局维度进行排他隔离 (例如: 重组时全局封板),
    禁止与日常订单的 BV 冒泡并发, 否则极小概率下可能导致向旧的祖先链错误传导业绩。
    """

    def _load_ancestors_info(self, user_id: str, graph_actor=None) -> List[Dict[str, Any]]:
        owns_client = False
        client = None
        try:
            # region 获取userId的所有上级
            if graph_actor is None:
                client = Client(SCHEDULE_ADDRESS)
                owns_client = True
                dataset = client.get_dataset("graph_actor")
                graph_actor = dataset.result()

            fut = graph_actor.get_allparent(str(user_id))
            df_bfs = fut.result()
            # endregion

            # region 验证图 Actor 输出合同
            if df_bfs is None:
                return []

            required_columns = {"ancestor", "predecessor", "level"}
            missing_columns = required_columns - set(df_bfs.columns)
            if missing_columns:
                raise RuntimeError(
                    f"get_allparent 缺少必要列: {missing_columns}"
                )
            if len(df_bfs) == 0:
                return []
            # endregion

            # region 按level排序 并换成对象list
            # graph_actor 对上级节点使用 ancestor；服务内部沿用 descendant 作为祖先节点键。
            pdf = df_bfs.rename(columns={"ancestor": "descendant"}).sort_values(
                "level",
                ascending=True,
            )

            rows = pdf[["descendant", "predecessor", "level"]].astype({
                "descendant": str, "predecessor": str, "level": int
            }).to_dict("records")
            # endregion

            # region 去重处理
            seen = set()
            out = []
            for row in rows:
                ancestor_id = row["descendant"]
                leg_id = row["predecessor"]
                key = (ancestor_id, leg_id)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "descendant": ancestor_id,
                    "predecessor": leg_id,
                    "level": int(row["level"])
                })
            return out
            # endregion
        finally:
            if owns_client and client is not None:
                client.close()

    def _get_or_init_user(self, period: str, user_id: str, run_config: PVAmountRunConfig) -> UserStats:
        """
        获取用户 stats; Redis 中不存在时返回零值的新对象 (不在此处落库,
        由后续 _save_models_pipeline 统一写回).

        本服务把 Redis 视为按月重置的缓存层: 月初被清空, 真正的持久存储
        在下游系统. 月内第一次拿到该用户的订单时, Redis 里必然查不到,
        这是"该用户本月零业绩起点"的正常语义, 不是数据异常.
        """
        user_id = str(user_id)
        record_pk = f"{period}:{user_id}"

        try:
            u = UserStats.get(record_pk)
        except NotFoundError:
            u = UserStats(
                pk=record_pk,
                id=user_id,
                period=period,
                user_id=user_id,
                pv=0,
                gpv=0,
                gpv_real=0,
                gpv_unreal=0,
                contrib=0,
                is_elite=False,
                virtual_width=0,
                rank=UserLevel.NOTHING,
                qualified_legs=set(),
                **build_factory_amount_fields(run_config.state),
            )
        self._normalize_qualified_legs(u)
        # 每次加载时按当前 gpv 重新派生，避免快照/下游读取到空值。
        self._recalc_gpv_real_unreal(u)
        return u

    @staticmethod
    def _lock_sort_key(user_id: str):
        s = str(user_id)
        try:
            return 0, int(s)
        except Exception:
            return 1, s

    @staticmethod
    def _normalize_qualified_legs(user: UserStats) -> Set[str]:
        legs = user.qualified_legs
        if legs is None:
            legs = set()
        elif not isinstance(legs, set):
            legs = set(legs)
        user.qualified_legs = legs
        return legs

    @staticmethod
    def _calc_virtual_width(gpv: int) -> int:
        if gpv >= VIRTUAL_MARK:
            return gpv // ELITE_MARK
        return 0

    @staticmethod
    def _calc_gpv_real_unreal(gpv: int) -> Tuple[int, int]:
        """
        按 PE/SE 晋级口径把 GPV 拆成真实业绩和虚拟业绩。

        业务含义：
        - GPV < 2000：未启动虚拟宽度，全部 GPV 都是真实业绩；
        - GPV >= 2000：启动虚拟宽度，真实业绩封顶为 1000，
          超出 1000 的部分作为 gpv_unreal。

        注意：
        virtual_width = floor(gpv / 1000)，表示“虚拟宽度数量”；
        gpv_unreal = gpv - 1000，表示“虚拟业绩数值”。
        二者不是同一个字段。
        """
        gpv = int(gpv or 0)
        if gpv < 0:
            gpv = 0

        if gpv >= VIRTUAL_MARK:
            return ELITE_MARK, gpv - ELITE_MARK
        return gpv, 0

    @staticmethod
    def _recalc_gpv_real_unreal(user: UserStats) -> None:
        user.gpv_real, user.gpv_unreal = UserStatsService._calc_gpv_real_unreal(user.gpv or 0)

    @staticmethod
    def _recalc_rank(user: UserStats) -> None:
        """重新计算 rank 状态。同时维护 is_elite, virtual_width, gpv_real, gpv_unreal。"""
        gpv = user.gpv or 0
        legs = UserStatsService._normalize_qualified_legs(user)

        # 同步维护 PE/SE 需要的真实/虚拟业绩拆分。
        UserStatsService._recalc_gpv_real_unreal(user)

        # region 判断该用户是否能成为elite，或是elite降级
        is_self_elite = gpv >= ELITE_MARK
        user.is_elite = is_self_elite
        # endregion

        # 计算虚拟宽度的虚拟下级数量
        user.virtual_width = UserStatsService._calc_virtual_width(gpv)

        # region 综合评定当前用户的最终 Rank
        total_elite_width = len(legs) + (user.virtual_width or 0)

        if total_elite_width >= 3:
            user.rank = UserLevel.SUPER_ELITE
        elif (is_self_elite and total_elite_width >= 1) or (
                not is_self_elite and total_elite_width >= 2
        ):
            user.rank = UserLevel.PRO_ELITE
        elif is_self_elite:
            user.rank = UserLevel.ELITE
        else:
            user.rank = UserLevel.NOTHING
        # endregion

    @staticmethod
    def _calc_contrib(user: UserStats) -> int:
        """临时贡献度: 达标截断, 向上贡献为 0。"""
        gpv = user.gpv or 0
        return gpv if gpv < ELITE_MARK else 0

    @staticmethod
    def _is_leg_qualified(leg_node: UserStats) -> bool:
        """文档定义的合格线判定:
        - 直属下线本人达到 Elite, 或
        - 直属下线本人未达标但其下方拥有 >= 1 条合格线 (即未断链)
        注: virtual_width > 0 必然伴随 rank >= ELITE, 所以无需重复检查.
        """
        rank = leg_node.rank or 0
        if rank >= UserLevel.ELITE:
            return True
        legs = leg_node.qualified_legs
        if legs is None:
            return False
        return len(legs) > 0

    def _acquire_locks(self, redis_conn, period: str, user_ids: List[str]):
        """有序批量拿锁。"""
        unique_ids = sorted(set(str(x) for x in user_ids), key=self._lock_sort_key)
        acquired = []

        try:
            for uid in unique_ids:
                lock = redis_conn.lock(
                    f"us_lock:{period}:{uid}",
                    timeout=LOCK_TIMEOUT,
                    blocking_timeout=LOCK_BLOCKING_TIMEOUT,
                    thread_local=True,
                )
                ok = lock.acquire(blocking=True)
                if not ok:
                    raise BusyLockError(f"获取用户锁失败: {uid} (period: {period})")
                acquired.append(lock)
            return acquired
        except Exception:
            self._release_locks(acquired)
            raise

    @staticmethod
    def _release_locks(locks) -> None:
        """逆序释放锁。"""
        for lock in reversed(locks):
            try:
                lock.release()
            except Exception:
                pass

    @staticmethod
    def _assert_locks_owned(locks) -> None:
        """写入前防并发覆盖检查。"""
        for lock in locks:
            try:
                if not lock.owned():
                    raise StaleLockError("锁已过期或不再属于当前任务")
            except StaleLockError:
                raise
            except Exception as e:
                raise StaleLockError(f"检查锁状态失败: {e}")

    @staticmethod
    def _refresh_locks(locks) -> None:
        for lock in locks:
            try:
                lock.extend(LOCK_TIMEOUT, replace_ttl=True)
            except Exception as e:
                raise StaleLockError(f"刷新锁 TTL 失败, 禁止继续写入: {e}")

    @staticmethod
    def _refresh_order_lock(order_lock) -> None:
        """为外层订单幂等锁续期。若续期失败直接抛出不可重试异常，熔断当前危险链路。"""
        if order_lock is None:
            return
        try:
            if not order_lock.owned():
                raise RuntimeError("订单全局排他锁已过期或不再属于当前任务，终止当前长链路计算。")
            order_lock.extend(LOCK_TIMEOUT, replace_ttl=True)
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"刷新订单锁 TTL 失败，禁止继续写入: {e}")

    @classmethod
    def assert_period_settlement_available(cls, period: str) -> None:
        """
        【全局统一业务守卫】：阻断任何在结算期间的数据写入或下游发奖读取。
        必须同时涵盖 GLOBAL(太阳线) 和 PLACEMENT(双轨) 双重状态检查。
        """
        redis_conn = UserStats.db()

        # 1. 查全局排他锁 (最高优先级物理隔离)
        if redis_conn.exists("system:global_recalc_lock"):
            raise RuntimeError("全局结算期冻结锁被持有，禁止订单、拓扑变更、发奖或结算读取。")

        # 2. 查太阳线全局重算状态
        global_status_raw = redis_conn.get(f"system:global_recalc_status:{period}")
        if global_status_raw:
            if isinstance(global_status_raw, bytes):
                global_status_raw = global_status_raw.decode("utf-8")
            try:
                g_status = json.loads(global_status_raw)
            except Exception:
                g_status = {"status": str(global_status_raw)}
            if g_status.get("status") in {"RUNNING", "FAILED"}:
                raise RuntimeError(f"period={period} 全局太阳线结算状态为 {g_status.get('status')}，禁止继续。")

        # 3. 查安置网双轨重算状态
        placement_status_raw = redis_conn.get(f"system:placement_recalc_status:{period}")
        if placement_status_raw:
            if isinstance(placement_status_raw, bytes):
                placement_status_raw = placement_status_raw.decode("utf-8")
            try:
                p_status = json.loads(placement_status_raw)
            except Exception:
                p_status = {"status": str(placement_status_raw)}
            if p_status.get("status") in {"RUNNING", "FAILED"}:
                raise RuntimeError(f"period={period} 双轨结算状态为 {p_status.get('status')}，禁止继续。")

    def _save_models_pipeline(self, redis_conn, models: List, done_key: Optional[str] = None,
                              done_payload: Optional[str] = None) -> None:
        """去重后通过 Pipeline 批量保存。"""
        if not models and not done_key:
            logger.info("无变更, 跳过写入。")
            return

        dedup: Dict[str, Any] = {}
        for model in models:
            cls_name = model.__class__.__name__
            period = getattr(model, "period", "")
            model_id = getattr(model, "id", "")
            dedup_key = f"{cls_name}:{period}:{model_id}"
            dedup[dedup_key] = model

        pipe = redis_conn.pipeline(transaction=True)
        for model in dedup.values():
            model.save(pipeline=pipe)

        if done_key:
            val = done_payload if done_payload else str(int(time.time()))
            pipe.set(done_key, val, ex=86400 * 7)

        pipe.execute()
        logger.info("=== 集中写入完成: 批量更新 %d 个节点 ===", len(dedup))

    # =================================================================
    # 核心更新逻辑
    # =================================================================
    def update_elite_performance(self, period: str, user_id: str, bv: int, order_id: str):
        # region 参数验证
        if not order_id:
            raise ValueError("订单增量处理必须传入 order_id 以保证幂等")
        # endregion

        # region 初始化
        period = str(period)
        user_id = str(user_id)
        bv = int(bv)
        done_key = f"system:idempotency:{period}:{order_id}:done"
        lock_key = f"system:idempotency:{period}:{order_id}:lock"
        # endregion

        # region 数据验证
        if bv == 0:
            logger.info("增量 BV 为 0, 跳过处理: period=%s, user_id=%s, order_id=%s", period, user_id, order_id)
            return
        # endregion

        # region 幂等验证（已完成订单不创建新的业务 run）
        redis_conn = UserStats.db()
        if redis_conn.exists(done_key):
            logger.warning("检测到重复订单 %s，忽略本次请求。", order_id)
            return
        # endregion

        # region 加载并冻结本次业务运行配置
        run_config = PVAmountRunSession.start(
            PVAmountConfigProvider(redis_conn)
        ).config
        # endregion

        order_lock = None
        try:
            # region 上订单锁
            order_lock = redis_conn.lock(
                lock_key,
                timeout=LOCK_TIMEOUT,
                blocking_timeout=LOCK_BLOCKING_TIMEOUT,
                thread_local=True,
            )
            if not order_lock.acquire(blocking=True):
                raise BusyLockError(f"订单正在处理中: {order_id}")
            # endregion

            # region 幂等验证
            if redis_conn.exists(done_key):
                logger.warning("拿到订单排他锁后检测到重复订单 %s，忽略本次请求。", order_id)
                return
            # endregion

            # region 获取该用户所有上级的关系表
            logger.info("开始处理用户 %s 的增量 BV: %d (期数: %s, 订单: %s)", user_id, bv, period, order_id)
            ancestors_info = self._load_ancestors_info(user_id)
            # endregion

            # region 收集所有可能参与计算的节点 (源 + 祖先)
            lock_user_ids = [user_id]
            for row in ancestors_info:
                lock_user_ids.append(str(row["descendant"]))
                lock_user_ids.append(str(row["predecessor"]))

            last_error: Optional[Exception] = None
            # endregion

            # 3. 带重试的抢锁逻辑
            for attempt in range(1, LOCK_MAX_RETRIES + 1):
                locks = []
                write_started = False

                try:
                    # region 所有id上锁，并设定时间
                    locks = self._acquire_locks(redis_conn, period, lock_user_ids)
                    self._refresh_locks(locks)
                    self._refresh_order_lock(order_lock)
                    # endregion

                    # region 幂等验证
                    if redis_conn.exists(done_key):
                        logger.warning("排队获取用户锁后，检测到订单 %s 已被其他实例完成，安全退出。", order_id)
                        return
                    # endregion

                    # region 参数初始化
                    models_to_save = []
                    processed_nodes: Dict[str, UserStats] = {}
                    # endregion

                    # ---------------------------------------------------------
                    # Step 1: 处理源用户
                    # ---------------------------------------------------------
                    # region 获取当前用户
                    current_user = self._get_or_init_user(period, user_id, run_config)
                    # endregion

                    # region 获取当前用户状态以及等级
                    prev_is_elite = current_user.is_elite
                    prev_rank = current_user.rank
                    # endregion

                    # region 计算当前elite等级
                    current_user.pv = (current_user.pv or 0) + bv
                    current_user.gpv = (current_user.gpv or 0) + bv

                    self._recalc_rank(current_user)
                    # endregion

                    # region 计算新的贡献度以及贡献差值
                    old_contrib = current_user.contrib or 0
                    # 计算临时贡献度，如果当前gpv小于1000，临时贡献度为当前gpv，否则为0
                    new_contrib = self._calc_contrib(current_user)
                    # 计算贡献差值：临时贡献度 - 当前贡献度
                    delta_update = new_contrib - old_contrib
                    current_user.contrib = new_contrib
                    # endregion

                    # region 源用户的 gpv 一定变了 (bv != 0), 将源用户信息添加到保存列表中
                    models_to_save.append(current_user)
                    processed_nodes[user_id] = current_user
                    # endregion

                    # region 判断自身资格是否有变化
                    status_changed = (
                            prev_is_elite != current_user.is_elite
                            or prev_rank != current_user.rank
                    )
                    # endregion

                    # region 早停: 贡献差值为 0 且自身资格未变 -> 不需要向上传导
                    if delta_update == 0 and not status_changed:
                        logger.info("用户 %s 的 delta_update=0 且资格未变, 停止向上冒泡。", user_id)
                        self._refresh_locks(locks)
                        self._refresh_order_lock(order_lock)
                        self._assert_locks_owned(locks)

                        if redis_conn.exists(done_key):
                            logger.warning("早停落库前最终校验检测到订单 %s 已被完成，终止脏写。", order_id)
                            return

                        write_started = True
                        done_payload = json.dumps(
                            {"period": period, "user_id": user_id, "bv": bv, "done_at": int(time.time())})
                        self._save_models_pipeline(redis_conn, models_to_save, done_key=done_key,
                                                   done_payload=done_payload)
                        return
                    # endregion

                    # ---------------------------------------------------------
                    # Step 2: 自底向上处理祖先
                    # ---------------------------------------------------------
                    for idx, row in enumerate(ancestors_info):

                        # region 获取父级节点的信息
                        ancestor_id = str(row["descendant"])
                        leg_id = str(row["predecessor"])
                        ancestor = self._get_or_init_user(period, ancestor_id, run_config)
                        # endregion

                        # region 记录父级节点的当前信息
                        legs = self._normalize_qualified_legs(ancestor)

                        prev_anc_is_elite = ancestor.is_elite
                        prev_anc_rank = ancestor.rank
                        prev_anc_width = len(legs)
                        # endregion

                        # 计算父级节点gpv：当前gpv+下级的贡献差值
                        ancestor.gpv = (ancestor.gpv or 0) + delta_update

                        # region 获取直推下级的信息
                        # 评估"本条分支"是否合格 -- 优先用 processed_nodes 里
                        # 已被本次事务修改过的最新内存态; 否则现读 Redis
                        # (该 leg 在 lock_user_ids 中, 我们持有它的锁).
                        leg_node = processed_nodes.get(leg_id)
                        if leg_node is None:
                            leg_node = self._get_or_init_user(period, leg_id, run_config)
                        # endregion

                        # region 判断直属下级这条线是否合格，这条线合格的条件是：
                        # 1. 前驱节点自己是 Elite (rank >= 1)
                        # 2. 或者前驱节点自己不是 Elite，但他底下的子孙有 Elite (leg_total_width > 0)
                        is_leg_qualified = self._is_leg_qualified(leg_node)

                        # 维护本祖先的 qualified_legs 只动当前这条分支条目;
                        # 兄弟分支由它们各自的更新流程串行修改 (它们也要锁这个祖先).
                        if is_leg_qualified:
                            legs.add(leg_id)
                        else:
                            legs.discard(leg_id)

                        ancestor.qualified_legs = legs
                        # endregion

                        # region 重新评定祖先 rank (内部会同步更新 is_elite, virtual_width)
                        self._recalc_rank(ancestor)
                        # endregion

                        # region 计算贡献差值：临时贡献度-当前贡献度
                        old_ancestor_contrib = ancestor.contrib or 0
                        # 计算临时贡献度，如果当前gpv小于1000，临时贡献度为当前gpv，否则为0
                        new_ancestor_contrib = self._calc_contrib(ancestor)
                        next_delta_update = new_ancestor_contrib - old_ancestor_contrib
                        ancestor.contrib = new_ancestor_contrib
                        # endregion

                        # region 判断自身资格是否有变化
                        anc_status_changed = (
                                prev_anc_is_elite != ancestor.is_elite
                                or prev_anc_rank != ancestor.rank
                                or prev_anc_width != len(ancestor.qualified_legs)
                        )
                        # endregion

                        # region 根据条件判断 是否保存父节点
                        # gpv_changed: 入站 delta != 0 时本祖先 gpv 一定变了;
                        # 状态变化或 gpv 变化任一为真都需要保存.
                        # 注: virtual_width 跨过 0 必然伴随 rank 变化 (>= ELITE_MARK),
                        # 因此 anc_status_changed 已经覆盖 virtual_width 的有效变化.
                        gpv_changed = (delta_update != 0)
                        should_save = gpv_changed or anc_status_changed

                        processed_nodes[ancestor_id] = ancestor
                        if should_save:
                            models_to_save.append(ancestor)
                        # endregion

                        # region 链路过长时周期性续约, 防过期
                        if idx > 0 and idx % LOCK_REFRESH_INTERVAL == 0:
                            self._refresh_locks(locks)
                            self._refresh_order_lock(order_lock)
                        # endregion

                        # region 早停: 上传业绩差值=0 且 本祖先资格状态未改变
                        # 把本层算出的 next_delta 作为给上层的输入
                        delta_update = next_delta_update

                        if delta_update == 0 and not anc_status_changed:
                            logger.info("到达上级用户 %s 时, 传导安全停止。", ancestor_id)
                            break
                        # endregion

                    # ---------------------------------------------------------
                    # Step 3: 落库前最终校验 (TOCTOU 防御 + 锁所有权状态)
                    # ---------------------------------------------------------
                    self._refresh_locks(locks)
                    self._refresh_order_lock(order_lock)
                    self._assert_locks_owned(locks)

                    if redis_conn.exists(done_key):
                        logger.warning("落库前最终校验检测到订单 %s 已被完成，终止脏写。", order_id)
                        return

                    write_started = True
                    done_payload = json.dumps(
                        {"period": period, "user_id": user_id, "bv": bv, "done_at": int(time.time())})
                    self._save_models_pipeline(redis_conn, models_to_save, done_key=done_key, done_payload=done_payload)
                    return

                except (BusyLockError, StaleLockError,
                        redis.exceptions.ConnectionError,
                        redis.exceptions.TimeoutError) as e:

                    if write_started:
                        raise RuntimeError(
                            f"写入阶段发生异常，结果可能已落库，禁止自动重试以免重复累计: "
                            f"period={period}, user_id={user_id}, order_id={order_id}, bv={bv}, error={e}"
                        ) from e

                    last_error = e
                    logger.warning("第 %d/%d 次尝试失败 (锁/网络异常): %s", attempt, LOCK_MAX_RETRIES, e)
                    sleep_seconds = LOCK_RETRY_BASE_SLEEP * (2 ** (attempt - 1))
                    time.sleep(sleep_seconds)

                finally:
                    self._release_locks(locks)

            raise RuntimeError(
                f"并发抢锁重试失败, 订单可能未处理: "
                f"period={period}, user_id={user_id}, order_id={order_id}, bv={bv}, last_error={last_error}"
            )

        finally:
            if order_lock is not None:
                try:
                    order_lock.release()
                except Exception:
                    pass