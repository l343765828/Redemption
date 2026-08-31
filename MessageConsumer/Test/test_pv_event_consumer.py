from collections import deque
from dataclasses import replace
import json
import logging
from types import SimpleNamespace

import pytest

from Common.PeriodResolver import PeriodResolutionError
from Common.PeriodResolver import MappingPeriodRepository, PeriodResolver
from MessageConsumer.PvEventDispatchCoordinator import PvEventDispatchCoordinator
from MessageConsumer.PvEventNormalizer import EventIdentityConflict
from MessageConsumer.PvEventNormalizer import InMemoryEventRegistry, PvEventNormalizer
from Order.ConsumedOrderLedger import ConsumedOrderConflict
from Order.ConsumedOrderLedger import InMemoryConsumedOrderLedger
from Order.PvEventDeliveryLedger import InMemoryPvEventDeliveryLedger
from Order.RefundReversalLedger import InMemoryRefundReversalLedger
from MessageConsumer.PvEventConsumer import (
    BOUNDED_RETRY_ATTEMPTS,
    CIRCUIT_BREAKER_THRESHOLD,
    ConsumerConfigurationError,
    ConsumerSettings,
    PartitionRef,
    PvEventConsumer,
    TOPIC_ORDERS,
    TOPIC_REFUNDS,
    _STAGE_ORDER,
    load_settings,
)


class TransientFailure(Exception):
    pass


class FakeKafkaException(Exception):
    pass


class FakeRetriableKafkaError:
    def retriable(self):
        return True


class FakeNonRetriableKafkaError:
    def retriable(self):
        return False


class FakeMessage:
    def __init__(
        self,
        payload=None,
        *,
        raw=None,
        topic=TOPIC_ORDERS,
        partition=0,
        offset=10,
        error=None,
    ):
        self._raw = (
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
            if raw is None
            else raw
        )
        self._topic = topic
        self._partition = partition
        self._offset = offset
        self._error = error

    def value(self):
        return self._raw

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset

    def error(self):
        return self._error

    def timestamp(self):
        return (1, 1_787_168_000_000)


class FakeKafkaError:
    def __init__(self, *, fatal=False, code=0):
        self._fatal = fatal
        self._code = code

    def fatal(self):
        return self._fatal

    def code(self):
        return self._code

    def __str__(self):
        return "fake kafka error"


class FakeConsumer:
    def __init__(self, assignments=None):
        self.commits = []
        self.pauses = []
        self.resumes = []
        self.poll_count = 0
        self.poll_timeouts = []
        self.closed = False
        self.subscriptions = []
        self.poll_results = deque()
        self.poll_hook = None
        self._assignments = list(assignments or [])

    def commit(self, *, message, asynchronous):
        self.commits.append((message, asynchronous))

    def pause(self, partitions):
        self.pauses.extend(partitions)

    def resume(self, partitions):
        self.resumes.extend(partitions)

    def poll(self, timeout):
        self.poll_count += 1
        self.poll_timeouts.append(timeout)
        if self.poll_hook is not None:
            self.poll_hook()
        return self.poll_results.popleft() if self.poll_results else None

    def assignment(self):
        return list(self._assignments)

    def subscribe(self, topics, **callbacks):
        self.subscriptions.append((list(topics), callbacks))

    def close(self):
        self.closed = True


class FakeDeliveryMessage:
    def __init__(self, topic, partition, offset):
        self._topic = topic
        self._partition = partition
        self._offset = offset

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset


class FakeProducer:
    def __init__(self, errors=None):
        self.errors = deque(errors or [])
        self.records = []
        self.flush_count = 0

    def produce(self, topic, *, key, value, callback):
        payload = json.loads(value.decode("utf-8"))
        self.records.append(
            {
                "topic": topic,
                "key": key.decode("utf-8"),
                "payload": payload,
                "raw_value": value,
            }
        )
        error = self.errors.popleft() if self.errors else None
        callback(error, FakeDeliveryMessage(topic, 0, len(self.records) - 1))

    def flush(self, timeout):
        self.flush_count += 1
        return 0


class SequenceCoordinator:
    def __init__(self, outcomes=None):
        self.outcomes = deque(outcomes or [SimpleNamespace(disposition="APPLY")])
        self.calls = []

    def _dispatch(self, kind, payload):
        self.calls.append((kind, payload))
        outcome = self.outcomes.popleft() if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def dispatch_order(self, payload):
        return self._dispatch("ORDER", payload)

    def dispatch_refund(self, payload):
        return self._dispatch("REFUND", payload)


@pytest.fixture
def settings():
    return ConsumerSettings(
        kafka_bootstrap="kafka.invalid:9092",
        dask_scheduler="tcp://dask.invalid:8786",
        redis_host="redis.invalid",
        redis_port=6379,
        redis_db=0,
        redis_password="test-password",
        bound_period=41,
        calc_month=209906,
        elite_rate_percent="15",
        ledger_key_prefix=None,
        bounded_retry_attempts=2,
        retry_backoff_base_s=0,
        circuit_breaker_threshold=2,
    )


def build_subject(
    settings,
    *,
    coordinator=None,
    consumer=None,
    producer=None,
    kafka_exception_types=(),
):
    return PvEventConsumer(
        consumer=consumer or FakeConsumer(),
        producer=producer or FakeProducer(),
        coordinator=coordinator or SequenceCoordinator(),
        settings=settings,
        transient_exception_types=(TransientFailure,),
        kafka_exception_types=kafka_exception_types,
        topic_partition_factory=PartitionRef,
        register_signals=False,
        consumer_instance="unit-test-consumer",
    )


def valid_order(**overrides):
    payload = {
        "order_id": "O-1",
        "user_id": "U-1",
        "period": 41,
        "bv": "100.25",
    }
    payload.update(overrides)
    return payload


