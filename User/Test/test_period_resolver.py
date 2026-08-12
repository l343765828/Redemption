from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from Common.PeriodResolver import (
    MappingPeriodRepository,
    PeriodResolutionError,
    PeriodResolver,
)


@pytest.fixture
def period_rows():
    return [
        {"PERIOD_NUM": 40, "CALC_YEAR": 2025, "CALC_MONTH": 12},
        {"PERIOD_NUM": 41, "CALC_YEAR": 2026, "CALC_MONTH": 1},
        {"PERIOD_NUM": 45, "CALC_YEAR": 2026, "CALC_MONTH": 2},
    ]


def test_current_uses_min_and_real_previous_row(period_rows) -> None:
    resolver = PeriodResolver(MappingPeriodRepository(period_rows))

    snap = resolver.resolve_current(41)

    assert snap.first_period_num == 40
    assert snap.period_num == 41
    assert snap.previous_period_num == 40
    assert len(snap.source_checksum) == 64


def test_approval_time_is_resolved_in_gmt_plus_8(period_rows) -> None:
    resolver = PeriodResolver(MappingPeriodRepository(period_rows))

    snap = resolver.resolve_approval_time(
        datetime(2026, 1, 31, 16, 0, tzinfo=timezone.utc)
    )

    assert snap.period_num == 45
    assert snap.calc_year == 2026
    assert snap.calc_month == 2
    assert snap.previous_period_num == 41


def test_first_period_has_no_previous(period_rows) -> None:
    resolver = PeriodResolver(MappingPeriodRepository(period_rows))

    snap = resolver.resolve_current(40)

    assert snap.first_period_num == 40
    assert snap.previous_period_num is None


def test_period_snapshot_is_immutable(period_rows) -> None:
    snap = PeriodResolver(MappingPeriodRepository(period_rows)).resolve_current(41)

    with pytest.raises(FrozenInstanceError):
        snap.period_num = 99


def test_duplicate_period_num_is_rejected(period_rows) -> None:
    rows = period_rows + [
        {"PERIOD_NUM": 41, "CALC_YEAR": 2026, "CALC_MONTH": 1}
    ]
    resolver = PeriodResolver(MappingPeriodRepository(rows))

    with pytest.raises(PeriodResolutionError):
        resolver.resolve_current(41)


def test_naive_approval_time_is_rejected(period_rows) -> None:
    resolver = PeriodResolver(MappingPeriodRepository(period_rows))

    with pytest.raises(PeriodResolutionError):
        resolver.resolve_approval_time(datetime(2026, 2, 1, 0, 0))
