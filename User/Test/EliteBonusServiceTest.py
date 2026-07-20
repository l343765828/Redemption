"""
EliteBonusService 集成测试（真实 Dask 图 + tb_user 真实关系）—— 最终版

采纳两轮外部 code review 的有效意见后的版本。

Dask 地址：tcp://127.0.0.1:8786
推荐关系来自 tb_user（child -> parent，0=根）：
    5 ── 4 ── 3 ──┬── 1 ──┬── 9
                  │       └── 13
                  └── 2 ── 10
    8 ── 7 ;  6 / 11 / 12 为孤立根
主源 user 9，祖先链 9 -> 1(L1) -> 3(L2) -> 4(L3) -> 5(L4)。

──────────────────────────────────────────────────────────────────
两类用例
──────────────────────────────────────────────────────────────────
[普通用例]   断言实现“当前正确行为”，应当 PASS。
[KNOWN-GAP]  断言“需求要求、但当前实现尚未满足”的行为，预期 XFAIL。
             —— 失败 = 服务实现待补，不是测试写错；XPASS = 已修复，请移除标记。
             —— XFAIL 只接受 AssertionError；其它异常一律按 ERROR 处理（见 main）。
             —— CI 口径：默认 strict，XPASS 也会让脚本非零退出，逼迫服务修复后
                把对应用例从 xfail 降级为普通用例；本地临时放行设 EB_XPASS_OK=1。

当前 KNOWN-GAP（均已对照源码确认现象）。按性质分两类，验收时请勿混为一谈：

  ◆ 核心业务缺口（主流程必然受影响，应优先修）：
    G1  退单/失格后未删除 eb_source（_track_bonus_source 只增不删）。
    G1' 即便 source key 残留，snapshot 也应过滤掉无效 SOURCE；当前会产出过期归属。
    G2  累计合格不回填历史下线 source（口径差异，需业务确认）。

  ◇ 防御性/脏数据缺口（仅当外部旁路写入脏数据时才触发，非主流程必错）：
    G3  snapshot 仅按 gpv_real>0 & bonus>0 过滤，不校验 is_qualified。
    G4  snapshot 不校验 SOURCE.bonus_user_id 是否在奖金表 → 可能产出悬空归属。
  （服务自身产出的数据天然满足 “gpv_real>0 ⇒ is_qualified”，正常增量流程不会触发
    G3/G4；它们是针对 ETL/历史数据等旁路写入的防御网。是否升级为硬性要求需业务确认。）

不在本套件覆盖（属其它测试层，刻意不塞进增量服务测试）：
  · PV_PCS / PV_PSS 字段口径 —— 增量入口 update(user_id, pv_delta) 无 PV_PSS 输入，
    应放 SQL / ETL 初始化兼容测试。
  · ELITE_CALC_ID=10 编码约定 —— 增量模型用 is_qualified 布尔表达、不落该编码字段，
    应放配置/编码约定检查测试。
  · BONUS_LAYER 口径 —— 见 test_source_skips_unqualified_nearest_... 的注释；本套件锁定
    的是“当前 Python BFS 距离口径”，若最终要对齐 SQL 的 TOP_DEEP 方向，期望值需重审。

──────────────────────────────────────────────────────────────────
运行（会 flushdb，务必指向测试 Redis）
──────────────────────────────────────────────────────────────────
    export ALLOW_REDIS_TEST_FLUSH=1     # 必须显式开启（脚本不会自动设置）
    python test_elite_bonus_service.py

前置：Dask 在 tcp://127.0.0.1:8786 且已发布 graph_actor（关系=tb_user，启动会校验
descendant/predecessor/level 三列及其取值）；Redis 带 RediSearch；项目根在 PYTHONPATH。
elite_rate 与 snapshot 的 user_info 为“确定性注入”（钉住配置/用户字段以便断言精确值），
与推荐关系无关，不是 mock 关系。
"""

import os
import sys
import logging
from decimal import Decimal
from typing import Dict, List, Any
from unittest.mock import MagicMock

from redis_om import Migrator, NotFoundError
from dask.distributed import Client
from Redishelper.BaseRedisModel import redis_conn
from Model.User.EliteBonusStats import EliteBonusStats
from User.EliteBonusService import EliteBonusService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------- 常量 ----------
PERIOD = 202604
CALC_MONTH = 4
DASK_ADDRESS = "tcp://127.0.0.1:8786"
GRAPH_DATASET = "graph_actor"