def test_success_and_duplicate_noop_both_commit_the_exact_message(settings):
    consumer = FakeConsumer()
    coordinator = SequenceCoordinator(
        [SimpleNamespace(disposition="DUPLICATE_NOOP")]
    )
    subject = build_subject(settings, coordinator=coordinator, consumer=consumer)
    message = FakeMessage(valid_order())

    subject.process_message(message)

    assert consumer.commits == [(message, False)]
    assert coordinator.calls == [("ORDER", valid_order())]


def test_refund_topic_dispatches_original_payload_and_commits(settings):
    consumer = FakeConsumer()
    coordinator = SequenceCoordinator()
    subject = build_subject(settings, coordinator=coordinator, consumer=consumer)
    payload = {
        "order_id": "R-1",
        "user_id": "U-1",
        "period": 41,
        "original_order_id": "O-1",
        "amount": "100.25",
    }
    message = FakeMessage(payload, topic=TOPIC_REFUNDS)

    subject.process_message(message)

    assert coordinator.calls == [("REFUND", payload)]
    assert consumer.commits == [(message, False)]


@pytest.mark.parametrize(
    "forbidden",
    [
        {"business_revision": 1},
        {"previous_business_revision": None},
        {"previous_amount": "1.00"},
        {
            "business_revision": 1,
            "previous_business_revision": None,
            "previous_amount": "1.00",
        },
    ],
)
def test_forbidden_fields_are_rejected_by_key_presence(settings, forbidden):
    consumer = FakeConsumer()
    producer = FakeProducer()
    coordinator = SequenceCoordinator()
    subject = build_subject(
        settings,
        consumer=consumer,
        producer=producer,
        coordinator=coordinator,
    )
    message = FakeMessage(valid_order(**forbidden))

    subject.process_message(message)

    assert coordinator.calls == []
    assert consumer.commits == [(message, False)]
    assert producer.records[-1]["payload"]["reason"] == "D9B_FORBIDDEN_FIELD"


@pytest.mark.parametrize("raw", [b"not-json", b"[]"])
def test_invalid_json_or_non_mapping_is_forwarded_before_commit(settings, raw):
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(settings, consumer=consumer, producer=producer)
    message = FakeMessage(raw=raw)

    subject.process_message(message)

    assert producer.records[-1]["payload"]["reason"] == "SCHEMA_VIOLATION"
    assert consumer.commits == [(message, False)]


def test_future_period_pauses_without_dispatch_or_commit(settings):
    consumer = FakeConsumer(assignments=[PartitionRef(TOPIC_ORDERS, 0)])
    coordinator = SequenceCoordinator()
    subject = build_subject(settings, coordinator=coordinator, consumer=consumer)
    message = FakeMessage(valid_order(period=42))

    subject.process_message(message)

    assert coordinator.calls == []
    assert consumer.commits == []
    assert consumer.pauses == [PartitionRef(TOPIC_ORDERS, 0)]
    assert subject.running is False


def test_future_period_with_empty_assignment_does_not_false_drain(settings):
    consumer = FakeConsumer(assignments=[])
    subject = build_subject(settings, consumer=consumer)

    subject.process_message(FakeMessage(valid_order(period=42)))

    assert subject.running is True


def test_all_assigned_partitions_must_report_boundary_before_drain(
    settings,
    caplog,
):
    assignments = [
        PartitionRef(TOPIC_ORDERS, 0),
        PartitionRef(TOPIC_REFUNDS, 0),
    ]
    consumer = FakeConsumer(assignments=assignments)
    subject = build_subject(settings, consumer=consumer)
    caplog.set_level(logging.CRITICAL, logger="MessageConsumer.PvEventConsumer")

    subject.process_message(FakeMessage(valid_order(period=42), partition=0))
    assert subject.running is True
    subject.process_message(
        FakeMessage(
            {
                "order_id": "R-1",
                "user_id": "U-1",
                "period": 42,
                "original_order_id": "O-1",
                "amount": "100.25",
            },
            topic=TOPIC_REFUNDS,
            partition=0,
        )
    )

    assert subject.running is False
    assert consumer.commits == []
    critical_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.CRITICAL
    ]
    assert critical_messages == [
        "PERIOD DRAIN COMPLETE: bound=41 detected=42, safe to rebind"
    ]


def test_expired_previous_period_is_forwarded_with_laggard_marker(settings):
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(settings, consumer=consumer, producer=producer)
    message = FakeMessage(valid_order(period=40))

    subject.process_message(message)

    payload = producer.records[-1]["payload"]
    assert payload["reason"] == "EXPIRED_PERIOD"
    assert payload["suspected_switch_laggard"] is True
    assert consumer.commits == [(message, False)]


def test_boolean_period_reaches_schema_instead_of_boundary_logic(settings):
    normalizer = PvEventNormalizer(
        PeriodResolver(
            MappingPeriodRepository(
                [{"PERIOD_NUM": 41, "CALC_YEAR": 2099, "CALC_MONTH": 6}]
            )
        ),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
        delivery_ledger=InMemoryPvEventDeliveryLedger(),
    )
    coordinator = PvEventDispatchCoordinator(
        normalizer,
        user_stats_service=SimpleNamespace(),
        placement_service=SimpleNamespace(),
        elite_bonus_service=SimpleNamespace(),
    )
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=coordinator,
        consumer=consumer,
        producer=producer,
    )

    subject.process_message(FakeMessage(valid_order(period=True)))

    assert consumer.pauses == []
    assert producer.records[-1]["payload"]["reason"] == "SCHEMA_VIOLATION"


