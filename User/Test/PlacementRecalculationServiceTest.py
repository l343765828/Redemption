"""
PlacementRecalculationService 双轨制/安置网结算测试用例集
（基于待正式登记的业务口径，见 D-2）

放置位置：和 PlacementRecalculationService.py 同目录（User/），保持包导入路径一致。

执行方式：
    ALLOW_PLACEMENT_DESTRUCTIVE_TEST=YES python3 -m User.PlacementRecalculationServiceTest
    注：测试 Redis 需预置 system:placement_test_env_marker 标识键，值为 PLACEMENT_TEST_ONLY。

排障模式（保留 Redis 现场不清理，建议配合过滤使用以锁定案发现场）：
    ONLY_CASE=test_case_3a_merge_semantics KEEP_TEST_DATA=1 ALLOW_PLACEMENT_DESTRUCTIVE_TEST=YES python3 -m User.PlacementRecalculationServiceTest

⚠️ 【独占环境约束声明】：
    本套件必须在独占测试环境运行，禁止与生产/UAT 结算任务共用 Redis！

⚠️ 核心图谱拓扑要求（程序启动时会执行前置校验 `_validate_required_topology`）：
    [用例1拓扑]
    1(A) --[Leg 1]--> 2(B)
    2(B) --[Leg 2]--> 3(C)

    [用例3,4拓扑]
    5(E) --[Leg 1]--> 6(F), 5(E) --[Leg 2]--> 7(G)
    8(H) --[Leg 1]--> 9(I), 8(H) --[Leg 2]--> 10(J)
    4(D), 11 为脱图辅助节点（4 用于纯结余过桥，11 用于纯 gpv 活跃分支验证）

    [用例6 满血 5 层二叉树拓扑：节点 100(Root) ~ 130(叶子)]
    Level 1: 100
    Level 2: 100->101(1L), 100->102(2L)
    Level 3: 101->103(1L), 101->104(2L); 102->105(1L), 102->106(2L)
    Level 4: 103->107,108; 104->109,110; 105->111,112; 106->113,114 (1L/2L顺延)
    Level 5: 107->115,116; ... 114->129,130 (共16个叶子，即节点 115 ~ 130)

测试集覆盖 PlacementRecalculationService 职责范围内的双轨制核心边界：
    本测试集用于验证 PlacementRecalculationService 的安置网 1L/2L、结余桥接与闭包聚合逻辑。
    不覆盖 CALC_PV.sql 全链路中的 PV_PSS、PV_PCS_ZC/PV_PCS_FX、STOCKIST_PV、AR_PERF_ACTIVE 快照写入与主表回写。

📝 【业务规则决策点 (D-1 ~ D-5) 声明】：
    - D-1 (精度口径现状锁定): 跨期残留小数一律按 Banker's Rounding (取偶) 处理为整数。待业务确认。
    - D-2 (零节点生命周期): 纯结余用户将产出 TOTAL=0 的实体行及桥接结余。下游对碰模块必须将"无行"与"TOTAL=0的行"视为同义。【待确认】确认人：____ 日期：____ 需求条目：____
    - D-3 (剥离测试认属): 推荐网/特批活跃/存货商 已脱离本模块职责，测试标记为 SKIP，需跨模块统筹。MID6 桥接分歧：仅存货商 PV + 旧结余的用户，需在归属登记时确认口径。
    - D-4 (负 PV / 退款订单口径): 负 PV 是否允许入 pv 字段、上游 Kafka 是否冲抵、传播规则。write_zero_nodes 参数存废与端到端负 PV 用例锚此项。
    - D-5 (MID7 成员资格映射契约): gpv/gpv_real/gpv_unreal 择一定义、是否等价 MID3 成员资格。TC3c 锚此项。
"""
import logging
import json
import os
from typing import Optional

from dask.distributed import Client
from redis_om import NotFoundError

from Model.User.UserStats import UserStats
from Common.PeriodResolver import PeriodSnapshot
from User.PlacementRecalculationService import PlacementRecalculationService
from Model.Config import SCHEDULE_ADDRESS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [PRSTest] %(message)s",
)
logger = logging.getLogger(__name__)

# =====================================================================
# 常量：测试期数与前置约束
# =====================================================================
PREV_PERIOD = "999904"
TEST_PERIOD = "999905"
CANDIDATE_PERIODS = (PREV_PERIOD, TEST_PERIOD)

ISOLATED_TEST_NODES = {"4", "11"}
TEST_ENV_MARKER_KEY = "system:placement_test_env_marker"

