import logging
import sys

import cudf
import dask_cudf
import pandas as pd
import numpy as np
from Common.BonusConfig import ConfigSnapshot
from unittest.mock import patch
from dask_cuda import LocalCUDACluster
from dask.distributed import Client

# 假设该模块名为 PEBonusBatchService
from User.PEBonusService import PEBonusService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [IntegrationTest] %(message)s'
)
logger = logging.getLogger(__name__)


# =====================================================================
# 辅助与数据初始化方法
# =====================================================================

def _dummy_graph_inputs():
    """构造合法结构的 Dummy 图输入，仅用于通过 execute_batch 的前置校验
    （真实图紧缩逻辑由 mock 替代）。"""
    dummy_users = dask_cudf.from_cudf(cudf.DataFrame({"src": [], "dst": []}), npartitions=1)
    dummy_stats = dask_cudf.from_cudf(cudf.DataFrame({"user_id": []}), npartitions=1)
    return dummy_users, dummy_stats


def _pe_config_snapshot(period_num: int, calc_month: int) -> ConfigSnapshot:
    """为 GPU UAT 固定显式费率输入，避免测试入口绕过 WORK-03 快照合同。"""
    return ConfigSnapshot.from_rows(
        [{"config_name": "proEliteRate", "type": "bonus", "value": "15"}],
        period_num=period_num,
        calc_month=calc_month,
        source="pe-gpu-uat-fixture",
        source_version="WORK-PVAM-02",
    )


def _get_test_data():
    """构造契约要求的上游数据源（覆盖用例 1-4、5a/5b）。"""
    period_num = 202606
    calc_month = 6

    # 1. 模拟网体紧缩产出 (AR_CALC_LV_ELITE)
    pdf_elite = pd.DataFrame([
        # 用例1 & 4：1,500.99 PV 按 micro-units 进入，最终 22,514 cents。
        {'PERIOD_NUM': period_num, 'CALC_MONTH': calc_month, 'USER_ID': 100, 'PARENT_UID': 0, 'GPV_REAL': 0,
         'GPV_UNREAL': 500_550_000, 'LAST_ELITE_CALC_ID': 20},
        {'PERIOD_NUM': period_num, 'CALC_MONTH': calc_month, 'USER_ID': 101, 'PARENT_UID': 100, 'GPV_REAL': 1_000_440_000,
         'GPV_UNREAL': 0, 'LAST_ELITE_CALC_ID': 10},
        # 用例2：级别过滤 (Elite 未达 PE 门槛)
        {'PERIOD_NUM': period_num, 'CALC_MONTH': calc_month, 'USER_ID': 200, 'PARENT_UID': 0, 'GPV_REAL': 2_000_000_000,
         'GPV_UNREAL': 0, 'LAST_ELITE_CALC_ID': 10},
        # 用例3：不活跃(300) 与 cudf-null 空值兜底(400: GPV_UNREAL=None)
        {'PERIOD_NUM': period_num, 'CALC_MONTH': calc_month, 'USER_ID': 300, 'PARENT_UID': 0, 'GPV_REAL': 0,
         'GPV_UNREAL': 1_000_000_000, 'LAST_ELITE_CALC_ID': 30},
        {'PERIOD_NUM': period_num, 'CALC_MONTH': calc_month, 'USER_ID': 400, 'PARENT_UID': 0, 'GPV_REAL': 0,
         'GPV_UNREAL': None, 'LAST_ELITE_CALC_ID': 20},
        # 挂载 401：迫使 400 进入 Source 拆分(detail_a)，使 400 的 Source fail-closed 断言非空真
        {'PERIOD_NUM': period_num, 'CALC_MONTH': calc_month, 'USER_ID': 401, 'PARENT_UID': 400, 'GPV_REAL': 1_000_000_000,
         'GPV_UNREAL': 0, 'LAST_ELITE_CALC_ID': 10},
    ])

    # 2. 模拟活跃状态 (AR_USER_PERF)
    pdf_perf = pd.DataFrame([
        {'PERIOD_NUM': period_num, 'USER_ID': 100, 'IS_ACTIVE': 1},
        {'PERIOD_NUM': period_num, 'USER_ID': 200, 'IS_ACTIVE': 1},
        {'PERIOD_NUM': period_num, 'USER_ID': 300, 'IS_ACTIVE': 0},
        # 跨期数据(上期)，验证 AR_USER_PERF 的 PERIOD_NUM 过滤
        {'PERIOD_NUM': 202605, 'USER_ID': 400, 'IS_ACTIVE': 1},
    ])

    # 3. 模拟用户维表 (UserInfo)
    pdf_user = pd.DataFrame({
        'id': [100, 101, 200, 300, 400, 401],
        'country_id': [1, 1, 1, 1, 2, 2],
        'user_name': [f'U{i}' for i in [100, 101, 200, 300, 400, 401]],
        'real_name': [f'RN{i}' for i in [100, 101, 200, 300, 400, 401]],
    })

    return {
        'period_num': period_num,
        'calc_month': calc_month,
        # nan_as_null=True：把 None 强制转为真实 cudf-null（Arrow validity mask），忠实模拟 SQL 的 IFNULL 语义
        'ddf_elite_mock': dask_cudf.from_cudf(cudf.from_pandas(pdf_elite, nan_as_null=True), npartitions=1),
        'ddf_perf': dask_cudf.from_cudf(cudf.from_pandas(pdf_perf), npartitions=1),
        'ddf_user': dask_cudf.from_cudf(cudf.from_pandas(pdf_user), npartitions=1),
    }