def test_transient_failure_pauses_polls_heartbeats_resumes_and_commits(settings):
    coordinator = SequenceCoordinator(
        [TransientFailure("redis down"), SimpleNamespace(disposition="APPLY")]
    )
    consumer = FakeConsumer()
    subject = build_subject(settings, coordinator=coordinator, consumer=consumer)
    message = FakeMessage(valid_order())

    subject.process_message(message)

    assert consumer.pauses == [PartitionRef(TOPIC_ORDERS, 0)]
    assert consumer.poll_count >= 1
    assert consumer.resumes == [PartitionRef(TOPIC_ORDERS, 0)]
    assert consumer.commits == [(message, False)]


def test_nonzero_backoff_polls_more_than_once(monkeypatch, settings):
    clock = [0.0]
    retry_settings = replace(settings, retry_backoff_base_s=2)
    consumer = FakeConsumer()
    consumer.poll_hook = lambda: clock.__setitem__(0, clock[0] + 0.5)
    subject = build_subject(retry_settings, consumer=consumer)
    monkeypatch.setattr(
        "MessageConsumer.PvEventConsumer.time.monotonic",
        lambda: clock[0],
    )

    subject._heartbeat_backoff(1)

    assert consumer.poll_count == 4


@pytest.mark.parametrize(
    ("attempt", "expected_seconds"),
    [(1, 1), (2, 2), (3, 4), (4, 8), (5, 16), (6, 30), (7, 30)],
)
def test_backoff_delay_doubles_and_caps_at_thirty_seconds(
    monkeypatch,
    settings,
    attempt,
    expected_seconds,
):
    clock = [0.0]
    retry_settings = replace(settings, retry_backoff_base_s=1)
    consumer = FakeConsumer()
    consumer.poll_hook = lambda: clock.__setitem__(0, clock[0] + 1)
    subject = build_subject(retry_settings, consumer=consumer)
    monkeypatch.setattr(
        "MessageConsumer.PvEventConsumer.time.monotonic",
        lambda: clock[0],
    )

    subject._heartbeat_backoff(attempt)

    assert consumer.poll_count == expected_seconds


def test_heartbeat_buffer_overflow_stops_without_exceeding_bound(
    monkeypatch,
    settings,
):
    clock = [0.0]
    retry_settings = replace(settings, retry_backoff_base_s=1)
    consumer = FakeConsumer()
    consumer.poll_results.extend(
        FakeMessage(valid_order(order_id=f"O-BUFFER-{index}"), partition=1)
        for index in range(101)
    )
    consumer.poll_hook = lambda: (
        clock.__setitem__(0, 2.0) if consumer.poll_count >= 101 else None
    )
    subject = build_subject(retry_settings, consumer=consumer)
    monkeypatch.setattr(
        "MessageConsumer.PvEventConsumer.time.monotonic",
        lambda: clock[0],
    )

    subject._heartbeat_backoff(1)

    assert len(subject._buffered_messages) <= 100
    assert subject.running is False
    assert consumer.commits == []


def test_heartbeat_buffered_message_is_polled_during_drain_and_committed_once(
    settings,
):
    coordinator = SequenceCoordinator(
        [TransientFailure("redis down"), SimpleNamespace(disposition="APPLY")]
    )
    consumer = FakeConsumer()
    buffered = FakeMessage(
        valid_order(order_id="O-BUFFERED"),
        partition=1,
        offset=11,
    )
    consumer.poll_results.append(buffered)
    subject = build_subject(settings, coordinator=coordinator, consumer=consumer)
    current = FakeMessage(valid_order(order_id="O-CURRENT"), partition=0)

    subject.process_message(current)
    assert list(subject._buffered_messages) == [buffered]
    consumer.poll_hook = lambda: (
        setattr(subject, "running", False) if consumer.poll_count >= 3 else None
    )
    subject.run()

    assert consumer.poll_timeouts[1] == 0.0
    assert coordinator.calls == [
        ("ORDER", valid_order(order_id="O-CURRENT")),
        ("ORDER", valid_order(order_id="O-CURRENT")),
        ("ORDER", valid_order(order_id="O-BUFFERED")),
    ]
    assert consumer.commits == [(current, False), (buffered, False)]


def test_transient_retry_stops_without_commit_or_resume_on_shutdown(settings):
    coordinator = SequenceCoordinator([TransientFailure("redis down")])
    consumer = FakeConsumer()
    subject = build_subject(settings, coordinator=coordinator, consumer=consumer)
    consumer.poll_hook = lambda: setattr(subject, "running", False)

    subject.process_message(FakeMessage(valid_order()))

    assert consumer.commits == []
    assert consumer.resumes == []


def test_run_closes_after_shutdown_interrupts_transient_retry(settings):
    coordinator = SequenceCoordinator([TransientFailure("redis down")])
    consumer = FakeConsumer()
    subject = build_subject(settings, coordinator=coordinator, consumer=consumer)
    consumer.poll_results.append(FakeMessage(valid_order()))
    consumer.poll_hook = lambda: (
        setattr(subject, "running", False) if consumer.poll_count >= 2 else None
    )

    subject.run()

    assert consumer.commits == []
    assert consumer.resumes == []
    assert consumer.closed is True


def test_boundary_and_retry_pause_registries_do_not_resume_each_other(settings):
    consumer = FakeConsumer(
        assignments=[
            PartitionRef(TOPIC_ORDERS, 0),
            PartitionRef(TOPIC_ORDERS, 1),
            PartitionRef(TOPIC_REFUNDS, 0),
        ]
    )
    coordinator = SequenceCoordinator(
        [TransientFailure("redis down"), SimpleNamespace(disposition="APPLY")]
    )
    subject = build_subject(settings, coordinator=coordinator, consumer=consumer)

    subject.process_message(FakeMessage(valid_order(period=42), partition=0))
    subject.process_message(
        FakeMessage(valid_order(order_id="O-RETRY"), partition=1)
    )

    assert subject.boundary_pauses == {(TOPIC_ORDERS, 0)}
    assert subject.retry_pauses == set()
    assert consumer.resumes == [PartitionRef(TOPIC_ORDERS, 1)]