def _binary_tree_edges():
    edges = set()
    for i in range(100, 115):
        left = 100 + (i - 100) * 2 + 1
        right = left + 1
        edges.add((str(i), str(left), 1))
        edges.add((str(i), str(right), 2))
    return edges

REQUIRED_EDGES = {
    ("1", "2", 1), ("2", "3", 2),
    ("5", "6", 1), ("5", "7", 2),
    ("8", "9", 1), ("8", "10", 2),
    *_binary_tree_edges()
}

# =====================================================================
# 测试专用子类与辅助方法
# =====================================================================
class PlacementRecalculationServiceForTest(PlacementRecalculationService):
    """
    测试专用子类。
    覆盖全局常量，保证 pytest 等同进程测试框架下的多用例环境隔离，防止污染生产配置。
    避免以 Test 开头以防被 pytest 误识别为测试用例类。
    """
    OUTBOX_STREAM_KEY = "system:test:placement_recalc_outbox_stream"


def _guard_destructive_env(redis_conn) -> None:
    """环境身份三重校验"""
    if os.environ.get("ALLOW_PLACEMENT_DESTRUCTIVE_TEST") != "YES":
        raise RuntimeError("拒绝执行：未设置 ALLOW_PLACEMENT_DESTRUCTIVE_TEST=YES（破坏性测试显式开关）")

    marker = redis_conn.get(TEST_ENV_MARKER_KEY)
    marker_str = marker.decode('utf-8') if isinstance(marker, bytes) else marker
    if marker_str != "PLACEMENT_TEST_ONLY":
        raise RuntimeError(f"拒绝执行：缺少测试环境标识键或值不为 PLACEMENT_TEST_ONLY，疑似误连非测试实例")

    if redis_conn.exists(PlacementRecalculationService.GLOBAL_RECALC_LOCK_KEY):
        raise RuntimeError("拒绝执行：检测到全局结算锁（结算在跑或服务锁泄漏）。不强删——等待 TTL 自愈或人工排查")


def _clear_all_redis() -> None:
    """重构安全清库：校验前置 + 异常收集抛出 + Outbox 清理"""
    redis_conn = UserStats.db()
    _guard_destructive_env(redis_conn)

    prefix = UserStats.make_key('')
    failures = []

    for period in CANDIDATE_PERIODS:
        for key in redis_conn.scan_iter(f"{prefix}{period}:*"):
            try:
                redis_conn.delete(key)
            except Exception as e:
                failures.append((str(key), repr(e)))

    try:
        redis_conn.delete(PlacementRecalculationServiceForTest.OUTBOX_STREAM_KEY)
        for period in CANDIDATE_PERIODS:
            redis_conn.delete(PlacementRecalculationService._status_key(period))
    except Exception as e:
        failures.append(("outbox/status", repr(e)))

    if failures:
        raise RuntimeError(f"清理未完成 {len(failures)} 项，禁止在脏环境继续: {failures[:5]}")

    logger.info("Redis 安全隔离清理完成：periods=%s", list(CANDIDATE_PERIODS))


def _validate_required_topology(client: Client) -> None:
    """拓扑预检升级：诱导子图精确校验"""
    ga = client.get_dataset("graph_actor").result()
    edges_ddf = ga.get_placement_edges().result()

    nodes = {x for e in REQUIRED_EDGES for x in e[:2]} | ISOLATED_TEST_NODES
    mask = edges_ddf["dst"].astype("str").isin(list(nodes)) | edges_ddf["src"].astype("str").isin(list(nodes))
    sub = edges_ddf[mask].compute().to_pandas()

    have = set(zip(
        sub["dst"].astype(str),
        sub["src"].astype(str),
        sub["placementLeg"].fillna(-1).astype(int)
    ))

    if len(sub) != len(REQUIRED_EDGES) or have != REQUIRED_EDGES:
        missing = sorted(list(REQUIRED_EDGES - have))[:10]
        extra   = sorted(list(have - REQUIRED_EDGES))[:10]
        raise RuntimeError(
            f"环境前置失败：测试节点诱导子图与要求不符。缺失(≤10): {missing} / "
            f"多余或非法(≤10): {extra} / 行数 {len(sub)} vs 期望 {len(REQUIRED_EDGES)}")


def _mock_prev_period_done(period: str) -> None:
    prev = PlacementRecalculationService._get_prev_period(period)
    if prev:
        redis_conn = UserStats.db()
        redis_conn.set(PlacementRecalculationService._status_key(prev), json.dumps({"status": "DONE"}))
        UserStats(pk=f"{prev}:9999", period=prev, id="9999", user_id="9999").save()


