"""raw 订单/退款事件到 NormalizedPvEvent 的唯一转换入口。"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict, Mapping, Protocol

from Common.PeriodResolver import PeriodResolver
from Model.Order.NormalizedPvEvent import NormalizedPvEvent
from Order.RefundReversalLedger import (
    APPLIED,
    DUPLICATE_NOOP,
    OriginalOrderNotRefundable,
    OriginalOrderRepository,
    OriginalOrderUnavailable,
    RefundReversalConflict,
    RefundReversalLedger,
)
from MessageConsumer.PvEventSchema import (
    validate_order_payload,
    validate_refund_payload,
)


NEW = "NEW"
DUPLICATE = "DUPLICATE"


class EventIdentityConflict(RuntimeError):
    """同一 source identity 对应了不同 payload hash。"""


class EventRegistry(Protocol):
    def register(
        self,
        *,
        source_system: str,
        source_event_id: str,
        payload_hash: str,
    ) -> str:
        ...


class InMemoryEventRegistry:
    """DEV 测试替身；不代表真实 Redis/Kafka 幂等验证。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._payload_hashes: Dict[str, str] = {}

    def register(
        self,
        *,
        source_system: str,
        source_event_id: str,
        payload_hash: str,
    ) -> str:
        identity = f"{source_system}:{source_event_id}"
        with self._lock:
            previous_hash = self._payload_hashes.get(identity)
            if previous_hash is None:
                self._payload_hashes[identity] = payload_hash
                return NEW
            if previous_hash != payload_hash:
                raise EventIdentityConflict(
                    "the same source identity was registered with a different payload hash"
                )
            return DUPLICATE


