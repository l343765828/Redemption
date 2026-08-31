import ast
from dataclasses import FrozenInstanceError
import importlib
from pathlib import Path

import pytest

from Common.PeriodResolver import MappingPeriodRepository, PeriodResolver
from MessageConsumer.PvEventNormalizer import (
    EventIdentityConflict,
    InMemoryEventRegistry,
    PvEventNormalizer,
)
from Order.ConsumedOrderLedger import (
    ConsumedOrderConflict,
    InMemoryConsumedOrderLedger,
    RedisConsumedOrderLedger,
)
from Order.PvEventDeliveryLedger import (
    DeliveryIdentityConflict,
    InMemoryPvEventDeliveryLedger,
)
from Order.RefundReversalLedger import (
    InMemoryRefundReversalLedger,
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
def order_ledger():
    return InMemoryConsumedOrderLedger()


def _normalizer(
    resolver,
    event_registry,
    refund_ledger,
    *,
    order_repository=None,
):
    return PvEventNormalizer(
        resolver,
        event_registry,
        refund_ledger,
        order_repository=order_repository,
        delivery_ledger=InMemoryPvEventDeliveryLedger(),
    )


@pytest.fixture
def order_repository():
    ledger = InMemoryConsumedOrderLedger()
    ledger.record_order("O-1", 100_250_000, 44)
    ledger.record_order("O-RETRY", 100_250_000, 44)
    ledger.record_order("O-CONFLICT", 100_250_000, 44)
    return ledger


def test_period_and_refund_contract(
    period_repository,
    event_registry,
    refund_ledger,
    order_repository,
) -> None:
    resolver = PeriodResolver(period_repository)
    normalizer = _normalizer(resolver, event_registry, refund_ledger, order_repository=order_repository)
    first = normalizer.normalize_refund(
        {
            "order_id": "R-1",
            "user_id": "U-1",
            "period": 45,
            "original_order_id": "O-1",
            "amount": "100.25",
        }
    )
    second = normalizer.normalize_refund(
        {
            "order_id": "R-2",
            "user_id": "U-1",
            "period": 45,
            "original_order_id": "O-1",
            "amount": "100.25",
        }
    )
    assert first.effective_pv_delta_units == -100_250_000
    assert first.period_snapshot.period_num == 45
    assert first.user_id == "U-1"
    assert second.disposition == "DUPLICATE_NOOP"
    assert second.effective_pv_delta_units == 0
    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_order(
            {"order_id": "O-X", "user_id": "U-X", "period": 45, "bv": 30.0}
        )


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

    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        FailOnceLedger(),
        order_repository=order_repository,
    )
    payload = {
        "order_id": "R-RETRY",
        "user_id": "U-RETRY",
        "period": 45,
        "original_order_id": "O-RETRY",
        "amount": "100.25",
    }

    with pytest.raises(RuntimeError, match="transient ledger failure"):
        normalizer.normalize_refund(payload)

    retried = normalizer.normalize_refund(payload)
    assert retried.disposition == "APPLY"
    assert retried.effective_pv_delta_units == -100_250_000


def test_exact_refund_retry_remains_noop(
    period_repository,
) -> None:
    order_ledger = InMemoryConsumedOrderLedger()
    order_ledger.record_order("O-HISTORY", 100_250_000, 44)
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )
    payload = {
        "order_id": "R-HISTORY",
        "user_id": "U-HISTORY",
        "period": 45,
        "original_order_id": "O-HISTORY",
        "amount": "100.25",
    }

    first = normalizer.normalize_refund(payload)
    normalizer.acknowledge_dispatched(first)
    duplicate = normalizer.normalize_refund(payload)

    assert first.disposition == "APPLY"
    assert duplicate.disposition == "DUPLICATE_NOOP"
    assert duplicate.effective_pv_delta_units == 0


def test_refund_conflict_is_not_swallowed_by_duplicate_registry(
    period_repository,
    order_repository,
) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_repository,
    )
    normalizer.normalize_refund(
        {
            "order_id": "R-ORIGINAL",
            "user_id": "U-CONFLICT",
            "period": 45,
            "original_order_id": "O-CONFLICT",
            "amount": "100.25",
        }
    )
    conflicting_payload = {
        "order_id": "R-CONFLICT",
        "user_id": "U-CONFLICT",
        "period": 45,
        "original_order_id": "O-CONFLICT",
        "amount": "99.00",
    }

    with pytest.raises(RefundReversalConflict):
        normalizer.normalize_refund(conflicting_payload)
    with pytest.raises(RefundReversalConflict):
        normalizer.normalize_refund(conflicting_payload)


def test_refund_requires_authoritative_order_amount(period_repository) -> None:
    order_ledger = InMemoryConsumedOrderLedger()
    order_ledger.record_order("O-AUTH", 100_250_000, 44)
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )

    with pytest.raises(RefundReversalConflict, match="authoritative original order"):
        normalizer.normalize_refund(
            {
                "order_id": "R-AUTH",
                "user_id": "U-AUTH",
                "period": 45,
                "original_order_id": "O-AUTH",
                "amount": "99.00",
            }
        )


def test_refund_blocks_missing_authority(period_repository) -> None:
    missing = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
    )
    payload = {
        "order_id": "R-MISSING",
        "user_id": "U-MISSING",
        "period": 45,
        "original_order_id": "O-MISSING",
        "amount": "1.00",
    }
    with pytest.raises(OriginalOrderUnavailable):
        missing.normalize_refund(payload)