def _inject_curr_activity(period: str, user_id: str, pv: int = 0, gpv: int = 0) -> None:
    try:
        s = UserStats.get(f"{period}:{user_id}")
    except NotFoundError:
        s = UserStats(pk=f"{period}:{user_id}", period=period, id=user_id, user_id=user_id)
    s.pv = pv
    s.gpv = gpv
    s.save()


def _inject_prev_surplus(prev_period: str, user_id: str, remain_1l: int = 0, remain_2l: int = 0) -> None:
    try:
        s = UserStats.get(f"{prev_period}:{user_id}")
    except NotFoundError:
        s = UserStats(pk=f"{prev_period}:{user_id}", period=prev_period, id=user_id, user_id=user_id)
    s.remain_surplus_1l = remain_1l
    s.remain_surplus_2l = remain_2l
    s.save()


def _inject_prev_surplus_raw_float(prev_period: str, user_id: str, remain_1l: float, remain_2l: float) -> None:
    key = f"{UserStats.make_key('')}{prev_period}:{user_id}"
    if not UserStats.db().exists(key):
        UserStats(pk=f"{prev_period}:{user_id}", period=prev_period, id=user_id, user_id=user_id).save()
    UserStats.db().json().set(key, "$.remain_surplus_1l", remain_1l)
    UserStats.db().json().set(key, "$.remain_surplus_2l", remain_2l)


def _run(period: str, *, write_zero_nodes: bool = True) -> None:
    # 使用显式 AR_PERIOD fixture，禁止测试调用方继续依赖本地 period 算术。
    snapshots = {
        PREV_PERIOD: PeriodSnapshot(
            period_num=999904, calc_year=9999, calc_month=4,
            first_period_num=999904, previous_period_num=None,
            source_checksum="placement-recalc-test-999904",
        ),
        TEST_PERIOD: PeriodSnapshot(
            period_num=999905, calc_year=9999, calc_month=5,
            first_period_num=999904, previous_period_num=999904,
            source_checksum="placement-recalc-test-999905",
        ),
    }
    svc = PlacementRecalculationServiceForTest()
    svc.settle_placement_period(
        period=period,
        period_snapshot=snapshots[period],
        write_zero_nodes=write_zero_nodes,
    )

    # 【校验增强】无论哪种用例，只要跑完成功路径，锁都必须被安全释放
    assert not UserStats.db().exists(
        PlacementRecalculationServiceForTest.GLOBAL_RECALC_LOCK_KEY
    ), "成功路径全局锁未释放，存在严重的死锁泄漏风险"


def _assert_placement(
    period: str,
    user_id: str,
    *,
    pv_1l: Optional[int] = None,
    pv_2l: Optional[int] = None,
    pre_surplus_1l: Optional[int] = None,
    pre_surplus_2l: Optional[int] = None,
    total_1l: Optional[int] = None,
    total_2l: Optional[int] = None,
    remain_surplus_1l: Optional[int] = None,
    remain_surplus_2l: Optional[int] = None,
) -> None:
    try:
        s = UserStats.get(f"{period}:{user_id}")
    except NotFoundError:
        raise AssertionError(f"[{period}] User {user_id} 缺失 UserStats 记录")

    fails = []
    if pv_1l is not None and (s.pv_1l or 0) != pv_1l:
        fails.append(f"pv_1l expected={pv_1l} actual={s.pv_1l}")
    if pv_2l is not None and (s.pv_2l or 0) != pv_2l:
        fails.append(f"pv_2l expected={pv_2l} actual={s.pv_2l}")
    if pre_surplus_1l is not None and (s.pre_surplus_1l or 0) != pre_surplus_1l:
        fails.append(f"pre_surplus_1l expected={pre_surplus_1l} actual={s.pre_surplus_1l}")
    if pre_surplus_2l is not None and (s.pre_surplus_2l or 0) != pre_surplus_2l:
        fails.append(f"pre_surplus_2l expected={pre_surplus_2l} actual={s.pre_surplus_2l}")
    if total_1l is not None and (s.total_1l or 0) != total_1l:
        fails.append(f"total_1l expected={total_1l} actual={s.total_1l}")
    if total_2l is not None and (s.total_2l or 0) != total_2l:
        fails.append(f"total_2l expected={total_2l} actual={s.total_2l}")
    if remain_surplus_1l is not None and (s.remain_surplus_1l or 0) != remain_surplus_1l:
        fails.append(f"remain_surplus_1l expected={remain_surplus_1l} actual={s.remain_surplus_1l}")
    if remain_surplus_2l is not None and (s.remain_surplus_2l or 0) != remain_surplus_2l:
        fails.append(f"remain_surplus_2l expected={remain_surplus_2l} actual={s.remain_surplus_2l}")

    if fails:
        raise AssertionError(f"[{period}] Placement User {user_id} 断言失败:\n  " + "\n  ".join(fails))
    logger.info("  ✓ [%s] User %s (Placement 双轨账目) 通过", period, user_id)


