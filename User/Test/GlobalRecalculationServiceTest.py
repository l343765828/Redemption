"""
GlobalRecalculationService 单月结算测试用例集
（已对齐 settle_period / 按期隔离 / 荣誉表外置，并按评审意见补强清库与荣誉断言）

放置位置：和 GlobalRecalculationService.py 同目录（User/），保持包导入路径一致。

执行方式：
    python3 -m User.GlobalRecalculationServiceTest

前置条件：
    1. Dask 集群已启动并监听 tcp://127.0.0.1:8786
    2. graph_actor 已通过 GraphService.run() 注入到 client.datasets["graph_actor"]，
       且 ddf_users 严格对应 tb_user.txt 全部 13 条边（业务用户假定为 1..13）
    3. Redis 可连接
    4. graph_actor.validate_graph_integrity() 可正常通过（settle_period 内部会强制校验）

与旧版测试的关键差异（随服务重构同步调整）：
    - 入口由 orchestrate_global_recalculation(reset_highest_rank=..., write_zero_nodes=...)
      改为 settle_period(period, *, write_zero_nodes=...)；不再有 reset_highest_rank。
    - 所有 UserStats 物理隔离：pk = f"{period}:{uid}"，注入/读取/断言全部带 period。
    - highest_rank 不再写在 UserStats 上，改由独立模型 UserPeriodHighestRank 维护，
      pk = f"{period}:{uid}"；断言 highest_rank / 荣誉字段一律从该表读取。
    - highest_rank 语义为「每月末快照取最高 + 跨月只升不降」：
      本期 highest = max(上一期 highest, 本期评定 rank)。月内不维护高水位。
    - 用例 2.2 因此改写为「两期结算」来验证跨月高水位保持。

清库策略（按评审意见加固）：
    - 清理覆盖 BASE_PREV / PREV / TEST 三期（2.2 结算 PREV 时会读 BASE_PREV，必须先清，
      否则上一期基线会被更早历史荣誉污染）。
    - 用户覆盖全图 1..13，而不是只清断言用户（settle 会保留 pv，残留非零 pv 会污染祖先 GPV）。
    - 用模型自带 all_pks() 做前缀安全的全量兜底（裸 scan "UserStats:*" 因 global_key_prefix
      = "user_stats" 很可能扫不到真实 key，不能依赖）。

断言规约：
    - qualified_legs 一律走集合比较：set(stats.qualified_legs) == {...}
    - UserStats 字段：gpv / rank / legs / virtual_width / is_elite / contrib
    - 荣誉字段：current_rank / prev_period / prev_highest_rank / highest_rank /
      settled_run_id / settled_at 取自 UserPeriodHighestRank
"""
import logging
from typing import Optional, Set

from dask.distributed import Client
from redis_om import NotFoundError

import Model.User.UserLevel as UserLevel
from Model.User.UserStats import UserStats
from Model.User.UserPeriodHighestRank import UserPeriodHighestRank
from Common.PeriodResolver import PeriodSnapshot
from User.GlobalRecalculationService import GlobalRecalculationService
from User.UserStatsService import SCHEDULE_ADDRESS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [GRSTest] %(message)s",
)
logger = logging.getLogger(__name__)


# =====================================================================
# 常量：测试期数与图用户全集
# =====================================================================
# 单期用例统一用 TEST_PERIOD；跨期用例（2.2）用 PREV_PERIOD 作为上一期。
# 必须满足 _get_previous_period(TEST_PERIOD) == PREV_PERIOD
#         _get_previous_period(PREV_PERIOD) == BASE_PREV_PERIOD
BASE_PREV_PERIOD = "202603"   # 2.2 结算 PREV_PERIOD 时服务会读到的上上期，必须一并清理
PREV_PERIOD = "202604"
TEST_PERIOD = "202605"

CANDIDATE_PERIODS = (BASE_PREV_PERIOD, PREV_PERIOD, TEST_PERIOD)

# tb_user.txt 全部业务用户（13 条边 -> 1..13）。清库覆盖全图，而非只断言用户。
ALL_GRAPH_USERS = [str(i) for i in range(1, 14)]