# =====================================================================
# 测试用例
# =====================================================================

def test_execute_batch_pe_rules(service: PEBonusService, test_data: dict):
    """用例 1-4 主路径：基数、向下截断、级别硬过滤、合法来源、活跃打标(fail-closed)、
    AR_USER_PERF 周期过滤、cudf-null 兜底、Source 拆分。"""
    dummy_users, dummy_stats = _dummy_graph_inputs()

    with patch.object(service, '_reconstruct_elite_snapshot', return_value=test_data['ddf_elite_mock']):
        results = service.execute_batch(
            period_num=test_data['period_num'],
            calc_month=test_data['calc_month'],
            ddf_users=dummy_users,
            ddf_stats=dummy_stats,
            ddf_user=test_data['ddf_user'],
            ddf_user_perf=test_data['ddf_perf'],
        )

        df_main = results['AR_CALC_BONUS_PE'].compute().to_pandas()
        df_source = results['AR_CALC_BONUS_PE_SOURCE'].compute().to_pandas()

        # ========== 验证 1：级别硬过滤 & 合法来源 ==========
        assert 200 not in df_main['USER_ID'].values, "硬过滤失败：Elite(<20) 不应进主表"
        assert 101 not in df_main['USER_ID'].values, "硬过滤失败：Elite(<20) 下级不应进主表"
        assert 200 not in df_source['BONUS_USER_ID'].values, "硬过滤失败：未达 PE 者不能作为奖金得主"
        assert 101 not in df_source['BONUS_USER_ID'].values, "硬过滤失败：未达 PE 下级不能作为奖金得主"
        assert 101 in df_source['SOURCE_USER_ID'].values, "来源过滤错误：非合格下级必须可作为来源进入 Source"

        # 得主集合应精确等于 PE+ 用户（防止多算/漏算）
        assert set(df_main['USER_ID'].astype(int).tolist()) == {100, 300, 400}
        assert set(df_source['BONUS_USER_ID'].astype(int).tolist()) == {100, 300, 400}

        # ========== 验证 2：截断逻辑 & 国别整型映射 ==========
        user_100_main = df_main[df_main['USER_ID'] == 100].iloc[0]
        assert user_100_main['COUNTRY_ID'] == 1, "COUNTRY_ID 维表映射/整型转换失败"
        assert int(user_100_main['TOTAL_BASE_GPV']) == 1_500_990_000, "基数累加错误"
        assert int(user_100_main['BONUS_PE_CENTS']) == 22_514, "截断错误：应为 22,514 cents，不可四舍五入为 22,515 cents"

        # ========== 验证 3：活跃 fail-closed、周期过滤、cudf-null 兜底 ==========
        assert user_100_main['IS_ACTIVE'] == 1, "活跃状态映射错误"

        # 300：不活跃但仍计算金额 —— 证明"只打标、不拦截"
        user_300_main = df_main[df_main['USER_ID'] == 300].iloc[0]
        assert user_300_main['IS_ACTIVE'] == 0, "活跃状态未同步"
        assert int(user_300_main['TOTAL_BASE_GPV']) == 1_000_000_000
        assert int(user_300_main['BONUS_PE_CENTS']) == 15_000

        # 400：仅有上期 perf → 周期过滤拦截 + fail-closed=0；GPV_UNREAL=null 不致 NaN
        user_400_main = df_main[df_main['USER_ID'] == 400].iloc[0]
        assert user_400_main['IS_ACTIVE'] == 0, "周期过滤失效：跨期活跃记录被错误继承"
        assert not pd.isna(user_400_main['TOTAL_BASE_GPV']), "空值兜底失败：cudf-null 导致基数为 NaN"
        assert int(user_400_main['TOTAL_BASE_GPV']) == 1_000_000_000  # 下级 401 的 1,000 PV micro-units + 本人 null→0
        assert int(user_400_main['BONUS_PE_CENTS']) == 15_000

        # Source 表 fail-closed —— 先断非空，杜绝 .all() 在空集上的"空真"
        s100 = df_source[df_source['BONUS_USER_ID'] == 100]
        assert len(s100) > 0
        assert (s100['IS_ACTIVE'] == 1).all(), "Source 活跃快照映射错误"

        s300 = df_source[df_source['BONUS_USER_ID'] == 300]
        assert len(s300) > 0, "测试数据错误：300 必须至少有一条 Source"
        assert (s300['IS_ACTIVE'] == 0).all(), "Source fail-closed 失败：300 应为 0"

        s400 = df_source[df_source['BONUS_USER_ID'] == 400]
        assert len(s400) > 0, "测试数据错误：400 必须至少有一条 Source"
        assert (s400['IS_ACTIVE'] == 0).all(), "Source 周期过滤 fail-closed 失败：400 应为 0"

        # 费率固定为 150,000 ppm。
        assert (df_main['PE_RATE_PPM'] == 150_000).all(), "主表 PE_RATE_PPM 不为 150,000"
        assert (df_source['PE_RATE_PPM'] == 150_000).all(), "Source 表 PE_RATE_PPM 不为 150,000"

        # ========== 验证 4：Source 拆分 ==========
        assert len(s100) == 2, "Source 拆分异常：下级 GPV_REAL 与本人 GPV_UNREAL 必须分拆为两行"
        src_real = s100[s100['SOURCE_USER_ID'] == 101].iloc[0]
        assert int(src_real['SOURCE_GPV']) == 1_000_440_000
        assert int(src_real['SOURCE_GPV_UNREAL']) == 0
        src_unreal = s100[s100['SOURCE_USER_ID'] == 100].iloc[0]
        assert int(src_unreal['SOURCE_GPV']) == 0
        assert int(src_unreal['SOURCE_GPV_UNREAL']) == 500_550_000