# =====================================================================
# 用例 1：安置网隔离与明细分类累加
# =====================================================================
def test_case_1_placement_basic_accumulation():
    print("\n" + "=" * 70)
    print("用例 1：安置网隔离与明细累加 (大腿包小腿验证)")
    print("=" * 70)

    _clear_all_redis()
    _mock_prev_period_done(TEST_PERIOD)

    logger.info("架构说明：PV_PCS_ZC (注册单) / PV_PCS_FX (复消单) 的分类预聚合已前移至订单 Kafka Consumer。")
    logger.info("PlacementRecalculationService 不再介入源单类型分类，专注网络闭包推演。")

    _inject_curr_activity(TEST_PERIOD, "3", pv=500)
    _inject_curr_activity(TEST_PERIOD, "2", pv=100)
    _run(TEST_PERIOD)

    _assert_placement(TEST_PERIOD, "3", pv_1l=0, pv_2l=0, total_1l=0, total_2l=0)
    _assert_placement(TEST_PERIOD, "2", pv_1l=0, pv_2l=500, total_1l=0, total_2l=500)
    _assert_placement(TEST_PERIOD, "1", pv_1l=600, pv_2l=0, total_1l=600, total_2l=0)


# =====================================================================
# 用例 2：推荐网 (太阳线) PV_PSS 包含本人合并测试
# =====================================================================
def test_case_2_sponsor_pv_pss():
    print("\n" + "=" * 70)
    print("用例 2：推荐网 PV_PSS 逻辑已剥离至 GlobalRecalculationService")
    print("=" * 70)
    logger.info("本服务专注于双轨制 1L/2L。太阳线 PV_PSS 等逻辑已由 Global 服务负责，跳过断言。")
    return "SKIP"


# =====================================================================
# 用例 3：活跃状态与纯结余过桥全矩阵测试 (三拆)
# =====================================================================
def _seed_tc3():
    _clear_all_redis(); _mock_prev_period_done(TEST_PERIOD)
    for uid in ("4", "5", "8", "11"):
        _inject_prev_surplus(PREV_PERIOD, uid, remain_1l=100, remain_2l=0)
    _inject_curr_activity(TEST_PERIOD, "5", pv=50)
    _inject_curr_activity(TEST_PERIOD, "9", pv=50)
    _inject_curr_activity(TEST_PERIOD, "10", pv=50)
    _inject_curr_activity(TEST_PERIOD, "11", pv=0, gpv=500)
    _run(TEST_PERIOD)


def test_case_3a_merge_semantics():
    print("\n" + "=" * 70)
    print("用例 3a：需求验收（与 SQL MID7/MID8 一致的部分）")
    print("=" * 70)
    _seed_tc3()
    _assert_placement(TEST_PERIOD, "5", pv_1l=0, pv_2l=0, pre_surplus_1l=100, pre_surplus_2l=0,
                      total_1l=100, total_2l=0, remain_surplus_1l=0, remain_surplus_2l=0)
    _assert_placement(TEST_PERIOD, "8", pv_1l=50, pv_2l=50, pre_surplus_1l=100, pre_surplus_2l=0,
                      total_1l=150, total_2l=50, remain_surplus_1l=0, remain_surplus_2l=0)
    s5 = UserStats.get(f"{TEST_PERIOD}:5")
    assert (s5.pv or 0) == 50 and (s5.gpv or 0) == 0, "回写破坏了非双轨字段"


def test_case_3b_pure_surplus_bridge():
    print("\n" + "=" * 70)
    print("用例 3b：纯结余桥接 CHARACTERIZATION")
    print("=" * 70)
    _seed_tc3()
    _assert_placement(TEST_PERIOD, "4", pv_1l=0, pv_2l=0, pre_surplus_1l=100, pre_surplus_2l=0,
                      total_1l=0, total_2l=0, remain_surplus_1l=100, remain_surplus_2l=0)
    return "CHARACTERIZATION"


