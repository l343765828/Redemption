# GlobalRecalculationService.py

import json
import logging
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dask.distributed import Client
from redis_om import NotFoundError

import Model.User.UserLevel as UserLevel
from Model.User.UserStats import UserStats
from Model.User.UserPeriodHighestRank import UserPeriodHighestRank
from User.UserStatsService import (
    UserStatsService,
    SCHEDULE_ADDRESS,
)

logger = logging.getLogger(__name__)


class GlobalRecalculationService(UserStatsService):
    """
    全局单期结算服务。

    架构规约：
    1. 【绝不回算历史】：不考虑跨期连锁反应。人工修改历史不归本服务管。
    2. 【绝不读历史图】：永远读取当前 GraphService 提供的最新全局图谱。
    3. 【当期草稿本】：UserStats 仅作为当期计算草稿，算完后随 TTL 自然消亡/归档。
    4. 【荣誉权威表】：UserPeriodHighestRank 作为最终结算产物，永久保留供追溯。
    5. 【单期状态锁】：拦截粒度细化至 period。
    6. 【全局算力锁】：保护 Dask/GPU 计算资源，带有心跳续期机制。
    7. 【事务发件箱】：状态修复(UserStats) + 荣誉表(UserPeriodHighestRank) + 不一致/漏算
       审计事件，在同一个 Redis 事务(MULTI/EXEC)中原子化写入 (Transactional Outbox)，
       三者要么全部成功、要么全部失败。
    8. 【整期完成哨兵】：settle_period 成功收尾时，在同一个 Redis 事务中原子写入
       DONE 状态 + SETTLEMENT_PERIOD_DONE 事件，供需要"等整期完成"语义的下游订阅。
       FAILED 路径不发哨兵——普通事件即发即用，描述的是已经在 Redis 落地的真实局部修正；
       哨兵单独作为"整期成功"的信号。
    """

    GLOBAL_RECALC_LOCK_KEY = "system:global_recalc_lock"

    # =========================================================================
    # 【Outbox 下游消费契约 —— 接入 Kafka Relay / 任何消费端的同事请先读这段】
    #
    # 本 Stream 承载两类事件，消费时机完全不同：
    # ... (此处省略契约注释，保持与原版一致) ...
    # =========================================================================
    OUTBOX_STREAM_KEY = "system:recalc_outbox_stream"

    STATUS_RUNNING = "RUNNING"
    STATUS_DONE = "DONE"
    STATUS_FAILED = "FAILED"

    LOCK_TTL_SECONDS = 60 * 60
    DASK_RESULT_TIMEOUT_SECONDS = 30 * 60

    PARENT_PAGE_SIZE = 5000
    CHILD_PAGE_SIZE = 2000

    MAX_PARENT_PAGES_PER_DEPTH = 100_000
    MAX_CHILD_PAGES_PER_PARENT = 100_000

    @classmethod
    def _status_key(cls, period: str) -> str:
        return f"system:global_recalc_status:{period}"

    @staticmethod
    def _get_previous_period(period) -> str:
        """
        推导上一期期数。
        实际 period 为 MySQL 自增整数，且连续不断：
        1 -> 无上一期，返回空字符串
        2 -> "1"
        5 -> "4"
        """
        try:
            period_int = int(period)
        except (ValueError, TypeError):
            # 拒绝静默失败：非法期数直接抛出异常，防止错误地把历史高水位记录覆盖归零
            raise ValueError(f"非法 period={period!r}，期数必须是连续自增整数")

        if period_int < 1:
            raise ValueError(f"非法 period={period!r}，期数必须 >= 1")

        if period_int == 1:
            return ""

        return str(period_int - 1)

    def settle_period(
            self,
            period,
            *,
            write_zero_nodes: bool = True,
    ) -> None:
        """
        单期期数结算入口。
        全局重算入口。

        Args:
            :param write_zero_nodes:
                True：
                    对 Redis 中不存在的图中用户，即使重算后为零，也创建 UserStats；
                    已存在且派生状态未变化的 UserStats 不会重复保存。
                False：
                    不创建全零 UserStats；
                    只保存发生漂移的节点，或新出现的非零节点。
            :param period: 期数 (支持传入 int 或 str，内部统一强转为 str)

        失败恢复策略：
            当前实现是原地写 Redis。
            任意失败后会标记 FAILED。
            恢复时建议重新从 max_depth 到 0 完整跑一遍。
        """
        # 强制转换为字符串，确保下游 Redis 键名与 payload 口径 100% 统一
        period = str(period)

        # region 上redis锁
        redis_conn = UserStats.db()
        run_id = str(uuid.uuid4())
        status_key = self._status_key(period)

        lock = redis_conn.lock(
            self.GLOBAL_RECALC_LOCK_KEY,
            timeout=self.LOCK_TTL_SECONDS,
            blocking_timeout=0,
            thread_local=True,
        )

        lock_acquired = lock.acquire(blocking=False)
        if not lock_acquired:
            raise RuntimeError(f"全局结算锁被持有，无法触发 {period} 的结算任务。")
        # endregion

        client: Optional[Client] = None

        try:
            # region 设置redis状态，禁止在此时进行订单处理或拓扑变更
            logger.info("开始单期结算 period=%s run_id=%s", period, run_id)
            self._set_period_settlement_status(redis_conn, status_key, self.STATUS_RUNNING, run_id)
            # endregion

            # region 验证图谱完整性
            client = Client(SCHEDULE_ADDRESS)

            graph_actor = self._await_actor_result(client.get_dataset("graph_actor"))
            if not graph_actor:
                raise RuntimeError("未在 Dask 集群中找到 graph_actor")

            logger.info("开始执行全局图完整性校验 run_id=%s", run_id)
            self._refresh_global_lock(lock)
            self._set_period_settlement_status(redis_conn, status_key, self.STATUS_RUNNING, run_id,
                                               {
                                                   "phase": "validating_graph",
                                                   "write_zero_nodes": write_zero_nodes,
                                               })
            # GraphService 必须在 Dask / cuDF / cuGraph 侧完成
            self._await_actor_result(graph_actor.validate_graph_integrity())
            # endregion

            # region 获取总深度
            self._refresh_global_lock(lock)
            max_depth = int(self._await_actor_result(graph_actor.get_max_root_depth()))
            logger.info("图完整性校验通过 max_depth=%s period=%s", max_depth, period)
            self._set_period_settlement_status(redis_conn, status_key, self.STATUS_RUNNING, run_id,
                                               {
                                                   "phase": "recalculating",
                                                   "max_depth": max_depth,
                                                   "current_depth": max_depth,
                                               })
            # endregion

            # region 处理当前层的所有节点
            for depth in range(max_depth, -1, -1):
                logger.info("开始处理 depth=%d period=%s run_id=%s", depth, period, run_id)
                parent_cursor: Optional[Any] = None
                parent_page_count = 0

                # 开始分页处理当前层的信息
                while True:
                    parent_page_count += 1

                    # region 验证 防止死循环
                    if parent_page_count > self.MAX_PARENT_PAGES_PER_DEPTH:
                        raise RuntimeError(
                            f"depth={depth} 超过最大 parent 页数 "
                            f"{self.MAX_PARENT_PAGES_PER_DEPTH}，疑似 cursor 不收敛。"
                        )
                    # endregion

                    # region 锁续期
                    self._refresh_global_lock(lock)
                    # endregion

                    # region 取出当页数据 和 下一页的第一条数据
                    page = self._await_actor_result(
                        graph_actor.get_nodes_at_depth_page(depth, parent_cursor, self.PARENT_PAGE_SIZE)
                    )
                    batch_parent_ids, next_parent_cursor = self._parse_page_result(page)
                    batch_parent_ids = [str(x) for x in batch_parent_ids]
                    # endregion

                    # region 验证
                    if not batch_parent_ids:
                        if next_parent_cursor is not None:
                            raise RuntimeError(
                                f"GraphService 分页契约错误：depth={depth} 返回空 items，"
                                f"但 next_cursor={next_parent_cursor} 非空。"
                            )
                        break
                    # endregion

                    # region 处理当前层的节点数据，算出gpv、贡献度、等级
                    logger.info(
                        "处理 parent batch run_id=%s depth=%s batch_size=%s cursor=%s",
                        run_id,
                        depth,
                        len(batch_parent_ids),
                        parent_cursor,
                    )
                    self._process_parent_batch(
                        graph_actor=graph_actor,
                        parent_ids=batch_parent_ids,
                        period=period,
                        run_id=run_id,
                        redis_conn=redis_conn,
                        write_zero_nodes=write_zero_nodes,
                        lock=lock
                    )
                    # endregion

                    # region 更新redis状态
                    self._set_period_settlement_status(redis_conn, status_key, self.STATUS_RUNNING, run_id,
                                                       {
                                                           "phase": "recalculating",
                                                           "max_depth": max_depth,
                                                           "current_depth": depth,
                                                           "next_parent_cursor": next_parent_cursor,
                                                           "parent_page_count": parent_page_count,
                                                       })
                    # endregion

                    # region 更新游标 如果为空 跳出循环
                    parent_cursor = next_parent_cursor
                    if parent_cursor is None:
                        break
                    # endregion
            # endregion

            # region 哨兵事件 -> 整个计算过程已经结束
            self._emit_settlement_done(
                redis_conn=redis_conn,
                status_key=status_key,
                period=period,
                run_id=run_id,
                max_depth=max_depth,
                write_zero_nodes=write_zero_nodes,
            )
            logger.info("单期结算圆满完成 period=%s run_id=%s", period, run_id)
            # endregion

        except Exception as e:
            logger.exception("单期结算失败 period=%s run_id=%s", period, run_id)
            try:
                self._set_period_settlement_status(
                    redis_conn, status_key, self.STATUS_FAILED, run_id, extra={"error": repr(e)}
                )
            except Exception as set_err:
                logger.error("标记 FAILED 失败 run_id=%s: %s", run_id, set_err)
            raise

        finally:
            if client is not None:
                try:
                    client.close()
                except Exception as close_err:
                    logger.warning("关闭 Dask Client 失败: %s", close_err)

            try:
                if lock.owned():
                    lock.release()
            except Exception as release_err:
                logger.warning("释放全局重算锁失败，等待 TTL 自动过期: %s", release_err)

    @staticmethod
    def _extract_comparable_state(node: UserStats) -> Dict[str, Any]:
        """提取用于比对的核心业务推导状态 (序列化安全)"""
        return {
            "gpv": node.gpv or 0,
            "contrib": node.contrib or 0,
            "rank": node.rank or UserLevel.NOTHING,
            "is_elite": bool(node.is_elite),
            "virtual_width": node.virtual_width or 0,
            "qualified_legs": sorted(list(node.qualified_legs or set()))
        }

    @classmethod
    def _has_state_changed(cls, old_state: Dict[str, Any], new_node: UserStats) -> bool:
        """判断重算前后的推导状态是否发生实质性不一致"""
        new_state = cls._extract_comparable_state(new_node)
        return old_state != new_state

    def _process_parent_batch(
            self,
            *,
            graph_actor,
            parent_ids: List[str],
            period: str,
            run_id: str,
            redis_conn,
            write_zero_nodes: bool,
            lock
    ) -> None:
        """
        处理一批同 depth 的父节点。

        关键点：
        1. 不一次性拉取 parent 的全部 child。
        2. 每个 parent 的 child 通过 get_direct_children_page 分页读取。
        3. child stats 也按页读取，避免大象节点击穿内存。
        4. write_zero_nodes=False 时，只跳过 Redis 原本不存在且重算后为零状态的用户。
        """

        # region 验证
        if not parent_ids:
            return
        # endregion

        # region 从redis获取parent_ids的所有实体
        parent_lookup = self._mget_users_with_exists(parent_ids, period)
        models_to_save: List[UserStats] = []
        outbox_events: List[Dict[str, Any]] = []
        honor_records: List[UserPeriodHighestRank] = []
        # endregion

        for pid in parent_ids:
            # region 获取p_node与旧状态快照
            self._refresh_global_lock(lock)
            p_node, existed_before = parent_lookup[pid]

            # 1. 在重算前，拍下核心状态的快照
            old_state = self._extract_comparable_state(p_node)
            # endregion

            # region 复位数据 gpv仅保留基础的pv
            self._reset_derived_state_keep_pv(p_node)
            # endregion

            child_cursor: Optional[Any] = None
            child_page_count = 0

            # region 通过循环所有直推节点，计算出gpv和合格的直属先先
            while True:
                # region 验证并刷新redis时长
                child_page_count += 1
                if child_page_count > self.MAX_CHILD_PAGES_PER_PARENT:
                    raise RuntimeError(f"parent_id={pid} 超过最大 child 页数，疑似 cursor 不收敛。")

                self._refresh_global_lock(lock)
                # endregion

                # region 分页获取子节点
                page = self._await_actor_result(
                    graph_actor.get_direct_children_page(pid, child_cursor, self.CHILD_PAGE_SIZE)
                )
                child_ids, next_child_cursor = self._parse_page_result(page)
                child_ids = [str(x) for x in child_ids]
                # endregion

                # region 验证
                if not child_ids:
                    if next_child_cursor is not None:
                        raise RuntimeError(f"GraphService 分页契约错误：parent_id={pid} 子节点为空，但 cursor 非空。")
                    break
                # endregion

                # region 获取子节点实体list
                child_lookup = self._mget_users_with_exists(child_ids, period)
                # endregion

                for cid in child_ids:
                    c_node, _ = child_lookup[cid]

                    # region 计算父节点的gpv
                    p_node.gpv = (p_node.gpv or 0) + (c_node.contrib or 0)
                    # endregion

                    # region 判断直属下级这条线是否合格，这条线合格的条件是：
                    # 1. 前驱节点自己是 Elite (rank >= 1)
                    # 2. 或者前驱节点自己不是 Elite，但他底下的子孙有 Elite (leg_total_width > 0)
                    if self._is_leg_qualified(c_node):
                        p_node.qualified_legs.add(c_node.id)
                    # endregion

                # region 验证 如果没有下一页的数据 跳出翻页循环
                child_cursor = next_child_cursor
                if child_cursor is None:
                    break
                # endregion
            # endregion

            # region 计算当前节点的等级和贡献度
            self._recalc_rank(p_node)
            p_node.contrib = self._calc_contrib(p_node)

            # 构建历史最高荣誉表记录（高水位 max），并按"晋衔口径"决定是否产出荣誉事件。
            honor_record, honor_event = self._build_highest_rank_record(
                period, p_node.id, p_node.rank, run_id
            )
            honor_records.append(honor_record)
            # 荣誉变更与 UserStats 是否漂移彼此独立，故 honor_event 不受 should_persist 约束：
            # 可能 UserStats 未漂移，但因跨月继承使历史最高创新高而需要发晋衔事件。
            if honor_event:
                outbox_events.append(honor_event)
            # endregion

            # region 差异比对与审计事件生成
            has_changed = self._has_state_changed(old_state, p_node)
            is_zero_node = self._is_zero_user_stats(p_node)

            # 写入判定：状态变了，或者是符合条件的新节点
            # 当一个节点之前不存在时，以下两种情况需要持久化：
            # 1、配置允许写入零值节点（即使节点值为零也保存）
            # 2、节点不是零值节点（非零节点总是要保存）
            should_persist = has_changed or (not existed_before and (write_zero_nodes or not is_zero_node))

            if should_persist:
                models_to_save.append(p_node)

                # 提取发送 Kafka 的审计事件
                if has_changed and existed_before:
                    outbox_events.append({
                        "event_type": "RECALC_STATE_DRIFT",
                        "period": period,
                        "user_id": p_node.id,
                        "old_state": old_state,
                        "new_state": self._extract_comparable_state(p_node),
                        "timestamp": int(time.time()),
                        "run_id": run_id
                    })
                elif not existed_before and not is_zero_node:
                    outbox_events.append({
                        "event_type": "RECALC_NODE_MATERIALIZED",
                        "period": period,
                        "user_id": p_node.id,
                        "old_state": old_state,
                        "new_state": self._extract_comparable_state(p_node),
                        "timestamp": int(time.time()),
                        "run_id": run_id
                    })
            # endregion

        # region 原子化集中写入（数据覆盖 + 荣誉表 + 事件入队）
        if models_to_save or outbox_events or honor_records:
            self._save_recalc_pipeline(redis_conn, models_to_save, outbox_events, honor_records)
        # endregion

    def _save_recalc_pipeline(
            self,
            redis_conn,
            models: List[UserStats],
            outbox_events: List[Dict[str, Any]],
            honor_records: List[UserPeriodHighestRank],
    ) -> None:
        """
        专用于全局重算的 Pipeline 写入。
        """
        pipe = redis_conn.pipeline(transaction=True)
        dedup_count = 0
        honor_count = 0

        # 1. 业务数据落库
        if models:
            dedup: Dict[str, UserStats] = {}
            for model in models:
                cls_name = model.__class__.__name__
                m_period = getattr(model, "period", "")
                model_id = getattr(model, "id", "")
                dedup_key = f"{cls_name}:{m_period}:{model_id}"
                dedup[dedup_key] = model

            for model in dedup.values():
                model.save(pipeline=pipe)
            dedup_count = len(dedup)

        # 2. 权威荣誉表落库
        if honor_records:
            honor_dedup: Dict[str, UserPeriodHighestRank] = {}
            for record in honor_records:
                honor_dedup[record.pk] = record

            for record in honor_dedup.values():
                record.save(pipeline=pipe)
            honor_count = len(honor_dedup)

        # 3. 审计/荣誉事件作为原子操作同时写入 Redis Stream
        if outbox_events:
            for event in outbox_events:
                pipe.xadd(
                    name=self.OUTBOX_STREAM_KEY,
                    fields={"payload": json.dumps(event, ensure_ascii=False, default=str)},
                    maxlen=100000,
                    approximate=True
                )

        pipe.execute()

        logger.info(
            "=== 原子化批处理完成: 覆盖更新 %d 个节点, 写入 %d 条荣誉记录, 发送 %d 个对账事件至 Outbox ===",
            dedup_count,
            honor_count,
            len(outbox_events) if outbox_events else 0,
        )

    def _build_highest_rank_record(
            self, period: str, user_id: str, current_rank: int, run_id: str
    ) -> Tuple[UserPeriodHighestRank, Optional[Dict[str, Any]]]:
        """
        构建权威荣誉表记录（高水位维护），并按"晋衔口径"决定是否产出荣誉事件。
        """
        # region 获取上期最高
        prev_period = self._get_previous_period(period)

        # 上期最高（跨期继承）
        prev_highest = 0
        if prev_period:
            try:
                prev_record = UserPeriodHighestRank.get(f"{prev_period}:{user_id}")
                prev_highest = int(prev_record.highest_rank or 0)
            except NotFoundError:
                prev_highest = 0
        # endregion

        # region 获取本期最高 并算出最新最高 -> new_highest
        current_period_highest = 0
        try:
            cur_record = UserPeriodHighestRank.get(f"{period}:{user_id}")
            current_period_highest = int(cur_record.highest_rank or 0)
        except NotFoundError:
            current_period_highest = 0

        cur_rank = int(current_rank or 0)
        new_highest = max(prev_highest, current_period_highest, cur_rank)
        # endregion

        # region 生成记录
        record = UserPeriodHighestRank(
            pk=f"{period}:{user_id}",
            id=f"{period}:{user_id}",
            period=period,
            user_id=user_id,
            current_rank=cur_rank,
            prev_period=prev_period,
            prev_highest_rank=prev_highest,
            highest_rank=new_highest,
            settled_run_id=run_id,
            settled_at=int(time.time()),
        )
        # endregion

        # region 如果new_highest发生变化了 返回honor_event
        honor_event: Optional[Dict[str, Any]] = None
        old_highest = max(prev_highest, current_period_highest)
        if new_highest > old_highest:
            honor_event = {
                "event_type": "HIGHEST_RANK_UPDATED",
                "period": period,
                "user_id": user_id,
                "current_rank": cur_rank,
                "old_highest_rank": old_highest,
                "new_highest_rank": new_highest,
                "prev_period_highest_rank": prev_highest,
                "current_period_highest_rank": current_period_highest,
                "timestamp": int(time.time()),
                "run_id": run_id,
            }
        # endregion

        return record, honor_event

    def _mget_users_with_exists(
            self,
            user_ids: Iterable[str],
            period: str
    ) -> Dict[str, Tuple[UserStats, bool]]:
        """
        批量读取 UserStats，并返回 Redis 中是否原本存在。

        优化点：
        - 使用 RedisJSON JSON.MGET 减少网络 RTT。
        - 保留原单条读取作为降级路径。
        - 对反序列化后的身份字段做严格校验，避免脏数据参与结算。
        """

        # region 初始化
        out: Dict[str, Tuple[UserStats, bool]] = {}
        period = str(period)
        uid_list = [str(uid) for uid in user_ids]
        # endregion

        # region 验证
        if not uid_list:
            return out
        # endregion

        # region 循环redis获取对象
        def fallback_single_get() -> Dict[str, Tuple[UserStats, bool]]:
            fallback_out: Dict[str, Tuple[UserStats, bool]] = {}

            for uid in uid_list:
                record_pk = f"{period}:{uid}"
                try:
                    node = UserStats.get(record_pk)
                    self._normalize_qualified_legs(node)
                    fallback_out[uid] = (node, True)
                except NotFoundError:
                    node = self._new_zero_user_stats(uid, period)
                    self._normalize_qualified_legs(node)
                    fallback_out[uid] = (node, False)

            return fallback_out
        # endregion

        redis_conn = UserStats.db()

        try:
            # region 生成redis key并批量获取
            keys = [UserStats.make_key(f"{period}:{uid}") for uid in uid_list]
            raw_results = redis_conn.json().mget(keys, ".")
            # endregion

            # region 验证
            if raw_results is None:
                raise RuntimeError("JSON.MGET 返回 None")

            if len(raw_results) != len(uid_list):
                raise RuntimeError(
                    f"JSON.MGET 返回数量异常: expected={len(uid_list)}, actual={len(raw_results)}"
                )
            # endregion
        # 当批量获取失败时 循环redis获取对象
        except Exception as e:
            logger.warning(
                "批量 JSON.MGET 失败，降级为单条读取模式: period=%s, count=%s, error=%s",
                period,
                len(uid_list),
                e,
            )
            return fallback_single_get()

        for uid, raw_data in zip(uid_list, raw_results):
            # region 生成键名
            expected_pk = f"{period}:{uid}"
            # endregion

            # region raw_data为空时 初始化对象 并跳过当前循环
            if raw_data is None:
                node = self._new_zero_user_stats(uid, period)
                self._normalize_qualified_legs(node)
                out[uid] = (node, False)
                continue
            # endregion

            try:
                model_data = raw_data

                # region 补齐pk值
                # Redis OM 某些版本/配置下，JSON 里可能不包含 pk。
                # 物理 key 已经证明当前记录属于 expected_pk，pk 缺失时可以补齐。
                raw_pk = model_data.get("pk")
                if raw_pk not in (None, expected_pk):
                    raise RuntimeError(
                        f"UserStats pk 与 Redis key 不一致: expected={expected_pk}, actual={raw_pk}"
                    )
                model_data["pk"] = expected_pk
                # endregion

                raw_period = model_data.get("period")
                if raw_period is not None and str(raw_period) != period:
                    raise RuntimeError(
                        f"UserStats period 不一致: expected={period}, actual={raw_period}"
                    )
                model_data["period"] = period

                # region 验证
                # 业务身份字段必须一致，不建议静默修复。
                if str(model_data.get("period")) != period:
                    raise RuntimeError(
                        f"UserStats period 不一致: expected={period}, actual={model_data.get('period')}"
                    )

                if str(model_data.get("id")) != uid:
                    raise RuntimeError(
                        f"UserStats id 不一致: expected={uid}, actual={model_data.get('id')}"
                    )

                if str(model_data.get("user_id")) != uid:
                    raise RuntimeError(
                        f"UserStats user_id 不一致: expected={uid}, actual={model_data.get('user_id')}"
                    )
                # endregion

                # region 将model_data转换成UserStats对象
                node = UserStats(**model_data)
                self._normalize_qualified_legs(node)
                out[uid] = (node, True)
                # endregion

            except Exception as e:
                logger.error(
                    "致命错误: 已存在 UserStats 反序列化失败或身份字段不一致。"
                    "period=%s, user_id=%s, error=%s",
                    period,
                    uid,
                    e,
                )
                raise RuntimeError(
                    f"用户 UserStats 数据损坏，结算阻断: period={period}, user_id={uid}, error={e}"
                ) from e

        return out

    def _new_zero_user_stats(self, uid: str, period: str) -> UserStats:
        """构造 Redis 中不存在用户的零值 UserStats。"""
        uid = str(uid)
        return UserStats(
            pk=f"{period}:{uid}",
            period=period,
            id=uid,
            user_id=uid,
            pv=0, gpv=0, contrib=0,
            is_elite=False, virtual_width=0,
            rank=UserLevel.NOTHING,
            qualified_legs=set(),
        )

    @staticmethod
    def _reset_derived_state_keep_pv(node: UserStats) -> None:
        node.gpv = node.pv or 0
        node.is_elite = False
        node.rank = UserLevel.NOTHING
        node.qualified_legs = set()
        node.virtual_width = 0
        node.contrib = 0

    @staticmethod
    def _is_zero_user_stats(node: UserStats) -> bool:
        if node.pv not in (None, 0): return False
        if node.gpv not in (None, 0): return False
        if node.contrib not in (None, 0): return False
        if node.rank not in (None, 0, UserLevel.NOTHING): return False
        if node.is_elite: return False
        if node.virtual_width not in (None, 0): return False
        if node.qualified_legs: return False
        return True

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
        raise TypeError(f"Unsupported page result type: {type(page)}")

    def _refresh_global_lock(self, lock) -> None:
        try:
            if not lock.owned():
                raise RuntimeError("全局重算锁已丢失，禁止继续写入。")
            lock.extend(self.LOCK_TTL_SECONDS, replace_ttl=True)
        except Exception as e:
            raise RuntimeError(f"刷新全局重算锁失败，禁止继续执行: {e}") from e

    # ==========================================
    # 状态与人工恢复机制
    # ==========================================

    @classmethod
    def _set_period_settlement_status(cls, redis_conn, status_key: str, status: str, run_id: str,
                                      extra: Dict = None) -> None:
        payload = {"status": status, "run_id": run_id, "updated_at": int(time.time())}
        if extra:
            payload.update(extra)
        redis_conn.set(status_key, json.dumps(payload, ensure_ascii=False, default=str))

    def _emit_settlement_done(
            self,
            redis_conn,
            status_key: str,
            period: str,
            run_id: str,
            max_depth: int,
            write_zero_nodes: bool,
    ) -> None:
        """整期结算成功的原子收尾"""
        done_status_payload = {
            "status": self.STATUS_DONE,
            "run_id": run_id,
            "updated_at": int(time.time()),
        }
        sentinel_event = {
            "event_type": "SETTLEMENT_PERIOD_DONE",
            "period": period,
            "run_id": run_id,
            "max_depth": int(max_depth),
            "write_zero_nodes": bool(write_zero_nodes),
            "timestamp": int(time.time()),
        }

        pipe = redis_conn.pipeline(transaction=True)
        pipe.set(
            status_key,
            json.dumps(done_status_payload, ensure_ascii=False, default=str),
        )
        pipe.xadd(
            name=self.OUTBOX_STREAM_KEY,
            fields={"payload": json.dumps(sentinel_event, ensure_ascii=False, default=str)},
            maxlen=100000,
            approximate=True
        )
        pipe.execute()

        logger.info(
            "=== 整期收尾原子提交完成: period=%s run_id=%s 状态=DONE, "
            "SETTLEMENT_PERIOD_DONE 哨兵已入 Outbox ===",
            period,
            run_id,
        )

    @classmethod
    def get_period_settlement_status(cls, period: str, redis_conn=None) -> Optional[Dict[str, Any]]:
        """读取全局重算状态。"""
        if redis_conn is None:
            redis_conn = UserStats.db()
        raw = redis_conn.get(cls._status_key(period))
        if raw is None: return None
        if isinstance(raw, bytes): raw = raw.decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {"status": str(raw), "raw": str(raw)}

    @classmethod
    def assert_period_settlement_available(cls, period: str) -> None:
        """业务入口保护：传入 period 检查"""
        redis_conn = UserStats.db()
        if redis_conn.exists(cls.GLOBAL_RECALC_LOCK_KEY):
            raise RuntimeError("全局结算锁被持有，禁止订单、拓扑变更、发奖或结算读取。")
        payload = cls.get_period_settlement_status(period, redis_conn)
        if payload and payload.get("status") in {cls.STATUS_RUNNING, cls.STATUS_FAILED}:
            raise RuntimeError(f"period={period} 结算状态为 {payload.get('status')}，禁止继续。")

    @classmethod
    def clear_period_settlement_failed(cls, period: str, *, by: str, reason: str) -> None:
        """手工解除 FAILED 阻塞。"""
        if not by or not reason:
            raise ValueError("清除 FAILED 状态必须提供 by 和 reason。")
        redis_conn = UserStats.db()
        status_key = cls._status_key(period)
        payload = cls.get_period_settlement_status(period, redis_conn)

        if payload and payload.get("status") != cls.STATUS_FAILED:
            raise RuntimeError(f"当前状态非 FAILED，禁止清除。payload={payload}")

        logger.warning("手工清除 FAILED 状态 period=%s by=%s reason=%s", period, by, reason)
        redis_conn.delete(status_key)

    @classmethod
    def mark_stuck_running_as_failed(cls, period: str, *, by: str, reason: str) -> None:
        """将卡死的 RUNNING 标记为 FAILED。"""
        redis_conn = UserStats.db()
        status_key = cls._status_key(period)
        probe_value = f"probe:{uuid.uuid4()}"

        if not redis_conn.set(cls.GLOBAL_RECALC_LOCK_KEY, probe_value, nx=True, ex=5):
            raise RuntimeError("全局锁仍被持有，可能确实有进程在运行，禁止强行标记 FAILED。")

        try:
            payload = cls.get_period_settlement_status(period, redis_conn)
            if not payload or payload.get("status") != cls.STATUS_RUNNING:
                raise RuntimeError(f"当前状态非 RUNNING，禁止处理。payload={payload}")

            logger.warning("将卡死的 RUNNING 标记为 FAILED period=%s by=%s reason=%s", period, by, reason)
            cls._set_period_settlement_status(
                redis_conn, status_key, cls.STATUS_FAILED, payload.get("run_id", "unknown"),
                extra={"phase": "failed_by_manual_recovery", "by": by, "reason": reason}
            )
        finally:
            current = redis_conn.get(cls.GLOBAL_RECALC_LOCK_KEY)
            if isinstance(current, bytes): current = current.decode("utf-8")
            if current == probe_value:
                redis_conn.delete(cls.GLOBAL_RECALC_LOCK_KEY)