@pytest.mark.parametrize(
    "bad_amount",
    [30.0, True, None, "3e1", " 30.00", "30.00 ", "NaN", "Infinity", "30.001"],
)
def test_raw_amount_rejects_noncanonical_values(
    period_repository,
    order_ledger,
    bad_amount,
) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )

    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_order(
            {
                "order_id": "O-X",
                "user_id": "U-X",
                "bv": bad_amount,
                "period": 41,
            }
        )


def test_order_amount_is_scaled_exactly_once(period_repository, order_ledger) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )

    event = normalizer.normalize_order(
        {
            "order_id": "O-30",
            "user_id": "U-30",
            "bv": "30.00",
            "previous_amount": "0.00",
            "period": 41,
            "business_revision": 7,
            "previous_business_revision": 6,
        }
    )

    assert event.effective_pv_delta_units == 30_000_000
    assert event.amount_encoding_version == 2
    assert event.business_revision == 7
    assert event.previous_business_revision == 6
    assert event.identity == "O-30"
    assert event.user_id == "U-30"
    assert event.period_snapshot.period_num == 41


def test_same_identity_with_different_hash_is_blocked(period_repository, order_ledger) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )
    normalizer.normalize_order(
        {"order_id": "O-1", "user_id": "U-1", "bv": "1.00", "period": 41}
    )

    with pytest.raises(EventIdentityConflict):
        normalizer.normalize_order(
            {"order_id": "O-1", "user_id": "U-1", "bv": "2.00", "period": 41}
        )


def test_legacy_source_field_participates_in_process_hash_conflict(
    period_repository,
    order_ledger,
) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )
    payload = {
        "order_id": "O-LEGACY-SOURCE",
        "user_id": "U-1",
        "bv": "1.00",
        "period": 41,
    }
    normalizer.normalize_order(payload)

    with pytest.raises(EventIdentityConflict):
        normalizer.normalize_order(dict(payload, **{"source_system": "LEGACY"}))


def test_legacy_source_field_hits_delivery_conflict_after_restart(
    period_repository,
    order_ledger,
) -> None:
    delivery_ledger = InMemoryPvEventDeliveryLedger()
    payload = {
        "order_id": "O-LEGACY-RESTART",
        "user_id": "U-1",
        "bv": "1.00",
        "period": 41,
    }
    first = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
        delivery_ledger=delivery_ledger,
    )
    first.normalize_order(payload)
    restarted = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
        delivery_ledger=delivery_ledger,
    )

    with pytest.raises(DeliveryIdentityConflict):
        restarted.normalize_order(
            dict(payload, **{"source_system": "LEGACY"})
        )


def test_legacy_source_constant_is_scoped_to_two_hash_regressions() -> None:
    project_root = Path(__file__).resolve().parents[2]
    target = "_".join(("source", "system"))
    allowed = {
        (
            "User/Test/test_pv_event_normalizer.py",
            "test_legacy_source_field_participates_in_process_hash_conflict",
        ),
        (
            "User/Test/test_pv_event_normalizer.py",
            "test_legacy_source_field_hits_delivery_conflict_after_restart",
        ),
    }
    violations = []

    for path in project_root.rglob("*.py"):
        relative = path.relative_to(project_root)
        relative_text = relative.as_posix()
        if (
            "__pycache__" in relative.parts
            or "Doc4" in relative.parts
            or "_bak" in path.name
            or "_final" in path.name
            or relative_text == "User/GraphService.py"
        ):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value != target:
                continue
            owner = None
            parent = parents.get(node)
            while parent is not None:
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    owner = parent.name
                    break
                parent = parents.get(parent)
            location = (relative_text, owner)
            if location not in allowed:
                violations.append(f"{relative_text}:{node.lineno}:{owner}")

    assert violations == []


def test_exact_duplicate_event_is_noop(period_repository, order_ledger) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )
    payload = {"order_id": "O-1", "user_id": "U-1", "bv": "1.00", "period": 41}

    first = normalizer.normalize_order(payload)
    normalizer.acknowledge_dispatched(first)
    second = normalizer.normalize_order(payload)

    assert first.disposition == "APPLY"
    assert first.effective_pv_delta_units == 1_000_000
    assert second.disposition == "DUPLICATE_NOOP"
    assert second.effective_pv_delta_units == 0


def test_normalized_event_is_immutable(period_repository, order_ledger) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )
    event = normalizer.normalize_order(
        {"order_id": "O-1", "user_id": "U-1", "bv": "1.00", "period": 41}
    )

    with pytest.raises(FrozenInstanceError):
        event.effective_pv_delta_units = 2_000_000


def test_business_revision_delta_is_new_amount_minus_previous(period_repository, order_ledger) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )

    event = normalizer.normalize_order(
        {
            "order_id": "O-REV-2",
            "user_id": "U-REV",
            "bv": "100.25",
            "previous_amount": "30.00",
            "period": 41,
            "business_revision": 2,
            "previous_business_revision": 1,
        }
    )

    assert event.effective_pv_delta_units == 70_250_000