def test_case_3c_gpv_activity_trigger():
    print("\n" + "=" * 70)
    print("用例 3c：gpv 触发活动 CHARACTERIZATION")
    print("=" * 70)
    _seed_tc3()
    _assert_placement(TEST_PERIOD, "11", pv_1l=0, pv_2l=0, pre_surplus_1l=100, pre_surplus_2l=0,
                      total_1l=100, total_2l=0, remain_surplus_1l=0, remain_surplus_2l=0)
    return "CHARACTERIZATION"


# =====================================================================
# 用例 4：结余合并与自然推演
# =====================================================================
def test_case_4_surplus_merge_and_calculate():
    print("\n" + "=" * 70)
    print("用例 4：结余合并与自然推演 (MID8 验证)")
    print("=" * 70)
    _clear_all_redis()
    _mock_prev_period_done(TEST_PERIOD)

    _inject_prev_surplus(PREV_PERIOD, "5", remain_1l=1000, remain_2l=200)
    _inject_curr_activity(TEST_PERIOD, "6", pv=300)
    _inject_curr_activity(TEST_PERIOD, "7", pv=400)
    _run(TEST_PERIOD)

    _assert_placement(TEST_PERIOD, "5", pv_1l=300, pv_2l=400, pre_surplus_1l=1000, pre_surplus_2l=200,
                      total_1l=1300, total_2l=600, remain_surplus_1l=0, remain_surplus_2l=0)


# =====================================================================
# 用例 5：存货商 (STOCKIST) MID6 孤岛验证
# =====================================================================
def test_case_5_stockist_pv():
    print("\n" + "=" * 70)
    print("用例 5：存货商 (STOCKIST) MID6 孤岛验证 [架构剥离说明]")
    print("=" * 70)
    logger.info("架构说明：STOCKIST_PV 属于纯存货逻辑 (MID6)，业务口径不参与安置网双轨对碰。")
    logger.info("现已隔离在外，确保存账目纯净。")
    return "SKIP"


# =====================================================================
# 用例 6：5 层满二叉树大体量深层调度聚合
# =====================================================================
def test_case_6_deep_binary_tree_accumulation():
    print("\n" + "=" * 70)
    print("用例 6：5 层满二叉树大体量深度聚合压测 (16叶子节点)")
    print("=" * 70)
    _clear_all_redis()
    _mock_prev_period_done(TEST_PERIOD)

    for leaf in range(115, 131):
        _inject_curr_activity(TEST_PERIOD, str(leaf), pv=10)
    _run(TEST_PERIOD)

    for leaf in range(115, 131):
        _assert_placement(TEST_PERIOD, str(leaf), pv_1l=0, pv_2l=0)
    for node in range(107, 115):
        _assert_placement(TEST_PERIOD, str(node), pv_1l=10, pv_2l=10, total_1l=10, total_2l=10)
    for node in range(103, 107):
        _assert_placement(TEST_PERIOD, str(node), pv_1l=20, pv_2l=20, total_1l=20, total_2l=20)

    _assert_placement(TEST_PERIOD, "101", pv_1l=40, pv_2l=40, total_1l=40, total_2l=40)
    _assert_placement(TEST_PERIOD, "102", pv_1l=40, pv_2l=40, total_1l=40, total_2l=40)
    _assert_placement(TEST_PERIOD, "100", pv_1l=80, pv_2l=80, total_1l=80, total_2l=80)


# =====================================================================
# 用例 7：浮点数精度截断与 int(round()) 抹平验证
# =====================================================================
def test_case_7_precision_and_rounding():
    print("\n" + "=" * 70)
    print("用例 7：底层精度验证 (Banker's Rounding 银行家舍入行为锁定)")
    print("=" * 70)
    _clear_all_redis()
    _mock_prev_period_done(TEST_PERIOD)

    logger.info("若未来业务方要求严格按 SQL 的 DECIMAL(16,2) 截断，必须自此用例推翻并修改底层模型。")
    _inject_prev_surplus_raw_float(PREV_PERIOD, "2", remain_1l=100.5, remain_2l=0.0)
    _inject_prev_surplus_raw_float(PREV_PERIOD, "3", remain_1l=101.5, remain_2l=0.0)
    _run(TEST_PERIOD)

    _assert_placement(TEST_PERIOD, "2", pre_surplus_1l=100, total_1l=0, remain_surplus_1l=100, remain_surplus_2l=0)
    _assert_placement(TEST_PERIOD, "3", pre_surplus_1l=102, total_1l=0, remain_surplus_1l=102, remain_surplus_2l=0)
    return "CHARACTERIZATION"


