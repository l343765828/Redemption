# -*- coding: utf-8 -*-
"""
Team Bonus (团队奖金 / TB) 结算 —— CALC_BE_TB 存储过程的 Python 忠实参考实现
=======================================================================

这是一个 **精确参考实现 (correctness oracle)**：
  * 全程使用 ``decimal.Decimal``，精确复刻 MySQL ``DECIMAL(16,2)/DECIMAL(16,6)``
    与 ``TRUNCATE(x, n)`` 的"向零截断"语义；
  * 完整复刻存储过程的 5 个阶段，包括其所有"怪癖"（中间表不清理、奖金池/有效基数
    的活跃口径不对称、阶段五结转的匹配/未匹配分支、22 位流水号格式等）；
  * 行级用 Decimal 逐行计算，保证可读、可断言、可逐位核对，是用来校验
    dask_cudf 分布式版本输出是否正确的"标准答案"。

输入为 pandas.DataFrame（与 MariaDB 表同名同列）：
  perf_month   : PERIOD_NUM, CALC_MONTH, USER_ID, TOTAL_1L, TOTAL_2L, PV_PCS, IS_ACTIVE
  user         : ID, MEMBER_LV, COUNTRY_ID
  member_level : ID, CALC_ID
  config       : CONFIG_NAME, VALUE, TYPE
  user_perf    : USER_ID, SURPLUS_1L, SURPLUS_2L, TOTAL_1L, TOTAL_2L

裁决原则：以存储过程 CALC_BE_TB 的实际执行为准（详见《需求与技术规范说明书》）。
"""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, getcontext
from datetime import datetime
from typing import Optional

import pandas as pd

from Common.BonusConfig import ConfigSnapshot

# DECIMAL(16,6) 的中间精度足够，留足余量防止链路上溢出有效位
getcontext().prec = 50

ZERO = Decimal("0")


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def D(x) -> Decimal:
    """把任意数值安全转成 Decimal（None/NaN -> None）。"""
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        # 先转 str 再进 Decimal，避免引入 float 的二进制误差
        if x != x:  # NaN
            return None
        return Decimal(str(x))
    return Decimal(str(x))


def truncate(value: Decimal, ndigits: int) -> Decimal:
    """复刻 MySQL TRUNCATE(value, ndigits)：向零截断（本场景数值非负，即向下取整）。"""
    quantum = Decimal(1).scaleb(-ndigits)          # 10^(-ndigits)
    return value.quantize(quantum, rounding=ROUND_DOWN)


def _null(v):
    """把 SQL NULL 的各种 pandas 表现（None / NaN / pd.NA）统一成 Python None。"""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


# 最终发奖表 AR_CALC_BONUS_TB 的 19 列，严格按 DDL / INSERT 顺序
BONUS_COLUMNS = [
    "ID", "PERIOD_NUM", "CALC_MONTH", "USER_ID",
    "TOTAL_1L", "TOTAL_2L", "SURPLUS_1L", "SURPLUS_2L", "TOUCH_PV",
    "LAST_MEMBER_LV", "LAST_MEMBER_CALC_ID", "TOUCH_RATE", "TOUCH_CAPPING",
    "ORI_TOUCH_BASE", "TOUCH_BASE", "TB_RATE", "BONUS_TB", "COUNTRY_ID", "IS_ACTIVE",
]

MID1_COLUMNS = [
    "PERIOD_NUM", "CALC_MONTH", "USER_ID", "TOTAL_1L", "TOTAL_2L",
    "SURPLUS_1L", "SURPLUS_2L", "TOUCH_PV", "TOUCH_RATE", "TOUCH_CAPPING",
    "LAST_MEMBER_LV", "LAST_MEMBER_CALC_ID", "COUNTRY_ID", "IS_ACTIVE", "PV_PCS",
]

MID2_COLUMNS = MID1_COLUMNS + ["ORI_TOUCH_BASE", "TOUCH_BASE"]