def test_boundary_pause_quarantines_prefetched_same_partition_messages(settings):
    consumer = FakeConsumer(assignments=[PartitionRef(TOPIC_ORDERS, 0)])
    producer = FakeProducer()
    coordinator = SequenceCoordinator()
    subject = build_subject(
        settings,
        consumer=consumer,
        producer=producer,
        coordinator=coordinator,
    )
    stale = FakeMessage(
        valid_order(order_id="O-LATER", previous_amount="1.00"),
        partition=0,
        offset=11,
    )
    subject._buffered_messages.append(stale)

    subject.process_message(
        FakeMessage(valid_order(order_id="O-BOUNDARY", period=42), partition=0)
    )
    assert list(subject._buffered_messages) == []
    subject.process_message(stale)

    assert consumer.commits == []
    assert producer.records == []
    assert coordinator.calls == []


def test_permanent_pre_delivery_conflict_forwards_with_no_redis_residue(settings):
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=SequenceCoordinator([EventIdentityConflict("drift")]),
        consumer=consumer,
        producer=producer,
    )
    message = FakeMessage(valid_order())

    subject.process_message(message)

    assert producer.records[-1]["payload"]["has_redis_residue"] is False
    assert consumer.commits == [(message, False)]


def test_permanent_post_delivery_conflict_forwards_with_redis_residue(settings):
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=SequenceCoordinator([ConsumedOrderConflict("conflict")]),
        consumer=consumer,
        producer=producer,
    )

    subject.process_message(FakeMessage(valid_order()))

    assert producer.records[-1]["payload"]["has_redis_residue"] is True
    assert len(consumer.commits) == 1


def _raise_from_elite_bonus_stage():
    def update_elite_bonus_incremental():
        raise ValueError("period mismatch")

    update_elite_bonus_incremental()


def test_stage_value_error_is_classified_post_delivery(settings):
    class StageCoordinator(SequenceCoordinator):
        def dispatch_order(self, payload):
            _raise_from_elite_bonus_stage()

    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=StageCoordinator(),
        producer=producer,
    )

    subject.process_message(FakeMessage(valid_order()))

    failure = producer.records[-1]["payload"]
    assert failure["failed_stage"] == "ELITE_BONUS"
    assert failure["has_redis_residue"] is True


def test_period_resolution_error_marks_possible_wiring_failure(settings):
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=SequenceCoordinator(
            [PeriodResolutionError("period repository mismatch")]
        ),
        producer=producer,
    )

    subject.process_message(FakeMessage(valid_order()))

    failure = producer.records[-1]["payload"]
    assert failure["reason"] == "PERIOD_RESOLUTION_ERROR"
    assert failure["possible_wiring_error"] is True


@pytest.mark.parametrize(
    ("exception_type", "expected_reason"),
    [
        (ValueError, "PERSISTENT_FAILURE"),
        (TypeError, "PERSISTENT_FAILURE"),
        (OverflowError, "PERSISTENT_FAILURE"),
        (PeriodResolutionError, "PERIOD_RESOLUTION_ERROR"),
    ],
)
def test_post_prepare_delivery_validation_failures_are_category_three(
    settings,
    exception_type,
    expected_reason,
):
    class PostPrepareFailureNormalizer(PvEventNormalizer):
        attempts = 0

        def _build_event(self, **_kwargs):
            self.attempts += 1
            raise exception_type("failure after prepare_delivery")

    normalizer = PostPrepareFailureNormalizer(
        PeriodResolver(
            MappingPeriodRepository(
                [{"PERIOD_NUM": 41, "CALC_YEAR": 2099, "CALC_MONTH": 6}]
            )
        ),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
        delivery_ledger=InMemoryPvEventDeliveryLedger(),
    )
    coordinator = PvEventDispatchCoordinator(
        normalizer,
        user_stats_service=SimpleNamespace(),
        placement_service=SimpleNamespace(),
        elite_bonus_service=SimpleNamespace(),
    )
    producer = FakeProducer()
    subject = build_subject(settings, coordinator=coordinator, producer=producer)

    subject.process_message(FakeMessage(valid_order()))

    failure = producer.records[-1]["payload"]
    assert normalizer.attempts == 1
    assert failure["reason"] == expected_reason
    assert failure["has_redis_residue"] is True


@pytest.mark.parametrize("failed_stage", ["placement", "ack"])
def test_stage_runtime_error_retries_full_budget_with_residue(
    settings,
    failed_stage,
):
    class RuntimeErrorNormalizer(PvEventNormalizer):
        ack_attempts = 0

        def acknowledge_dispatched(self, *args, **kwargs):
            self.ack_attempts += 1
            if failed_stage == "ack":
                raise RuntimeError("ambiguous ACK failure")
            return super().acknowledge_dispatched(*args, **kwargs)

    class UserStage:
        def update_elite_performance(self, **_kwargs):
            return None

    class PlacementStage:
        attempts = 0

        def update_placement_performance(self, **_kwargs):
            self.attempts += 1
            if failed_stage == "placement":
                raise RuntimeError("ambiguous placement failure")

    class EliteStage:
        def update_elite_bonus_incremental(self, **_kwargs):
            return None

    normalizer = RuntimeErrorNormalizer(
        PeriodResolver(
            MappingPeriodRepository(
                [{"PERIOD_NUM": 41, "CALC_YEAR": 2099, "CALC_MONTH": 6}]
            )
        ),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
        delivery_ledger=InMemoryPvEventDeliveryLedger(),
    )
    placement = PlacementStage()
    coordinator = PvEventDispatchCoordinator(
        normalizer,
        user_stats_service=UserStage(),
        placement_service=placement,
        elite_bonus_service=EliteStage(),
    )
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=coordinator,
        consumer=consumer,
        producer=producer,
    )

    subject.process_message(FakeMessage(valid_order()))

    failure = producer.records[-1]["payload"]
    attempts = placement.attempts if failed_stage == "placement" else normalizer.ack_attempts
    assert attempts == settings.bounded_retry_attempts
    assert failure["reason"] == "RETRY_EXHAUSTED"
    assert failure["has_redis_residue"] is True
    assert consumer.pauses == [PartitionRef(TOPIC_ORDERS, 0)]
    assert consumer.resumes == [PartitionRef(TOPIC_ORDERS, 0)]


