from __future__ import annotations

import importlib.util
from decimal import Decimal
import sys
from pathlib import Path

import pytest
import pandas as pd


from Common.BonusConfig import (
    CONFIG_REQUIREMENT_MATRIX,
    ConfigSnapshot,
    ConfigSnapshotLoader,
    ensure_config_snapshot,
    parse_signed_percent_to_ppm,
    requirement_matrix_manifest,
)

from User.team_bonus_tb import TeamBonusCalculator

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("15", 150_000),
        (Decimal("-15"), -150_000),
        ("0", 0),
        ("4.5", 45_000),
    ],
)
def test_signed_percent_to_ppm(raw, expected):
    assert parse_signed_percent_to_ppm(raw) == expected


@pytest.mark.parametrize(
    "raw,expected_exception",
    [
        (15.0, TypeError),
        ("1e1", TypeError),
        ("NaN", TypeError),
        (Decimal("Infinity"), ValueError),
        ("0.00001", ValueError),
    ],
)
def test_signed_percent_to_ppm_rejects_noncanonical_or_too_precise(raw, expected_exception):
    with pytest.raises(expected_exception):
        parse_signed_percent_to_ppm(raw)


def test_parser_does_not_add_business_maximum():
    assert parse_signed_percent_to_ppm("101") == 1_010_000


def test_snapshot_checksum_is_stable_across_row_and_field_order():
    rows_a = [
        {"config_name": "proEliteRate", "type": "bonus", "value": "15"},
        {"config_name": "eliteRate", "type": "bonus", "value": "10"},
    ]
    rows_b = [
        {"value": "10", "type": "bonus", "config_name": "eliteRate"},
        {"value": "15", "config_name": "proEliteRate", "type": "bonus"},
    ]

    first = ConfigSnapshot.from_rows(rows_a, loaded_at="2026-08-12T00:00:00+00:00")
    second = ConfigSnapshot.from_rows(rows_b, loaded_at="2026-08-12T00:01:00+00:00")

    assert first.raw_rows_checksum == second.raw_rows_checksum
    assert first.canonical_checksum == second.canonical_checksum
    assert first.snapshot_id == second.snapshot_id


def test_snapshot_is_frozen_from_mutable_source():
    source = [{"config_name": "proEliteRate", "type": "bonus", "value": "15"}]
    loader = ConfigSnapshotLoader(source)
    snapshot = loader.load(period_num=202608, calc_month=8)
    source[0]["value"] = "99"
    source.append({"config_name": "eliteRate", "type": "bonus", "value": "20"})
    next_snapshot = loader.load(period_num=202609, calc_month=9)

    assert snapshot.require_ppm("proEliteRate", award="PE") == 150_000
    assert snapshot.raw_row_count == 1
    assert next_snapshot.require_ppm("proEliteRate", award="PE") == 990_000
    assert next_snapshot.snapshot_id != snapshot.snapshot_id
    assert ensure_config_snapshot(snapshot, period_num=202608, calc_month=8) is snapshot
    snapshot.assert_run(202608, 8)
    with pytest.raises(ValueError):
        snapshot.assert_run(202607, 8)


def test_sql_missing_zero_and_min_duplicate_semantics():
    missing = ConfigSnapshot.from_rows([])
    duplicate = ConfigSnapshot.from_rows([
        {"config_name": "eliteRate", "type": "bonus", "value": "20"},
        {"config_name": "eliteRate", "type": "bonus", "value": "-5"},
    ])
    assert list(missing.to_pandas().columns) == ["config_name", "type", "value"]

    assert missing.require_ppm("eliteRate", award="ELITE") == 0
    assert duplicate.require_ppm("eliteRate", award="ELITE") == -50_000


def test_se_name_and_type_are_exact_raw():
    canonical = ConfigSnapshot.from_rows([
        {"config_name": "superEliteRate", "type": "bonus", "value": "-10"},
    ])
    name_with_space = ConfigSnapshot.from_rows([
        {"config_name": " superEliteRate", "type": "bonus", "value": "10"},
    ])
    type_with_case_change = ConfigSnapshot.from_rows([
        {"config_name": "superEliteRate", "type": "BONUS", "value": "10"},
    ])

    assert canonical.require_ppm("superEliteRate", award="SE") == -100_000
    assert name_with_space.require_ppm("superEliteRate", award="SE") == 0
    assert type_with_case_change.require_ppm("superEliteRate", award="SE") == 0

def test_se_country_prefix_allows_multiple_keys_but_rejects_same_key_duplicates():
    valid = ConfigSnapshot.from_rows([
        {"config_name": "Country1", "type": "bonus", "value": "1"},
        {"config_name": "Country3", "type": "bonus", "value": "1"},
    ])
    duplicate = ConfigSnapshot.from_rows([
        {"config_name": "Country1", "type": "bonus", "value": "1"},
        {"config_name": "Country1", "type": "bonus", "value": "2"},
    ])

    assert len(valid.country_rows("SE")) == 2
    with pytest.raises(ValueError, match="duplicate config rows"):
        duplicate.country_rows("SE")


