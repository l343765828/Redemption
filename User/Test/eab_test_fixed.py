"""
EAB 集成测试（修正版）

本版根据 code review 意见修正，相对上一版的改动：
[必须修改]
  1. TC-CONF-02 参数化 0 / -10 / 101（原仅测 -10）
  2. TC-CONF-05 按 Final Approved Edition 规范断言（None/""→"配置的值为空"，"abc"/"NaN"→"值非法"，
     "Infinity"→"不是有限数值"）；服务 _parse_eab_rate 已同步对齐（strip 判空 + NaN 单独归"值非法"）
  2b. TC-DIRT-03A 参数化 None / np.nan（规范要求两者都熔断）
  3. TC-DIRT-03B 补维表空串 ""（原仅 "null"）
  4. TC-DIRT-10 补 np.nan 与 "null"（原仅 None / ""）
  5. TC-PERF-04 补 1.5 与 None（原仅 2）
  6. TC-STR-02 补"两大区·一有单一无单"混合场景
  7. _expect_fail 增加严格异常类型断言（默认 ValueError）
  8. main() 失败时 sys.exit(1)（CI 可正确判红）
  9. TC-DIRT-05 / TC-DIRT-08 拆成独立测试函数
[断言增强]
  10. TC-CAL-02 / 05 / 06 / 07 补全字段与金额断言
  11. TC-MAP-01 / 04 补奖金金额断言（验证资金池/分母而不仅是映射字段）
  12. TC-DIRT-08 补 country_id / region_country_id / actual_bonus 断言
  13. TC-STR-01 在保留 SG 版本基础上，补一个完全按规范的 MY 版本

注意：
- 本测试需配合【空分区修复版】EliteAchievementBonusService.py 运行
  （TC-CAL-05 / TC-PART-01 是空分区 BUG 的回归防线）。
- 若服务文件实际名为 EliteAchievementBonusService(2).py 之类，请重命名为
  EliteAchievementBonusService.py 或调整下面的 import。
"""
import logging
import sys
import pandas as pd
import numpy as np
import dask.dataframe as dd
from decimal import Decimal
from dask.distributed import LocalCluster, Client

from EliteAchievementBonusService import EliteAchievementBonusService, build_eab_service_for_prod, reject_float_before_dask

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - [IntegrationTest] %(message)s')
logger = logging.getLogger(__name__)


def _to_dask(pdf, npartitions=1):
    return dd.from_pandas(pdf, npartitions=npartitions)


def _get_base_data():
    period_num = 202604
    calc_month = 4
    pdf_elite = pd.DataFrame([
        {'period_num': period_num, 'user_id': 'U100', 'gpv': "1000", 'country_id': 'US'},
        {'period_num': period_num, 'user_id': 'U200', 'gpv': "2000", 'country_id': 'US'}
    ])
    pdf_orders = pd.DataFrame([{'period_num': period_num, 'country_id': 'MY', 'pv': "10000"}])
    pdf_perf = pd.DataFrame([
        {'period_num': period_num, 'user_id': 'U100', 'is_active': 1},
        {'period_num': period_num, 'user_id': 'U200', 'is_active': 1}
    ])
    pdf_user_info = pd.DataFrame({'id': ['U100', 'U200'], 'country_id': ['MY', 'MY']})
    pdf_config = pd.DataFrame([
        {'config_name': 'eabRate', 'value': "10", 'type': 'bonus'},
        {'config_name': 'CountrySG', 'value': 'MY', 'type': 'bonus'}
    ])
    pdf_master = pd.DataFrame({'country_id': ['MY', 'SG']})
    return {
        'period_num': period_num, 'calc_month': calc_month,
        'ddf_elite': _to_dask(pdf_elite), 'ddf_orders': _to_dask(pdf_orders),
        'ddf_perf': _to_dask(pdf_perf), 'df_config': pdf_config,
        'df_user': pdf_user_info, 'df_master': pdf_master
    }


def _base_args(**updates):
    base = _get_base_data()
    args = {
        'period': base['period_num'], 'calc_month': base['calc_month'],
        'ddf_elite_users': base['ddf_elite'], 'ddf_orders': base['ddf_orders'],
        'ddf_user_perf': base['ddf_perf'], 'df_config': base['df_config'],
        'df_user_info': base['df_user'], 'df_country_master': base['df_master']
    }
    args.update(updates)
    return args


def _eab_rate_config(value):
    """构造只含一条 eabRate 的配置（value 可为任意类型，用于配置异常测试）。"""
    return pd.DataFrame([{'config_name': 'eabRate', 'value': value, 'type': 'bonus'}])


def _expect_fail(func, expected_msg, *args, expected_type=ValueError, **kwargs):
    """
    断言 func 抛出 expected_type 类型、且消息包含 expected_msg 的异常。
    expected_type 默认 ValueError —— 杜绝"任何异常只要含关键字就通过"的弱断言。
    """
    try:
        func(*args, **kwargs)
    except Exception as e:
        if not isinstance(e, expected_type):
            raise AssertionError(
                f"异常类型不符。\n期望类型: {expected_type.__name__}\n"
                f"实际异常: {type(e).__name__}: {e}"
            )
        if expected_msg in str(e):
            return
        raise AssertionError(
            f"异常信息不匹配。\n期望包含: {expected_msg}\n实际异常: {type(e).__name__}: {e}"
        )
    raise AssertionError(f"预期抛出异常，但代码静默通过。期望关键字: {expected_msg}")


