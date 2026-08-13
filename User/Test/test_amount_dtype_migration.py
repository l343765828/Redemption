import ast
import copy
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from Common.AmountModelAdapter import require_v2_amount_record
from Common.PeriodResolver import MappingPeriodRepository, PeriodResolver
from MessageConsumer.PvEventNormalizer import (
    InMemoryEventRegistry,
    PvEventNormalizer,
)
from Order.PvEventDeliveryLedger import InMemoryPvEventDeliveryLedger
from Order.ConsumedOrderLedger import InMemoryConsumedOrderLedger
from Model.Order.NormalizedPvEvent import require_normalized_pv_event
from Order.RefundReversalLedger import InMemoryRefundReversalLedger
from Common.PvAmount import (
    BONUS_CENT_SCALE,
    INT64_MAX,
    INT64_MIN,
    PV_SCALE,
    RATE_PPM_SCALE,
    assert_integer_amount_dtype,
    checked_add_int64,
    require_amount_version,
    require_int64,
    require_units_int,
    units_ppm_to_bonus_cents,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _function_source(relative_path: str, function_name: str) -> str:
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    assert len(functions) == 1
    return ast.get_source_segment(source, functions[0])


def _load_method(relative_path: str, class_name: str, function_name: str, globals_: dict):
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    class_node = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    function_node = next(
        copy.deepcopy(node) for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    function_node.decorator_list = []
    function_node.returns = None
    for argument in (
        function_node.args.posonlyargs
        + function_node.args.args
        + function_node.args.kwonlyargs
    ):
        argument.annotation = None
    isolated = ast.Module(body=[function_node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    namespace = dict(globals_)
    exec(compile(isolated, relative_path, "exec"), namespace)
    return namespace[function_name]


def _string_subscripts(relative_path: str) -> set[str]:
    tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    return {
        node.slice.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    }


def _normalized_event():
    resolver = PeriodResolver(
        MappingPeriodRepository(
            [{"PERIOD_NUM": 40, "CALC_YEAR": 2026, "CALC_MONTH": 1}]
        )
    )
    return PvEventNormalizer(
        resolver,
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
        delivery_ledger=InMemoryPvEventDeliveryLedger(),
    ).normalize_order(
        {
            "order_id": "O-1",
            "user_id": "U-1",
            "bv": "1.25",
            "period": 40,
        }
    )


def test_normalized_event_carries_strict_units_int() -> None:
    event = require_normalized_pv_event(_normalized_event())

    assert type(event.effective_pv_delta_units) is int
    assert event.effective_pv_delta_units == 1_250_000
    assert event.amount_encoding_version == 2


def test_three_incremental_entries_expose_same_normalized_event_contract() -> None:
    targets = {
        "User/UserStatsService.py": "update_elite_performance",
        "User/PlacementIncrementalService.py": "update_placement_performance",
        "User/EliteBonusService.py": "update_elite_bonus_incremental",
    }

    for relative_path, function_name in targets.items():
        tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ]
        assert len(functions) == 1
        assert any(arg.arg == "normalized_event" for arg in functions[0].args.kwonlyargs)


def test_period_adapters_do_not_contain_local_period_arithmetic() -> None:
    targets = [
        ("User/GlobalRecalculationService.py", "_get_previous_period"),
        ("User/PlacementIncrementalService.py", "_get_prev_period"),
        ("User/PlacementRecalculationService.py", "_get_prev_period"),
    ]

    for relative_path, function_name in targets:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        ]
        assert len(functions) == 1
        function_source = ast.get_source_segment(source, functions[0])
        assert "previous_period_num" in function_source
        assert "period_int - 1" not in function_source
        assert "m - 1" not in function_source


def test_user_stats_and_global_recalculation_use_v2_scaled_rank_thresholds() -> None:
    user_stats_source = (REPO_ROOT / "User/UserStatsService.py").read_text(
        encoding="utf-8"
    )
    global_source = (REPO_ROOT / "User/GlobalRecalculationService.py").read_text(
        encoding="utf-8"
    )

    assert "ELITE_MARK = 1000 * PV_SCALE" in user_stats_source
    assert "VIRTUAL_MARK = 2000 * PV_SCALE" in user_stats_source
    assert "from User.UserStatsService import" in global_source
    assert "ELITE_MARK," in global_source
    assert "VIRTUAL_MARK," in global_source


def test_global_elite_recalculation_uses_units_threshold_and_cents_only() -> None:
    source = (
        REPO_ROOT / "User/GlobalEliteBonusRecalculationService.py"
    ).read_text(encoding="utf-8")
    evaluate_source = _function_source(
        "User/GlobalEliteBonusRecalculationService.py", "_evaluate_node"
    )
    reset_source = _function_source(
        "User/GlobalEliteBonusRecalculationService.py", "_reset_all_derived_stats"
    )

    assert "ELITE_MARK = 1000 * PV_SCALE" in source
    assert "estimated_bonus_cents" in evaluate_source
    assert "float(" not in evaluate_source
    assert "$.estimated_bonus_cents" in reset_source

    evaluate = _load_method(
        "User/GlobalEliteBonusRecalculationService.py",
        "GlobalEliteBonusRecalculationService",
        "_evaluate_node",
        {
            "EliteBonusStats": object,
            "units_ppm_to_bonus_cents": units_ppm_to_bonus_cents,
        },
    )
    service = SimpleNamespace(
        ELITE_MARK=1000 * PV_SCALE,
        elite_rate_ppm=150_000,
    )
    node = SimpleNamespace(
        gpv=1_500_990_000,
        qualified_downlines=set(),
        is_qualified=False,
        qualifying_path=None,
        gpv_real=0,
        contrib_to_parent=0,
        estimated_bonus=99.99,
        estimated_bonus_cents=0,
    )

    evaluate(service, node)
    assert node.is_qualified is True
    assert node.estimated_bonus_cents == 22_514
    assert node.estimated_bonus is None


def test_elite_v2_uses_scaled_threshold_and_integer_bonus_cents() -> None:
    source = (REPO_ROOT / "User/EliteBonusService.py").read_text(encoding="utf-8")
    evaluate_source = _function_source("User/EliteBonusService.py", "_evaluate_node")

    assert "ELITE_MARK_UNITS = 1000 * PV_SCALE" in source
    assert "units_ppm_to_bonus_cents" in evaluate_source
    assert "estimated_bonus_cents" in evaluate_source
    assert "estimated_bonus = float" not in evaluate_source


def test_pe_truncates_once_after_units_times_ppm() -> None:
    truncate_source = _function_source("User/PEBonusService.py", "_apply_truncate")

    assert "BONUS_PE_CENTS" in truncate_source
    assert "RATE_PPM_SCALE" in truncate_source
    assert "PV_SCALE" in truncate_source
    assert "cp.round" not in truncate_source
    assert "/ 100.0" not in truncate_source


def test_pe_fallback_active_threshold_uses_micro_units() -> None:
    source = _function_source("User/PEBonusService.py", "execute_batch")

    assert ">= 30 * PV_SCALE" in source
    assert ">= 30).astype" not in source


def test_recalculation_callers_inject_period_snapshot_and_se_demo_uses_units() -> None:
    global_main = _function_source("User/GlobalRecalculationService.py", "main")
    global_test_run = _function_source(
        "User/Test/GlobalRecalculationServiceTest.py", "_run"
    )
    placement_test_run = _function_source(
        "User/Test/PlacementRecalculationServiceTest.py", "_run"
    )
    se_main = _function_source("User/SuperEliteBonusService.py", "main")

    assert "period_snapshot=" in global_main
    assert "period_snapshot=" in global_test_run
    assert "period_snapshot=" in placement_test_run
    assert "'pv_units'" in se_main
    assert "'pv':" not in se_main

def test_pe_manual_and_gpu_uat_callers_use_v2_output_contract() -> None:
    required_keys = {
        "User/PEBonusService_Main.py": {"BONUS_PE_CENTS"},
        "User/Test/PEBonusServiceTest.py": {"BONUS_PE_CENTS", "PE_RATE_PPM"},
    }
    for relative_path, expected_keys in required_keys.items():
        keys = _string_subscripts(relative_path)
        assert "BONUS_PE" not in keys
        assert "PE_RATE" not in keys
        assert expected_keys <= keys

        tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
        constructors = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "PEBonusService"
        ]
        assert constructors
        assert all(call.args or call.keywords for call in constructors)


def test_super_elite_keeps_units_through_groupby_and_lands_cents() -> None:
    source = (REPO_ROOT / "User/SuperEliteBonusService.py").read_text(
        encoding="utf-8"
    )

    assert "pv_units" in source
    assert "bonus_se_cents" in source
    assert "assert_integer_amount_dtype" in source
    assert "pv_mills" not in source
    assert ".round()" not in source
    calculate_source = _function_source(
        "User/SuperEliteBonusService.py", "calculate_se_bonus"
    )
    assert "pool[['bonus_country', 'bonus_se', 'bonus_se_cents']]" in calculate_source
    helper_source = _function_source(
        "User/SuperEliteBonusService.py", "_units_ppm_count_to_bonus_cents"
    )
    assert "require_int64" in helper_source


def test_leadership_bonus_has_no_float_amount_kernel() -> None:
    source = (REPO_ROOT / "User/LeadershipBonusGPUService.py").read_text(
        encoding="utf-8"
    )
    truncate_source = _function_source(
        "User/LeadershipBonusGPUService.py", "_truncate_gpu"
    )

    assert "RATE_PPM_SCALE" in source
    assert "BONUS_CENT_SCALE" in source
    assert "row_bonus_cents" in source
    assert "float64" not in source
    assert "nextafter" not in truncate_source
    divide_source = _function_source(
        "User/LeadershipBonusGPUService.py", "_divide_units_to_ppm"
    )
    assert "numerator_abs" in divide_source
    assert "cp.where(numerator < 0, -magnitude, magnitude)" in divide_source
    assert "numerator // denominator" not in divide_source


def test_amount_path_sources_reject_unapproved_float64_lines() -> None:
    targets = (
        "User/PEBonusService.py",
        "User/PEBonusService_Main.py",
        "User/SuperEliteBonusService.py",
        "User/PlacementRecalculationService.py",
        "User/PlacementIncrementalService.py",
        "User/EliteBonusService.py",
        "User/EliteAchievementBonusService.py",
    )
    # PE 的 parent_id 是图关系 ID，不是金额列；cuDF 需先转为 float64 才能 fillna，再恢复为 int64。
    allowed_float64_lines = {
        "User/PEBonusService.py": {
            "ddf_tree['parent_id'] = ddf_tree['parent_id'].astype('float64').fillna(0).astype('int64')"
        }
    }

    for relative_path in targets:
        source_lines = (REPO_ROOT / relative_path).read_text(encoding="utf-8").splitlines()
        float64_lines = {line.strip() for line in source_lines if "float64" in line}
        allowed_lines = allowed_float64_lines.get(relative_path, set())

        assert float64_lines <= allowed_lines, (
            f"{relative_path} contains unapproved float64 lines: "
            f"{sorted(float64_lines - allowed_lines)}"
        )


def test_leadership_bonus_global_rate_uses_ppm_helper_and_checked_int64_math() -> None:
    compute_source = _function_source(
        "User/LeadershipBonusGPUService.py", "compute_leadership_bonus"
    )
    truncate_source = _function_source(
        "User/LeadershipBonusGPUService.py", "_truncate_gpu"
    )
    multiply_source = _function_source(
        "User/LeadershipBonusGPUService.py", "_mul_units_by_ppm"
    )
    cents_source = _function_source(
        "User/LeadershipBonusGPUService.py", "_units_ppm_to_cents"
    )
    divide_source = _function_source(
        "User/LeadershipBonusGPUService.py", "_divide_units_to_ppm"
    )

    assert "self._divide_units_to_ppm(" in compute_source
    assert 'global_bonus_units, df_global_detail["lb_pv"]' in compute_source
    assert "bonus_lb_cents\"].values * (PV_SCALE // BONUS_CENT_SCALE) //" not in compute_source
    assert "_abs_int64_gpu" in truncate_source
    assert "_checked_mul_nonnegative_gpu" in multiply_source
    assert "_checked_mul_nonnegative_gpu" in cents_source
    assert "_checked_mul_nonnegative_gpu" in divide_source
    assert "safe_denominator" in divide_source


def test_signed_int64_guard_rejects_uint64_before_cast() -> None:
    frame = pd.DataFrame(
        {"pv_units": pd.Series([np.iinfo(np.uint64).max], dtype="uint64")}
    )

    with pytest.raises(TypeError, match="signed int64 dtype"):
        assert_integer_amount_dtype(frame, ["pv_units"], "unsigned amount")


def test_signed_int64_guard_rejects_narrow_signed_dtype() -> None:
    frame = pd.DataFrame({"pv_units": pd.Series([1], dtype="int32")})

    with pytest.raises(TypeError, match="signed int64 dtype"):
        assert_integer_amount_dtype(frame, ["pv_units"], "narrow amount")


def test_pe_se_and_leadership_execute_sql_golden_amounts(monkeypatch) -> None:
    fake_cp = SimpleNamespace(
        abs=np.abs,
        any=np.any,
        asarray=np.asarray,
        maximum=np.maximum,
        where=np.where,
    )
    monkeypatch.setitem(sys.modules, "cupy", fake_cp)

    apply_pe_truncate = _load_method(
        "User/PEBonusService.py",
        "PEBonusService",
        "_apply_truncate",
        {
            "BONUS_CENT_SCALE": BONUS_CENT_SCALE,
            "PV_SCALE": PV_SCALE,
            "RATE_PPM_SCALE": RATE_PPM_SCALE,
        },
    )
    pe_result = apply_pe_truncate(
        pd.DataFrame(
            {
                "TOTAL_BASE_GPV": pd.Series([1_500_990_000], dtype="int64"),
                "PE_RATE_PPM": pd.Series([150_000], dtype="int64"),
            }
        )
    )
    assert int(pe_result.loc[0, "BONUS_PE_CENTS"]) == 22_514

    se_bonus_cents = _load_method(
        "User/SuperEliteBonusService.py",
        "SuperEliteBonusService",
        "_units_ppm_count_to_bonus_cents",
        {
            "BONUS_CENT_SCALE": BONUS_CENT_SCALE,
            "PV_SCALE": PV_SCALE,
            "RATE_PPM_SCALE": RATE_PPM_SCALE,
            "require_int64": require_int64,
        },
    )
    assert se_bonus_cents(1_500_990_000, 100_000, 3) == 5_003

    fake_cudf = SimpleNamespace(
        Series=lambda values, index=None: pd.Series(np.asarray(values), index=index)
    )
    leadership_globals = {
        "BONUS_CENT_SCALE": BONUS_CENT_SCALE,
        "INT64_MAX": INT64_MAX,
        "INT64_MIN": INT64_MIN,
        "PV_SCALE": PV_SCALE,
        "RATE_PPM_SCALE": RATE_PPM_SCALE,
        "cp": fake_cp,
        "cudf": fake_cudf,
    }

    class LeadershipFormula:
        pass

    for method_name in (
        "_abs_int64_gpu",
        "_checked_mul_nonnegative_gpu",
        "_checked_add_nonnegative_gpu",
        "_mul_units_by_ppm",
        "_divide_units_to_ppm",
        "_units_ppm_to_cents",
    ):
        setattr(
            LeadershipFormula,
            method_name,
            _load_method(
                "User/LeadershipBonusGPUService.py",
                "LeadershipBonusGPUService",
                method_name,
                leadership_globals,
            ),
        )

    leadership = LeadershipFormula()
    base_units = pd.Series([1_500_990_000], dtype="int64")
    rate_ppm = pd.Series([150_000], dtype="int64")
    honor_bonus_units = leadership._mul_units_by_ppm(base_units, rate_ppm)
    derived_rate_ppm = leadership._divide_units_to_ppm(
        honor_bonus_units, base_units
    )
    bonus_cents = leadership._units_ppm_to_cents(base_units, derived_rate_ppm)

    assert int(honor_bonus_units.iloc[0]) == 225_148_500
    assert int(derived_rate_ppm.iloc[0]) == 150_000
    assert int(bonus_cents.iloc[0]) == 22_514


def test_v2_record_read_boundaries_reject_legacy_or_mixed_records() -> None:
    targets = [
        ("User/UserStatsService.py", "_get_or_init_user"),
        ("User/PlacementIncrementalService.py", "_load_prev_surplus"),
        ("User/PlacementIncrementalService.py", "_get_or_init_user_with_surplus"),
        ("User/PlacementRecalculationService.py", "_mget_users_with_exists"),
        ("User/EliteBonusService.py", "_get_or_create_node"),
        ("User/EliteBonusService.py", "_propagate_upward"),
        ("User/GlobalRecalculationService.py", "_mget_users_with_exists"),
        ("User/GlobalEliteBonusRecalculationService.py", "_mget_stats_with_exists"),
        ("User/GlobalEliteBonusRecalculationService.py", "_fallback_single_get"),
        ("User/PEBonusService_Main.py", "build_ddf_stats_from_redis"),
        ("User/PEBonusService_Main.py", "_build_ddf_stats_via_mget"),
    ]

    for relative_path, function_name in targets:
        source = _function_source(relative_path, function_name)
        assert "require_v2_amount_record" in source, (
            f"{relative_path}:{function_name} must fail-loud on legacy/mixed records"
        )

def test_placement_full_recalculation_rejects_legacy_record_before_model_construction() -> None:
    raw_record = {
        "id": "U-LEGACY",
        "user_id": "U-LEGACY",
        "pk": "41:U-LEGACY",
        "period": "41",
        "pv": 1,
    }

    class FakeJson:
        @staticmethod
        def mget(keys, path):
            assert keys == ["41:U-LEGACY"]
            assert path == "."
            return [dict(raw_record)]

    class FakeRedis:
        @staticmethod
        def json():
            return FakeJson()

    class FakeUserStats:
        constructed = False

        @staticmethod
        def db():
            return FakeRedis()

        @staticmethod
        def make_key(value):
            return value

        def __init__(self, **kwargs):
            type(self).constructed = True

    load_users = _load_method(
        "User/PlacementRecalculationService.py",
        "PlacementRecalculationService",
        "_mget_users_with_exists",
        {
            "UserStats": FakeUserStats,
            "logger": SimpleNamespace(warning=lambda *args, **kwargs: None),
            "require_v2_amount_record": require_v2_amount_record,
        },
    )

    with pytest.raises(ValueError, match="V2_AMOUNT_RECORD_REQUIRED"):
        load_users(
            SimpleNamespace(),
            ["U-LEGACY"],
            "41",
            object(),
        )
    assert FakeUserStats.constructed is False


@pytest.mark.parametrize(
    ("left", "right"),
    [(INT64_MAX, 1), (INT64_MIN, -1)],
)
def test_placement_mid8_rejects_signed_int64_overflow(left, right) -> None:
    apply_mid8 = _load_method(
        "User/PlacementIncrementalService.py",
        "PlacementIncrementalService",
        "_apply_mid8_logic",
        {
            "checked_add_int64": checked_add_int64,
            "require_units_int": require_units_int,
        },
    )
    node = SimpleNamespace(
        pv=1,
        pv_1l=left,
        pv_2l=0,
        pre_surplus_1l=right,
        pre_surplus_2l=0,
        total_1l=0,
        total_2l=0,
    )

    with pytest.raises(OverflowError):
        apply_mid8(SimpleNamespace(), node, has_activity=True)


def test_elite_contribution_delta_rejects_signed_int64_overflow() -> None:
    evaluate = _load_method(
        "User/EliteBonusService.py",
        "EliteBonusService",
        "_evaluate_node",
        {
            "ELITE_MARK_UNITS": 1000 * PV_SCALE,
            "checked_add_int64": checked_add_int64,
            "units_ppm_to_bonus_cents": units_ppm_to_bonus_cents,
        },
    )
    node = SimpleNamespace(
        gpv=INT64_MAX,
        qualified_downlines=set(),
        is_qualified=False,
        qualifying_path=None,
        contrib_to_parent=INT64_MIN,
        gpv_real=0,
        estimated_bonus=None,
        estimated_bonus_cents=0,
    )

    with pytest.raises(OverflowError):
        evaluate(SimpleNamespace(elite_rate_ppm=150_000), node)


def test_all_persisted_amount_accumulation_paths_call_checked_int64() -> None:
    targets = [
        ("User/UserStatsService.py", "_update_elite_performance_units"),
        ("User/EliteBonusService.py", "_evaluate_node"),
        ("User/EliteBonusService.py", "update_elite_bonus_incremental"),
        ("User/EliteBonusService.py", "_propagate_upward"),
        ("User/PlacementIncrementalService.py", "_apply_mid8_logic"),
        ("User/PlacementIncrementalService.py", "_update_placement_performance_units"),
        ("User/PlacementRecalculationService.py", "_write_back_placement_matrix"),
        ("User/GlobalRecalculationService.py", "_process_parent_batch"),
        ("User/GlobalEliteBonusRecalculationService.py", "_process_parent_batch"),
    ]

    for relative_path, function_name in targets:
        source = _function_source(relative_path, function_name)
        assert "checked_add_int64" in source, (
            f"{relative_path}:{function_name} must fail-loud before persisting "
            "an out-of-range amount"
        )


def test_placement_v2_rejects_float_round_trip_and_asserts_integer_merges() -> None:
    extract_source = _function_source(
        "User/PlacementRecalculationService.py", "_process_extract_batch"
    )
    previous_source = _function_source(
        "User/PlacementRecalculationService.py", "_mget_prev_surplus"
    )
    calculate_source = _function_source(
        "User/PlacementRecalculationService.py", "_calculate_placement_pv"
    )

    assert "float(" not in extract_source
    assert "round(" not in extract_source
    assert "float(" not in previous_source
    assert "round(" not in previous_source
    assert calculate_source.count("assert_integer_amount_dtype") >= 3
    assert 'cudf.Series(dtype="int64")' in (REPO_ROOT / "User/PlacementRecalculationService.py").read_text(encoding="utf-8")

def test_elite_stage_atomically_binds_normalized_identity_revision_and_hash() -> None:
    entry_source = _function_source(
        "User/EliteBonusService.py", "update_elite_bonus_incremental"
    )
    save_source = _function_source("User/EliteBonusService.py", "_batch_save")

    assert "event.identity" in entry_source
    assert "event.business_revision" in entry_source
    assert "event.payload_hash" in entry_source
    assert "event_done_key" in entry_source
    assert "event_lock" in entry_source
    assert "done_key" in save_source
    assert "pipe.set(done_key" in save_source
    assert "self.redis_conn.pipeline(transaction=True)" in save_source

def test_elite_v2_golden_threshold_and_final_cent_truncate() -> None:

    evaluate = _load_method(
        "User/EliteBonusService.py",
        "EliteBonusService",
        "_evaluate_node",
        {
            "ELITE_MARK_UNITS": 1000 * PV_SCALE,
            "checked_add_int64": checked_add_int64,
            "units_ppm_to_bonus_cents": units_ppm_to_bonus_cents,
        },
    )
    service = SimpleNamespace(elite_rate_ppm=150_000)

    below_threshold = SimpleNamespace(
        gpv=999_999_999,
        gpv_real=0,
        pv_pcs=0,
        contrib_to_parent=0,
        qualified_downlines=set(),
        is_qualified=False,
        qualifying_path=None,
        estimated_bonus=None,
        estimated_bonus_cents=0,
    )
    evaluate(service, below_threshold)
    assert below_threshold.is_qualified is False
    assert below_threshold.estimated_bonus_cents == 0

    qualified = SimpleNamespace(
        gpv=1_500_990_000,
        gpv_real=0,
        pv_pcs=1_500_990_000,
        contrib_to_parent=0,
        qualified_downlines=set(),
        is_qualified=False,
        qualifying_path=None,
        estimated_bonus=None,
        estimated_bonus_cents=0,
    )
    evaluate(service, qualified)
    assert qualified.is_qualified is True
    assert qualified.estimated_bonus_cents == 22_514
    assert type(qualified.estimated_bonus_cents) is int
    assert qualified.estimated_bonus is None
    assert units_ppm_to_bonus_cents(10_000, 1_500_000, "TRUNCATE") == 1


def test_placement_v2_preserves_large_int_and_rejects_float() -> None:
    process_batch = _load_method(
        "User/PlacementRecalculationService.py",
        "PlacementRecalculationService",
        "_process_extract_batch",
        {
            "require_amount_version": require_amount_version,
            "require_units_int": require_units_int,
        },
    )

    class JsonClient:
        def __init__(self, record):
            self.record = record

        def mget(self, _keys, _path):
            return [self.record]

    class Redis:
        def __init__(self, record):
            self.client = JsonClient(record)

        def json(self):
            return self.client

    exact = 9_007_199_254_740_993
    base = {
        "id": "U1",
        "user_id": "U1",
        "amount_encoding_version": 2,
        "pv": exact,
        "pv_1l": 0,
        "pv_2l": 0,
        "pre_surplus_1l": 0,
        "pre_surplus_2l": 0,
        "total_1l": 0,
        "total_2l": 0,
    }
    active = {}
    process_batch(None, Redis(base), [b"stats:40:U1"], active, set(), False)
    assert active["U1"] == exact
    assert type(active["U1"]) is int

    bad = dict(base, pv=1.25)
    with pytest.raises(TypeError):
        process_batch(None, Redis(bad), [b"stats:40:U1"], {}, set(), False)