# ---------- tb_user 命名用户 ----------
U_LEAF = "9"   # 主源（深度 4 的叶子）
U_P1 = "1"     # 9 的直属父级 (level 1)
U_P2 = "3"     # level 2
U_P3 = "4"     # level 3
U_P4 = "5"     # level 4（根）

# ---------- 启动校验：user 9 完整祖先链（含 predecessor） ----------
EXPECTED_CHAIN_9 = [
    {"descendant": "1", "predecessor": "9", "level": 1},
    {"descendant": "3", "predecessor": "1", "level": 2},
    {"descendant": "4", "predecessor": "3", "level": 3},
    {"descendant": "5", "predecessor": "4", "level": 4},
]


# =====================================================================
# 真实 Dask 连接 + 启动校验
# =====================================================================

_CLIENT: Client = None


def _client() -> Client:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = Client(DASK_ADDRESS, timeout=30)
    return _CLIENT


def precheck():
    """校验 graph_actor 已发布，且 get_allparent(9) 的三列与 tb_user 完全一致。"""
    datasets = set(_client().list_datasets())
    if GRAPH_DATASET not in datasets:
        raise RuntimeError(
            f"调度器 {DASK_ADDRESS} 上未发现已发布的 '{GRAPH_DATASET}'，现有: {sorted(datasets)}。"
        )

    actor = _client().get_dataset(GRAPH_DATASET).result()
    df = actor.get_allparent(U_LEAF).result()

    required = {"descendant", "predecessor", "level"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"get_allparent 缺少必要列: {missing}（实现依赖这三列做路径 B 维护）")

    got = [
        {"descendant": str(r["descendant"]),
         "predecessor": str(r["predecessor"]),
         "level": int(r["level"])}
        for _, r in df.sort_values("level").iterrows()
    ]
    if got != EXPECTED_CHAIN_9:
        raise RuntimeError(
            "线上图关系与 tb_user 不一致（含 predecessor 校验）：\n"
            f"  expected={EXPECTED_CHAIN_9}\n  got     ={got}"
        )
    logger.info("✓ 启动校验通过：graph_actor 已发布，descendant/predecessor/level 与 tb_user 一致。")


# =====================================================================
# Redis 固件 / 确定性注入
# =====================================================================

def _flushdb_test_only():
    if os.environ.get("ALLOW_REDIS_TEST_FLUSH") != "1":
        raise RuntimeError("拒绝执行 flushdb：必须显式设置 ALLOW_REDIS_TEST_FLUSH=1")
    redis_conn.flushdb()


def _reset():
    _flushdb_test_only()
    Migrator().run()                 # flushdb 会清掉 RediSearch 索引，必须重建


def make_rate_loader(rate: str):
    def loader() -> Decimal:
        return Decimal(rate)
    return loader


def pinned_user_info_resolver(user_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    return {
        uid: {
            "user_name": f"User{uid}",
            "real_name": f"Real{uid}",
            "country_id": "CN",
            "parent_uid": str(int(uid) + 1) if uid.isdigit() else "0",
            "top_deep": int(uid) if uid.isdigit() else 0,
        }
        for uid in user_ids
    }


def _make_service(rate: str = "0.15", with_userinfo: bool = False,
                  period: int = PERIOD) -> EliteBonusService:
    svc = EliteBonusService(
        period_num=period,
        calc_month=CALC_MONTH,
        elite_rate_loader=make_rate_loader(rate),
        user_info_resolver=pinned_user_info_resolver if with_userinfo else None,
        dask_address=DASK_ADDRESS,
    )
    svc._dask_client = _client()
    return svc


def _get(uid: str, period: int = PERIOD) -> EliteBonusStats:
    return EliteBonusStats.get(f"{period}:{uid}")


def _src(svc: EliteBonusService, uid: str) -> Dict[str, str]:
    return svc._safe_hgetall(f"eb_source:{svc.period_num}:{uid}")


# #####################################################################
# 普通用例（应 PASS）
# #####################################################################

# ---- §7.1.1 基础合格（路径 A）+ 自归属 layer=0 ----
def test_path_a_basic_and_self_source():
    _reset()
    svc = _make_service(rate="0.15")
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=1000)

    u = _get(U_LEAF)
    assert u.gpv == 1000
    assert u.is_qualified is True
    assert u.qualifying_path == "A"
    assert u.gpv_real == 1000
    assert u.contrib_to_parent == 0
    assert u.estimated_bonus == 150.0

    s = _src(svc, U_LEAF)
    assert s["bonus_user_id"] == U_LEAF
    assert int(s["layer"]) == 0