# =====================================================================
# 用例 7b：单元级回写舍入锁定 CHARACTERIZATION
# =====================================================================
class _FakeLock:
    def owned(self): return True
    def extend(self, *a, **k): pass
    def release(self): pass

def test_case_7b_writeback_rounding_characterization():
    print("\n" + "=" * 70)
    print("用例 7b：单元级回写舍入锁定 CHARACTERIZATION")
    print("=" * 70)
    _clear_all_redis()
    svc = PlacementRecalculationServiceForTest()
    svc._write_back_placement_matrix(
        redis_conn=UserStats.db(), target_list=["71"],
        gpu_res_dict={"71": {"PV_1L": 100.5, "PV_2L": 101.5}},
        active_pv_dict={}, period=TEST_PERIOD, run_id="tc7b",
        write_zero_nodes=True, lock=_FakeLock(),
    )
    _assert_placement(TEST_PERIOD, "71", pv_1l=100, pv_2l=102, total_1l=100, total_2l=102)
    return "CHARACTERIZATION"


# =====================================================================
# 用例 7c：GPU 聚合保真测试
# =====================================================================
def _make_edges(rows):
    import cudf, dask_cudf
    return dask_cudf.from_cudf(cudf.DataFrame({
        "dst": [r[0] for r in rows], "src": [r[1] for r in rows],
        "placementLeg": [r[2] for r in rows]}), npartitions=1)

def test_case_7c_gpu_aggregation_fidelity():
    print("\n" + "=" * 70)
    print("用例 7c：GPU 聚合保真测试")
    print("=" * 70)
    import cudf
    svc = PlacementRecalculationServiceForTest()
    closure = svc._build_placement_closure_table(_make_edges([("1","2",1), ("2","3",2)]), _FakeLock())
    df_pv = cudf.DataFrame({"user_id": ["2", "3", "3"], "pv": [100.25, 0.125, 0.125]})

    res = svc._calculate_placement_pv(closure, df_pv)

    # 验证左腿 (PV_1L) 的聚合保真度
    row1 = res[res["ancestor"] == "1"].iloc[0]
    assert float(row1["PV_1L"]) == 100.5

    # 验证右腿 (PV_2L) 同用户多行预聚合与聚合保真度
    row2 = res[res["ancestor"] == "2"].iloc[0]
    assert float(row2["PV_2L"]) == 0.25


# =====================================================================
# 用例 8：闭包防线四合一熔断（单元级）
# =====================================================================
def _expect_fuse(rows, keyword):
    svc = PlacementRecalculationServiceForTest()
    try:
        svc._build_placement_closure_table(_make_edges(rows), _FakeLock())
        raise AssertionError(f"未触发熔断（期望包含 '{keyword}' 的 RuntimeError）")
    except RuntimeError as e:
        assert keyword in str(e), f"熔断类型错位: 期望 {keyword}, 实际 {e}"

def test_case_8_closure_guard_fuses():
    print("\n" + "=" * 70)
    print("用例 8：闭包防线四合一熔断（单元级）")
    print("=" * 70)
    _expect_fuse([("1","2",1), ("1","3",2), ("3","2",1)], "多路径")
    _expect_fuse([("1","2",3)], "非法 leg")
    _expect_fuse([("1","2",1), ("1","2",2)], "基础边表")
    _expect_fuse([("1","2",1), ("1","2",1)], "基础边表")


# =====================================================================
# 用例 9：时序契约防线 (fail-fast 拦截)
# =====================================================================
def test_case_9_period_contract_guards():
    print("\n" + "=" * 70)
    print("用例 9：时序契约防线 (fail-fast 拦截)")
    print("=" * 70)

    _clear_all_redis()
    UserStats.db().set(PlacementRecalculationService._status_key(PREV_PERIOD), json.dumps({"status": "RUNNING"}))
    try:
        _run(TEST_PERIOD); raise AssertionError("未拦截非 DONE 上期")
    except RuntimeError as e:
        assert "时序违背" in str(e)

    _clear_all_redis()
    _inject_prev_surplus(PREV_PERIOD, "4", remain_1l=1)
    try:
        _run(TEST_PERIOD); raise AssertionError("未拦截哨兵丢失")
    except RuntimeError as e:
        assert "哨兵丢失" in str(e)


# =====================================================================
# 用例 10：幂等性（同期连跑两次零漂移无副作用）
# =====================================================================
def _assert_settle_done(period: str) -> None:
    raw = UserStats.db().get(PlacementRecalculationService._status_key(period))
    assert raw is not None and json.loads(raw).get("status") == "DONE", f"期末状态应为 DONE，实际: {raw}"