def test_runtime_error_retries_to_budget_then_forwards_and_resumes(settings):
    coordinator = SequenceCoordinator([RuntimeError("closed period")])
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=coordinator,
        consumer=consumer,
        producer=producer,
    )
    message = FakeMessage(valid_order())

    subject.process_message(message)

    assert len(coordinator.calls) == settings.bounded_retry_attempts
    assert producer.records[-1]["payload"]["reason"] == "RETRY_EXHAUSTED"
    assert consumer.commits == [(message, False)]
    assert consumer.pauses == [PartitionRef(TOPIC_ORDERS, 0)]
    assert consumer.poll_count >= 1
    assert consumer.resumes == [PartitionRef(TOPIC_ORDERS, 0)]


def test_latest_transient_failure_cannot_exhaust_an_older_bounded_budget(settings):
    retry_settings = replace(settings, bounded_retry_attempts=2)
    coordinator = SequenceCoordinator(
        [RuntimeError("ambiguous"), TransientFailure("redis down")]
    )
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(
        retry_settings,
        coordinator=coordinator,
        consumer=consumer,
        producer=producer,
    )
    consumer.poll_hook = lambda: (
        setattr(subject, "running", False) if consumer.poll_count >= 2 else None
    )

    subject.process_message(FakeMessage(valid_order()))

    assert consumer.commits == []
    assert consumer.resumes == []
    assert producer.records == []


def test_bounded_budget_restarts_after_transient_failures(settings):
    retry_settings = replace(settings, bounded_retry_attempts=2)
    transient_failures = 3
    coordinator = SequenceCoordinator(
        [TransientFailure("redis down")] * transient_failures
        + [RuntimeError("ambiguous")]
    )
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(
        retry_settings,
        coordinator=coordinator,
        consumer=consumer,
        producer=producer,
    )
    message = FakeMessage(valid_order())

    subject.process_message(message)

    assert len(coordinator.calls) == (
        transient_failures + retry_settings.bounded_retry_attempts
    )
    assert producer.records[-1]["payload"]["reason"] == "RETRY_EXHAUSTED"
    assert consumer.commits == [(message, False)]
    assert consumer.resumes == [PartitionRef(TOPIC_ORDERS, 0)]


def test_mixed_transient_bounded_transient_sequence_never_commits(settings):
    retry_settings = replace(settings, bounded_retry_attempts=3)
    coordinator = SequenceCoordinator(
        [
            TransientFailure("redis down"),
            RuntimeError("ambiguous"),
            TransientFailure("redis still down"),
        ]
    )
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(
        retry_settings,
        coordinator=coordinator,
        consumer=consumer,
        producer=producer,
    )
    consumer.poll_hook = lambda: (
        setattr(subject, "running", False) if consumer.poll_count >= 3 else None
    )

    subject.process_message(FakeMessage(valid_order()))

    assert consumer.commits == []
    assert consumer.resumes == []
    assert producer.records == []


def test_exception_message_contains_full_schema_and_fallback_key(settings):
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=SequenceCoordinator([ValueError("invalid")]),
        producer=producer,
    )

    subject.process_message(
        FakeMessage(
            {"user_id": "U-X", "period": True, "bv": "1.00"},
            partition=2,
            offset=99,
        )
    )

    record = producer.records[-1]
    expected_fields = {
        "event_identity",
        "event_kind",
        "period",
        "user_id",
        "failed_stage",
        "completed_stages",
        "pending_stages",
        "exception_class",
        "exception_message",
        "reason",
        "has_redis_residue",
        "unclassified",
        "source_topic",
        "source_partition",
        "source_offset",
        "payload_hash",
        "original_payload",
        "occurred_at",
        "consumer_instance",
    }
    assert expected_fields <= set(record["payload"])
    assert record["key"] == f"{TOPIC_ORDERS}:2:99"


def test_non_canonical_number_is_forwarded_as_strict_json(settings):
    normalizer = PvEventNormalizer(
        PeriodResolver(
            MappingPeriodRepository(
                [{"PERIOD_NUM": 41, "CALC_YEAR": 2099, "CALC_MONTH": 6}]
            )
        ),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
        delivery_ledger=InMemoryPvEventDeliveryLedger(),
    )
    coordinator = PvEventDispatchCoordinator(
        normalizer,
        user_stats_service=SimpleNamespace(
            update_elite_performance=lambda **_kwargs: None
        ),
        placement_service=SimpleNamespace(
            update_placement_performance=lambda **_kwargs: None
        ),
        elite_bonus_service=SimpleNamespace(
            update_elite_bonus_incremental=lambda **_kwargs: None
        ),
    )
    consumer = FakeConsumer()
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=coordinator,
        consumer=consumer,
        producer=producer,
    )
    message = FakeMessage(
        raw=(
            b'{"order_id":"O-NAN","user_id":"U-1","period":41,'
            b'"bv":"100.25","note":NaN}'
        )
    )

    subject.process_message(message)

    record = producer.records[-1]
    assert b"NaN" not in record["raw_value"]
    assert record["payload"]["non_canonical_payload"] is True
    assert isinstance(record["payload"]["original_payload"], str)
    assert consumer.commits == [(message, False)]