def run_module1_historical_bugs(service):
    # TC-REG-01: 跨期数据污染拦截
    pdf_elite = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000"}, {'period_num': 202603, 'user_id': 'U300', 'gpv': "9999"}])
    pdf_orders = pd.DataFrame([{'period_num': 202604, 'country_id': 'MY', 'pv': "10000"}, {'period_num': 202603, 'country_id': 'MY', 'pv': "99999"}])
    pdf_perf = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': 1}, {'period_num': 202603, 'user_id': 'U300', 'is_active': 1}])
    pdf_user = pd.DataFrame({'id': ['U100', 'U300'], 'country_id': ['MY', 'MY']})
    res = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite), ddf_orders=_to_dask(pdf_orders), ddf_user_perf=_to_dask(pdf_perf), df_user_info=pdf_user))
    aud = res['AR_CALC_BONUS_EAB_AUDIT'].compute()
    assert 'U300' not in aud['user_id'].values, "受到历史期人员污染"
    assert aud.iloc[0]['period_num'] == 202604 and aud.iloc[0]['calc_month'] == 4, "输出周期未对齐入参"
    assert Decimal(aud.iloc[0]['actual_bonus']) == Decimal("1000.00"), "受到历史 PV 污染"

    # TC-REG-02: 主副表驱动颠倒
    pdf_elite_2 = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000"}])
    pdf_orders_2 = pd.DataFrame([{'period_num': 202604, 'country_id': 'SG', 'pv': "10000"}])
    pdf_perf_2 = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': 1}])
    pdf_user_2 = pd.DataFrame({'id': ['U100'], 'country_id': ['MY']})
    res_2 = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_2), ddf_orders=_to_dask(pdf_orders_2), ddf_user_perf=_to_dask(pdf_perf_2), df_user_info=pdf_user_2))
    aud_2 = res_2['AR_CALC_BONUS_EAB_AUDIT'].compute()
    u100_res_2 = aud_2.iloc[0]
    assert u100_res_2['region_country_id'] == 'MY', "未能正确映射到 MY 大区"
    assert Decimal(u100_res_2['actual_bonus']) == Decimal("1000.00"), "主副表颠倒导致漏发"
    assert Decimal(u100_res_2['calc_bonus']) == Decimal("1000.00")
    assert u100_res_2['record_type'] == 'payable'

    # TC-REG-03A/B: 同期重复拦截
    pdf_elite_bad = pd.concat([pdf_elite_2, pdf_elite_2])
    _expect_fail(service.calculate_eab_bonus, "达标会员存在重复 user_id", **_base_args(ddf_elite_users=_to_dask(pdf_elite_bad)))
    pdf_perf_bad = pd.concat([pdf_perf_2, pdf_perf_2])
    _expect_fail(service.calculate_eab_bonus, "ddf_user_perf 单用户多行", **_base_args(ddf_user_perf=_to_dask(pdf_perf_bad)))

    # TC-REG-03C: 活跃表跨期 Fan-out 防御
    pdf_perf_cross = pd.concat([pdf_perf_2, pd.DataFrame([{'period_num': 202603, 'user_id': 'U100', 'is_active': 0}])])
    res_cross = service.calculate_eab_bonus(**_base_args(ddf_user_perf=_to_dask(pdf_perf_cross)))
    aud_cross = res_cross['AR_CALC_BONUS_EAB_AUDIT'].compute()
    assert len(aud_cross) > 0, "跨期历史数据不应触发单用户多行阻断"
    assert aud_cross[aud_cross['user_id'] == 'U100'].iloc[0]['is_active'] == 1, "历史期不活跃状态不应污染当期活跃状态"


