from __future__ import annotations

"""
Honor Level High GPU 历史最高奖衔滚动判定系统（修正版）

对齐资料：
- CALC_LV_HONOR_HIGH.sql
- 需求规格说明书_历史最高奖衔滚动判定系统_V2.5.md

"""

import logging
import time
from typing import Iterable, Optional, Tuple

import cudf
import cupy as cp

LOG = logging.getLogger("User.HonorLevelHighGPUService")


class HonorLevelHighGPUService:
    """
    基于 GPU（cuDF / CuPy）的历史最高奖衔滚动判定实现。

    输入语义：
    - iv_period_num: 当前周期编号
    - df_last_honor: 当月奖衔结果，当前周期的 AR_CALC_LV_HONOR 结果（每个 user_id 最多一行）
    - df_history_record: 历史记录，既有 AR_CALC_LV_HONOR_RECORD 全量 / 当前作用域数据
    - df_push_record: PUSH补录记录，AR_CALC_LV_HONOR_RECORD_PUSH 数据
    - df_user_highest: 用户最高奖衔快照，AR_USER 的 user_id / highest_honor_lv 快照
    - df_honor_levels: 奖衔维表，AR_HONOR_LEVEL 维表，必须包含 calc_id、honor_lv

    返回：
    - df_result: 对齐 AR_CALC_LV_HONOR_HIGH 的结果集
    - df_record_out: 对齐 AR_CALC_LV_HONOR_RECORD 的新记录集
    """

    def __init__(self, strict_sql_mode: bool = True, deduplicate_history: bool = False):
        self.strict_sql_mode = strict_sql_mode
        self.deduplicate_history = deduplicate_history

    # ==================================================================
    # 主入口
    # ==================================================================
    def compute_highest_honor_gpu(
            self,
            iv_period_num: int,
            df_last_honor: Optional[cudf.DataFrame],
            df_history_record: Optional[cudf.DataFrame],
            df_push_record: Optional[cudf.DataFrame],
            df_user_highest: cudf.DataFrame,
            df_honor_levels: cudf.DataFrame,
    ) -> Tuple[cudf.DataFrame, cudf.DataFrame]:
        t0 = time.perf_counter()
        # region 参数验证
        self._validate_entry_args(iv_period_num)
        self._validate_input_schemas(
            df_last_honor=df_last_honor,
            df_history_record=df_history_record,
            df_push_record=df_push_record,
            df_user_highest=df_user_highest,
            df_honor_levels=df_honor_levels,
        )
        # endregion

        # region 获取user_id的type
        user_id_dtype = self._resolve_user_id_dtype(
            df_user_highest, df_last_honor, df_history_record, df_push_record
        )
        # endregion

        LOG.info("开始最高奖衔计算，period=%s", iv_period_num)

        # --------------------------------------------------------------
        # 0. 奖衔维表准备：calc_id -> 奖衔主键 ID
        # --------------------------------------------------------------
        # region 创建df_hl 通过df_honor_levels copy，并获取70、80、90的值
        # 将df_honor_levels中的 “calc_id、honor_lv” 变成 “calc_id、honor_level_id”
        df_hl = self._normalize_honor_levels(df_honor_levels)
        # 将df_hl转换成字典：calc_id作为key，honor_level_id作为value
        calc_to_lv = self._build_calc_to_level_map(df_hl)
        # 取出calc_id对应的value
        lv70 = self._require_level_id(calc_to_lv, 70)
        lv80 = self._require_level_id(calc_to_lv, 80)
        lv90 = self._require_level_id(calc_to_lv, 90)
        # endregion

        # --------------------------------------------------------------
        # 1. 阶段一：PUSH 补录 + 当月写入记录表
        # --------------------------------------------------------------
        # region 生成df_hist、df_push -> 将calc_to_lv的key、value添加df_history_record、df_push_record中
        df_hist = self._prepare_record_df(
            df_history_record,
            user_id_dtype=user_id_dtype,
            calc_to_lv=calc_to_lv,
        )

        df_push = self._prepare_record_df(
            df_push_record,
            user_id_dtype=user_id_dtype,
            calc_to_lv=calc_to_lv,
        )
        # endregion

        # region 对补录list 做筛选：1、过去11个月 2、不包含本期 3、只筛选“准2星皇冠”以上
        # 设定时间上限和下限 大于>=当前周期-11 且 小于 当前周期-1 且 last_honor_calc_id>=80
        if len(df_push) > 0:
            mask_push = (
                    (df_push["period_num"] >= (iv_period_num - 11))
                    & (df_push["period_num"] <= (iv_period_num - 1))
                    & (df_push["last_honor_calc_id"] >= 80)
            )
            df_push = df_push[mask_push].copy().reset_index(drop=True)
        # endregion

        # region 创建df_curr -> copy df_last_honor并新增iv_period_num
        df_curr = self._prepare_current_honor_df(
            df_last_honor,
            user_id_dtype=user_id_dtype,
            calc_to_lv=calc_to_lv,
            iv_period_num=iv_period_num,
        )
        # endregion

        # region 创建df_rec_all -> 将df_hist、df_push、df_curr放到GPU中
        parts = []
        if len(df_hist) > 0:
            parts.append(df_hist)
        if len(df_push) > 0:
            parts.append(df_push)
        if len(df_curr) > 0:
            parts.append(df_curr)

        if parts:
            df_rec_all = cudf.concat(parts, ignore_index=True)
        else:
            df_rec_all = self._empty_record_df(user_id_dtype)
        # endregion

        # region 按 (user_id, period_num) 去重，防止脏数据
        if self.deduplicate_history and len(df_rec_all) > 0:
            LOG.warning(
                "deduplicate_history=True：将按 (user_id, period_num) 去重，"
                "这会偏离 SQL 原始计数语义，但可缓解重复执行导致的次数虚增。"
            )
            df_rec_all = (
                df_rec_all
                .sort_values(["user_id", "period_num", "last_honor_calc_id"], ascending=[True, True, False])
                .drop_duplicates(subset=["user_id", "period_num"], keep="first")
                .reset_index(drop=True)
            )
        # endregion

        # --------------------------------------------------------------
        # 2. 阶段一：初始化 HIGH 表（从 AR_USER 全量会员快照）
        # --------------------------------------------------------------
        # region 创建df_users，通过df_user_highestcopy
        df_users = df_user_highest[["user_id", "highest_honor_lv"]].copy().reset_index(drop=True)
        df_users["user_id"] = df_users["user_id"].astype(user_id_dtype)
        # endregion

        # region 通过user_id去重df_users
        if self.strict_sql_mode:
            self._assert_unique(df_users, ["user_id"], "df_user_highest.user_id")
        else:
            df_users = df_users.drop_duplicates(subset=["user_id"], keep="first").reset_index(drop=True)
        # endregion

        # region 创建lv_lookup
        lv_lookup = df_hl[["calc_id", "honor_level_id"]].rename(
            columns={"calc_id": "_ori_calc_id", "honor_level_id": "_ori_highest_honor_lv"}
        )
        # endregion

        # region 创建df_high -> df_users联查lv_lookup 找
        df_high = df_users.merge(
            lv_lookup,
            left_on="highest_honor_lv",
            right_on="_ori_highest_honor_lv",
            how="left",
        ).reset_index(drop=True)

        # region 新增ori_系列和cur_系列，ori_是期初静态快照，cur_是动态计算游标
        df_high["ori_highest_honor_calc_id"] = df_high["_ori_calc_id"].fillna(0).astype("int32")
        df_high["ori_highest_honor_lv"] = df_high["highest_honor_lv"]
        df_high["cur_calc_id"] = df_high["ori_highest_honor_calc_id"].astype("int32")
        df_high["cur_lv"] = df_high["ori_highest_honor_lv"]
        # endregion
        # endregion

        # region 数据验证
        # 输入中若存在未知奖衔 ID，不阻断执行，但在 strict 模式下记录警告
        if len(df_high) > 0:
            unknown_mask = df_high["highest_honor_lv"].notna() & df_high["_ori_calc_id"].isna()
            unknown_cnt = int(unknown_mask.sum())
            if unknown_cnt > 0:
                LOG.warning(
                    "df_user_highest 中有 %d 条 highest_honor_lv 无法映射到 calc_id，已按 0 处理。",
                    unknown_cnt,
                )

        df_high = df_high.drop(columns=["highest_honor_lv", "_ori_calc_id", "_ori_highest_honor_lv"]).reset_index(
            drop=True)
        # endregion

        # region 联查df_curr，讲当月结果（last_honor_calc_id、last_honor_lv）放入df_high中
        if len(df_curr) > 0:
            df_last_dedup = df_curr[["user_id", "last_honor_calc_id", "last_honor_lv"]].copy().reset_index(drop=True)
            # 这里 df_curr 已经完成唯一性校验 / 规范化
            df_high = df_high.merge(df_last_dedup, on="user_id", how="left").reset_index(drop=True)
        else:
            df_high["last_honor_calc_id"] = cudf.Series(cp.zeros(len(df_high), dtype=cp.int32), index=df_high.index)
            df_high["last_honor_lv"] = cudf.Series([None] * len(df_high), index=df_high.index)

        df_high["last_honor_calc_id"] = df_high["last_honor_calc_id"].fillna(0).astype("int32")
        # endregion

        # --------------------------------------------------------------
        # 3. 阶段二：10~70 直接取高，但单月上限封顶 70
        # --------------------------------------------------------------
        LOG.info("阶段二：70 级封顶判定")
        # region 取出当前等级（不含当月）和当月等级
        cur_calc = df_high["cur_calc_id"].astype("int32")
        last_calc = df_high["last_honor_calc_id"].astype("int32")
        # endregion

        # region 配置条件 为cur_calc_id赋值
        # 是否更新当前等级：当前等级<70 且 当月等级大于当前等级
        mask_trigger_70 = (cur_calc < 70) & (last_calc > cur_calc)
        # 计算当前等级：如果当月等级小于70 取当月 否则 取70
        next_calc_70 = cp.where(last_calc.values < 70, last_calc.values, cp.int32(70)).astype(cp.int32)
        df_high["cur_calc_id"] = cudf.Series(
            cp.where(mask_trigger_70.values, next_calc_70, cur_calc.values).astype(cp.int32),
            index=df_high.index,
        )
        # endregion

        # region 配置条件 为cur_lv赋值
        mask_use_last = mask_trigger_70 & (last_calc < 70)
        mask_use_70 = mask_trigger_70 & (last_calc >= 70)
        cur_lv = df_high["cur_lv"]
        # 满足升级条件且小于70级，取最新
        cur_lv = cur_lv.where(~mask_use_last, df_high["last_honor_lv"])
        # 满足升级条件且大于等级70级，取70
        # ~:python取反，当为false时，取参数里的值，为true保留原值
        cur_lv = cur_lv.where(~mask_use_70, lv70)
        df_high["cur_lv"] = cur_lv
        # endregion

        # --------------------------------------------------------------
        # 4. 阶段三：80 级 12 个月滚动判定（SQL: PERIOD_NUM >= current-11）
        # --------------------------------------------------------------
        LOG.info("阶段三：80 级滚动判定")
        # region 过滤出12个月之内 last_honor_calc_id>=80  按用户分组 统计last_honor_calc_id次数
        if len(df_rec_all) > 0:
            df_window = df_rec_all[df_rec_all["period_num"] >= (iv_period_num - 11)].copy().reset_index(drop=True)
            cnt_80 = (
                df_window[df_window["last_honor_calc_id"] >= 80]
                .groupby("user_id")
                .agg({"last_honor_calc_id": "count"})
                .reset_index()
                .rename(columns={"last_honor_calc_id": "c80"})
            )
        else:
            df_window = df_rec_all
            cnt_80 = cudf.DataFrame(
                {
                    "user_id": cudf.Series(dtype=user_id_dtype),
                    "c80": cudf.Series(dtype="int32"),
                }
            )
        # endregion

        # region df_high联查cnt_80，将统计出的“次数”新增到df_high中
        df_high = df_high.merge(cnt_80, on="user_id", how="left").reset_index(drop=True)
        c80 = df_high["c80"].fillna(0).astype("int32")
        # endregion

        # region 筛选出满足80级的数据
        cur_calc = df_high["cur_calc_id"].astype("int32")
        mask_80 = (cur_calc < 80) & (c80 >= 2)
        df_high["cur_calc_id"] = cudf.Series(
            cp.where(mask_80.values, cp.int32(80), cur_calc.values).astype(cp.int32),
            index=df_high.index,
        )
        df_high["cur_lv"] = df_high["cur_lv"].where(~mask_80, lv80)
        # endregion

        # --------------------------------------------------------------
        # 5. 阶段四：90 级 12 个月滚动判定（SQL: PERIOD_NUM >= current-11）
        # --------------------------------------------------------------
        LOG.info("阶段四：90 级滚动判定")
        # region 同理 筛选出满足90级的数据
        if len(df_window) > 0:
            cnt_90 = (
                df_window[df_window["last_honor_calc_id"] == 90]
                .groupby("user_id")
                .agg({"last_honor_calc_id": "count"})
                .reset_index()
                .rename(columns={"last_honor_calc_id": "c90"})
            )
        else:
            cnt_90 = cudf.DataFrame(
                {
                    "user_id": cudf.Series(dtype=user_id_dtype),
                    "c90": cudf.Series(dtype="int32"),
                }
            )

        df_high = df_high.merge(cnt_90, on="user_id", how="left").reset_index(drop=True)
        c90 = df_high["c90"].fillna(0).astype("int32")

        cur_calc = df_high["cur_calc_id"].astype("int32")
        mask_90 = (cur_calc < 90) & (c90 >= 3)
        df_high["cur_calc_id"] = cudf.Series(
            cp.where(mask_90.values, cp.int32(90), cur_calc.values).astype(cp.int32),
            index=df_high.index,
        )
        df_high["cur_lv"] = df_high["cur_lv"].where(~mask_90, lv90)
        # endregion

        # --------------------------------------------------------------
        # 6. 输出整理（对齐 AR_CALC_LV_HONOR_HIGH / RECORD）
        # --------------------------------------------------------------
        n = len(df_high)
        df_result = cudf.DataFrame(
            {
                "period_num": cudf.Series(cp.full(n, iv_period_num, dtype=cp.int32)),
                "user_id": df_high["user_id"],
                "ori_highest_honor_lv": df_high["ori_highest_honor_lv"],
                "ori_highest_honor_calc_id": df_high["ori_highest_honor_calc_id"].astype("int32"),
                "highest_honor_calc_id": df_high["cur_calc_id"].astype("int32"),
                "highest_honor_lv": df_high["cur_lv"],
            }
        ).reset_index(drop=True)

        df_rec_all = df_rec_all[self._record_cols()].reset_index(drop=True)

        elapsed = time.perf_counter() - t0
        LOG.info("最高奖衔计算完成，耗时 %.4fs，输出 high=%d，record=%d", elapsed, len(df_result), len(df_rec_all))
        return df_result, df_rec_all

    # ==================================================================
    # 输入校验
    # ==================================================================
    def _validate_entry_args(self, iv_period_num: int) -> None:
        if iv_period_num is None:
            raise ValueError("iv_period_num 不能为空")
        try:
            int(iv_period_num)
        except Exception as exc:  # pragma: no cover - 防御式校验
            raise ValueError("iv_period_num 必须可转换为整数") from exc

    def _validate_input_schemas(
            self,
            df_last_honor: Optional[cudf.DataFrame],
            df_history_record: Optional[cudf.DataFrame],
            df_push_record: Optional[cudf.DataFrame],
            df_user_highest: cudf.DataFrame,
            df_honor_levels: cudf.DataFrame,
    ) -> None:
        self._require_columns(df_user_highest, "df_user_highest", {"user_id", "highest_honor_lv"})
        self._require_columns(df_honor_levels, "df_honor_levels", {"calc_id"})

        if df_last_honor is not None:
            self._require_columns(df_last_honor, "df_last_honor", {"user_id", "last_honor_calc_id"})
        if df_history_record is not None:
            self._require_columns(df_history_record, "df_history_record",
                                  {"user_id", "period_num", "last_honor_calc_id"})
        if df_push_record is not None:
            self._require_columns(df_push_record, "df_push_record", {"user_id", "period_num", "last_honor_calc_id"})

    def _require_columns(self, df: cudf.DataFrame, name: str, required: Iterable[str]) -> None:
        missing = set(required) - set(df.columns)
        if missing:
            raise ValueError(f"{name} 缺少必需列: {sorted(missing)}")

    def _assert_unique(self, df: cudf.DataFrame, cols: Iterable[str], name: str) -> None:
        if len(df) == 0:
            return
        dup_any = df[list(cols)].duplicated().any()
        if bool(dup_any):
            raise ValueError(f"{name} 存在重复，违反唯一性约束。")

    def _resolve_user_id_dtype(self, *dfs: Optional[cudf.DataFrame]):
        for df in dfs:
            if df is not None and "user_id" in df.columns:
                return df["user_id"].dtype
        return "object"

    # ==================================================================
    # 维表规范化
    # ==================================================================
    def _normalize_honor_levels(self, df_honor_levels: cudf.DataFrame) -> cudf.DataFrame:
        df_hl = df_honor_levels.copy().reset_index(drop=True)

        if "calc_id" not in df_hl.columns:
            raise ValueError("df_honor_levels 缺少 calc_id 列")

        df_hl = df_hl[["calc_id", "honor_lv"]].copy().reset_index(drop=True)
        df_hl = df_hl.rename(columns={"honor_lv": "honor_level_id"})
        df_hl["calc_id"] = df_hl["calc_id"].fillna(0).astype("int32")

        return df_hl

    def _build_calc_to_level_map(self, df_hl: cudf.DataFrame) -> dict:
        return dict(
            zip(
                df_hl["calc_id"].to_arrow().to_pylist(),
                df_hl["honor_level_id"].to_arrow().to_pylist(),
            )
        )

    def _require_level_id(self, calc_to_lv: dict, calc_id: int):
        if calc_id not in calc_to_lv or calc_to_lv[calc_id] is None:
            raise ValueError(f"df_honor_levels 中缺少 calc_id={calc_id} 的奖衔映射，无法完成历史最高奖衔计算。")
        return calc_to_lv[calc_id]

    # ==================================================================
    # 记录表规范化
    # ==================================================================
    def _record_cols(self):
        return ["user_id", "period_num", "last_honor_lv", "last_honor_calc_id"]

    def _empty_record_df(self, user_id_dtype) -> cudf.DataFrame:
        return cudf.DataFrame(
            {
                "user_id": cudf.Series(dtype=user_id_dtype),
                "period_num": cudf.Series(dtype="int32"),
                "last_honor_lv": cudf.Series(dtype="object"),
                "last_honor_calc_id": cudf.Series(dtype="int32"),
            }
        )

    def _prepare_record_df(
            self,
            df: Optional[cudf.DataFrame],
            user_id_dtype,
            calc_to_lv: dict,
    ) -> cudf.DataFrame:
        if df is None or len(df) == 0:
            return self._empty_record_df(user_id_dtype)

        out = df.copy().reset_index(drop=True)
        out["user_id"] = out["user_id"].astype(user_id_dtype)
        out["period_num"] = out["period_num"].fillna(0).astype("int32")
        out["last_honor_calc_id"] = out["last_honor_calc_id"].fillna(0).astype("int32")

        if "last_honor_lv" not in out.columns:
            out["last_honor_lv"] = cudf.Series([None] * len(out), index=out.index)

        out = self._backfill_level_id(out, calc_col="last_honor_calc_id", lv_col="last_honor_lv", calc_to_lv=calc_to_lv)
        return out[self._record_cols()].reset_index(drop=True)

    def _prepare_current_honor_df(
            self,
            df_last_honor: Optional[cudf.DataFrame],
            user_id_dtype,
            calc_to_lv: dict,
            iv_period_num: int,
    ) -> cudf.DataFrame:
        if df_last_honor is None or len(df_last_honor) == 0:
            return self._empty_record_df(user_id_dtype)

        out = df_last_honor.copy().reset_index(drop=True)
        out["user_id"] = out["user_id"].astype(user_id_dtype)
        out["last_honor_calc_id"] = out["last_honor_calc_id"].fillna(0).astype("int32")

        if "last_honor_lv" not in out.columns:
            out["last_honor_lv"] = cudf.Series([None] * len(out), index=out.index)

        out = self._backfill_level_id(out, calc_col="last_honor_calc_id", lv_col="last_honor_lv", calc_to_lv=calc_to_lv)

        if self.strict_sql_mode:
            self._assert_unique(out, ["user_id"], "df_last_honor.user_id")
        else:
            out = (
                out.sort_values(["user_id", "last_honor_calc_id"], ascending=[True, False])
                .drop_duplicates(subset=["user_id"], keep="first")
                .reset_index(drop=True)
            )

        out["period_num"] = cudf.Series(cp.full(len(out), iv_period_num, dtype=cp.int32), index=out.index)
        return out[self._record_cols()].reset_index(drop=True)

    def _backfill_level_id(self, df: cudf.DataFrame, calc_col: str, lv_col: str, calc_to_lv: dict) -> cudf.DataFrame:
        if len(df) == 0:
            return df

        lu = cudf.DataFrame(
            {
                "_calc_key": cudf.Series(list(calc_to_lv.keys()), dtype="int32"),
                "_level_id": cudf.Series(list(calc_to_lv.values())),
            }
        )
        out = df.merge(lu, left_on=calc_col, right_on="_calc_key", how="left").reset_index(drop=True)

        if lv_col not in out.columns:
            out[lv_col] = out["_level_id"]
        else:
            fill_mask = self._is_missing_text(out[lv_col])
            out[lv_col] = out[lv_col].where(~fill_mask, out["_level_id"])

        return out.drop(columns=["_calc_key", "_level_id"], errors="ignore").reset_index(drop=True)

    def _is_missing_text(self, s: cudf.Series) -> cudf.Series:
        # 对字符串 / object 列，None 和空串都视为“缺失”
        try:
            return s.isna() | (s == "")
        except Exception:
            return s.isna()


