from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from Common.PeriodResolver import MappingPeriodRepository, PeriodResolver
from MessageConsumer.PvEventNormalizer import (
    EventIdentityConflict,
    InMemoryEventRegistry,
    PvEventNormalizer,
)
from Order.RefundReversalLedger import (
    InMemoryRefundReversalLedger,
    MappingOriginalOrderRepository,
    OriginalOrderNotRefundable,
    OriginalOrderUnavailable,
    RedisRefundReversalLedger,
    RefundReversalConflict,
)


@pytest.fixture
def period_repository():
    return MappingPeriodRepository(
        [
            {"PERIOD_NUM": 40, "CALC_YEAR": 2025, "CALC_MONTH": 12},
            {"PERIOD_NUM": 41, "CALC_YEAR": 2026, "CALC_MONTH": 1},
            {"PERIOD_NUM": 45, "CALC_YEAR": 2026, "CALC_MONTH": 2},
        ]
    )


@pytest.fixture
def event_registry():
    return InMemoryEventRegistry()


@pytest.fixture
def refund_ledger():
    return InMemoryRefundReversalLedger()


@pytest.fixture
def order_repository():
    return MappingOriginalOrderRepository(
        {
            "O-1": {"amount_units": 100_250_000, "refundable": True},
            "O-RETRY": {"amount_units": 100_250_000, "refundable": True},
            "O-CONFLICT": {"amount_units": 100_250_000, "refundable": True},
        }
    )


def test_period_and_refund_contract(
    period_repository,
    event_registry,
    refund_ledger,
    order_repository,
) -> None:
    resolver = PeriodResolver(period_repository)
    snap = resolver.resolve_approval_time(
        datetime(2026, 1, 31, 16, 0, tzinfo=timezone.utc)
    )
    assert snap.calc_year == 2026
    assert snap.calc_month == 2
    normalizer = PvEventNormalizer(resolver, event_registry, refund_ledger, order_repository=order_repository)
    first = normalizer.normalize_refund(
        {
            "source_event_id": "R-1",
            "original_order_id": "O-1",
            "amount": "100.25",
            "approved_at": "2026-01-31T16:00:00Z",
        }
    )
    second = normalizer.normalize_refund(
        {
            "source_event_id": "R-2",
            "original_order_id": "O-1",
            "amount": "100.25",
            "approved_at": "2026-01-31T16:00:00Z",
        }
    )
    assert first.effective_pv_delta_units == -100_250_000
    assert second.disposition == "DUPLICATE_NOOP"
    assert second.effective_pv_delta_units == 0
    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_order({"source_event_id": "O-X", "amount": 30.0})


def test_refund_retry_rechecks_ledger_after_transient_failure(
    period_repository,
    order_repository,
) -> None:
    class FailOnceLedger:
        def __init__(self):
            self._failed = False
            self._delegate = InMemoryRefundReversalLedger()

        def claim_whole_order(self, **kwargs):
            if not self._failed:
                self._failed = True
                raise RuntimeError("transient ledger failure")
            return self._delegate.claim_whole_order(**kwargs)

    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        FailOnceLedger(),
        order_repository=order_repository,
    )
    payload = {
        "source_event_id": "R-RETRY",
        "original_order_id": "O-RETRY",
        "amount": "100.25",
        "approved_at": "2026-01-31T16:00:00Z",
    }

    with pytest.raises(RuntimeError, match="transient ledger failure"):
        normalizer.normalize_refund(payload)

    retried = normalizer.normalize_refund(payload)
    assert retried.disposition == "APPLY"
    assert retried.effective_pv_delta_units == -100_250_000


def test_exact_refund_retry_remains_noop_after_authority_status_changes(
    period_repository,
) -> None:
    authoritative_record = {
        "amount_units": 100_250_000,
        "refundable": True,
    }
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=MappingOriginalOrderRepository(
            {"O-HISTORY": authoritative_record}
        ),
    )
    payload = {
        "source_event_id": "R-HISTORY",
        "original_order_id": "O-HISTORY",
        "amount": "100.25",
        "approved_at": "2026-01-31T16:00:00Z",
    }

    first = normalizer.normalize_refund(payload)
    authoritative_record["refundable"] = False
    duplicate = normalizer.normalize_refund(payload)

    assert first.disposition == "APPLY"
    assert duplicate.disposition == "DUPLICATE_NOOP"
    assert duplicate.effective_pv_delta_units == 0


def test_refund_conflict_is_not_swallowed_by_duplicate_registry(
    period_repository,
    order_repository,
) -> None:
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_repository,
    )
    normalizer.normalize_refund(
        {
            "source_event_id": "R-ORIGINAL",
            "original_order_id": "O-CONFLICT",
            "amount": "100.25",
            "approved_at": "2026-01-31T16:00:00Z",
        }
    )
    conflicting_payload = {
        "source_event_id": "R-CONFLICT",
        "original_order_id": "O-CONFLICT",
        "amount": "99.00",
        "approved_at": "2026-01-31T16:00:00Z",
    }

    with pytest.raises(RefundReversalConflict):
        normalizer.normalize_refund(conflicting_payload)
    with pytest.raises(RefundReversalConflict):
        normalizer.normalize_refund(conflicting_payload)


def test_refund_requires_authoritative_order_amount(period_repository) -> None:
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=MappingOriginalOrderRepository(
            {"O-AUTH": {"amount_units": 100_250_000, "refundable": True}}
        ),
    )

    with pytest.raises(RefundReversalConflict, match="authoritative original order"):
        normalizer.normalize_refund(
            {
                "source_event_id": "R-AUTH",
                "original_order_id": "O-AUTH",
                "amount": "99.00",
                "approved_at": "2026-01-31T16:00:00Z",
            }
        )


