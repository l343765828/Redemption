# -*- coding: utf-8 -*-
# PlacementRecalculationService.py

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

import cudf
import dask_cudf
from dask.distributed import Client, wait as dask_wait

import Model.User.UserLevel as UserLevel
from Model.User.UserStats import UserStats
from Common.AmountModelAdapter import build_factory_amount_fields, require_v2_amount_record
from Common.PeriodResolver import PeriodSnapshot
from Common.PvAmount import (
    assert_integer_amount_dtype,
    checked_add_int64,
    require_amount_version,
    require_units_int,
)
from Redishelper.PVAmountConfigProvider import (
    PVAmountConfigProvider,
    PVAmountRunConfig,
    PVAmountRunSession,
)
from User.UserStatsService import UserStatsService
from Model.Config import SCHEDULE_ADDRESS

logger = logging.getLogger(__name__)


class PlacementRecalculationService(UserStatsService):
    """
    双轨制（安置网）左右区业绩（1L/2L）全局全量批处理重算服务。

    ⚠️【Runbook 级运维纪律声明（级联重算与依赖约束）】：
    1. 【跑批顺序依赖】：本服务依赖推荐网维护的 `gpv`。全量重算时必须先跑推荐网 (Global)，后跑安置网 (Placement)。
    2. 【级联重算约束】：若修改历史导致 N 期数据变动，必须按时间顺序逐一重跑 N+1 及之后的所有期数，严禁单独重跑中间期次！
    """

    GLOBAL_RECALC_LOCK_KEY = "system:global_recalc_lock"
    OUTBOX_STREAM_KEY = "system:recalc_outbox_stream"

    STATUS_RUNNING = "RUNNING"
    STATUS_DONE = "DONE"
    STATUS_FAILED = "FAILED"

    PARENT_PAGE_SIZE = 5000
    LOCK_TTL_SECONDS = 3600
    DASK_RESULT_TIMEOUT_SECONDS = 30 * 60

    @classmethod
    def _status_key(cls, period: str) -> str:
        return f"system:placement_recalc_status:{period}"

    @staticmethod
    def _get_prev_period(period: str, period_snapshot: PeriodSnapshot) -> Optional[str]:
        """从 AR_PERIOD 快照读取真实上一期，不再猜测 YYYYMM 或执行减一。"""
        if not isinstance(period_snapshot, PeriodSnapshot):
            raise TypeError("period_snapshot must be PeriodSnapshot")
        if str(period_snapshot.period_num) != str(period):
            raise ValueError("period_snapshot 与入口 period 不一致")
        return (
            None
            if period_snapshot.previous_period_num is None
            else str(period_snapshot.previous_period_num)
        )

    def settle_placement_period(
        self,
        period: str,
        write_zero_nodes: bool = True,
        *,
        period_snapshot: PeriodSnapshot,
    ) -> None:
        period = str(period)
        if not isinstance(period_snapshot, PeriodSnapshot):
            raise TypeError("settle_placement_period 必须注入 PeriodSnapshot")
        if str(period_snapshot.period_num) != period:
            raise ValueError("period_snapshot 与 settle_placement_period period 不一致")
        run_id = str(uuid.uuid4())
        status_key = self._status_key(period)
        # region 加载并冻结本次业务运行配置
        redis_conn = UserStats.db()
        run_config = PVAmountRunSession.start(
            PVAmountConfigProvider(redis_conn)
        ).config
        # endregion

        prev_period = self._get_prev_period(period, period_snapshot)
        if prev_period:
            prev_status_raw = redis_conn.get(self._status_key(prev_period))
            if prev_status_raw:
                p_status = json.loads(prev_status_raw)
                if p_status.get("status") != self.STATUS_DONE:
                    raise RuntimeError(f"时序违背：上一期 {prev_period} 结算未完成，禁止跑本期！")
            else:
                sample_prev_key = next(redis_conn.scan_iter(f"{UserStats.make_key('')}{prev_period}:*", count=5000),
                                       None)
                if sample_prev_key is not None:
                    raise RuntimeError(
                        f"时序严重违背：存在 {prev_period} 期的实体数据，但结算状态哨兵丢失！请先完成 {prev_period} 期的结算。")

        lock = redis_conn.lock(
            self.GLOBAL_RECALC_LOCK_KEY,
            timeout=self.LOCK_TTL_SECONDS,
            thread_local=True,
        )

        if not lock.acquire(blocking=False):
            raise RuntimeError(f"全局结算锁已被持有，阻断期数 {period} 的双轨重算任务。")

        client: Optional[Client] = None
        try:
            logger.info("【双轨 1L/2L 结算开始】period=%s run_id=%s", period, run_id)
            self._set_status(redis_conn, status_key, self.STATUS_RUNNING, run_id, {"phase": "initializing"})

            client = Client(SCHEDULE_ADDRESS)
            graph_actor = client.get_dataset("graph_actor").result()
            if not graph_actor:
                raise RuntimeError("未在集群中找到 graph_actor 实例")

            self._refresh_lock(lock)
            self._set_status(redis_conn, status_key, self.STATUS_RUNNING, run_id, {"phase": "validating_graph"})
            graph_actor.validate_graph_integrity().result(timeout=self.DASK_RESULT_TIMEOUT_SECONDS)

            self._refresh_lock(lock)
            self._set_status(redis_conn, status_key, self.STATUS_RUNNING, run_id, {"phase": "extracting_graph_edges"})
            fut_edges = graph_actor.get_placement_edges()
            edges_ddf = fut_edges.result(timeout=self.DASK_RESULT_TIMEOUT_SECONDS)

            self._refresh_lock(lock)
            self._set_status(redis_conn, status_key, self.STATUS_RUNNING, run_id, {"phase": "extracting_redis_data"})
            active_pv_dict, existing_placement_users, df_pv_local = self._extract_period_data(
                redis_conn, period, period_snapshot
            )

            gpu_res_dict = {}
            if not df_pv_local.empty:
                self._set_status(redis_conn, status_key, self.STATUS_RUNNING, run_id,
                                 {"phase": "gpu_closure_aggregating"})
                closure_ddf = self._build_placement_closure_table(edges_ddf, lock)
                pdf_res = self._calculate_placement_pv(closure_ddf, df_pv_local)
                gpu_res_dict = pdf_res.set_index('ancestor')[['PV_1L', 'PV_2L']].to_dict('index')

            self._refresh_lock(lock)

            all_target_users = set(gpu_res_dict.keys())
            all_target_users.update(active_pv_dict.keys())
            all_target_users.update(existing_placement_users)

            target_list = list(all_target_users)
            logger.info("GPU 聚合完成，进入 1L/2L 回写阶段。受影响节点总数: %d", len(target_list))

            self._set_status(redis_conn, status_key, self.STATUS_RUNNING, run_id, {"phase": "streaming_to_redis"})
            self._write_back_placement_matrix(
                redis_conn=redis_conn,
                target_list=target_list,
                gpu_res_dict=gpu_res_dict,
                active_pv_dict=active_pv_dict,
                period=period,
                run_id=run_id,
                write_zero_nodes=write_zero_nodes,
                run_config=run_config,
                period_snapshot=period_snapshot,
                lock=lock
            )

            self._emit_settlement_done(redis_conn, status_key, period, run_id, len(target_list))
            logger.info("【双轨 1L/2L 结算圆满完成】period=%s run_id=%s", period, run_id)

        except Exception as e:
            logger.exception("双轨批处理重算熔断崩塌 period=%s run_id=%s", period, run_id)
            try:
                self._set_status(redis_conn, status_key, self.STATUS_FAILED, run_id, {"error": repr(e)})
            except Exception:
                pass
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

    # =====================================================================
    # 数据提取与降级防线
    # =====================================================================

    def _extract_period_data(
        self,
        redis_conn,
        period: str,
        period_snapshot: PeriodSnapshot,
    ) -> Tuple[Dict[str, int], Set[str], cudf.DataFrame]:
        active_pv_dict = {}
        existing_placement_users = set()

        match_pattern = f"{UserStats.make_key('')}{period}:*"
        keys_batch = []
        for key in redis_conn.scan_iter(match_pattern, count=5000):
            keys_batch.append(key)
            if len(keys_batch) >= self.PARENT_PAGE_SIZE:
                self._process_extract_batch(redis_conn, keys_batch, active_pv_dict, existing_placement_users,
                                            is_prev_period=False)
                keys_batch = []
        if keys_batch:
            self._process_extract_batch(redis_conn, keys_batch, active_pv_dict, existing_placement_users,
                                        is_prev_period=False)

        prev_period = self._get_prev_period(period, period_snapshot)
        if prev_period:
            prev_pattern = f"{UserStats.make_key('')}{prev_period}:*"
            prev_keys_batch = []
            for key in redis_conn.scan_iter(prev_pattern, count=5000):
                prev_keys_batch.append(key)
                if len(prev_keys_batch) >= self.PARENT_PAGE_SIZE:
                    self._process_extract_batch(redis_conn, prev_keys_batch, active_pv_dict, existing_placement_users,
                                                is_prev_period=True)
                    prev_keys_batch = []
            if prev_keys_batch:
                self._process_extract_batch(redis_conn, prev_keys_batch, active_pv_dict, existing_placement_users,
                                            is_prev_period=True)

        if not active_pv_dict:
            df_pv = cudf.DataFrame({"user_id": cudf.Series(dtype="str"), "pv": cudf.Series(dtype="int64")})
        else:
            df_pv = cudf.DataFrame({"user_id": list(active_pv_dict.keys()), "pv": list(active_pv_dict.values())})

        return active_pv_dict, existing_placement_users, df_pv

    def _process_extract_batch(self, redis_conn, keys: List[bytes], active_pv_dict: Dict[str, int],
                               existing_placement_users: Set[str], is_prev_period: bool):
        if not keys: return

        try:
            raw_results = redis_conn.json().mget(keys, ".")
            if not raw_results or len(raw_results) != len(keys):
                raise RuntimeError(f"数据提取批次 MGET 返回长度不匹配 (Expected {len(keys)})")
        except Exception as e:
            raise RuntimeError(f"数据提取批次 MGET 失败，源池不完整，中止全量重算: {e}") from e

        for key_bytes, raw_data in zip(keys, raw_results):
            if not raw_data:
                continue

            key_str = key_bytes.decode('utf-8') if isinstance(key_bytes, bytes) else str(key_bytes)
            actual_uid = key_str.split(':')[-1]

            payload_id = raw_data.get("id")
            payload_user_id = raw_data.get("user_id")

            if payload_id is None or str(payload_id) != actual_uid:
                raise RuntimeError(f"提取阶段发现严重脏数据：Key={key_str}, 内部 id={payload_id}")
            if payload_user_id is None or str(payload_user_id) != actual_uid:
                raise RuntimeError(f"提取阶段发现严重脏数据：Key={key_str}, 内部 user_id={payload_user_id}")

            require_amount_version(raw_data.get("amount_encoding_version"))
            if is_prev_period:
                remain_1l = require_units_int(
                    raw_data.get("remain_surplus_1l") or 0,
                    "remain_surplus_1l",
                )
                remain_2l = require_units_int(
                    raw_data.get("remain_surplus_2l") or 0,
                    "remain_surplus_2l",
                )
                if remain_1l != 0 or remain_2l != 0:
                    existing_placement_users.add(actual_uid)
            else:
                pv_val = require_units_int(raw_data.get("pv") or 0, "pv")
                if pv_val != 0:
                    active_pv_dict[actual_uid] = pv_val

                if any(
                    require_units_int(raw_data.get(field) or 0, field) != 0
                    for field in [
                        "pv_1l", "pv_2l", "pre_surplus_1l",
                        "pre_surplus_2l", "total_1l", "total_2l",
                    ]
                ):
                    existing_placement_users.add(actual_uid)

    def _mget_prev_surplus(self, user_ids: List[str], prev_period: str) -> Dict[str, Dict[str, int]]:
        out = {uid: {"1l": 0, "2l": 0} for uid in user_ids}
        if not prev_period or not user_ids:
            return out

        redis_conn = UserStats.db()
        keys = [UserStats.make_key(f"{prev_period}:{uid}") for uid in user_ids]

        try:
            raw_results = redis_conn.json().mget(keys, ".")
            if not raw_results or len(raw_results) != len(keys):
                raise RuntimeError(f"拉取上期结余 MGET 返回长度不匹配 (Expected {len(keys)})")
        except Exception as e:
            logger.warning("拉取上期结余 MGET 异常，降级为单条安全读取模式: %s", e)
            raw_results = []
            for k in keys:
                raw_results.append(redis_conn.json().get(k, "."))

        for uid, raw_data in zip(user_ids, raw_results):
            if raw_data:
                actual_id = raw_data.get("id")
                actual_user_id = raw_data.get("user_id")
                if actual_id is None or str(actual_id) != uid:
                    raise RuntimeError(f"提取上期结余时发现脏数据：id 错位 (expected={uid}, actual={actual_id})")
                if actual_user_id is None or str(actual_user_id) != uid:
                    raise RuntimeError(
                        f"提取上期结余时发现脏数据：user_id 错位 (expected={uid}, actual={actual_user_id})")

                require_amount_version(raw_data.get("amount_encoding_version"))
                out[uid]["1l"] = require_units_int(
                    raw_data.get("remain_surplus_1l") or 0,
                    "remain_surplus_1l",
                )
                out[uid]["2l"] = require_units_int(
                    raw_data.get("remain_surplus_2l") or 0,
                    "remain_surplus_2l",
                )
        return out

    def _mget_users_with_exists(
        self,
        user_ids: List[str],
        period: str,
        run_config: PVAmountRunConfig,
    ) -> Dict[str, Tuple[UserStats, bool]]:
        out: Dict[str, Tuple[UserStats, bool]] = {}
        if not user_ids: return out

        redis_conn = UserStats.db()
        keys = [UserStats.make_key(f"{period}:{uid}") for uid in user_ids]

        raw_results = []
        try:
            raw = redis_conn.json().mget(keys, ".")
            if raw is None or len(raw) != len(user_ids):
                raise RuntimeError("MGET returned None or length mismatch")
            raw_results = raw
        except Exception as e:
            logger.warning("批量 MGET 发生异常，降级为单条安全获取模式: %s", e)
            for k in keys:
                r = redis_conn.json().get(k, ".")
                raw_results.append(r)

        for uid, raw_data in zip(user_ids, raw_results):
            if raw_data is None:
                out[uid] = (self._new_zero_user_stats(uid, period, run_config), False)
                continue

            actual_id = raw_data.get("id")
            actual_user_id = raw_data.get("user_id")

            if actual_id is None or str(actual_id) != uid:
                raise RuntimeError(f"发现严重脏数据：UserStats id 错位 (expected={uid}, actual={actual_id})")
            if actual_user_id is None or str(actual_user_id) != uid:
                raise RuntimeError(f"发现严重脏数据：UserStats user_id 错位 (expected={uid}, actual={actual_user_id})")

            expected_pk = f"{period}:{uid}"
            raw_pk = raw_data.get("pk")
            if raw_pk is not None and raw_pk != expected_pk:
                raise RuntimeError(f"发现严重脏数据：UserStats pk 错位 (expected={expected_pk}, actual={raw_pk})")

            raw_period = raw_data.get("period")
            if raw_period is not None and str(raw_period) != period:
                raise RuntimeError(f"发现严重脏数据：UserStats period 错位 (expected={period}, actual={raw_period})")

            # V2 全量重算禁止把 legacy 整数静默解释为 micro-units。
            require_v2_amount_record(raw_data)
            raw_data["pk"] = expected_pk
            raw_data["period"] = period

            node = UserStats(**raw_data)
            if node.qualified_legs is None:
                node.qualified_legs = set()
            elif not isinstance(node.qualified_legs, set):
                node.qualified_legs = set(node.qualified_legs)

            out[uid] = (node, True)

        return out

    def _new_zero_user_stats(self, uid: str, period: str, run_config: PVAmountRunConfig) -> UserStats:
        return UserStats(
            pk=f"{period}:{uid}", period=period, id=uid, user_id=uid,
            pv=0, gpv=0, gpv_real=0, gpv_unreal=0, contrib=0,
            is_elite=False, virtual_width=0, rank=UserLevel.NOTHING, qualified_legs=set(),
            pv_1l=0, pv_2l=0,
            pre_surplus_1l=0, pre_surplus_2l=0, total_1l=0, total_2l=0,
            remain_surplus_1l=0, remain_surplus_2l=0,
            **build_factory_amount_fields(run_config.state),
        )

    # =====================================================================
    # GPU 算力逻辑
    # =====================================================================

    def _count_ddf_rows(self, ddf) -> int:
        return 0 if ddf is None else int(ddf.map_partitions(len).sum().compute())

    def _dedup_with_multipath_guard(self, ddf: dask_cudf.DataFrame, stage: str) -> Tuple[dask_cudf.DataFrame, int]:
        """
        带多路径熔断的去重防线。
        前提：合法安置网(每节点至多一个安置父)中 (ancestor, descendant) 至多一条路径，
        去重前后行数必然相等；不等 ⟺ 多路径/重复边 ⟹ 熔断，绝不静默取其一。
        """
        raw = ddf.persist()
        before = self._count_ddf_rows(raw)

        deduped = raw.drop_duplicates(subset=["ancestor", "descendant"]).persist()
        dask_wait(deduped)
        after = self._count_ddf_rows(deduped)

        if before != after:
            detail = ""
            try:
                # 仅失败路径才执行昂贵诊断。
                # to_frame("cnt") 显式命名计数列，规避列名不兼容坑；
                # 先过滤再 head 取样，避免全量物化到客户端导致 OOM。
                dup = (
                    raw.groupby(["ancestor", "descendant"])
                    .size()
                    .to_frame("cnt")
                    .reset_index()
                )
                dup = dup[dup["cnt"] > 1]
                samples = dup.head(20, npartitions=-1).to_pandas().to_dict("records")
                detail = f"，样本(≤20)：{samples}"
            except Exception as diag_err:
                detail = f"（诊断采样失败: {diag_err!r}）"
            raise RuntimeError(
                f"非法安置网络：{stage} 存在 {before - after} 条 (ancestor, descendant) "
                f"多路径/重复记录，为防止双轨业绩被静默改写(SQL双计 vs 随机取一)，停止计算{detail}"
            )
        return deduped, after

    def _build_placement_closure_table(self, edges_ddf: dask_cudf.DataFrame, lock,
                                       max_depth: int = 5000) -> dask_cudf.DataFrame:
        edges = edges_ddf[["dst", "src", "placementLeg"]].rename(
            columns={"dst": "ancestor", "src": "descendant", "placementLeg": "leg"}
        )

        edges["ancestor"] = edges["ancestor"].astype("str")
        edges["descendant"] = edges["descendant"].astype("str")

        edges["leg"] = edges["leg"].fillna(0).astype("int32")
        bad_legs_ddf = edges[(edges["leg"] != 1) & (edges["leg"] != 2)]
        bad_legs_count = self._count_ddf_rows(bad_legs_ddf)
        if bad_legs_count > 0:
            raise RuntimeError(
                f"安置边表存在 {bad_legs_count} 条非法 leg (不为 1 或 2)，为防止双轨业绩断档蒸发，停止计算。")

        # 基础边表防线
        edges, _ = self._dedup_with_multipath_guard(edges, stage="基础边表")

        # 【修改 A 落实】：单一数据源衍生，保证类型继承和防线效果，不回头调用未防御的基础表
        edges_raw = edges[["ancestor", "descendant"]].rename(
            columns={"ancestor": "dst", "descendant": "src"}
        ).persist()
        dask_wait(edges_raw)

        parts, curr, converged = [edges], edges, False

        for i in range(max_depth):
            if i % 10 == 0:
                self._refresh_lock(lock)

            next_level = curr.merge(
                edges_raw, left_on="descendant", right_on="dst", how="inner"
            )[["ancestor", "src", "leg"]].rename(columns={"src": "descendant"})

            # 闭包展开循环内防线
            next_level, level_rows = self._dedup_with_multipath_guard(
                next_level, stage=f"闭包展开·路径长度 {i + 2}"
            )

            if level_rows == 0:
                converged = True
                break

            parts.append(next_level)
            curr = next_level

        if not converged:
            raise RuntimeError(f"安置网闭包在 {max_depth} 层内未收敛，停止计算。")

        # 全表合并防线（拦截跨层多路径）
        closure_ddf, closure_rows = self._dedup_with_multipath_guard(
            dask_cudf.concat(parts, ignore_index=True), stage="闭包全表合并"
        )
        logger.info("闭包表构建完成，共 %d 条祖先-后代关系", closure_rows)
        return closure_ddf

    def _calculate_placement_pv(self, closure_ddf: dask_cudf.DataFrame, df_pv_local: cudf.DataFrame) -> cudf.DataFrame:
        df_pv = df_pv_local[["user_id", "pv"]].copy()
        df_pv["user_id"] = df_pv["user_id"].astype("str")
        assert_integer_amount_dtype(df_pv, ["pv"], "placement input")
        df_pv = df_pv.groupby("user_id").agg({"pv": "sum"}).reset_index()
        assert_integer_amount_dtype(df_pv, ["pv"], "placement grouped input")

        nparts = getattr(closure_ddf, "npartitions", 1)
        ddf_pv = dask_cudf.from_cudf(df_pv, npartitions=nparts)

        joined = closure_ddf.merge(
            ddf_pv, left_on="descendant", right_on="user_id", how="inner"
        )
        assert_integer_amount_dtype(joined, ["pv"], "placement joined input")

        joined["PV_1L"] = joined["pv"].where(joined["leg"] == 1, 0)
        joined["PV_2L"] = joined["pv"].where(joined["leg"] == 2, 0)

        agg_ddf = joined.groupby("ancestor").agg({
            "PV_1L": "sum",
            "PV_2L": "sum"
        }).reset_index()
        assert_integer_amount_dtype(
            agg_ddf,
            ["PV_1L", "PV_2L"],
            "placement grouped output",
        )

        result = agg_ddf.compute().to_pandas()
        assert_integer_amount_dtype(
            result,
            ["PV_1L", "PV_2L"],
            "placement computed output",
        )
        return result

    # =====================================================================
    # Redis 回写与对账事件
    # =====================================================================

    def _write_back_placement_matrix(
            self,
            redis_conn,
            target_list: List[str],
            gpu_res_dict: Dict[str, Dict[str, int]],
            active_pv_dict: Dict[str, int],
            period: str,
            run_id: str,
            write_zero_nodes: bool,
            run_config: PVAmountRunConfig,
            period_snapshot: PeriodSnapshot,
            lock
    ) -> None:
        prev_period = self._get_prev_period(period, period_snapshot)

        for i in range(0, len(target_list), self.PARENT_PAGE_SIZE):
            self._refresh_lock(lock)
            batch_ids = target_list[i: i + self.PARENT_PAGE_SIZE]

            user_lookup = self._mget_users_with_exists(batch_ids, period, run_config)
            prev_surplus_lookup = self._mget_prev_surplus(batch_ids, prev_period)

            models_to_save: List[UserStats] = []
            outbox_events: List[Dict[str, Any]] = []

            for uid in batch_ids:
                pv_1l_new = require_units_int(
                    gpu_res_dict.get(uid, {}).get('PV_1L', 0),
                    "PV_1L",
                )
                pv_2l_new = require_units_int(
                    gpu_res_dict.get(uid, {}).get('PV_2L', 0),
                    "PV_2L",
                )

                pre_surplus_1l = prev_surplus_lookup[uid]["1l"]
                pre_surplus_2l = prev_surplus_lookup[uid]["2l"]

                node, existed_before = user_lookup[uid]
                gpv = require_units_int(getattr(node, "gpv", 0) or 0, "gpv")

                has_current_activity = (uid in active_pv_dict) or (pv_1l_new != 0) or (pv_2l_new != 0) or (gpv != 0)

                if has_current_activity:
                    total_1l_new = checked_add_int64(pv_1l_new, pre_surplus_1l)
                    total_2l_new = checked_add_int64(pv_2l_new, pre_surplus_2l)
                    remain_surplus_1l_new = require_units_int(getattr(node, "remain_surplus_1l", 0) or 0, "remain_surplus_1l")
                    remain_surplus_2l_new = require_units_int(getattr(node, "remain_surplus_2l", 0) or 0, "remain_surplus_2l")
                else:
                    total_1l_new = 0
                    total_2l_new = 0
                    remain_surplus_1l_new = pre_surplus_1l
                    remain_surplus_2l_new = pre_surplus_2l

                old_pv_1l = require_units_int(getattr(node, "pv_1l", 0) or 0, "pv_1l")
                old_pv_2l = require_units_int(getattr(node, "pv_2l", 0) or 0, "pv_2l")
                old_total_1l = require_units_int(getattr(node, "total_1l", 0) or 0, "total_1l")
                old_total_2l = require_units_int(getattr(node, "total_2l", 0) or 0, "total_2l")
                old_remain_1l = require_units_int(getattr(node, "remain_surplus_1l", 0) or 0, "remain_surplus_1l")
                old_remain_2l = require_units_int(getattr(node, "remain_surplus_2l", 0) or 0, "remain_surplus_2l")

                has_drift = (
                        (old_pv_1l != pv_1l_new) or (old_pv_2l != pv_2l_new) or
                        (old_total_1l != total_1l_new) or (old_total_2l != total_2l_new) or
                        (old_remain_1l != remain_surplus_1l_new) or (old_remain_2l != remain_surplus_2l_new)
                )

                is_zero_perf = (
                        total_1l_new == 0 and total_2l_new == 0 and
                        remain_surplus_1l_new == 0 and remain_surplus_2l_new == 0
                )

                should_persist = has_drift or (not existed_before and (write_zero_nodes or not is_zero_perf))

                if should_persist:
                    node.pv_1l = pv_1l_new
                    node.pv_2l = pv_2l_new
                    node.pre_surplus_1l = pre_surplus_1l
                    node.pre_surplus_2l = pre_surplus_2l
                    node.total_1l = total_1l_new
                    node.total_2l = total_2l_new
                    node.remain_surplus_1l = remain_surplus_1l_new
                    node.remain_surplus_2l = remain_surplus_2l_new

                    models_to_save.append(node)

                    if has_drift and existed_before:
                        outbox_events.append({
                            "event_type": "PLACEMENT_PV_DRIFT",
                            "period": period,
                            "user_id": node.id,
                            "drift_details": {
                                "pv_1l": [old_pv_1l, pv_1l_new],
                                "pv_2l": [old_pv_2l, pv_2l_new],
                                "total_1l": [old_total_1l, total_1l_new],
                                "total_2l": [old_total_2l, total_2l_new],
                                "remain_1l": [old_remain_1l, remain_surplus_1l_new],
                                "remain_2l": [old_remain_2l, remain_surplus_2l_new]
                            },
                            "timestamp": int(time.time()),
                            "run_id": run_id
                        })
                    elif not existed_before and not is_zero_perf:
                        outbox_events.append({
                            "event_type": "PLACEMENT_NODE_MATERIALIZED",
                            "period": period,
                            "user_id": node.id,
                            "new_state": {
                                "pv_1l": pv_1l_new, "pv_2l": pv_2l_new,
                                "total_1l": total_1l_new, "total_2l": total_2l_new,
                                "remain_1l": remain_surplus_1l_new, "remain_2l": remain_surplus_2l_new
                            },
                            "timestamp": int(time.time()),
                            "run_id": run_id
                        })

            if models_to_save or outbox_events:
                self._execute_atomic_pipeline(redis_conn, models_to_save, outbox_events)

    def _execute_atomic_pipeline(self, redis_conn, models: List[UserStats],
                                 outbox_events: List[Dict[str, Any]]) -> None:
        pipe = redis_conn.pipeline(transaction=True)

        for model in models:
            model.save(pipeline=pipe)

        for event in outbox_events:
            pipe.xadd(
                name=self.OUTBOX_STREAM_KEY,
                fields={"payload": json.dumps(event, ensure_ascii=False, default=str)},
                maxlen=100000,
                approximate=True
            )
        pipe.execute()

    def _refresh_lock(self, lock) -> None:
        try:
            if not lock.owned():
                raise RuntimeError("全局重算排他锁已丢失，由于禁止并发，立即中断向 Redis 强写！")
            lock.extend(self.LOCK_TTL_SECONDS, replace_ttl=True)
        except Exception as e:
            raise RuntimeError(f"锁刷新失败: {e}") from e

    @classmethod
    def _set_status(cls, redis_conn, status_key: str, status: str, run_id: str, extra: Optional[Dict] = None) -> None:
        payload = {"status": status, "run_id": run_id, "updated_at": int(time.time()), "engine": "GPU_Dask_cuDF"}
        if extra:
            payload.update(extra)
        redis_conn.set(status_key, json.dumps(payload, ensure_ascii=False, default=str))

    def _emit_settlement_done(self, redis_conn, status_key: str, period: str, run_id: str, impacted_count: int) -> None:
        done_payload = {"status": self.STATUS_DONE, "run_id": run_id, "updated_at": int(time.time()),
                        "impacted_count": impacted_count}
        sentinel_event = {
            "event_type": "PLACEMENT_SETTLEMENT_PERIOD_DONE",
            "period": period, "run_id": run_id, "impacted_count": impacted_count, "timestamp": int(time.time()),
        }
        pipe = redis_conn.pipeline(transaction=True)
        pipe.set(status_key, json.dumps(done_payload, ensure_ascii=False, default=str))
        pipe.xadd(
            name=self.OUTBOX_STREAM_KEY,
            fields={"payload": json.dumps(sentinel_event, ensure_ascii=False, default=str)},
            maxlen=100000, approximate=True
        )
        pipe.execute()