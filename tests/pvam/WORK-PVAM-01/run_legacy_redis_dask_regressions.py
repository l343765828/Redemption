"""在冻结 scope 内运行受 PVAM 影响的旧 Redis/Dask 回归套件。"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _require_flush_permission() -> None:
    if os.environ.get("ALLOW_REDIS_TEST_FLUSH") != "1":
        raise RuntimeError(
            "拒绝运行：套件会 flushdb；请确认使用专用测试 Redis，"
            "并显式设置 ALLOW_REDIS_TEST_FLUSH=1。"
        )


def _publish_test_01(redis_client) -> None:
    """清库后显式重建测试态 01；不改变 production provider 的 fail-loud 合同。"""

    from Redishelper.PVAmountConfigBootstrap import publish_manual_bootstrap

    publish_manual_bootstrap(
        1,
        expected_active_version=None,
        redis_client=redis_client,
    )


def _warn_redis_target(redis_client) -> None:
    """在首次 flushdb 前显示实际目标，供操作人员再次核对测试库。"""

    try:
        options = redis_client.connection_pool.connection_kwargs
        print(
            "⚠ 即将对 Redis 执行 flushdb → "
            f"host={options.get('host')} port={options.get('port')} "
            f"db={options.get('db')}；请确认这是测试库。"
        )
    except Exception:
        print("⚠ 即将对当前 Redis 执行 flushdb；请确认这是测试库。")


def run_user_stats() -> None:
    from User.Test import UserStatsServiceTests as suite

    _warn_redis_target(suite.UserStats.db())
    original_flush = suite._flushdb_test_only

    # region 测试清库后重建 PVAM 配置
    def flush_and_publish_01() -> None:
        original_flush()
        _publish_test_01(suite.UserStats.db())

    suite._flushdb_test_only = flush_and_publish_01
    # endregion

    suite.main()


def _elite_precheck(suite) -> None:
    """按 graph_actor 的正式 ancestor 输出校验测试关系链。"""

    # region 获取并验证图数据集
    datasets = set(suite._client().list_datasets())
    if suite.GRAPH_DATASET not in datasets:
        raise RuntimeError(
            f"调度器 {suite.DASK_ADDRESS} 上未发现已发布的 "
            f"'{suite.GRAPH_DATASET}'，现有: {sorted(datasets)}。"
        )

    actor = suite._client().get_dataset(suite.GRAPH_DATASET).result()
    frame = actor.get_allparent(suite.U_LEAF).result()
    required_columns = {"ancestor", "predecessor", "level"}
    missing_columns = required_columns - set(frame.columns)
    if missing_columns:
        raise RuntimeError(f"get_allparent 缺少必要列: {missing_columns}")
    # endregion

    # region 校验祖先链
    got = [
        {
            "descendant": str(row["ancestor"]),
            "predecessor": str(row["predecessor"]),
            "level": int(row["level"]),
        }
        for _, row in frame.sort_values("level").iterrows()
    ]
    if got != suite.EXPECTED_CHAIN_9:
        raise RuntimeError(
            "线上图关系与 tb_user 不一致（含 predecessor 校验）：\n"
            f"  expected={suite.EXPECTED_CHAIN_9}\n  got     ={got}"
        )
    # endregion


def _run_elite_functions(suite) -> None:
    # region 收集普通用例与已知缺口用例
    tests = [
        (name, function, name.startswith("test_GAP_"))
        for name, function in vars(suite).items()
        if name.startswith("test_") and callable(function)
    ]
    passed = 0
    failed = []
    errored = []
    xfailed = []
    xpassed = []
    # endregion

    # region 执行并分类结果
    for name, function, is_xfail in tests:
        print(f"\n--- 运行: {name} ---")
        try:
            function()
            if is_xfail:
                xpassed.append(name)
                print(f"⚠ XPASS {name}")
            else:
                passed += 1
                print(f"✓ PASS  {name}")
        except AssertionError as exc:
            if is_xfail:
                xfailed.append(name)
                print(f"✗→XFAIL {name}\n        断言失败: {exc}")
            else:
                failed.append(name)
                print(f"✗ FAIL  {name}\n        断言失败: {exc}")
        except Exception as exc:
            errored.append(name)
            print(f"✗ ERROR {name}\n        意外异常: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    # endregion

    # region 汇总并保持原套件的 strict XPASS 口径
    strict_xpass = os.environ.get("EB_XPASS_OK") != "1"
    real_failed = failed + errored + (xpassed if strict_xpass else [])
    print("\n" + "=" * 64)
    print(
        f"PASS {passed}  |  FAIL {len(failed)}  |  ERROR {len(errored)}  "
        f"|  XFAIL {len(xfailed)}  |  XPASS {len(xpassed)}   (共 {len(tests)})"
    )
    if real_failed:
        raise SystemExit(1)
    # endregion


def run_elite_bonus() -> None:
    from User.Test import EliteBonusServiceTest as suite

    _warn_redis_target(suite.redis_conn)
    original_reset = suite._reset

    # region 测试清库后重建 PVAM 配置
    def reset_and_publish_01() -> None:
        original_reset()
        _publish_test_01(suite.redis_conn)

    suite._reset = reset_and_publish_01
    # endregion

    try:
        _elite_precheck(suite)
        _run_elite_functions(suite)
    finally:
        if suite._CLIENT is not None:
            suite._CLIENT.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行会清空专用测试 Redis 的 PVAM 旧链路回归。",
    )
    parser.add_argument(
        "suite",
        choices=("user-stats", "elite-bonus"),
        help="选择要执行的旧回归套件。",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    _require_flush_permission()

    runners: dict[str, Callable[[], None]] = {
        "user-stats": run_user_stats,
        "elite-bonus": run_elite_bonus,
    }
    runners[args.suite]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