def test_revision_and_previous_amount_must_be_paired(period_repository, order_ledger) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )

    with pytest.raises(ValueError):
        normalizer.normalize_order(
            {
                "order_id": "O-REV-X",
                "user_id": "U-REV",
                "bv": "100.25",
                "period": 41,
                "business_revision": 2,
                "previous_business_revision": 1,
            }
        )

    with pytest.raises(ValueError):
        normalizer.normalize_order(
            {
                "order_id": "O-REV-Y",
                "user_id": "U-REV",
                "bv": "100.25",
                "previous_amount": "30.00",
                "period": 41,
            }
        )


def test_order_requires_message_period_and_user_id(period_repository, order_ledger) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )

    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_order(
            {
                "order_id": "O-NO-PERIOD",
                "user_id": "U-1",
                "bv": "1.00",
                "approved_at": "2026-01-31T16:00:00Z",
            }
        )
    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_order(
            {"order_id": "O-NO-USER", "period": 41, "bv": "1.00"}
        )


@pytest.mark.parametrize("bad_period", [0, -1, "41", True, 41.0])
def test_order_rejects_non_integer_message_period(
    period_repository,
    order_ledger,
    bad_period,
) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )

    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_order(
            {
                "order_id": "O-BAD-PERIOD",
                "user_id": "U-1",
                "period": bad_period,
                "bv": "1.00",
            }
        )


@pytest.mark.parametrize("bad_period", [0, -1, "45", True, 45.0])
def test_refund_rejects_non_integer_message_period(
    period_repository,
    order_repository,
    bad_period,
) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_repository,
    )

    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_refund(
            {
                "order_id": "R-BAD-PERIOD",
                "user_id": "U-1",
                "period": bad_period,
                "original_order_id": "O-1",
                "amount": "100.25",
            }
        )


def test_refund_requires_message_period_and_user_id(
    period_repository,
    order_repository,
) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_repository,
    )

    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_refund(
            {
                "order_id": "R-NO-PERIOD",
                "user_id": "U-1",
                "original_order_id": "O-1",
                "amount": "100.25",
            }
        )
    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_refund(
            {
                "order_id": "R-NO-USER",
                "period": 45,
                "original_order_id": "O-1",
                "amount": "100.25",
            }
        )


def test_refund_uses_message_period_without_approved_at(
    period_repository,
    order_repository,
) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_repository,
    )

    event = normalizer.normalize_refund(
        {
            "order_id": "R-MESSAGE-PERIOD",
            "user_id": "U-1",
            "period": 45,
            "original_order_id": "O-1",
            "amount": "100.25",
        }
    )

    assert event.period_snapshot.period_num == 45
    assert event.user_id == "U-1"