def main():
    # ══════════════════════════════════════════════════════════════
    # 1. 奖衔维表 (AR_HONOR_LEVEL)
    #    必须包含 calc_id = 70, 80, 90
    # ══════════════════════════════════════════════════════════════
    df_honor_levels = cudf.DataFrame({
        "calc_id": [10, 20, 30, 40, 50, 60, 70, 80, 90],
        "honor_lv": ["L10", "L20", "L30", "L40", "L50", "L60", "L70", "L80", "L90"],
    })

    # ══════════════════════════════════════════════════════════════
    # 2. 用户最高奖衔快照 (AR_USER)
    # ══════════════════════════════════════════════════════════════
    df_user_highest = cudf.DataFrame({
        "user_id": ["U001", "U002", "U003", "U004", "U005"],
        "highest_honor_lv": ["L10", "L30", "L70", "L80", "L60"],
    })

    # ══════════════════════════════════════════════════════════════
    # 3. 当月奖衔结果 (AR_CALC_LV_HONOR)
    # ══════════════════════════════════════════════════════════════
    df_last_honor = cudf.DataFrame({
        "user_id": ["U001", "U002", "U003", "U004", "U005"],
        "last_honor_calc_id": [60, 80, 90, 90, 40],
        "last_honor_lv": ["L60", "L80", "L90", "L90", "L40"],
    })

    # ══════════════════════════════════════════════════════════════
    # 4. 历史记录 (AR_CALC_LV_HONOR_RECORD)
    #
    #    period_num 是连续递增的顺序编号（非 YYYYMM），
    #    与 SQL 存储过程中的 IV_PERIOD_NUM 语义一致。
    #
    #    当前周期 = 12，滚动窗口 = [12-11, 12] = [1, 12]
    # ══════════════════════════════════════════════════════════════
    iv_period_num = 12  # 当前周期（顺序编号）

    # U002: 历史 1 次 >=80 + 当月 1 次 = 2 次 → 触发 80 级
    # U003: 历史 2 次 =90  + 当月 1 次 = 3 次 → 触发 90 级
    # U004: 历史 2 次 =90  + 当月 1 次 = 3 次 → 触发 90 级
    df_history_record = cudf.DataFrame({
        "user_id": ["U002", "U003", "U003", "U004", "U004", "U001"],
        "period_num": [10, 9, 10, 8, 10, 11],
        "last_honor_calc_id": [80, 90, 90, 90, 90, 30],
        "last_honor_lv": ["L80", "L90", "L90", "L90", "L90", "L30"],
    })

    # ══════════════════════════════════════════════════════════════
    # 5. PUSH 补录记录（本例不使用）
    # ══════════════════════════════════════════════════════════════
    df_push_record = None

    # ══════════════════════════════════════════════════════════════
    # 6. 调用计算
    # ══════════════════════════════════════════════════════════════
    service = HonorLevelHighGPUService(strict_sql_mode=True, deduplicate_history=False)

    df_result, df_record_out = service.compute_highest_honor_gpu(
        iv_period_num=iv_period_num,
        df_last_honor=df_last_honor,
        df_history_record=df_history_record,
        df_push_record=df_push_record,
        df_user_highest=df_user_highest,
        df_honor_levels=df_honor_levels,
    )

    # ══════════════════════════════════════════════════════════════
    # 7. 查看结果
    # ══════════════════════════════════════════════════════════════
    print("=" * 70)
    print("df_result (AR_CALC_LV_HONOR_HIGH):")
    print("=" * 70)
    print(df_result.to_pandas().to_string(index=False))

    print()
    print("=" * 70)
    print("df_record_out (AR_CALC_LV_HONOR_RECORD):")
    print("=" * 70)
    print(df_record_out.to_pandas().to_string(index=False))

    print()
    print("=" * 70)
    print("预期结果说明：")
    print("=" * 70)
    print("""
    U001: 初始 L10(calc=10), 当月 60 → 60>10 且 <70 → 直升60       → highest = L60
    U002: 初始 L30(calc=30), 当月 80 → 先封顶70; 滚动2次>=80 → 升80 → highest = L80
    U003: 初始 L70(calc=70), 当月 90 → 滚动3次>=80→80, 3次=90→90   → highest = L90
    U004: 初始 L80(calc=80), 当月 90 → 滚动3次=90 → 升90            → highest = L90
    U005: 初始 L60(calc=60), 当月 40 → 40<60 不触发, 保持原值        → highest = L60
    """)


if __name__ == "__main__":
    main()