def test_permanent_failure_emits_sanitized_error_log(settings, caplog):
    connection_uri = "redis://operator:test-password@redis.invalid:6379/0"
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=SequenceCoordinator([ConsumedOrderConflict(connection_uri)]),
        producer=producer,
    )
    caplog.set_level(logging.ERROR, logger="MessageConsumer.PvEventConsumer")

    subject.process_message(FakeMessage(valid_order()))

    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert error_records
    error_text = caplog.text
    assert "event_identity=O-1" in error_text
    assert "failed_stage=NORMALIZE" in error_text
    assert "reason=PERSISTENT_FAILURE" in error_text
    assert "exception_class=ConsumedOrderConflict" in error_text
    assert "test-password" not in error_text
    assert connection_uri not in error_text
    assert "redis://" not in error_text
    assert producer.records[-1]["payload"]["exception_message"] == "[REDACTED_CONNECTION]"


def test_unclassified_permanent_failure_error_log_contains_traceback(settings, caplog):
    class UnclassifiedCoordinator(SequenceCoordinator):
        def update_placement_performance(self):
            raise LookupError("unknown stage failure")

        def dispatch_order(self, payload):
            self.update_placement_performance()

    retry_settings = replace(settings, bounded_retry_attempts=1)
    subject = build_subject(
        retry_settings,
        coordinator=UnclassifiedCoordinator(),
    )
    caplog.set_level(logging.ERROR, logger="MessageConsumer.PvEventConsumer")

    subject.process_message(FakeMessage(valid_order()))

    assert any(record.levelno >= logging.ERROR for record in caplog.records)
    assert "failed_stage=PLACEMENT_PERFORMANCE" in caplog.text
    assert "reason=RETRY_EXHAUSTED" in caplog.text
    assert "exception_class=LookupError" in caplog.text
    assert "Traceback (most recent call last)" in caplog.text
    assert "LookupError: unknown stage failure" in caplog.text


def test_exception_delivery_failure_does_not_commit_when_shutdown(settings):
    consumer = FakeConsumer()
    producer = FakeProducer(errors=[RuntimeError("broker down")])
    subject = build_subject(settings, consumer=consumer, producer=producer)
    consumer.poll_hook = lambda: setattr(subject, "running", False)
    message = FakeMessage(valid_order(previous_amount="1.00"))

    subject.process_message(message)

    assert consumer.commits == []


def test_exception_delivery_retry_resumes_partition_after_confirmed_commit(settings):
    consumer = FakeConsumer()
    producer = FakeProducer(errors=[RuntimeError("broker down"), None])
    subject = build_subject(settings, consumer=consumer, producer=producer)
    message = FakeMessage(valid_order(previous_amount="1.00"))

    subject.process_message(message)

    assert consumer.commits == [(message, False)]
    assert consumer.pauses == [PartitionRef(TOPIC_ORDERS, 0)]
    assert consumer.resumes == [PartitionRef(TOPIC_ORDERS, 0)]


def test_dispatch_success_retries_commit_before_publishing_failure(settings):
    class PostDispatchCommitFailureConsumer(FakeConsumer):
        def __init__(self):
            super().__init__()
            self.commit_attempts = 0

        def commit(self, *, message, asynchronous):
            self.commit_attempts += 1
            if self.commit_attempts == 1:
                raise FakeKafkaException(FakeRetriableKafkaError())
            super().commit(message=message, asynchronous=asynchronous)

    consumer = PostDispatchCommitFailureConsumer()
    producer = FakeProducer()
    coordinator = SequenceCoordinator()
    subject = build_subject(
        settings,
        coordinator=coordinator,
        consumer=consumer,
        producer=producer,
        kafka_exception_types=(FakeKafkaException,),
    )
    message = FakeMessage(valid_order())

    subject.process_message(message)

    assert len(coordinator.calls) == 1
    assert producer.records == []
    assert consumer.commit_attempts == 2
    assert consumer.commits == [(message, False)]
    assert subject.running is True


def test_dispatch_success_non_retryable_commit_failure_reports_completed_business(
    settings,
):
    class NonRetryableCommitConsumer(FakeConsumer):
        def commit(self, *, message, asynchronous):
            raise FakeKafkaException(FakeNonRetriableKafkaError())

    consumer = NonRetryableCommitConsumer()
    producer = FakeProducer()
    coordinator = SequenceCoordinator()
    subject = build_subject(
        settings,
        coordinator=coordinator,
        consumer=consumer,
        producer=producer,
        kafka_exception_types=(FakeKafkaException,),
    )

    subject.process_message(FakeMessage(valid_order()))

    assert len(coordinator.calls) == 1
    assert len(producer.records) == 1
    record = producer.records[0]["payload"]
    assert record["failed_stage"] == "ACK"
    assert record["completed_stages"] == list(_STAGE_ORDER)
    assert record["pending_stages"] == []
    assert record["has_redis_residue"] is False
    assert record["reason"] == "OFFSET_COMMIT_FAILURE"
    assert consumer.commits == []
    assert subject.running is False