def test_refund_rejects_invalid_optional_approved_at(
    period_repository,
    order_repository,
) -> None:
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_repository,
    )

    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_refund(
            {
                "order_id": "R-BAD-AUDIT-TIME",
                "user_id": "U-1",
                "period": 45,
                "original_order_id": "O-1",
                "amount": "100.25",
                "approved_at": "2026-02-01T00:00:00",
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
    redis_conn = _FakeRedis([b"APPLIED", b"100250000", b"1"])
    ledger = RedisRefundReversalLedger(redis_conn)

    claim = ledger.claim_whole_order(
        original_order_id="O-1",
        event_identity="REFUND_API:R-1",
        payload_hash="a" * 64,
        original_amount_units=100_250_000,
        original_order_refundable=True,
    )

    assert claim.disposition == "APPLIED"
    assert claim.original_amount_units == 100_250_000
    assert claim.same_event is True
    assert len(redis_conn.calls) == 1
    assert redis_conn.calls[0][1] == 1
    assert redis_conn.calls[0][2] == "pvam:refund_reversal:O-1"
    assert redis_conn.calls[0][3] == "REFUND_API:R-1"
    assert "'event_identity', event_identity" in ledger._CLAIM_SCRIPT
    assert "stored_event_identity == event_identity" in ledger._CLAIM_SCRIPT


def test_redis_refund_ledger_blocks_new_nonrefundable_order() -> None:
    redis_conn = _FakeRedis([b"NOT_REFUNDABLE", b"100250000", b"0"])
    ledger = RedisRefundReversalLedger(redis_conn)

    with pytest.raises(OriginalOrderNotRefundable):
        ledger.claim_whole_order(
            original_order_id="O-BLOCKED",
            event_identity="REFUND_API:R-BLOCKED",
            payload_hash="c" * 64,
            original_amount_units=100_250_000,
            original_order_refundable=False,
        )
    assert redis_conn.calls[0][-1] == "0"


def test_redis_refund_ledger_blocks_conflicting_amount() -> None:
    redis_conn = _FakeRedis([b"CONFLICT", b"100250000", b"0"])
    ledger = RedisRefundReversalLedger(redis_conn)

    with pytest.raises(RefundReversalConflict):
        ledger.claim_whole_order(
            original_order_id="O-1",
            event_identity="REFUND_API:R-2",
            payload_hash="b" * 64,
            original_amount_units=99_000_000,
            original_order_refundable=True,
        )



def test_redis_refund_ledger_marks_other_refund_as_different_event() -> None:
    redis_conn = _FakeRedis([b"DUPLICATE_NOOP", b"100250000", b"0"])
    ledger = RedisRefundReversalLedger(redis_conn)

    claim = ledger.claim_whole_order(
        original_order_id="O-1",
        event_identity="REFUND_API:R-OTHER",
        payload_hash="c" * 64,
        original_amount_units=100_250_000,
        original_order_refundable=True,
    )

    assert claim.same_event is False

def test_in_memory_consumed_order_ledger_is_idempotent_and_conflicts() -> None:
    ledger = InMemoryConsumedOrderLedger()

    ledger.record_order("O-LEDGER", 100_250_000, 44)
    ledger.record_order("O-LEDGER", 100_250_000, 44)

    snapshot = ledger.get_refundable_order("O-LEDGER")
    assert snapshot.original_order_id == "O-LEDGER"
    assert snapshot.amount_units == 100_250_000
    assert snapshot.refundable is True
    assert ledger.get_order_period("O-LEDGER") == 44

    with pytest.raises(ConsumedOrderConflict):
        ledger.record_order("O-LEDGER", 99_000_000, 44)
    with pytest.raises(ConsumedOrderConflict):
        ledger.record_order("O-LEDGER", 100_250_000, 45)


def test_in_memory_consumed_order_ledger_keeps_current_and_previous_period() -> None:
    ledger = InMemoryConsumedOrderLedger()
    ledger.record_order("O-40", 40_000_000, 40)
    ledger.record_order("O-41", 41_000_000, 41)
    ledger.record_order("O-42", 42_000_000, 42)

    ledger.purge_periods_before(42)

    with pytest.raises(OriginalOrderUnavailable):
        ledger.get_refundable_order("O-40")
    assert ledger.get_order_period("O-41") == 41
    assert ledger.get_order_period("O-42") == 42


def test_normalizer_requires_consumed_order_ledger(period_repository) -> None:
    with pytest.raises(TypeError, match="consumed order ledger"):
        _normalizer(
            PeriodResolver(period_repository),
            InMemoryEventRegistry(),
            InMemoryRefundReversalLedger(),
        )


def test_order_normalization_records_consumed_order_authority(
    period_repository,
) -> None:
    order_ledger = InMemoryConsumedOrderLedger()
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )

    event = normalizer.normalize_order(
        {
            "order_id": "O-RECORDED",
            "user_id": "U-1",
            "period": 41,
            "bv": "100.25",
        }
    )

    snapshot = order_ledger.get_refundable_order("O-RECORDED")
    assert event.disposition == "APPLY"
    assert snapshot.amount_units == 100_250_000
    assert order_ledger.get_order_period("O-RECORDED") == 41


def test_redis_consumed_order_ledger_records_with_one_atomic_eval() -> None:
    redis_conn = _FakeRedis(b"RECORDED")
    ledger = RedisConsumedOrderLedger(redis_conn)

    ledger.record_order("O-REDIS", 100_250_000, 44)

    assert len(redis_conn.calls) == 1
    assert redis_conn.calls[0][1] == 2
    assert redis_conn.calls[0][2] == "pvam:order_ledger:O-REDIS"
    assert redis_conn.calls[0][3] == "pvam:order_ledger:__period_index__"
    assert redis_conn.calls[0][-3:] == ("O-REDIS", "100250000", "44")


def test_redis_consumed_order_ledger_blocks_conflicting_record() -> None:
    ledger = RedisConsumedOrderLedger(_FakeRedis(b"CONFLICT"))

    with pytest.raises(ConsumedOrderConflict):
        ledger.record_order("O-REDIS", 99_000_000, 44)


def test_redis_consumed_order_ledger_reads_and_purges_without_real_redis() -> None:
    read_conn = _FakeRedis([b"FOUND", b"100250000", b"44"])
    ledger = RedisConsumedOrderLedger(read_conn)

    snapshot = ledger.get_refundable_order("O-REDIS")
    period = ledger.get_order_period("O-REDIS")

    assert snapshot.amount_units == 100_250_000
    assert snapshot.refundable is True
    assert period == 44
    purge_conn = _FakeRedis(1)
    RedisConsumedOrderLedger(purge_conn).purge_periods_before(46)
    assert purge_conn.calls[0][1] == 1
    assert purge_conn.calls[0][2] == "pvam:order_ledger:__period_index__"
    assert purge_conn.calls[0][-1] == "44"


def test_order_retry_records_consumed_ledger_after_transient_failure(
    period_repository,
) -> None:
    class FailOnceOrderLedger:
        def __init__(self):
            self._failed = False
            self._delegate = InMemoryConsumedOrderLedger()

        def record_order(self, order_id, amount_units, period):
            if not self._failed:
                self._failed = True
                raise RuntimeError("transient order ledger failure")
            return self._delegate.record_order(order_id, amount_units, period)

        def get_refundable_order(self, original_order_id):
            return self._delegate.get_refundable_order(original_order_id)

        def get_order_period(self, original_order_id):
            return self._delegate.get_order_period(original_order_id)

        def purge_periods_before(self, period):
            self._delegate.purge_periods_before(period)

    order_ledger = FailOnceOrderLedger()
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )
    payload = {
        "order_id": "O-LEDGER-RETRY",
        "user_id": "U-1",
        "period": 41,
        "bv": "100.25",
    }

    with pytest.raises(RuntimeError, match="transient order ledger failure"):
        normalizer.normalize_order(payload)

    retried = normalizer.normalize_order(payload)
    assert retried.disposition == "APPLY"
    assert retried.effective_pv_delta_units == 100_250_000
    assert order_ledger.get_refundable_order("O-LEDGER-RETRY").amount_units == 100_250_000