def run_module2_core_calc(service):
    # TC-CAL-01: 标准全额发放
    res_1 = service.calculate_eab_bonus(**_base_args())
    aud_1 = res_1['AR_CALC_BONUS_EAB_AUDIT'].compute()
    leg_1 = res_1['AR_CALC_BONUS_EAB'].compute()
    assert len(aud_1) == 2 and len(leg_1) == 2
    for uid in ['U100', 'U200']:
        assert Decimal(aud_1[aud_1['user_id'] == uid].iloc[0]['actual_bonus']) == Decimal("500.00")
        assert aud_1[aud_1['user_id'] == uid].iloc[0]['record_type'] == 'payable'
        assert leg_1[leg_1['user_id'] == uid].iloc[0]['is_active'] == 1
        assert Decimal(leg_1[leg_1['user_id'] == uid].iloc[0]['bonus_eab']) == Decimal("500.00")

    # TC-CAL-02: 活跃度拦截（[增强] 两人都在两表中，字段全断言）
    pdf_perf = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': 1}, {'period_num': 202604, 'user_id': 'U200', 'is_active': 0}])
    res_2 = service.calculate_eab_bonus(**_base_args(ddf_user_perf=_to_dask(pdf_perf)))
    aud_2 = res_2['AR_CALC_BONUS_EAB_AUDIT'].compute()
    leg_2 = res_2['AR_CALC_BONUS_EAB'].compute()
    # 两人都在 Audit 和 Legacy
    assert set(aud_2['user_id']) == {'U100', 'U200'} and set(leg_2['user_id']) == {'U100', 'U200'}, "两人都应在 Audit 和 Legacy"
    # A: 活跃 payable，calc == actual == 500
    a_aud = aud_2[aud_2['user_id'] == 'U100'].iloc[0]
    assert a_aud['record_type'] == 'payable'
    assert Decimal(a_aud['calc_bonus']) == Decimal("500.00")
    assert Decimal(a_aud['actual_bonus']) == Decimal("500.00")
    # B: 不活跃 audit，calc == 500 但 actual == 0
    b_aud = aud_2[aud_2['user_id'] == 'U200'].iloc[0]
    assert b_aud['record_type'] == 'audit'
    assert Decimal(b_aud['calc_bonus']) == Decimal("500.00")
    assert Decimal(b_aud['actual_bonus']) == Decimal("0.00")
    # Legacy 中 B：bonus_eab == 500，is_active == 0
    b_leg = leg_2[leg_2['user_id'] == 'U200'].iloc[0]
    assert Decimal(b_leg['bonus_eab']) == Decimal("500.00")
    assert b_leg['is_active'] == 0

    # TC-CAL-03: 除不尽的高精度舍入
    pdf_elite_3 = pd.DataFrame([{'period_num': 202604, 'user_id': f'U{i}', 'gpv': "1000"} for i in range(1, 4)])
    pdf_orders_3 = pd.DataFrame([{'period_num': 202604, 'country_id': 'MY', 'pv': "1000"}])
    pdf_perf_3 = pd.DataFrame([{'period_num': 202604, 'user_id': f'U{i}', 'is_active': 1} for i in range(1, 4)])
    pdf_user_3 = pd.DataFrame({'id': [f'U{i}' for i in range(1, 4)], 'country_id': ['MY'] * 3})
    res_3 = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_3), ddf_orders=_to_dask(pdf_orders_3), ddf_user_perf=_to_dask(pdf_perf_3), df_user_info=pdf_user_3))
    aud_3 = res_3['AR_CALC_BONUS_EAB_AUDIT'].compute()
    assert len(aud_3) == 3
    assert set(aud_3['actual_bonus']) == {"33.33"}, "应确保所有 3 人金额均等且舍入精确"

    # TC-CAL-04: 舍入进位临界值测试
    pdf_elite_1 = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000"}])
    pdf_orders_4 = pd.DataFrame([{'period_num': 202604, 'country_id': 'MY', 'pv': "12.35"}])
    pdf_perf_1 = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': 1}])
    pdf_user_1 = pd.DataFrame({'id': ['U100'], 'country_id': ['MY']})
    res_4 = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_1), ddf_orders=_to_dask(pdf_orders_4), ddf_user_perf=_to_dask(pdf_perf_1), df_user_info=pdf_user_1))
    assert Decimal(res_4['AR_CALC_BONUS_EAB_AUDIT'].compute().iloc[0]['actual_bonus']) == Decimal("1.24")

    # TC-CAL-05: 无人分钱除零保护（[增强] Audit 和 Legacy 都为空）
    pdf_elite_none = pd.DataFrame(columns=['period_num', 'user_id', 'gpv'])
    res_5 = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_none)))
    assert len(res_5['AR_CALC_BONUS_EAB_AUDIT'].compute()) == 0, "Audit 应为空"
    assert len(res_5['AR_CALC_BONUS_EAB'].compute()) == 0, "Legacy 也应为空"

    # TC-CAL-06: 0 PV（[增强] 补 record_type == audit）
    pdf_orders_zero = pd.DataFrame([{'period_num': 202604, 'country_id': 'MY', 'pv': "0"}])
    res_zero = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_1), ddf_orders=_to_dask(pdf_orders_zero), df_user_info=pdf_user_1))
    aud_zero = res_zero['AR_CALC_BONUS_EAB_AUDIT'].compute()
    leg_zero = res_zero['AR_CALC_BONUS_EAB'].compute()
    assert Decimal(aud_zero.iloc[0]['calc_bonus']) == Decimal("0.00")
    assert Decimal(aud_zero.iloc[0]['actual_bonus']) == Decimal("0.00")
    assert aud_zero.iloc[0]['record_type'] == 'audit', "0 PV 应为 audit 明细"
    assert len(leg_zero) == 0

    # TC-CAL-07: 负净 PV（[增强] 补 calc_bonus == 0.00 与 record_type == audit）
    pdf_orders_neg = pd.DataFrame([{'period_num': 202604, 'country_id': 'MY', 'pv': "-100"}])
    res_neg = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_1), ddf_orders=_to_dask(pdf_orders_neg), df_user_info=pdf_user_1))
    aud_neg = res_neg['AR_CALC_BONUS_EAB_AUDIT'].compute()
    leg_neg = res_neg['AR_CALC_BONUS_EAB'].compute()
    assert Decimal(aud_neg.iloc[0]['calc_bonus']) == Decimal("0.00"), "负 PV 按 0 池，calc_bonus 应为 0.00"
    assert Decimal(aud_neg.iloc[0]['actual_bonus']) == Decimal("0.00")
    assert aud_neg.iloc[0]['record_type'] == 'audit', "负 PV 应为 audit 明细"
    assert len(leg_neg) == 0