# 注意：COUNTRY_ID 与 PV_PCS 并非 SQL MID 表的原始列，而是 Python 内部为减少二次
# JOIN 而随行携带的"辅助列"——COUNTRY_ID 供阶段四发奖直接取用（等价于 SQL 在发奖时
# LEFT JOIN AR_USER），PV_PCS 不参与任何计算（阶段三 TOTAL_PV 实际取自快照表而非 MID1），
# 仅为可读性保留。若要与数据库中间表逐列对账，请用下面的 *_SQL_COLUMNS（mid?_df(sql_faithful=True)）。
#
# 列顺序对齐 SQL：与 AR_CALC_BONUS_TB 的 DDL 列序一致（该表由 MID2 直接 INSERT...SELECT 填充），
# 即 TOUCH_PV → LAST_MEMBER_LV → LAST_MEMBER_CALC_ID → TOUCH_RATE → TOUCH_CAPPING
# →(MID2 才有 ORI_TOUCH_BASE → TOUCH_BASE)→ IS_ACTIVE。
# （规范正文的字段说明表只是"描述顺序"，对账须以 DDL 实际列序为准。）
MID1_SQL_COLUMNS = [
    "PERIOD_NUM", "CALC_MONTH", "USER_ID", "TOTAL_1L", "TOTAL_2L",
    "SURPLUS_1L", "SURPLUS_2L", "TOUCH_PV",
    "LAST_MEMBER_LV", "LAST_MEMBER_CALC_ID", "TOUCH_RATE", "TOUCH_CAPPING",
    "IS_ACTIVE",
]

MID2_SQL_COLUMNS = [
    "PERIOD_NUM", "CALC_MONTH", "USER_ID", "TOTAL_1L", "TOTAL_2L",
    "SURPLUS_1L", "SURPLUS_2L", "TOUCH_PV",
    "LAST_MEMBER_LV", "LAST_MEMBER_CALC_ID", "TOUCH_RATE", "TOUCH_CAPPING",
    "ORI_TOUCH_BASE", "TOUCH_BASE", "IS_ACTIVE",
]


