"""
月度奖金结算 Pipeline (完整可运行版)

修复了 run_monthly_bonus_pipeline.py 的以下问题:
1. df_history_record / df_user_highest / df_users / df_perf_month / df_config 全部补全(原版未定义)
2. iv_period_num 改为顺序编号,与 HonorLevelHighGPUService 12 个月滚动窗口语义对齐
3. 完整打印 3 步之间的 DataFrame 流转,以及最终 5 张结果表

调用顺序(已确认正确):
    HonorLevelGPUService          ──┐
        ↓ df_honor_snapshot         │
    HonorLevelHighGPUService        │
        ↓ df_honor_high             │
    LeadershipBonusGPUService  ←────┘ (同时吸纳 snapshot 和 high)

前置条件:
- MySQL tb_user 已同步到 Delta
- 已执行 UserService.loadAllUser(),Dask 上有 graph_actor 数据集
- 已执行(改造后的) UserStatsService.init_debug_data(),Redis 里有 user_stats
"""

import cudf

from User.HonorLevelGPUService import HonorLevelGPUService
from User.HonorLevelHighGPUService import HonorLevelHighGPUService
from User.LeadershipBonusGPUService import LeadershipBonusGPUService


# ======================================================================
# 维表/外部表 mock(生产中应来自各自数据源)
# ======================================================================

def build_honor_levels() -> cudf.DataFrame:
    """AR_HONOR_LEVEL 维表,calc_id ↔ 奖衔名称。三个服务都要用。"""
    return cudf.DataFrame({
        "calc_id":  [10, 20, 30, 40, 50, 60, 70, 80, 90],
        "honor_lv": ["Director", "2S_Director", "3S_Director",
                     "Diamond",  "2S_Diamond",  "3S_Diamond",
                     "Crown",    "2S_Crown",    "3S_Crown"],
    })


def build_users(user_ids: list) -> cudf.DataFrame:
    """
    AR_USER 表,Leadership 需要 user_id / country_id / is_active(还有 user_name / real_name 用于溯源)。
    user_id 必须是 int64,与 HonorLevelGPUService 从 Redis 读出来的类型对齐。
    """
    return cudf.DataFrame({
        "user_id":   [int(u) for u in user_ids],
        "user_name": [f"U{u}" for u in user_ids],
        "real_name": [f"用户{u}" for u in user_ids],
        "country_id": ["MY"] * len(user_ids),
        "is_active":  [1] * len(user_ids),
    })


def build_perf_month(period_num: int) -> cudf.DataFrame:
    """AR_USER_PERF,各国当期总 PV。计算 honor_bonus = total_pv * honor_rate。"""
    return cudf.DataFrame({
        "period_num": [period_num],
        "country_id": ["MY"],
        "pv_pcs":     [200000.0],   # 当月 MY 国家总业绩
    })


def build_config() -> cudf.DataFrame:
    """
    AR_CONFIG,只取 type='bonus' 的两类:
    - leadershipRate{calc_id}: 各代奖金费率(%)
    - Country{XX} = YY: 大区映射(本例无大区,故只放费率)
    """
    return cudf.DataFrame({
        "config_name": [
            "leadershipRate10", "leadershipRate20", "leadershipRate30",
            "leadershipRate40", "leadershipRate50", "leadershipRate60",
            "leadershipRate70", "leadershipRate80", "leadershipRate90",
        ],
        "value": ["4.5", "4.5", "4.5",
                  "3.6", "3.6", "3.6",
                  "1.8", "1.8", "1.8"],
        "type":  ["bonus"] * 9,
    })


def build_history_record(user_ids: list) -> cudf.DataFrame:
    """
    AR_CALC_LV_HONOR_RECORD,过往周期奖衔记录。
    例:让用户 5 在过去几期就达到过 80 级 2 次,以便 HighService 触发 80 级历史最高。
    """
    return cudf.DataFrame({
        "user_id":            [5,  5,  4,  3],
        "period_num":         [10, 11, 11, 11],
        "last_honor_calc_id": [80, 80, 70, 60],
        "last_honor_lv":      ["2S_Crown", "2S_Crown", "Crown", "3S_Diamond"],
    })


def build_user_highest(user_ids: list) -> cudf.DataFrame:
    """
    AR_USER 中的 highest_honor_lv 静态快照。
    给每个用户一个初始历史最高,HighService 会基于当期 + 历史滚动判定决定要不要往上推。
    """
    return cudf.DataFrame({
        "user_id":          [int(u) for u in user_ids],
        "highest_honor_lv": ["Director"] * len(user_ids),
    })


# ======================================================================
# 主管道
# ======================================================================