def test_execute_batch_perf_same_key_conflict_raise(service: PEBonusService, test_data: dict):
    """用例 5a：AR_USER_PERF 同期同人、值不同的重复记录，必须被 _dedup_or_raise 熔断。"""
    dummy_users, dummy_stats = _dummy_graph_inputs()

    bad_perf = pd.DataFrame([
        {'PERIOD_NUM': 202606, 'USER_ID': 100, 'IS_ACTIVE': 1},
        {'PERIOD_NUM': 202606, 'USER_ID': 100, 'IS_ACTIVE': 0},  # 同键冲突
    ])
    ddf_bad_perf = dask_cudf.from_cudf(cudf.from_pandas(bad_perf), npartitions=1)

    with patch.object(service, '_reconstruct_elite_snapshot', return_value=test_data['ddf_elite_mock']):
        try:
            service.execute_batch(
                period_num=test_data['period_num'],
                calc_month=test_data['calc_month'],
                ddf_users=dummy_users,
                ddf_stats=dummy_stats,
                ddf_user=test_data['ddf_user'],
                ddf_user_perf=ddf_bad_perf,
            )
            assert False, "预期抛出 ValueError，但代码未抛出异常"
        except ValueError as e:
            assert "存在同键冲突数据" in str(e), f"未包含预期的异常信息，实际信息为: {str(e)}"


