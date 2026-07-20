# -*- coding: utf-8 -*-
"""
TC-01 ~ TC-18 自动化验证：用《团队奖金TB结算测试用例_终极落版.md》的断言
逐条校验 team_bonus_tb.TeamBonusCalculator 的输出。

运行：python3 test_team_bonus_tb.py
"""
from datetime import datetime
from decimal import Decimal

import pandas as pd

from team_bonus_tb import TeamBonusCalculator, D

PERIOD = 202506
FIX_NOW = datetime(2026, 6, 23, 15, 30, 45)

# 累计每个用例的通过情况
_results = []


def Dn(x):  # 简写
    return Decimal(str(x))


# --------------------------------------------------------------------------- #
# 造数工具
# --------------------------------------------------------------------------- #
def build(users, perf, configs, user_perf=None, member_levels=None):
    """
    users:   list of (user_id, calc_id_or_None, country_id)  —— calc_id 即等级映射后的 CALC_ID
    perf:    list of (user_id, t1l, t2l, pv, active[, period[, calc_month]])
    configs: dict, 形如 {"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping3": 1500, ...}
             value 可为 (val, type) 元组以指定 TYPE；否则默认 TYPE='bonus'
             同名多行用 list： {"teamBisectRate": [24, 10]}
    user_perf: list of (user_id, s1l, s2l, t1l, t2l)
    member_levels: 可选，覆盖默认等级表
    """
    # 用户表 + 等级表：calc_id=N -> 等级 ID=f"L{N}"，member_level(L{N})=N
    user_rows, lvl_rows, seen_lvl = [], [], set()
    for uid, calc_id, country in users:
        lv = None if calc_id is None else f"L{calc_id}"
        user_rows.append({"ID": uid, "MEMBER_LV": lv, "COUNTRY_ID": country})
        if calc_id is not None and lv not in seen_lvl:
            lvl_rows.append({"ID": lv, "CALC_ID": calc_id})
            seen_lvl.add(lv)
    if member_levels is not None:
        lvl_rows = member_levels
    user_df = pd.DataFrame(user_rows, columns=["ID", "MEMBER_LV", "COUNTRY_ID"])
    lvl_df = pd.DataFrame(lvl_rows, columns=["ID", "CALC_ID"])

    # 业绩快照
    perf_rows = []
    for rec in perf:
        uid, t1l, t2l, pv, active = rec[0], rec[1], rec[2], rec[3], rec[4]
        period = rec[5] if len(rec) > 5 else PERIOD
        cmonth = rec[6] if len(rec) > 6 else 6
        perf_rows.append({
            "PERIOD_NUM": period, "CALC_MONTH": cmonth, "USER_ID": uid,
            "TOTAL_1L": Dn(t1l), "TOTAL_2L": Dn(t2l), "PV_PCS": Dn(pv),
            "IS_ACTIVE": active,
        })
    perf_df = pd.DataFrame(perf_rows, columns=[
        "PERIOD_NUM", "CALC_MONTH", "USER_ID", "TOTAL_1L", "TOTAL_2L", "PV_PCS", "IS_ACTIVE"])

    # 配置表
    cfg_rows = []
    for name, val in configs.items():
        items = val if isinstance(val, list) else [val]
        for it in items:
            if isinstance(it, tuple):
                v, t = it
            else:
                v, t = it, "bonus"
            cfg_rows.append({"CONFIG_NAME": name, "VALUE": Dn(v), "TYPE": t})
    cfg_df = pd.DataFrame(cfg_rows, columns=["CONFIG_NAME", "VALUE", "TYPE"])

    # 业绩主表
    up_rows = []
    for rec in (user_perf or []):
        uid, s1, s2, t1, t2 = rec
        up_rows.append({"USER_ID": uid, "SURPLUS_1L": Dn(s1), "SURPLUS_2L": Dn(s2),
                        "TOTAL_1L": Dn(t1), "TOTAL_2L": Dn(t2)})
    up_df = pd.DataFrame(up_rows, columns=["USER_ID", "SURPLUS_1L", "SURPLUS_2L", "TOTAL_1L", "TOTAL_2L"])

    return TeamBonusCalculator(perf_df, user_df, lvl_df, cfg_df, up_df)


def bonus_of(calc, user_id):
    """取某 user 的所有 BONUS_TB（Decimal 列表）。"""
    df = calc.bonus_df()
    return [r["BONUS_TB"] for _, r in df.iterrows() if r["USER_ID"] == user_id]


def check(name, cond, detail=""):
    _results.append((name, cond, detail))
    flag = "PASS" if cond else "FAIL"
    print(f"  [{flag}] {name}" + (f"  -> {detail}" if (detail and not cond) else ""))
    return cond


def assert_counts(s, mid1, mid2, bonus):
    """显式断言本次 INSERT 影响的三表行数（规范要求每条用例都断言）。"""
    got = (s["mid1_inserted"], s["mid2_inserted"], s["bonus_inserted"])
    check(f"行数 MID1={mid1} / MID2={mid2} / BONUS={bonus}", got == (mid1, mid2, bonus), got)


