# test_bonus_pipeline_auto_check.py

import cudf
from User.UserStatsService import UserStatsService
from User.HonorLevelGPUService import HonorLevelGPUService
from User.HonorLevelHighGPUService import HonorLevelHighGPUService
from User.LeadershipBonusGPUService import LeadershipBonusGPUService

# -----------------------------
# 1. Redis 初始化数据
# -----------------------------
service = UserStatsService()
service.clear_all_redis_data()
service.init_debug_data()
print("✅ Redis 测试数据初始化完成")

# -----------------------------
# 2. 构建维表 / 配置 / 历史数据
# -----------------------------
def build_honor_levels() -> cudf.DataFrame:
    return cudf.DataFrame({
        "calc_id":  [10,20,30,40,50,60,70,80,90],
        "honor_lv":["Director","2S_Director","3S_Director",
                    "Diamond","2S_Diamond","3S_Diamond",
                    "Crown","2S_Crown","3S_Crown"]
    })

def build_users():
    user_ids = ["1","2","3","4","5","6","7","8","9","10","11","12","13"]
    return cudf.DataFrame({
        "user_id":[int(u) for u in user_ids],
        "user_name":[f"U{u}" for u in user_ids],
        "real_name":[f"用户{u}" for u in user_ids],
        "country_id":["MY"]*len(user_ids),
        "is_active":[1]*len(user_ids)
    })

def build_perf_month(period_num=12):
    return cudf.DataFrame({
        "period_num":[period_num],
        "country_id":["MY"],
        "pv_pcs":[200000.0]
    })

def build_config():
    return cudf.DataFrame({
        "config_name":[f"leadershipRate{i}" for i in [10,20,30,40,50,60,70,80,90]],
        "value":["4.5","4.5","4.5","3.6","3.6","3.6","1.8","1.8","1.8"],
        "type":["bonus"]*9
    })

def build_history_record():
    return cudf.DataFrame({
        "user_id":[5,5,4,3],
        "period_num":[10,11,11,11],
        "last_honor_calc_id":[80,80,70,60],
        "last_honor_lv":["2S_Crown","2S_Crown","Crown","3S_Diamond"]
    })

def build_user_highest():
    return cudf.DataFrame({
        "user_id":[1,2,3,4,5,6,7,8,9,10,11,12,13],
        "highest_honor_lv":["Director"]*13
    })

df_honor_levels   = build_honor_levels()
df_users          = build_users()
df_perf_month     = build_perf_month()
df_config         = build_config()
df_history_record = build_history_record()
df_user_highest   = build_user_highest()

# -----------------------------
# 3. HonorLevelGPUService 测试
# -----------------------------
honor_svc = HonorLevelGPUService(strict_sql_mode=True)
df_honor_snapshot, df_layer_records = honor_svc.recompute_all_gpu(df_honor_levels=df_honor_levels)

# 自动断言 Honor Snapshot
for idx, row in df_honor_snapshot.to_pandas().iterrows():
    uid = row["user_id"]
    assert 0 <= row["ori_honor_calc_id"] <= 90, f"用户{uid} ori_honor_calc_id异常"
    assert row["bonus_honor_calc_id"] <= row["ori_honor_calc_id"], f"用户{uid} bonus_honor_calc_id异常"
    assert row["last_honor_calc_id"] <= row["ori_honor_calc_id"], f"用户{uid} last_honor_calc_id异常"
print("✅ HonorLevelGPUService 自动检查通过")

# -----------------------------
# 4. HonorLevelHighGPUService 测试
# -----------------------------
high_svc = HonorLevelHighGPUService(strict_sql_mode=True, deduplicate_history=False)
df_honor_high, df_record_out = high_svc.compute_highest_honor_gpu(
    iv_period_num=12,
    df_last_honor=df_honor_snapshot,
    df_history_record=df_history_record,
    df_push_record=None,
    df_user_highest=df_user_highest,
    df_honor_levels=df_honor_levels
)

# 自动断言历史最高奖衔
for idx, row in df_honor_high.to_pandas().iterrows():
    uid = row["user_id"]
    assert row["highest_honor_calc_id"] <= 90, f"用户{uid} 历史最高奖衔异常"
print("✅ HonorLevelHighGPUService 自动检查通过")

# -----------------------------
# 5. LeadershipBonusGPUService 测试
# -----------------------------
lead_svc = LeadershipBonusGPUService()
results = lead_svc.compute_leadership_bonus(
    iv_period_num=12,
    iv_calc_month=12,
    df_users=df_users,
    df_honor_snapshot=df_honor_snapshot,
    df_perf_month=df_perf_month,
    df_honor_levels=df_honor_levels,
    df_config=df_config,
    df_honor_high=df_honor_high
)

df_bonus = results['df_bonus']

# 自动断言 LB_PV 和奖金
for idx, row in df_bonus.to_pandas().iterrows():
    uid = row["user_id"]
    assert row["lb_pv"] >= 0, f"用户{uid} LB_PV异常"
    assert row["lb_amount"] >= 0, f"用户{uid} 奖金异常"
print("✅ LeadershipBonusGPUService 自动检查通过")

print("🎉 所有自动校验通过！")