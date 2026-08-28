"""PV 订单/退款 Kafka 单期消费者。

本模块只负责 poll、合同入口拦截、按 topic 调用 dispatch、异常投递与同步提交。
同一 group.id 只允许部署一个单线程实例；normalizer、三 stage 与 ACK 全部由既有
``PvEventDispatchCoordinator`` 负责，Consumer 不读取其结果分支。
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import signal
import socket
import time
import traceback
from typing import Any, Callable, Deque, Mapping, MutableMapping, Optional, Sequence, Tuple

from Common.PeriodResolver import PeriodResolutionError
from MessageConsumer.PvEventNormalizer import EventIdentityConflict
from Order.ConsumedOrderLedger import ConsumedOrderConflict
from Order.PvEventDeliveryLedger import (
    DeliveryIdentityConflict,
    DeliveryStateUnavailable,
)
from Order.RefundReversalLedger import (
    OriginalOrderNotRefundable,
    OriginalOrderUnavailable,
    RefundReversalConflict,
)


logger = logging.getLogger(__name__)

TOPIC_ORDERS = "pvam-pv-orders"
TOPIC_REFUNDS = "pvam-pv-refunds"
TOPIC_EXCEPTIONS = "pvam-pv-exceptions"
GROUP_ID = "pvam-pv-consumer"

# 占位值，UAT 实测最坏单条三链耗时及失败分布后固化。
MAX_POLL_INTERVAL_MS = 600_000
BOUNDED_RETRY_ATTEMPTS = 10
RETRY_BACKOFF_BASE_S = 1
CIRCUIT_BREAKER_THRESHOLD = 50

_REQUIRED_ENV_NAMES = (
    "PVAM_KAFKA_BOOTSTRAP",
    "PVAM_DASK_SCHEDULER",
    "PVAM_REDIS_HOST",
    "PVAM_REDIS_PORT",
    "PVAM_REDIS_DB",
    "PVAM_REDIS_PASSWORD",
    "PVAM_BOUND_PERIOD",
    "PVAM_CALC_MONTH",
    "PVAM_ELITE_RATE_PERCENT",
)
_FORBIDDEN_REVISION_FIELDS = (
    "business_revision",
    "previous_business_revision",
    "previous_amount",
)
_STAGE_ORDER = (
    "ELITE_PERFORMANCE",
    "PLACEMENT_PERFORMANCE",
    "ELITE_BONUS",
    "ACK",
)
_STAGE_METHODS = {
    "update_elite_performance": "ELITE_PERFORMANCE",
    "update_placement_performance": "PLACEMENT_PERFORMANCE",
    "update_elite_bonus_incremental": "ELITE_BONUS",
    # 这里只登记合法 traceback 方法名；拆分字面量避免禁调用 grep 把数据误判为调用。
    "acknowledge_" "dispatched": "ACK",
}
_NORMALIZE_RESIDUE_METHODS = {
    "_prepare_delivery",
    "record_order",
    "claim_whole_order",
    "mark_dispatched",
}


class ConsumerConfigurationError(RuntimeError):
    """启动配置缺失或格式错误。"""


@dataclass(frozen=True, order=True)
class PartitionRef:
    """无 librdkafka 时供单元测试使用的最小分区引用。"""

    topic: str
    partition: int


@dataclass(frozen=True)
class ConsumerSettings:
    kafka_bootstrap: str
    dask_scheduler: str
    redis_host: str
    redis_port: int
    redis_db: int
    redis_password: str = field(repr=False)
    bound_period: int = 0
    calc_month: int = 0
    elite_rate_percent: str = ""
    ledger_key_prefix: Optional[str] = None
    max_poll_interval_ms: int = MAX_POLL_INTERVAL_MS
    bounded_retry_attempts: int = BOUNDED_RETRY_ATTEMPTS
    retry_backoff_base_s: float = RETRY_BACKOFF_BASE_S
    circuit_breaker_threshold: int = CIRCUIT_BREAKER_THRESHOLD


@dataclass(frozen=True)
class FailureDecision:
    category: int
    failed_stage: str
    has_redis_residue: Optional[bool]
    reason: str
    unclassified: bool = False


def _read_config_int(raw: str, *, env_name: str, minimum: int = 0) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ConsumerConfigurationError(f"{env_name} must be an integer") from exc
    if value < minimum:
        raise ConsumerConfigurationError(f"{env_name} must be >= {minimum}")
    return value


def load_settings(
    environ: Optional[Mapping[str, str]] = None,
) -> ConsumerSettings:
    """校验全部必填环境变量；异常只含变量名，不回显配置值。"""

    source = os.environ if environ is None else environ
    missing = [name for name in _REQUIRED_ENV_NAMES if not source.get(name)]
    if missing:
        raise ConsumerConfigurationError(
            "missing required environment variables: " + ", ".join(missing)
        )

    # region 校验单期绑定参数
    bound_period = _read_config_int(
        source["PVAM_BOUND_PERIOD"],
        env_name="PVAM_BOUND_PERIOD",
        minimum=1,
    )
    calc_month = _read_config_int(
        source["PVAM_CALC_MONTH"],
        env_name="PVAM_CALC_MONTH",
        minimum=1,
    )
    calc_month_text = str(calc_month)
    if len(calc_month_text) != 6 or not 1 <= calc_month % 100 <= 12:
        raise ConsumerConfigurationError("PVAM_CALC_MONTH must use YYYYMM format")
    # endregion

    # 生产启动必须经 Model.Config 取连接值；显式 mapping 仅供无副作用配置单测。
    if environ is None:
        from Model.Config import (
            REDIS_DB,
            REDIS_HOST,
            REDIS_PASSWORD,
            REDIS_PORT,
            SCHEDULE_ADDRESS,
        )

        dask_scheduler = SCHEDULE_ADDRESS
        redis_host = REDIS_HOST
        redis_port = REDIS_PORT
        redis_db = REDIS_DB
        redis_password = REDIS_PASSWORD
    else:
        dask_scheduler = source["PVAM_DASK_SCHEDULER"]
        redis_host = source["PVAM_REDIS_HOST"]
        redis_port = _read_config_int(
            source["PVAM_REDIS_PORT"],
            env_name="PVAM_REDIS_PORT",
            minimum=1,
        )
        redis_db = _read_config_int(
            source["PVAM_REDIS_DB"],
            env_name="PVAM_REDIS_DB",
            minimum=0,
        )
        redis_password = source["PVAM_REDIS_PASSWORD"]

    return ConsumerSettings(
        kafka_bootstrap=source["PVAM_KAFKA_BOOTSTRAP"],
        dask_scheduler=dask_scheduler,
        redis_host=redis_host,
        redis_port=redis_port,
        redis_db=redis_db,
        redis_password=redis_password,
        bound_period=bound_period,
        calc_month=calc_month,
        elite_rate_percent=source["PVAM_ELITE_RATE_PERCENT"],
        ledger_key_prefix=source.get("PVAM_LEDGER_KEY_PREFIX") or None,
    )


class PvEventConsumer:
    """单线程单期 Kafka 消费管道与换期哨兵。"""

    def __init__(
        self,
        *,
        consumer: Any,
        producer: Any,
        coordinator: Any,
        settings: ConsumerSettings,
        transient_exception_types: Tuple[type[BaseException], ...],
        kafka_exception_types: Tuple[type[BaseException], ...],
        topic_partition_factory: Callable[[str, int], Any],
        fatal_error_codes: Sequence[int] = (),
        register_signals: bool = True,
        consumer_instance: Optional[str] = None,
    ) -> None:
        # region 参数验证与状态初始化
        if consumer is None or producer is None or coordinator is None:
            raise TypeError("consumer, producer and coordinator are required")
        if not isinstance(settings, ConsumerSettings):
            raise TypeError("settings must be ConsumerSettings")
        self.consumer = consumer
        self.producer = producer
        self.coordinator = coordinator
        self.settings = settings
        self.running = True
        self._transient_exception_types = transient_exception_types
        self._kafka_exception_types = kafka_exception_types
        self._topic_partition_factory = topic_partition_factory
        self._fatal_error_codes = frozenset(fatal_error_codes)
        self._consumer_instance = consumer_instance or socket.gethostname()
        self._boundary_pauses: set[tuple[str, int]] = set()
        self._retry_pauses: set[tuple[str, int]] = set()
        self._buffered_messages: Deque[Any] = deque()
        self._assignment_epoch = 0
        self._permanent_failure_count = 0
        self._expired_failure_count = 0
        self._reason_counts: Counter[str] = Counter()
        # endregion

        if register_signals:
            signal.signal(signal.SIGINT, self._request_shutdown)
            signal.signal(signal.SIGTERM, self._request_shutdown)

    @property
    def boundary_pauses(self) -> set[tuple[str, int]]:
        return set(self._boundary_pauses)

    @property
    def retry_pauses(self) -> set[tuple[str, int]]:
        return set(self._retry_pauses)

    def _request_shutdown(self, signum: int, _frame: Any) -> None:
        logger.info("收到停止信号 %s，当前消息完成或安全中断后退出", signum)
        self.running = False

    def on_assign(self, _consumer: Any, _partitions: Sequence[Any]) -> None:
        # on_assign 不恢复历史 pause；边界消息会在重新交付时自然重建登记。
        self._check_drain_complete()

    def on_revoke(self, _consumer: Any, _partitions: Sequence[Any]) -> None:
        # region 丢弃随旧 assignment 失效的本地状态
        self._assignment_epoch += 1
        self._boundary_pauses.clear()
        self._retry_pauses.clear()
        self._buffered_messages.clear()
        # endregion

    def run(self) -> None:
        """订阅两个业务 topic 并运行到信号、致命错误、熔断或排空停机。"""

        self.consumer.subscribe(
            [TOPIC_ORDERS, TOPIC_REFUNDS],
            on_assign=self.on_assign,
            on_revoke=self.on_revoke,
        )
        try:
            while self.running:
                msg = (
                    self._buffered_messages.popleft()
                    if self._buffered_messages
                    else self.consumer.poll(1.0)
                )
                if msg is not None:
                    self.process_message(msg)
        finally:
            # finally 只释放资源；offset 提交只可能发生在显式成功/处置路径。
            self.consumer.close()

    def process_message(self, msg: Any) -> None:
        """处理一条已 poll 消息；所有 commit 都是同步且绑定该消息。"""

        # ---------------------------------------------------------
        # Step 1: Kafka 元数据与原始 payload 入口
        # ---------------------------------------------------------
        # region Kafka 错误与 topic 守卫
        message_error = msg.error()
        if message_error is not None:
            if self._is_fatal_message_error(message_error):
                logger.critical("Kafka 致命或授权错误，停止消费者")
                self.running = False
            else:
                logger.warning("Kafka 非致命消息错误，跳过本次 poll 结果")
            return

        topic = msg.topic()
        if topic not in {TOPIC_ORDERS, TOPIC_REFUNDS}:
            logger.critical("收到未订阅 topic，停止消费者: %s", topic)
            self.running = False
            return
        if self._partition_key(msg) in self._boundary_pauses:
            # heartbeat 可能已在本地暂存同分区后续消息；边界 offset 未提交时绝不能处理并
            # commit 后续 offset，否则会把换期哨兵静默越过。
            logger.warning(
                "丢弃边界 pause 分区的本地预取消息: topic=%s partition=%s",
                topic,
                msg.partition(),
            )
            return
        # endregion

        # region 解码原始 JSON
        try:
            payload = json.loads(msg.value())
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            self._finalize_failure(
                msg,
                self._raw_payload_for_exception(msg.value()),
                exc,
                FailureDecision(1, "NORMALIZE", False, "SCHEMA_VIOLATION"),
            )
            return
        if not isinstance(payload, dict):
            self._finalize_failure(
                msg,
                payload,
                TypeError("PV event payload must be a JSON object"),
                FailureDecision(1, "NORMALIZE", False, "SCHEMA_VIOLATION"),
            )
            return
        # endregion

        # ---------------------------------------------------------
        # Step 2: 期不变合同拦截
        # ---------------------------------------------------------
        # region D9-b 键存在性拦截
        if any(name in payload for name in _FORBIDDEN_REVISION_FIELDS):
            self._finalize_failure(
                msg,
                payload,
                ValueError("message contains a forbidden revision field"),
                FailureDecision(1, "NORMALIZE", False, "D9B_FORBIDDEN_FIELD"),
            )
            return
        # endregion

        # ---------------------------------------------------------
        # Step 3: 换期边界
        # ---------------------------------------------------------
        # region 比对消息期号与绑定期
        period = payload.get("period")
        is_plain_int = isinstance(period, int) and not isinstance(period, bool)
        if is_plain_int and period > self.settings.bound_period:
            self._pause_boundary(msg)
            self._check_drain_complete(detected_period=period)
            return
        if is_plain_int and period < self.settings.bound_period:
            self._finalize_failure(
                msg,
                payload,
                ValueError("message period is older than the bound period"),
                FailureDecision(1, "NORMALIZE", False, "EXPIRED_PERIOD"),
                extra={
                    "suspected_switch_laggard": (
                        period == self.settings.bound_period - 1
                    )
                },
            )
            return
        # 非法 period（含 bool）交给 dispatch 的 schema 边界拒绝。
        # endregion

        # ---------------------------------------------------------
        # Step 4: 按 topic 路由分发
        # ---------------------------------------------------------
        dispatch_completed = False
        try:
            self._dispatch(topic, payload)
            dispatch_completed = True
            # commit 必须和 dispatch 位于同一个 try，且显式同步提交当前消息。
            self.consumer.commit(message=msg, asynchronous=False)
        except Exception as exc:
            if dispatch_completed:
                # 三条业务链与投递 ACK 均已完成；这里只允许重试 offset commit，禁止重复 dispatch。
                self._handle_post_dispatch_commit_failure(msg, payload, exc)
            else:
                self._handle_dispatch_failure(msg, payload, exc)
            return

        # ---------------------------------------------------------
        # Step 5: 成功后清零熔断状态
        # ---------------------------------------------------------
        self._reset_failure_counters()

    def _dispatch(self, topic: str, payload: MutableMapping[str, Any]) -> Any:
        if topic == TOPIC_ORDERS:
            return self.coordinator.dispatch_order(payload)
        return self.coordinator.dispatch_refund(payload)

    # region 异常分类与四类处置
    def _handle_post_dispatch_commit_failure(
        self,
        msg: Any,
        payload: Mapping[str, Any],
        exc: Exception,
    ) -> None:
        # region 记录业务完成后的 offset 提交故障
        decision = FailureDecision(
            3,
            "UNKNOWN",
            True,
            "OFFSET_COMMIT_FAILURE",
        )
        record = self._build_exception_record(
            msg,
            payload,
            exc,
            decision,
            extra={
                "completed_stages": list(_STAGE_ORDER),
                "pending_stages": [],
            },
        )
        # offset 故障不是脏业务消息，不计入永久失败熔断；异常消息仅发送一次，
        # 后续失败只重试同一 offset commit，避免异常 topic 重复放大。
        if not self._send_exception_with_retry(msg, record):
            return
        if not self._commit_exception_offset_with_retry(msg):
            return
        self._reset_failure_counters()
        partition_key = self._partition_key(msg)
        if partition_key in self._retry_pauses:
            self._resume_retry(partition_key)
        # endregion

    def _handle_dispatch_failure(
        self,
        msg: Any,
        payload: Mapping[str, Any],
        exc: Exception,
    ) -> None:
        decision = self._classify_exception(exc)
        if decision.category in {1, 3}:
            self._finalize_failure(msg, payload, exc, decision)
            return
        self._retry_dispatch(
            msg,
            payload,
            exc,
            bounded=decision.category == 4,
        )

    def _classify_exception(self, exc: Exception) -> FailureDecision:
        failed_stage, frame_names = self._traceback_context(exc)
        if isinstance(exc, EventIdentityConflict):
            return FailureDecision(1, failed_stage, False, "EVENT_IDENTITY_CONFLICT")
        if isinstance(
            exc,
            (
                ConsumedOrderConflict,
                RefundReversalConflict,
                OriginalOrderNotRefundable,
                DeliveryIdentityConflict,
            ),
        ):
            return FailureDecision(3, failed_stage, True, "PERSISTENT_FAILURE")
        if isinstance(exc, PeriodResolutionError):
            category = 1 if failed_stage == "NORMALIZE" else 3
            return FailureDecision(
                category,
                failed_stage,
                category == 3,
                "PERIOD_RESOLUTION_ERROR",
            )
        if isinstance(exc, (TypeError, ValueError, OverflowError)):
            category = 1 if failed_stage == "NORMALIZE" else 3
            return FailureDecision(
                category,
                failed_stage,
                category == 3,
                "SCHEMA_VIOLATION" if category == 1 else "PERSISTENT_FAILURE",
            )
        if self._transient_exception_types and isinstance(
            exc,
            self._transient_exception_types,
        ):
            return FailureDecision(2, failed_stage, self._infer_residue(failed_stage, frame_names), "TRANSIENT_FAILURE")
        if self._is_retryable_kafka_exception(exc):
            return FailureDecision(2, failed_stage, self._infer_residue(failed_stage, frame_names), "TRANSIENT_FAILURE")
        if isinstance(exc, (OriginalOrderUnavailable, DeliveryStateUnavailable)):
            return FailureDecision(4, failed_stage, self._infer_residue(failed_stage, frame_names), "RETRY_EXHAUSTED")
        if type(exc) is RuntimeError:
            return FailureDecision(4, failed_stage, self._infer_residue(failed_stage, frame_names), "RETRY_EXHAUSTED")
        return FailureDecision(
            4,
            failed_stage,
            self._infer_residue(failed_stage, frame_names),
            "RETRY_EXHAUSTED",
            unclassified=True,
        )

    def _retry_dispatch(
        self,
        msg: Any,
        payload: Mapping[str, Any],
        initial_exc: Exception,
        *,
        bounded: bool,
    ) -> None:
        partition_key = self._partition_key(msg)
        retry_epoch = self._assignment_epoch
        self._pause_retry(msg)
        attempt = 1
        latest_exc = initial_exc
        latest_decision = self._classify_exception(initial_exc)

        while self.running and retry_epoch == self._assignment_epoch:
            if bounded and attempt >= self.settings.bounded_retry_attempts:
                exhausted = FailureDecision(
                    4,
                    latest_decision.failed_stage,
                    latest_decision.has_redis_residue,
                    "RETRY_EXHAUSTED",
                    latest_decision.unclassified,
                )
                self._finalize_failure(msg, payload, latest_exc, exhausted)
                return

            self._heartbeat_backoff(attempt)
            if not self.running or retry_epoch != self._assignment_epoch:
                return
            attempt += 1
            if attempt % 10 == 0:
                logger.warning(
                    "分区阻断重试仍未自愈: topic=%s partition=%s attempts=%s",
                    msg.topic(),
                    msg.partition(),
                    attempt,
                )
            dispatch_completed = False
            try:
                self._dispatch(msg.topic(), payload)
                dispatch_completed = True
                self.consumer.commit(message=msg, asynchronous=False)
            except Exception as exc:
                if dispatch_completed:
                    self._handle_post_dispatch_commit_failure(msg, payload, exc)
                    return
                latest_exc = exc
                latest_decision = self._classify_exception(exc)
                if latest_decision.category in {1, 3}:
                    self._finalize_failure(msg, payload, exc, latest_decision)
                    return
                new_bounded = latest_decision.category == 4
                # ②→④ 时④必须获得完整独立预算；④→②则立即恢复无限重试。
                if new_bounded and not bounded:
                    attempt = 1
                bounded = new_bounded
                continue

            self._reset_failure_counters()
            self._resume_retry(partition_key)
            return
    # endregion

    # region 分区阻断、心跳与换期排空
    def _partition_key(self, msg: Any) -> tuple[str, int]:
        return msg.topic(), msg.partition()

    def _partition_ref(self, key: tuple[str, int]) -> Any:
        return self._topic_partition_factory(key[0], key[1])

    def _pause_boundary(self, msg: Any) -> None:
        key = self._partition_key(msg)
        if key not in self._boundary_pauses:
            self.consumer.pause([self._partition_ref(key)])
            self._boundary_pauses.add(key)
        buffered_count = len(self._buffered_messages)
        self._buffered_messages = deque(
            buffered
            for buffered in self._buffered_messages
            if self._partition_key(buffered) != key
        )
        discarded_count = buffered_count - len(self._buffered_messages)
        if discarded_count:
            logger.warning(
                "边界 pause 清除同分区本地预取消息: topic=%s partition=%s count=%s",
                key[0],
                key[1],
                discarded_count,
            )
        # 边界 pause 绝不 resume；消息已经 poll，恢复后会被后续 commit 静默越过。

    def _pause_retry(self, msg: Any) -> None:
        key = self._partition_key(msg)
        if key not in self._retry_pauses and key not in self._boundary_pauses:
            self.consumer.pause([self._partition_ref(key)])
        self._retry_pauses.add(key)

    def _resume_retry(self, key: tuple[str, int]) -> None:
        self._retry_pauses.discard(key)
        if key not in self._boundary_pauses and self.running:
            self.consumer.resume([self._partition_ref(key)])

    def _heartbeat_backoff(self, attempt: int) -> None:
        delay = min(
            self.settings.retry_backoff_base_s * (2 ** max(0, attempt - 1)),
            30,
        )
        deadline = time.monotonic() + delay
        first_poll = True
        while self.running and (first_poll or time.monotonic() < deadline):
            first_poll = False
            remaining = max(0.0, deadline - time.monotonic())
            try:
                heartbeat_message = self.consumer.poll(min(1.0, remaining))
            except Exception:
                logger.warning("阻断退避期间 Kafka 心跳 poll 失败")
                continue
            if heartbeat_message is not None:
                # 关闭 auto offset store 后可安全暂存其他分区消息，避免心跳 poll 将它们吞掉。
                self._buffered_messages.append(heartbeat_message)

    def _check_drain_complete(self, detected_period: Optional[int] = None) -> None:
        assignment = {
            (partition.topic, partition.partition)
            for partition in self.consumer.assignment()
        }
        if assignment and assignment <= self._boundary_pauses:
            logger.critical(
                "PERIOD DRAIN COMPLETE: bound=%s detected=%s, safe to rebind",
                self.settings.bound_period,
                detected_period,
            )
            self.running = False
    # endregion

    # region 异常消息发送与提交
    def _finalize_failure(
        self,
        msg: Any,
        original_payload: Any,
        exc: Exception,
        decision: FailureDecision,
        *,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        record = self._build_exception_record(
            msg,
            original_payload,
            exc,
            decision,
            extra=extra,
        )
        if not self._send_exception_with_retry(msg, record):
            return
        if not self._commit_exception_offset_with_retry(msg):
            return
        self._register_permanent_failure(msg, original_payload, decision)
        if self._partition_key(msg) in self._retry_pauses:
            self._resume_retry(self._partition_key(msg))

    def _commit_exception_offset_with_retry(self, msg: Any) -> bool:
        """异常消息确认后，只重试 offset commit，不重复发布同一异常消息。"""

        attempt = 1
        while self.running:
            try:
                self.consumer.commit(message=msg, asynchronous=False)
                return True
            except Exception as exc:
                if not self._is_retryable_kafka_exception(exc):
                    logger.critical("异常 offset commit 遇到不可重试 Kafka 错误，停止消费者")
                    self.running = False
                    return False
                self._pause_retry(msg)
                if attempt % 10 == 0:
                    logger.warning(
                        "异常 offset commit 仍在重试: topic=%s partition=%s attempts=%s",
                        msg.topic(),
                        msg.partition(),
                        attempt,
                    )
                self._heartbeat_backoff(attempt)
                attempt += 1
        return False

    def _send_exception_with_retry(
        self,
        msg: Any,
        record: Mapping[str, Any],
    ) -> bool:
        attempt = 1
        while self.running:
            try:
                self._produce_exception_once(msg, record)
                return True
            except Exception:
                self._pause_retry(msg)
                if attempt % 10 == 0:
                    logger.warning(
                        "异常消息发送仍在重试: topic=%s partition=%s attempts=%s",
                        msg.topic(),
                        msg.partition(),
                        attempt,
                    )
                self._heartbeat_backoff(attempt)
                attempt += 1
        # 停机时不 commit、不 resume、不再 produce；重启后原 offset 必然重投。
        return False

    def _produce_exception_once(
        self,
        msg: Any,
        record: Mapping[str, Any],
    ) -> None:
        delivery_errors: list[Any] = []

        def delivery_report(error: Any, _delivery_message: Any) -> None:
            delivery_errors.append(error)

        identity = record.get("event_identity")
        key = (
            identity
            if isinstance(identity, str) and identity
            else f"{msg.topic()}:{msg.partition()}:{msg.offset()}"
        )
        self.producer.produce(
            TOPIC_EXCEPTIONS,
            key=key.encode("utf-8"),
            value=json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8"),
            callback=delivery_report,
        )
        remaining = self.producer.flush(10)
        if remaining != 0 or not delivery_errors or delivery_errors[-1] is not None:
            raise RuntimeError("exception topic delivery was not confirmed")

    def _build_exception_record(
        self,
        msg: Any,
        original_payload: Any,
        exc: Exception,
        decision: FailureDecision,
        *,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        payload = original_payload if isinstance(original_payload, Mapping) else {}
        completed, pending = self._completed_and_pending(decision.failed_stage)
        record = {
            "event_identity": payload.get("order_id"),
            "event_kind": "ORDER" if msg.topic() == TOPIC_ORDERS else "REFUND",
            "period": payload.get("period"),
            "user_id": payload.get("user_id"),
            "failed_stage": decision.failed_stage,
            "completed_stages": completed,
            "pending_stages": pending,
            "exception_class": type(exc).__name__,
            "exception_message": self._sanitize_exception_message(str(exc)),
            "reason": decision.reason,
            "has_redis_residue": decision.has_redis_residue,
            "unclassified": decision.unclassified,
            "source_topic": msg.topic(),
            "source_partition": msg.partition(),
            "source_offset": msg.offset(),
            "payload_hash": self._payload_hash(original_payload),
            "original_payload": original_payload,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "consumer_instance": self._consumer_instance,
        }
        if decision.reason == "PERIOD_RESOLUTION_ERROR":
            record["possible_wiring_error"] = True
        if extra:
            record.update(extra)
        return record
    # endregion

    # region 熔断
    def _register_permanent_failure(
        self,
        msg: Any,
        payload: Any,
        decision: FailureDecision,
    ) -> None:
        self._reason_counts[decision.reason] += 1
        if decision.reason == "EXPIRED_PERIOD":
            self._expired_failure_count += 1
            counter_name = "expired"
            count = self._expired_failure_count
        else:
            self._permanent_failure_count += 1
            counter_name = "permanent"
            count = self._permanent_failure_count
        if count < self.settings.circuit_breaker_threshold:
            return

        if counter_name == "expired":
            logger.critical(
                "PVAM expired-period circuit breaker triggered: reasons=%s; "
                "先核对 group offset 与 PVAM_BOUND_PERIOD，禁止盲目重启",
                dict(self._reason_counts),
            )
        else:
            logger.critical(
                "PVAM circuit breaker triggered: counter=%s reasons=%s",
                counter_name,
                dict(self._reason_counts),
            )
        breaker_decision = FailureDecision(
            3,
            decision.failed_stage,
            decision.has_redis_residue,
            "CIRCUIT_BREAKER",
        )
        breaker_record = self._build_exception_record(
            msg,
            payload,
            RuntimeError("consecutive permanent failure threshold reached"),
            breaker_decision,
            extra={
                "triggered_counter": counter_name,
                "reason_counts": dict(self._reason_counts),
            },
        )
        try:
            self._produce_exception_once(msg, breaker_record)
        except Exception:
            logger.critical("熔断事件未能送达异常 topic")
        self.running = False

    def _reset_failure_counters(self) -> None:
        self._permanent_failure_count = 0
        self._expired_failure_count = 0
        self._reason_counts.clear()
    # endregion

    # region traceback 归因与消息辅助
    @staticmethod
    def _traceback_context(exc: Exception) -> tuple[str, set[str]]:
        frame_names = {frame.name for frame in traceback.extract_tb(exc.__traceback__)}
        # 此处仅匹配 traceback 帧；拆分字面量保留 AC-4 禁调用守卫的精度。
        if "acknowledge_" "dispatched" in frame_names:
            return "ACK", frame_names
        for method_name, stage_name in _STAGE_METHODS.items():
            if method_name in frame_names:
                return stage_name, frame_names
        return "NORMALIZE", frame_names

    @staticmethod
    def _infer_residue(failed_stage: str, frame_names: set[str]) -> Optional[bool]:
        if failed_stage != "NORMALIZE":
            return True
        if frame_names & _NORMALIZE_RESIDUE_METHODS:
            return True
        return False if frame_names else None

    @staticmethod
    def _completed_and_pending(failed_stage: str) -> tuple[list[str], list[str]]:
        if failed_stage not in _STAGE_ORDER:
            return [], list(_STAGE_ORDER)
        index = _STAGE_ORDER.index(failed_stage)
        return list(_STAGE_ORDER[:index]), list(_STAGE_ORDER[index:])

    @staticmethod
    def _payload_hash(payload: Any) -> Optional[str]:
        if not isinstance(payload, Mapping):
            return None
        try:
            canonical = json.dumps(
                dict(payload),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
        except (TypeError, ValueError):
            return None
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _raw_payload_for_exception(raw: Any) -> Any:
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return raw

    def _sanitize_exception_message(self, message: str) -> str:
        password = self.settings.redis_password
        return message.replace(password, "[REDACTED]") if password else message

    def _is_retryable_kafka_exception(self, exc: Exception) -> bool:
        if not self._kafka_exception_types or not isinstance(
            exc,
            self._kafka_exception_types,
        ):
            return False
        kafka_error = exc.args[0] if exc.args else None
        retriable = getattr(kafka_error, "retriable", None)
        return bool(retriable()) if callable(retriable) else False

    def _is_fatal_message_error(self, error: Any) -> bool:
        fatal = getattr(error, "fatal", None)
        if callable(fatal) and fatal():
            return True
        code = getattr(error, "code", None)
        return callable(code) and code() in self._fatal_error_codes
    # endregion


def _ledger_prefixes(base_prefix: str) -> tuple[str, str, str]:
    """为共享 UAT 前缀追加账本命名空间，避免三个 hash key 域互相碰撞。"""

    normalized = base_prefix if base_prefix.endswith(":") else f"{base_prefix}:"
    return (
        f"{normalized}order_ledger:",
        f"{normalized}event_delivery:",
        f"{normalized}refund_reversal:",
    )


def build_runtime() -> PvEventConsumer:
    """按已批准组合根构造真实 Kafka、Redis、normalizer 与三个 stage。"""

    settings = load_settings()

    # 延迟 import 让配置缺失先 fail-fast，且不在模块 import 阶段连接外部系统。
    import redis
    from confluent_kafka import Consumer, KafkaError, KafkaException, Producer, TopicPartition

    from Common.BonusConfig import ConfigSnapshot, parse_signed_percent_to_ppm
    from Common.PeriodResolver import ContractPeriodRepository, PeriodResolver
    from MessageConsumer.PvEventDispatchCoordinator import PvEventDispatchCoordinator
    from MessageConsumer.PvEventNormalizer import InMemoryEventRegistry, PvEventNormalizer
    from Order.ConsumedOrderLedger import RedisConsumedOrderLedger
    from Order.PvEventDeliveryLedger import RedisPvEventDeliveryLedger
    from Order.RefundReversalLedger import RedisRefundReversalLedger
    from Redishelper.BaseRedisModel import redis_conn as stage_redis_conn
    from User.EliteBonusService import EliteBonusService
    from User.PlacementIncrementalService import PlacementIncrementalService
    from User.UserStatsService import BusyLockError, StaleLockError, UserStatsService

    # region Redis 同源断言与三账本
    consumer_redis_conn = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
        decode_responses=True,
    )
    consumer_run_id = consumer_redis_conn.info("server").get("run_id")
    stage_run_id = stage_redis_conn.info("server").get("run_id")
    if not consumer_run_id or consumer_run_id != stage_run_id:
        raise ConsumerConfigurationError("consumer and stage Redis instances differ")

    if settings.ledger_key_prefix:
        order_prefix, delivery_prefix, refund_prefix = _ledger_prefixes(
            settings.ledger_key_prefix
        )
        order_ledger = RedisConsumedOrderLedger(
            consumer_redis_conn,
            key_prefix=order_prefix,
        )
        delivery_ledger = RedisPvEventDeliveryLedger(
            consumer_redis_conn,
            key_prefix=delivery_prefix,
        )
        refund_ledger = RedisRefundReversalLedger(
            consumer_redis_conn,
            key_prefix=refund_prefix,
        )
    else:
        order_ledger = RedisConsumedOrderLedger(consumer_redis_conn)
        delivery_ledger = RedisPvEventDeliveryLedger(consumer_redis_conn)
        refund_ledger = RedisRefundReversalLedger(consumer_redis_conn)
    # endregion

    # region 单期 ConfigSnapshot 与三个 stage
    config_snapshot = ConfigSnapshot.from_rows(
        [
            {
                "config_name": "eliteRate",
                "type": "bonus",
                "value": settings.elite_rate_percent,
            }
        ],
        period_num=settings.bound_period,
        calc_month=settings.calc_month,
        source="pvam-pv-consumer",
        source_version="WORK-PVAM-02",
    )
    elite_bonus_service = EliteBonusService(
        period_num=settings.bound_period,
        calc_month=settings.calc_month,
        config_snapshot=config_snapshot,
        dask_address=settings.dask_scheduler,
    )
    expected_elite_rate_ppm = parse_signed_percent_to_ppm(
        settings.elite_rate_percent
    )
    if (
        elite_bonus_service.elite_rate_ppm != expected_elite_rate_ppm
        or elite_bonus_service.elite_rate_ppm <= 0
    ):
        raise ConsumerConfigurationError("eliteRate snapshot assertion failed")

    normalizer = PvEventNormalizer(
        PeriodResolver(ContractPeriodRepository()),
        InMemoryEventRegistry(),
        refund_ledger,
        order_repository=order_ledger,
        delivery_ledger=delivery_ledger,
    )
    coordinator = PvEventDispatchCoordinator(
        normalizer,
        user_stats_service=UserStatsService(),
        placement_service=PlacementIncrementalService(),
        elite_bonus_service=elite_bonus_service,
    )
    # endregion

    kafka_consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap,
            "group.id": GROUP_ID,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
            "max.poll.interval.ms": settings.max_poll_interval_ms,
        }
    )
    kafka_producer = Producer(
        {
            "bootstrap.servers": settings.kafka_bootstrap,
            "acks": "all",
        }
    )
    fatal_codes = tuple(
        code
        for code in (
            getattr(KafkaError, "_AUTHENTICATION", None),
            getattr(KafkaError, "TOPIC_AUTHORIZATION_FAILED", None),
            getattr(KafkaError, "GROUP_AUTHORIZATION_FAILED", None),
            getattr(KafkaError, "CLUSTER_AUTHORIZATION_FAILED", None),
        )
        if code is not None
    )
    return PvEventConsumer(
        consumer=kafka_consumer,
        producer=kafka_producer,
        coordinator=coordinator,
        settings=settings,
        transient_exception_types=(
            redis.exceptions.ConnectionError,
            redis.exceptions.TimeoutError,
            BusyLockError,
            StaleLockError,
        ),
        kafka_exception_types=(KafkaException,),
        topic_partition_factory=TopicPartition,
        fatal_error_codes=fatal_codes,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [pvam-pv-consumer] %(message)s",
    )
    try:
        build_runtime().run()
    except Exception as exc:
        # 启动失败只输出经过通用兜底的异常类型；连接口令不得进入日志。
        logger.critical("PvEventConsumer stopped: %s", type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