def test_execute_batch_elite_same_key_conflict_raise(service: PEBonusService, test_data: dict):
    """用例 5b：AR_CALC_LV_ELITE 同期同人重复（模拟上游同期重复追加），必须被 _dedup_or_raise 熔断。"""
    dummy_users, dummy_stats = _dummy_graph_inputs()

    base = test_data['ddf_elite_mock'].compute()
    conflict = cudf.DataFrame([{
        'PERIOD_NUM': 202606, 'CALC_MONTH': 6, 'USER_ID': 100, 'PARENT_UID': 0,
        'GPV_REAL': 999_000_000, 'GPV_UNREAL': 999_000_000, 'LAST_ELITE_CALC_ID': 20,
    }])
    bad_elite = dask_cudf.from_cudf(cudf.concat([base, conflict], ignore_index=True), npartitions=1)

    with patch.object(service, '_reconstruct_elite_snapshot', return_value=bad_elite):
        try:
            service.execute_batch(
                period_num=test_data['period_num'],
                calc_month=test_data['calc_month'],
                ddf_users=dummy_users,
                ddf_stats=dummy_stats,
                ddf_user=test_data['ddf_user'],
                ddf_user_perf=test_data['ddf_perf'],
            )
            assert False, "预期抛出 ValueError，但代码未抛出异常"
        except ValueError as e:
            assert "存在同键冲突数据" in str(e), f"未包含预期的异常信息，实际信息为: {str(e)}"


def test_execute_batch_null_is_active_fail_closed(service: PEBonusService, test_data: dict):
    """用例 6：当前期 AR_USER_PERF 有行但 IS_ACTIVE 为 NULL（区别于"缺行"），
    应 fail-closed 降级为 0，验证 fillna(0) 对真实 cudf-null 生效；金额照算（只打标不拦截）。"""
    dummy_users, dummy_stats = _dummy_graph_inputs()

    pdf_elite = pd.DataFrame([
        {'PERIOD_NUM': 202606, 'CALC_MONTH': 6, 'USER_ID': 500, 'PARENT_UID': 0,
         'GPV_REAL': 0, 'GPV_UNREAL': 200_000_000, 'LAST_ELITE_CALC_ID': 20},
    ])
    # 用 np.nan 保证 IS_ACTIVE 列为 float64；nan_as_null=True 再转成真实 cudf-null
    pdf_perf = pd.DataFrame({
        'PERIOD_NUM': [202606],
        'USER_ID': [500],
        'IS_ACTIVE': [np.nan],
    })
    pdf_user = pd.DataFrame({
        'id': [500], 'country_id': [1], 'user_name': ['U500'], 'real_name': ['RN500'],
    })

    ddf_elite = dask_cudf.from_cudf(cudf.from_pandas(pdf_elite, nan_as_null=True), npartitions=1)
    ddf_perf = dask_cudf.from_cudf(cudf.from_pandas(pdf_perf, nan_as_null=True), npartitions=1)
    ddf_user = dask_cudf.from_cudf(cudf.from_pandas(pdf_user), npartitions=1)

    with patch.object(service, '_reconstruct_elite_snapshot', return_value=ddf_elite):
        results = service.execute_batch(
            period_num=202606, calc_month=6,
            ddf_users=dummy_users, ddf_stats=dummy_stats,
            ddf_user=ddf_user, ddf_user_perf=ddf_perf,
        )

    df_main = results['AR_CALC_BONUS_PE'].compute().to_pandas()
    df_source = results['AR_CALC_BONUS_PE_SOURCE'].compute().to_pandas()

    row = df_main[df_main['USER_ID'] == 500].iloc[0]
    assert row['IS_ACTIVE'] == 0, "IS_ACTIVE=NULL 未 fail-closed 为 0"
    assert int(row['BONUS_PE_CENTS']) == 3_000, "金额应照算：200 PV × 150,000 ppm = 3,000 cents"

    s500 = df_source[df_source['BONUS_USER_ID'] == 500]
    assert len(s500) > 0
    assert (s500['IS_ACTIVE'] == 0).all(), "Source 表 IS_ACTIVE=NULL 未 fail-closed 为 0"