def run_module3_config_mapping(service):
    # TC-CONF-01
    _expect_fail(service.calculate_eab_bonus, "EAB_RATE 配置缺失", **_base_args(df_config=pd.DataFrame([{'config_name': 'CountrySG', 'value': 'MY', 'type': 'bonus'}])))

    # TC-CONF-02: [修正] 参数化 0 / -10 / 101 三个非法范围值都应熔断
    for bad_rate in ["0", "-10", "101"]:
        _expect_fail(service.calculate_eab_bonus, "介于 (0, 100]", **_base_args(df_config=_eab_rate_config(bad_rate)))

    # TC-CONF-03
    _expect_fail(service.calculate_eab_bonus, "配置存在多条", **_base_args(df_config=pd.DataFrame([{'config_name': 'eabRate', 'value': "10", 'type': 'bonus'}, {'config_name': 'eabRate', 'value': "20", 'type': 'bonus'}])))
    # TC-CONF-04
    _expect_fail(service.calculate_eab_bonus, "配置值为 float", **_base_args(df_config=_eab_rate_config(10.0)))

    # TC-CONF-05: 配置异常值（服务已按 Final Approved Edition 规范对齐）
    # TC-CONF-05A: 空值 None / ""（含纯空白）-> "配置的值为空"
    for v in [None, ""]:
        _expect_fail(service.calculate_eab_bonus, "配置的值为空", **_base_args(df_config=_eab_rate_config(v)))
    # TC-CONF-05B: 非法字符串 "abc" / "NaN" -> "值非法"
    #   （注：Decimal("NaN") 本身合法，服务在 is_finite 之前用 is_nan() 单独归类为"值非法"）
    for v in ["abc", "NaN"]:
        _expect_fail(service.calculate_eab_bonus, "值非法", **_base_args(df_config=_eab_rate_config(v)))
    # TC-CONF-05C: "Infinity" -> "不是有限数值"
    _expect_fail(service.calculate_eab_bonus, "不是有限数值", **_base_args(df_config=_eab_rate_config("Infinity")))

    # TC-MAP-01: 干扰类型忽略（[增强] 不仅断言映射字段，还断言奖金金额，验证资金池/分母正确）
    cfg_other = pd.DataFrame([{'config_name': 'eabRate', 'value': "10", 'type': 'bonus'}, {'config_name': 'CountrySG', 'value': 'MY', 'type': 'bonus'}, {'config_name': 'CountrySG', 'value': 'XX', 'type': 'other'}])
    pdf_elite_1 = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000"}])
    pdf_orders_sg = pd.DataFrame([{'period_num': 202604, 'country_id': 'SG', 'pv': "10000"}])
    pdf_user_my = pd.DataFrame({'id': ['U100'], 'country_id': ['MY']})
    res_map = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_1), ddf_orders=_to_dask(pdf_orders_sg), df_user_info=pdf_user_my, df_config=cfg_other))
    aud_map = res_map['AR_CALC_BONUS_EAB_AUDIT'].compute()
    assert aud_map.iloc[0]['region_country_id'] == 'MY'
    assert Decimal(aud_map.iloc[0]['actual_bonus']) == Decimal("1000.00"), "SG->MY 合并后资金池/分母应使 U100 得 1000.00"

    # TC-MAP-02 & 03
    _expect_fail(service.calculate_eab_bonus, "重复源国家", **_base_args(df_config=pd.DataFrame([{'config_name': 'eabRate', 'value': "10", 'type': 'bonus'}, {'config_name': 'CountrySG', 'value': 'MY', 'type': 'bonus'}, {'config_name': 'CountrySG', 'value': 'XX', 'type': 'bonus'}])))
    _expect_fail(service.calculate_eab_bonus, "目标大区 value 非法", **_base_args(df_config=pd.DataFrame([{'config_name': 'eabRate', 'value': "10", 'type': 'bonus'}, {'config_name': 'CountrySG', 'value': '', 'type': 'bonus'}])))

    # TC-MAP-04: 普通国家无映射保持原样（[增强] 补奖金金额断言）
    pdf_elite_us = pd.DataFrame([{'period_num': 202604, 'user_id': 'U1', 'gpv': "1000"}])
    pdf_orders_us = pd.DataFrame([{'period_num': 202604, 'country_id': 'US', 'pv': "1000"}])
    pdf_perf_us = pd.DataFrame([{'period_num': 202604, 'user_id': 'U1', 'is_active': 1}])
    pdf_user_us = pd.DataFrame({'id': ['U1'], 'country_id': ['US']})
    df_master_us = pd.DataFrame({'country_id': ['US', 'MY']})
    cfg_us_only = pd.DataFrame([{'config_name': 'eabRate', 'value': "10", 'type': 'bonus'}])
    res_us = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_us), ddf_orders=_to_dask(pdf_orders_us), ddf_user_perf=_to_dask(pdf_perf_us), df_user_info=pdf_user_us, df_country_master=df_master_us, df_config=cfg_us_only))
    aud_us = res_us['AR_CALC_BONUS_EAB_AUDIT'].compute()
    assert aud_us.iloc[0]['region_country_id'] == 'US'
    assert Decimal(aud_us.iloc[0]['actual_bonus']) == Decimal("100.00"), "US 独立成区，1000*10%/1 应为 100.00"

    # TC-MAP-05: 源国家不在主数据
    cfg_bad_src = pd.DataFrame([{'config_name': 'eabRate', 'value': "10", 'type': 'bonus'}, {'config_name': 'CountryZZ', 'value': 'MY', 'type': 'bonus'}])
    _expect_fail(service.calculate_eab_bonus, "源国家不在国家主数据", **_base_args(df_config=cfg_bad_src))