class TeamBonusCalculator:
    """CALC_BE_TB 的忠实复刻。

    重要：MID1 / MID2 / BONUS 在存储过程里是 **只 INSERT、过程内不清理** 的表。
    因此本类把它们建模为"跨次累积"的内部账本（self._mid1 / self._mid2 / self._bonus）。
    - 正常结算：调用方必须先 ``cleanup_mid_tables()``（对应"执行前全量清空"），
      此时账本只含本次数据，行为与单次 SQL 一致；
    - 若 **不清理** 连续重跑：账本累积，可复刻 TC-14 的级联放大事故。
    """

    def __init__(self, perf_month, user, member_level, config, user_perf):
        self.perf_month = perf_month.copy().reset_index(drop=True)
        self.user = user.copy().reset_index(drop=True)
        self.member_level = member_level.copy().reset_index(drop=True)
        # snapshot 仅作为受控 fixture 适配；本模块仍是 SQL oracle，不接生产链路。
        if isinstance(config, ConfigSnapshot):
            config = config.to_pandas(uppercase_columns=True)
        self.config = config.copy().reset_index(drop=True)
        # user_perf 会被原地结转刷新，保留为可写状态
        self.user_perf = user_perf.copy().reset_index(drop=True)

        # 中间表 / 发奖表账本（跨次累积，模拟 INSERT 无清理）
        self._mid1: list[dict] = []
        self._mid2: list[dict] = []
        self._bonus: list[dict] = []

        # 预解析等级 -> CALC_ID 映射（LEFT JOIN AR_MEMBER_LEVEL ON ID = MEMBER_LV）
        self._lvl_to_calc = {
            str(r["ID"]): r["CALC_ID"] for _, r in self.member_level.iterrows()
        }
        # 预解析会员 -> (MEMBER_LV, COUNTRY_ID)
        # 用 _null() 把 pandas 缺失值（NaN/pd.NA）归一成 Python None，
        # 以对齐 SQL 中的 NULL 语义（否则 TC-17 的 COUNTRY_ID 占位会变成 'nan'）。
        self._user_idx = {
            str(r["ID"]): (_null(r.get("MEMBER_LV")), _null(r.get("COUNTRY_ID")))
            for _, r in self.user.iterrows()
        }

    # ------------------------------------------------------------------ #
    # 阶段零：配置解析（全部要求 TYPE='bonus'）
    # ------------------------------------------------------------------ #
    def _bonus_cfg(self) -> pd.DataFrame:
        return self.config[self.config["TYPE"] == "bonus"]

    def bisect_rate(self) -> Decimal:
        """teamBisectRate: IFNULL(MIN(VALUE), 0) / 100。缺失 -> 0。"""
        cfg = self._bonus_cfg()
        rows = cfg[cfg["CONFIG_NAME"] == "teamBisectRate"]["VALUE"]
        vals = [D(v) for v in rows if D(v) is not None]
        if not vals:
            return ZERO
        return min(vals) / Decimal(100)

    def _cfg_values(self, name: str) -> list:
        """TYPE='bonus' 下 CONFIG_NAME=name 的全部命中 VALUE（保留多行，对齐 SQL LEFT JOIN）。

        teamTouchRate/teamTouchCapping 在 SQL 中是 LEFT JOIN + IFNULL(VALUE, 0)：
        命中行即使 VALUE 为 NULL 也会保留并取 0，而非被丢弃。因此这里把 NULL 归一成 0
        （影响脏配置扇出时的行数；正常 NOT NULL 配置下行为不变）。
        """
        cfg = self._bonus_cfg()
        rows = cfg[cfg["CONFIG_NAME"] == name]["VALUE"]
        return [(ZERO if D(v) is None else D(v)) for v in rows]

    def _touch_rate_values(self, calc_id) -> list:
        """teamTouchRate{CALC_ID} 全部命中值 / 100（空列表 = 等级未命中或缺配置）。"""
        if calc_id is None or (isinstance(calc_id, float) and calc_id != calc_id):
            return []
        return [v / Decimal(100) for v in self._cfg_values(f"teamTouchRate{int(calc_id)}")]

    def _touch_capping_values(self, calc_id) -> list:
        """teamTouchCapping{CALC_ID} 全部命中值（不除 100；空列表 = 缺配置）。"""
        if calc_id is None or (isinstance(calc_id, float) and calc_id != calc_id):
            return []
        return self._cfg_values(f"teamTouchCapping{int(calc_id)}")

    def touch_rate(self, calc_id) -> Decimal:
        """teamTouchRate{CALC_ID}: IFNULL(VALUE, 0) / 100。等级未命中/缺配置 -> 0。

        SQL 对该项是直接 LEFT JOIN（无聚合）：同名多行会让 MID1 扇出。
        strict_config=True（默认）时此处直接报错，避免静默吞掉重复配置；
        strict_config=False 时由阶段一按笛卡尔扇出忠实复刻 SQL 行为。
        """
        vals = self._touch_rate_values(calc_id)
        if len(vals) > 1 and getattr(self, "_strict_config", True):
            raise ValueError(
                f"AR_CONFIG 重复：teamTouchRate{int(calc_id)}(TYPE='bonus') 命中 {len(vals)} 行。"
                " 配置表应保证 (CONFIG_NAME,TYPE) 唯一；如需复刻 SQL 脏配置扇出请用 strict_config=False。")
        return vals[0] if vals else ZERO

    def touch_capping(self, calc_id) -> Decimal:
        """teamTouchCapping{CALC_ID}: IFNULL(VALUE, 0)。不除 100；0 = 不封顶。

        同 touch_rate：SQL 为直接 LEFT JOIN，strict_config 控制重复配置是报错还是扇出。
        """
        vals = self._touch_capping_values(calc_id)
        if len(vals) > 1 and getattr(self, "_strict_config", True):
            raise ValueError(
                f"AR_CONFIG 重复：teamTouchCapping{int(calc_id)}(TYPE='bonus') 命中 {len(vals)} 行。"
                " 配置表应保证 (CONFIG_NAME,TYPE) 唯一；如需复刻 SQL 脏配置扇出请用 strict_config=False。")
        return vals[0] if vals else ZERO

    # ------------------------------------------------------------------ #
    # 阶段一：生成会员对碰基础信息 -> MID1（含活跃与不活跃，按 PERIOD 过滤）
    # ------------------------------------------------------------------ #
    def _stage1_build_mid1(self, iv_period_num: int) -> int:
        snap = self.perf_month[self.perf_month["PERIOD_NUM"] == iv_period_num]
        inserted = 0
        for _, row in snap.iterrows():
            uid = str(row["USER_ID"])
            t1l = D(row["TOTAL_1L"]) or ZERO
            t2l = D(row["TOTAL_2L"]) or ZERO

            # 会员 / 等级 LEFT JOIN
            member_lv, country_id = self._user_idx.get(uid, (None, None))
            calc_id = self._lvl_to_calc.get(str(member_lv)) if member_lv is not None else None

            surplus_1l = (t1l - t2l) if (t1l - t2l) >= 0 else ZERO   # MAX(1L-2L,0)
            surplus_2l = (t2l - t1l) if (t2l - t1l) > 0 else ZERO    # MAX(2L-1L,0)
            touch_pv = t2l if (t1l - t2l) >= 0 else t1l              # MIN(1L,2L)

            # TOUCH_RATE / TOUCH_CAPPING 在 SQL 中是两次直接 LEFT JOIN AR_CONFIG。
            # strict（默认）：每行唯一命中（touch_rate/touch_capping 内部会对重复配置报错）。
            # 非 strict：忠实复刻双表 LEFT JOIN 的笛卡尔扇出（任一侧多行 -> MID1 多行）。
            if getattr(self, "_strict_config", True):
                rate_cap_pairs = [(self.touch_rate(calc_id), self.touch_capping(calc_id))]
            else:
                rates = self._touch_rate_values(calc_id) or [ZERO]
                caps = self._touch_capping_values(calc_id) or [ZERO]
                rate_cap_pairs = [(rt, cp) for rt in rates for cp in caps]

            for touch_rate_v, touch_capping_v in rate_cap_pairs:
                self._mid1.append({
                    "PERIOD_NUM": int(row["PERIOD_NUM"]),
                    "CALC_MONTH": int(row["CALC_MONTH"]),       # 来源：快照表，而非入参
                    "USER_ID": uid,
                    "TOTAL_1L": t1l,
                    "TOTAL_2L": t2l,
                    "SURPLUS_1L": surplus_1l,
                    "SURPLUS_2L": surplus_2l,
                    "TOUCH_PV": touch_pv,
                    "TOUCH_RATE": touch_rate_v,
                    "TOUCH_CAPPING": touch_capping_v,
                    "LAST_MEMBER_LV": member_lv,
                    "LAST_MEMBER_CALC_ID": calc_id,
                    "COUNTRY_ID": country_id,
                    "IS_ACTIVE": int(row["IS_ACTIVE"]),
                    "PV_PCS": D(row["PV_PCS"]) or ZERO,
                })
                inserted += 1
        return inserted

    # ------------------------------------------------------------------ #
    # 阶段二：生成对碰计奖基数 -> MID2（读全量 MID1，WHERE TOUCH_PV>0，不区分活跃）
    # ------------------------------------------------------------------ #
    def _stage2_build_mid2(self) -> int:
        inserted = 0
        for r in self._mid1:                       # 全量 MID1，无周期过滤
            if r["TOUCH_PV"] > 0:
                ori = r["TOUCH_PV"] * r["TOUCH_RATE"]
                cap = r["TOUCH_CAPPING"]
                # 封顶三段判定
                if cap == 0:
                    touch_base = ori                 # 不封顶
                elif cap <= ori:
                    touch_base = cap                 # 触发封顶
                else:
                    touch_base = ori                 # 未达封顶
                row = dict(r)
                row["ORI_TOUCH_BASE"] = ori
                row["TOUCH_BASE"] = touch_base
                self._mid2.append(row)
                inserted += 1
        return inserted

    # ------------------------------------------------------------------ #
    # 阶段三：全盘奖金池与加权比例 TB_RATE
    # ------------------------------------------------------------------ #
    def _stage3_reduce(self, iv_period_num: int):
        # TOTAL_PV：来自快照表（按 PERIOD 过滤），不校验活跃
        snap = self.perf_month[self.perf_month["PERIOD_NUM"] == iv_period_num]
        total_pv = sum((D(v) or ZERO) for v in snap["PV_PCS"]) if len(snap) else ZERO

        # TOTAL_BASE：来自全量 MID2，仅活跃，无周期过滤
        total_base = sum(r["TOUCH_BASE"] for r in self._mid2 if r["IS_ACTIVE"] == 1)
        total_base = total_base if total_base else ZERO

        bisect = self.bisect_rate()
        total_tb = total_pv * bisect

        if total_base == 0:
            tb_rate = ZERO                                   # 除零保护
        else:
            tb_rate = truncate(total_tb / total_base, 6)     # 6 位向下截断

        return {
            "TOTAL_PV": total_pv,
            "TOTAL_BASE": total_base,
            "TB_BISECT_RATE": bisect,
            "TOTAL_TB": total_tb,
            "TB_RATE": tb_rate,
        }

    # ------------------------------------------------------------------ #
    # 阶段四：生成个人团队奖 -> AR_CALC_BONUS_TB
    #   仅当 TB_RATE>0；逐行条件 TOUCH_BASE>0 且 IS_ACTIVE=1（读全量 MID2）
    # ------------------------------------------------------------------ #
    def _stage4_bonus(self, tb_rate: Decimal, now: datetime) -> int:
        if tb_rate <= 0:
            return 0
        time_str = now.strftime("%Y%m%d%H%M%S")        # 14 位
        rownum = 0
        inserted = 0
        for r in self._mid2:                            # 全量 MID2，无周期过滤
            if r["TOUCH_BASE"] > 0 and r["IS_ACTIVE"] == 1:
                rownum += 1                             # @ROWNUM 从 1 起
                bonus_tb = truncate(r["TOUCH_BASE"] * tb_rate, 2)   # 2 位向下截断
                country = "-1" if r["COUNTRY_ID"] is None else str(r["COUNTRY_ID"])
                self._bonus.append({
                    "ID": time_str + str(rownum).zfill(8),          # 22 位流水号
                    "PERIOD_NUM": r["PERIOD_NUM"],
                    "CALC_MONTH": r["CALC_MONTH"],
                    "USER_ID": r["USER_ID"],
                    "TOTAL_1L": r["TOTAL_1L"],
                    "TOTAL_2L": r["TOTAL_2L"],
                    "SURPLUS_1L": r["SURPLUS_1L"],
                    "SURPLUS_2L": r["SURPLUS_2L"],
                    "TOUCH_PV": r["TOUCH_PV"],
                    "LAST_MEMBER_LV": r["LAST_MEMBER_LV"],
                    "LAST_MEMBER_CALC_ID": r["LAST_MEMBER_CALC_ID"],
                    "TOUCH_RATE": r["TOUCH_RATE"],
                    "TOUCH_CAPPING": r["TOUCH_CAPPING"],
                    "ORI_TOUCH_BASE": r["ORI_TOUCH_BASE"],
                    "TOUCH_BASE": r["TOUCH_BASE"],
                    "TB_RATE": tb_rate,
                    "BONUS_TB": bonus_tb,
                    "COUNTRY_ID": country,
                    "IS_ACTIVE": 1,                                  # 受发奖条件约束，恒为 1
                })
                inserted += 1
        return inserted

    # ------------------------------------------------------------------ #
    # 阶段五：业绩结转刷新 AR_USER_PERF（LEFT JOIN 全量 MID1 ON USER_ID）
    # ------------------------------------------------------------------ #
    def _stage5_rollover(self):
        # 存储过程对 AR_USER_PERF 是多表 UPDATE ... LEFT JOIN MID1 ON USER_ID。
        # 当 MID1 内同一 USER_ID 出现多行（上游脏数据），目标行匹配多条来源、结果不可控（规范 4.3）。
        #   strict_unique_user=True（默认）：发现 MID1 重复 USER_ID 直接报错（生产应保证唯一）；
        #   strict_unique_user=False：保留"取最后一条"的确定化近似（SQL 实为不确定），
        #                             仅用于 TC-14/TC-15 这类脏数据穿透测试。
        seen, dup = set(), set()
        for r in self._mid1:
            if r["USER_ID"] in seen:
                dup.add(r["USER_ID"])
            seen.add(r["USER_ID"])
        if dup and getattr(self, "_strict_unique_user", True):
            raise ValueError(
                f"MID1 存在重复 USER_ID {sorted(dup)}：上游须保证 PERIOD_NUM+USER_ID 唯一（规范 4.3）。"
                " 如需复刻 SQL 的不确定结转请用 strict_unique_user=False。")

        mid1_by_user: dict[str, dict] = {}
        for r in self._mid1:
            mid1_by_user[r["USER_ID"]] = r          # 非 strict：取最后一条（确定化近似）

        for idx, row in self.user_perf.iterrows():
            uid = str(row["USER_ID"])
            src = mid1_by_user.get(uid)
            if src is None:
                # 未匹配（僵尸用户）：SURPLUS 保持不变；TOTAL = 原 SURPLUS
                self.user_perf.at[idx, "TOTAL_1L"] = D(row["SURPLUS_1L"])
                self.user_perf.at[idx, "TOTAL_2L"] = D(row["SURPLUS_2L"])
                # SURPLUS_1L / SURPLUS_2L 自赋值，无需改动
            else:
                # 匹配：四字段同步本期最新状态
                self.user_perf.at[idx, "SURPLUS_1L"] = src["SURPLUS_1L"]
                self.user_perf.at[idx, "SURPLUS_2L"] = src["SURPLUS_2L"]
                self.user_perf.at[idx, "TOTAL_1L"] = src["TOTAL_1L"]
                self.user_perf.at[idx, "TOTAL_2L"] = src["TOTAL_2L"]

    # ------------------------------------------------------------------ #
    # 编排
    # ------------------------------------------------------------------ #
    def run(self, iv_period_num: int, iv_calc_month: Optional[int] = None,
            now: Optional[datetime] = None, *,
            strict_config: bool = True, strict_unique_user: bool = True) -> dict:
        """执行一次完整结算。返回行数与全盘量汇总（便于测试断言）。

        iv_calc_month 仅为接口兼容，**不参与主体逻辑**（与 SQL 一致）。
        now 可注入固定时间，便于 ID 断言与并发隔离测试。

        strict_config（默认 True）：AR_CONFIG 中 teamTouchRate{N}/teamTouchCapping{N}
            同名多行直接报错（生产应保证配置唯一）；False 则按 SQL LEFT JOIN 笛卡尔扇出。
        strict_unique_user（默认 True）：MID1 内重复 USER_ID 在阶段五结转时直接报错；
            False 则保留"取最后一条"的确定化近似（用于 TC-14/TC-15 脏数据穿透）。
        """
        self._strict_config = strict_config
        self._strict_unique_user = strict_unique_user
        if now is None:
            now = datetime.now()

        n_mid1 = self._stage1_build_mid1(iv_period_num)
        n_mid2 = self._stage2_build_mid2()
        agg = self._stage3_reduce(iv_period_num)
        n_bonus = self._stage4_bonus(agg["TB_RATE"], now)
        self._stage5_rollover()

        return {
            "mid1_inserted": n_mid1,
            "mid2_inserted": n_mid2,
            "bonus_inserted": n_bonus,
            "mid1_total_rows": len(self._mid1),
            "mid2_total_rows": len(self._mid2),
            "bonus_total_rows": len(self._bonus),
            **agg,
        }

    # ------------------------------------------------------------------ #
    # 账本视图 / 清理（对应 SQL 的表）
    # ------------------------------------------------------------------ #
    def cleanup_mid_tables(self):
        """对应"执行前全量清空 MID1/MID2"。"""
        self._mid1.clear()
        self._mid2.clear()

    def cleanup_bonus(self):
        """对应重算前清理发奖表（SQL 本身无幂等，需外部保证）。"""
        self._bonus.clear()

    def cleanup_all(self):
        """对应"执行前全量清空 MID1/MID2/AR_CALC_BONUS_TB"——推荐的常规前置入口。

        测试用例总前置要求三表全清；除非刻意验证不清理的累积行为（如 TC-14），
        否则常规结算前都应调用本方法，避免在同一实例重算时漏清奖金表。
        """
        self.cleanup_mid_tables()
        self.cleanup_bonus()

    def mid1_df(self, sql_faithful: bool = False) -> pd.DataFrame:
        """MID1 视图。sql_faithful=True 时仅返回 SQL MID1 的原始列（剔除内部辅助列）。"""
        cols = MID1_SQL_COLUMNS if sql_faithful else MID1_COLUMNS
        return pd.DataFrame(self._mid1, columns=cols)

    def mid2_df(self, sql_faithful: bool = False) -> pd.DataFrame:
        """MID2 视图。sql_faithful=True 时仅返回 SQL MID2 的原始列（剔除内部辅助列）。"""
        cols = MID2_SQL_COLUMNS if sql_faithful else MID2_COLUMNS
        return pd.DataFrame(self._mid2, columns=cols)

    def bonus_df(self) -> pd.DataFrame:
        return pd.DataFrame(self._bonus, columns=BONUS_COLUMNS)
