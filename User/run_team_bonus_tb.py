# -*- coding: utf-8 -*-
"""
team_bonus_tb 调用示例 / 冒烟测试
=================================
演示如何构造 5 张输入表、运行一次完整结算，并打印中间表、发奖表与结转后的业绩主表。
直接运行：

    python run_team_bonus_tb.py

样例数据特意覆盖了几条关键路径：
  * A：左>右标准对碰；B：左=右完美对碰；C：触发封顶；
  * D：不活跃会员（验证 TOTAL_PV 含其 PV、但 TOTAL_BASE 不含其基数的"活跃口径不对称"）；
  * 业绩主表里 A 命中本期快照（覆写分支）、Z 是僵尸用户（未匹配分支）。
"""
from decimal import Decimal

import pandas as pd

from team_bonus_tb import TeamBonusCalculator

# 让 Decimal / 宽表打印得整齐一些
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def D(x):
    """构造输入时把数值写成 Decimal，避免 float 误差（与库内精度口径一致）。"""
    return Decimal(str(x))


def build_sample_inputs():
    """返回 (perf_month, user, member_level, config, user_perf) 五张 DataFrame。"""
    PERIOD, MONTH = 202506, 6

    # ① 业绩快照 AR_PERF_MONTH —— 本期每个会员一行（含活跃与不活跃）
    perf_month = pd.DataFrame(
        [
            # USER_ID, TOTAL_1L, TOTAL_2L, PV_PCS, IS_ACTIVE
            {"PERIOD_NUM": PERIOD, "CALC_MONTH": MONTH, "USER_ID": "A",
             "TOTAL_1L": D(1000), "TOTAL_2L": D(600), "PV_PCS": D(100), "IS_ACTIVE": 1},
            {"PERIOD_NUM": PERIOD, "CALC_MONTH": MONTH, "USER_ID": "B",
             "TOTAL_1L": D(500), "TOTAL_2L": D(500), "PV_PCS": D(200), "IS_ACTIVE": 1},
            {"PERIOD_NUM": PERIOD, "CALC_MONTH": MONTH, "USER_ID": "C",
             "TOTAL_1L": D(20000), "TOTAL_2L": D(10000), "PV_PCS": D(1000), "IS_ACTIVE": 1},
            {"PERIOD_NUM": PERIOD, "CALC_MONTH": MONTH, "USER_ID": "D",
             "TOTAL_1L": D(800), "TOTAL_2L": D(700), "PV_PCS": D(50), "IS_ACTIVE": 0},  # 不活跃
        ],
        columns=["PERIOD_NUM", "CALC_MONTH", "USER_ID", "TOTAL_1L", "TOTAL_2L", "PV_PCS", "IS_ACTIVE"],
    )

    # ② 会员表 AR_USER —— MEMBER_LV 关联 AR_MEMBER_LEVEL.ID
    user = pd.DataFrame(
        [
            {"ID": "A", "MEMBER_LV": "LV_D", "COUNTRY_ID": "MY"},
            {"ID": "B", "MEMBER_LV": "LV_SD", "COUNTRY_ID": "MY"},
            {"ID": "C", "MEMBER_LV": "LV_GD", "COUNTRY_ID": "TH"},
            {"ID": "D", "MEMBER_LV": "LV_D", "COUNTRY_ID": "MY"},
        ],
        columns=["ID", "MEMBER_LV", "COUNTRY_ID"],
    )

    # ③ 等级表 AR_MEMBER_LEVEL —— ID 与 user.MEMBER_LV 对齐；CALC_ID 用于拼接配置名
    member_level = pd.DataFrame(
        [
            {"ID": "LV_D", "CALC_ID": 1},
            {"ID": "LV_SD", "CALC_ID": 2},
            {"ID": "LV_GD", "CALC_ID": 3},
        ],
        columns=["ID", "CALC_ID"],
    )

    # ④ 配置表 AR_CONFIG（均 TYPE='bonus'）
    #    teamBisectRate=24%；各等级 teamTouchRate{CALC_ID} 与 teamTouchCapping{CALC_ID}
    config = pd.DataFrame(
        [
            {"CONFIG_NAME": "teamBisectRate", "VALUE": D(24), "TYPE": "bonus"},
            {"CONFIG_NAME": "teamTouchRate1", "VALUE": D(10), "TYPE": "bonus"},
            {"CONFIG_NAME": "teamTouchCapping1", "VALUE": D(0), "TYPE": "bonus"},      # 0 = 不封顶
            {"CONFIG_NAME": "teamTouchRate2", "VALUE": D(15), "TYPE": "bonus"},
            {"CONFIG_NAME": "teamTouchCapping2", "VALUE": D(0), "TYPE": "bonus"},
            {"CONFIG_NAME": "teamTouchRate3", "VALUE": D(20), "TYPE": "bonus"},
            {"CONFIG_NAME": "teamTouchCapping3", "VALUE": D(1500), "TYPE": "bonus"},   # GD 段封顶 1500
        ],
        columns=["CONFIG_NAME", "VALUE", "TYPE"],
    )

    # ⑤ 业绩主表 AR_USER_PERF（结转刷新对象，会被原地更新）
    #    A：本期快照里有 -> 覆写分支；Z：本期快照里没有 -> 僵尸用户未匹配分支
    user_perf = pd.DataFrame(
        [
            {"USER_ID": "A", "SURPLUS_1L": D(1), "SURPLUS_2L": D(2), "TOTAL_1L": D(3), "TOTAL_2L": D(4)},
            {"USER_ID": "Z", "SURPLUS_1L": D(100), "SURPLUS_2L": D(0), "TOTAL_1L": D(999), "TOTAL_2L": D(888)},
        ],
        columns=["USER_ID", "SURPLUS_1L", "SURPLUS_2L", "TOTAL_1L", "TOTAL_2L"],
    )

    return perf_month, user, member_level, config, user_perf