# ---- §7.1.2 累计合格（金额/资格 + user 1 自归属）----
def test_group_accumulation_qualifies_path_a():
    _reset()
    svc = _make_service(rate="0.15")
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=800)
    svc.update_elite_bonus_incremental(user_id=U_P1, pv_delta=200)

    child = _get(U_LEAF)
    assert child.is_qualified is False
    assert child.contrib_to_parent == 800

    p = _get(U_P1)
    assert p.gpv == 1000                       # 200 自身 + 800 下线汇总
    assert p.is_qualified is True
    assert p.qualifying_path == "A"
    assert p.gpv_real == 1000
    assert p.estimated_bonus == 150.0
    assert p.contrib_to_parent == 0

    s1 = _src(svc, U_P1)
    assert s1["bonus_user_id"] == U_P1
    assert int(s1["layer"]) == 0


# ---- §7.1.3 截断：源用户合格后业绩不上流 ----
def test_qualified_node_truncates_upward_flow():
    _reset()
    svc = _make_service(rate="0.15")
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=1500)

    u = _get(U_LEAF)
    assert u.is_qualified is True
    assert u.qualifying_path == "A"
    assert u.contrib_to_parent == 0

    p = _get(U_P1)
    assert p.gpv == 0                          # 业绩被截断，未上流
    assert p.gpv_real == 0
    # 注：user 1 会因下线 9 合格而连带（路径 B）合格，但 gpv_real=0、无奖金。


# ---- §7.1.4 连带合格（路径 B）----
def test_path_b_connected_qualification():
    _reset()
    svc = _make_service(rate="0.156")
    svc.update_elite_bonus_incremental(user_id=U_P1, pv_delta=200)
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=1000)

    u = _get(U_LEAF)
    assert u.is_qualified is True
    assert u.qualifying_path == "A"
    assert u.contrib_to_parent == 0

    p = _get(U_P1)
    assert p.gpv == 200
    assert U_LEAF in p.qualified_downlines
    assert p.is_qualified is True
    assert p.qualifying_path == "B"
    assert p.gpv_real == 200
    assert p.contrib_to_parent == 0
    assert p.estimated_bonus == 31.2           # 200 × 15.6%

    gp = _get(U_P2)
    assert gp.is_qualified is True             # 路径 B 连带合格
    assert gp.qualifying_path == "B"
    assert U_P1 in gp.qualified_downlines
    assert gp.gpv == 0
    assert gp.gpv_real == 0


# ---- §7.1.5 费率配置生效（12%）----
def test_rate_config_takes_effect():
    _reset()
    svc = _make_service(rate="0.12")
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=1000)
    assert _get(U_LEAF).estimated_bonus == 120.0


# ---- §7.1.6 向下截断不四舍五入 ----
def test_bonus_truncation_not_rounding():
    _reset()
    svc = _make_service(rate="0.156")
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=1001)
    u = _get(U_LEAF)
    assert u.gpv_real == 1001
    assert u.estimated_bonus == 156.15         # 156.156 截断；四舍五入会得 156.16


# ---- §7.2.8 零业绩 ----
def test_zero_pv_no_qualification_no_source():
    _reset()
    svc = _make_service(rate="0.15")
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=0)
    u = _get(U_LEAF)
    assert u.gpv == 0
    assert u.is_qualified is False
    assert u.gpv_real == 0
    assert svc.redis_conn.exists(f"eb_source:{PERIOD}:{U_LEAF}") == 0