def test_case_10_idempotency_run():
    print("\n" + "=" * 70)
    print("用例 10：账本与事件双幂等（同期连跑两次零漂移无副作用）")
    print("=" * 70)
    _clear_all_redis()
    _mock_prev_period_done(TEST_PERIOD)

    _inject_prev_surplus(PREV_PERIOD, "5", remain_1l=1000, remain_2l=200)
    _inject_curr_activity(TEST_PERIOD, "6", pv=300)
    _inject_curr_activity(TEST_PERIOD, "7", pv=400)

    _run(TEST_PERIOD)
    _assert_placement(TEST_PERIOD, "5", pv_1l=300, pv_2l=400, total_1l=1300, total_2l=600, remain_surplus_1l=0, remain_surplus_2l=0)

    ob = PlacementRecalculationServiceForTest.OUTBOX_STREAM_KEY
    tail = UserStats.db().xrevrange(ob, count=1)
    last_id = tail[0][0] if tail else "0-0"
    last_id = last_id.decode() if isinstance(last_id, bytes) else last_id

    _run(TEST_PERIOD)

    # 使用 xread 替代 xrange 的 exclusive bound，兼容 Redis 6.2 以下版本
    delta_streams = UserStats.db().xread({ob: last_id})
    assert delta_streams and len(delta_streams[0][1]) == 1, f"第二遍应恰好产生 1 条事件，实际: {delta_streams}"

    _id, fields = delta_streams[0][1][0]
    payload = fields.get(b"payload") or fields.get("payload")
    assert json.loads(payload)["event_type"] == "PLACEMENT_SETTLEMENT_PERIOD_DONE"

    _assert_placement(TEST_PERIOD, "5", pv_1l=300, pv_2l=400, total_1l=1300, total_2l=600, remain_surplus_1l=0, remain_surplus_2l=0)
    _assert_settle_done(TEST_PERIOD)


# =====================================================================
# 用例 11：脏数据熔断 + 失败路径锁释放 + FAILED 状态
# =====================================================================
def _inject_dirty_record(period: str, key_uid: str, payload_id: str) -> None:
    UserStats(pk=f"{period}:{key_uid}", period=period, id=payload_id, user_id=payload_id).save()

def test_case_11_dirty_data_fuse_lock_release():
    print("\n" + "=" * 70)
    print("用例 11：脏数据熔断 + 失败路径锁释放 + FAILED 状态")
    print("=" * 70)
    _clear_all_redis(); _mock_prev_period_done(TEST_PERIOD)
    _inject_dirty_record(TEST_PERIOD, "12", "99")
    try:
        _run(TEST_PERIOD); raise AssertionError("未拦截脏数据")
    except RuntimeError as e:
        assert "脏数据" in str(e)
    assert not UserStats.db().exists(PlacementRecalculationServiceForTest.GLOBAL_RECALC_LOCK_KEY), "失败路径锁未释放"
    raw = UserStats.db().get(PlacementRecalculationService._status_key(TEST_PERIOD))
    assert json.loads(raw).get("status") == "FAILED", f"失败后状态应为 FAILED: {raw}"


# =====================================================================
# 用例 12：纠偏重算 + 非双轨字段保护
# =====================================================================
def test_case_12_corrective_recalc_field_preservation():
    print("\n" + "=" * 70)
    print("用例 12：纠偏重算 + 非双轨字段保护")
    print("=" * 70)
    _clear_all_redis(); _mock_prev_period_done(TEST_PERIOD)
    s = UserStats(pk=f"{TEST_PERIOD}:5", period=TEST_PERIOD, id="5", user_id="5")
    s.pv = 50; s.gpv = 70
    s.pv_1l = 999; s.total_1l = 999
    # 注入待验证保护的其它非双轨字段
    s.rank = 20
    s.qualified_legs = {"6", "7"}
    s.save()

    _run(TEST_PERIOD)
    _assert_placement(TEST_PERIOD, "5", pv_1l=0, pv_2l=0, total_1l=0, total_2l=0)

    s_after = UserStats.get(f"{TEST_PERIOD}:5")
    assert (s_after.pv or 0) == 50 and (s_after.gpv or 0) == 70, "非双轨字段(pv/gpv)被破坏"
    assert (s_after.rank or 0) == 20, "非双轨字段(rank)被破坏"
    assert set(s_after.qualified_legs or set()) == {"6", "7"}, "非双轨字段(qualified_legs)被破坏"