def test_refund_blocks_missing_or_nonrefundable_authority(period_repository) -> None:
    missing = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=MappingOriginalOrderRepository({}),
    )
    payload = {
        "source_event_id": "R-MISSING",
        "original_order_id": "O-MISSING",
        "amount": "1.00",
        "approved_at": "2026-01-31T16:00:00Z",
    }
    with pytest.raises(OriginalOrderUnavailable):
        missing.normalize_refund(payload)

    blocked = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=MappingOriginalOrderRepository(
            {"O-BLOCKED": {"amount_units": 1_000_000, "refundable": False}}
        ),
    )
    with pytest.raises(OriginalOrderNotRefundable):
        blocked.normalize_refund(dict(payload, original_order_id="O-BLOCKED"))

@pytest.mark.parametrize(
    "bad_amount",
    [30.0, True, None, "3e1", " 30.00", "30.00 ", "NaN", "Infinity", "30.001"],
)
def test_raw_amount_rejects_noncanonical_values(
    period_repository,
    bad_amount,
) -> None:
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
    )

    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_order(
            {
                "source_event_id": "O-X",
                "amount": bad_amount,
                "period_num": 41,
            }
        )


def test_order_amount_is_scaled_exactly_once(period_repository) -> None:
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        source_system="ORDER_API",
    )

    event = normalizer.normalize_order(
        {
            "source_event_id": "O-30",
            "amount": "30.00",
            "previous_amount": "0.00",
            "period_num": 41,
            "business_revision": 7,
            "previous_business_revision": 6,
        }
    )

    assert event.effective_pv_delta_units == 30_000_000
    assert event.amount_encoding_version == 2
    assert event.business_revision == 7
    assert event.previous_business_revision == 6
    assert event.identity == "ORDER_API:O-30"


def test_same_identity_with_different_hash_is_blocked(period_repository) -> None:
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
    )
    normalizer.normalize_order(
        {"source_event_id": "O-1", "amount": "1.00", "period_num": 41}
    )

    with pytest.raises(EventIdentityConflict):
        normalizer.normalize_order(
            {"source_event_id": "O-1", "amount": "2.00", "period_num": 41}
        )


def test_exact_duplicate_event_is_noop(period_repository) -> None:
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
    )
    payload = {"source_event_id": "O-1", "amount": "1.00", "period_num": 41}

    first = normalizer.normalize_order(payload)
    second = normalizer.normalize_order(payload)

    assert first.disposition == "APPLY"
    assert first.effective_pv_delta_units == 1_000_000
    assert second.disposition == "DUPLICATE_NOOP"
    assert second.effective_pv_delta_units == 0


def test_normalized_event_is_immutable(period_repository) -> None:
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
    )
    event = normalizer.normalize_order(
        {"source_event_id": "O-1", "amount": "1.00", "period_num": 41}
    )

    with pytest.raises(FrozenInstanceError):
        event.effective_pv_delta_units = 2_000_000


def test_business_revision_delta_is_new_amount_minus_previous(period_repository) -> None:
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
    )

    event = normalizer.normalize_order(
        {
            "source_event_id": "O-REV-2",
            "amount": "100.25",
            "previous_amount": "30.00",
            "period_num": 41,
            "business_revision": 2,
            "previous_business_revision": 1,
        }
    )

    assert event.effective_pv_delta_units == 70_250_000


def test_revision_and_previous_amount_must_be_paired(period_repository) -> None:
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
    )

    with pytest.raises(ValueError):
        normalizer.normalize_order(
            {
                "source_event_id": "O-REV-X",
                "amount": "100.25",
                "period_num": 41,
                "business_revision": 2,
                "previous_business_revision": 1,
            }
        )

    with pytest.raises(ValueError):
        normalizer.normalize_order(
            {
                "source_event_id": "O-REV-Y",
                "amount": "100.25",
                "previous_amount": "30.00",
                "period_num": 41,
            }
        )


class _FakeRedis:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def eval(self, *args):
        self.calls.append(args)
        return self.response


def test_redis_refund_ledger_uses_one_atomic_eval() -> None:
    redis_conn = _FakeRedis([b"APPLIED", b"100250000"])
    ledger = RedisRefundReversalLedger(redis_conn)

    claim = ledger.claim_whole_order(
        original_order_id="O-1",
        source_event_id="R-1",
        payload_hash="a" * 64,
        original_amount_units=100_250_000,
        original_order_refundable=True,
    )

    assert claim.disposition == "APPLIED"
    assert claim.original_amount_units == 100_250_000
    assert len(redis_conn.calls) == 1
    assert redis_conn.calls[0][1] == 1
    assert redis_conn.calls[0][2] == "pvam:refund_reversal:O-1"


def test_redis_refund_ledger_blocks_new_nonrefundable_order() -> None:
    redis_conn = _FakeRedis([b"NOT_REFUNDABLE", b"100250000"])
    ledger = RedisRefundReversalLedger(redis_conn)

    with pytest.raises(OriginalOrderNotRefundable):
        ledger.claim_whole_order(
            original_order_id="O-BLOCKED",
            source_event_id="R-BLOCKED",
            payload_hash="c" * 64,
            original_amount_units=100_250_000,
            original_order_refundable=False,
        )
    assert redis_conn.calls[0][-1] == "0"


def test_redis_refund_ledger_blocks_conflicting_amount() -> None:
    redis_conn = _FakeRedis([b"CONFLICT", b"100250000"])
    ledger = RedisRefundReversalLedger(redis_conn)

    with pytest.raises(RefundReversalConflict):
        ledger.claim_whole_order(
            original_order_id="O-1",
            source_event_id="R-2",
            payload_hash="b" * 64,
            original_amount_units=99_000_000,
            original_order_refundable=True,
        )
