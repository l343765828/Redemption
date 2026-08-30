from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


USER_AMOUNT_FIELDS = {
    "pv": 10,
    "gpv": 20,
    "gpv_real": 20,
    "gpv_unreal": 0,
    "contrib": 5,
    "pv_1l": 1,
    "pv_2l": 2,
    "pre_surplus_1l": 3,
    "pre_surplus_2l": 4,
    "total_1l": 4,
    "total_2l": 6,
    "remain_surplus_1l": 3,
    "remain_surplus_2l": 4,
}

ELITE_AMOUNT_FIELDS = {
    "pv_pcs": 10,
    "gpv": 20,
    "gpv_real": 20,
    "contrib_to_parent": 5,
}


class Record(SimpleNamespace):
    def __init__(self, **values):
        super().__init__(**values)
        self.save_calls = 0

    def save(self):
        self.save_calls += 1


def install_model(monkeypatch, migration, name, records):
    class Model:
        remaining = list(records)

        @classmethod
        def get(cls, record_id):
            assert record_id == "41:U-1"
            return cls.remaining.pop(0)

    monkeypatch.setattr(migration, name, Model)


def user_record(*, version=None, **overrides):
    values = {
        "period": "41",
        "amount_encoding_version": version,
        **USER_AMOUNT_FIELDS,
        **overrides,
    }
    return Record(**values)


def elite_record(*, version=None, estimated_bonus=0.0, cents=None, **overrides):
    values = {
        "period_num": 41,
        "amount_encoding_version": version,
        "estimated_bonus": estimated_bonus,
        "estimated_bonus_cents": cents,
        **ELITE_AMOUNT_FIELDS,
        **overrides,
    }
    return Record(**values)


def test_user_stats_migration_defaults_to_dry_run_then_applies_and_is_idempotent(monkeypatch):
    migration = importlib.import_module("Redishelper.PVAmountMigration")
    dry_record = user_record()
    install_model(monkeypatch, migration, "UserStats", [dry_record])

    dry_result = migration.migrate_user_stats_record(41, "41:U-1")

    assert dry_result.status == "READY"
    assert dry_result.mode == "DRY_RUN"
    assert dry_record.amount_encoding_version is None
    assert dry_record.save_calls == 0

    initial = user_record()
    fresh = user_record()
    install_model(monkeypatch, migration, "UserStats", [initial, fresh])

    applied = migration.migrate_user_stats_record(41, "41:U-1", apply=True)

    assert applied.status == "MIGRATED"
    assert applied.before_version is None
    assert applied.after_version == 2
    assert fresh.amount_encoding_version == 2
    assert fresh.save_calls == 1

    already_v2 = user_record(version=2)
    install_model(monkeypatch, migration, "UserStats", [already_v2])

    repeated = migration.migrate_user_stats_record(41, "41:U-1", apply=True)

    assert repeated.status == "ALREADY_V2"
    assert repeated.after_version == 2
    assert already_v2.save_calls == 0


def test_user_stats_migration_rejects_bool_and_signed_int64_overflow(monkeypatch):
    migration = importlib.import_module("Redishelper.PVAmountMigration")

    for invalid, expected_code in (
        (user_record(pv=True), "INVALID_AMOUNT_FIELD:pv"),
        (user_record(gpv=2 ** 63), "INT64_OUT_OF_RANGE:gpv"),
    ):
        install_model(monkeypatch, migration, "UserStats", [invalid])

        result = migration.migrate_user_stats_record(
            41,
            "41:U-1",
            apply=True,
        )

        assert result.status == "REJECTED"
        assert result.code == expected_code
        assert invalid.amount_encoding_version is None
        assert invalid.save_calls == 0


def test_user_stats_apply_rechecks_values_before_write(monkeypatch):
    migration = importlib.import_module("Redishelper.PVAmountMigration")
    initial = user_record()
    changed = user_record(pv=11)
    install_model(monkeypatch, migration, "UserStats", [initial, changed])

    result = migration.migrate_user_stats_record(41, "41:U-1", apply=True)

    assert result.status == "REJECTED"
    assert result.code == "STALE_RECORD"
    assert changed.amount_encoding_version is None
    assert changed.save_calls == 0


def test_migration_requires_full_record_id_before_loading_a_model():
    migration = importlib.import_module("Redishelper.PVAmountMigration")

    with pytest.raises(ValueError, match="exact record suffix"):
        migration.migrate_user_stats_record(41, "41:")


def test_elite_migration_requires_recalculation_for_nonzero_legacy_bonus(monkeypatch):
    migration = importlib.import_module("Redishelper.PVAmountMigration")
    legacy = elite_record(estimated_bonus=12.34)
    install_model(monkeypatch, migration, "EliteBonusStats", [legacy])

    result = migration.migrate_elite_bonus_stats_record(
        41,
        "41:U-1",
        apply=True,
    )

    assert result.status == "RECALC_REQUIRED"
    assert result.code == "LEGACY_BONUS_NONZERO"
    assert legacy.amount_encoding_version is None
    assert legacy.save_calls == 0


def test_elite_zero_legacy_bonus_migrates_to_blank_v2_and_repeats_idempotently(monkeypatch):
    migration = importlib.import_module("Redishelper.PVAmountMigration")
    initial = elite_record(estimated_bonus=0.0)
    fresh = elite_record(estimated_bonus=0.0)
    install_model(monkeypatch, migration, "EliteBonusStats", [initial, fresh])

    applied = migration.migrate_elite_bonus_stats_record(
        41,
        "41:U-1",
        apply=True,
    )

    assert applied.status == "MIGRATED"
    assert fresh.estimated_bonus is None
    assert fresh.estimated_bonus_cents == 0
    assert fresh.amount_encoding_version == 2
    assert fresh.save_calls == 1

    already_v2 = elite_record(version=2, estimated_bonus=None, cents=99)
    install_model(monkeypatch, migration, "EliteBonusStats", [already_v2])

    repeated = migration.migrate_elite_bonus_stats_record(
        41,
        "41:U-1",
        apply=True,
    )

    assert repeated.status == "ALREADY_V2"
    assert already_v2.estimated_bonus_cents == 99
    assert already_v2.save_calls == 0