def test_retry_dispatch_commit_failure_does_not_repeat_completed_dispatch(settings):
    class RetryCommitFailureConsumer(FakeConsumer):
        def __init__(self):
            super().__init__()
            self.commit_attempts = 0

        def commit(self, *, message, asynchronous):
            self.commit_attempts += 1
            if self.commit_attempts == 1:
                raise FakeKafkaException(FakeRetriableKafkaError())
            super().commit(message=message, asynchronous=asynchronous)

    consumer = RetryCommitFailureConsumer()
    producer = FakeProducer()
    coordinator = SequenceCoordinator(
        [TransientFailure("redis unavailable"), SimpleNamespace(disposition="APPLY")]
    )
    subject = build_subject(
        settings,
        coordinator=coordinator,
        consumer=consumer,
        producer=producer,
        kafka_exception_types=(FakeKafkaException,),
    )
    message = FakeMessage(valid_order())

    subject.process_message(message)

    assert len(coordinator.calls) == 2
    assert consumer.commits == [(message, False)]
    assert producer.records == []


def test_retryable_exception_offset_commit_is_retried_without_losing_message(settings):
    class CommitRetryConsumer(FakeConsumer):
        def __init__(self):
            super().__init__()
            self.commit_attempts = 0

        def commit(self, *, message, asynchronous):
            self.commit_attempts += 1
            if self.commit_attempts == 1:
                raise FakeKafkaException(FakeRetriableKafkaError())
            super().commit(message=message, asynchronous=asynchronous)

    consumer = CommitRetryConsumer()
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=SequenceCoordinator([EventIdentityConflict("drift")]),
        consumer=consumer,
        producer=producer,
        kafka_exception_types=(FakeKafkaException,),
    )
    message = FakeMessage(valid_order())

    subject.process_message(message)

    assert consumer.commit_attempts == 2
    assert consumer.commits == [(message, False)]
    assert consumer.poll_count >= 1


def test_non_retryable_exception_offset_commit_stops_and_closes(settings):
    class NonRetryableCommitConsumer(FakeConsumer):
        def __init__(self):
            super().__init__()
            self.commit_attempts = 0

        def commit(self, *, message, asynchronous):
            self.commit_attempts += 1
            raise FakeKafkaException(FakeNonRetriableKafkaError())

    consumer = NonRetryableCommitConsumer()
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=SequenceCoordinator([EventIdentityConflict("drift")]),
        consumer=consumer,
        producer=producer,
        kafka_exception_types=(FakeKafkaException,),
    )
    consumer.poll_results.append(FakeMessage(valid_order()))

    subject.run()

    assert subject.running is False
    assert consumer.closed is True
    assert consumer.commit_attempts == 1
    assert consumer.commits == []
    assert len(producer.records) == 1


@pytest.mark.parametrize(
    ("method_name", "expected_stage", "expected_completed"),
    [
        ("update_elite_performance", "ELITE_PERFORMANCE", []),
        (
            "update_placement_performance",
            "PLACEMENT_PERFORMANCE",
            ["ELITE_PERFORMANCE"],
        ),
        (
            "update_elite_bonus_incremental",
            "ELITE_BONUS",
            ["ELITE_PERFORMANCE", "PLACEMENT_PERFORMANCE"],
        ),
        (
            "acknowledge_dispatched",
            "ACK",
            ["ELITE_PERFORMANCE", "PLACEMENT_PERFORMANCE", "ELITE_BONUS"],
        ),
    ],
)
def test_traceback_stage_attribution_matrix(
    settings,
    method_name,
    expected_stage,
    expected_completed,
):
    namespace = {}
    exec(
        f"def {method_name}():\n    raise ValueError('stage failure')",
        namespace,
    )

    class StageCoordinator(SequenceCoordinator):
        def dispatch_order(self, payload):
            namespace[method_name]()

    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=StageCoordinator(),
        producer=producer,
    )

    subject.process_message(FakeMessage(valid_order()))

    failure = producer.records[-1]["payload"]
    assert failure["failed_stage"] == expected_stage
    assert failure["completed_stages"] == expected_completed
    assert failure["has_redis_residue"] is True


@pytest.mark.parametrize(
    ("failing_stage", "expected_stage", "expected_completed"),
    [
        ("user", "ELITE_PERFORMANCE", []),
        ("placement", "PLACEMENT_PERFORMANCE", ["ELITE_PERFORMANCE"]),
        (
            "elite",
            "ELITE_BONUS",
            ["ELITE_PERFORMANCE", "PLACEMENT_PERFORMANCE"],
        ),
    ],
)
def test_real_coordinator_stage_attribution_matches_done_markers(
    settings,
    failing_stage,
    expected_stage,
    expected_completed,
):
    class MarkerRedis:
        def __init__(self):
            self.values = {}

        def set(self, key, value):
            self.values[key] = value

        def exists(self, key):
            return key in self.values

    marker_redis = MarkerRedis()

    class UserStage:
        def update_elite_performance(self, *, user_id, normalized_event):
            if failing_stage == "user":
                raise ValueError("injected user stage failure")
            marker_redis.set(
                f"system:idempotency:41:{normalized_event.identity}:done",
                "1",
            )

    class PlacementStage:
        def update_placement_performance(self, *, user_id, normalized_event):
            if failing_stage == "placement":
                raise ValueError("injected placement stage failure")
            marker_redis.set(
                f"system:idempotency:placement:41:{normalized_event.identity}:done",
                "1",
            )

    class EliteStage:
        def update_elite_bonus_incremental(self, *, user_id, normalized_event):
            if failing_stage == "elite":
                raise ValueError("injected elite stage failure")
            marker_redis.set(
                f"system:idempotency:elite:41:{normalized_event.identity}:done",
                "1",
            )

    normalizer = PvEventNormalizer(
        PeriodResolver(
            MappingPeriodRepository(
                [{"PERIOD_NUM": 41, "CALC_YEAR": 2099, "CALC_MONTH": 6}]
            )
        ),
        InMemoryEventRegistry(),
        InMemoryRefundReversalLedger(),
        order_repository=InMemoryConsumedOrderLedger(),
        delivery_ledger=InMemoryPvEventDeliveryLedger(),
    )
    coordinator = PvEventDispatchCoordinator(
        normalizer,
        user_stats_service=UserStage(),
        placement_service=PlacementStage(),
        elite_bonus_service=EliteStage(),
    )
    producer = FakeProducer()
    subject = build_subject(settings, coordinator=coordinator, producer=producer)

    subject.process_message(FakeMessage(valid_order()))

    failure = producer.records[-1]["payload"]
    expected_marker_keys = {
        "ELITE_PERFORMANCE": "system:idempotency:41:O-1:done",
        "PLACEMENT_PERFORMANCE": "system:idempotency:placement:41:O-1:done",
        "ELITE_BONUS": "system:idempotency:elite:41:O-1:done",
    }
    assert failure["failed_stage"] == expected_stage
    assert failure["completed_stages"] == expected_completed
    assert failure["pending_stages"] == list(_STAGE_ORDER[len(expected_completed):])
    assert {
        stage
        for stage, key in expected_marker_keys.items()
        if marker_redis.exists(key)
    } == set(expected_completed)