# =====================================================================
# 辅助
# =====================================================================
def _clear_all_redis() -> None:
    """
    全量清库：清空两个模型在所有候选期数下的记录，并清掉全局锁与按期状态键。

    三层保险，互为兜底：
      1. all_pks()：模型自己算 key 前缀，前缀安全且跨所有期数全清（最彻底）。
      2. 全图用户 × 候选期数精确 delete：保证断言相关数据一定被清，不依赖 all_pks。
      3. 裸 key（lock / status）由本服务用 redis_conn.set 写入，前缀可控，scan 可靠。
    """
    redis_conn = UserStats.db()

    # 1. all_pks 全量兜底（前缀安全）
    for model in (UserStats, UserPeriodHighestRank):
        try:
            for pk in list(model.all_pks()):
                try:
                    model.delete(pk)
                except Exception:
                    pass
        except Exception:
            # 某些 redis_om 版本无 all_pks，忽略，靠第 2 层精确删除
            pass

    # 2. 全图用户 × 候选期数精确删除（确定性保证）
    for period in CANDIDATE_PERIODS:
        for uid in ALL_GRAPH_USERS:
            for model in (UserStats, UserPeriodHighestRank):
                try:
                    model.delete(f"{period}:{uid}")
                except Exception:
                    pass

    # 3. 全局锁 + 所有按期状态键（裸 key，前缀可控）
    try:
        redis_conn.delete(GlobalRecalculationService.GLOBAL_RECALC_LOCK_KEY)
    except Exception:
        pass
    try:
        for key in redis_conn.scan_iter("system:global_recalc_status:*"):
            redis_conn.delete(key)
    except Exception:
        pass

    logger.info("Redis 全量清理完成：periods=%s users=%s", list(CANDIDATE_PERIODS), ALL_GRAPH_USERS)


def _inject_pv(period: str, user_id: str, pv: int) -> None:
    """
    写入某期某用户的基础 PV，派生状态全部置零。
    settle_period 会在结算时基于 PV 完整重建派生状态，这里只造「基础 PV 快照」。

    注意：
        - pk 必须带 period 前缀做物理隔离。
        - 不再写 highest_rank：UserStats.highest_rank 已弃用，服务不读不写。
    """
    UserStats(
        pk=f"{period}:{user_id}",
        period=period,
        id=user_id,            # 纯业务 id，保持干净不污染拓扑
        user_id=user_id,
        pv=pv,
        gpv=pv,
        contrib=0,
        is_elite=False,
        virtual_width=0,
        rank=UserLevel.NOTHING,
        qualified_legs=set(),
    ).save()


def _run(period: str, *, write_zero_nodes: bool = True) -> None:
    """使用显式 AR_PERIOD 测试快照触发单期结算。"""
    snapshots = {
        BASE_PREV_PERIOD: PeriodSnapshot(
            period_num=202603, calc_year=2026, calc_month=3,
            first_period_num=202603, previous_period_num=None,
            source_checksum="global-recalc-test-202603",
        ),
        PREV_PERIOD: PeriodSnapshot(
            period_num=202604, calc_year=2026, calc_month=4,
            first_period_num=202603, previous_period_num=202603,
            source_checksum="global-recalc-test-202604",
        ),
        TEST_PERIOD: PeriodSnapshot(
            period_num=202605, calc_year=2026, calc_month=5,
            first_period_num=202603, previous_period_num=202604,
            source_checksum="global-recalc-test-202605",
        ),
    }
    svc = GlobalRecalculationService()
    svc.settle_period(
        period=period,
        period_snapshot=snapshots[period],
        write_zero_nodes=write_zero_nodes,
    )


def _get_stats(period: str, user_id: str) -> UserStats:
    """读取某期 UserStats，并把 qualified_legs 归一化为 set。"""
    s = UserStats.get(f"{period}:{user_id}")
    if s.qualified_legs is None:
        s.qualified_legs = set()
    elif not isinstance(s.qualified_legs, set):
        s.qualified_legs = set(s.qualified_legs)
    return s


def _get_highest_rank(period: str, user_id: str) -> Optional[int]:
    """从权威荣誉表读取某期 highest_rank；不存在返回 None。"""
    try:
        rec = UserPeriodHighestRank.get(f"{period}:{user_id}")
    except NotFoundError:
        return None
    return int(rec.highest_rank or 0)