# ---- §7.3.10(a) 跳过未合格的最近祖先，归属到“首个合格祖先” ----
def test_source_skips_unqualified_nearest_and_uses_first_qualified_ancestor():
    """预置 user 3(L2)、user 4(L3) 合格，user 1(L1) 未合格；user 9 产 500：
    归属应为 user 3、layer=2。

    ⚠️ 命名说明（采纳 review）：本用例验证的是“跳过未合格的最近祖先 1，命中首个
       合格祖先 3”。由于服务在遇到稳定合格且 delta=0 的祖先(此处 3)即提前停止传播，
       user 4 根本不会被访问——所以本用例**并不**验证“多个合格祖先之间取最小 layer”，
       那一点改由下面的 test_track_bonus_source_keeps_min_layer 直测。

    ⚠️ 口径提示（需业务确认）：Python 的 layer = 源到得奖人的 BFS 距离(最小=最近源头)，
       与 SQL 的 BONUS_LAYER/TOP_DEEP(最小=最靠近网体顶端)方向相反；若要对齐 SQL，
       期望值可能应为更靠近根的 user 4。本用例是“现实现回归”，不等于“业务口径已确认”。"""
    _reset()
    svc = _make_service(rate="0.15")
    EliteBonusStats(id=f"{PERIOD}:{U_P2}", user_id=U_P2, period_num=PERIOD,
                    gpv=1000, gpv_real=1000, is_qualified=True, qualifying_path="A").save()
    EliteBonusStats(id=f"{PERIOD}:{U_P3}", user_id=U_P3, period_num=PERIOD,
                    gpv=1000, gpv_real=1000, is_qualified=True, qualifying_path="A").save()

    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=500)

    s = _src(svc, U_LEAF)
    assert s["bonus_user_id"] == U_P2
    assert int(s["layer"]) == 2


# ---- §7.3.10(b) 直测 _track_bonus_source 的“保留最小 layer” ----
def test_track_bonus_source_keeps_min_layer():
    """不依赖传播/早停，直接验证溯源去重：乱序写入 layer 3 → 2 → 4，应稳定保留最小的 2。"""
    _reset()
    svc = _make_service(rate="0.15")

    svc._track_bonus_source(U_LEAF, U_P3, layer=3)   # 首次写入 → 3
    s = _src(svc, U_LEAF)
    assert s["bonus_user_id"] == U_P3
    assert int(s["layer"]) == 3

    svc._track_bonus_source(U_LEAF, U_P2, layer=2)   # 2 < 3 → 覆盖为 2
    s = _src(svc, U_LEAF)
    assert s["bonus_user_id"] == U_P2
    assert int(s["layer"]) == 2

    svc._track_bonus_source(U_LEAF, U_P4, layer=4)   # 4 > 2 → 忽略
    s = _src(svc, U_LEAF)
    assert s["bonus_user_id"] == U_P2
    assert int(s["layer"]) == 2


# ---- §7.3.11 无合格上级 → 不写 SOURCE（与 SQL 的已知口径差异）----
def test_no_qualified_upline_writes_no_source():
    _reset()
    svc = _make_service(rate="0.15")
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=500)
    assert _get(U_LEAF).is_qualified is False
    assert svc.redis_conn.exists(f"eb_source:{PERIOD}:{U_LEAF}") == 0


# ---- 退单取消资格（仅校验 stats；source 残留见 KNOWN-GAP G1）----
def test_refund_dequalifies_stats():
    _reset()
    svc = _make_service(rate="0.15")
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=1000)
    assert _get(U_LEAF).is_qualified is True

    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=-1000)
    u = _get(U_LEAF)
    assert u.gpv == 0
    assert u.is_qualified is False
    assert u.gpv_real == 0
    assert u.estimated_bonus == 0.0


# ---- 退单负值边界保护 ----
def test_refund_boundary_guard_skips_negative_pv():
    _reset()
    svc = _make_service(rate="0.15")
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=30)
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=-50)   # 30-50<0 → 跳过
    u = _get(U_LEAF)
    assert u.pv_pcs == 30
    assert u.gpv == 30
    assert u.is_qualified is False