def test_unraised_unknown_failure_keeps_residue_unknown(settings):
    subject = build_subject(settings)
    error = Exception("no traceback")

    decision = subject._classify_exception(error)
    record = subject._build_exception_record(
        FakeMessage(valid_order()),
        valid_order(),
        error,
        decision,
    )

    assert decision.unclassified is True
    assert decision.has_redis_residue is None
    assert record["has_redis_residue"] is None


def test_circuit_breaker_stops_after_threshold_and_success_resets(settings):
    producer = FakeProducer()
    consumer = FakeConsumer()
    subject = build_subject(
        settings,
        coordinator=SequenceCoordinator(
            [EventIdentityConflict("bad"), SimpleNamespace(disposition="APPLY"), EventIdentityConflict("bad"), EventIdentityConflict("bad")]
        ),
        consumer=consumer,
        producer=producer,
    )

    subject.process_message(FakeMessage(valid_order(order_id="O-1")))
    subject.process_message(FakeMessage(valid_order(order_id="O-2")))
    subject.process_message(FakeMessage(valid_order(order_id="O-3")))
    assert subject.running is True
    subject.process_message(FakeMessage(valid_order(order_id="O-4")))

    assert subject.running is False
    assert any(
        record["payload"]["reason"] == "CIRCUIT_BREAKER"
        for record in producer.records
    )


def test_expired_period_uses_an_independent_circuit_counter(settings):
    producer = FakeProducer()
    subject = build_subject(
        settings,
        coordinator=SequenceCoordinator([EventIdentityConflict("bad")]),
        producer=producer,
    )

    subject.process_message(FakeMessage(valid_order(order_id="O-BAD")))
    subject.process_message(FakeMessage(valid_order(order_id="O-OLD-1", period=40)))
    assert subject.running is True
    subject.process_message(FakeMessage(valid_order(order_id="O-OLD-2", period=40)))

    assert subject.running is False
    breaker = producer.records[-1]["payload"]
    assert breaker["reason"] == "CIRCUIT_BREAKER"
    assert breaker["triggered_counter"] == "expired"


def test_message_errors_do_not_enter_business_or_commit(settings):
    coordinator = SequenceCoordinator()
    consumer = FakeConsumer()
    subject = build_subject(
        settings,
        coordinator=coordinator,
        consumer=consumer,
    )
    subject.process_message(FakeMessage(raw=None, error=FakeKafkaError(fatal=False)))
    assert subject.running is True
    assert consumer.commits == []
    assert consumer.pauses == []
    subject.process_message(FakeMessage(raw=None, error=FakeKafkaError(fatal=True)))

    assert subject.running is False
    assert coordinator.calls == []
    assert consumer.commits == []
    assert consumer.pauses == []


def test_topic_guard_stops_before_payload_processing(settings):
    consumer = FakeConsumer()
    subject = build_subject(settings, consumer=consumer)

    subject.process_message(FakeMessage(valid_order(), topic="unexpected"))

    assert subject.running is False
    assert consumer.commits == []


def test_revoke_clears_pause_registries_without_resuming_boundary(settings):
    consumer = FakeConsumer(assignments=[PartitionRef(TOPIC_ORDERS, 0)])
    subject = build_subject(settings, consumer=consumer)
    subject.process_message(FakeMessage(valid_order(period=42)))
    assert subject.boundary_pauses == {(TOPIC_ORDERS, 0)}

    subject.on_revoke(consumer, [PartitionRef(TOPIC_ORDERS, 0)])

    assert subject.boundary_pauses == set()
    assert subject.retry_pauses == set()
    assert consumer.resumes == []


def test_required_environment_is_fail_fast_without_values_in_error():
    env = {
        "PVAM_KAFKA_BOOTSTRAP": "kafka.invalid:9092",
        "PVAM_DASK_SCHEDULER": "tcp://dask.invalid:8786",
        "PVAM_REDIS_HOST": "redis.invalid",
        "PVAM_REDIS_PORT": "6379",
        "PVAM_REDIS_DB": "0",
        "PVAM_REDIS_PASSWORD": "do-not-print",
        "PVAM_BOUND_PERIOD": "41",
        "PVAM_CALC_MONTH": "209906",
        "PVAM_ELITE_RATE_PERCENT": "15",
    }
    del env["PVAM_REDIS_PASSWORD"]

    with pytest.raises(ConsumerConfigurationError) as exc_info:
        load_settings(env)

    assert "PVAM_REDIS_PASSWORD" in str(exc_info.value)
    assert "do-not-print" not in str(exc_info.value)


def test_contract_tuning_defaults_remain_explicit():
    assert BOUNDED_RETRY_ATTEMPTS == 10
    assert CIRCUIT_BREAKER_THRESHOLD == 50