def test_previous_period_order_refund_lands_in_message_period(
    period_repository,
) -> None:
    order_ledger = InMemoryConsumedOrderLedger()
    order_ledger.record_order("O-PREVIOUS", 100_250_000, 44)
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )

    event = normalizer.normalize_refund(
        {
            "order_id": "R-PREVIOUS",
            "user_id": "U-1",
            "period": 45,
            "original_order_id": "O-PREVIOUS",
            "amount": "100.25",
        }
    )

    assert event.effective_pv_delta_units == -100_250_000
    assert event.period_snapshot.period_num == 45


def test_refund_rejects_order_older_than_previous_period(
    period_repository,
) -> None:
    order_ledger = InMemoryConsumedOrderLedger()
    order_ledger.record_order("O-TOO-OLD", 100_250_000, 43)
    normalizer = _normalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
    )

    with pytest.raises(RefundReversalConflict, match="period"):
        normalizer.normalize_refund(
            {
                "order_id": "R-TOO-OLD",
                "user_id": "U-1",
                "period": 45,
                "original_order_id": "O-TOO-OLD",
                "amount": "100.25",
            }
        )


def test_in_memory_delivery_ledger_requires_ack_before_dispatched() -> None:
    delivery_module = importlib.import_module("Order.PvEventDeliveryLedger")
    ledger = delivery_module.InMemoryPvEventDeliveryLedger()

    first = ledger.prepare_delivery("ORDER_API:O-1", "a" * 64)
    pending_retry = ledger.prepare_delivery("ORDER_API:O-1", "a" * 64)
    acknowledged = ledger.mark_dispatched("ORDER_API:O-1", "a" * 64)
    dispatched_retry = ledger.prepare_delivery("ORDER_API:O-1", "a" * 64)

    assert first == "PENDING"
    assert pending_retry == "PENDING"
    assert acknowledged == "DISPATCHED"
    assert dispatched_retry == "DISPATCHED"


def test_delivery_ledger_rejects_payload_drift_and_ack_without_pending() -> None:
    delivery_module = importlib.import_module("Order.PvEventDeliveryLedger")
    ledger = delivery_module.InMemoryPvEventDeliveryLedger()
    ledger.prepare_delivery("ORDER_API:O-1", "a" * 64)

    with pytest.raises(delivery_module.DeliveryIdentityConflict):
        ledger.prepare_delivery("ORDER_API:O-1", "b" * 64)
    with pytest.raises(delivery_module.DeliveryStateUnavailable):
        ledger.mark_dispatched("ORDER_API:O-MISSING", "a" * 64)


def test_redis_delivery_ledger_prepares_and_acknowledges_atomically() -> None:
    delivery_module = importlib.import_module("Order.PvEventDeliveryLedger")
    prepare_conn = _FakeRedis(b"PENDING")
    prepare_ledger = delivery_module.RedisPvEventDeliveryLedger(prepare_conn)

    prepared = prepare_ledger.prepare_delivery("ORDER_API:O-1", "a" * 64)

    assert prepared == "PENDING"
    assert len(prepare_conn.calls) == 1
    assert prepare_conn.calls[0][1] == 1
    assert prepare_conn.calls[0][2] == "pvam:event_delivery:ORDER_API:O-1"
    assert prepare_conn.calls[0][-1] == "a" * 64

    ack_conn = _FakeRedis(b"DISPATCHED")
    ack_ledger = delivery_module.RedisPvEventDeliveryLedger(ack_conn)
    acknowledged = ack_ledger.mark_dispatched("ORDER_API:O-1", "a" * 64)

    assert acknowledged == "DISPATCHED"
    assert len(ack_conn.calls) == 1
    assert ack_conn.calls[0][1] == 1
    assert ack_conn.calls[0][2] == "pvam:event_delivery:ORDER_API:O-1"


def test_redis_delivery_ledger_fails_loud_on_conflict_or_missing_ack() -> None:
    delivery_module = importlib.import_module("Order.PvEventDeliveryLedger")
    conflict_ledger = delivery_module.RedisPvEventDeliveryLedger(
        _FakeRedis(b"CONFLICT")
    )
    with pytest.raises(delivery_module.DeliveryIdentityConflict):
        conflict_ledger.prepare_delivery("ORDER_API:O-1", "b" * 64)

    missing_ledger = delivery_module.RedisPvEventDeliveryLedger(
        _FakeRedis(b"MISSING")
    )
    with pytest.raises(delivery_module.DeliveryStateUnavailable):
        missing_ledger.mark_dispatched("ORDER_API:O-1", "a" * 64)


def test_pending_order_replays_delta_until_dispatch_ack(period_repository) -> None:
    delivery_ledger = InMemoryPvEventDeliveryLedger()
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
        delivery_ledger=delivery_ledger,
    )
    payload = {
        "order_id": "O-PENDING",
        "user_id": "U-1",
        "period": 41,
        "bv": "100.25",
    }

    first = normalizer.normalize_order(payload)
    pending_retry = normalizer.normalize_order(payload)
    normalizer.acknowledge_dispatched(first)
    dispatched_retry = normalizer.normalize_order(payload)

    assert first.disposition == "APPLY"
    assert pending_retry.disposition == "APPLY"
    assert pending_retry.effective_pv_delta_units == 100_250_000
    assert dispatched_retry.disposition == "DUPLICATE_NOOP"
    assert dispatched_retry.effective_pv_delta_units == 0


