# -*- coding: utf-8 -*-
# PlacementIncrementalService.py

import json
import logging
import time
from typing import Any, Dict, List, Tuple, Optional

import redis
from dask.distributed import Client
from redis_om import NotFoundError

import Model.User.UserLevel as UserLevel
from Model.Config import SCHEDULE_ADDRESS
from Model.User.UserStats import UserStats
from Common.AmountModelAdapter import build_factory_amount_fields, require_v2_amount_record
from Common.PeriodResolver import PeriodResolver, PeriodSnapshot
from Common.PvAmount import checked_add_int64, require_units_int
from Model.Order.NormalizedPvEvent import (
    NormalizedPvEvent,
    require_normalized_pv_event,
)
from Redishelper.PVAmountConfigProvider import (
    PVAmountConfigProvider,
    PVAmountRunConfig,
    PVAmountRunSession,
)

# 引入 GlobalRecalculationService 用于联合状态检查
from User.GlobalRecalculationService import GlobalRecalculationService
from User.UserStatsService import (
    UserStatsService,
    LOCK_TIMEOUT,
    LOCK_BLOCKING_TIMEOUT,
    LOCK_MAX_RETRIES,
    LOCK_RETRY_BASE_SLEEP,
    LOCK_REFRESH_INTERVAL,
    BusyLockError,
    StaleLockError
)

logger = logging.getLogger(__name__)