# =====================================================================
# 用例 13：write_zero_nodes 参数语义单测
# =====================================================================
def test_case_13_write_zero_nodes_flag_semantics():
    print("\n" + "=" * 70)
    print("用例 13：write_zero_nodes 参数语义单测")
    print("=" * 70)
    _clear_all_redis()
    svc = PlacementRecalculationServiceForTest()
    common = dict(redis_conn=UserStats.db(), target_list=["zu1"], gpu_res_dict={},
                  active_pv_dict={}, period=TEST_PERIOD, run_id="tc13", lock=_FakeLock())
    svc._write_back_placement_matrix(write_zero_nodes=False, **common)
    try:
        UserStats.get(f"{TEST_PERIOD}:zu1"); raise AssertionError("False 分支不应物化零节点")
    except NotFoundError:
        pass
    svc._write_back_placement_matrix(write_zero_nodes=True, **common)
    s = UserStats.get(f"{TEST_PERIOD}:zu1")
    assert (s.pv_1l or 0) == 0 and (s.total_1l or 0) == 0

    # 零节点不应触发漂移事件
    assert UserStats.db().xlen(PlacementRecalculationServiceForTest.OUTBOX_STREAM_KEY) == 0, "零节点物化不应发送事件"


# =====================================================================
# 入口
# =====================================================================
def main():
    print(f"\n连接 Dask 调度器: {SCHEDULE_ADDRESS}")

    passed, characterized, skipped, failed = [], [], [], []

    all_cases = (
        test_case_1_placement_basic_accumulation,
        test_case_2_sponsor_pv_pss,
        test_case_3a_merge_semantics,
        test_case_3b_pure_surplus_bridge,
        test_case_3c_gpv_activity_trigger,
        test_case_4_surplus_merge_and_calculate,
        test_case_5_stockist_pv,
        test_case_6_deep_binary_tree_accumulation,
        test_case_7_precision_and_rounding,
        test_case_7b_writeback_rounding_characterization,
        test_case_7c_gpu_aggregation_fidelity,
        test_case_8_closure_guard_fuses,
        test_case_9_period_contract_guards,
        test_case_10_idempotency_run,
        test_case_11_dirty_data_fuse_lock_release,
        test_case_12_corrective_recalc_field_preservation,
        test_case_13_write_zero_nodes_flag_semantics,
    )

    only_case = os.environ.get("ONLY_CASE")
    if only_case:
        all_cases = tuple(
            c for c in all_cases
            if c.__name__ == only_case or c.__name__.startswith(only_case + "_")
        )
        if not all_cases:
            logger.error(f"未找到指定的测试用例: {only_case}")
            raise SystemExit(1)

    client = None
    try:
        client = Client(SCHEDULE_ADDRESS)

        try:
            _validate_required_topology(client)
        except Exception as e:
            logger.exception("环境预检失败 (可能 graph_actor 未发布或图数据异常): %s", e)
            raise SystemExit(1)

        for case_fn in all_cases:
            try:
                res = case_fn()
                if res == "SKIP":
                    skipped.append(case_fn.__name__)
                elif res == "CHARACTERIZATION":
                    characterized.append(case_fn.__name__)
                else:
                    passed.append(case_fn.__name__)
            except AssertionError as e:
                failed.append((case_fn.__name__, str(e)))
                logger.error("用例失败: %s\n%s", case_fn.__name__, e)
            except Exception as e:
                failed.append((case_fn.__name__, f"运行异常: {e!r}"))
                logger.exception("用例运行异常: %s", case_fn.__name__)
    finally:
        if os.environ.get("KEEP_TEST_DATA") == "1":
            logger.info("=== 环境变量 KEEP_TEST_DATA=1 已生效，跳过测试后现场清理 ===")
        else:
            try:
                _clear_all_redis()
            except Exception as e:
                failed.append(("teardown", f"测试后清理失败: {e!r}"))
                logger.exception("测试后清理失败（teardown 兜底），产生死锁泄漏风险")

        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    print("\n" + "=" * 70)
    print(f"需求验收通过: {len(passed)} / 现状锁定(待决策): {len(characterized)} / 跳过: {len(skipped)} / 失败: {len(failed)}")
    for name in passed:
        print(f"  ✓ [PASS] {name}")
    for name in characterized:
        print(f"  ◐ [CHAR] {name}")
    for name in skipped:
        print(f"  - [SKIP] {name}")
    for name, msg in failed:
        print(f"  ✗ [FAIL] {name}: {msg.splitlines()[0]}")
    print("=" * 70)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()