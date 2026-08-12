from __future__ import annotations

"""
Leadership Bonus GPU 国家与大区结算系统（Honor Snapshot 输入版 / 修正版）

修正点：
1. 不再要求调用方重复传 df_network / df_pv_raw / df_honor_last；
2. 直接接收 HonorLevelGPUService 的输出快照 df_honor_snapshot；
3. 在内部切出：
   - df_network   = user_id / parent_uid / parent_se_id / grandpa_se_id
   - df_pv_raw    = user_id / gpv_real / gpv_unreal
   - df_honor_last= user_id / ori_honor_calc_id / bonus_honor_calc_id / last_honor_calc_id (+ *_lv)
4. 支持可选传入 HonorLevelHighGPUService 的结果 df_honor_high，
   将 highest_honor_calc_id / highest_honor_lv 覆盖为 Leadership 结果表展示用的
   last_honor_calc_id / last_honor_lv；
5. _build_inputs_from_honor_snapshot 不再返回未被使用的 snap。

注意：
- Leadership Bonus 的奖金拦截仍严格使用 ORI_HONOR_CALC_ID / BONUS_HONOR_CALC_ID；
- last_honor_* 在本服务中仅作为结果表展示字段，不参与 Leadership Bonus 拦截。
"""

import logging
import time
from typing import Dict, Iterable, Optional, Tuple

import cudf
import cupy as cp

from Common.BonusConfig import ensure_config_snapshot

LOG = logging.getLogger("Bonus.LeadershipBonusGPUService")