def _assert_user(
    period: str,
    user_id: str,
    *,
    gpv: Optional[int] = None,
    qualified_legs: Optional[Set[str]] = None,
    virtual_width: Optional[int] = None,
    rank: Optional[int] = None,
    is_elite: Optional[bool] = None,
    contrib: Optional[int] = None,
    highest_rank: Optional[int] = None,
) -> None:
    """
    逐字段断言 UserStats（+ 便捷地顺带校验 highest_rank）。
    gpv/rank/legs/virtual_width/is_elite/contrib 取自 UserStats；
    highest_rank 取自 UserPeriodHighestRank。
    """
    try:
        s = _get_stats(period, user_id)
    except NotFoundError:
        raise AssertionError(
            f"[{period}] User {user_id} 不存在于 UserStats（write_zero_nodes=True 时不应缺失）"
        )

    fails = []
    if gpv is not None and (s.gpv or 0) != gpv:
        fails.append(f"gpv expected={gpv} actual={s.gpv}")
    if qualified_legs is not None and set(s.qualified_legs) != qualified_legs:
        fails.append(
            f"qualified_legs expected={qualified_legs} actual={set(s.qualified_legs)}"
        )
    if virtual_width is not None and (s.virtual_width or 0) != virtual_width:
        fails.append(f"virtual_width expected={virtual_width} actual={s.virtual_width}")
    if rank is not None and (s.rank or 0) != rank:
        fails.append(f"rank expected={rank} actual={s.rank}")
    if is_elite is not None and bool(s.is_elite) != is_elite:
        fails.append(f"is_elite expected={is_elite} actual={s.is_elite}")
    if contrib is not None and (s.contrib or 0) != contrib:
        fails.append(f"contrib expected={contrib} actual={s.contrib}")
    if highest_rank is not None:
        actual_highest = _get_highest_rank(period, user_id)
        if actual_highest is None:
            fails.append(
                f"highest_rank expected={highest_rank} actual=<UserPeriodHighestRank 缺失>"
            )
        elif actual_highest != highest_rank:
            fails.append(f"highest_rank expected={highest_rank} actual={actual_highest}")

    if fails:
        raise AssertionError(f"[{period}] User {user_id} 断言失败:\n  " + "\n  ".join(fails))

    logger.info("  ✓ [%s] User %s (stats) 通过", period, user_id)


def _assert_honor(
    period: str,
    user_id: str,
    *,
    current_rank: Optional[int] = None,
    prev_period: Optional[str] = None,
    prev_highest_rank: Optional[int] = None,
    highest_rank: Optional[int] = None,
    require_audit: bool = True,
) -> None:
    """
    对 UserPeriodHighestRank 做完整字段断言（覆盖 highest_rank 之外的字段）。
    require_audit=True 时额外校验 settled_run_id / settled_at 已写入。
    """
    try:
        rec = UserPeriodHighestRank.get(f"{period}:{user_id}")
    except NotFoundError:
        raise AssertionError(f"[{period}] User {user_id} 缺少 UserPeriodHighestRank 记录")

    fails = []
    if current_rank is not None and int(rec.current_rank or 0) != current_rank:
        fails.append(f"current_rank expected={current_rank} actual={rec.current_rank}")
    if prev_period is not None and getattr(rec, "prev_period", None) != prev_period:
        fails.append(f"prev_period expected={prev_period} actual={getattr(rec, 'prev_period', None)}")
    if prev_highest_rank is not None and int(getattr(rec, "prev_highest_rank", 0) or 0) != prev_highest_rank:
        fails.append(
            f"prev_highest_rank expected={prev_highest_rank} "
            f"actual={getattr(rec, 'prev_highest_rank', None)}"
        )
    if highest_rank is not None and int(rec.highest_rank or 0) != highest_rank:
        fails.append(f"highest_rank expected={highest_rank} actual={rec.highest_rank}")

    if require_audit:
        if not getattr(rec, "settled_run_id", None):
            fails.append("settled_run_id 为空（模型缺字段或服务未写入）")
        if not int(getattr(rec, "settled_at", 0) or 0):
            fails.append("settled_at 为空（模型缺字段或服务未写入）")

    if fails:
        raise AssertionError(f"[{period}] Honor {user_id} 断言失败:\n  " + "\n  ".join(fails))

    logger.info("  ✓ [%s] User %s (honor) 通过", period, user_id)