class PvEventNormalizer:
    """只在 raw 边界调用公共金额解析器，并冻结后续 stage 输入。"""

    def __init__(
        self,
        resolver: PeriodResolver,
        event_registry: EventRegistry,
        refund_ledger: RefundReversalLedger,
        *,
        order_repository: OriginalOrderRepository | None = None,
        source_system: str = "PV_EVENT_DEV_ADAPTER",
    ):
        if not isinstance(resolver, PeriodResolver):
            raise TypeError("resolver must be PeriodResolver")
        if event_registry is None:
            raise TypeError("event_registry is required")
        if refund_ledger is None:
            raise TypeError("refund_ledger is required")
        if not isinstance(source_system, str) or not source_system:
            raise TypeError("source_system must be a non-empty string")
        self._resolver = resolver
        self._event_registry = event_registry
        self._refund_ledger = refund_ledger
        self._order_repository = order_repository
        # DEV 默认值只为任务书固定的测试骨架服务；生产入口必须注入真实 source identity。
        self._source_system = source_system

    def normalize_order(self, payload: Mapping[str, Any]) -> NormalizedPvEvent:
        validated = validate_order_payload(payload)
        source_system = validated.source_system or self._source_system
        payload_hash = self._hash_payload(payload)
        # DEC-011 D1：订单周期由消息直接提供，本系统不再从批准时间推导归期。
        period_snapshot = self._resolver.resolve_current(validated.period_num)
        registration = self._register(
            source_system=source_system,
            source_event_id=validated.source_event_id,
            payload_hash=payload_hash,
        )
        if registration == DUPLICATE:
            return self._build_event(
                source_system=source_system,
                source_event_id=validated.source_event_id,
                user_id=validated.user_id,
                payload_hash=payload_hash,
                business_revision=validated.business_revision,
                previous_business_revision=validated.previous_business_revision,
                delta_units=0,
                period_snapshot=period_snapshot,
                disposition=DUPLICATE_NOOP,
                event_kind="ORDER",
            )
        return self._build_event(
            source_system=source_system,
            source_event_id=validated.source_event_id,
            user_id=validated.user_id,
            payload_hash=payload_hash,
            business_revision=validated.business_revision,
            previous_business_revision=validated.previous_business_revision,
            delta_units=(
                validated.amount_units
                - (validated.previous_amount_units or 0)
            ),
            period_snapshot=period_snapshot,
            disposition="APPLY",
            event_kind="ORDER",
        )

    def normalize_refund(self, payload: Mapping[str, Any]) -> NormalizedPvEvent:
        validated = validate_refund_payload(payload)
        source_system = validated.source_system or self._source_system
        payload_hash = self._hash_payload(payload)
        # DEC-011 D3：退款归期由上游消息确定；approved_at 仅作审计留痕。
        period_snapshot = self._resolver.resolve_current(validated.period_num)

        # region 查询原订单权威金额与可退款状态
        # raw refund amount 只用于检测上游漂移；负向 delta 必须来自原订单 repository。
        if self._order_repository is None:
            raise OriginalOrderUnavailable(
                "refund normalization requires an authoritative original order repository"
            )
        authoritative_order = self._order_repository.get_refundable_order(
            validated.original_order_id
        )
        if validated.original_amount_units != authoritative_order.amount_units:
            raise RefundReversalConflict(
                "refund amount conflicts with the authoritative original order"
            )
        # endregion

        self._register(
            source_system=source_system,
            source_event_id=validated.source_event_id,
            payload_hash=payload_hash,
        )
        # region 退款权威账本确认
        # event identity 只证明 payload 未漂移；ledger 失败时不能把已登记事件误判为完成。
        # 可退款状态只约束首次原子声明；已完成的相同退款即使订单状态变化仍保持 no-op。
        # 因此重复事件仍核对整单冲销 CAS，由 ledger 决定本次是否需要恢复 APPLY。
        claim = self._refund_ledger.claim_whole_order(
            original_order_id=validated.original_order_id,
            source_event_id=validated.source_event_id,
            payload_hash=payload_hash,
            original_amount_units=authoritative_order.amount_units,
            original_order_refundable=authoritative_order.refundable,
        )
        disposition = "APPLY" if claim.disposition == APPLIED else DUPLICATE_NOOP
        delta_units = -claim.original_amount_units if claim.disposition == APPLIED else 0
        # endregion

        return self._build_event(
            source_system=source_system,
            source_event_id=validated.source_event_id,
            user_id=validated.user_id,
            payload_hash=payload_hash,
            business_revision=validated.business_revision,
            previous_business_revision=validated.previous_business_revision,
            delta_units=delta_units,
            period_snapshot=period_snapshot,
            disposition=disposition,
            event_kind="REFUND",
            original_order_id=validated.original_order_id,
        )

    def _register(
        self,
        *,
        source_system: str,
        source_event_id: str,
        payload_hash: str,
    ) -> str:
        disposition = self._event_registry.register(
            source_system=source_system,
            source_event_id=source_event_id,
            payload_hash=payload_hash,
        )
        if disposition not in {NEW, DUPLICATE}:
            raise RuntimeError(
                f"event registry returned an invalid disposition: {disposition!r}"
            )
        return disposition

    @staticmethod
    def _hash_payload(payload: Mapping[str, Any]) -> str:
        if not isinstance(payload, Mapping):
            raise TypeError("PV event payload must be a mapping")
        try:
            canonical = json.dumps(
                dict(payload),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise TypeError("PV event payload must be canonical JSON data") from exc
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_event(
        *,
        source_system: str,
        source_event_id: str,
        user_id: str,
        payload_hash: str,
        business_revision: int,
        previous_business_revision: Any,
        delta_units: int,
        period_snapshot: Any,
        disposition: str,
        event_kind: str,
        original_order_id: Any = None,
    ) -> NormalizedPvEvent:
        return NormalizedPvEvent(
            source_system=source_system,
            source_event_id=source_event_id,
            user_id=user_id,
            payload_hash=payload_hash,
            business_revision=business_revision,
            previous_business_revision=previous_business_revision,
            effective_pv_delta_units=delta_units,
            period_snapshot=period_snapshot,
            disposition=disposition,
            event_kind=event_kind,
            original_order_id=original_order_id,
        )