# ---- §2.2 期末快照：字段映射（夹具补齐为合格态）----
def test_snapshot_output_mapping():
    _reset()
    svc = _make_service(rate="0.156", with_userinfo=True)

    EliteBonusStats(id=f"{PERIOD}:88", user_id="88", period_num=PERIOD,
                    gpv=2000, gpv_real=2000, is_qualified=True, qualifying_path="A",
                    contrib_to_parent=0, estimated_bonus=312.0).save()
    EliteBonusStats(id=f"{PERIOD}:99", user_id="99", period_num=PERIOD,
                    gpv=1000, gpv_real=1000, is_qualified=True, qualifying_path="A",
                    contrib_to_parent=0, estimated_bonus=156.0, pv_pcs=50).save()
    svc.redis_conn.hset(f"eb_source:{PERIOD}:99",
                        mapping={"layer": 1, "bonus_user_id": "88"})

    db_mock = MagicMock()
    res = svc.snapshot_period_to_db(db_executor=db_mock)
    assert res["bonus_count"] == 2
    assert res["source_count"] == 1

    calls = db_mock.call_args_list
    assert len(calls) == 2

    bonus_table, bonus_rows = calls[0][0]
    assert bonus_table == "AR_CALC_BONUS_E"
    row88 = next(r for r in bonus_rows if r["user_id"] == "88")
    assert row88["period_num"] == PERIOD
    assert row88["gpv_real"] == 2000
    assert row88["e_rate"] == 0.156
    assert row88["country_id"] == "CN"
    assert row88["parent_uid"] == "89"
    assert len(row88["id"]) == 22

    source_table, source_rows = calls[1][0]
    assert source_table == "AR_CALC_BONUS_E_SOURCE"
    src = source_rows[0]
    assert src["source_user_id"] == "99"
    assert src["source_pv"] == 50
    assert src["bonus_user_id"] == "88"
    assert src["bonus_layer"] == 1
    assert src["source_real_name"] == "Real99"
    assert src["bonus_real_name"] == "Real88"


# ---- 快照是只读、可重复读（注意：这≠DB 幂等，见下一条）----
def test_snapshot_is_read_only_and_repeatable():
    """连续两次 snapshot 返回相同结果，且不改动 Redis（只读、可重复读）。
    ⚠️ 这只证明读侧可重复，**不**证明对 DB 幂等——见
       test_snapshot_calls_executor_every_run_not_db_idempotent。"""
    _reset()
    svc = _make_service(rate="0.156", with_userinfo=True)
    EliteBonusStats(id=f"{PERIOD}:88", user_id="88", period_num=PERIOD,
                    gpv=2000, gpv_real=2000, is_qualified=True, qualifying_path="A",
                    estimated_bonus=312.0).save()
    svc.redis_conn.hset(f"eb_source:{PERIOD}:99",
                        mapping={"layer": 1, "bonus_user_id": "88"})

    r1 = svc.snapshot_period_to_db(db_executor=MagicMock())
    r2 = svc.snapshot_period_to_db(db_executor=MagicMock())
    assert r1 == r2                            # 两次结果一致
    assert _get("88").gpv_real == 2000         # 快照不改动 Redis
    assert svc.redis_conn.exists(f"eb_source:{PERIOD}:99") == 1


# ---- 文档化：snapshot 本身不保证 DB 幂等 ----
def test_snapshot_calls_executor_every_run_not_db_idempotent():
    """每次调用都会把同一批 bonus_rows 交给 db_executor 落盘。
    若真实 db_executor 是 INSERT，重复执行将产生重复行——
    DB 幂等需由 upsert 或“重跑前 cleanup_period”保证，不由本函数负责。
    本用例锁定该设计边界：两次 snapshot → AR_CALC_BONUS_E 被调用 2 次。"""
    _reset()
    svc = _make_service(rate="0.156", with_userinfo=True)
    EliteBonusStats(id=f"{PERIOD}:88", user_id="88", period_num=PERIOD,
                    gpv=2000, gpv_real=2000, is_qualified=True, qualifying_path="A",
                    estimated_bonus=312.0).save()

    db_mock = MagicMock()
    svc.snapshot_period_to_db(db_executor=db_mock)
    svc.snapshot_period_to_db(db_executor=db_mock)

    bonus_calls = [c for c in db_mock.call_args_list if c[0][0] == "AR_CALC_BONUS_E"]
    assert len(bonus_calls) == 2               # 非 DB 幂等：重复落盘


