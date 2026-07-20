import logging
import os
import sys
import uuid
from typing import Dict, List, Set, Tuple
from redis_om import Migrator

# =====================================================================
# 导入生产环境代码与模型
# =====================================================================
from User.UserStatsService import UserStatsService
import Model.User.UserLevel as UserLevel
from Model.User.UserStats import UserStats

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [IntegrationTest] %(message)s'
)
logger = logging.getLogger(__name__)

SCHEDULE_ADDRESS = "tcp://127.0.0.1:8786"
TEST_PERIOD = "202605"  # 全局统一测试期数

# =====================================================================
# tb_user 测试数据参照表
# (此处的映射现在仅作为全量用户 ID 的参照，关系实际上由 graph_actor 提供)
# =====================================================================
TB_USER_DATA: List[Tuple[str, str, str, str]] = [
    ("1", "1", "3", "2025-12-24 19:04:13"),
    ("10", "10", "2", "2026-01-01 12:29:32"),
    ("11", "11", "0", "2026-01-01 12:35:03"),
    ("12", "12", "0", "2026-01-01 16:07:14"),
    ("13", "13", "1", "2026-02-17 12:10:51"),
    ("2", "2", "3", "2026-01-01 12:27:41"),
    ("3", "3", "4", "2026-01-01 12:27:44"),
    ("4", "4", "5", "2026-01-01 12:27:46"),
    ("5", "5", "0", "2026-01-01 12:27:49"),
    ("6", "6", "0", "2026-01-01 12:27:52"),
    ("7", "7", "8", "2026-01-01 12:27:11"),
    ("8", "8", "0", "2026-01-01 12:28:00"),
    ("9", "9", "1", "2026-01-01 12:28:04"),
]

# 提取全部 user_id 以便初始化 Redis 节点状态 (gpv 等)
TB_USER_ALL_IDS: List[str] = sorted(
    {user_id for (_id, user_id, _p, _ct) in TB_USER_DATA},
    key=lambda x: (0, int(x)) if x.isdigit() else (1, x),
)


# =====================================================================
# 测试装备 (test fixtures)
# =====================================================================
def _flushdb_test_only():
    """安全闸门: 必须显式 ALLOW_REDIS_TEST_FLUSH=1."""
    if os.environ.get("ALLOW_REDIS_TEST_FLUSH") != "1":
        raise RuntimeError(
            "拒绝执行 flushdb. 必须显式设置环境变量 ALLOW_REDIS_TEST_FLUSH=1, "
            "并确认 redis_om 当前连接的是一个专用的测试 DB."
        )
    conn = UserStats.db()
    conn.flushdb()
    logger.info("测试 DB 已清空。")


def _populate_users(svc: UserStatsService,
                    state: Dict[str, Tuple[int, Set[str]]]) -> None:
    """
    单阶段灌库:
    由于图关系已经交由 Dask 的 graph_actor 负责处理，
    这里仅需将涉及到的 UserStats 节点属性 (GPV 等) 初始化至 Redis。
    """
    union_ids = list({*TB_USER_ALL_IDS, *state.keys()})
    period = TEST_PERIOD

    for uid in union_ids:
        gpv, legs = state.get(uid, (0, set()))
        u = UserStats(
            pk=f"{period}:{uid}",   # 复合主键隔离
            period=period,
            id=str(uid),
            user_id=str(uid),
            pv=int(gpv),
            gpv=int(gpv),
            qualified_legs=set(str(x) for x in legs),
        )
        svc._recalc_rank(u)
        u.contrib = svc._calc_contrib(u)
        u.save()

    try:
        Migrator().run()
    except Exception as e:
        logger.warning("Migrator().run() 失败: %s", e)


def _baseline_state() -> Dict[str, Tuple[int, Set[str]]]:
    """基准初始数据"""
    return {
        "5": (4500, set()),
        "4": (3500, set()),
        "3": (2500, set()),
        "2": (800, set()),
        "1": (1200, set()),
        "9": (600, set()),
        "13": (300, set()),
        "10": (400, set()),
        "6": (0, set()), "7": (0, set()), "8": (0, set()),
        "11": (0, set()), "12": (0, set()),
    }


