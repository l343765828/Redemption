"""
EAB 调用示例：如何调用 EliteAchievementBonusService.calculate_eab_bonus
运行： python eab_usage_example.py
"""
import pandas as pd
import dask.dataframe as dd
from EliteAchievementBonusService import (
    EliteAchievementBonusService,
    build_eab_service_for_prod,
    reject_float_before_dask,
)

# ===== 计算参数 =====
PERIOD = 202503      # 期数
CALC_MONTH = 3       # 计算月（1-12）

# ===== 1) ddf_elite_users（dask）：由 UserStats 组装 =====
# 关键：UserStats.period 必须 rename 成 period_num；不带 country_id；金额用 int/str，切勿 float
# 生产中 user_stats_pdf 来自 Redis 扫描 UserStats(当期)
user_stats_pdf = pd.DataFrame({
    "period":  [str(PERIOD)] * 4,            # UserStats.period (str)
    "user_id": ["U001", "U002", "U003", "U004"],
    "gpv":     [1500, 2000, 999, 1200],      # UserStats.gpv (int)；U003<1000 不达标
})
elite_pdf = user_stats_pdf.rename(columns={"period": "period_num"})[["period_num", "user_id", "gpv"]]
ddf_elite_users = dd.from_pandas(elite_pdf, npartitions=2)

# ===== 2) ddf_orders（dask）：period_num, country_id, pv =====
orders_pdf = pd.DataFrame({
    "period_num": [PERIOD] * 3,
    "country_id": ["MY", "SG", "TW"],
    "pv":         ["100000.00", "50000.00", "30000.00"],   # 字符串，无 float
})
ddf_orders = dd.from_pandas(orders_pdf, npartitions=2)

# ===== 3) ddf_user_perf（dask）：user_id, is_active（period_num 可选）=====
perf_pdf = pd.DataFrame({
    "user_id":   ["U001", "U002", "U003", "U004"],
    "is_active": [1, 1, 1, 0],               # U004 不活跃 -> 进审计、actual=0
})
ddf_user_perf = dd.from_pandas(perf_pdf, npartitions=1)

# ===== 4) df_config（pandas）：eabRate + Country* 映射 =====
df_config = pd.DataFrame(
    [("eabRate", "10", "bonus"),             # 比例 10%
     ("CountrySG", "MY", "bonus")],          # SG 并入 MY 大区
    columns=["config_name", "value", "type"],
)

# ===== 5) df_user_info（pandas）：id, country_id —— 权威国籍来源 =====
# 三边 country_id 必须同一编码空间（这里与 orders/config 都用 MY/SG/TW 代码）
df_user_info = pd.DataFrame({
    "id":         ["U001", "U002", "U003", "U004"],
    "country_id": ["MY", "SG", "MY", "TW"],
})

# ===== 6) df_country_master（pandas，可选，强烈建议生产传入）=====
df_country_master = pd.DataFrame({"country_id": ["MY", "SG", "TW"]})

# ===== （可选）进 dask 前的 float 预检 =====
reject_float_before_dask(elite_pdf, {"gpv"}, "ddf_elite_users")
reject_float_before_dask(orders_pdf, {"pv"}, "ddf_orders")

# ===== 7) 实例化并调用 =====
# 方式 A：直接构造（required_region_sources 指定哪些国家"必须"在配置里有映射）
service = EliteAchievementBonusService(required_region_sources={"SG"})
# 方式 B（生产推荐，required_region_sources 为空会直接报错）：
# service = build_eab_service_for_prod(required_region_sources={"SG"})

result = service.calculate_eab_bonus(
    period=PERIOD,
    calc_month=CALC_MONTH,
    ddf_elite_users=ddf_elite_users,
    ddf_orders=ddf_orders,
    ddf_user_perf=ddf_user_perf,
    df_config=df_config,
    df_user_info=df_user_info,
    df_country_master=df_country_master,     # 不传 = None（与 SuperElite 入参对齐）
)

# ===== 8) 消费输出：两张 dask 表 =====
legacy_ddf = result["AR_CALC_BONUS_EAB"]         # 旧表兼容（仅 bonus_eab>0）
audit_ddf = result["AR_CALC_BONUS_EAB_AUDIT"]    # 审计全量（calc/actual/region/record_type）

legacy_pdf = legacy_ddf.compute()                # 触发计算（落库前 .compute()）
audit_pdf = audit_ddf.compute()

print("===== AR_CALC_BONUS_EAB（旧表兼容）=====")
print(legacy_pdf.to_string(index=False))
print("\n===== AR_CALC_BONUS_EAB_AUDIT（审计）=====")
print(audit_pdf.to_string(index=False))

# ===== 9) 持久化（由你的持久化层负责，引擎不做）=====
# - 生成主键 id（legacy 的 id 现在是占位空串）
# - 按业务唯一键 UPSERT：(period_num, user_id)；record_type 不进键
# - 单期单事务覆盖