def main():
    perf_month, user, member_level, config, user_perf = build_sample_inputs()

    # 1) 实例化
    calc = TeamBonusCalculator(perf_month, user, member_level, config, user_perf)

    # 2) 执行前全量清空中间表/奖金表（常规前置；不清会跨次累积）
    calc.cleanup_all()

    # 3) 运行一次结算
    #    入参只需周期号；CALC_MONTH 取自快照（入参 iv_calc_month 不参与主体逻辑）。
    #    strict_config / strict_unique_user 默认 True：配置或上游数据重复会直接报错。
    summary = calc.run(iv_period_num=202506)

    # 4) 打印全盘汇总
    print("=" * 70)
    print("全盘汇总（run 的返回值）")
    print("=" * 70)
    for k in ["mid1_inserted", "mid2_inserted", "bonus_inserted",
              "TOTAL_PV", "TOTAL_BASE", "TB_BISECT_RATE", "TOTAL_TB", "TB_RATE"]:
        print(f"  {k:<16}= {summary[k]}")

    # 5) 中间表（用 sql_faithful=True 取与 DDL 一致的列序，剔除内部辅助列）
    print("\n" + "=" * 70)
    print("MID1（对碰基础信息，含活跃+不活跃）")
    print("=" * 70)
    print(calc.mid1_df(sql_faithful=True).to_string(index=False))

    print("\n" + "=" * 70)
    print("MID2（对碰计奖基数，TOUCH_PV>0）")
    print("=" * 70)
    print(calc.mid2_df(sql_faithful=True).to_string(index=False))

    # 6) 最终发奖表（19 列，活跃且 TOUCH_BASE>0 才发）
    print("\n" + "=" * 70)
    print("AR_CALC_BONUS_TB（最终发奖明细）")
    print("=" * 70)
    bonus = calc.bonus_df()
    cols = ["ID", "USER_ID", "TOUCH_PV", "TOUCH_RATE", "TOUCH_BASE",
            "TB_RATE", "BONUS_TB", "COUNTRY_ID", "IS_ACTIVE"]
    print(bonus[cols].to_string(index=False))
    print(f"\n  共发奖 {len(bonus)} 笔，奖金合计 = {sum(bonus['BONUS_TB'])}")

    # 7) 结转后的业绩主表（A=覆写分支，Z=未匹配分支）
    print("\n" + "=" * 70)
    print("AR_USER_PERF（阶段五结转后）")
    print("=" * 70)
    print(calc.user_perf.to_string(index=False))

    print("\n✅ 运行结束，未抛异常即说明链路正常。")


if __name__ == "__main__":
    main()