def run_module4_fail_fast(service):
    pdf_elite_one = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000"}])

    # TC-PARAM/INPUT
    _expect_fail(service.calculate_eab_bonus, "带小数的非整数值", **_base_args(period=202604.9))
    _expect_fail(service.calculate_eab_bonus, "非法", **_base_args(calc_month=13))
    _expect_fail(service.calculate_eab_bonus, "CPU dask.DataFrame", **_base_args(ddf_orders=pd.DataFrame([{'period_num': 202604}])))
    _expect_fail(service.calculate_eab_bonus, "缺失必需字段", **_base_args(ddf_orders=_to_dask(pd.DataFrame([{'period_num': 202604, 'country_id': 'MY'}]))))

    # TC-DIRT-01A/B: Float 拦截
    pdf_dirty_float = pd.DataFrame([{'period_num': 202604, 'country_id': 'MY', 'pv': 1000.0}])
    _expect_fail(service.calculate_eab_bonus, "dtype 为 float", **_base_args(ddf_orders=_to_dask(pdf_dirty_float)))
    pdf_mixed_float = pd.DataFrame({'period_num': [202604, 202604], 'country_id': ['MY', 'MY'], 'pv': pd.Series(["1000", 1.0], dtype="object")})
    _expect_fail(reject_float_before_dask, "混入 float 值", pdf=pdf_mixed_float, cols={'pv'}, df_name='ddf_orders')

    # TC-DIRT-02: 超精度
    pdf_elite_005 = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000.005"}])
    _expect_fail(service.calculate_eab_bonus, "小数位超 2 位", **_base_args(ddf_elite_users=_to_dask(pdf_elite_005)))

    # TC-DIRT-03A: 维表空值 None / np.nan -> "ID/国籍为空"（[修正] 补 np.nan，规范要求两者都熔断）
    for bad_cid in [None, np.nan]:
        pdf_user_bad = pd.DataFrame({'id': ['U100'], 'country_id': [bad_cid]})
        _expect_fail(service.calculate_eab_bonus, "ID/国籍为空", **_base_args(df_user_info=pdf_user_bad, ddf_elite_users=_to_dask(pdf_elite_one)))
    # TC-DIRT-03B: 维表非法字符串 "null" 与 ""（[修正] 补空串）
    for bad_cid in ["null", ""]:
        pdf_user_bad = pd.DataFrame({'id': ['U100'], 'country_id': [bad_cid]})
        _expect_fail(service.calculate_eab_bonus, "存在国籍或ID为非法无效字符串", **_base_args(df_user_info=pdf_user_bad, ddf_elite_users=_to_dask(pdf_elite_one)))

    # TC-DIRT-04: 目标大区不在主数据
    cfg_bad_tgt = pd.DataFrame([{'config_name': 'eabRate', 'value': "10", 'type': 'bonus'}, {'config_name': 'CountrySG', 'value': 'XX', 'type': 'bonus'}])
    _expect_fail(service.calculate_eab_bonus, "目标大区不在国家主数据", **_base_args(df_config=cfg_bad_tgt, ddf_elite_users=_to_dask(pdf_elite_one)))

    # TC-DIRT-06: 维表国籍编码空间不一致
    pdf_user_60 = pd.DataFrame({'id': ['U100'], 'country_id': ['60']})
    pdf_orders_my = pd.DataFrame([{'period_num': 202604, 'country_id': 'MY', 'pv': "1000"}])
    _expect_fail(service.calculate_eab_bonus, "维表国籍不在国家主数据", **_base_args(df_user_info=pdf_user_60, ddf_orders=_to_dask(pdf_orders_my), ddf_elite_users=_to_dask(pdf_elite_one)))

    # TC-DIRT-07: Eager 熔断
    pdf_elite_zero = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "0"}])
    pdf_orders_abc = pd.DataFrame([{'period_num': 202604, 'country_id': 'MY', 'pv': "abc"}])
    _expect_fail(service.calculate_eab_bonus, "脏数据", **_base_args(ddf_elite_users=_to_dask(pdf_elite_zero), ddf_orders=_to_dask(pdf_orders_abc)))

    # TC-DIRT-09: 维表重复 ID
    pdf_user_dup = pd.DataFrame({'id': ['U100', 'U100'], 'country_id': ['MY', 'MY']})
    _expect_fail(service.calculate_eab_bonus, "存在重复 ID", **_base_args(df_user_info=pdf_user_dup, ddf_elite_users=_to_dask(pdf_elite_one)))

    # TC-DIRT-10: 订单国籍脏值（[修正] 补 np.nan 与 "null" 完整 token 覆盖）
    for bad_country, kw in [(None, "空值/非法ID"), (np.nan, "空值/非法ID"), ("", "空值/非法ID"), ("null", "空值/非法ID"), ("XX", "不在国家主数据中的国家")]:
        _expect_fail(service.calculate_eab_bonus, kw, **_base_args(ddf_orders=_to_dask(pd.DataFrame([{'period_num': 202604, 'country_id': bad_country, 'pv': "10000"}]))))

    # TC-DIRT-11: 未达标脏 ID 容错 vs 达标脏 ID 熔断
    pdf_elite_unq = pd.DataFrame([{'period_num': 202604, 'user_id': '', 'gpv': "500"}, {'period_num': 202604, 'user_id': 'U100', 'gpv': "1000"}])
    res_unq = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_unq)))
    assert len(res_unq['AR_CALC_BONUS_EAB_AUDIT'].compute()) > 0
    pdf_elite_q_bad = pd.DataFrame([{'period_num': 202604, 'user_id': '', 'gpv': "1000"}])
    _expect_fail(service.calculate_eab_bonus, "存在空值/非法ID", **_base_args(ddf_elite_users=_to_dask(pdf_elite_q_bad)))