def perf_row(calc, user_id):
    """取阶段五结转后 AR_USER_PERF 某用户的一行（dict）。"""
    df = calc.user_perf
    row = df[df["USER_ID"] == user_id].iloc[0]
    return {k: row[k] for k in ("SURPLUS_1L", "SURPLUS_2L", "TOTAL_1L", "TOTAL_2L")}


# --------------------------------------------------------------------------- #
# 第一部分：核心业务规则与对碰链路
# --------------------------------------------------------------------------- #
def tc01():
    print("TC-01 标准对碰（左>右）")
    c = build(users=[("A", 1, "MY")],
              perf=[("A", 1000, 600, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_mid_tables()
    s = c.run(PERIOD, now=FIX_NOW)
    m1 = c.mid1_df().iloc[0]
    check("行数 MID1/MID2/BONUS=1/1/1", (s["mid1_inserted"], s["mid2_inserted"], s["bonus_inserted"]) == (1, 1, 1))
    check("TOUCH_PV=600", m1["TOUCH_PV"] == 600)
    check("SURPLUS_1L=400 / SURPLUS_2L=0", m1["SURPLUS_1L"] == 400 and m1["SURPLUS_2L"] == 0)
    check("TOUCH_BASE=60", c.mid2_df().iloc[0]["TOUCH_BASE"] == 60)
    check("TOTAL_PV=100 / TOTAL_TB=24 / TB_RATE=0.4",
          s["TOTAL_PV"] == 100 and s["TOTAL_TB"] == 24 and s["TB_RATE"] == Dn("0.4"))
    check("A.BONUS_TB=24.00", bonus_of(c, "A") == [Dn("24.00")], bonus_of(c, "A"))


def tc02():
    print("TC-02 完美对碰（左=右）")
    c = build(users=[("B", 2, "MY")],
              perf=[("B", 500, 500, 200, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate2": 15, "teamTouchCapping2": 0})
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    m1 = c.mid1_df().iloc[0]
    assert_counts(s, 1, 1, 1)
    check("TOUCH_PV=500 / SURPLUS 双 0", m1["TOUCH_PV"] == 500 and m1["SURPLUS_1L"] == 0 and m1["SURPLUS_2L"] == 0)
    check("TOUCH_BASE=75", c.mid2_df().iloc[0]["TOUCH_BASE"] == 75)
    check("TOTAL_TB=48 / TB_RATE=0.64", s["TOTAL_TB"] == 48 and s["TB_RATE"] == Dn("0.64"))
    check("B.BONUS_TB=48.00", bonus_of(c, "B") == [Dn("48.00")], bonus_of(c, "B"))


def tc03():
    print("TC-03 标准对碰（右>左）")
    c = build(users=[("C", 1, "MY")],
              perf=[("C", 300, 800, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    m1 = c.mid1_df().iloc[0]
    assert_counts(s, 1, 1, 1)
    check("TOUCH_PV=300 / SURPLUS_2L=500", m1["TOUCH_PV"] == 300 and m1["SURPLUS_1L"] == 0 and m1["SURPLUS_2L"] == 500)
    check("TOUCH_BASE=30 / TB_RATE=0.8", c.mid2_df().iloc[0]["TOUCH_BASE"] == 30 and s["TB_RATE"] == Dn("0.8"))
    check("C.BONUS_TB=24.00", bonus_of(c, "C") == [Dn("24.00")], bonus_of(c, "C"))


def tc04():
    print("TC-04 封顶触发（超限）")
    c = build(users=[("D", 3, "MY")],
              perf=[("D", 20000, 10000, 1000, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate3": 20, "teamTouchCapping3": 1500})
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    m2 = c.mid2_df().iloc[0]
    assert_counts(s, 1, 1, 1)
    check("TOUCH_PV=10000 / ORI=2000 / TOUCH_BASE=1500",
          m2["TOUCH_PV"] == 10000 and m2["ORI_TOUCH_BASE"] == 2000 and m2["TOUCH_BASE"] == 1500)
    check("TB_RATE=0.16", s["TB_RATE"] == Dn("0.16"))
    check("D.BONUS_TB=240.00", bonus_of(c, "D") == [Dn("240.00")], bonus_of(c, "D"))


def tc05():
    print("TC-05 封顶边界（等于）")
    c = build(users=[("E", 3, "MY")],
              perf=[("E", 10000, 7500, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate3": 20, "teamTouchCapping3": 1500})
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    m2 = c.mid2_df().iloc[0]
    assert_counts(s, 1, 1, 1)
    check("ORI=1500 命中<= -> TOUCH_BASE=1500", m2["ORI_TOUCH_BASE"] == 1500 and m2["TOUCH_BASE"] == 1500)
    check("TB_RATE=0.016", s["TB_RATE"] == Dn("0.016"))
    check("E.BONUS_TB=24.00", bonus_of(c, "E") == [Dn("24.00")], bonus_of(c, "E"))


def tc06a():
    print("TC-06A 不活跃物理隔离")
    c = build(users=[("F", 1, "MY"), ("G", 1, "MY")],
              perf=[("F", 1000, 1000, 100, 0), ("G", 1000, 1000, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_mid_tables(); s = c.run(PERIOD, now=FIX_NOW)
    check("行数 MID1=2 / MID2=2 / BONUS=1",
          (s["mid1_inserted"], s["mid2_inserted"], s["bonus_inserted"]) == (2, 2, 1))
    check("TOTAL_PV=200 / TOTAL_BASE=100(仅活跃) / TB_RATE=0.48",
          s["TOTAL_PV"] == 200 and s["TOTAL_BASE"] == 100 and s["TB_RATE"] == Dn("0.48"))
    check("G.BONUS_TB=48.00 / F 无发奖", bonus_of(c, "G") == [Dn("48.00")] and bonus_of(c, "F") == [])


def tc06b():
    print("TC-06B 活跃单边（无对碰）贡献池")
    c = build(users=[("H", 1, "MY"), ("G", 1, "MY")],
              perf=[("H", 1000, 0, 100, 1), ("G", 1000, 1000, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_mid_tables(); s = c.run(PERIOD, now=FIX_NOW)
    check("行数 MID1=2 / MID2=1(仅G) / BONUS=1",
          (s["mid1_inserted"], s["mid2_inserted"], s["bonus_inserted"]) == (2, 1, 1))
    check("TOTAL_PV=200(含H) / TOTAL_BASE=100 / TB_RATE=0.48",
          s["TOTAL_PV"] == 200 and s["TOTAL_BASE"] == 100 and s["TB_RATE"] == Dn("0.48"))
    check("G.BONUS_TB=48.00（对照无H则24）", bonus_of(c, "G") == [Dn("48.00")], bonus_of(c, "G"))


# --------------------------------------------------------------------------- #
# 第二部分：配置异常与降级防御
# --------------------------------------------------------------------------- #
def tc07a():
    print("TC-07A 缺失拨出率配置")
    c = build(users=[("U", 1, "MY")],
              perf=[("U", 1000, 1000, 100, 1)],
              configs={"teamTouchRate1": 10, "teamTouchCapping1": 0},  # 无 teamBisectRate
              user_perf=[("U", 999, 888, 777, 666)])  # 前置旧值，验证 TB_RATE=0 时阶段五仍结转
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    check("bisect=0 -> TOTAL_TB=0 -> TB_RATE=0", s["TOTAL_TB"] == 0 and s["TB_RATE"] == 0)
    assert_counts(s, 1, 1, 0)
    p = perf_row(c, "U")  # 即便不发奖，AR_USER_PERF 仍被 MID1 覆写
    check("阶段五仍结转：U 四字段=0/0/1000/1000",
          (p["SURPLUS_1L"], p["SURPLUS_2L"], p["TOTAL_1L"], p["TOTAL_2L"]) == (0, 0, 1000, 1000), p)


def tc07b():
    print("TC-07B 配置 TYPE 脏数据过滤")
    c = build(users=[("U", 1, "MY")],
              perf=[("U", 1000, 1000, 100, 1)],
              configs={"teamBisectRate": (24, "system"), "teamTouchRate1": 10, "teamTouchCapping1": 0},
              user_perf=[("U", 5, 5, 5, 5)])
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    check("TYPE!='bonus' 被过滤 -> TB_RATE=0", s["TB_RATE"] == 0)
    assert_counts(s, 1, 1, 0)
    p = perf_row(c, "U")
    check("阶段五仍结转：U 四字段=0/0/1000/1000",
          (p["SURPLUS_1L"], p["SURPLUS_2L"], p["TOTAL_1L"], p["TOTAL_2L"]) == (0, 0, 1000, 1000), p)


def tc08():
    print("TC-08 多条拨出率取最小值")
    c = build(users=[("I", 1, "MY")],
              perf=[("I", 1000, 1000, 100, 1)],
              configs={"teamBisectRate": [24, 10], "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    assert_counts(s, 1, 1, 1)
    check("bisect=MIN(24,10)/100=0.10", s["TB_BISECT_RATE"] == Dn("0.10"))
    check("TOTAL_TB=10 / TB_RATE=0.1", s["TOTAL_TB"] == 10 and s["TB_RATE"] == Dn("0.1"))
    check("I.BONUS_TB=10.00", bonus_of(c, "I") == [Dn("10.00")], bonus_of(c, "I"))


def tc09a():
    print("TC-09A 等级表无匹配")
    # 用户 MEMBER_LV 指向不存在的等级 -> CALC_ID=NULL
    user_df = pd.DataFrame([{"ID": "U", "MEMBER_LV": "GHOST", "COUNTRY_ID": "MY"}])
    lvl_df = pd.DataFrame([{"ID": "L1", "CALC_ID": 1}])  # 不含 GHOST
    perf_df = pd.DataFrame([{"PERIOD_NUM": PERIOD, "CALC_MONTH": 6, "USER_ID": "U",
                             "TOTAL_1L": Dn(1000), "TOTAL_2L": Dn(1000), "PV_PCS": Dn(100), "IS_ACTIVE": 1}])
    cfg_df = pd.DataFrame([
        {"CONFIG_NAME": "teamBisectRate", "VALUE": Dn(24), "TYPE": "bonus"},
        {"CONFIG_NAME": "teamTouchRate1", "VALUE": Dn(10), "TYPE": "bonus"},
    ])
    c = TeamBonusCalculator(perf_df, user_df, lvl_df, cfg_df, pd.DataFrame(
        columns=["USER_ID", "SURPLUS_1L", "SURPLUS_2L", "TOTAL_1L", "TOTAL_2L"]))
    c.cleanup_mid_tables(); s = c.run(PERIOD, now=FIX_NOW)
    m1 = c.mid1_df().iloc[0]
    check("LAST_MEMBER_CALC_ID=None -> TOUCH_RATE=0", m1["LAST_MEMBER_CALC_ID"] is None and m1["TOUCH_RATE"] == 0)
    check("行数 MID1=1 / MID2=1 / BONUS=0 / TOUCH_BASE=0",
          (s["mid1_inserted"], s["mid2_inserted"], s["bonus_inserted"]) == (1, 1, 0)
          and c.mid2_df().iloc[0]["TOUCH_BASE"] == 0)


def tc09b():
    print("TC-09B 对应等级无比例配置（缺 teamTouchRate）")
    c = build(users=[("U", 5, "MY")],
              perf=[("U", 1000, 1000, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchCapping5": 1500})  # 有 Cap 无 Rate
    c.cleanup_mid_tables(); s = c.run(PERIOD, now=FIX_NOW)
    check("TOUCH_RATE=0 -> BONUS=0 / TOUCH_BASE=0（即使设Cap）",
          (s["bonus_inserted"] == 0) and c.mid2_df().iloc[0]["TOUCH_BASE"] == 0)
    check("行数 MID1=1 / MID2=1", (s["mid1_inserted"], s["mid2_inserted"]) == (1, 1))


def tc10():
    print("TC-10 对应等级未设封顶")
    c = build(users=[("U", 1, "MY")],
              perf=[("U", 1000, 600, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate1": 10})  # 无 teamTouchCapping1
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    m2 = c.mid2_df().iloc[0]
    assert_counts(s, 1, 1, 1)
    check("TOUCH_CAPPING=0 不封顶 -> TOUCH_BASE=60", m2["TOUCH_CAPPING"] == 0 and m2["TOUCH_BASE"] == 60)
    check("TB_RATE=0.4 / BONUS_TB=24.00", s["TB_RATE"] == Dn("0.4") and bonus_of(c, "U") == [Dn("24.00")])


# --------------------------------------------------------------------------- #
# 第三部分：精度截断与大盘加权
# --------------------------------------------------------------------------- #
def tc11a():
    print("TC-11A TB_RATE 6 位截断")
    c = build(users=[("U", 1, "MY")],
              perf=[("U", 60, 60, 1, 1)],
              configs={"teamBisectRate": 100, "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    assert_counts(s, 1, 1, 1)
    check("TOTAL_PV=1 / TOTAL_BASE=6 / TOTAL_TB=1", s["TOTAL_PV"] == 1 and s["TOTAL_BASE"] == 6 and s["TOTAL_TB"] == 1)
    check("TB_RATE=TRUNCATE(1/6,6)=0.166666(非0.166667)", s["TB_RATE"] == Dn("0.166666"), s["TB_RATE"])
    check("BONUS_TB=TRUNCATE(6×0.166666,2)=0.99", bonus_of(c, "U") == [Dn("0.99")], bonus_of(c, "U"))


def tc11b():
    print("TC-11B 极小比例坍缩致全盘停发")
    c = build(users=[("U", 1, "MY")],
              perf=[("U", 100000000, 100000000, 9, 1)],
              configs={"teamBisectRate": 100, "teamTouchRate1": 10, "teamTouchCapping1": 0},
              user_perf=[("U", 1, 2, 3, 4)])
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    check("TOTAL_TB=9 / TOTAL_BASE=10,000,000", s["TOTAL_TB"] == 9 and s["TOTAL_BASE"] == 10000000)
    check("TB_RATE=TRUNCATE(9/1e7,6)=0.000000 -> 停发", s["TB_RATE"] == 0)
    assert_counts(s, 1, 1, 0)
    p = perf_row(c, "U")
    check("阶段五仍结转：U 四字段=0/0/1e8/1e8",
          (p["SURPLUS_1L"], p["SURPLUS_2L"], p["TOTAL_1L"], p["TOTAL_2L"]) == (0, 0, 100000000, 100000000), p)


def tc12():
    print("TC-12 发奖金额 2 位截断（含 K 金额）")
    c = build(users=[("G", 1, "MY"), ("K", 1, "MY")],
              perf=[("G", 800, 800, 2000, 1), ("K", 299200, 299200, 8000, 1)],
              configs={"teamBisectRate": 100, "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_mid_tables(); s = c.run(PERIOD, now=FIX_NOW)
    check("TOTAL_PV=10000 / TOTAL_BASE=30000 / TB_RATE=0.333333",
          s["TOTAL_PV"] == 10000 and s["TOTAL_BASE"] == 30000 and s["TB_RATE"] == Dn("0.333333"))
    check("G.BONUS_TB=TRUNCATE(80×0.333333,2)=26.66", bonus_of(c, "G") == [Dn("26.66")], bonus_of(c, "G"))
    check("K.BONUS_TB=TRUNCATE(9973.32336,2)=9973.32", bonus_of(c, "K") == [Dn("9973.32")], bonus_of(c, "K"))
    check("行数 MID1=2 / MID2=2 / BONUS=2",
          (s["mid1_inserted"], s["mid2_inserted"], s["bonus_inserted"]) == (2, 2, 2))


def tc13():
    print("TC-13 有效总基数为 0 的保护")
    c = build(users=[("U", 1, "MY")],
              perf=[("U", 100, 0, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping1": 0},
              user_perf=[("U", 9, 9, 9, 9)])
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    check("TOTAL_PV=100 / TOTAL_BASE=0 -> TB_RATE=0", s["TOTAL_PV"] == 100 and s["TOTAL_BASE"] == 0 and s["TB_RATE"] == 0)
    assert_counts(s, 1, 0, 0)  # TOUCH_PV=0 不进 MID2
    p = perf_row(c, "U")  # 阶段五读 MID1（不受 TOUCH_PV 过滤）-> 仍结转
    check("阶段五仍结转：U 四字段=100/0/100/0",
          (p["SURPLUS_1L"], p["SURPLUS_2L"], p["TOTAL_1L"], p["TOTAL_2L"]) == (100, 0, 100, 0), p)


# --------------------------------------------------------------------------- #
# 第四部分：高危状态、脏数据与特定映射
# --------------------------------------------------------------------------- #
def tc14():
    print("TC-14 幂等性崩溃（重跑级联放大，不清理中间表）")
    # 10 个活跃且有基数用户
    users = [(f"U{i}", 1, "MY") for i in range(10)]
    perf = [(f"U{i}", 1000, 1000, 100, 1) for i in range(10)]
    cfg = {"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping1": 0}
    c = build(users, perf, cfg)
    c.cleanup_all()
    # 故意不清理 + 重跑，制造 MID1 内重复 USER_ID，属脏数据穿透：显式关闭 strict_unique_user
    s1 = c.run(PERIOD, now=datetime(2026, 6, 23, 15, 30, 45), strict_unique_user=False)
    check("第1次 MID1=10 / MID2=10 / BONUS=10",
          (s1["mid1_total_rows"], s1["mid2_total_rows"], s1["bonus_total_rows"]) == (10, 10, 10))
    pv1, base1, rate1 = s1["TOTAL_PV"], s1["TOTAL_BASE"], s1["TB_RATE"]
    # 不清理，第二次（不同秒，避免 ID 冲突）
    s2 = c.run(PERIOD, now=datetime(2026, 6, 23, 15, 30, 46), strict_unique_user=False)
    check("第2次累计 MID1=20 / MID2=30 / BONUS=40",
          (s2["mid1_total_rows"], s2["mid2_total_rows"], s2["bonus_total_rows"]) == (20, 30, 40),
          (s2["mid1_total_rows"], s2["mid2_total_rows"], s2["bonus_total_rows"]))
    check("TOTAL_PV 两次相同（快照汇总不受污染）", s2["TOTAL_PV"] == pv1)
    check("TOTAL_BASE 第2次膨胀约3倍（全量MID2活跃）", s2["TOTAL_BASE"] == base1 * 3,
          (base1, s2["TOTAL_BASE"]))


def tc15():
    print("TC-15 上游脏数据穿透（同 PERIOD+USER 两行）")
    # 同一 USER_ID 两行快照
    user_df = pd.DataFrame([{"ID": "X", "MEMBER_LV": "L1", "COUNTRY_ID": "MY"}])
    lvl_df = pd.DataFrame([{"ID": "L1", "CALC_ID": 1}])
    perf_df = pd.DataFrame([
        {"PERIOD_NUM": PERIOD, "CALC_MONTH": 6, "USER_ID": "X",
         "TOTAL_1L": Dn(1000), "TOTAL_2L": Dn(600), "PV_PCS": Dn(100), "IS_ACTIVE": 1},
        {"PERIOD_NUM": PERIOD, "CALC_MONTH": 6, "USER_ID": "X",
         "TOTAL_1L": Dn(2000), "TOTAL_2L": Dn(300), "PV_PCS": Dn(100), "IS_ACTIVE": 1},
    ])
    cfg_df = pd.DataFrame([
        {"CONFIG_NAME": "teamBisectRate", "VALUE": Dn(24), "TYPE": "bonus"},
        {"CONFIG_NAME": "teamTouchRate1", "VALUE": Dn(10), "TYPE": "bonus"},
        {"CONFIG_NAME": "teamTouchCapping1", "VALUE": Dn(0), "TYPE": "bonus"},
    ])
    up_df = pd.DataFrame([{"USER_ID": "X", "SURPLUS_1L": Dn(0), "SURPLUS_2L": Dn(0),
                           "TOTAL_1L": Dn(0), "TOTAL_2L": Dn(0)}])
    c = TeamBonusCalculator(perf_df, user_df, lvl_df, cfg_df, up_df)
    # 同 PERIOD+USER 两行属上游脏数据：阶段五结转结果 SQL 实为不确定，
    # 这里显式关闭 strict_unique_user 以复刻穿透（并刻意不断言 X 的结转结果）。
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW, strict_unique_user=False)
    check("行数 MID1=2 / MID2=2 / BONUS=2",
          (s["mid1_inserted"], s["mid2_inserted"], s["bonus_inserted"]) == (2, 2, 2))
    check("TOTAL_PV=200 / TOTAL_BASE=90 / TOTAL_TB=48 / TB_RATE=0.533333",
          s["TOTAL_PV"] == 200 and s["TOTAL_BASE"] == 90 and s["TOTAL_TB"] == 48 and s["TB_RATE"] == Dn("0.533333"))
    multiset = sorted(bonus_of(c, "X"))
    check("X 的 BONUS_TB 多重集合={15.99, 31.99}", multiset == [Dn("15.99"), Dn("31.99")], multiset)


def tc16a():
    print("TC-16A 僵尸用户结转（未匹配分支，专用空快照周期）")
    EMPTY_PERIOD = 209901
    perf_df = pd.DataFrame(columns=["PERIOD_NUM", "CALC_MONTH", "USER_ID",
                                    "TOTAL_1L", "TOTAL_2L", "PV_PCS", "IS_ACTIVE"])  # 该周期无快照
    user_df = pd.DataFrame(columns=["ID", "MEMBER_LV", "COUNTRY_ID"])
    lvl_df = pd.DataFrame(columns=["ID", "CALC_ID"])
    cfg_df = pd.DataFrame([{"CONFIG_NAME": "teamBisectRate", "VALUE": Dn(24), "TYPE": "bonus"}])
    up_df = pd.DataFrame([{"USER_ID": "Z", "SURPLUS_1L": Dn(100), "SURPLUS_2L": Dn(0),
                           "TOTAL_1L": Dn(999), "TOTAL_2L": Dn(888)}])  # 历史脏 TOTAL，应被重置为原 SURPLUS
    c = TeamBonusCalculator(perf_df, user_df, lvl_df, cfg_df, up_df)
    c.cleanup_mid_tables(); s = c.run(EMPTY_PERIOD, now=FIX_NOW)
    check("行数 MID1=0 / MID2=0 / BONUS=0",
          (s["mid1_inserted"], s["mid2_inserted"], s["bonus_inserted"]) == (0, 0, 0))
    z = c.user_perf.iloc[0]
    check("Z: SURPLUS_1L=100 不变 / SURPLUS_2L=0 不变", z["SURPLUS_1L"] == 100 and z["SURPLUS_2L"] == 0)
    check("Z: TOTAL_1L=原SURPLUS=100 / TOTAL_2L=0", z["TOTAL_1L"] == 100 and z["TOTAL_2L"] == 0,
          (z["TOTAL_1L"], z["TOTAL_2L"]))


def tc16b():
    print("TC-16B 参与本期的用户结转（匹配分支，Y 已存在于 AR_USER_PERF）")
    c = build(users=[("Y", 1, "MY")],
              perf=[("Y", 1000, 800, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping1": 0},
              user_perf=[("Y", 0, 0, 0, 0)])  # 前置：Y 已存在
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    m1 = c.mid1_df().iloc[0]
    assert_counts(s, 1, 1, 1)
    check("MID1: TOTAL=1000/800 SURPLUS=200/0",
          m1["TOTAL_1L"] == 1000 and m1["TOTAL_2L"] == 800 and m1["SURPLUS_1L"] == 200 and m1["SURPLUS_2L"] == 0)
    check("TB_RATE=0.3 / BONUS_TB=24.00", s["TB_RATE"] == Dn("0.3") and bonus_of(c, "Y") == [Dn("24.00")])
    y = c.user_perf.iloc[0]
    check("AR_USER_PERF Y 四字段覆写=1000/800/200/0",
          y["TOTAL_1L"] == 1000 and y["TOTAL_2L"] == 800 and y["SURPLUS_1L"] == 200 and y["SURPLUS_2L"] == 0,
          (y["TOTAL_1L"], y["TOTAL_2L"], y["SURPLUS_1L"], y["SURPLUS_2L"]))


def tc17():
    print("TC-17 空国家代码映射")
    c = build(users=[("W", 1, None)],   # COUNTRY_ID = NULL
              perf=[("W", 1000, 1000, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    assert_counts(s, 1, 1, 1)
    check("TOUCH_BASE=100 / TB_RATE=0.24 / BONUS_TB=24.00",
          c.mid2_df().iloc[0]["TOUCH_BASE"] == 100 and s["TB_RATE"] == Dn("0.24") and bonus_of(c, "W") == [Dn("24.00")])
    country = c.bonus_df().iloc[0]["COUNTRY_ID"]
    check("发奖记录 W.COUNTRY_ID='-1'", country == "-1", country)


def tc18():
    print("TC-18 入参月份被忽略")
    # 入参 month=12，但快照 CALC_MONTH=6
    c = build(users=[("V", 1, "MY")],
              perf=[("V", 1000, 1000, 100, 1, PERIOD, 6)],
              configs={"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_all(); s = c.run(PERIOD, iv_calc_month=12, now=FIX_NOW)
    assert_counts(s, 1, 1, 1)
    check("BONUS_TB=24.00", bonus_of(c, "V") == [Dn("24.00")])
    cmonth = c.bonus_df().iloc[0]["CALC_MONTH"]
    check("发奖记录 CALC_MONTH=6（非入参12）", cmonth == 6, cmonth)


def tc_id_format():
    print("附加：22 位流水号格式与 @ROWNUM 连续性（不绑定记录顺序）")
    c = build(users=[("G", 1, "MY"), ("K", 1, "MY")],
              perf=[("G", 800, 800, 2000, 1), ("K", 299200, 299200, 8000, 1)],
              configs={"teamBisectRate": 100, "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_all(); c.run(PERIOD, now=datetime(2026, 6, 23, 15, 30, 45))
    ids = list(c.bonus_df()["ID"])
    # 规范：多行发奖 SQL 无 ORDER BY，断言不应依赖返回顺序，只校验"形状"：
    #   ① 全部 22 位；② 前 14 位时间戳一致；③ 后 8 位序号集合 = {00000001, 00000002}。
    check("ID 长度=22", all(len(i) == 22 for i in ids), ids)
    check("前缀均为 20260623153045", all(i[:14] == "20260623153045" for i in ids), ids)
    suffixes = sorted(i[14:] for i in ids)
    check("序号集合={00000001, 00000002}", suffixes == ["00000001", "00000002"], suffixes)


def tc_dup_config():
    print("附加：AR_CONFIG 同名多行（strict 报错 / 非 strict 按 SQL LEFT JOIN 扇出）")
    # strict_config=True（默认）：重复 teamTouchRate1 应直接报错，避免静默吞掉
    c = build(users=[("U", 1, "MY")],
              perf=[("U", 1000, 600, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate1": [10, 20], "teamTouchCapping1": 0})
    raised = False
    try:
        c.cleanup_all(); c.run(PERIOD, now=FIX_NOW)
    except ValueError:
        raised = True
    check("strict_config=True 时重复 teamTouchRate1 报错", raised)
    # strict_config=False：按 SQL 双表 LEFT JOIN 扇出 -> MID1/MID2 各 2 行
    # （扇出同时令 MID1 出现重复 USER_ID，故阶段五也需 strict_unique_user=False）
    c2 = build(users=[("U", 1, "MY")],
               perf=[("U", 1000, 600, 100, 1)],
               configs={"teamBisectRate": 24, "teamTouchRate1": [10, 20], "teamTouchCapping1": 0})
    c2.cleanup_all()
    s = c2.run(PERIOD, now=FIX_NOW, strict_config=False, strict_unique_user=False)
    assert_counts(s, 2, 2, 2)
    bases = sorted(r["TOUCH_BASE"] for _, r in c2.mid2_df().iterrows())
    check("扇出两行 TOUCH_BASE={60,120}", bases == [Dn("60"), Dn("120")], bases)


def tc_strict_user():
    print("附加：MID1 重复 USER_ID（strict_unique_user 默认报错）")
    perf_df = pd.DataFrame([
        {"PERIOD_NUM": PERIOD, "CALC_MONTH": 6, "USER_ID": "X",
         "TOTAL_1L": Dn(1000), "TOTAL_2L": Dn(600), "PV_PCS": Dn(100), "IS_ACTIVE": 1},
        {"PERIOD_NUM": PERIOD, "CALC_MONTH": 6, "USER_ID": "X",
         "TOTAL_1L": Dn(2000), "TOTAL_2L": Dn(300), "PV_PCS": Dn(100), "IS_ACTIVE": 1},
    ])
    user_df = pd.DataFrame([{"ID": "X", "MEMBER_LV": "L1", "COUNTRY_ID": "MY"}])
    lvl_df = pd.DataFrame([{"ID": "L1", "CALC_ID": 1}])
    cfg_df = pd.DataFrame([
        {"CONFIG_NAME": "teamBisectRate", "VALUE": Dn(24), "TYPE": "bonus"},
        {"CONFIG_NAME": "teamTouchRate1", "VALUE": Dn(10), "TYPE": "bonus"},
        {"CONFIG_NAME": "teamTouchCapping1", "VALUE": Dn(0), "TYPE": "bonus"},
    ])
    up_df = pd.DataFrame([{"USER_ID": "X", "SURPLUS_1L": Dn(0), "SURPLUS_2L": Dn(0),
                           "TOTAL_1L": Dn(0), "TOTAL_2L": Dn(0)}])
    c = TeamBonusCalculator(perf_df, user_df, lvl_df, cfg_df, up_df)
    raised = False
    try:
        c.cleanup_all(); c.run(PERIOD, now=FIX_NOW)   # 默认 strict_unique_user=True
    except ValueError:
        raised = True
    check("strict_unique_user=True 时 MID1 重复 USER_ID 报错", raised)


def tc_null_config():
    print("附加：teamTouchRate VALUE=NULL 按 IFNULL(…,0) 取 0（不丢弃命中行）")
    user_df = pd.DataFrame([{"ID": "U", "MEMBER_LV": "L1", "COUNTRY_ID": "MY"}])
    lvl_df = pd.DataFrame([{"ID": "L1", "CALC_ID": 1}])
    perf_df = pd.DataFrame([{"PERIOD_NUM": PERIOD, "CALC_MONTH": 6, "USER_ID": "U",
                             "TOTAL_1L": Dn(1000), "TOTAL_2L": Dn(600), "PV_PCS": Dn(100), "IS_ACTIVE": 1}])
    cfg_df = pd.DataFrame([
        {"CONFIG_NAME": "teamBisectRate", "VALUE": Dn(24), "TYPE": "bonus"},
        {"CONFIG_NAME": "teamTouchRate1", "VALUE": None, "TYPE": "bonus"},   # VALUE=NULL
        {"CONFIG_NAME": "teamTouchCapping1", "VALUE": Dn(0), "TYPE": "bonus"},
    ])
    empty_up = pd.DataFrame(columns=["USER_ID", "SURPLUS_1L", "SURPLUS_2L", "TOTAL_1L", "TOTAL_2L"])
    c = TeamBonusCalculator(perf_df, user_df, lvl_df, cfg_df, empty_up)
    c.cleanup_all(); s = c.run(PERIOD, now=FIX_NOW)
    check("NULL 比例 -> TOUCH_RATE=0 / TOUCH_BASE=0 / 不发奖",
          c.mid1_df().iloc[0]["TOUCH_RATE"] == 0 and c.mid2_df().iloc[0]["TOUCH_BASE"] == 0 and s["bonus_inserted"] == 0)
    # NULL 命中行仍参与扇出：teamTouchRate1=[NULL, 20] -> 非 strict 扇出 2 行（含 0 与 0.2）
    cfg_df2 = pd.DataFrame([
        {"CONFIG_NAME": "teamBisectRate", "VALUE": Dn(100), "TYPE": "bonus"},
        {"CONFIG_NAME": "teamTouchRate1", "VALUE": None, "TYPE": "bonus"},
        {"CONFIG_NAME": "teamTouchRate1", "VALUE": Dn(20), "TYPE": "bonus"},
        {"CONFIG_NAME": "teamTouchCapping1", "VALUE": Dn(0), "TYPE": "bonus"},
    ])
    c2 = TeamBonusCalculator(perf_df.copy(), user_df.copy(), lvl_df.copy(), cfg_df2, empty_up.copy())
    c2.cleanup_all(); s2 = c2.run(PERIOD, now=FIX_NOW, strict_config=False, strict_unique_user=False)
    rates = sorted(r["TOUCH_RATE"] for _, r in c2.mid1_df().iterrows())
    check("NULL 命中行参与扇出：MID1=2 且 TOUCH_RATE={0, 0.2}",
          s2["mid1_inserted"] == 2 and rates == [Dn("0"), Dn("0.2")], (s2["mid1_inserted"], rates))


def tc_sql_faithful_cols():
    print("附加：mid?_df(sql_faithful=True) 列序对齐 AR_CALC_BONUS_TB DDL")
    c = build(users=[("U", 1, "MY")],
              perf=[("U", 1000, 600, 100, 1)],
              configs={"teamBisectRate": 24, "teamTouchRate1": 10, "teamTouchCapping1": 0})
    c.cleanup_all(); c.run(PERIOD, now=FIX_NOW)
    cols1 = list(c.mid1_df(sql_faithful=True).columns)
    cols2 = list(c.mid2_df(sql_faithful=True).columns)
    check("MID1 列序: LAST_MEMBER_CALC_ID 在 TOUCH_RATE 之前",
          cols1.index("LAST_MEMBER_CALC_ID") < cols1.index("TOUCH_RATE"), cols1)
    check("MID1 剔除内部辅助列 COUNTRY_ID/PV_PCS",
          "COUNTRY_ID" not in cols1 and "PV_PCS" not in cols1, cols1)
    check("MID2 列序: TOUCH_BASE 在 IS_ACTIVE 之前", cols2.index("TOUCH_BASE") < cols2.index("IS_ACTIVE"), cols2)


def main():
    for fn in [tc01, tc02, tc03, tc04, tc05, tc06a, tc06b,
               tc07a, tc07b, tc08, tc09a, tc09b, tc10,
               tc11a, tc11b, tc12, tc13,
               tc14, tc15, tc16a, tc16b, tc17, tc18,
               tc_id_format, tc_dup_config, tc_strict_user,
               tc_null_config, tc_sql_faithful_cols]:
        fn()
    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    print("\n" + "=" * 60)
    print(f"断言通过：{passed}/{total}")
    failed = [(n, d) for n, ok, d in _results if not ok]
    if failed:
        print("失败项：")
        for n, d in failed:
            print(f"  - {n}  {d}")
    else:
        print("全部断言通过 ✅")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