class LeadershipBonusGPUService:
    """
    基于 GPU (cuDF / CuPy) 的 Leadership Bonus 结算引擎。

    推荐输入：
    - df_honor_snapshot: HonorLevelGPUService 输出快照
    - df_honor_high: Optional[HonorLevelHighGPUService 输出]
        需含 user_id, highest_honor_calc_id，最好同时含 highest_honor_lv
    """

    def __init__(self, strict_sql_mode: bool = True, max_recursive_hops: int = 5000):
        self.strict_sql_mode = strict_sql_mode
        self.max_recursive_hops = max_recursive_hops

    # ==================================================================
    # 工具函数
    # ==================================================================
    def _truncate_gpu(self, series: cudf.Series, decimals: int) -> cudf.Series:
        """
        实现 SQL TRUNCATE(val, decimals) 的严格截断，并尽量修复浮点乘法导致的
        例如 10.01 * 100 -> 1000.9999999999999 这类“略微下沉”问题。

        关键策略：
        - 不再固定加 1e-9，避免极端边界值被误抬升；
        - 仅对非负数做 1 ULP 的 nextafter(+inf) 微调，然后再 cp.trunc。
        """
        factor = 10 ** decimals
        scaled = series.values.astype("float64") * factor
        nudged = cp.where(scaled >= 0, cp.nextafter(scaled, cp.inf), scaled)
        return cudf.Series(cp.trunc(nudged) / factor, index=series.index)

    def _empty_frame(self, schema: Dict[str, object]) -> cudf.DataFrame:
        return cudf.DataFrame({col: cudf.Series(dtype=dtype) for col, dtype in schema.items()})

    def _dtype_is_numeric(self, dtype) -> bool:
        s = str(dtype).lower()
        return ("int" in s) or ("float" in s) or ("uint" in s) or ("decimal" in s)

    def _fillna_scalar(self, series: cudf.Series, text_default, num_default):
        if self._dtype_is_numeric(series.dtype):
            return series.fillna(num_default)
        return series.fillna(text_default)

    def _non_root_mask(self, series: cudf.Series) -> cudf.Series:
        """
        兼容字符串/数字两种根节点写法。
        将 0 / '0' / 0.0 / 空串 / None / <NA> 都视为“非有效节点”。
        """
        s = series.astype("str")
        mask = series.notna()
        mask = mask & (s != "0")
        mask = mask & (s != "0.0")
        mask = mask & (s != "")
        mask = mask & (s != "<NA>")
        mask = mask & (s != "None")
        mask = mask & (s != "nan")
        mask = mask & (s != "NaN")
        return mask.fillna(False)

    def _attach_sql_like_ids(self, df: cudf.DataFrame) -> cudf.DataFrame:
        """
        模拟 SQL 的 'YYYYMMDDHHMMSS' + 8 位流水号（纯 GPU 向量化实现）。
        """
        df = df.reset_index(drop=True)
        if len(df) > 0:
            prefix = time.strftime("%Y%m%d%H%M%S")
            seq = (
                cudf.Series(cp.arange(1, len(df) + 1))
                .astype("str")
                .str.pad(8, side="left", fillchar="0")
            )
            df["id"] = prefix + seq
        else:
            df["id"] = cudf.Series(dtype="str")
        return df

    def _require_columns(self, df: cudf.DataFrame, name: str, required: Iterable[str]) -> None:
        missing = set(required) - set(df.columns)
        if missing:
            raise ValueError(f"{name} 缺少必需列: {sorted(missing)}")

    def _is_missing_text_like(self, series: cudf.Series) -> cudf.Series:
        s = series.astype("str")
        mask = series.isna()
        mask = mask | (s == "")
        mask = mask | (s == "<NA>")
        mask = mask | (s == "None")
        mask = mask | (s == "nan")
        mask = mask | (s == "NaN")
        return mask.fillna(True)

    def _attach_honor_lv_by_calc_id(
            self,
            df: cudf.DataFrame,
            df_honor_levels: cudf.DataFrame,
            calc_col: str,
            out_col: str,
    ) -> cudf.DataFrame:
        if calc_col not in df.columns or len(df) == 0:
            return df

        lu = df_honor_levels[["calc_id", "honor_lv"]].copy().reset_index(drop=True)
        lu["calc_id"] = lu["calc_id"].fillna(0).astype("int32")
        key_col = f"_{calc_col}_key"
        map_col = f"_{out_col}_map"
        lu = lu.rename(columns={"calc_id": key_col, "honor_lv": map_col})

        out = df.merge(lu, left_on=calc_col, right_on=key_col, how="left")
        if out_col in out.columns:
            fill_mask = self._is_missing_text_like(out[out_col])
            out[out_col] = out[out_col].where(~fill_mask, out[map_col])
        else:
            out[out_col] = out[map_col]

        return out.drop(columns=[key_col, map_col], errors="ignore")

    # 根据df_honor_snapshot、df_honor_levels创建df_network、df_pv_raw、df_honor_last
    def _build_inputs_from_honor_snapshot(
            self,
            df_honor_snapshot: cudf.DataFrame,
            df_honor_levels: cudf.DataFrame,
    ) -> Tuple[cudf.DataFrame, cudf.DataFrame, cudf.DataFrame]:
        """
        从 HonorLevelGPUService 输出快照中切出 Leadership 所需的三份输入。
        """
        self._require_columns(
            df_honor_snapshot,
            "df_honor_snapshot",
            {
                "user_id",
                "parent_uid",
                "parent_se_id",
                "grandpa_se_id",
                "gpv_real",
                "gpv_unreal",
                "ori_honor_calc_id",
                "bonus_honor_calc_id",
                "last_honor_calc_id",
            },
        )

        # region 创建snap -> 通过df_honor_snapshot复制
        snap = df_honor_snapshot.copy().reset_index(drop=True)

        snap["user_id"] = snap["user_id"].astype(snap["user_id"].dtype)
        snap["parent_uid"] = snap["parent_uid"].fillna(0).astype("int64")
        snap["parent_se_id"] = snap["parent_se_id"].fillna(0).astype("int64")
        snap["grandpa_se_id"] = snap["grandpa_se_id"].fillna(0).astype("int64")
        snap["gpv_real"] = snap["gpv_real"].fillna(0.0).astype("float64")
        snap["gpv_unreal"] = snap["gpv_unreal"].fillna(0.0).astype("float64")
        snap["ori_honor_calc_id"] = snap["ori_honor_calc_id"].fillna(0).astype("int32")
        snap["bonus_honor_calc_id"] = snap["bonus_honor_calc_id"].fillna(0).astype("int32")
        snap["last_honor_calc_id"] = snap["last_honor_calc_id"].fillna(0).astype("int32")
        # endregion

        # region 联查df_honor_levels，通过id将对应的值放在snap中，新增ori_honor_lv、bonus_honor_lv、last_honor_lv
        # ori_honor_lv：级别等级，这个月的真实业绩（团队的深度、宽度、活跃 SE 数量）决定，
        # bonus_honor_lv：拿钱等级 = min(级别等级, 会员资格等级)
        # last_honor_lv：最终等级
        snap = self._attach_honor_lv_by_calc_id(snap, df_honor_levels, "ori_honor_calc_id", "ori_honor_lv")
        snap = self._attach_honor_lv_by_calc_id(snap, df_honor_levels, "bonus_honor_calc_id", "bonus_honor_lv")
        snap = self._attach_honor_lv_by_calc_id(snap, df_honor_levels, "last_honor_calc_id", "last_honor_lv")
        # endregion

        # region 创建df_network -> 从snap中取"user_id"、"parent_uid"、"parent_se_id"、"grandpa_se_id"
        df_network = snap[
            ["user_id", "parent_uid", "parent_se_id", "grandpa_se_id"]
        ].copy().reset_index(drop=True)
        # endregion

        # region 创建df_pv_raw -> 从snap中取"user_id"、"gpv_real"、"gpv_unreal"
        df_pv_raw = snap[
            ["user_id", "gpv_real", "gpv_unreal"]
        ].copy().reset_index(drop=True)
        # endregion

        # region 创建df_honor_last -> 从snap中获取"user_id"、"ori_honor_calc_id"、"bonus_honor_calc_id"、"last_honor_calc_id"及其lv
        honor_cols = ["user_id", "ori_honor_calc_id", "bonus_honor_calc_id", "last_honor_calc_id"]
        optional_honor_cols = [c for c in ["ori_honor_lv", "bonus_honor_lv", "last_honor_lv"] if c in snap.columns]
        df_honor_last = snap[honor_cols + optional_honor_cols].copy().reset_index(drop=True)
        # endregion

        return df_network, df_pv_raw, df_honor_last

    def _apply_honor_high_display(
            self,
            df_honor_last: cudf.DataFrame,
            df_honor_high: Optional[cudf.DataFrame],
            df_honor_levels: cudf.DataFrame,
    ) -> cudf.DataFrame:
        """
        如果提供 HonorLevelHighGPUService 的输出，则用其 historical highest 覆盖
        Leadership 结果表展示用的 last_honor_calc_id / last_honor_lv。

        说明：
        - HonorLevelHighGPUService 当前输出字段名为 highest_honor_calc_id / highest_honor_lv；
        - Leadership 结果表字段名沿用 last_honor_calc_id / last_honor_lv。
        """
        if df_honor_high is None or len(df_honor_high) == 0:
            return df_honor_last

        self._require_columns(df_honor_high, "df_honor_high", {"user_id", "highest_honor_calc_id"})

        high = df_honor_high.copy().reset_index(drop=True)
        high["user_id"] = high["user_id"].astype(df_honor_last["user_id"].dtype)
        high["highest_honor_calc_id"] = high["highest_honor_calc_id"].fillna(0).astype("int32")

        if "highest_honor_lv" not in high.columns:
            high["highest_honor_lv"] = cudf.Series([None] * len(high), index=high.index)

        high = self._attach_honor_lv_by_calc_id(high, df_honor_levels, "highest_honor_calc_id", "highest_honor_lv")
        high = high[["user_id", "highest_honor_calc_id", "highest_honor_lv"]].copy().reset_index(drop=True)
        high = high.rename(
            columns={
                "highest_honor_calc_id": "_disp_last_honor_calc_id",
                "highest_honor_lv": "_disp_last_honor_lv",
            }
        )

        out = df_honor_last.merge(high, on="user_id", how="left")

        if "last_honor_calc_id" not in out.columns:
            out["last_honor_calc_id"] = cudf.Series(cp.zeros(len(out), dtype=cp.int32), index=out.index)
        out["last_honor_calc_id"] = (
            out["_disp_last_honor_calc_id"]
            .fillna(out["last_honor_calc_id"])
            .fillna(0)
            .astype("int32")
        )

        if "last_honor_lv" not in out.columns:
            out["last_honor_lv"] = cudf.Series([None] * len(out), index=out.index)
        use_disp_lv = ~self._is_missing_text_like(out["_disp_last_honor_lv"])
        out["last_honor_lv"] = out["last_honor_lv"].where(~use_disp_lv, out["_disp_last_honor_lv"])

        return out.drop(columns=["_disp_last_honor_calc_id", "_disp_last_honor_lv"], errors="ignore")

    # ==================================================================
    # 主入口
    # ==================================================================
    def compute_leadership_bonus(
            self,
            iv_period_num: int,
            iv_calc_month: int,
            df_users: cudf.DataFrame,  # 需含: user_id, user_name, real_name, country_id, is_active
            df_honor_snapshot: cudf.DataFrame,  # HonorLevelGPUService 输出快照
            df_perf_month: cudf.DataFrame,  # 需含: period_num, country_id, pv_pcs
            df_honor_levels: cudf.DataFrame,  # 需含: calc_id, honor_lv
            df_config: cudf.DataFrame,  # 需含: config_name, value, type
            df_honor_high: Optional[cudf.DataFrame] = None,  # HonorLevelHighGPUService 输出，可选
    ) -> Dict[str, cudf.DataFrame]:
        t0 = time.perf_counter()
        LOG.info("开始 Leadership Bonus 结算，周期: %s", iv_period_num)

        # region 验证
        self._require_columns(df_users, "df_users", {"user_id", "country_id", "is_active"})
        self._require_columns(df_perf_month, "df_perf_month", {"period_num", "country_id", "pv_pcs"})
        self._require_columns(df_honor_levels, "df_honor_levels", {"calc_id", "honor_lv"})
        config_snapshot = ensure_config_snapshot(
            df_config,
            period_num=iv_period_num,
            calc_month=iv_calc_month,
        )
        # endregion

        # region 创建df_network（用户关系）、df_pv_raw（real以及unreal）、df_honor_last（等级相关）
        df_network, df_pv_raw, df_honor_last = self._build_inputs_from_honor_snapshot(
            df_honor_snapshot=df_honor_snapshot,
            df_honor_levels=df_honor_levels,
        )
        df_honor_last = self._apply_honor_high_display(
            df_honor_last=df_honor_last,
            df_honor_high=df_honor_high,
            df_honor_levels=df_honor_levels,
        )
        # endregion

        # --------------------------------------------------------------
        # 0. 配置准备（严格按 TYPE='bonus'）
        # --------------------------------------------------------------

        # region 创建df_rate_cfg 等级对应的 signed ppm
        rate_rows = config_snapshot.iter_ppm_rows("LB", "leadershipRate*")
        df_rate_cfg = cudf.DataFrame({
            "config_name": [name for name, _ in rate_rows],
            "honor_rate_ppm": [ppm for _, ppm in rate_rows],
        })
        df_rate_cfg["layer_calc_id"] = (
            df_rate_cfg["config_name"].str.replace("leadershipRate", "").astype("int32")
        )
        df_rate_cfg["honor_rate"] = df_rate_cfg["honor_rate_ppm"].astype("float64") / 1_000_000.0
        # endregion

        # region 创建df_region_cfg -> 取出国家ID、默认大区ID和默认大区名称
        # df_region_cfg -> config_name value type source_country_id region_default_id
        country_rows = config_snapshot.country_rows("LB")
        df_region_cfg = cudf.DataFrame({
            "config_name": [row["config_name"] for row in country_rows],
            "value": [row["value"] for row in country_rows],
            "type": [row["type"] for row in country_rows],
        })
        df_region_cfg["source_country_id"] = df_region_cfg["config_name"].str.replace("Country", "")
        df_region_cfg["region_default_id"] = df_region_cfg["value"]
        print("展示df_rate_cfg 111")
        print(df_rate_cfg)
        print("展示df_region_cfg 111")
        print(df_region_cfg)
        # endregion

        # --------------------------------------------------------------
        # 1. 第一层计奖业绩归集（MID2_1）
        # --------------------------------------------------------------
        # region 创建df_mid2_1 -> 记录了所有用户的购买记录 和se用户的lb_pv
        # region 创建df_base -> df_pv_raw联查df_users、df_network，组建用户关系以及real unreal
        df_base = df_pv_raw.merge(df_users[["user_id", "country_id"]], on="user_id", how="left")
        df_base = df_base.merge(df_network, on="user_id", how="left")

        # 生成没有上级的条件
        non_root_parent_se = self._non_root_mask(df_base["parent_se_id"])
        # endregion

        # region 创建df_u -> gpv_unreal>0且有上级的节点
        mask_u = (df_base["gpv_unreal"] > 0) & non_root_parent_se
        df_u = df_base[mask_u][["user_id", "parent_se_id", "country_id", "gpv_unreal"]].rename(
            columns={"user_id": "source_user_id", "parent_se_id": "se_id"}
        )
        df_u["gpv_real"] = 0.0
        # endregion

        # region 创建df_r -> gpv_real>0且有上级节点 并且se_id=parent_uid==parent_se_id？grandpa_se_id:parent_se_id
        mask_r = (df_base["gpv_real"] > 0) & non_root_parent_se
        df_r = df_base[mask_r].copy()
        cond_skip = (df_r["parent_uid"] == df_r["parent_se_id"]).fillna(False)
        df_r["se_id"] = df_r["parent_se_id"]
        df_r["se_id"] = df_r["se_id"].mask(cond_skip, df_r["grandpa_se_id"])
        df_r = df_r[self._non_root_mask(df_r["se_id"])]
        df_r = df_r[["user_id", "se_id", "country_id", "gpv_real"]].rename(
            columns={"user_id": "source_user_id"}
        )
        df_r["gpv_unreal"] = 0.0
        # endregion

        # df_mid2_1 计算出每个se用户的lb_pv
        # region 创建df_mid2_1 -> 将df_u、df_r组合在一起 生成lb_pv=gpv_real+gpv_unreal
        if len(df_u) == 0 and len(df_r) == 0:
            df_mid2_1 = self._empty_frame({
                "source_user_id": df_users["user_id"].dtype,
                "se_id": df_users["user_id"].dtype,
                "country_id": df_users["country_id"].dtype,
                "gpv_unreal": "float64",
                "gpv_real": "float64",
                "lb_pv": "float64",
            })
        else:
            df_mid2_1 = cudf.concat([df_u, df_r], ignore_index=True)
            df_mid2_1["lb_pv"] = df_mid2_1["gpv_real"] + df_mid2_1["gpv_unreal"]
        # endregion
        print("打印df_mid2_1")
        print(df_mid2_1)
        # endregion

        # --------------------------------------------------------------
        # 2. 国家种子 + 全局活跃 SE 递归（MID5_1）
        # --------------------------------------------------------------
        # region 创建df_mid5_1 -> 记录每个bonus_user_id在第几代被source_user_id贡献了多少
        # region 创建df_active_links -> 创建lb_pv>0的用户关系list
        # region 创建df_global_pv -> 聚合se_id 对lb_pv汇总
        df_global_pv = df_mid2_1.groupby("se_id").agg({"lb_pv": "sum"}).reset_index()
        # endregion

        # region 创建df_active_links（"lookup_user_id", "lookup_parent_se_id"） -> 根据active_ses取出活跃的se节点
        # 取出 lb_pv>0的se节点
        active_ses = df_global_pv[df_global_pv["lb_pv"] > 0]["se_id"]
        df_active_links = df_network[
            df_network["user_id"].isin(active_ses)
        ][["user_id", "parent_se_id"]].copy()
        df_active_links = df_active_links.rename(columns={
            "user_id": "lookup_user_id",
            "parent_se_id": "lookup_parent_se_id",
        })
        # endregion
        # endregion

        # 当前国家起步种子
        # region 创建df_seed -> 对df_mid2_1中的se_id、country_id聚合，对lb_pv进行求和 并取出lb_pv>0
        df_seed = df_mid2_1.groupby(["se_id", "country_id"]).agg({"lb_pv": "sum"}).reset_index()
        df_seed = df_seed[df_seed["lb_pv"] > 0].copy()
        # endregion

        # region 更改df_seed：联查df_network，新增parent列
        df_seed_parent = df_network[["user_id", "parent_se_id"]].rename(
            columns={"user_id": "seed_user_id", "parent_se_id": "next_parent"}
        )
        df_seed = df_seed.merge(df_seed_parent, left_on="se_id", right_on="seed_user_id", how="left")
        # endregion

        # 联查df_active_links，next_parent=lookup_user_id，
        # 不断将bonus_user_id=next_parent，next_parent=lookup_parent_se_id
        # region 计算出source_user_id贡献了多少个上级
        LOG.info("开始全局向上递归传输 (MID5_1)...")
        frontier = df_seed[["se_id", "country_id", "lb_pv", "next_parent"]].copy()
        frontier = frontier.rename(columns={
            "se_id": "source_user_id",
            "lb_pv": "seed_lb_pv",
        })
        frontier["bonus_user_id"] = frontier["source_user_id"]
        frontier["layer_calc_id"] = 10
        frontier = frontier[
            ["source_user_id", "bonus_user_id", "next_parent", "layer_calc_id", "country_id", "seed_lb_pv"]
        ]

        records = []
        for _ in range(self.max_recursive_hops):
            if len(frontier) == 0:
                break

            records.append(
                frontier[["source_user_id", "bonus_user_id", "layer_calc_id", "country_id", "seed_lb_pv"]].copy()
            )

            frontier = frontier.merge(
                df_active_links,
                left_on="next_parent",
                right_on="lookup_user_id",
                how="inner",
            )
            if len(frontier) == 0:
                break

            frontier = frontier[
                ["source_user_id", "country_id", "seed_lb_pv", "layer_calc_id", "lookup_user_id", "lookup_parent_se_id"]
            ].copy()
            frontier = frontier.rename(columns={
                "lookup_user_id": "bonus_user_id",
                "lookup_parent_se_id": "next_parent",
            })
            frontier["layer_calc_id"] = (frontier["layer_calc_id"].astype("int32") + 10).astype("int32")
            frontier = frontier[
                ["source_user_id", "bonus_user_id", "next_parent", "layer_calc_id", "country_id", "seed_lb_pv"]
            ]
        # endregion

        # region 数据验证
        # 用户关系>max_recursive_hops时 抛异常
        if len(frontier) > 0 and self.strict_sql_mode:
            raise ValueError(
                f"Leadership Bonus 递归超过安全上限 {self.max_recursive_hops} 层，可能存在环路或异常长链。"
            )
        # endregion

        # region 创建df_mid5_1 -> 记录每个bonus_user_id在第几代被source_user_id贡献了多少
        if records:
            df_mid5_1 = cudf.concat(records, ignore_index=True)
        else:
            LOG.warning("本周期未产生任何活跃 SE 种子，安全返回空表。")
            df_mid5_1 = self._empty_frame({
                "source_user_id": df_users["user_id"].dtype,
                "bonus_user_id": df_users["user_id"].dtype,
                "layer_calc_id": "int32",
                "country_id": df_users["country_id"].dtype,
                "seed_lb_pv": "float64",
            })
        # endregion

        # region 创建df_mid5_agg -> 将df_mid5_1中的bonus_user_id、layer_calc_id、country_id聚合，对seed_lb_pv求和
        df_mid5_agg = df_mid5_1.groupby(
            ["bonus_user_id", "layer_calc_id", "country_id"]
        ).agg({"seed_lb_pv": "sum"}).reset_index().rename(
            columns={"bonus_user_id": "user_id", "seed_lb_pv": "lb_pv"}
        )
        # endregion
        # endregion

        # --------------------------------------------------------------
        # 3. 第一级拦截 + 大区转换（AR_CALC_LV_HONOR_PV_1）
        # --------------------------------------------------------------
        # 创建df_pv_1 -> 新增等级信息 df_mid5_agg联查df_honor_last，将lv对齐
        # region 并做第一层筛选 layer_calc_id<=ori_honor_calc_id 筛选出与当期业绩对应的有效记录
        df_pv_1 = df_mid5_agg.merge(
            df_honor_last[["user_id", "ori_honor_calc_id", "bonus_honor_calc_id", "bonus_honor_lv"]],
            on="user_id",
            how="left",
        )
        df_pv_1["ori_honor_calc_id"] = df_pv_1["ori_honor_calc_id"].fillna(0).astype("int32")
        df_pv_1["bonus_honor_calc_id"] = df_pv_1["bonus_honor_calc_id"].fillna(0).astype("int32")
        # 防止数据溢出
        df_pv_1 = df_pv_1[df_pv_1["layer_calc_id"] <= df_pv_1["ori_honor_calc_id"]].copy()

        df_pv_1 = df_pv_1.merge(
            df_honor_levels.rename(columns={"calc_id": "layer_calc_id", "honor_lv": "layer_lv"}),
            on="layer_calc_id",
            how="left",
        )
        # endregion

        # 更新df_pv_1 -> 新增国家信息 country_id联查df_region_cfg的source_country_id
        # region 获取region_default_id “calc_country_id” = region_default_id!=null?region_default_id:country_id
        df_pv_1 = df_pv_1.merge(df_region_cfg, left_on="country_id", right_on="source_country_id", how="left")
        df_pv_1["calc_country_id"] = df_pv_1["region_default_id"].fillna(df_pv_1["country_id"])
        # endregion

        # --------------------------------------------------------------
        # 4. 每层总盘 / 总池 / 单价 计算 此级别所在区域的总奖⾦ 和 此级别所在区域的⽐例
        # --------------------------------------------------------------
        # 算出每个国家 每个层级当月的lv_pv
        # region 创建df_pool -> df_pv_1聚合calc_country_id、layer_calc_id，对lb_pv（total_lb_pv）求和
        df_pool = df_pv_1.groupby(["calc_country_id", "layer_calc_id"]).agg({"lb_pv": "sum"}).reset_index()
        df_pool = df_pool.rename(columns={"lb_pv": "total_lb_pv"})
        # endregion

        # region 创建df_total_perf -> 算出当前区域的总业绩 total_pv
        # 创建df_perf_curr -> 根据df_perf_month取出当期的国家总业绩
        # 创建df_perf_mapped -> df_perf_curr的country_id 联查 df_region_cfg的source_country_id
        # region 更新df_perf_mapped -> 新增calc_country_id calc_country_id = region_default_id!=null?region_default_id:country_id
        df_perf_curr = df_perf_month[df_perf_month["period_num"] == iv_period_num].copy()
        df_perf_mapped = df_perf_curr.merge(
            df_region_cfg,
            left_on="country_id",
            right_on="source_country_id",
            how="left",
        )
        df_perf_mapped["calc_country_id"] = df_perf_mapped["region_default_id"].fillna(df_perf_mapped["country_id"])
        # endregion

        # region 创建df_total_perf -> df_perf_mapped聚合calc_country_id 对pv_pcs（total_pv）求和
        df_total_perf = df_perf_mapped.groupby("calc_country_id").agg({"pv_pcs": "sum"}).reset_index().rename(
            columns={"pv_pcs": "total_pv"}
        )
        # endregion
        # endregion

        # region 创建df_rate -> df_pool联查df_total_perf 获取total_pv
        df_rate = df_pool.merge(df_total_perf, on="calc_country_id", how="left")
        df_rate["total_pv"] = df_rate["total_pv"].fillna(0.0)
        # endregion

        # region 更新df_rate -> df_rate联查df_rate_cfg 获取honor_rate
        print("展示df_rate_cfg")
        print(df_rate_cfg)
        df_rate = df_rate.merge(df_rate_cfg[["layer_calc_id", "honor_rate"]], on="layer_calc_id", how="left")
        df_rate["honor_rate"] = df_rate["honor_rate"].fillna(0.0)
        # endregion

        # region 计算honor_bonus（此级别所在区域的总奖⾦）=total_pv*honor_rate
        # 此级别区域的总奖⾦=区域的⽉BV × 每层的比例
        df_rate["honor_bonus"] = self._truncate_gpu(df_rate["honor_rate"] * df_rate["total_pv"], 6)
        # endregion

        # region 计算lb_rate（此级别所在区域的⽐例）=honor_bonus/total_lb_pv
        # 此级别所在区域的⽐例 = 此级别区域的总奖⾦ ÷ 此级别所有符合者总lb_pv
        safe_lb_rate = cp.where(
            df_rate["total_lb_pv"].values > 0,
            df_rate["honor_bonus"].values / df_rate["total_lb_pv"].values,
            0.0,
        )
        df_rate["lb_rate"] = self._truncate_gpu(cudf.Series(safe_lb_rate, index=df_rate.index), 6)
        # endregion

        # --------------------------------------------------------------
        # 5. DETAIL_COUNTRY1 / DETAIL_COUNTRY 计算每个区域每个用户每个级别的奖金 然后对发奖金的用户 同区还原
        # --------------------------------------------------------------

        # 创建df_detail1 -> df_pv_1联查df_rate。通过calc_country_id、layer_calc_id 获取lb_rate
        # 计算row_bonus（此级别国家的个⼈奖⾦）= lb_pv*lb_rate
        # region 此级别区域的个⼈奖⾦ = 此区域的每个用户每个级别的lb_pv ×此级别国家的⽐例
        df_detail1 = df_pv_1.merge(df_rate, on=["calc_country_id", "layer_calc_id"], how="inner")
        df_detail1["row_bonus"] = self._truncate_gpu(df_detail1["lb_pv"] * df_detail1["lb_rate"], 2)
        # endregion

        # 创建df_detail_agg -> df_detail1聚合"user_id", "layer_calc_id", "calc_country_id"
        # 对lb_pv、row_bonus（row_bonus）求和
        # region 得出每个用户在每个级别每个区域的奖金
        df_detail_agg = df_detail1.groupby(["user_id", "layer_calc_id", "calc_country_id"]).agg(
            {
                "lb_pv": "sum",
                "row_bonus": "sum",
                "bonus_honor_lv": "first",
                "bonus_honor_calc_id": "max",
                "total_lb_pv": "max",
                "total_pv": "max",
                "honor_rate": "max",
                "honor_bonus": "max",
                "lb_rate": "max",
                "layer_lv": "first",
            }
        ).reset_index().rename(columns={"row_bonus": "bonus_lb"})
        # endregion

        # region 更新df_detail_agg -> 通过user_id，df_detail_agg联查df_users获取country_id（user_country）
        df_detail_agg = df_detail_agg.merge(
            df_users[["user_id", "country_id"]].rename(columns={"country_id": "user_country"}),
            on="user_id",
            how="left",
        )
        # endregion

        # region 更新df_detail_agg -> 通过user_country df_detail_agg联查df_region_cfg 获取region_default_id（u_region）
        df_detail_agg = df_detail_agg.merge(
            df_region_cfg.rename(columns={"source_country_id": "u_src", "region_default_id": "u_region"}),
            left_on="user_country",
            right_on="u_src",
            how="left",
        )
        # endregion

        # 下单区域（calc_country_id）如果和拿奖用户的区域ID（u_region）一致，
        # 那结算用户的bonus_country_id=（还原）user_country，否则=calc_country_id
        # region 创建df_detail_country_out -> 同区还原
        cond_restore = (df_detail_agg["calc_country_id"] == df_detail_agg["u_region"]).fillna(False)
        df_detail_agg["bonus_country_id"] = df_detail_agg["calc_country_id"]
        df_detail_agg["bonus_country_id"] = df_detail_agg["bonus_country_id"].mask(
            cond_restore,
            df_detail_agg["user_country"],
        )

        df_detail_agg["period_num"] = iv_period_num
        df_detail_agg["calc_month"] = iv_calc_month

        df_detail_country_out = df_detail_agg[[
            "period_num", "calc_month", "user_id", "layer_lv", "layer_calc_id", "lb_pv",
            "bonus_honor_lv", "bonus_honor_calc_id", "total_lb_pv", "total_pv",
            "honor_rate", "honor_bonus", "lb_rate", "bonus_lb", "bonus_country_id",
        ]].rename(columns={"bonus_country_id": "country_id"})
        # endregion

        # --------------------------------------------------------------
        # 6. 国家级落表 输出每个用户在每个国家的奖金
        # --------------------------------------------------------------

        # region 保留符合层级条件的层级奖金，降不符合条件的层级奖金赋值0
        is_payout_valid = (df_detail_agg["layer_calc_id"] <= df_detail_agg["bonus_honor_calc_id"]).fillna(False)
        df_detail_agg["valid_bonus_lb"] = df_detail_agg["bonus_lb"].where(is_payout_valid, 0.0)
        # endregion

        # 创建df_bonus_country -> 对"user_id", "bonus_country_id"聚合
        # 对bonus_lb（理论获得的钱）、valid_bonus_lb（实际获得的钱）求和
        # region 得出理论上拿的奖金和实际到手的奖金
        df_bonus_country = df_detail_agg.groupby(["user_id", "bonus_country_id"]).agg(
            {"bonus_lb": "sum", "valid_bonus_lb": "sum"}
        ).reset_index()

        df_bonus_country["bonus_lb"] = self._truncate_gpu(df_bonus_country["bonus_lb"], 2)
        df_bonus_country["valid_bonus_lb"] = self._truncate_gpu(df_bonus_country["valid_bonus_lb"], 2)
        # endregion

        # region 筛选出有奖金的数据
        df_bonus_country = df_bonus_country[df_bonus_country["valid_bonus_lb"] > 0].copy()
        # endregion

        # region 更新df_bonus_country -> 联查df_honor_last 展示last_honor_lv（历史最高）
        df_bonus_country = df_bonus_country.merge(
            df_honor_last[["user_id", "last_honor_lv", "last_honor_calc_id"]],
            on="user_id",
            how="left",
        )
        # endregion

        # region 更新df_bonus_country -> 联查df_users 展示"is_active", "country_id"
        df_bonus_country = df_bonus_country.merge(
            df_users[["user_id", "is_active", "country_id"]],
            on="user_id",
            how="left",
        )
        # endregion

        # region 创建df_bonus_country_out
        df_bonus_country["last_honor_lv"] = self._fillna_scalar(df_bonus_country["last_honor_lv"], "-1", -1)
        df_bonus_country["last_honor_calc_id"] = self._fillna_scalar(df_bonus_country["last_honor_calc_id"], "-1", -1)
        df_bonus_country["country_id"] = self._fillna_scalar(df_bonus_country["country_id"], "-1", -1)
        df_bonus_country["is_active"] = df_bonus_country["is_active"].fillna(0)
        df_bonus_country["period_num"] = iv_period_num
        df_bonus_country["calc_month"] = iv_calc_month
        df_bonus_country = self._attach_sql_like_ids(df_bonus_country)

        df_bonus_country_out = df_bonus_country[[
            "id", "period_num", "calc_month", "user_id", "last_honor_lv", "last_honor_calc_id",
            "bonus_lb", "valid_bonus_lb", "country_id", "bonus_country_id", "is_active",
        ]].rename(columns={"bonus_lb": "ori_bonus_lb", "valid_bonus_lb": "bonus_lb"})
        # endregion

        # --------------------------------------------------------------
        # 7. 全局汇总落表
        # --------------------------------------------------------------
        # 创建df_global_detail -> df_detail_agg聚合"user_id", "layer_calc_id"
        # region 对lb_pv、total_lb_pv、total_pv、bonus_lb求和
        df_global_detail = df_detail_agg.groupby(["user_id", "layer_calc_id"]).agg(
            {
                "lb_pv": "sum",
                "bonus_honor_lv": "first",
                "bonus_honor_calc_id": "max",
                "total_lb_pv": "sum",
                "total_pv": "sum",
                "honor_rate": "max",
                "honor_bonus": "sum",
                "bonus_lb": "sum",
                "layer_lv": "first",
            }
        ).reset_index()
        # endregion

        # region 创建df_global_detail中的lb_rate：bonus_lb（总奖金）/lb_pv（总业绩）
        safe_global_lb_rate = cp.where(
            df_global_detail["lb_pv"].values > 0,
            df_global_detail["bonus_lb"].values / df_global_detail["lb_pv"].values,
            0.0,
        )
        df_global_detail["lb_rate"] = cudf.Series(safe_global_lb_rate, index=df_global_detail.index)
        # endregion

        # region 创建df_global_detail_out 统计出当期该用户在每一代贡献了多少钱 不区分区域
        df_global_detail["period_num"] = iv_period_num
        df_global_detail["calc_month"] = iv_calc_month
        df_global_detail_out = df_global_detail[[
            "period_num", "calc_month", "user_id", "layer_lv", "layer_calc_id", "lb_pv",
            "bonus_honor_lv", "bonus_honor_calc_id", "total_lb_pv", "total_pv",
            "honor_rate", "honor_bonus", "lb_rate", "bonus_lb",
        ]]
        # endregion

        # region 创建df_global_summary
        df_global_summary = df_bonus_country_out.groupby("user_id").agg(
            {"ori_bonus_lb": "sum", "bonus_lb": "sum"}
        ).reset_index()
        df_global_summary = df_global_summary.merge(
            df_honor_last[["user_id", "last_honor_lv", "last_honor_calc_id"]],
            on="user_id",
            how="left",
        )
        df_global_summary = df_global_summary.merge(
            df_users[["user_id", "country_id", "is_active"]],
            on="user_id",
            how="left",
        )
        df_global_summary["last_honor_lv"] = self._fillna_scalar(df_global_summary["last_honor_lv"], "-1", -1)
        df_global_summary["last_honor_calc_id"] = self._fillna_scalar(df_global_summary["last_honor_calc_id"], "-1", -1)
        df_global_summary["country_id"] = self._fillna_scalar(df_global_summary["country_id"], "-1", -1)
        df_global_summary["is_active"] = df_global_summary["is_active"].fillna(0)
        df_global_summary["period_num"] = iv_period_num
        df_global_summary["calc_month"] = iv_calc_month
        df_global_summary = self._attach_sql_like_ids(df_global_summary)
        # endregion

        # region 创建df_bonus_country_out 统计出当期该用户的全球业绩
        df_global_summary_out = df_global_summary[[
            "id", "period_num", "calc_month", "user_id", "last_honor_lv", "last_honor_calc_id",
            "ori_bonus_lb", "bonus_lb", "country_id", "is_active",
        ]]
        # endregion

        # --------------------------------------------------------------
        # 8. 溯源表 AR_CALC_BE_LB_MID3 / AR_CALC_BONUS_LB_COUNTRY_SOURCE
        # --------------------------------------------------------------
        LOG.info("生成溯源明细...")
        if len(df_mid5_1) == 0 or len(df_mid2_1) == 0:
            trace_schema = {
                "period_num": "int32",
                "calc_month": "int32",
                "bonus_user_id": df_users["user_id"].dtype,
                "bonus_user_name": df_users["user_name"].dtype if "user_name" in df_users.columns else "object",
                "bonus_real_name": df_users["real_name"].dtype if "real_name" in df_users.columns else "object",
                "source_user_id": df_users["user_id"].dtype,
                "source_user_name": df_users["user_name"].dtype if "user_name" in df_users.columns else "object",
                "source_real_name": df_users["real_name"].dtype if "real_name" in df_users.columns else "object",
                "bonus_layer": "int32",
                "source_gpv_real": "float64",
                "source_gpv_unreal": "float64",
                "is_active": df_users["is_active"].dtype if "is_active" in df_users.columns else "int32",
                "source_country_id": df_users["country_id"].dtype,
                "bonus_country_id": df_users["country_id"].dtype,
                "ori_honor_lv": df_honor_levels[
                    "honor_lv"].dtype if "honor_lv" in df_honor_levels.columns else "object",
                "ori_honor_calc_id": "int32",
                "bonus_honor_lv": df_honor_levels[
                    "honor_lv"].dtype if "honor_lv" in df_honor_levels.columns else "object",
                "bonus_honor_calc_id": "int32",
            }
            df_mid3 = self._empty_frame(trace_schema)
            df_source_out = self._empty_frame(trace_schema)
        else:
            # df_mid2_1 记录了购买用户 且计算出每个se_id用户的lb_pv
            # df_mid5_1 记录了source_user_id 且计算出每个bonus_user_id在第几代被source_user_id贡献了多少
            # region 创建df_trace -> df_mid5_1的source_user_id联查df_mid2_1的se_id，能查出是谁真正买单
            df_mid5_trace = df_mid5_1[["source_user_id", "bonus_user_id", "layer_calc_id"]].drop_duplicates()
            df_mid5_trace = df_mid5_trace.rename(columns={"source_user_id": "seed_user_id"})
            df_mid2_trace = df_mid2_1.rename(columns={"source_user_id": "bottom_source_user_id"})
            df_trace = df_mid2_trace.merge(df_mid5_trace, left_on="se_id", right_on="seed_user_id", how="inner")
            # endregion

            # region df_trace联查df_users 获取bottom_source_user_id、bonus_user_id的相关信息
            # 严格对齐 SQL：INNER JOIN AR_USER U1
            df_trace = df_trace.merge(
                df_users[["user_id", "user_name", "real_name", "country_id"]].rename(
                    columns={
                        "user_id": "bottom_source_user_id",
                        "country_id": "source_country_id",
                        "user_name": "source_user_name",
                        "real_name": "source_real_name",
                    }
                ),
                on="bottom_source_user_id",
                how="inner",
            )

            # 严格对齐 SQL：INNER JOIN AR_USER U2
            df_trace = df_trace.merge(
                df_users[["user_id", "user_name", "real_name", "country_id", "is_active"]].rename(
                    columns={
                        "user_id": "bonus_user_id",
                        "country_id": "b_country_id",
                        "user_name": "bonus_user_name",
                        "real_name": "bonus_real_name",
                    }
                ),
                on="bonus_user_id",
                how="inner",
            )
            # endregion

            # region df_trace联查df_honor_last 获取bonus_honor_calc_id（拿钱等级）
            # SQL 对 AR_CALC_LV_HONOR / 大区配置是 LEFT JOIN
            df_trace = df_trace.merge(
                df_honor_last[
                    ["user_id", "ori_honor_lv", "ori_honor_calc_id", "bonus_honor_lv", "bonus_honor_calc_id"]].rename(
                    columns={"user_id": "bonus_user_id"}
                ),
                on="bonus_user_id",
                how="left",
            )
            # endregion

            # region df_trace联查 df_region_cfg获取购买者和bonus_user的国家信息
            df_trace = df_trace.merge(
                df_region_cfg.rename(columns={"source_country_id": "rc1_src", "region_default_id": "rc1_reg"}),
                left_on="source_country_id",
                right_on="rc1_src",
                how="left",
            )
            df_trace = df_trace.merge(
                df_region_cfg.rename(columns={"source_country_id": "rc2_src", "region_default_id": "rc2_reg"}),
                left_on="b_country_id",
                right_on="rc2_src",
                how="left",
            )
            # endregion

            # bonus_country_id = 下单用户的国家id有大区 且 和奖金用户属于同区 -> b_country_id(奖金用户的国籍)
            # bonus_country_id = 下单用户的国家id有大区 且 和奖金用户不属于同区 -> rc1_reg(下单用户所在区域)
            # bonus_country_id = 下单用户的国家id没有大区 -> source_country_id(下单用户国籍)
            # region 计算bonus_country_id归属地
            has_rc1 = df_trace["rc1_src"].notna().fillna(False)
            same_reg = (df_trace["rc1_reg"] == df_trace["rc2_reg"]).fillna(False)

            df_trace["bonus_country_id"] = df_trace["source_country_id"]
            df_trace["bonus_country_id"] = df_trace["bonus_country_id"].mask(
                has_rc1 & same_reg,
                df_trace["b_country_id"],
            )
            df_trace["bonus_country_id"] = df_trace["bonus_country_id"].mask(
                has_rc1 & (~same_reg),
                df_trace["rc1_reg"],
            )
            # endregion

            # region 数据填充
            df_trace["is_active"] = df_trace["is_active"].fillna(0)
            df_trace["bonus_honor_calc_id"] = df_trace["bonus_honor_calc_id"].fillna(0).astype("int32")
            df_trace["ori_honor_calc_id"] = df_trace["ori_honor_calc_id"].fillna(0).astype("int32")
            df_trace["period_num"] = iv_period_num
            df_trace["calc_month"] = iv_calc_month
            # endregion

            # region 创建df_mid3 -> 部分字段重命名
            df_mid3 = df_trace[[
                "period_num", "calc_month", "bonus_user_id", "bonus_user_name", "bonus_real_name",
                "bottom_source_user_id", "source_user_name", "source_real_name", "layer_calc_id",
                "gpv_real", "gpv_unreal", "is_active", "source_country_id", "bonus_country_id",
                "ori_honor_lv", "ori_honor_calc_id", "bonus_honor_lv", "bonus_honor_calc_id",
            ]].rename(columns={
                "bottom_source_user_id": "source_user_id",
                "layer_calc_id": "bonus_layer",
                "gpv_real": "source_gpv_real",
                "gpv_unreal": "source_gpv_unreal",
            })
            # endregion

            # region 创建df_source_out -> 过滤出消费的数据
            # 筛选出有业绩的数据
            mask_source_valid = (df_mid3["source_gpv_real"] > 0) | (df_mid3["source_gpv_unreal"] > 0)
            # 资格拦截
            mask_layer_valid = df_mid3["bonus_layer"] <= df_mid3["bonus_honor_calc_id"]
            df_source_out = df_mid3[mask_source_valid & mask_layer_valid].copy()
            # endregion

        elapsed = time.perf_counter() - t0
        LOG.info("Leadership Bonus GPU 计算完成，耗时: %.4f秒", elapsed)

        return {
            # region 当前周期 在某国家（country_id）该用户（user_id）在第几代（layer_calc_id）赚了多少钱（bonus_lb）
            # honor_bonus (当期·国家总奖金池)、total_lb_pv (当期·国家总合格业绩)
            # lb_rate (当期·单价汇率)，lb_rate = honor_bonus / total_lb_pv （总钱数 ÷ 总PV）
            # lb_pv(当期·个人有效业绩)
            "AR_CALC_BE_LB_DETAIL_COUNTRY": df_detail_country_out.reset_index(drop=True),
            # endregion

            # region 当前周期 在某些国家（bonus_country_id）需要给用户（user_id）的当地（country_id）银行卡发多少钱（bonus_lb）
            # ori_bonus_lb（理论奖金）会员等级不限制的条件下
            "AR_CALC_BONUS_LB_COUNTRY": df_bonus_country_out.reset_index(drop=True),
            # endregion

            # region 当前周期 该用户（user_id）在每一代贡献了多少钱（bonus_lb） 不区分区域
            # honor_bonus (当期·国家总奖金池)、total_lb_pv (当期·国家总合格业绩)
            # lb_rate (当期·单价汇率)，lb_rate = honor_bonus / total_lb_pv （总钱数 ÷ 总PV）
            # lb_pv(当期·个人有效业绩)
            "AR_CALC_BE_LB_DETAIL": df_global_detail_out.reset_index(drop=True),
            # endregion

            # region 当前周期 该用户（user_id）在全球获得的总奖金（bonus_lb）
            # ori_bonus_lb（理论奖金）会员等级不限制的条件下
            "AR_CALC_BONUS_LB": df_global_summary_out.reset_index(drop=True),
            # endregion

            # region 所有记录 包含0业绩 所有的底层小弟（source_user_id）分别给上级（bonus_user_id）输送了多少 real 和 unreal
            # bonus_layer 这笔业绩在得奖人视角下是第几代/第几层
            "AR_CALC_BE_LB_MID3": df_mid3.reset_index(drop=True),
            # endregion

            # region 过滤0业绩 所有的底层小弟（source_user_id）分别给上级（bonus_user_id）输送了多少 real 和 unreal
            "AR_CALC_BONUS_LB_COUNTRY_SOURCE": df_source_out.reset_index(drop=True),
            # endregion
        }