def test_normalizer_requires_delivery_ledger(period_repository) -> None:
    with pytest.raises(TypeError, match="delivery ledger"):
        PvEventNormalizer(
            PeriodResolver(period_repository),
            InMemoryEventRegistry(),
            InMemoryRefundReversalLedger(),
            order_repository=InMemoryConsumedOrderLedger(),
        )


def test_refund_claim_distinguishes_same_event_from_other_refund() -> None:
    ledger = InMemoryRefundReversalLedger()
    first = ledger.claim_whole_order(
        original_order_id="O-CLAIM",
        event_identity="REFUND_API:R-CLAIM-1",
        payload_hash="a" * 64,
        original_amount_units=100_250_000,
        original_order_refundable=True,
    )
    same_event = ledger.claim_whole_order(
        original_order_id="O-CLAIM",
        event_identity="REFUND_API:R-CLAIM-1",
        payload_hash="a" * 64,
        original_amount_units=100_250_000,
        original_order_refundable=True,
    )
    other_refund = ledger.claim_whole_order(
        original_order_id="O-CLAIM",
        event_identity="REFUND_API:R-CLAIM-2",
        payload_hash="b" * 64,
        original_amount_units=100_250_000,
        original_order_refundable=True,
    )

    assert first.same_event is True
    assert same_event.same_event is True
    assert other_refund.same_event is False


def test_other_refund_identity_for_claimed_order_does_not_reapply(
    period_repository,
) -> None:
    order_ledger = InMemoryConsumedOrderLedger()
    order_ledger.record_order("O-ONCE", 100_250_000, 44)
    delivery_ledger = InMemoryPvEventDeliveryLedger()
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
        delivery_ledger=delivery_ledger,
    )

    first = normalizer.normalize_refund(
        {
            "order_id": "R-ONCE-1",
            "user_id": "U-1",
            "period": 45,
            "original_order_id": "O-ONCE",
            "amount": "100.25",
        }
    )
    other_refund = normalizer.normalize_refund(
        {
            "order_id": "R-ONCE-2",
            "user_id": "U-1",
            "period": 45,
            "original_order_id": "O-ONCE",
            "amount": "100.25",
        }
    )

    assert first.effective_pv_delta_units == -100_250_000
    assert other_refund.disposition == "DUPLICATE_NOOP"
    assert other_refund.effective_pv_delta_units == 0


class _RecordingStageServices:
    def __init__(self, calls, *, fail_placement_once=False):
        self.calls = calls
        self.fail_placement_once = fail_placement_once

    def update_elite_performance(self, *, user_id, normalized_event):
        self.calls.append(("user_stats", user_id, normalized_event.identity))

    def update_placement_performance(self, *, user_id, normalized_event):
        self.calls.append(("placement", user_id, normalized_event.identity))
        if self.fail_placement_once:
            self.fail_placement_once = False
            raise RuntimeError("placement stage failed")

    def update_elite_bonus_incremental(self, *, user_id, normalized_event):
        self.calls.append(("elite_bonus", user_id, normalized_event.identity))


class _RecordingDeliveryLedger:
    def __init__(self, calls, *, disconnect_after_first_ack=False):
        self.calls = calls
        self.disconnect_after_first_ack = disconnect_after_first_ack
        self.delegate = InMemoryPvEventDeliveryLedger()

    def prepare_delivery(self, identity, payload_hash):
        return self.delegate.prepare_delivery(identity, payload_hash)

    def mark_dispatched(self, identity, payload_hash):
        status = self.delegate.mark_dispatched(identity, payload_hash)
        self.calls.append(("ack", identity))
        if self.disconnect_after_first_ack:
            self.disconnect_after_first_ack = False
            raise RuntimeError("ack response disconnected after commit")
        return status


def _coordinator_fixture(period_repository, delivery_ledger, stages):
    coordinator_module = importlib.import_module(
        "MessageConsumer.PvEventDispatchCoordinator"
    )
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
        delivery_ledger=delivery_ledger,
    )
    return coordinator_module.PvEventDispatchCoordinator(
        normalizer,
        user_stats_service=stages,
        placement_service=stages,
        elite_bonus_service=stages,
    )


def test_dispatch_coordinator_acks_after_all_three_stages(
    period_repository,
) -> None:
    calls = []
    delivery_ledger = _RecordingDeliveryLedger(calls)
    stages = _RecordingStageServices(calls)
    coordinator = _coordinator_fixture(period_repository, delivery_ledger, stages)
    payload = {
        "order_id": "O-DISPATCH",
        "user_id": "U-DISPATCH",
        "period": 41,
        "bv": "100.25",
    }

    first = coordinator.dispatch_order(payload)
    duplicate = coordinator.dispatch_order(payload)

    assert first.disposition == "APPLY"
    assert duplicate.disposition == "DUPLICATE_NOOP"
    assert calls == [
        ("user_stats", "U-DISPATCH", "O-DISPATCH"),
        ("placement", "U-DISPATCH", "O-DISPATCH"),
        ("elite_bonus", "U-DISPATCH", "O-DISPATCH"),
        ("ack", "O-DISPATCH"),
    ]