# ---- 跨期独立计算：202604 与 202605 互不干扰 ----
def test_cross_period_independent_calc():
    _reset()
    _make_service(rate="0.15", period=202604).update_elite_bonus_incremental(U_LEAF, 1000)
    _make_service(rate="0.15", period=202605).update_elite_bonus_incremental(U_LEAF, 500)

    a = _get(U_LEAF, period=202604)
    assert a.gpv == 1000 and a.is_qualified is True
    b = _get(U_LEAF, period=202605)
    assert b.gpv == 500 and b.is_qualified is False


# ---- §7.4 清理按周期隔离：stats + source + lock 三类都清，且只清本期 ----
def test_cleanup_clears_stats_source_lock_period_scoped():
    """cleanup_period 应清掉本期的 stats + eb_source + eb_lock，其它周期不受影响。
    注意：stats 用裸 pattern `elite_bonus_stats:{period}:*` 删除，能否命中取决于
    redis_om 真实 key 前缀（global/model_key_prefix 拼接）；若该 NotFoundError 断言
    失败，多半是 pattern 与真实 key 不一致——值得核对。"""
    _reset()
    EliteBonusStats(id="202604:9", user_id="9", period_num=202604,
                    gpv=1000, is_qualified=True, estimated_bonus=150.0).save()
    EliteBonusStats(id="202605:9", user_id="9", period_num=202605,
                    gpv=1000, is_qualified=True, estimated_bonus=150.0).save()
    conn = redis_conn
    conn.hset("eb_source:202604:9", mapping={"layer": 0, "bonus_user_id": "9"})
    conn.hset("eb_source:202605:9", mapping={"layer": 0, "bonus_user_id": "9"})
    conn.set("eb_lock:202604:9", "dummy")
    conn.set("eb_lock:202605:9", "dummy")

    _make_service(rate="0.15", period=202604).cleanup_period()

    # stats：本期清，下期留
    try:
        _get("9", period=202604)
        assert False, "202604:9 stats 应已被清"
    except NotFoundError:
        pass
    assert _get("9", period=202605).is_qualified is True
    # source：本期清，下期留
    assert conn.exists("eb_source:202604:9") == 0
    assert conn.exists("eb_source:202605:9") == 1
    # lock：本期清，下期留
    assert conn.exists("eb_lock:202604:9") == 0
    assert conn.exists("eb_lock:202605:9") == 1


# #####################################################################
# KNOWN-GAP 用例（预期 XFAIL；失败=服务待补，不是测试错）
# #####################################################################

# ---- G1: 退单/失格后应删除 eb_source key ----
def test_GAP_refund_clears_source_key():
    _reset()
    svc = _make_service(rate="0.15", with_userinfo=True)
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=1000)
    assert svc.redis_conn.exists(f"eb_source:{PERIOD}:{U_LEAF}") == 1   # +1000 写入自归属

    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=-1000)  # 退单失格
    # 期望：失格后不应残留 source key（当前实现不删 → XFAIL）
    assert svc.redis_conn.exists(f"eb_source:{PERIOD}:{U_LEAF}") == 0


# ---- G1': 即便 key 残留，snapshot 也应过滤掉过期 SOURCE ----
def test_GAP_refund_snapshot_drops_stale_source_even_if_key_left():
    _reset()
    svc = _make_service(rate="0.15", with_userinfo=True)
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=1000)
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=-1000)

    res = svc.snapshot_period_to_db(db_executor=MagicMock())
    assert res["bonus_count"] == 0             # 失格者无奖金（当前已满足）
    assert res["source_count"] == 0            # 但当前仍会产出过期 SOURCE → XFAIL


# ---- G2: 累计合格应回填历史下线 source（user 9 → user 1, layer 1）----
def test_GAP_group_accumulation_backfills_child_source():
    _reset()
    svc = _make_service(rate="0.15")
    svc.update_elite_bonus_incremental(user_id=U_LEAF, pv_delta=800)    # 9 早于 1 合格时上推
    svc.update_elite_bonus_incremental(user_id=U_P1, pv_delta=200)      # 1 因自身 200 合格

    assert _get(U_P1).is_qualified is True
    # 期望：早先贡献 800 的 user 9，最终应归属到新合格的 user 1（当前不回填 → XFAIL）
    s9 = _src(svc, U_LEAF)
    assert s9.get("bonus_user_id") == U_P1
    assert int(s9.get("layer", -1)) == 1