def run_module5_structure_perf_part(service):
    # TC-STR-01 (SG 版本): 权威国籍覆盖 + 验证 Legacy 保留原始维表国籍而非大区国籍
    pdf_elite_sg = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000", 'country_id': 'US'}])
    pdf_orders_sg = pd.DataFrame([{'period_num': 202604, 'country_id': 'SG', 'pv': "10000"}])
    pdf_perf_sg = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': 1}])
    pdf_user_sg = pd.DataFrame({'id': ['U100'], 'country_id': ['SG']})
    res_str1 = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_sg), ddf_orders=_to_dask(pdf_orders_sg), ddf_user_perf=_to_dask(pdf_perf_sg), df_user_info=pdf_user_sg))
    leg1, aud1 = res_str1['AR_CALC_BONUS_EAB'].compute(), res_str1['AR_CALC_BONUS_EAB_AUDIT'].compute()
    assert leg1.iloc[0]['country_id'] == 'SG', "Legacy 未保留原始维表国籍"
    assert aud1.iloc[0]['country_id'] == 'SG', "Audit 未保留原始维表国籍"
    assert aud1.iloc[0]['region_country_id'] == 'MY', "Audit 未正确使用映射大区"

    # TC-STR-01b (MY 版本, [新增] 完全按规范文字: 评级表带 US, 维表为 MY, 无映射): 断言原始国籍 == MY
    pdf_elite_us2 = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000", 'country_id': 'US'}])
    pdf_orders_my2 = pd.DataFrame([{'period_num': 202604, 'country_id': 'MY', 'pv': "10000"}])
    pdf_perf_my2 = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': 1}])
    pdf_user_my2 = pd.DataFrame({'id': ['U100'], 'country_id': ['MY']})
    cfg_no_map = pd.DataFrame([{'config_name': 'eabRate', 'value': "10", 'type': 'bonus'}])
    res_str1b = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_us2), ddf_orders=_to_dask(pdf_orders_my2), ddf_user_perf=_to_dask(pdf_perf_my2), df_user_info=pdf_user_my2, df_config=cfg_no_map))
    leg1b, aud1b = res_str1b['AR_CALC_BONUS_EAB'].compute(), res_str1b['AR_CALC_BONUS_EAB_AUDIT'].compute()
    assert leg1b.iloc[0]['country_id'] == 'MY', "评级表 US 应被丢弃，使用维表 MY"
    assert aud1b.iloc[0]['country_id'] == 'MY'
    assert aud1b.iloc[0]['region_country_id'] == 'MY', "无映射时大区即原始国籍 MY"

    # TC-STR-02/03: 完整结构契约（达标/未达标 + 活跃/不活跃）
    pdf_elite_str2 = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000"}, {'period_num': 202604, 'user_id': 'U200', 'gpv': "1000"}, {'period_num': 202604, 'user_id': 'U300', 'gpv': "500"}])
    pdf_perf_str2 = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': 1}, {'period_num': 202604, 'user_id': 'U200', 'is_active': 0}, {'period_num': 202604, 'user_id': 'U300', 'is_active': 1}])
    pdf_user_str2 = pd.DataFrame({'id': ['U100', 'U200', 'U300'], 'country_id': ['MY', 'MY', 'MY']})
    res_str2 = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_str2), ddf_user_perf=_to_dask(pdf_perf_str2), df_user_info=pdf_user_str2))
    aud2, leg2 = res_str2['AR_CALC_BONUS_EAB_AUDIT'].compute(), res_str2['AR_CALC_BONUS_EAB'].compute()
    assert 'U300' not in aud2['user_id'].values and 'U300' not in leg2['user_id'].values, "未达标会员混入表内"
    aud_u100 = aud2[aud2['user_id'] == 'U100'].iloc[0]
    assert aud_u100['record_type'] == 'payable'
    assert Decimal(aud_u100['actual_bonus']) > 0
    aud_u200 = aud2[aud2['user_id'] == 'U200'].iloc[0]
    assert aud_u200['record_type'] == 'audit'
    assert Decimal(aud_u200['actual_bonus']) == Decimal("0.00")
    assert Decimal(aud_u200['calc_bonus']) > 0
    leg_u200 = leg2[leg2['user_id'] == 'U200'].iloc[0]
    assert leg_u200['is_active'] == 0
    assert Decimal(leg_u200['bonus_eab']) == Decimal(aud_u200['calc_bonus']), "Legacy 未保留不活跃者的理论奖金"

    # TC-STR-02b ([新增] 两大区·一有单一无单混合): MY 有 PV, TW 无 PV，各 1 名达标活跃会员
    pdf_elite_2reg = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000"}, {'period_num': 202604, 'user_id': 'U400', 'gpv': "1000"}])
    pdf_orders_2reg = pd.DataFrame([{'period_num': 202604, 'country_id': 'MY', 'pv': "10000"}])  # TW 无单
    pdf_perf_2reg = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': 1}, {'period_num': 202604, 'user_id': 'U400', 'is_active': 1}])
    pdf_user_2reg = pd.DataFrame({'id': ['U100', 'U400'], 'country_id': ['MY', 'TW']})
    master_2reg = pd.DataFrame({'country_id': ['MY', 'SG', 'TW']})
    res_2reg = service.calculate_eab_bonus(**_base_args(ddf_elite_users=_to_dask(pdf_elite_2reg), ddf_orders=_to_dask(pdf_orders_2reg), ddf_user_perf=_to_dask(pdf_perf_2reg), df_user_info=pdf_user_2reg, df_country_master=master_2reg))
    aud_2reg = res_2reg['AR_CALC_BONUS_EAB_AUDIT'].compute()
    leg_2reg = res_2reg['AR_CALC_BONUS_EAB'].compute()
    # MY 大区有 PV：U100 payable 1000.00
    u100_2reg = aud_2reg[aud_2reg['user_id'] == 'U100'].iloc[0]
    assert u100_2reg['region_country_id'] == 'MY'
    assert u100_2reg['record_type'] == 'payable'
    assert Decimal(u100_2reg['actual_bonus']) == Decimal("1000.00")
    # TW 大区无 PV：U400 calc=0.00 audit，且不在 Legacy
    u400_2reg = aud_2reg[aud_2reg['user_id'] == 'U400'].iloc[0]
    assert u400_2reg['region_country_id'] == 'TW'
    assert Decimal(u400_2reg['calc_bonus']) == Decimal("0.00")
    assert u400_2reg['record_type'] == 'audit'
    assert 'U400' not in leg_2reg['user_id'].values, "无 PV 大区达标者不应进入 Legacy"
    assert 'U100' in leg_2reg['user_id'].values

    # TC-STR-04
    pdf_elite_mis = pd.DataFrame([{'period_num': 202604, 'user_id': 'U999', 'gpv': "1000"}])
    _expect_fail(service.calculate_eab_bonus, "未匹配到国籍", **_base_args(ddf_elite_users=_to_dask(pdf_elite_mis)))

    # TC-STR-05: 确定性与主键占位
    res1 = service.calculate_eab_bonus(**_base_args())
    res2 = service.calculate_eab_bonus(**_base_args())
    leg_a, leg_b = res1['AR_CALC_BONUS_EAB'].compute(), res2['AR_CALC_BONUS_EAB'].compute()
    aud_a, aud_b = res1['AR_CALC_BONUS_EAB_AUDIT'].compute(), res2['AR_CALC_BONUS_EAB_AUDIT'].compute()
    assert (leg_a['id'] == "").all(), "Legacy 的 ID 未使用空串占位"
    pd.testing.assert_frame_equal(leg_a.sort_values(['period_num', 'user_id']).reset_index(drop=True), leg_b.sort_values(['period_num', 'user_id']).reset_index(drop=True))
    pd.testing.assert_frame_equal(aud_a.sort_values(['period_num', 'user_id']).reset_index(drop=True), aud_b.sort_values(['period_num', 'user_id']).reset_index(drop=True))

    # TC-STR-06: 活跃表缺记录默认不活跃
    pdf_perf_empty = pd.DataFrame(columns=['period_num', 'user_id', 'is_active'])
    res_emp = service.calculate_eab_bonus(**_base_args(ddf_user_perf=_to_dask(pdf_perf_empty)))
    aud_emp, leg_emp = res_emp['AR_CALC_BONUS_EAB_AUDIT'].compute(), res_emp['AR_CALC_BONUS_EAB'].compute()
    assert set(aud_emp['actual_bonus']) == {"0.00"}, "默认不活跃实际发放不为 0.00"
    assert set(aud_emp['record_type']) == {"audit"}, "默认不活跃类型不为 audit"
    assert set(leg_emp['is_active']) == {0}, "默认不活跃在 Legacy 中未标记为 0"

    # TC-PERF-01
    pdf_perf_no_period = pd.DataFrame([{'user_id': 'U100', 'is_active': 1}, {'user_id': 'U200', 'is_active': 1}])
    res_perf1 = service.calculate_eab_bonus(**_base_args(ddf_user_perf=_to_dask(pdf_perf_no_period)))
    assert set(res_perf1['AR_CALC_BONUS_EAB_AUDIT'].compute()['is_active']) == {1}

    # TC-PERF-02
    pdf_perf_period = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': 1}, {'period_num': 202604, 'user_id': 'U200', 'is_active': 1}, {'period_num': 202603, 'user_id': 'U100', 'is_active': 0}, {'period_num': 202603, 'user_id': 'U200', 'is_active': 0}])
    res_perf2 = service.calculate_eab_bonus(**_base_args(ddf_user_perf=_to_dask(pdf_perf_period)))
    assert set(res_perf2['AR_CALC_BONUS_EAB_AUDIT'].compute()['is_active']) == {1}

    # TC-PERF-03: 无周期列单用户多行
    pdf_perf_multi = pd.DataFrame([{'user_id': 'U100', 'is_active': 1}, {'user_id': 'U100', 'is_active': 0}])
    _expect_fail(service.calculate_eab_bonus, "单用户多行", **_base_args(ddf_user_perf=_to_dask(pdf_perf_multi)))

    # TC-PERF-04: 活跃枚举越界（[修正] 补 1.5 与 None，原仅 2）
    for bad_active in [2, 1.5, None]:
        pdf_perf_enum = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': bad_active}])
        _expect_fail(service.calculate_eab_bonus, "非法状态码", **_base_args(ddf_user_perf=_to_dask(pdf_perf_enum)))

    # TC-PART-01: 多分区空表安全（partition 0 空 + string gpv，回归空分区 BUG）
    ddf_elite_part = dd.concat(
        [_to_dask(pd.DataFrame(columns=['period_num', 'user_id', 'gpv'])) for _ in range(5)] +
        [_to_dask(pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000"}]))] +
        [_to_dask(pd.DataFrame(columns=['period_num', 'user_id', 'gpv'])) for _ in range(4)]
    )
    res_part = service.calculate_eab_bonus(**_base_args(ddf_elite_users=ddf_elite_part))
    assert len(res_part['AR_CALC_BONUS_EAB'].compute()) > 0, "多分区空表导致假阴性"


# =====================================================================
# 独立用例（[修正] TC-DIRT-05 / 08 拆成独立函数，互不阻断、定位清晰）
# =====================================================================

def run_tc_dirt_05(service):
    """TC-DIRT-05: 业务要求国家缺映射 -> 熔断（需 build_eab_service_for_prod）。service 参数仅占位。"""
    service_req = build_eab_service_for_prod({'SG'})
    cfg_missing_req = pd.DataFrame([{'config_name': 'eabRate', 'value': "10", 'type': 'bonus'}])
    _expect_fail(service_req.calculate_eab_bonus, "可合并国家缺少映射", **_base_args(df_config=cfg_missing_req))


def run_tc_dirt_08(service):
    """TC-DIRT-08: 不传 master 降级，数字 60 独立成区（[增强] 补 country/region/actual 断言）。"""
    pdf_elite_num = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'gpv': "1000"}])
    pdf_orders_num = pd.DataFrame([{'period_num': 202604, 'country_id': '60', 'pv': "1000"}])
    pdf_perf_num = pd.DataFrame([{'period_num': 202604, 'user_id': 'U100', 'is_active': 1}])
    pdf_user_num = pd.DataFrame({'id': ['U100'], 'country_id': ['60']})
    res_deg = service.calculate_eab_bonus(**_base_args(
        ddf_elite_users=_to_dask(pdf_elite_num), ddf_orders=_to_dask(pdf_orders_num),
        ddf_user_perf=_to_dask(pdf_perf_num), df_user_info=pdf_user_num, df_country_master=None
    ))
    aud_deg = res_deg['AR_CALC_BONUS_EAB_AUDIT'].compute()
    assert len(aud_deg) > 0, "主数据未安全降级"
    row = aud_deg.iloc[0]
    assert row['country_id'] == '60', "数字 60 应作为原始国籍保留"
    assert row['region_country_id'] == '60', "数字 60 应被当作独立大区（未被静默并区）"
    assert Decimal(row['actual_bonus']) == Decimal("100.00"), "1000*10%/1 应为 100.00"