def test_dispatch_coordinator_keeps_pending_when_stage_fails(
    period_repository,
) -> None:
    calls = []
    delivery_ledger = _RecordingDeliveryLedger(calls)
    stages = _RecordingStageServices(calls, fail_placement_once=True)
    coordinator = _coordinator_fixture(period_repository, delivery_ledger, stages)
    payload = {
        "order_id": "O-STAGE-RETRY",
        "user_id": "U-STAGE-RETRY",
        "period": 41,
        "bv": "1.00",
    }

    with pytest.raises(RuntimeError, match="placement stage failed"):
        coordinator.dispatch_order(payload)

    retried = coordinator.dispatch_order(payload)
    duplicate = coordinator.dispatch_order(payload)

    assert retried.disposition == "APPLY"
    assert duplicate.disposition == "DUPLICATE_NOOP"
    assert calls == [
        ("user_stats", "U-STAGE-RETRY", "O-STAGE-RETRY"),
        ("placement", "U-STAGE-RETRY", "O-STAGE-RETRY"),
        ("user_stats", "U-STAGE-RETRY", "O-STAGE-RETRY"),
        ("placement", "U-STAGE-RETRY", "O-STAGE-RETRY"),
        ("elite_bonus", "U-STAGE-RETRY", "O-STAGE-RETRY"),
        ("ack", "O-STAGE-RETRY"),
    ]


def test_dispatch_ack_commit_then_disconnect_does_not_reapply(
    period_repository,
) -> None:
    calls = []
    delivery_ledger = _RecordingDeliveryLedger(
        calls,
        disconnect_after_first_ack=True,
    )
    stages = _RecordingStageServices(calls)
    coordinator = _coordinator_fixture(period_repository, delivery_ledger, stages)
    payload = {
        "order_id": "O-ACK-DISCONNECT",
        "user_id": "U-ACK",
        "period": 41,
        "bv": "1.00",
    }

    with pytest.raises(RuntimeError, match="ack response disconnected after commit"):
        coordinator.dispatch_order(payload)

    retried = coordinator.dispatch_order(payload)

    assert retried.disposition == "DUPLICATE_NOOP"
    assert calls == [
        ("user_stats", "U-ACK", "O-ACK-DISCONNECT"),
        ("placement", "U-ACK", "O-ACK-DISCONNECT"),
        ("elite_bonus", "U-ACK", "O-ACK-DISCONNECT"),
        ("ack", "O-ACK-DISCONNECT"),
    ]


def test_order_record_commit_then_disconnect_replays_pending_delta(
    period_repository,
) -> None:
    class CommitThenDisconnectOrderLedger:
        def __init__(self):
            self.failed = False
            self.delegate = InMemoryConsumedOrderLedger()

        def record_order(self, order_id, amount_units, period):
            disposition = self.delegate.record_order(
                order_id,
                amount_units,
                period,
            )
            if not self.failed:
                self.failed = True
                raise RuntimeError("order record response disconnected after commit")
            return disposition

        def get_refundable_order(self, original_order_id):
            return self.delegate.get_refundable_order(original_order_id)

        def get_order_period(self, original_order_id):
            return self.delegate.get_order_period(original_order_id)

        def purge_periods_before(self, period):
            self.delegate.purge_periods_before(period)

    order_ledger = CommitThenDisconnectOrderLedger()
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
        delivery_ledger=InMemoryPvEventDeliveryLedger(),
    )
    payload = {
        "order_id": "O-RECORD-DISCONNECT",
        "user_id": "U-1",
        "period": 41,
        "bv": "100.25",
    }

    with pytest.raises(
        RuntimeError,
        match="order record response disconnected after commit",
    ):
        normalizer.normalize_order(payload)

    retried = normalizer.normalize_order(payload)

    assert retried.disposition == "APPLY"
    assert retried.effective_pv_delta_units == 100_250_000


def test_refund_claim_commit_then_disconnect_replays_pending_delta(
    period_repository,
) -> None:
    class CommitThenDisconnectRefundLedger:
        def __init__(self):
            self.failed = False
            self.delegate = InMemoryRefundReversalLedger()

        def claim_whole_order(self, **kwargs):
            claim = self.delegate.claim_whole_order(**kwargs)
            if not self.failed:
                self.failed = True
                raise RuntimeError("refund claim response disconnected after commit")
            return claim

    order_ledger = InMemoryConsumedOrderLedger()
    order_ledger.record_order("O-REFUND-DISCONNECT", 100_250_000, 44)
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        CommitThenDisconnectRefundLedger(),
        order_repository=order_ledger,
        delivery_ledger=InMemoryPvEventDeliveryLedger(),
    )
    payload = {
        "order_id": "R-CLAIM-DISCONNECT",
        "user_id": "U-1",
        "period": 45,
        "original_order_id": "O-REFUND-DISCONNECT",
        "amount": "100.25",
    }

    with pytest.raises(
        RuntimeError,
        match="refund claim response disconnected after commit",
    ):
        normalizer.normalize_refund(payload)

    retried = normalizer.normalize_refund(payload)

    assert retried.disposition == "APPLY"
    assert retried.effective_pv_delta_units == -100_250_000