# ---- G3: snapshot 应跳过未合格的脏记录（is_qualified=False 不得落库）----
def test_GAP_snapshot_skips_not_qualified_dirty_record():
    _reset()
    svc = _make_service(rate="0.156", with_userinfo=True)
    EliteBonusStats(id=f"{PERIOD}:77", user_id="77", period_num=PERIOD,
                    gpv_real=1000, estimated_bonus=156.0, is_qualified=False).save()
    res = svc.snapshot_period_to_db(db_executor=MagicMock())
    assert res["bonus_count"] == 0             # 未合格不应入奖金表（当前不校验 → XFAIL）


# ---- G4: SOURCE.bonus_user_id 必须存在于奖金表（悬空归属应剔除）----
def test_GAP_snapshot_drops_source_without_bonus_row():
    _reset()
    svc = _make_service(rate="0.156", with_userinfo=True)
    EliteBonusStats(id=f"{PERIOD}:88", user_id="88", period_num=PERIOD,
                    gpv=2000, gpv_real=2000, is_qualified=True, qualifying_path="A",
                    estimated_bonus=312.0).save()
    svc.redis_conn.hset(f"eb_source:{PERIOD}:99", mapping={"layer": 1, "bonus_user_id": "88"})
    svc.redis_conn.hset(f"eb_source:{PERIOD}:55", mapping={"layer": 1, "bonus_user_id": "66"})  # 66 无奖金

    res = svc.snapshot_period_to_db(db_executor=MagicMock())
    assert res["bonus_count"] == 1
    assert res["source_count"] == 1            # 期望剔除悬空，仅保留 99→88（当前=2 → XFAIL）