def _gen_order_id(prefix: str) -> str:
    """生成唯一订单号防止被幂等防御拦截"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# =====================================================================
# 测试用例
# =====================================================================
def test_case_a_source_level_early_stop(svc: UserStatsService):
    _flushdb_test_only()
    _populate_users(svc, _baseline_state())

    svc.update_elite_performance(period=TEST_PERIOD, user_id="4", bv=50, order_id=_gen_order_id("A"))

    u4 = UserStats.get(f"{TEST_PERIOD}:4")
    assert u4.pv == 3550
    assert u4.gpv == 3550
    assert u4.contrib == 0
    assert u4.rank == UserLevel.SUPER_ELITE

    u5 = UserStats.get(f"{TEST_PERIOD}:5")
    assert u5.gpv == 4500
    assert u5.qualified_legs == set()

    u3 = UserStats.get(f"{TEST_PERIOD}:3")
    assert u3.gpv == 2500


def test_case_b_propagation_no_truncation(svc: UserStatsService):
    _flushdb_test_only()
    _populate_users(svc, _baseline_state())

    svc.update_elite_performance(period=TEST_PERIOD, user_id="9", bv=200, order_id=_gen_order_id("B"))

    u9 = UserStats.get(f"{TEST_PERIOD}:9")
    assert u9.pv == 800 and u9.gpv == 800
    assert u9.contrib == 800
    assert u9.rank == UserLevel.NOTHING and u9.is_elite is False

    u1 = UserStats.get(f"{TEST_PERIOD}:1")
    assert u1.gpv == 1400
    assert u1.contrib == 0
    assert u1.rank == UserLevel.ELITE
    assert u1.qualified_legs == set()

    u3 = UserStats.get(f"{TEST_PERIOD}:3")
    assert u3.gpv == 2500 and u3.qualified_legs == set()
    u4 = UserStats.get(f"{TEST_PERIOD}:4")
    assert u4.gpv == 3500
    u5 = UserStats.get(f"{TEST_PERIOD}:5")
    assert u5.gpv == 4500


def test_case_c_truncation_rollback(svc: UserStatsService):
    _flushdb_test_only()
    state = _baseline_state()
    state["9"] = (900, set())
    state["1"] = (1500, set())
    _populate_users(svc, state)

    svc.update_elite_performance(period=TEST_PERIOD, user_id="9", bv=200, order_id=_gen_order_id("C"))

    u9 = UserStats.get(f"{TEST_PERIOD}:9")
    assert u9.gpv == 1100 and u9.contrib == 0
    assert u9.rank == UserLevel.ELITE and u9.is_elite is True

    u1 = UserStats.get(f"{TEST_PERIOD}:1")
    assert u1.gpv == 600
    assert u1.contrib == 600
    assert u1.qualified_legs == {"9"}
    assert u1.rank == UserLevel.NOTHING

    u3 = UserStats.get(f"{TEST_PERIOD}:3")
    assert u3.gpv == 3100 and u3.qualified_legs == {"1"}
    assert u3.rank == UserLevel.SUPER_ELITE

    u4 = UserStats.get(f"{TEST_PERIOD}:4")
    assert u4.gpv == 3500 and u4.qualified_legs == {"3"}
    assert u4.rank == UserLevel.SUPER_ELITE

    u5 = UserStats.get(f"{TEST_PERIOD}:5")
    assert u5.gpv == 4500 and u5.qualified_legs == {"4"}
    assert u5.rank == UserLevel.SUPER_ELITE


def test_case_d_missing_ancestor_initialized_as_blank(svc: UserStatsService):
    """
    Redis 中缺失的祖先被视为"本期零起点", 由 _get_or_init_user 零值初始化,
    链路正常向上传导, 不再抛 BrokenAncestorChainError.
    """
    _flushdb_test_only()
    _populate_users(svc, _baseline_state())

    # 模拟"4 号本月尚未在 Redis 中存在"
    UserStats.delete(f"{TEST_PERIOD}:4")

    svc.update_elite_performance(period=TEST_PERIOD, user_id="9", bv=500, order_id=_gen_order_id("D"))

    # ---- 9 号 (源): gpv 1100 升 Elite, contrib 600 -> 0, 向上 delta = -600 ----
    u9 = UserStats.get(f"{TEST_PERIOD}:9")
    assert u9.pv == 1100, f"u9.pv expected 1100, got {u9.pv}"
    assert u9.gpv == 1100, f"u9.gpv expected 1100, got {u9.gpv}"
    assert u9.contrib == 0, f"u9.contrib expected 0, got {u9.contrib}"
    assert u9.is_elite is True, f"u9.is_elite expected True, got {u9.is_elite}"
    assert u9.rank == UserLevel.ELITE, f"u9.rank expected ELITE, got {u9.rank}"
    assert set(u9.qualified_legs) == set()

    # ---- 1 号: gpv 1200 + (-600) = 600, 跌出 Elite;
    #          但获得合格线 {9} (9 已升 Elite); contrib 重新变为 600 (gpv<1000); ----
    u1 = UserStats.get(f"{TEST_PERIOD}:1")
    assert u1.gpv == 600, f"u1.gpv expected 600, got {u1.gpv}"
    assert u1.contrib == 600, f"u1.contrib expected 600, got {u1.contrib}"
    assert set(u1.qualified_legs) == {"9"}, \
        f"u1.qualified_legs expected {{'9'}}, got {set(u1.qualified_legs)}"
    assert u1.rank == UserLevel.NOTHING, f"u1.rank expected NOTHING, got {u1.rank}"

    # ---- 3 号: 接收 1 号上传的 +600, gpv 2500 -> 3100;
    #          1 号自身虽非 Elite, 但其 legs 非空 -> 仍是 3 号的合格线;
    #          virtual_width = 3100 // 1000 = 3, total = 1 + 3 = 4 -> SUPER_ELITE ----
    u3 = UserStats.get(f"{TEST_PERIOD}:3")
    assert u3.gpv == 3100, f"u3.gpv expected 3100, got {u3.gpv}"
    assert u3.contrib == 0, f"u3.contrib expected 0, got {u3.contrib}"
    assert u3.virtual_width == 3, f"u3.virtual_width expected 3, got {u3.virtual_width}"
    assert set(u3.qualified_legs) == {"1"}, \
        f"u3.qualified_legs expected {{'1'}}, got {set(u3.qualified_legs)}"
    assert u3.rank == UserLevel.SUPER_ELITE, \
        f"u3.rank expected SUPER_ELITE, got {u3.rank}"

    # ---- 4 号: Redis 中本不存在, 被零值初始化后参与本轮;
    #          入站 delta = 0 (3 号 contrib 一直为 0), gpv 保持 0;
    #          3 号是 SUPER_ELITE -> 4 号获得合格线 {3};
    #          自身未达 Elite + 总宽度 1 < 2 -> rank=NOTHING ----
    u4 = UserStats.get(f"{TEST_PERIOD}:4")
    assert u4.pv == 0, f"u4.pv expected 0, got {u4.pv}"
    assert u4.gpv == 0, f"u4.gpv expected 0, got {u4.gpv}"
    assert u4.contrib == 0, f"u4.contrib expected 0, got {u4.contrib}"
    assert u4.is_elite is False, f"u4.is_elite expected False, got {u4.is_elite}"
    assert u4.virtual_width == 0, f"u4.virtual_width expected 0, got {u4.virtual_width}"
    assert set(u4.qualified_legs) == {"3"}, \
        f"u4.qualified_legs expected {{'3'}}, got {set(u4.qualified_legs)}"
    assert u4.rank == UserLevel.NOTHING, f"u4.rank expected NOTHING, got {u4.rank}"

    # ---- 5 号: 入站 delta=0, gpv 保持 4500;
    #          4 号自身非 Elite 但 legs 非空 -> 仍是 5 号的合格线;
    #          total = 1 + 4 (virtual) = 5 -> 仍是 SUPER_ELITE, width 从 0 -> 1 ----
    u5 = UserStats.get(f"{TEST_PERIOD}:5")
    assert u5.gpv == 4500, f"u5.gpv expected 4500, got {u5.gpv}"
    assert u5.contrib == 0, f"u5.contrib expected 0, got {u5.contrib}"
    assert set(u5.qualified_legs) == {"4"}, \
        f"u5.qualified_legs expected {{'4'}}, got {set(u5.qualified_legs)}"
    assert u5.rank == UserLevel.SUPER_ELITE, \
        f"u5.rank expected SUPER_ELITE, got {u5.rank}"


def test_case_e_rank_virtual_width_boundaries(svc: UserStatsService):
    _flushdb_test_only()
    _populate_users(svc, {
        "20": (999, set()),
        "21": (1000, set()),
        "22": (1999, set()),
        "23": (2000, set()),
        "24": (2999, set()),
        "25": (3000, set()),
        "26": (999, {"a", "b"}),
        "27": (1000, {"a"}),
        "28": (999, {"a", "b", "c"}),
    })

    expectations = {
        "20": (False, 0, UserLevel.NOTHING, 999),
        "21": (True, 0, UserLevel.ELITE, 0),
        "22": (True, 0, UserLevel.ELITE, 0),
        "23": (True, 2, UserLevel.PRO_ELITE, 0),
        "24": (True, 2, UserLevel.PRO_ELITE, 0),
        "25": (True, 3, UserLevel.SUPER_ELITE, 0),
        "26": (False, 0, UserLevel.PRO_ELITE, 999),
        "27": (True, 0, UserLevel.PRO_ELITE, 0),
        "28": (False, 0, UserLevel.SUPER_ELITE, 999),
    }

    for uid, (is_elite, virtual_width, rank, contrib) in expectations.items():
        u = UserStats.get(f"{TEST_PERIOD}:{uid}")
        assert u.is_elite is is_elite
        assert u.virtual_width == virtual_width
        assert u.rank == rank
        assert u.contrib == contrib


def test_case_f_source_crosses_virtual_width_boundary_status_only(svc: UserStatsService):
    _flushdb_test_only()
    state = _baseline_state()
    state["1"] = (1900, set())
    state["3"] = (2500, {"1"})
    state["4"] = (3500, {"3"})
    state["5"] = (4500, {"4"})
    _populate_users(svc, state)

    pre = {}
    for uid in ("3", "4", "5"):
        u = UserStats.get(f"{TEST_PERIOD}:{uid}")
        pre[uid] = (u.gpv, set(u.qualified_legs), u.rank, u.contrib)

    svc.update_elite_performance(period=TEST_PERIOD, user_id="1", bv=100, order_id=_gen_order_id("F"))

    u1 = UserStats.get(f"{TEST_PERIOD}:1")
    assert u1.pv == 2000 and u1.gpv == 2000
    assert u1.contrib == 0 and u1.virtual_width == 2
    assert u1.rank == UserLevel.PRO_ELITE

    for uid, (gpv, legs, rank, contrib) in pre.items():
        u = UserStats.get(f"{TEST_PERIOD}:{uid}")
        assert u.gpv == gpv
        assert set(u.qualified_legs) == legs
        assert u.rank == rank
        assert u.contrib == contrib


def test_case_g_two_sibling_truncations_accumulate_qualified_legs(svc: UserStatsService):
    _flushdb_test_only()
    state = _baseline_state()
    state["9"] = (900, set())
    state["13"] = (900, set())
    state["1"] = (1800, set())
    state["3"] = (0, set())
    state["4"] = (0, set())
    state["5"] = (0, set())
    _populate_users(svc, state)

    svc.update_elite_performance(period=TEST_PERIOD, user_id="9", bv=200, order_id=_gen_order_id("G1"))
    svc.update_elite_performance(period=TEST_PERIOD, user_id="13", bv=200, order_id=_gen_order_id("G2"))

    for uid in ("9", "13"):
        u = UserStats.get(f"{TEST_PERIOD}:{uid}")
        assert u.gpv == 1100
        assert u.contrib == 0
        assert u.rank == UserLevel.ELITE

    u1 = UserStats.get(f"{TEST_PERIOD}:1")
    assert u1.gpv == 0
    assert u1.contrib == 0
    assert set(u1.qualified_legs) == {"9", "13"}
    assert u1.rank == UserLevel.PRO_ELITE

    for uid, expected_leg in (("3", "1"), ("4", "3"), ("5", "4")):
        u = UserStats.get(f"{TEST_PERIOD}:{uid}")
        assert u.gpv == 0
        assert u.contrib == 0
        assert set(u.qualified_legs) == {expected_leg}
        assert u.rank == UserLevel.NOTHING


def test_case_h_zero_bv_noop(svc: UserStatsService):
    _flushdb_test_only()
    _populate_users(svc, _baseline_state())

    before = {}
    for uid in ("9", "1", "3", "4", "5"):
        u = UserStats.get(f"{TEST_PERIOD}:{uid}")
        before[uid] = (u.pv, u.gpv, u.contrib, u.rank, set(u.qualified_legs))

    svc.update_elite_performance(period=TEST_PERIOD, user_id="9", bv=0, order_id=_gen_order_id("H"))

    for uid, expected in before.items():
        u = UserStats.get(f"{TEST_PERIOD}:{uid}")
        actual = (u.pv, u.gpv, u.contrib, u.rank, set(u.qualified_legs))
        assert actual == expected


# =====================================================================
# main: 测试运行器
# =====================================================================
def main():
    logger.info("连接 Dask 调度器: %s", SCHEDULE_ADDRESS)
    svc = UserStatsService()
    tests = [
        ("Case A: 源端早停, 不触碰祖先", test_case_a_source_level_early_stop),
        ("Case B: 单层冒泡到 Elite 父后停止", test_case_b_propagation_no_truncation),
        ("Case C: 跨过 1000 触发截断回滚 + 全链路合格线更新", test_case_c_truncation_rollback),
        ("Case D: Redis 中缺失的祖先被零值初始化并继续传导", test_case_d_missing_ancestor_initialized_as_blank),
        ("Case E: rank / virtual_width 边界", test_case_e_rank_virtual_width_boundaries),
        (
            "Case F: 源用户跨 virtual width 边界但祖先不变",
            test_case_f_source_crosses_virtual_width_boundary_status_only),
        ("Case G: 两个兄弟分支依次截断并累积合格线", test_case_g_two_sibling_truncations_accumulate_qualified_legs),
        ("Case H: bv=0 no-op", test_case_h_zero_bv_noop),
    ]

    failed: List[Tuple[str, str]] = []
    for name, fn in tests:
        print(f"\n--- 运行: {name} ---")
        try:
            fn(svc)
            print(f"✓ PASS  {name}")
        except AssertionError as e:
            print(f"✗ FAIL  {name}\n        断言失败: {e}")
            failed.append((name, f"AssertionError: {e}"))
        except Exception as e:
            print(f"✗ ERROR {name}\n        意外异常: {type(e).__name__}: {e}")
            failed.append((name, f"{type(e).__name__}: {e}"))

    print("\n" + "=" * 60)
    if failed:
        print(f"{len(failed)}/{len(tests)} 个用例失败:")
        for name, reason in failed:
            print(f"  - {name}\n      {reason}")
        sys.exit(1)
    else:
        print(f"全部 {len(tests)} 个用例通过 ✓")


if __name__ == "__main__":
    main()