def main():
    # ══════════════════════════════════════════════════════════════
    # 基础参数
    # ══════════════════════════════════════════════════════════════
    iv_period_num = 12
    iv_calc_month = 6

    # ══════════════════════════════════════════════════════════════
    # 参数 1: df_users —— 来源：AR_USER 表
    # ══════════════════════════════════════════════════════════════
    df_users = cudf.DataFrame({
        "user_id": [1001, 1002, 1003, 1004, 1005, 1006],
        "user_name": ["A", "B", "C", "D", "E", "F"],
        "real_name": ["张A", "李B", "王C", "赵D", "陈E", "刘F"],
        "country_id": ["MY", "MY", "MY", "SG", "MY", "MY"],
        "is_active": [1, 1, 1, 1, 1, 1],
    })

    # ══════════════════════════════════════════════════════════════
    # 参数 2: df_honor_snapshot
    #         —— 来源：HonorLevelGPUService (fixed) 的 df_f 输出
    #
    # 新版 df_f 比原版多了 3 列：
    #   grandpa_se_id, gpv_real, gpv_unreal
    #
    # LeadershipBonusGPUService 内部会自动切分成：
    #   df_network   ← user_id, parent_uid, parent_se_id, grandpa_se_id
    #   df_pv_raw    ← user_id, gpv_real, gpv_unreal
    #   df_honor_last← user_id, ori_honor_calc_id, bonus_honor_calc_id,
    #                   last_honor_calc_id (+ *_lv)
    # ══════════════════════════════════════════════════════════════
    df_honor_snapshot = cudf.DataFrame({
        # --- 网络关系 ---
        "user_id": [1001, 1002, 1003, 1004, 1005, 1006],
        "parent_uid": [0, 1001, 1002, 1003, 1004, 1005],
        "parent_se_id": [0, 1001, 1002, 1003, 1004, 1005],
        "grandpa_se_id": [0, 0, 1001, 1002, 1003, 1004],
        # --- 业绩拆分 ---
        "gpv_real": [1000.0, 1000.0, 1500.0, 1000.0, 1200.0, 0.0],
        "gpv_unreal": [1500.0, 2000.0, 0.0, 1000.0, 0.0, 0.0],
        # --- 奖衔等级 ---
        "ori_honor_calc_id": [40, 30, 20, 10, 10, 0],
        "bonus_honor_calc_id": [40, 30, 20, 10, 10, 0],
        "last_honor_calc_id": [40, 30, 20, 10, 10, 0],
        # --- 以下为 df_f 中的其他列（Leadership 不直接使用，但带着没关系）---
        "lb_pv": [3500.0, 1000.0, 2200.0, 0.0, 0.0, 0.0],
        "legs_max_calc_id": [40, 30, 20, 10, 10, 0],
        "honor90_legs": [0, 0, 0, 0, 0, 0],
        "honor80_legs": [0, 0, 0, 0, 0, 0],
        "honor70_legs": [0, 0, 0, 0, 0, 0],
        "se_num_excluding_self": [4, 3, 2, 1, 1, 0],
        "is_active": [1, 1, 1, 1, 1, 1],
        "last_elite_calc_id": [30, 30, 30, 30, 30, 0],
        "limit_honor_calc_id": [90, 90, 90, 90, 90, 0],
    })
    #
    # 实际生产中，直接用 HonorLevelGPUService 的返回值：
    #
    #   honor_svc = HonorLevelGPUService()
    #   df_honor_snapshot, df_layer_records = honor_svc.recompute_all_gpu(
    #       df_honor_levels=df_honor_levels
    #   )
    #

    # ══════════════════════════════════════════════════════════════
    # 参数 3: df_perf_month —— 来源：AR_USER_PERF 表
    # ══════════════════════════════════════════════════════════════
    df_perf_month = cudf.DataFrame({
        "period_num": [12, 12, 12],
        "country_id": ["MY", "SG", "BN"],
        "pv_pcs": [300000.0, 150000.0, 50000.0],
    })

    # ══════════════════════════════════════════════════════════════
    # 参数 4: df_honor_levels —— 来源：AR_HONOR_LEVEL 维表
    # ══════════════════════════════════════════════════════════════
    df_honor_levels = cudf.DataFrame({
        "calc_id": [10, 20, 30, 40, 50, 60, 70, 80, 90],
        "honor_lv": [
            "Director", "2S_Director", "3S_Director",
            "Diamond", "2S_Diamond", "3S_Diamond",
            "Crown", "2S_Crown", "3S_Crown",
        ],
    })

    # ══════════════════════════════════════════════════════════════
    # 参数 5: df_config —— 来源：AR_CONFIG 配置表
    # ══════════════════════════════════════════════════════════════
    df_config = cudf.DataFrame({
        "config_name": [
            "leadershipRate10", "leadershipRate20", "leadershipRate30",
            "leadershipRate40", "leadershipRate50", "leadershipRate60",
            "leadershipRate70", "leadershipRate80", "leadershipRate90",
            "CountrySG", "CountryBN",
        ],
        "value": [
            "4.5", "4.5", "4.5",
            "3.6", "3.6", "3.6",
            "1.8", "1.8", "1.8",
            "MY", "MY",
        ],
        "type": [
            "bonus", "bonus", "bonus",
            "bonus", "bonus", "bonus",
            "bonus", "bonus", "bonus",
            "bonus", "bonus",
        ],
    })

    # ══════════════════════════════════════════════════════════════
    # 参数 6 (可选): df_honor_high
    #         —— 来源：HonorLevelHighGPUService 的 df_result 输出
    #
    # 必需列：user_id, highest_honor_calc_id
    # 可选列：highest_honor_lv（没有的话会自动通过 df_honor_levels 补全）
    #
    # 作用：用历史最高奖衔覆盖结果表中的 last_honor_calc_id / last_honor_lv 展示字段。
    # 如果不传，结果表中的 last_honor_* 就是 HonorLevelGPUService 的当期计算值。
    # ══════════════════════════════════════════════════════════════
    df_honor_high = cudf.DataFrame({
        "user_id": [1001, 1002, 1003, 1004, 1005],
        "highest_honor_calc_id": [40, 30, 20, 10, 10],
        "highest_honor_lv": ["Diamond", "3S_Director", "2S_Director", "Director", "Director"],
    })
    #
    # 实际生产中：
    #
    #   high_svc = HonorLevelHighGPUService()
    #   df_honor_high, df_record_out = high_svc.compute_highest_honor_gpu(
    #       iv_period_num=iv_period_num,
    #       iv_calc_month=iv_calc_month,
    #       df_last_honor=...,         # 当月 Honor 结果
    #       df_history_record=...,     # 历史记录
    #       df_push_record=None,       # PUSH 补录（可选）
    #       df_user_highest=...,       # AR_USER 快照
    #       df_honor_levels=df_honor_levels,
    #   )
    #

    # ══════════════════════════════════════════════════════════════
    # 调用计算
    # ══════════════════════════════════════════════════════════════
    service = LeadershipBonusGPUService(strict_sql_mode=True)

    results = service.compute_leadership_bonus(
        iv_period_num=iv_period_num,
        iv_calc_month=iv_calc_month,
        df_users=df_users,
        df_honor_snapshot=df_honor_snapshot,  # ← 直接传 HonorLevel 的 df_f
        df_perf_month=df_perf_month,
        df_honor_levels=df_honor_levels,
        df_config=df_config,
        df_honor_high=df_honor_high,  # ← 可选，传了则覆盖展示字段
    )

    # ══════════════════════════════════════════════════════════════
    # 查看结果
    # ══════════════════════════════════════════════════════════════
    for table_name, df in results.items():
        print(f"\n{'=' * 70}")
        print(f"  {table_name}  ({len(df)} rows)")
        print(f"{'=' * 70}")
        if len(df) > 0:
            print(df.to_pandas().to_string(index=False))
        else:
            print("  (empty)")

    # ══════════════════════════════════════════════════════════════════
    # 附：新版 vs 原版接口对比
    # ══════════════════════════════════════════════════════════════════
    #
    #  原版 compute_leadership_bonus() 签名：
    #  ┌──────────────────────────────────────────────────────────────┐
    #  │ iv_period_num                                                │
    #  │ iv_calc_month                                                │
    #  │ df_users          ← AR_USER                                  │
    #  │ df_network        ← 需手动从 df_f 拼装 + 推导 grandpa_se_id  │
    #  │ df_pv_raw         ← 需手动重算 gpv_real / gpv_unreal         │
    #  │ df_honor_last     ← 需手动合并 HonorLevel + HonorHigh 结果   │
    #  │ df_perf_month     ← AR_USER_PERF                             │
    #  │ df_honor_levels   ← AR_HONOR_LEVEL                           │
    #  │ df_config         ← AR_CONFIG                                │
    #  └──────────────────────────────────────────────────────────────┘
    #
    #  新版 compute_leadership_bonus() 签名：
    #  ┌──────────────────────────────────────────────────────────────┐
    #  │ iv_period_num                                                │
    #  │ iv_calc_month                                                │
    #  │ df_users            ← AR_USER                                │
    #  │ df_honor_snapshot   ← HonorLevelGPUService.df_f 直接传入     │
    #  │ df_perf_month       ← AR_USER_PERF                           │
    #  │ df_honor_levels     ← AR_HONOR_LEVEL                         │
    #  │ df_config           ← AR_CONFIG                              │
    #  │ df_honor_high=None  ← HonorHighGPUService.df_result (可选)   │
    #  └──────────────────────────────────────────────────────────────┘
    #
    #  原来需要手动做的 3 件事（推导 grandpa、重算 gpv 拆分、合并 honor 结果）
    #  现在全部由 LeadershipBonusGPUService 内部的
    #  _build_inputs_from_honor_snapshot() 和
    #  _apply_honor_high_display() 自动完成。


if __name__ == "__main__":
    main()