def test_nonexact_awards_export_canonical_views_without_mutating_raw_rows():
    snapshot = ConfigSnapshot.from_rows([
        {"config_name": " leadershipRate10 ", "type": " BONUS ", "value": "4.5"},
        {"config_name": " country1 ", "type": " BONUS ", "value": "0"},
    ])

    assert snapshot.iter_ppm_rows("LB", "leadershipRate*") == (
        ("leadershipRate10", 45_000),
    )
    assert snapshot.country_rows("EAB") == (
        {"config_name": "Country1", "type": "bonus", "value": "0"},
    )
    assert snapshot.raw_rows[0].get("config_name") == " leadershipRate10 "
    assert snapshot.raw_rows[1].get("type") == " BONUS "


def test_country_empty_and_literal_zero_remain_visible_to_upstream_owned_policy():
    snapshot = ConfigSnapshot.from_rows([
        {"config_name": "Country", "type": "bonus", "value": ""},
        {"config_name": "Country0", "type": "bonus", "value": "0"},
    ])

    assert snapshot.country_rows("EAB") == (
        {"config_name": "Country", "type": "bonus", "value": ""},
        {"config_name": "Country0", "type": "bonus", "value": "0"},
    )


def test_eab_and_lb_nonbonus_country_rows_are_ignored_without_global_rejection():
    snapshot = ConfigSnapshot.from_rows([
        {"config_name": "Country1", "type": "upstream", "value": "0"},
        {"config_name": "Country2", "type": "bonus", "value": ""},
    ])

    assert snapshot.country_rows("EAB") == (
        {"config_name": "Country2", "type": "bonus", "value": ""},
    )
    assert snapshot.country_rows("LB") == snapshot.country_rows("EAB")


def test_matrix_is_machine_readable_and_covers_current_awards():
    assert set(CONFIG_REQUIREMENT_MATRIX) == {"PE", "ELITE", "SE", "EAB", "LB", "TB"}
    manifest = requirement_matrix_manifest()
    assert manifest["PE"][0]["config_name"] == "proEliteRate"
    assert manifest["SE"][0]["exact_raw_name"] is True
    assert manifest["SE"][0]["exact_raw_type"] is True


def test_snapshot_manifest_is_serializable_and_round_trips():
    module_path = ROOT / "Model" / "Config" / "ConfigSnapshot.py"
    spec = importlib.util.spec_from_file_location("pvam_config_snapshot_manifest", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    snapshot = ConfigSnapshot.from_rows(
        [{"config_name": "eliteRate", "type": "bonus", "value": "15"}],
        period_num=202608,
        calc_month=8,
        source="uat-fixture",
        source_version="sha256:abc",
    )
    manifest = module.ConfigSnapshotManifest.from_snapshot(snapshot)
    restored = module.ConfigSnapshotManifest.from_mapping(manifest.to_dict())

    assert restored == manifest

    assert restored.raw_row_count == 1
    assert restored.snapshot_id == snapshot.snapshot_id


def test_team_bonus_oracle_accepts_snapshot_fixture_without_changing_values():
    snapshot = ensure_config_snapshot([
        {"CONFIG_NAME": "teamBisectRate", "TYPE": "bonus", "VALUE": "24"},
        {"CONFIG_NAME": "teamTouchRate10", "TYPE": "bonus", "VALUE": "10"},
        {"CONFIG_NAME": "teamTouchCapping10", "TYPE": "bonus", "VALUE": "0"},
    ])
    fixture = snapshot.to_pandas(uppercase_columns=True)
    calculator = TeamBonusCalculator(
        perf_month=pd.DataFrame(columns=["PERIOD_NUM"]),
        user=pd.DataFrame(columns=["ID", "MEMBER_LV", "COUNTRY_ID"]),
        member_level=pd.DataFrame(columns=["ID", "CALC_ID"]),
        config=snapshot,
        user_perf=pd.DataFrame(columns=["USER_ID"]),
    )

    assert calculator.bisect_rate() == Decimal("0.24")


    assert list(fixture["CONFIG_NAME"]) == [
        "teamBisectRate",
        "teamTouchRate10",
        "teamTouchCapping10",
    ]
    assert list(fixture["VALUE"]) == ["24", "10", "0"]


@pytest.mark.parametrize(
    ("relative_path", "forbidden"),
    [
        ("User/PEBonusService.py", "_pro_elite_rate_ppm = 150000"),
        ("User/EliteBonusService.py", "self.elite_rate = Decimal('0.15')"),
        ("User/GlobalEliteBonusRecalculationService.py", "elite_rate: float = 0.15"),
    ],
)
def test_production_rate_fallbacks_are_removed(relative_path, forbidden):
    assert forbidden not in (ROOT / relative_path).read_text(encoding="utf-8")