# ==========================================
# 2. 预置 Redis 中的基础个人业绩 (PV)
# ==========================================
def inject_mock_pv_data(period: str):
    redis_conn = UserStats.db()
    stats_prefix = UserStats.make_key("")
    for key in redis_conn.scan_iter(f"{stats_prefix}*"):
        redis_conn.delete(key)

    honor_prefix = UserPeriodHighestRank.make_key("")
    for key in redis_conn.scan_iter(f"{honor_prefix}*"):
        redis_conn.delete(key)

    # 造数必须带有 period 和正确的 pk
    UserStats(pk=f"{period}:13", period=period, id="13", user_id="13", pv=1000, gpv=1000, is_elite=False,
              rank=UserLevel.NOTHING).save()
    UserStats(pk=f"{period}:9", period=period, id="9", user_id="9", pv=800, gpv=800, is_elite=False,
              rank=UserLevel.NOTHING).save()
    UserStats(pk=f"{period}:10", period=period, id="10", user_id="10", pv=2000, gpv=2000, is_elite=False,
              rank=UserLevel.NOTHING).save()
    print("Redis 测试基础 PV 数据注入完成。")


def main():
    SCHEDULER_ADDRESS = "tcp://127.0.0.1:8786"
    # 修改测试入参：适配整型/字符串型的单期自增编号
    test_period = "5"
    inject_mock_pv_data(test_period)

    print(f"连接到 Dask 调度器: {SCHEDULER_ADDRESS}...")
    try:
        svc = GlobalRecalculationService()
        print(f"启动 GlobalRecalculationService 单期结算 (period={test_period})...")
        svc.settle_period(period=test_period, write_zero_nodes=True)

        print("\n=== 重算结果验证 ===")
        for uid in ["1", "2", "3", "9", "10", "13"]:
            try:
                stats = UserStats.get(f"{test_period}:{uid}")
                honor = UserPeriodHighestRank.get(f"{test_period}:{uid}")
                print(f"User {uid}: GPV={stats.gpv}, Rank={stats.rank}, "
                      f"HighestRank={honor.highest_rank}, Elite={stats.is_elite}, "
                      f"VirtualWidth={stats.virtual_width}, QualifiedLegs={list(stats.qualified_legs)}, "
                      f"Contrib={stats.contrib}")
            except Exception as e:
                print(f"User {uid}: 获取失败 ({e})")
    except Exception as e:
        print(f"结算流程异常终止: {e}")


if __name__ == "__main__":
    main()