# test_userstatsservice_elite_report.py
from UserStatsService import UserStatsService
from Model.User.UserStats import UserStats
from Model.User.UserLevel import ELITE, PRO_ELITE, SUPER_ELITE, NOTHING

# 初始化服务
svc = UserStatsService()

# -----------------------------
# 1. 清空 Redis
# -----------------------------
svc.clear_all_redis_data()

# -----------------------------
# 2. 初始化调试数据（SE 链）
# -----------------------------
svc.init_debug_data()

# -----------------------------
# 3. 定义测试用例
# -----------------------------
test_cases = [
    # (用户ID, 增加 BV, 预期 rank)
    ("3", 50, SUPER_ELITE),  # SE 已有下级贡献，越级晋升
    ("1", 0, PRO_ELITE),     # SE，GPV满足，直推下级少
    ("9", 0, ELITE),         # 普通下单，GPV足够升ELITE
    ("10", 0, PRO_ELITE),    # 下单贡献者越级给祖父级
    ("5", 0, SUPER_ELITE),   # 顶层 SE，不变
    ("2", 0, PRO_ELITE),     # SE，父级贡献调整
]

# -----------------------------
# 4. 执行测试并收集报告
# -----------------------------
report = []

for user_id, bv, expected_rank in test_cases:
    try:
        print(f"\n=== 测试用户 {user_id}, 增加 BV={bv} ===")
        svc.update_elite_performance(user_id=user_id, bv=bv)
        user = UserStats.get(user_id)
        actual_rank = user.rank
        passed = (actual_rank == expected_rank)
        report.append({
            "user_id": user_id,
            "expected_rank": expected_rank,
            "actual_rank": actual_rank,
            "is_elite": user.is_elite,
            "virtual_width": user.virtual_width,
            "highest_rank": user.highest_rank,
            "passed": passed,
            "error": None
        })
        print(f"用户 {user_id} 最终 rank={actual_rank}, highest_rank={user.highest_rank}, "
              f"is_elite={user.is_elite}, virtual_width={user.virtual_width}, "
              f"{'✅ 通过' if passed else '❌ 失败'}")
    except Exception as e:
        report.append({
            "user_id": user_id,
            "expected_rank": expected_rank,
            "actual_rank": None,
            "is_elite": None,
            "virtual_width": None,
            "highest_rank": None,
            "passed": False,
            "error": str(e)
        })
        print(f"❌ 用户 {user_id} 测试异常: {e}")

# -----------------------------
# 5. 汇总测试结果
# -----------------------------
total = len(report)
passed_count = sum(1 for r in report if r["passed"])
failed_count = total - passed_count

print("\n=== 测试报告 ===")
print("{:<6} {:<13} {:<13} {:<10} {:<14} {:<14} {:<8}".format(
    "用户ID", "预期Rank", "实际Rank", "is_elite", "virtual_width", "highest_rank", "状态"))
for r in report:
    status = "通过" if r["passed"] else "失败"
    if r["error"]:
        status += f" (异常: {r['error']})"
    print("{:<6} {:<13} {:<13} {:<10} {:<14} {:<14} {:<8}".format(
        r["user_id"],
        r["expected_rank"],
        r["actual_rank"] if r["actual_rank"] is not None else "-",
        str(r["is_elite"]) if r["is_elite"] is not None else "-",
        r["virtual_width"] if r["virtual_width"] is not None else "-",
        r["highest_rank"] if r["highest_rank"] is not None else "-",
        status
    ))

print(f"\n总测试用例数: {total}, 通过: {passed_count}, 失败: {failed_count}")