def test_sql_truncate_does_not_preround_base(service: PEBonusService, test_data: dict):
    """用例 7：1,500.999 PV 精确进入 micro-units 后，只在最终奖金分边界截断。"""
    dummy_users, dummy_stats = _dummy_graph_inputs()

    pdf_elite = pd.DataFrame([
        {'PERIOD_NUM': 202606, 'CALC_MONTH': 6, 'USER_ID': 600, 'PARENT_UID': 0,
         'GPV_REAL': 0, 'GPV_UNREAL': 1_500_999_000, 'LAST_ELITE_CALC_ID': 20},
    ])
    pdf_perf = pd.DataFrame([{'PERIOD_NUM': 202606, 'USER_ID': 600, 'IS_ACTIVE': 1}])
    pdf_user = pd.DataFrame({'id': [600], 'country_id': [1], 'user_name': ['U600'], 'real_name': ['RN600']})

    ddf_elite = dask_cudf.from_cudf(cudf.from_pandas(pdf_elite, nan_as_null=True), npartitions=1)
    ddf_perf = dask_cudf.from_cudf(cudf.from_pandas(pdf_perf), npartitions=1)
    ddf_user = dask_cudf.from_cudf(cudf.from_pandas(pdf_user), npartitions=1)

    with patch.object(service, '_reconstruct_elite_snapshot', return_value=ddf_elite):
        results = service.execute_batch(
            period_num=202606, calc_month=6,
            ddf_users=dummy_users, ddf_stats=dummy_stats,
            ddf_user=ddf_user, ddf_user_perf=ddf_perf,
        )

    df_main = results['AR_CALC_BONUS_PE'].compute().to_pandas()
    row = df_main[df_main['USER_ID'] == 600].iloc[0]

    assert int(row['TOTAL_BASE_GPV']) == 1_500_999_000
    assert int(row['BONUS_PE_CENTS']) == 22_514


# =====================================================================
# main: 测试运行器
# =====================================================================

def main():
    logger.info("初始化本地 Dask GPU 集群 (LocalCUDACluster)...")
    cluster = LocalCUDACluster(n_workers=1, threads_per_worker=1)
    client = Client(cluster)
    logger.info(f"Dask 集群启动成功: {client.scheduler.address}")

    try:
        # 生成基于 Dask 的通用测试数据
        test_data = _get_test_data()
        config_snapshot = _pe_config_snapshot(
            test_data['period_num'], test_data['calc_month']
        )
        service = PEBonusService(config_snapshot)

        tests = [
            ("Case 1-4: PE 规则主路径验证", test_execute_batch_pe_rules),
            ("Case 5a: AR_USER_PERF 同键冲突熔断测试", test_execute_batch_perf_same_key_conflict_raise),
            ("Case 5b: AR_CALC_LV_ELITE 同键冲突熔断测试", test_execute_batch_elite_same_key_conflict_raise),
            ("Case 6: IS_ACTIVE=NULL fail-closed 降级测试", test_execute_batch_null_is_active_fail_closed),
            ("Case 7: SQL 最终截断边界测试", test_sql_truncate_does_not_preround_base),
        ]

        failed: list[tuple[str, str]] = []
        for name, fn in tests:
            print(f"\n--- 运行: {name} ---")
            try:
                fn(service, test_data)
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

    finally:
        # 清理 Dask 集群资源
        logger.info("关闭 Dask Client 与 Cluster...")
        client.close()
        cluster.close()


if __name__ == "__main__":
    main()