# =====================================================================
# main: 测试运行器（[修正] 失败时 sys.exit(1)）
# =====================================================================

def main():
    # [修正] LocalCluster 启动包 try/except + processes=False，失败时降级到默认本地调度器，
    #        避免 CI 环境因 distributed 端口/权限/worker 策略等问题在进入测试前就退出。
    cluster = None
    client = None
    try:
        try:
            cluster = LocalCluster(n_workers=2, threads_per_worker=2, dashboard_address=None, processes=False)
            client = Client(cluster)
            print(f"Dask LocalCluster 启动成功: {client.scheduler.address}")
        except Exception as e:
            print(f"⚠ LocalCluster 启动失败，降级使用 Dask 默认本地调度器: {type(e).__name__}: {e}")

        service = EliteAchievementBonusService()
        tests = [
            ("Module 1", run_module1_historical_bugs),
            ("Module 2", run_module2_core_calc),
            ("Module 3", run_module3_config_mapping),
            ("Module 4", run_module4_fail_fast),
            ("Module 5", run_module5_structure_perf_part),
            ("TC-DIRT-05", run_tc_dirt_05),
            ("TC-DIRT-08", run_tc_dirt_08),
        ]
        failed = []
        for name, fn in tests:
            try:
                fn(service)
                print(f"✓ PASS  {name}")
            except AssertionError as e:
                print(f"✗ FAIL  {name}: {e}")
                failed.append((name, f"AssertionError: {e}"))
            except Exception as e:
                print(f"✗ ERROR {name}: {type(e).__name__}: {e}")
                failed.append((name, f"{type(e).__name__}: {e}"))

        print("\n" + "=" * 60)
        if failed:
            print(f"{len(failed)}/{len(tests)} 组用例失败:")
            for name, reason in failed:
                print(f"  - {name}: {reason}")
            sys.exit(1)
        else:
            print(f"全部 {len(tests)} 组用例通过 ✓")
    finally:
        if client is not None:
            client.close()
        if cluster is not None:
            cluster.close()


if __name__ == "__main__":
    main()
