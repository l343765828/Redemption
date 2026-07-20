"""
Honor Level GPU 全量结算引擎 v3 (fixed)

基于 cuDF / CuPy 的全量 Honor 结算实现。
业务口径对齐：
- Honor_Level_最终版_v6.md
- CALC_LV_HONOR_LAST.sql
"""

from __future__ import annotations
import logging
import time
from typing import Optional, Tuple
import cudf
import cupy as cp
import pandas as pd
from Model.User.UserStats import UserStats
from dask.distributed import Client

LOG = logging.getLogger("User.HonorLevelGPUService")
SCHEDULE_ADDRESS = "tcp://127.0.0.1:8786"


class HonorLevelGPUService:
    """
    基于 GPU (cuDF / CuPy) 的全量 Honor 结算引擎。

    输入约束：
    - 快照必须包含 gpv（引擎内部会自动计算 gpv_real / gpv_unreal）；
    - last_elite_calc_id 必须已由 Elite 阶段刷新完成；
    - 若希望输出 *_honor_lv / layer_lv，需要额外传入 df_honor_levels 维表。
    """

    def __init__(self, strict_sql_mode: bool = True):
        self.strict_sql_mode = strict_sql_mode

    def build_snapshots_from_redis(self, batch_size: int = 10000):
        """
        从 Redis 中分批读取 UserStats 构建 df_snapshots，防止内存溢出。
        返回
        df_snapshots:
                必需列:
                    - user_id
                    - last_elite_calc_id    elite等级
                    - gpv
                    - limit_honor_calc_id   会员等级
                可选列:
                    - is_active
        """

        # 完整的状态映射契约
        rank_to_calc_id = {0: 0, 1: 10, 2: 20, 3: 30}

        df_chunks = []
        offset = 0

        print(f"⏳ 开始分批从 Redis 提取数据，每批 {batch_size} 条...")

        while True:
            # 1. 游标分批读取，避免一次性撑爆内存
            # page(offset, limit) 底层利用了 RediSearch 的分页能力
            users_batch = UserStats.find().page(offset, batch_size)

            # 如果当前批次为空，说明数据已经读完
            if not users_batch:
                break

            rows = []
            for u in users_batch:
                rows.append({
                    "user_id": int(u.user_id),
                    "last_elite_calc_id": rank_to_calc_id.get(u.rank, 0),
                    "gpv": float(u.gpv or 0.0),
                    "limit_honor_calc_id": 90,  # 默认不阻断
                    "is_active": 1  # 默认活跃
                })

            # 2. 将这一批数据立即转为 DataFrame，让 Pandas 底层的 C 数组接管数据
            # 此时上一批的 users_batch (厚重的 ORM 对象) 和 rows (Python 原生字典) 将在循环结束被 GC 垃圾回收
            chunk_df = pd.DataFrame(rows)
            df_chunks.append(chunk_df)

            print(f"   已读取并缓存 {offset + len(users_batch)} 条...")
            offset += batch_size

        # 3. 数据拼装兜底与类型推断
        if not df_chunks:
            # 如果库里完全没数据，造一个标准结构的空表，防止 GPU 抛空指针
            df_pd = pd.DataFrame(columns=["user_id", "last_elite_calc_id", "gpv", "limit_honor_calc_id", "is_active"])
            df_pd = df_pd.astype(
                {"user_id": "int64", "last_elite_calc_id": "int32", "gpv": "float64", "limit_honor_calc_id": "int32",
                 "is_active": "int32"})
        else:
            # 高效拼接所有批次 (pd.concat 性能极高)
            df_pd = pd.concat(df_chunks, ignore_index=True)

        print(f"✅ 数据提取完毕，共 {len(df_pd)} 条。正在推入 GPU 显存...")

        # 4. 一次性从系统内存 (CPU RAM) 推送到显存 (GPU VRAM)
        df_snapshots = cudf.DataFrame.from_pandas(df_pd)

        return df_snapshots

    # ==================================================================
    # 主入口
    # ==================================================================
    def recompute_all_gpu(
            self,
            df_honor_levels: Optional[cudf.DataFrame] = None,
    ) -> Tuple[cudf.DataFrame, cudf.DataFrame]:
        """
        全量结算主入口。

        参数:

            df_edges:
                必需列:
                    - src (user_id)
                    - dst (parent_uid，原始物理树父节点)
            df_honor_levels:
                可选维表，用于补充 *_honor_lv / layer_lv。
                支持列:
                    - calc_id
                    - honor_lv   或   id

        返回:
            (df_honor_result, df_layer_records)
        """

        # region 参数验证
        t0 = time.perf_counter()
        df_snapshots = self.build_snapshots_from_redis()
        print("获取完df_snapshots")
        # region 获取df_edges
        client = Client(SCHEDULE_ADDRESS)
        actor_future = client.get_dataset("graph_actor")
        actor = actor_future.result()
        ddf_edges = actor.get_ddf_edges().result()
        df_edges = ddf_edges.compute()
        df_edges["src"] = df_edges["src"].astype("int64")
        df_edges["dst"] = df_edges["dst"].astype("int64")
        print("获取完df_edges")
        # endregion
        self._validate_inputs(df_snapshots, df_edges)
        # endregion

        # region 预处理 格式转换
        LOG.info("开始 GPU 结算，节点数: %d", len(df_snapshots))

        df_snap = df_snapshots.copy().reset_index(drop=True)
        df_snap["user_id"] = df_snap["user_id"].astype("int64")
        df_snap["last_elite_calc_id"] = (
            df_snap["last_elite_calc_id"].fillna(0).astype("int32")
        )
        df_snap["limit_honor_calc_id"] = (
            df_snap["limit_honor_calc_id"].fillna(0).astype("int32")
        )
        if "is_active" in df_snap.columns:
            df_snap["is_active"] = df_snap["is_active"].fillna(0).astype("int32")
        else:
            df_snap["is_active"] = cp.zeros(len(df_snap), dtype=cp.int32)

        # 【核心插入】：基于传入的 GPV 动态推导 gpv_real 和 gpv_unreal
        df_snap["gpv"] = df_snap["gpv"].fillna(0.0).astype("float64")
        gpv_vals = df_snap["gpv"].values

        # 规则1：gpv >= 2000 -> real = 1000, unreal = gpv - 1000
        # 规则2：1000 <= gpv < 2000 -> real = gpv, unreal = 0
        # 规则3：gpv < 1000 -> 不达标，real = 0, unreal = 0
        df_snap["gpv_real"] = cp.where(
            gpv_vals >= 2000,
            1000.0,
            cp.where(gpv_vals >= 1000, gpv_vals, 0.0)
        ).astype("float64")

        df_snap["gpv_unreal"] = cp.where(
            gpv_vals >= 2000,
            gpv_vals - 1000.0,
            0.0
        ).astype("float64")

        edges = df_edges.copy().reset_index(drop=True)
        edges["src"] = edges["src"].astype("int64")
        edges["dst"] = edges["dst"].fillna(0).astype("int64")
        # endregion

        # region 关联原始物理父节点：df_snap、edges联查，获取parent_uid生成 --> df_base
        df_base = df_snap.merge(edges, left_on="user_id", right_on="src", how="left")
        df_base["parent_uid"] = df_base["dst"].fillna(0).astype("int64")
        df_base = df_base.drop(columns=["src", "dst"]).reset_index(drop=True)
        # endregion

        # region 获取动态层数上限：树/链路不可能超过节点数；超过即视为环路或坏数据。
        max_hops = max(int(len(df_base)) + 1, 1)
        # endregion

        # region 创建df_pse -> 压缩关系 返回只有se的链路表格
        LOG.info("PARENT_SE 压缩...")

        df_pse = self._compute_nearest_se(df_base, max_hops=max_hops)
        # endregion

        # region df_base联查df_pse 将df_base中的parent_se_id赋值
        df_base = df_base.merge(df_pse, on="user_id", how="left")
        df_base["parent_se_id"] = df_base["parent_se_id"].fillna(0).astype("int64")
        # endregion

        # region df_base的parent_se_id联查df_pse的user_id 将df_base中的grandpa_se_id赋值
        # 爷爷级 SE（用于 GPV_REAL 防抱团越级）
        df_gp = df_pse.rename(
            columns={"user_id": "_pid", "parent_se_id": "grandpa_se_id"}
        )
        df_base = df_base.merge(df_gp, left_on="parent_se_id", right_on="_pid", how="left")
        df_base["grandpa_se_id"] = df_base["grandpa_se_id"].fillna(0).astype("int64")
        df_base = df_base.drop(columns=["_pid"], errors="ignore").reset_index(drop=True)
        # endregion

        # 过滤出“gpv_unreal>0且parent_se_id!=0”的节点，并按parent_se_id分组对gpv_unreal求和
        # region GPV_UNREAL → 无条件交给 PARENT_SE -> agg_u:["se_id", "lb_unreal"]
        LOG.info("LB_PV 归集...")

        mask_u = (df_base["gpv_unreal"] > 0) & (df_base["parent_se_id"] != 0)
        df_u = df_base[mask_u][["parent_se_id", "gpv_unreal"]].copy().reset_index(drop=True)
        if len(df_u) > 0:
            agg_u = df_u.groupby("parent_se_id").agg({"gpv_unreal": "sum"}).reset_index()
            agg_u.columns = ["se_id", "lb_unreal"]
        else:
            agg_u = cudf.DataFrame(
                {
                    "se_id": cudf.Series(dtype="int64"),
                    "lb_unreal": cudf.Series(dtype="float64"),
                }
            )
        # endregion

        # 过滤出“gpv_real>0且parent_se_id!=0”的节点
        # target_se = parent_uid==parent_se_id?grandpa_se_id:parent_se_id，target_se分组对gpv_real求和
        # region GPV_REAL → 防抱团路由（直推上级是 SE 则越级）-> agg_r:["se_id", "lb_real"]
        mask_r = (df_base["gpv_real"] > 0) & (df_base["parent_se_id"] != 0)
        df_r = df_base[mask_r][
            ["parent_uid", "parent_se_id", "grandpa_se_id", "gpv_real"]
        ].copy().reset_index(drop=True)
        if len(df_r) > 0:
            cond_skip = df_r["parent_uid"].values == df_r["parent_se_id"].values
            target = cp.where(
                cond_skip,
                df_r["grandpa_se_id"].values.astype("int64"),
                df_r["parent_se_id"].values.astype("int64"),
            )
            df_r["target_se"] = target.astype("int64")
            df_r = df_r[df_r["target_se"] != 0].reset_index(drop=True)
            if len(df_r) > 0:
                agg_r = df_r.groupby("target_se").agg({"gpv_real": "sum"}).reset_index()
                agg_r.columns = ["se_id", "lb_real"]
            else:
                agg_r = cudf.DataFrame(
                    {
                        "se_id": cudf.Series(dtype="int64"),
                        "lb_real": cudf.Series(dtype="float64"),
                    }
                )
        else:
            agg_r = cudf.DataFrame(
                {
                    "se_id": cudf.Series(dtype="int64"),
                    "lb_real": cudf.Series(dtype="float64"),
                }
            )
        # endregion

        # region 创建df_lb -> agg_u联查agg_r，合并LB_PV LB_PV=lb_unreal+lb_real
        df_lb = agg_u.merge(agg_r, on="se_id", how="outer")
        if "lb_unreal" not in df_lb.columns:
            df_lb["lb_unreal"] = cp.zeros(len(df_lb), dtype=cp.float64)
        if "lb_real" not in df_lb.columns:
            df_lb["lb_real"] = cp.zeros(len(df_lb), dtype=cp.float64)
        if len(df_lb) > 0:
            df_lb = df_lb.fillna(0)
            df_lb["se_id"] = df_lb["se_id"].astype("int64")
            df_lb["lb_unreal"] = df_lb["lb_unreal"].astype("float64")
            df_lb["lb_real"] = df_lb["lb_real"].astype("float64")
            df_lb["lb_pv"] = df_lb["lb_unreal"] + df_lb["lb_real"]
        else:
            df_lb = cudf.DataFrame(
                {
                    "se_id": cudf.Series(dtype="int64"),
                    "lb_unreal": cudf.Series(dtype="float64"),
                    "lb_real": cudf.Series(dtype="float64"),
                    "lb_pv": cudf.Series(dtype="float64"),
                }
            )
        # endregion

        # region 通过df_base获取所有SE节点的 id list -> all_se_ids
        all_se_ids = (
            df_base[df_base["last_elite_calc_id"] == 30]["user_id"]
            .astype("int64")
            .reset_index(drop=True)
        )
        # endregion

        # 创建df_active_se -> 通过df_lb 过滤出lb_pv>0的活跃节点
        # region 通过df_lb，找出活跃SE的id list -> active_set
        df_active_se = df_lb[df_lb["lb_pv"] > 0][["se_id", "lb_pv"]].copy().reset_index(drop=True)
        if len(df_active_se) > 0:
            # 防止数据异常 导出出现幽灵节点
            df_active_se = df_active_se[df_active_se["se_id"].isin(all_se_ids)].copy().reset_index(drop=True)
        active_set = df_active_se["se_id"].astype("int64").reset_index(drop=True)
        # endregion

        # region 生成SE 网络全边集（src、dst）-> df_se_edges_all
        se_mask = (df_base["last_elite_calc_id"] == 30) & (df_base["parent_se_id"] != 0)
        df_se_edges_all = df_base[se_mask][["user_id", "parent_se_id"]].rename(
            columns={"user_id": "src", "parent_se_id": "dst"}
        ).copy().reset_index(drop=True)
        # endregion

        # region 生成父节点活跃的SE 网络全边集（src、dst）-> df_se_edges_active
        df_se_edges_active = df_se_edges_all[
            df_se_edges_all["dst"].isin(active_set)
        ].copy().reset_index(drop=True)
        # endregion

        # region 计算 “活跃”SE收到奖金的最大长度 和 每层长度SE的业绩 （奖金计算）
        LOG.info("深度递归 & 逐层业绩...")
        df_depth, df_layers = self._compute_depth_and_layers(
            df_active_se, df_se_edges_active, max_hops=max_hops
        )
        # endregion

        # region 计算 “所有”SE的宽度和深度。并算出个宽度的最大长度（奖衔计算）
        # 参与深度计算的时候，例如手下有三代se，这三代se必须为活跃se
        # 参与宽度计算的时候，直推se节点可以不活跃，只需要统计出直推se节点的深度有几代即可
        LOG.info("分支宽度递归...")
        df_width = self._compute_width(
            all_se_ids, df_se_edges_all, active_set, max_hops=max_hops
        )
        # endregion

        # region 通过df_base创建df_f，将之前算好的LB_PV、深度、宽度合并
        LOG.info("MID9-FINAL: 职级判定...")
        df_f = df_base[
            [
                "user_id",
                "parent_uid",
                "parent_se_id",
                "grandpa_se_id",
                "gpv_real",
                "gpv_unreal",
                "last_elite_calc_id",
                "limit_honor_calc_id",
                "is_active",
            ]
        ].copy().reset_index(drop=True)
        df_f["grandpa_se_id"] = df_f["grandpa_se_id"].fillna(0).astype("int64")
        df_f["gpv_real"] = df_f["gpv_real"].fillna(0).astype("float64")
        df_f["gpv_unreal"] = df_f["gpv_unreal"].fillna(0).astype("float64")

        # region 合并 LB_PV
        df_f = df_f.merge(
            df_lb[["se_id", "lb_pv"]], left_on="user_id", right_on="se_id", how="left"
        )
        df_f["lb_pv"] = df_f["lb_pv"].fillna(0).astype("float64")
        df_f = df_f.drop(columns=["se_id"], errors="ignore")
        # endregion

        # region 合并长度 legs_max_calc_id -> 财务深度
        df_f = df_f.merge(df_depth, left_on="user_id", right_on="se_id", how="left")
        df_f["legs_max_calc_id"] = df_f["legs_max_calc_id"].fillna(0).astype("int32")
        df_f = df_f.drop(columns=["se_id"], errors="ignore")
        # endregion

        # 通常legs_max_calc_id >= (raw_longest_se_num-1) 最终取最小 min(legs_max_calc_id,raw_longest_se_num-1)
        # region 合并宽度 raw_longest_se_num -> 人头深度数量
        df_f = df_f.merge(df_width, left_on="user_id", right_on="se_id", how="left")
        for col in ["raw_longest_se_num", "honor90_legs", "honor80_legs", "honor70_legs"]:
            if col not in df_f.columns:
                df_f[col] = cp.zeros(len(df_f), dtype=cp.int32)
            df_f[col] = df_f[col].fillna(0).astype("int32")
        df_f = df_f.drop(columns=["se_id"], errors="ignore")
        # endregion
        # endregion

        # region ori_honor_calc_id：业绩等级，这个月的真实业绩（团队的深度、宽度、活跃 SE 数量）决定
        # 只有 active SE (SE 且 LB_PV > 0) 才参与正式评定
        is_active_se = (
                (df_f["last_elite_calc_id"] == 30) & (df_f["lb_pv"] > 0)
        ).values

        legs = df_f["legs_max_calc_id"].values.astype("int32")
        h90 = df_f["honor90_legs"].values.astype("int32")
        h80 = df_f["honor80_legs"].values.astype("int32")
        h70 = df_f["honor70_legs"].values.astype("int32")

        ori = cp.where(
            (legs >= 90) & (h90 >= 3),
            90,
            cp.where(
                (legs >= 80) & (h80 >= 3),
                80,
                cp.where(
                    (legs >= 70) & (h70 >= 3),
                    70,
                    (cp.minimum(legs, 60) // 10) * 10,
                ),
            ),
        )
        df_f["ori_honor_calc_id"] = cp.where(is_active_se, ori, 0).astype("int32")
        # endregion

        # region bonus_honor_calc_id：拿钱等级 = min(业绩等级, 会员资格等级)
        df_f["bonus_honor_calc_id"] = cp.minimum(
            df_f["ori_honor_calc_id"].values.astype("int32"),
            df_f["limit_honor_calc_id"].values.astype("int32"),
        ).astype("int32")
        # endregion

        # region last_honor_calc_id：算出honor level 的最终等级
        # bonus_honor_calc_id > se_num_excluding_self时:
        # 属于正常情况：将之前的代数加的10移除，才是真正下面有几代
        # bonus_honor_calc_id < se_num_excluding_self时:
        # 情况1：se_num_excluding_self深度超长，但是宽度不够，所以按bonus_honor_calc_id走
        # 情况2：深度和宽度都符合条件，但是会员级别不够导致bonus_honor_calc_id小了

        # region 最长线 SE 数扣除本人；对非 active SE 归零
        raw_longest = df_f["raw_longest_se_num"].values.astype("int32")
        se_excl = cp.maximum(raw_longest - 1, 0)
        df_f["se_num_excluding_self"] = cp.where(
            is_active_se,
            se_excl,
            0,
        ).astype("int32")
        # endregion

        df_f["last_honor_calc_id"] = cp.minimum(
            df_f["bonus_honor_calc_id"].values.astype("int32"),
            (df_f["se_num_excluding_self"].values.astype("int32") * 10),
        ).astype("int32")
        # endregion

        # region 非 active SE 的宽度字段归零
        df_f["honor90_legs"] = cp.where(is_active_se, h90, 0).astype("int32")
        df_f["honor80_legs"] = cp.where(is_active_se, h80, 0).astype("int32")
        df_f["honor70_legs"] = cp.where(is_active_se, h70, 0).astype("int32")
        # endregion

        # region df_honor_levels不为空时，将数据对齐到df_honor_levels中的等级名称
        # df_honor_levels不为空时，清洗数据只保留calc_id、honor_lv
        df_hl = self._normalize_honor_levels(df_honor_levels)
        if df_hl is not None:
            df_f = self._attach_honor_lv(df_f, df_hl, "ori_honor_calc_id", "ori_honor_lv")
            df_f = self._attach_honor_lv(df_f, df_hl, "limit_honor_calc_id", "limit_honor_lv")
            df_f = self._attach_honor_lv(df_f, df_hl, "bonus_honor_calc_id", "bonus_honor_lv")
            df_f = self._attach_honor_lv(df_f, df_hl, "last_honor_calc_id", "last_honor_lv")
        # endregion

        # region 筛选出符合ori_honor_calc_id的lb_pv
        LOG.info("生成截层明细 (Layer Records)...")
        df_layer_out = df_layers.merge(
            df_f[["user_id", "ori_honor_calc_id", "bonus_honor_calc_id", "is_active"]],
            on="user_id",
            how="inner",
        )
        df_layer_out = df_layer_out[
            df_layer_out["layer_calc_id"] <= df_layer_out["ori_honor_calc_id"]
            ].copy().reset_index(drop=True)

        if df_hl is not None and len(df_layer_out) > 0:
            df_layer_out = self._attach_honor_lv(df_layer_out, df_hl, "layer_calc_id", "layer_lv")
            df_layer_out = self._attach_honor_lv(
                df_layer_out, df_hl, "bonus_honor_calc_id", "bonus_honor_lv"
            )
        # endregion

        # region 输出整理
        result_cols = [
            "user_id",
            "parent_uid",
            "parent_se_id",
            "grandpa_se_id",
            "gpv_real",
            "gpv_unreal",
            "lb_pv",
            "legs_max_calc_id",
            "honor90_legs",
            "honor80_legs",
            "honor70_legs",
            "ori_honor_calc_id",
            "limit_honor_calc_id",
            "bonus_honor_calc_id",
            "se_num_excluding_self",
            "last_honor_calc_id",
            "is_active",
        ]
        optional_result_cols = [
            "ori_honor_lv",
            "limit_honor_lv",
            "bonus_honor_lv",
            "last_honor_lv",
        ]
        result_cols.extend([c for c in optional_result_cols if c in df_f.columns])
        df_f = df_f[[c for c in result_cols if c in df_f.columns]]

        layer_cols = [
            "user_id",
            "layer_calc_id",
            "lb_pv",
            "bonus_honor_calc_id",
            "is_active",
        ]
        optional_layer_cols = ["layer_lv", "bonus_honor_lv"]
        layer_cols.extend([c for c in optional_layer_cols if c in df_layer_out.columns])
        df_layer_out = df_layer_out[[c for c in layer_cols if c in df_layer_out.columns]]

        elapsed = time.perf_counter() - t0
        LOG.info("GPU 结算完成，耗时: %.4fs", elapsed)
        # endregion

        return df_f, df_layer_out

    # ==================================================================
    # 输入校验
    # ==================================================================
    def _validate_inputs(self, df_snapshots: cudf.DataFrame, df_edges: cudf.DataFrame) -> None:
        required_snapshot_cols = {
            "user_id",
            "last_elite_calc_id",
            "gpv",  # 校验替换为传入 GPV
            "limit_honor_calc_id",
        }
        required_edge_cols = {"src", "dst"}

        missing_snap = required_snapshot_cols - set(df_snapshots.columns)
        if missing_snap:
            raise ValueError(f"df_snapshots 缺少必需列: {sorted(missing_snap)}")

        missing_edges = required_edge_cols - set(df_edges.columns)
        if missing_edges:
            raise ValueError(f"df_edges 缺少必需列: {sorted(missing_edges)}")

        if len(df_snapshots) == 0:
            return

        dup_users = df_snapshots["user_id"].astype("int64").duplicated().any()
        if bool(dup_users):
            raise ValueError("df_snapshots.user_id 存在重复，无法构成唯一快照。")

        dup_src = df_edges["src"].astype("int64").duplicated().any()
        if bool(dup_src):
            raise ValueError("df_edges.src 存在重复，原始物理树父边不唯一。")

    # ==================================================================
    # MID1: 最近上级 SE
    # ==================================================================
    def _compute_nearest_se(
            self,
            df_base: cudf.DataFrame,
            max_hops: int,
    ) -> cudf.DataFrame:
        """
        沿 parent_uid 链向上查找最近 SE。
        """
        # region 复制出一份新表df_w（"user_id", "parent_uid"） 新增字段“curr”，值为parent_uid，新增字段“parent_se_id”，值为0
        df_w = df_base[["user_id", "parent_uid"]].copy().reset_index(drop=True)
        df_w["curr"] = df_w["parent_uid"].astype("int64")
        df_w["parent_se_id"] = cp.zeros(len(df_w), dtype=cp.int64)
        # endregion

        # region 筛选出se的数据，并创建表se_lu，新增字段“_is_se”，值为1
        se_lu = (
            df_base[df_base["last_elite_calc_id"] == 30][["user_id"]]
            .rename(columns={"user_id": "_ck"})
            .copy()
            .reset_index(drop=True)
        )
        se_lu["_is_se"] = cp.ones(len(se_lu), dtype=cp.int8)
        # endregion

        # region 创建表tree_lu，只保留"user_id", "parent_uid"
        tree_lu = (
            df_base[["user_id", "parent_uid"]]
            .rename(columns={"user_id": "_n", "parent_uid": "_p"})
            .copy()
            .reset_index(drop=True)
        )
        # endregion

        frontier_remaining = False
        for _ in range(max_hops):
            # region 查找是否还有 条件：“未找到se父节点且有父节点”的节点，如果没有则跳出循环
            # 遍历所有dr_w的数据，满足“se父节点id为0（未找到se父节点）且父节点不为0”时 返回true
            # mask 返回结果类似：[false,false,true]
            mask = (df_w["parent_se_id"] == 0) & (df_w["curr"] != 0)
            # 当结果里都是false时，bool(mask.any())才返false，有任意一个true，则返回true
            frontier_remaining = bool(mask.any())
            if not frontier_remaining:
                break
            # endregion

            # region 筛选出满足条件的数据
            df_s = df_w[mask][["user_id", "curr"]].copy().reset_index(drop=True)
            # endregion

            # region df_s的curr联查se_lu的_ck
            df_ck = df_s.merge(se_lu, left_on="curr", right_on="_ck", how="left")
            # endregion

            # region 找到父节点是 SE 的集合：准备更新
            df_found = (
                df_ck[df_ck["_is_se"] == 1][["user_id", "curr"]]
                .rename(columns={"curr": "_fse"})
                .copy()
                .reset_index(drop=True)
            )
            # endregion

            # region 如果父节点不是se 联查tree_lu 获取父节点的父节点
            df_nf = df_ck[df_ck["_is_se"].isna()][["user_id", "curr"]].copy().reset_index(drop=True)
            if len(df_nf) > 0:
                df_nf = df_nf.merge(tree_lu, left_on="curr", right_on="_n", how="left")
                df_nf["_nc"] = df_nf["_p"].fillna(0).astype("int64")
                df_nf = df_nf[["user_id", "_nc"]].copy().reset_index(drop=True)
            else:
                df_nf = cudf.DataFrame(
                    {
                        "user_id": cudf.Series(dtype="int64"),
                        "_nc": cudf.Series(dtype="int64"),
                    }
                )
            # endregion

            # region 安全更新 parent_se_id：df_w联查df_found 将df_found中的_fse赋值parent_se_id
            df_w = df_w.merge(df_found, on="user_id", how="left")
            has_found = df_w["_fse"].notna().values
            df_w["parent_se_id"] = cp.where(
                has_found,
                df_w["_fse"].fillna(0).values.astype("int64"),
                df_w["parent_se_id"].values.astype("int64"),
            )
            df_w = df_w.drop(columns=["_fse"]).reset_index(drop=True)
            # endregion

            # region 安全更新 curr：df_w联查df_nf 将df_nf中的_nc赋值curr
            df_w = df_w.merge(df_nf, on="user_id", how="left")
            has_next = df_w["_nc"].notna().values
            df_w["curr"] = cp.where(
                has_next,
                df_w["_nc"].fillna(0).values.astype("int64"),
                df_w["curr"].values.astype("int64"),
            )
            df_w = df_w.drop(columns=["_nc"]).reset_index(drop=True)
            # endregion

        # region 安全效验
        if frontier_remaining and self.strict_sql_mode:
            unresolved = int(((df_w["parent_se_id"] == 0) & (df_w["curr"] != 0)).sum())
            raise ValueError(
                f"MID1 PARENT_SE 查找超过最大跳数 {max_hops}，"
                f"仍有 {unresolved} 个节点未收敛；可能存在环路或脏数据。"
            )
        # endregion

        return df_w[["user_id", "parent_se_id"]]

    # ==================================================================
    # MID5 + MID6: 深度递归 & 逐层业绩
    # ==================================================================
    def _compute_depth_and_layers(
            self,
            df_active_se: cudf.DataFrame,
            df_edges_active: cudf.DataFrame,
            max_hops: int,
    ) -> Tuple[cudf.DataFrame, cudf.DataFrame]:
        """
        种子 = 活跃 SE (LB_PV > 0)。
        链路仅通过活跃 SE。

        每个种子携带自身 lb_pv，沿 parent_se 向上传播。
        在每个经过的节点，累加到对应的 (节点, layer_calc_id) 业绩桶中。
        """
        # region 将df_active_se复制给df_st,并新增列layer，默认值为10
        df_st = (
            df_active_se.rename(columns={"se_id": "src"})[["src", "lb_pv"]]
            .copy()
            .reset_index(drop=True)
        )
        df_st["layer"] = cp.full(len(df_st), 10, dtype=cp.int32)
        # endregion

        # region 参数初始化
        records = []
        frontier = df_st
        frontier_remaining = False
        # endregion

        for _ in range(max_hops):
            # region 验证是否跳出
            frontier_remaining = len(frontier) > 0
            if not frontier_remaining:
                break
            # endregion

            # region records记录当前节点（frontier）的信息
            records.append(frontier[["src", "layer", "lb_pv"]].copy())
            # endregion

            # region 联查df_edges_active 获取dst信息
            df_nx = frontier.merge(df_edges_active, on="src", how="inner")
            # 验证是否结束
            if len(df_nx) == 0:
                frontier = df_nx
                frontier_remaining = False
                break
            # endregion

            # region 身份转换并更新层级信息，并将新的层节点赋值给frontier
            df_nx["layer"] = (df_nx["layer"].astype("int32") + 10).astype("int32")
            df_nx["src"] = df_nx["dst"].values.astype("int64")
            df_nx = df_nx.drop(columns=["dst"]).reset_index(drop=True)
            frontier = df_nx
            # endregion

        # region 验证
        if frontier_remaining and self.strict_sql_mode and len(frontier) > 0:
            raise ValueError(
                f"MID5 深度递归超过最大跳数 {max_hops}；可能存在环路或异常长链。"
            )
        # endregion

        # region 如果records为空，返回空数据
        if not records:
            return (
                cudf.DataFrame(
                    {
                        "se_id": cudf.Series(dtype="int64"),
                        "legs_max_calc_id": cudf.Series(dtype="int32"),
                    }
                ),
                cudf.DataFrame(
                    {
                        "user_id": cudf.Series(dtype="int64"),
                        "layer_calc_id": cudf.Series(dtype="int32"),
                        "lb_pv": cudf.Series(dtype="float64"),
                    }
                ),
            )
        # endregion

        # region 返回se的最大深度
        df_all = cudf.concat(records, ignore_index=True)

        df_dep = df_all.groupby("src").agg({"layer": "max"}).reset_index()
        df_dep.columns = ["se_id", "legs_max_calc_id"]
        # endregion

        # region 返回se 每个层级 对应的lb_pv
        df_lyr = (
            df_all.groupby(["src", "layer"]).agg({"lb_pv": "sum"}).reset_index()
        )
        df_lyr.columns = ["user_id", "layer_calc_id", "lb_pv"]
        # endregion

        return df_dep, df_lyr

    # ==================================================================
    # MID7 + MID8: 分支宽度
    # ==================================================================
    def _compute_width(
            self,
            all_se_ids: cudf.Series,
            df_edges_all: cudf.DataFrame,
            active_set: cudf.Series,
            max_hops: int,
    ) -> cudf.DataFrame:
        """
        all_se_ids：所有SE节点的id list
        df_edges_all：SE 网络全边集（src、dst）
        active_set：活跃SE的id list
        链路从严（长度计算）：仅当 dst ∈ active_se 时才继续向上传播。否则直接截停重新计算
        例如：B1 活跃，B2 活跃，B3 不活跃，B4 活跃 -> 长度为3，从B3开算1
        B1 不活跃，B2 活跃，B3 活跃，B4 活跃 -> 长度为1，从B1开算1
        宽度计算：通过branch_parts统计出每条线的最大深度，然后过滤出符合条件个数
        即使直推节点不活跃，也被包含在了branch_parts，主要是为了统计当前节点下的se_num数量
        例如B1上级是A1，即使B1不活跃也被放到了branch_parts中
        df_br["ge3"] = (df_br["se_num"] >= 3)
        df_br["ge2"] = (df_br["se_num"] >= 2)
        df_br["ge1"] = (df_br["se_num"] >= 1)
        再根据parent_se汇总，对df_br["ge3"]、df_br["ge2"]、df_br["ge1"]求和，得出宽度个数
        但分支记录在传播过滤之前完成（与 CPU / SQL 语义一致）。
        """
        # region 通过all_se_ids创建df_st，新增“se_num”列
        src_series = all_se_ids.astype("int64").reset_index(drop=True)
        df_st = cudf.DataFrame({"src": src_series})
        df_st["se_num"] = cp.ones(len(df_st), dtype=cp.int32)
        # endregion

        # region 参数初始化
        # 记录每个se用户的活跃下线se数量
        longest_parts = []
        branch_parts = []
        frontier = df_st
        frontier_remaining = False
        # endregion

        # region 算出每个se节点的深度和宽度
        for _ in range(max_hops):
            # region 跳出循环条件
            frontier_remaining = len(frontier) > 0
            if not frontier_remaining:
                break
            # endregion

            # region 将frontier的数据（src、se_num）添加到longest_parts中
            longest_parts.append(frontier[["src", "se_num"]].copy())
            # endregion

            # region frontier联查df_edges_all，获取dst，并生成df_wp
            df_wp = frontier.merge(df_edges_all, on="src", how="inner")
            if len(df_wp) == 0:
                frontier = df_wp
                frontier_remaining = False
                break
            # endregion

            # region 将带父节点（dst）的df_wp添加到branch_parts中
            branch_parts.append(
                df_wp[["dst", "src", "se_num"]]
                .rename(columns={"dst": "parent_se", "src": "branch_key"})
                .copy()
                .reset_index(drop=True)
            )
            # endregion

            # region 筛选出 父节点活跃 的数据，链路从严，上级不活跃？当场掐断！
            df_nx = df_wp[df_wp["dst"].isin(active_set)].copy().reset_index(drop=True)
            if len(df_nx) == 0:
                frontier = df_nx
                frontier_remaining = False
                break
            # endregion

            # region 更新链路长度
            df_nx["se_num"] = (df_nx["se_num"].fillna(0).astype("int32") + 1).astype("int32")
            df_nx["src"] = df_nx["dst"].values.astype("int64")
            df_nx = df_nx.drop(columns=["dst"])
            # endregion

            # region 同一节点只保留最大 se_num，并将df_nx赋值给frontier
            df_nx = df_nx.groupby("src").agg({"se_num": "max"}).reset_index()
            frontier = df_nx
            # endregion
        # endregion

        if frontier_remaining and self.strict_sql_mode and len(frontier) > 0:
            raise ValueError(
                f"MID7 宽度递归超过最大跳数 {max_hops}；可能存在环路或异常长链。"
            )

        # region 统计出每个用户的活跃se的最大下线数量
        if longest_parts:
            df_lon = (
                cudf.concat(longest_parts, ignore_index=True)
                .groupby("src")
                .agg({"se_num": "max"})
                .reset_index()
            )
            df_lon.columns = ["se_id", "raw_longest_se_num"]
        else:
            df_lon = cudf.DataFrame(
                {
                    "se_id": cudf.Series(dtype="int64"),
                    "raw_longest_se_num": cudf.Series(dtype="int32"),
                }
            )
        # endregion

        # region 统计出每个parent_se下的branch_key的最大深度
        # 分组parent_se、branch_key，获取se_num（深度）最大的max
        # 再根据se_num的条件算出ge3、ge2、ge1
        # 再按parent_se分组，对ge3、ge2、ge1求和，算出宽度各自的宽度数量
        if branch_parts:
            df_br = cudf.concat(branch_parts, ignore_index=True)
            df_br = (
                df_br.groupby(["parent_se", "branch_key"])
                .agg({"se_num": "max"})
                .reset_index()
            )
            df_br["ge3"] = (df_br["se_num"] >= 3).astype("int32")
            df_br["ge2"] = (df_br["se_num"] >= 2).astype("int32")
            df_br["ge1"] = (df_br["se_num"] >= 1).astype("int32")

            df_legs = (
                df_br.groupby("parent_se")
                .agg({"ge3": "sum", "ge2": "sum", "ge1": "sum"})
                .reset_index()
            )
            df_legs.columns = [
                "se_id",
                "honor90_legs",
                "honor80_legs",
                "honor70_legs",
            ]
        else:
            df_legs = cudf.DataFrame(
                {
                    "se_id": cudf.Series(dtype="int64"),
                    "honor90_legs": cudf.Series(dtype="int32"),
                    "honor80_legs": cudf.Series(dtype="int32"),
                    "honor70_legs": cudf.Series(dtype="int32"),
                }
            )
        # endregion

        # region df_lon联查df_legs，获取该下线的最长深度和宽度
        df_result = df_lon.merge(df_legs, on="se_id", how="outer")
        if len(df_result) > 0:
            df_result = df_result.fillna(0)
            df_result["se_id"] = df_result["se_id"].astype("int64")
            for col in ["raw_longest_se_num", "honor90_legs", "honor80_legs", "honor70_legs"]:
                df_result[col] = df_result[col].astype("int32")
        # endregion
        return df_result

    # ==================================================================
    # 只保留calc_id、honor_lv两列数据，如果有id列，将id重命名为honor_lv
    # ==================================================================
    def _normalize_honor_levels(
            self,
            df_honor_levels: Optional[cudf.DataFrame],
    ) -> Optional[cudf.DataFrame]:
        if df_honor_levels is None:
            return None
        if len(df_honor_levels) == 0:
            return None

        df_hl = df_honor_levels.copy().reset_index(drop=True)
        if "calc_id" not in df_hl.columns:
            raise ValueError("df_honor_levels 缺少 calc_id 列。")
        if "honor_lv" not in df_hl.columns:
            if "id" in df_hl.columns:
                df_hl = df_hl.rename(columns={"id": "honor_lv"})
            else:
                raise ValueError("df_honor_levels 需要 honor_lv 或 id 列。")

        df_hl = df_hl[["calc_id", "honor_lv"]].copy().reset_index(drop=True)
        df_hl["calc_id"] = df_hl["calc_id"].fillna(0).astype("int32")
        return df_hl

    def _attach_honor_lv(
            self,
            df: cudf.DataFrame,
            df_hl: cudf.DataFrame,
            calc_id_col: str,
            out_col: str,
    ) -> cudf.DataFrame:
        if calc_id_col not in df.columns or len(df) == 0:
            return df
        lu = df_hl.rename(columns={"calc_id": f"_{calc_id_col}", "honor_lv": out_col})
        df = df.merge(lu, left_on=calc_id_col, right_on=f"_{calc_id_col}", how="left")
        return df.drop(columns=[f"_{calc_id_col}"], errors="ignore")


def main():
    svc = HonorLevelGPUService()
    df_honor_result, df_layer_records = svc.recompute_all_gpu()

    # 转成 Pandas 打印，cudf 直接 print 有时显示不全
    print("\n===== Honor Result =====")
    print(df_honor_result.to_pandas().to_string())

    print("\n===== Layer Records =====")
    print(df_layer_records.to_pandas().to_string())


if __name__ == "__main__":
    main()