def test_delivery_prepare_commit_then_disconnect_replays_pending_delta(
    period_repository,
) -> None:
    class CommitThenDisconnectDeliveryLedger:
        def __init__(self):
            self.failed = False
            self.delegate = InMemoryPvEventDeliveryLedger()

        def prepare_delivery(self, identity, payload_hash):
            status = self.delegate.prepare_delivery(identity, payload_hash)
            if not self.failed:
                self.failed = True
                raise RuntimeError("prepare response disconnected after commit")
            return status

        def mark_dispatched(self, identity, payload_hash):
            return self.delegate.mark_dispatched(identity, payload_hash)

    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
        delivery_ledger=CommitThenDisconnectDeliveryLedger(),
    )
    payload = {
        "order_id": "O-PREPARE-DISCONNECT",
        "user_id": "U-1",
        "period": 41,
        "bv": "100.25",
    }

    with pytest.raises(
        RuntimeError,
        match="prepare response disconnected after commit",
    ):
        normalizer.normalize_order(payload)

    retried = normalizer.normalize_order(payload)

    assert retried.disposition == "APPLY"
    assert retried.effective_pv_delta_units == 100_250_000


def test_order_pending_binds_payload_before_ambiguous_ledger_commit(
    period_repository,
) -> None:
    class CommitThenDisconnectOrderLedger:
        def __init__(self):
            self.failed = False
            self.delegate = InMemoryConsumedOrderLedger()

        def record_order(self, order_id, amount_units, period):
            self.delegate.record_order(order_id, amount_units, period)
            if not self.failed:
                self.failed = True
                raise RuntimeError("order record response disconnected after commit")

        def get_refundable_order(self, original_order_id):
            return self.delegate.get_refundable_order(original_order_id)

        def get_order_period(self, original_order_id):
            return self.delegate.get_order_period(original_order_id)

        def purge_periods_before(self, period):
            self.delegate.purge_periods_before(period)

    order_ledger = CommitThenDisconnectOrderLedger()
    delivery_ledger = InMemoryPvEventDeliveryLedger()
    original = {
        "order_id": "O-BIND-BEFORE-RECORD",
        "user_id": "U-ORIGINAL",
        "period": 41,
        "bv": "100.25",
    }
    first_normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
        delivery_ledger=delivery_ledger,
    )
    with pytest.raises(RuntimeError, match="disconnected after commit"):
        first_normalizer.normalize_order(original)

    restarted_normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
        delivery_ledger=delivery_ledger,
    )
    mutated = dict(original, user_id="U-MUTATED")

    with pytest.raises(DeliveryIdentityConflict):
        restarted_normalizer.normalize_order(mutated)


def test_refund_pending_binds_payload_before_ambiguous_claim_commit(
    period_repository,
) -> None:
    class CommitThenDisconnectRefundLedger:
        def __init__(self):
            self.failed = False
            self.delegate = InMemoryRefundReversalLedger()

        def claim_whole_order(self, **kwargs):
            self.delegate.claim_whole_order(**kwargs)
            if not self.failed:
                self.failed = True
                raise RuntimeError("refund claim response disconnected after commit")
            return self.delegate.claim_whole_order(**kwargs)

    order_ledger = InMemoryConsumedOrderLedger()
    order_ledger.record_order("O-BIND-BEFORE-CLAIM", 100_250_000, 44)
    refund_ledger = CommitThenDisconnectRefundLedger()
    delivery_ledger = InMemoryPvEventDeliveryLedger()
    original = {
        "order_id": "R-BIND-BEFORE-CLAIM",
        "user_id": "U-ORIGINAL",
        "period": 45,
        "original_order_id": "O-BIND-BEFORE-CLAIM",
        "amount": "100.25",
    }
    first_normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        refund_ledger,
        order_repository=order_ledger,
        delivery_ledger=delivery_ledger,
    )
    with pytest.raises(RuntimeError, match="disconnected after commit"):
        first_normalizer.normalize_refund(original)

    restarted_normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        refund_ledger,
        order_repository=order_ledger,
        delivery_ledger=delivery_ledger,
    )
    mutated = dict(original, user_id="U-MUTATED")

    with pytest.raises(DeliveryIdentityConflict):
        restarted_normalizer.normalize_refund(mutated)


def test_dispatch_coordinator_routes_refund_delta_and_then_acks(
    period_repository,
) -> None:
    coordinator_module = importlib.import_module(
        "MessageConsumer.PvEventDispatchCoordinator"
    )
    calls = []
    delivery_ledger = _RecordingDeliveryLedger(calls)
    stages = _RecordingStageServices(calls)
    order_ledger = InMemoryConsumedOrderLedger()
    order_ledger.record_order("O-DISPATCH-REFUND", 100_250_000, 44)
    normalizer = PvEventNormalizer(
        PeriodResolver(period_repository),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=order_ledger,
        delivery_ledger=delivery_ledger,
    )
    coordinator = coordinator_module.PvEventDispatchCoordinator(
        normalizer,
        user_stats_service=stages,
        placement_service=stages,
        elite_bonus_service=stages,
    )

    event = coordinator.dispatch_refund(
        {
            "order_id": "R-DISPATCH",
            "user_id": "U-REFUND",
            "period": 45,
            "original_order_id": "O-DISPATCH-REFUND",
            "amount": "100.25",
        }
    )

    assert event.effective_pv_delta_units == -100_250_000
    assert calls == [
        ("user_stats", "U-REFUND", "R-DISPATCH"),
        ("placement", "U-REFUND", "R-DISPATCH"),
        ("elite_bonus", "U-REFUND", "R-DISPATCH"),
        ("ack", "R-DISPATCH"),
    ]