class PlacementIncrementalService(UserStatsService):
    """
    双轨制（安置网 1L/2L）增量计算服务。

    架构规约：
    1. 【单一职责】：专注计算安置网的 PV_1L, PV_2L 以及对碰 TOTAL。不干涉推荐网的 GPV/等级计算。
    2. 【有序拿锁】：基于 UserStatsService 底层的有序 ID 排序机制获取 Redis 分布式锁，杜绝死锁。
    3. 【动态拓扑】：每次计算前通过 Dask 调用 graph_actor 实时查询安置网向上的闭包路径（1L/2L）。
    4. 【跨期结转】：不管本期节点是否存在，都会从上一期提取 `remain_surplus` 并补齐。
    5. 【期中口径差异】：增量逻辑仅覆盖源节点(MID1)与安置祖先(MID5)。不合并没有安置动静的推荐网团队(MID3)/存货商(MID6)状态。未覆盖部分由全量重算兜底。
    6. 【时序跨期假设】：若 N 期订单在 N-1 期对碰扣减尚未落库时到达，会带入未扣减的结余。这属于合理时序穿透，依赖周期后的全量对账补齐。

    🚨【下游契约与模型依赖硬性声明】🚨：
    - `UserStats` 模型必须包含 `placement_initialized`, `placement_settled`, `placement_revision`, `settled_revision` 四个生命周期独立字段！
    - 对碰/全量结算扣减 remain 时，必须在同一原子写内置 `placement_settled=True` 和 `settled_revision=rev`！
    - 已结算节点收到新业绩时增量会翻转 settled 为 False 递增 revision 并发送漂移事件，下游必须消费该事件触发重结算。
    """

    GLOBAL_RECALC_LOCK_KEY = "system:global_recalc_lock"
    OUTBOX_STREAM_KEY = "system:recalc_outbox_stream"
    PERIOD_CLOSED_KEY_TMPL = "system:placement_period_closed:{period}"

    STATUS_RUNNING = "RUNNING"
    STATUS_DONE = "DONE"
    STATUS_FAILED = "FAILED"

    @classmethod
    def _status_key(cls, period: str) -> str:
        return f"system:placement_recalc_status:{period}"

    def __init__(self, period_resolver: Optional[PeriodResolver] = None):
        self._period_resolver = period_resolver

    def _resolve_period_snapshot(
        self,
        period: str,
        period_snapshot: Optional[PeriodSnapshot] = None,
    ) -> PeriodSnapshot:
        snapshot = period_snapshot
        if snapshot is None:
            if self._period_resolver is None:
                raise RuntimeError("生产 period 入口必须注入 PeriodResolver 或 PeriodSnapshot")
            try:
                period_num = int(period)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"非法 period={period!r}") from exc
            snapshot = self._period_resolver.resolve_current(period_num)
        if not isinstance(snapshot, PeriodSnapshot):
            raise TypeError("period_snapshot must be PeriodSnapshot")
        if str(snapshot.period_num) != str(period):
            raise ValueError("period_snapshot 与入口 period 不一致")
        return snapshot

    def _get_prev_period(
        self,
        period: str,
        period_snapshot: Optional[PeriodSnapshot] = None,
    ) -> str:
        """从已解析的 AR_PERIOD 快照读取真实上一期，不执行本地算术。"""
        snapshot = self._resolve_period_snapshot(period, period_snapshot)
        return "" if snapshot.previous_period_num is None else str(snapshot.previous_period_num)

    def _assert_no_recalc_conflict(self, redis_conn, period: str) -> None:
        """集中抽取 TOCTOU 防御检查与封期闸门"""
        closed_key = self.PERIOD_CLOSED_KEY_TMPL.format(period=period)
        if redis_conn.exists(closed_key):
            raise RuntimeError(f"period={period} 已封期结算，迟到订单请走人工冲正通道，拒绝自动接入。")

        if redis_conn.exists(self.GLOBAL_RECALC_LOCK_KEY):
            raise RuntimeError("全局重算锁被持有，为防并发脏覆盖，放弃本次增量。")

        for key in (GlobalRecalculationService._status_key(period), self._status_key(period)):
            payload = redis_conn.get(key)
            if payload and json.loads(payload).get("status") in {self.STATUS_RUNNING, self.STATUS_FAILED}:
                raise RuntimeError(f"period={period} 发生全量状态阻塞({key})，放弃本次增量。")

    def _load_placement_ancestors(self, user_id: str, graph_actor=None) -> List[Dict[str, Any]]:
        """
        无锁查询安置网 (Placement Tree) 中该用户上层的所有祖先，及所在的区域 (Leg: 1 或 2)。
        """
        owns_client = False
        client = None
        try:
            if graph_actor is None:
                client = Client(SCHEDULE_ADDRESS)
                owns_client = True
                dataset = client.get_dataset("graph_actor")
                graph_actor = dataset.result()

            # 孤立/不存在节点的合法空跑由 GraphService 内置校验返回空表。
            fut = graph_actor.get_placement_leg_path(str(user_id))
            df_bfs = fut.result()

            if df_bfs is None or len(df_bfs) == 0:
                return []

            pdf = df_bfs.sort_values("level", ascending=True)
            rows = pdf[["ancestor", "placementLeg", "level"]].astype({
                "ancestor": str, "placementLeg": int, "level": int
            }).to_dict("records")

            out = []
            seen = set()
            for row in rows:
                anc_id = row["ancestor"]
                leg = int(row["placementLeg"])
                if anc_id in seen:
                    continue
                seen.add(anc_id)
                out.append({
                    "ancestor": anc_id,
                    "leg": leg,
                    "level": int(row["level"])
                })
            return out
        finally:
            if owns_client and client is not None:
                client.close()

    def _load_prev_surplus(
        self,
        period: str,
        user_id: str,
        period_snapshot: PeriodSnapshot,
    ) -> Tuple[int, int]:
        """加载上一期结余，消除 float 默认值。"""
        prev_period = self._get_prev_period(period, period_snapshot)
        if not prev_period:
            return 0, 0

        try:
            prev_node = UserStats.get(f"{prev_period}:{user_id}")
            require_v2_amount_record(prev_node)
            if not getattr(prev_node, "placement_settled", False):
                logger.warning("时序穿透：period=%s user=%s 继承了上期未结算 remain，待全量对账修正。", period, user_id)
            return (
                int(getattr(prev_node, "remain_surplus_1l", 0) or 0),
                int(getattr(prev_node, "remain_surplus_2l", 0) or 0),
            )
        except NotFoundError:
            return 0, 0

    def _get_or_init_user_with_surplus(
        self,
        period: str,
        user_id: str,
        run_config: PVAmountRunConfig,
        period_snapshot: PeriodSnapshot,
    ) -> Tuple[UserStats, bool, bool]:
        """
        带跨期结转机制的节点获取。
        【返回】：(节点对象, 是否曾经存在, 内部是否对节点做了修正)。
        【核心防线】：无论当期节点是否已由其他服务(如太阳线)创建，都强制补齐上期结余。
        """
        user_id = str(user_id)
        record_pk = f"{period}:{user_id}"
        existed_before = True
        changed = False

        pre_1l, pre_2l = self._load_prev_surplus(period, user_id, period_snapshot)

        try:
            u = UserStats.get(record_pk)
            require_v2_amount_record(u)
            self._normalize_qualified_legs(u)

            # 如果记录是由推荐网增量服务先行创建的，它的 pre_surplus 必为默认的 0。
            # 无条件纠正补齐，防止用户的双轨历史结余被静默洗飞！
            if int(getattr(u, "pre_surplus_1l", 0) or 0) != pre_1l:
                u.pre_surplus_1l = pre_1l
                changed = True
            if int(getattr(u, "pre_surplus_2l", 0) or 0) != pre_2l:
                u.pre_surplus_2l = pre_2l
                changed = True

            # 若尚未进行过首次桥接初始化，同步桥接结余，随后标识置位。
            if not getattr(u, "placement_initialized", False):
                if int(getattr(u, "remain_surplus_1l", 0) or 0) != pre_1l:
                    u.remain_surplus_1l = pre_1l
                    changed = True
                if int(getattr(u, "remain_surplus_2l", 0) or 0) != pre_2l:
                    u.remain_surplus_2l = pre_2l
                    changed = True
                u.placement_initialized = True
                changed = True

        except NotFoundError:
            existed_before = False
            changed = True
            u = UserStats(
                pk=record_pk, period=period, id=user_id, user_id=user_id,
                pv=0, gpv=0, gpv_real=0, gpv_unreal=0, contrib=0,
                is_elite=False, virtual_width=0, rank=UserLevel.NOTHING, qualified_legs=set(),
                pv_1l=0, pv_2l=0, total_1l=0, total_2l=0,
                pre_surplus_1l=pre_1l, pre_surplus_2l=pre_2l,
                remain_surplus_1l=pre_1l, remain_surplus_2l=pre_2l,
                placement_initialized=True,
                placement_settled=False,
                placement_revision=0,
                settled_revision=0,
                **build_factory_amount_fields(run_config.state),
            )

        return u, existed_before, changed

    def _apply_mid8_logic(self, node: UserStats, has_activity: bool) -> None:
        """
        【安置网 MID8 计算逻辑】：融合 PV 新增与结余。
        若有活动，结余进入 TOTAL 供对碰。增量服务不碰 remain，保障下游对碰结果不被覆盖冲刷。
        """
        pv_1l = require_units_int(node.pv_1l or 0, "pv_1l")
        pv_2l = require_units_int(node.pv_2l or 0, "pv_2l")
        pre_1l = require_units_int(node.pre_surplus_1l or 0, "pre_surplus_1l")
        pre_2l = require_units_int(node.pre_surplus_2l or 0, "pre_surplus_2l")

        if has_activity or (node.pv or 0) != 0 or pv_1l != 0 or pv_2l != 0:
            node.total_1l = checked_add_int64(pv_1l, pre_1l)
            node.total_2l = checked_add_int64(pv_2l, pre_2l)
        else:
            node.total_1l = 0
            node.total_2l = 0

    def _save_placement_pipeline(
            self, redis_conn, models: List[UserStats], outbox_events: List[Dict[str, Any]], done_key: str, period: str
    ) -> None:
        """原子化落库与发送 Drift 事件（提交点带封期/重算 WATCH 闸门）"""
        closed_key = self.PERIOD_CLOSED_KEY_TMPL.format(period=period)
        pipe = redis_conn.pipeline(transaction=True)
        try:
            pipe.watch(closed_key, self.GLOBAL_RECALC_LOCK_KEY)
            if pipe.exists(closed_key) or pipe.exists(self.GLOBAL_RECALC_LOCK_KEY):
                raise RuntimeError(f"提交时刻检测到封期/重算(period={period})，安全放弃，未产生任何写入。")

            pipe.multi()
            dedup = {f"{m.period}:{m.id}": m for m in models}
            for model in dedup.values():
                model.save(pipeline=pipe)

            for event in outbox_events:
                pipe.xadd(
                    name=self.OUTBOX_STREAM_KEY,
                    fields={"payload": json.dumps(event, ensure_ascii=False, default=str)},
                    maxlen=100000,
                    approximate=True
                )

            pipe.set(done_key, "1")
            pipe.execute()
        except redis.exceptions.WatchError:
            raise RuntimeError(f"提交原子中止：封期/重算键在提交瞬间变更(period={period})，未产生任何写入，可安全重试。")
        finally:
            pipe.reset()
        logger.info("=== 双轨增量原子落库完成: 更新 %d 个节点, 发送 %d 个对账事件 ===", len(models), len(outbox_events))

    # =================================================================
    # 核心：双轨制增量更新逻辑
    # =================================================================
    def update_placement_performance(
        self,
        period: Optional[str] = None,
        user_id: Optional[str] = None,
        bv: Optional[int] = None,
        order_id: Optional[str] = None,
        *,
        normalized_event: Optional[NormalizedPvEvent] = None,
    ):
        """处理安置网增量；生产 v2 入口必须传入同一 normalized event。"""
        # region 归一化事件合同
        if normalized_event is not None:
            event = require_normalized_pv_event(normalized_event)
            if user_id is None:
                raise ValueError("normalized event stage 必须传入 user_id")
            return self._update_placement_performance_units(
                period=str(event.period_snapshot.period_num),
                user_id=str(user_id),
                bv=event.effective_pv_delta_units,
                order_id=event.identity,
                period_snapshot=event.period_snapshot,
            )
        # endregion

        # region 旧入口兼容适配
        if period is None or user_id is None or order_id is None:
            raise ValueError("legacy adapter requires period, user_id and order_id")
        if not isinstance(bv, int) or isinstance(bv, bool):
            raise TypeError("legacy bv must already be strict units int")
        done_key = f"system:idempotency:placement:{period}:{order_id}:done"
        redis_conn = UserStats.db()
        if redis_conn.exists(done_key):
            logger.warning("检测到双轨重复订单 %s，忽略本次请求。", order_id)
            return
        snapshot = self._resolve_period_snapshot(str(period))
        return self._update_placement_performance_units(
            str(period), str(user_id), bv, str(order_id), snapshot
        )
        # endregion

    def _update_placement_performance_units(
        self,
        period: str,
        user_id: str,
        bv: int,
        order_id: str,
        period_snapshot: PeriodSnapshot,
    ):
        if not order_id:
            raise ValueError("双轨增量处理必须传入 order_id 以保证幂等")

        if not isinstance(bv, int) or isinstance(bv, bool):
            raise ValueError(
                f"BV 必须为公共金额层定义的 strict units int，拒绝静默转换: bv={bv!r} ({type(bv).__name__})")

        period = str(period)
        period_snapshot = self._resolve_period_snapshot(period, period_snapshot)
        user_id = str(user_id)
        done_key = f"system:idempotency:placement:{period}:{order_id}:done"
        lock_key = f"system:idempotency:placement:{period}:{order_id}:lock"

        # region 幂等验证（已完成订单不创建新的业务 run）
        redis_conn = UserStats.db()
        if redis_conn.exists(done_key):
            logger.warning("检测到双轨重复订单 %s，忽略本次请求。", order_id)
            return
        # endregion

        # region 零增量完成态
        if bv == 0:
            # 零增量不改变双轨状态，但必须写完成键，使已 ACK 事件保留完整三链证据。
            self._save_placement_pipeline(redis_conn, [], [], done_key, period)
            logger.info(
                "双轨增量 BV 为 0, 跳过业务状态并记录 stage 完成态: "
                "period=%s, user_id=%s, order_id=%s",
                period,
                user_id,
                order_id,
            )
            return
        # endregion

        # region 加载并冻结本次业务运行配置
        run_config = PVAmountRunSession.start(
            PVAmountConfigProvider(redis_conn)
        ).config
        # endregion

        order_lock = None
        try:
            order_lock = redis_conn.lock(
                lock_key, timeout=LOCK_TIMEOUT, blocking_timeout=LOCK_BLOCKING_TIMEOUT, thread_local=True
            )
            if not order_lock.acquire(blocking=True):
                raise BusyLockError(f"订单双轨计算正在处理中: {order_id}")

            if redis_conn.exists(done_key):
                return

            self._assert_no_recalc_conflict(redis_conn, period)

            logger.info("开始处理用户 %s 的双轨增量 BV: %d (订单: %s)", user_id, bv, order_id)
            ancestors_info = self._load_placement_ancestors(user_id)

            lock_user_ids = [user_id] + [str(x["ancestor"]) for x in ancestors_info]
            last_error: Optional[Exception] = None

            for attempt in range(1, LOCK_MAX_RETRIES + 1):
                locks = []
                write_started = False

                try:
                    locks = self._acquire_locks(redis_conn, period, lock_user_ids)
                    self._refresh_locks(locks)
                    self._refresh_order_lock(order_lock)

                    self._assert_no_recalc_conflict(redis_conn, period)

                    if redis_conn.exists(done_key):
                        return

                    models_to_save = []
                    outbox_events = []
                    processed_nodes: Dict[str, UserStats] = {}

                    # ---------------------------------------------------------
                    # Step A: 激活本人 (源节点) 的对碰合并状态
                    # ---------------------------------------------------------
                    node_self, existed_self, dirty_self = self._get_or_init_user_with_surplus(
                        period, user_id, run_config, period_snapshot
                    )
                    processed_nodes[user_id] = node_self

                    old_t1, old_t2 = node_self.total_1l, node_self.total_2l
                    old_r1, old_r2 = node_self.remain_surplus_1l, node_self.remain_surplus_2l
                    was_settled_self = bool(getattr(node_self, "placement_settled", False))

                    self._apply_mid8_logic(node_self, has_activity=True)

                    totals_changed_self = (old_t1 != node_self.total_1l or old_t2 != node_self.total_2l)
                    if totals_changed_self:
                        node_self.placement_revision = int(getattr(node_self, "placement_revision", 0) or 0) + 1

                    invalidated_self = was_settled_self and totals_changed_self
                    if invalidated_self:
                        node_self.placement_settled = False
                        dirty_self = True

                    if invalidated_self or dirty_self or not existed_self or totals_changed_self or old_r1 != node_self.remain_surplus_1l or old_r2 != node_self.remain_surplus_2l:
                        models_to_save.append(node_self)
                        outbox_events.append({
                            "event_type": "PLACEMENT_INCREMENTAL_DRIFT",
                            "period": period, "user_id": user_id, "order_id": order_id,
                            "drift_details": {
                                "total_1l": [old_t1, node_self.total_1l], "total_2l": [old_t2, node_self.total_2l],
                                "remain_1l": [old_r1, node_self.remain_surplus_1l],
                                "remain_2l": [old_r2, node_self.remain_surplus_2l],
                                "settlement_invalidated": invalidated_self,
                                "placement_revision": getattr(node_self, "placement_revision", 0)
                            },
                            "timestamp": int(time.time())
                        })

                    # ---------------------------------------------------------
                    # Step B: 自底向上处理各级安置树祖先
                    # ---------------------------------------------------------
                    for idx, row in enumerate(ancestors_info):
                        anc_id = str(row["ancestor"])
                        leg = int(row["leg"])

                        if anc_id in processed_nodes:
                            anc_node = processed_nodes[anc_id]
                            existed_anc = True
                            dirty_anc = False
                        else:
                            anc_node, existed_anc, dirty_anc = self._get_or_init_user_with_surplus(
                                period, anc_id, run_config, period_snapshot
                            )
                            processed_nodes[anc_id] = anc_node

                        o_pv1, o_pv2 = anc_node.pv_1l, anc_node.pv_2l
                        o_t1, o_t2 = anc_node.total_1l, anc_node.total_2l
                        was_settled_anc = bool(getattr(anc_node, "placement_settled", False))

                        if leg == 1:
                            anc_node.pv_1l = checked_add_int64(anc_node.pv_1l or 0, bv)
                        elif leg == 2:
                            anc_node.pv_2l = checked_add_int64(anc_node.pv_2l or 0, bv)
                        else:
                            raise ValueError(f"非法的安置区 leg={leg}")

                        self._apply_mid8_logic(anc_node, has_activity=True)

                        perf_changed = (
                                    o_pv1 != anc_node.pv_1l or o_pv2 != anc_node.pv_2l or o_t1 != anc_node.total_1l or o_t2 != anc_node.total_2l)

                        if perf_changed:
                            anc_node.placement_revision = int(getattr(anc_node, "placement_revision", 0) or 0) + 1

                        invalidated_anc = was_settled_anc and perf_changed
                        if invalidated_anc:
                            anc_node.placement_settled = False

                        if invalidated_anc or dirty_anc or not existed_anc or perf_changed:
                            models_to_save.append(anc_node)
                            outbox_events.append({
                                "event_type": "PLACEMENT_INCREMENTAL_DRIFT",
                                "period": period, "user_id": anc_id, "order_id": order_id,
                                "drift_details": {
                                    "pv_1l": [o_pv1, anc_node.pv_1l], "pv_2l": [o_pv2, anc_node.pv_2l],
                                    "total_1l": [o_t1, anc_node.total_1l], "total_2l": [o_t2, anc_node.total_2l],
                                    "settlement_invalidated": invalidated_anc,
                                    "placement_revision": getattr(anc_node, "placement_revision", 0)
                                },
                                "timestamp": int(time.time())
                            })

                        if idx > 0 and idx % LOCK_REFRESH_INTERVAL == 0:
                            self._refresh_locks(locks)
                            self._refresh_order_lock(order_lock)

                    # ---------------------------------------------------------
                    # Step C: 原子提交 (包含最终的 TOCTOU 极限防御)
                    # ---------------------------------------------------------
                    self._refresh_locks(locks)
                    self._refresh_order_lock(order_lock)
                    self._assert_locks_owned(locks)

                    self._assert_no_recalc_conflict(redis_conn, period)

                    if redis_conn.exists(done_key):
                        return

                    write_started = True
                    if models_to_save or outbox_events:
                        self._save_placement_pipeline(redis_conn, models_to_save, outbox_events, done_key, period)
                    else:
                        self._save_placement_pipeline(redis_conn, [], [], done_key, period)
                    return

                except (
                BusyLockError, StaleLockError, redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
                    if write_started:
                        raise RuntimeError(
                            f"写入阶段异常，订单可能部分落库，禁重试以免双计: order_id={order_id}, err={e}") from e
                    last_error = e
                    sleep_seconds = LOCK_RETRY_BASE_SLEEP * (2 ** (attempt - 1))
                    time.sleep(sleep_seconds)
                finally:
                    self._release_locks(locks)

            raise RuntimeError(f"并发抢锁重试失败, 双轨订单流产: user={user_id}, order_id={order_id}, err={last_error}")

        finally:
            if order_lock is not None:
                try:
                    order_lock.release()
                except Exception:
                    pass