# =====================================================================
# 用例 1.1：基础精英 Elite 晋级与上级截断
# =====================================================================
def test_case_1_1():
    print("\n" + "=" * 70)
    print("用例 1.1：基础精英 Elite 晋级与上级截断")
    print("=" * 70)

    _clear_all_redis()
    _inject_pv(TEST_PERIOD, "13", 1000)
    _run(TEST_PERIOD)

    # 触发节点：User 13 自身达标 Elite，向上贡献截断为 0
    _assert_user(TEST_PERIOD, "13", gpv=1000, qualified_legs=set(), virtual_width=0,
                 rank=UserLevel.ELITE, is_elite=True, contrib=0,
                 highest_rank=UserLevel.ELITE)

    # User 1 不接收业绩数字，只接收结构线
    _assert_user(TEST_PERIOD, "1", gpv=0, qualified_legs={"13"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=0,
                 highest_rank=UserLevel.NOTHING)

    # 全链路结构穿透：User 3 -> 4 -> 5
    _assert_user(TEST_PERIOD, "3", gpv=0, qualified_legs={"1"},
                 rank=UserLevel.NOTHING, contrib=0)
    _assert_user(TEST_PERIOD, "4", gpv=0, qualified_legs={"3"},
                 rank=UserLevel.NOTHING, contrib=0)
    _assert_user(TEST_PERIOD, "5", gpv=0, qualified_legs={"4"},
                 rank=UserLevel.NOTHING, contrib=0)

    print("[PASS] 用例 1.1")


# =====================================================================
# 用例 1.2：未达标期的临时贡献传导
# =====================================================================
def test_case_1_2():
    print("\n" + "=" * 70)
    print("用例 1.2：未达标期的临时贡献传导")
    print("=" * 70)

    _clear_all_redis()
    _inject_pv(TEST_PERIOD, "9", 800)
    _run(TEST_PERIOD)

    # User 9 未达标，800 作为 contrib 100% 向上层层传导
    _assert_user(TEST_PERIOD, "9", gpv=800, qualified_legs=set(), virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=800,
                 highest_rank=UserLevel.NOTHING)

    # 全链路 800 不被截断（没有任何 Elite 拦截）
    _assert_user(TEST_PERIOD, "1", gpv=800, qualified_legs=set(),
                 rank=UserLevel.NOTHING, contrib=800)
    _assert_user(TEST_PERIOD, "3", gpv=800, qualified_legs=set(),
                 rank=UserLevel.NOTHING, contrib=800)
    _assert_user(TEST_PERIOD, "4", gpv=800, qualified_legs=set(),
                 rank=UserLevel.NOTHING, contrib=800)
    _assert_user(TEST_PERIOD, "5", gpv=800, qualified_legs=set(),
                 rank=UserLevel.NOTHING, contrib=800)

    print("[PASS] 用例 1.2")


# =====================================================================
# 用例 1.3：高业绩触发虚拟宽度机制
# =====================================================================
def test_case_1_3():
    print("\n" + "=" * 70)
    print("用例 1.3：高业绩触发虚拟宽度机制")
    print("=" * 70)

    _clear_all_redis()
    _inject_pv(TEST_PERIOD, "10", 2000)
    _run(TEST_PERIOD)

    # User 10：gpv=2000 -> virtual_width = 2000 // 1000 = 2
    # 自身 Elite + total_width = 0 + 2 = 2 >= 1 -> 命中 Pro Elite 路径 A
    _assert_user(TEST_PERIOD, "10", gpv=2000, qualified_legs=set(), virtual_width=2,
                 rank=UserLevel.PRO_ELITE, is_elite=True, contrib=0,
                 highest_rank=UserLevel.PRO_ELITE)

    # User 2：只接收结构线
    _assert_user(TEST_PERIOD, "2", gpv=0, qualified_legs={"10"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=0,
                 highest_rank=UserLevel.NOTHING)

    # 结构穿透：2 -> 3 -> 4 -> 5
    _assert_user(TEST_PERIOD, "3", gpv=0, qualified_legs={"2"},
                 rank=UserLevel.NOTHING, contrib=0)
    _assert_user(TEST_PERIOD, "4", gpv=0, qualified_legs={"3"},
                 rank=UserLevel.NOTHING, contrib=0)
    _assert_user(TEST_PERIOD, "5", gpv=0, qualified_legs={"4"},
                 rank=UserLevel.NOTHING, contrib=0)

    print("[PASS] 用例 1.3")


# =====================================================================
# 用例 2.1：复杂网体合并传导与无业绩晋升路径 B
# =====================================================================
def test_case_2_1():
    print("\n" + "=" * 70)
    print("用例 2.1：复杂网体合并传导与无业绩晋升路径 B")
    print("=" * 70)

    _clear_all_redis()
    _inject_pv(TEST_PERIOD, "13", 1000)
    _inject_pv(TEST_PERIOD, "9", 800)
    _inject_pv(TEST_PERIOD, "10", 2000)
    _run(TEST_PERIOD)

    # ---- 触发层 ----
    _assert_user(TEST_PERIOD, "13", gpv=1000, qualified_legs=set(), virtual_width=0,
                 rank=UserLevel.ELITE, is_elite=True, contrib=0,
                 highest_rank=UserLevel.ELITE)
    _assert_user(TEST_PERIOD, "9", gpv=800, qualified_legs=set(), virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=800,
                 highest_rank=UserLevel.NOTHING)
    _assert_user(TEST_PERIOD, "10", gpv=2000, qualified_legs=set(), virtual_width=2,
                 rank=UserLevel.PRO_ELITE, is_elite=True, contrib=0,
                 highest_rank=UserLevel.PRO_ELITE)

    # ---- 中间层 ----
    # User 1：收 9 的 800 业绩 + 13 的结构线
    _assert_user(TEST_PERIOD, "1", gpv=800, qualified_legs={"13"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=800,
                 highest_rank=UserLevel.NOTHING)
    # User 2：只收 10 的结构线，10 已 Elite 不传业绩
    _assert_user(TEST_PERIOD, "2", gpv=0, qualified_legs={"10"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=0,
                 highest_rank=UserLevel.NOTHING)

    # ---- 关键节点 User 3：无业绩晋升路径 B ----
    # gpv=800（来自 9 -> 1 -> 3 的 contrib 链）
    # legs={"1","2"}，total_width = 2 + 0 = 2，非自身 Elite + legs>=2 -> Pro Elite
    _assert_user(TEST_PERIOD, "3", gpv=800, qualified_legs={"1", "2"}, virtual_width=0,
                 rank=UserLevel.PRO_ELITE, is_elite=False, contrib=800,
                 highest_rank=UserLevel.PRO_ELITE)

    # ---- 上层穿透 ----
    _assert_user(TEST_PERIOD, "4", gpv=800, qualified_legs={"3"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=800,
                 highest_rank=UserLevel.NOTHING)
    _assert_user(TEST_PERIOD, "5", gpv=800, qualified_legs={"4"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=800,
                 highest_rank=UserLevel.NOTHING)

    # ---- 荣誉表完整字段校验（单期首结算：prev 查不到 -> prev_highest=0）----
    _assert_honor(TEST_PERIOD, "3",
                  current_rank=UserLevel.PRO_ELITE,
                  prev_period=PREV_PERIOD,
                  prev_highest_rank=UserLevel.NOTHING,
                  highest_rank=UserLevel.PRO_ELITE)
    _assert_honor(TEST_PERIOD, "13",
                  current_rank=UserLevel.ELITE,
                  prev_period=PREV_PERIOD,
                  prev_highest_rank=UserLevel.NOTHING,
                  highest_rank=UserLevel.ELITE)

    print("[PASS] 用例 2.1")


# =====================================================================
# 用例 2.2：跨月高水位维持与业绩回滚（两期结算）
#
# 新架构 highest_rank 是跨月维护的，因此：
#   先结算上一期（PREV_PERIOD，10 升 PRO_ELITE 建立基线），
#   再结算本期（TEST_PERIOD，10 退货归零导致当期降级），
#   验证本期 highest_rank = max(上期 highest, 本期 rank) 仍保持高水位。
#
# 致命约束：
#   - 起始必须连 BASE_PREV_PERIOD(202603) 一起清，否则结算 PREV 时会读到旧荣誉污染基线。
#   - PREV 结算后到 TEST 结算前，绝不能再清 UserPeriodHighestRank。
# =====================================================================
def test_case_2_2():
    print("\n" + "=" * 70)
    print("用例 2.2：跨月高水位维持与业绩回滚（两期结算）")
    print("=" * 70)

    # ---- Step 0：全量清库（含 BASE_PREV 202603，避免基线污染）----
    _clear_all_redis()

    # ---- Step 1：结算上一期，建立高水位基线（数据同 2.1）----
    _inject_pv(PREV_PERIOD, "13", 1000)
    _inject_pv(PREV_PERIOD, "9", 800)
    _inject_pv(PREV_PERIOD, "10", 2000)
    _run(PREV_PERIOD)

    # 基线确认：上期 10 = PRO_ELITE，3 = PRO_ELITE（路径 B）
    _assert_user(PREV_PERIOD, "10", gpv=2000, rank=UserLevel.PRO_ELITE,
                 is_elite=True, highest_rank=UserLevel.PRO_ELITE)
    _assert_user(PREV_PERIOD, "3", gpv=800, qualified_legs={"1", "2"},
                 rank=UserLevel.PRO_ELITE, is_elite=False,
                 highest_rank=UserLevel.PRO_ELITE)
    # 上一期同样是首结算：prev(202603) 查不到 -> prev_highest=0
    _assert_honor(PREV_PERIOD, "10",
                  current_rank=UserLevel.PRO_ELITE,
                  prev_period=BASE_PREV_PERIOD,
                  prev_highest_rank=UserLevel.NOTHING,
                  highest_rank=UserLevel.PRO_ELITE)

    # ---- Step 2：结算本期，User 10 大单退货 -> 当期 gpv=0 ----
    # 注意：不清 UserPeriodHighestRank，让本期能读到上期高水位
    _inject_pv(TEST_PERIOD, "13", 1000)
    _inject_pv(TEST_PERIOD, "9", 800)
    _inject_pv(TEST_PERIOD, "10", 0)
    _run(TEST_PERIOD)

    # ---- User 10：当期降级 NOTHING，但 highest_rank 跨月保持 PRO_ELITE ----
    _assert_user(TEST_PERIOD, "10", gpv=0, qualified_legs=set(), virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=0,
                 highest_rank=UserLevel.PRO_ELITE)
    _assert_honor(TEST_PERIOD, "10",
                  current_rank=UserLevel.NOTHING,
                  prev_period=PREV_PERIOD,
                  prev_highest_rank=UserLevel.PRO_ELITE,
                  highest_rank=UserLevel.PRO_ELITE)

    # ---- User 2：失去 User 10 这条合格线（10 当期 rank=0 且无下级 Elite）----
    _assert_user(TEST_PERIOD, "2", gpv=0, qualified_legs=set(), virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=0,
                 highest_rank=UserLevel.NOTHING)

    # ---- User 3：只剩 {"1"} 一条合格线（2 不再合格），当期降级 NOTHING，
    #              但 highest_rank 跨月保持 PRO_ELITE ----
    _assert_user(TEST_PERIOD, "3", gpv=800, qualified_legs={"1"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=800,
                 highest_rank=UserLevel.PRO_ELITE)
    _assert_honor(TEST_PERIOD, "3",
                  current_rank=UserLevel.NOTHING,
                  prev_period=PREV_PERIOD,
                  prev_highest_rank=UserLevel.PRO_ELITE,
                  highest_rank=UserLevel.PRO_ELITE)

    # ---- User 4/5：User 13 分支仍撑住结构线，整段保持 ----
    _assert_user(TEST_PERIOD, "4", gpv=800, qualified_legs={"3"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=800,
                 highest_rank=UserLevel.NOTHING)
    _assert_user(TEST_PERIOD, "5", gpv=800, qualified_legs={"4"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=800,
                 highest_rank=UserLevel.NOTHING)

    # ---- 不受退货影响的节点：13 / 9 / 1 ----
    _assert_user(TEST_PERIOD, "13", gpv=1000, qualified_legs=set(), virtual_width=0,
                 rank=UserLevel.ELITE, is_elite=True, contrib=0,
                 highest_rank=UserLevel.ELITE)
    _assert_user(TEST_PERIOD, "9", gpv=800, qualified_legs=set(), virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=800,
                 highest_rank=UserLevel.NOTHING)
    _assert_user(TEST_PERIOD, "1", gpv=800, qualified_legs={"13"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=800,
                 highest_rank=UserLevel.NOTHING)

    print("[PASS] 用例 2.2")


def _assert_user_stats_absent(period: str, user_id: str) -> None:
    """断言某期某用户在 UserStats 中不存在（用于验证 write_zero_nodes=False 跳过真零节点）。"""
    try:
        UserStats.get(f"{period}:{user_id}")
    except NotFoundError:
        logger.info("  ✓ [%s] User %s 已按预期跳过保存", period, user_id)
        return
    raise AssertionError(
        f"[{period}] User {user_id} 不应被保存到 UserStats"
        f"（真零节点在 write_zero_nodes=False 时应跳过）"
    )


# =====================================================================
# 用例 3.1：write_zero_nodes=False 时，仍保留 gpv=0 的「结构晋级」节点
#
# 回归保护历史 bug：旧版保存条件是 p_node.gpv > 0，会把自身 gpv=0、
# 纯靠合格线结构晋级的节点漏存。修正版改为 not _is_zero_user_stats(node)
# （按 rank / qualified_legs 等综合判定），本用例守住这条分支。
#
# 场景（只造两条结构线，不注入 9 的 800 业绩）：
#   13(1000) -> 1 -> 3
#   10(2000) -> 2 -> 3
#   3 自身 gpv=0，但有 {"1","2"} 两条合格线 -> 路径 B -> PRO_ELITE，必须被保存。
#   而真正全零的 9（未注入、无下级）应被跳过，不写 UserStats。
# =====================================================================
def test_case_3_1_write_zero_nodes_false_keeps_structure_promotion():
    print("\n" + "=" * 70)
    print("用例 3.1：write_zero_nodes=False 时保留 gpv=0 的结构晋级节点")
    print("=" * 70)

    _clear_all_redis()
    _inject_pv(TEST_PERIOD, "13", 1000)
    _inject_pv(TEST_PERIOD, "10", 2000)
    _run(TEST_PERIOD, write_zero_nodes=False)

    # ---- 关键节点 User 3：gpv=0，但靠 {"1","2"} 两条合格线晋升 PRO_ELITE，且必须被保存 ----
    _assert_user(TEST_PERIOD, "3", gpv=0, qualified_legs={"1", "2"}, virtual_width=0,
                 rank=UserLevel.PRO_ELITE, is_elite=False, contrib=0,
                 highest_rank=UserLevel.PRO_ELITE)
    _assert_honor(TEST_PERIOD, "3",
                  current_rank=UserLevel.PRO_ELITE,
                  prev_period=PREV_PERIOD,
                  prev_highest_rank=UserLevel.NOTHING,
                  highest_rank=UserLevel.PRO_ELITE)

    # ---- 中间结构节点 1 / 2：同样 gpv=0 但持有合格线，也必须被保存（同一保存分支）----
    _assert_user(TEST_PERIOD, "1", gpv=0, qualified_legs={"13"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=0,
                 highest_rank=UserLevel.NOTHING)
    _assert_user(TEST_PERIOD, "2", gpv=0, qualified_legs={"10"}, virtual_width=0,
                 rank=UserLevel.NOTHING, is_elite=False, contrib=0,
                 highest_rank=UserLevel.NOTHING)

    # ---- 反向验证：真正全零的 User 9（未注入、无下级）应被跳过，不写 UserStats ----
    _assert_user_stats_absent(TEST_PERIOD, "9")

    print("[PASS] 用例 3.1")


# =====================================================================
# 入口
# =====================================================================
def main():
    print(f"\n连接 Dask 调度器: {SCHEDULE_ADDRESS}")

    passed = []
    failed = []

    all_cases = (
        test_case_1_1,
        test_case_1_2,
        test_case_1_3,
        test_case_2_1,
        test_case_2_2,
        test_case_3_1_write_zero_nodes_false_keeps_structure_promotion,
    )

    # 连通性探测客户端（settle_period 内部各自开/关自己的 Client）。
    # 放进 try/finally，确保连接阶段异常也能安全关闭。
    client = None
    try:
        client = Client(SCHEDULE_ADDRESS)

        for case_fn in all_cases:
            try:
                case_fn()
                passed.append(case_fn.__name__)
            except AssertionError as e:
                failed.append((case_fn.__name__, str(e)))
                logger.error("用例失败: %s\n%s", case_fn.__name__, e)
            except Exception as e:  # 结算/连接异常也归入失败，避免静默
                failed.append((case_fn.__name__, f"运行异常: {e!r}"))
                logger.exception("用例运行异常: %s", case_fn.__name__)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    print("\n" + "=" * 70)
    print(f"通过: {len(passed)} / 失败: {len(failed)}")
    for name in passed:
        print(f"  ✓ {name}")
    for name, msg in failed:
        print(f"  ✗ {name}: {msg.splitlines()[0]}")
    print("=" * 70)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()