# =====================================================================
# Main
# =====================================================================
if __name__ == "__main__":
    # —— 安全闸门：不自动开启 flushdb ——
    if os.environ.get("ALLOW_REDIS_TEST_FLUSH") != "1":
        print("拒绝运行：本套件会 flushdb。请仅在测试 Redis 上显式 `export ALLOW_REDIS_TEST_FLUSH=1`。")
        sys.exit(3)
    try:
        kw = redis_conn.connection_pool.connection_kwargs
        print(f"⚠ 即将对 Redis 执行 flushdb → host={kw.get('host')} port={kw.get('port')} db={kw.get('db')}；"
              f"请确认这是测试库。")
    except Exception:
        print("⚠ 即将对当前 Redis 执行 flushdb；请确认这是测试库。")

    print("\n=== 启动校验（Dask 连接 + tb_user 关系/predecessor 一致性） ===")
    try:
        precheck()
    except Exception as e:
        print(f"✗ 启动校验失败：{type(e).__name__}: {e}")
        try:
            if _CLIENT is not None:
                _CLIENT.close()
        except Exception:
            pass
        sys.exit(2)

    # (名称, 函数, xfail_原因 or None)
    tests = [
        ("§7.1.1 基础合格 + 自归属",            test_path_a_basic_and_self_source, None),
        ("§7.1.2 下线汇总累计合格",              test_group_accumulation_qualifies_path_a, None),
        ("§7.1.3 合格后业绩截断不上流",          test_qualified_node_truncates_upward_flow, None),
        ("§7.1.4 连带合格（路径 B）",            test_path_b_connected_qualification, None),
        ("§7.1.5 费率配置生效（12%）",           test_rate_config_takes_effect, None),
        ("§7.1.6 向下截断不四舍五入",            test_bonus_truncation_not_rounding, None),
        ("§7.2.8 零业绩不合格不溯源",            test_zero_pv_no_qualification_no_source, None),
        ("§7.3.10a 跳过未合格/命中首个合格祖先", test_source_skips_unqualified_nearest_and_uses_first_qualified_ancestor, None),
        ("§7.3.10b 溯源保留最小 layer(直测)",    test_track_bonus_source_keeps_min_layer, None),
        ("§7.3.11 无合格上级不写 SOURCE",        test_no_qualified_upline_writes_no_source, None),
        ("退单取消资格(stats)",                  test_refund_dequalifies_stats, None),
        ("退单负值边界保护",                     test_refund_boundary_guard_skips_negative_pv, None),
        ("§2.2 期末快照字段映射",                test_snapshot_output_mapping, None),
        ("快照只读可重复读",                     test_snapshot_is_read_only_and_repeatable, None),
        ("快照非 DB 幂等(每次都落盘)",           test_snapshot_calls_executor_every_run_not_db_idempotent, None),
        ("跨期独立计算",                         test_cross_period_independent_calc, None),
        ("清理:stats+source+lock 按周期隔离",    test_cleanup_clears_stats_source_lock_period_scoped, None),
        # —— KNOWN-GAP（预期 XFAIL）——
        ("[G1] 退单后删除 source key",           test_GAP_refund_clears_source_key,
         "[核心] 失格后未删除 eb_source"),
        ("[G1'] 退单后快照过滤过期 SOURCE",      test_GAP_refund_snapshot_drops_stale_source_even_if_key_left,
         "[核心] snapshot 不过滤过期/无效 SOURCE"),
        ("[G2] 累计合格回填下线 source",         test_GAP_group_accumulation_backfills_child_source,
         "[核心] 历史下线 source 不回填（口径差异，需业务确认）"),
        ("[G3] 快照跳过未合格脏数据",            test_GAP_snapshot_skips_not_qualified_dirty_record,
         "[防御性] snapshot 不校验 is_qualified（仅旁路脏数据触发，需业务确认）"),
        ("[G4] 快照剔除悬空 SOURCE",             test_GAP_snapshot_drops_source_without_bonus_row,
         "[防御性] snapshot 不校验 bonus_user 是否在奖金表（仅旁路脏数据触发）"),
    ]

    passed = 0
    failed, errored, xfailed, xpassed = [], [], [], []
    for name, fn, xfail in tests:
        print(f"\n--- 运行: {name} ---")
        try:
            fn()
            if xfail:
                xpassed.append(name)
                print(f"⚠ XPASS {name}\n        服务似乎已修复，建议移除 xfail 标记（原缺口：{xfail}）")
            else:
                passed += 1
                print(f"✓ PASS  {name}")
        except AssertionError as e:
            # 只有 AssertionError 才视为“预期内的已知缺口”
            if xfail:
                xfailed.append(name)
                print(f"✗→XFAIL {name}（已知缺口，符合预期）\n        缺口: {xfail}\n        现象: 断言失败: {e}")
            else:
                failed.append(name)
                print(f"✗ FAIL  {name}\n        断言失败: {e}")
        except Exception as e:
            # 非 AssertionError（Redis/Dask/字段/导入/NotFoundError 等）一律算 ERROR，
            # 即使 xfail=True 也不吞——避免“什么错都能吞”的保护伞（采纳 review 主要问题 1）
            import traceback
            errored.append(name)
            tag = "（xfail 用例，但非断言异常，按 ERROR 处理）" if xfail else ""
            print(f"✗ ERROR {name}{tag}\n        意外异常: {type(e).__name__}: {e}")
            traceback.print_exc()

    try:
        if _CLIENT is not None:
            _CLIENT.close()
    except Exception:
        pass

    # 默认 strict：XPASS（已知缺口的用例意外通过）也算失败，逼迫服务修复后
    # 把该用例从 xfail 降级为普通用例。本地临时放行：EB_XPASS_OK=1。
    strict_xpass = os.environ.get("EB_XPASS_OK") != "1"
    real_failed = failed + errored + (xpassed if strict_xpass else [])

    print("\n" + "=" * 64)
    print(f"PASS {passed}  |  FAIL {len(failed)}  |  ERROR {len(errored)}  "
          f"|  XFAIL {len(xfailed)}  |  XPASS {len(xpassed)}   (共 {len(tests)})")
    if xfailed:
        print(f"XFAIL（已知服务缺口，预期内）: {xfailed}")
    if xpassed:
        if strict_xpass:
            print(f"XPASS（视为失败）: {xpassed}")
            print("  → 这些 KNOWN-GAP 已不再复现，说明服务可能已修复："
                  "请将对应用例从 xfail 降级为普通用例并更新断言；本地临时放行设 EB_XPASS_OK=1。")
        else:
            print(f"XPASS（EB_XPASS_OK=1 已放行，不计失败）: {xpassed}")
    if real_failed:
        print(f"需要关注的失败/错误/XPASS: {real_failed}")
        sys.exit(1)
    print("普通用例全部通过 ✓（KNOWN-GAP 的 XFAIL 属预期）")