def run_pipeline(iv_period_num: int = 12, iv_calc_month: int = 12):
    """
    iv_period_num 用顺序编号,不要用 YYYYMM,否则 HighService 内的 12 月滚动窗口会错位。
    """
    print("=" * 70)
    print(f"月度奖金结算 Pipeline 启动  period_num={iv_period_num}  month={iv_calc_month}")
    print("=" * 70)

    # 取 tb_user.sql 中所有用户
    user_ids = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]

    df_honor_levels   = build_honor_levels()
    df_users          = build_users(user_ids)
    df_perf_month     = build_perf_month(iv_period_num)
    df_config         = build_config()
    df_history_record = build_history_record(user_ids)
    df_user_highest   = build_user_highest(user_ids)

    # ----------------------------------------------------------------
    # Step 1: HonorLevelGPUService
    #   内部自动从 Redis 读 UserStats,从 Dask graph_actor 读 edges
    # ----------------------------------------------------------------
    print("\n" + "-" * 70)
    print("[Step 1] HonorLevelGPUService.recompute_all_gpu()")
    print("-" * 70)
    honor_svc = HonorLevelGPUService(strict_sql_mode=True)
    df_honor_snapshot, df_layer_records = honor_svc.recompute_all_gpu(
        df_honor_levels=df_honor_levels,
    )
    print(f"✅ df_honor_snapshot: {len(df_honor_snapshot)} 行")
    print(df_honor_snapshot.to_pandas().to_string(index=False))
    print(f"\n✅ df_layer_records: {len(df_layer_records)} 行")
    print(df_layer_records.to_pandas().to_string(index=False))

    # ----------------------------------------------------------------
    # Step 2: HonorLevelHighGPUService
    #   df_last_honor 直接用 Step1 的 df_honor_snapshot
    #   注意 user_id 类型要一致(都是 int64)
    # ----------------------------------------------------------------
    print("\n" + "-" * 70)
    print("[Step 2] HonorLevelHighGPUService.compute_highest_honor_gpu()")
    print("-" * 70)
    high_svc = HonorLevelHighGPUService(
        strict_sql_mode=True,
        deduplicate_history=False,
    )
    df_honor_high, df_record_out = high_svc.compute_highest_honor_gpu(
        iv_period_num=iv_period_num,
        df_last_honor=df_honor_snapshot,        # ← 来自 Step1
        df_history_record=df_history_record,
        df_push_record=None,
        df_user_highest=df_user_highest,
        df_honor_levels=df_honor_levels,
    )
    print(f"✅ df_honor_high: {len(df_honor_high)} 行")
    print(df_honor_high.to_pandas().to_string(index=False))
    print(f"\n✅ df_record_out: {len(df_record_out)} 行")
    print(df_record_out.to_pandas().to_string(index=False))

    # ----------------------------------------------------------------
    # Step 3: LeadershipBonusGPUService
    #   同时吸纳 Step1 的 snapshot 和 Step2 的 high
    # ----------------------------------------------------------------
    print("\n" + "-" * 70)
    print("[Step 3] LeadershipBonusGPUService.compute_leadership_bonus()")
    print("-" * 70)
    bonus_svc = LeadershipBonusGPUService(strict_sql_mode=True)
    bonus_results = bonus_svc.compute_leadership_bonus(
        iv_period_num=iv_period_num,
        iv_calc_month=iv_calc_month,
        df_users=df_users,
        df_honor_snapshot=df_honor_snapshot,    # ← 来自 Step1
        df_perf_month=df_perf_month,
        df_honor_levels=df_honor_levels,
        df_config=df_config,
        df_honor_high=df_honor_high,            # ← 来自 Step2 (可选)
    )

    print("\n" + "=" * 70)
    print("Step 3 返回结果(共 5 张表)")
    print("=" * 70)
    for table_name, df in bonus_results.items():
        print(f"\n▼ {table_name}  ({len(df)} 行)")
        print("-" * 70)
        if len(df) > 0:
            print(df.to_pandas().to_string(index=False))
        else:
            print("  (empty)")

    return {
        "honor_snapshot": df_honor_snapshot,
        "layer_records":  df_layer_records,
        "honor_high":     df_honor_high,
        "record_out":     df_record_out,
        "bonus":          bonus_results,
    }


if __name__ == "__main__":
    results = run_pipeline(iv_period_num=12, iv_calc_month=12)

    # 主用户拿到全球总奖金的快速查询
    print("\n" + "=" * 70)
    print("最终全球奖金汇总 (AR_CALC_BONUS_LB):")
    print("=" * 70)
    df_global = results["bonus"]["AR_CALC_BONUS_LB"]
    if len(df_global) > 0:
        print(df_global.to_pandas().to_string(index=False))
    else:
        print("(没有用户拿到奖金,检查 init_debug_data 中的 SE 链是否正确)")
