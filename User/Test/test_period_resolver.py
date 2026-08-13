import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from Common.PeriodResolver import (
    ContractPeriodRepository,
    MappingPeriodRepository,
    PeriodResolutionError,
    PeriodResolver,
    PeriodSnapshot,
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


@pytest.mark.parametrize(
    ("period_num", "expected_previous"),
    [(1, None), (2, 1), (41, 40)],
)
def test_contract_period_repository_uses_dec_011_arithmetic(
    period_num,
    expected_previous,
) -> None:
    snapshot = ContractPeriodRepository().resolve_current(period_num)
    checksum_payload = {"contract": "DEC-011", "period": period_num}
    expected_checksum = hashlib.sha256(
        json.dumps(
            checksum_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    assert snapshot.period_num == period_num
    assert snapshot.first_period_num == 1
    assert snapshot.previous_period_num == expected_previous
    assert snapshot.calc_year is None
    assert snapshot.calc_month is None
    assert snapshot.source_checksum == expected_checksum


@pytest.mark.parametrize("bad_period", [0, -1, True, "41"])
def test_contract_period_repository_rejects_invalid_message_period(
    bad_period,
) -> None:
    with pytest.raises((TypeError, PeriodResolutionError)):
        ContractPeriodRepository().resolve_current(bad_period)


def test_contract_period_repository_retires_approval_time_resolution() -> None:
    with pytest.raises(
        PeriodResolutionError,
        match="approval-time resolution retired by DEC-011",
    ):
        ContractPeriodRepository().resolve_approved_at(
            datetime(2026, 2, 1, tzinfo=timezone.utc)
        )


def test_approval_time_rejects_snapshot_without_calendar_fields() -> None:
    class CalendarlessRepository:
        def resolve_current(self, period_num):
            raise AssertionError("not used")

        def resolve_approved_at(self, approved_at):
            return PeriodSnapshot(
                period_num=41,
                calc_year=None,
                calc_month=None,
                first_period_num=1,
                previous_period_num=40,
                source_checksum="calendarless-test-snapshot",
            )

    resolver = PeriodResolver(CalendarlessRepository())

    with pytest.raises(PeriodResolutionError, match="calendar fields"):
        resolver.resolve_approval_time(datetime(2026, 2, 1, tzinfo=timezone.utc))


@pytest.mark.parametrize(
    ("calc_year", "calc_month"),
    [(2026, None), (None, 2)],
)
def test_period_snapshot_rejects_partial_calendar_fields(
    calc_year,
    calc_month,
) -> None:
    with pytest.raises(PeriodResolutionError, match="both present or both None"):
        PeriodSnapshot(
            period_num=41,
            calc_year=calc_year,
            calc_month=calc_month,
            first_period_num=1,
            previous_period_num=40,
            source_checksum="partial-calendar-test",
        )
