"""按 MSG-CONTRACT-v1 独立实现的 WORK-PVAM-02 UAT 消息生产工具。

本工具只以合同文档定义字段，不与消费端共享 schema 代码。保持两端独立可以让 UAT
暴露双方对合同理解不一致的问题，避免共享实现造成同源误判。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
from typing import Any, Iterable, Mapping, Optional, Sequence


TOPIC_ORDERS = "pvam-pv-orders"
TOPIC_REFUNDS = "pvam-pv-refunds"
SCENARIOS = (
    "order",
    "refund",
    "cross-period-refund",
    "duplicate",
    "payload-drift",
    "forbidden-field",
    "schema-invalid",
    "future-period",
    "expired-period",
    "drain-sentinel",
)
FORBIDDEN_FIELDS = (
    "business_revision",
    "previous_business_revision",
    "previous_amount",
)
INVALID_CASES = (
    "bv-number",
    "missing-required",
    "period-zero",
    "period-negative",
    "period-bool",
    "amount-scale",
)


class ProducerConfigurationError(RuntimeError):
    """命令行参数或连接配置不足，无法构造指定场景。"""


class DeliveryError(RuntimeError):
    """Kafka 回调未确认投递成功。"""


@dataclass(frozen=True)
class PlannedMessage:
    topic: str
    key: str
    payload: Mapping[str, Any]
    partition: Optional[int] = None

    def encoded_payload(self) -> bytes:
        return json.dumps(
            self.payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")


def _deterministic_id(scenario: str, period: int, sequence: int) -> str:
    return f"{scenario}-{period}-{sequence}"


def _order_payload(
    *,
    order_id: str,
    period: Any,
    user_id: str,
    bv: Any,
) -> dict[str, Any]:
    return {
        "type": "order",
        "order_id": order_id,
        "period": period,
        "user_id": user_id,
        "bv": bv,
    }


def _refund_payload(
    *,
    order_id: str,
    period: int,
    user_id: str,
    original_order_id: str,
    amount: str,
    approved_at: Optional[str],
) -> dict[str, Any]:
    payload = {
        "type": "refund",
        "order_id": order_id,
        "period": period,
        "user_id": user_id,
        "original_order_id": original_order_id,
        "amount": amount,
    }
    if approved_at is not None:
        payload["approved_at"] = approved_at
    return payload


def _message(
    topic: str,
    payload: Mapping[str, Any],
    *,
    partition: Optional[int] = None,
) -> PlannedMessage:
    return PlannedMessage(
        topic=topic,
        key=str(payload["order_id"]),
        payload=payload,
        partition=partition,
    )


def build_plan(args: argparse.Namespace) -> list[PlannedMessage]:
    """从合同字段构造投递计划；不读 Redis、不探测消费端。"""

    scenario = args.scenario
    order_id = args.order_id or _deterministic_id(
        scenario,
        args.period,
        args.seq,
    )
    amount = args.amount if args.amount is not None else args.bv

    # region 合同正常路径
    if scenario in {"order", "future-period", "expired-period"}:
        return [
            _message(
                TOPIC_ORDERS,
                _order_payload(
                    order_id=order_id,
                    period=args.period,
                    user_id=args.user_id,
                    bv=args.bv,
                ),
                partition=args.partition,
            )
        ]

    if scenario == "refund":
        if not args.original_order_id:
            raise ProducerConfigurationError(
                "refund requires --original-order-id"
            )
        return [
            _message(
                TOPIC_REFUNDS,
                _refund_payload(
                    order_id=order_id,
                    period=args.period,
                    user_id=args.user_id,
                    original_order_id=args.original_order_id,
                    amount=amount,
                    approved_at=args.approved_at,
                ),
                partition=args.partition,
            )
        ]

    if scenario == "cross-period-refund":
        base_order_id = args.order_id or _deterministic_id(
            scenario,
            args.period,
            args.seq,
        )
        refund_period = args.period + 1
        refund_id = args.refund_order_id or _deterministic_id(
            scenario,
            refund_period,
            args.seq + 1,
        )
        return [
            _message(
                TOPIC_ORDERS,
                _order_payload(
                    order_id=base_order_id,
                    period=args.period,
                    user_id=args.user_id,
                    bv=args.bv,
                ),
            ),
            _message(
                TOPIC_REFUNDS,
                _refund_payload(
                    order_id=refund_id,
                    period=refund_period,
                    user_id=args.user_id,
                    original_order_id=base_order_id,
                    amount=amount,
                    approved_at=args.approved_at,
                ),
            ),
        ]
    # endregion

    # region 幂等、漂移与合同违规路径
    if scenario == "duplicate":
        message = _message(
            TOPIC_ORDERS,
            _order_payload(
                order_id=order_id,
                period=args.period,
                user_id=args.user_id,
                bv=args.bv,
            ),
            partition=args.partition,
        )
        return [message, message]

    if scenario == "payload-drift":
        first = _order_payload(
            order_id=order_id,
            period=args.period,
            user_id=args.user_id,
            bv=args.bv,
        )
        drifted = dict(first)
        drifted["bv"] = args.drift_bv
        return [
            _message(TOPIC_ORDERS, first, partition=args.partition),
            _message(TOPIC_ORDERS, drifted, partition=args.partition),
        ]

    if scenario == "forbidden-field":
        selected = args.forbidden_field or list(FORBIDDEN_FIELDS)
        payload = _order_payload(
            order_id=order_id,
            period=args.period,
            user_id=args.user_id,
            bv=args.bv,
        )
        for field_name in selected:
            if field_name == "business_revision":
                payload[field_name] = 1
            elif field_name == "previous_business_revision":
                payload[field_name] = None
            else:
                payload[field_name] = args.bv
        return [_message(TOPIC_ORDERS, payload, partition=args.partition)]

    if scenario == "schema-invalid":
        payload = _order_payload(
            order_id=order_id,
            period=args.period,
            user_id=args.user_id,
            bv=args.bv,
        )
        if args.invalid_case == "bv-number":
            payload["bv"] = float(args.bv)
        elif args.invalid_case == "missing-required":
            del payload["user_id"]
        elif args.invalid_case == "period-zero":
            payload["period"] = 0
        elif args.invalid_case == "period-negative":
            payload["period"] = -1
        elif args.invalid_case == "period-bool":
            payload["period"] = True
        elif args.invalid_case == "amount-scale":
            payload["bv"] = "1500.999"
        return [_message(TOPIC_ORDERS, payload, partition=args.partition)]
    # endregion

    # region 六分区换期排空哨兵
    if scenario == "drain-sentinel":
        if not args.original_order_id:
            raise ProducerConfigurationError(
                "drain-sentinel requires --original-order-id from an already "
                "refunded order"
            )
        if not args.refund_order_id:
            raise ProducerConfigurationError(
                "drain-sentinel requires --refund-order-id from the exact "
                "already-delivered refund"
            )
        if args.amount is None:
            raise ProducerConfigurationError(
                "drain-sentinel requires --amount from the exact "
                "already-delivered refund"
            )
        if args.partition is not None:
            raise ProducerConfigurationError(
                "drain-sentinel always targets all six partitions; omit --partition"
            )
        messages: list[PlannedMessage] = []
        for partition in range(3):
            sequence = args.seq + partition
            sentinel_id = _deterministic_id(scenario, args.period, sequence)
            messages.append(
                _message(
                    TOPIC_ORDERS,
                    _order_payload(
                        order_id=sentinel_id,
                        period=args.period,
                        user_id=args.user_id,
                        bv="0",
                    ),
                    partition=partition,
                )
            )
        for partition in range(3):
            messages.append(
                _message(
                    TOPIC_REFUNDS,
                    _refund_payload(
                        order_id=args.refund_order_id,
                        period=args.period,
                        user_id=args.user_id,
                        original_order_id=args.original_order_id,
                        amount=amount,
                        approved_at=args.approved_at,
                    ),
                    partition=partition,
                )
            )
        return messages
    # endregion

    raise ProducerConfigurationError(f"unsupported scenario: {scenario}")


def _evidence_record(
    message: PlannedMessage,
    *,
    partition: Optional[int],
    offset: Optional[int],
    sent_at: str,
) -> dict[str, Any]:
    encoded = message.encoded_payload()
    return {
        "topic": message.topic,
        "partition": partition,
        "offset": offset,
        "key": message.key,
        "payload": message.payload,
        "payload_sha256": hashlib.sha256(encoded).hexdigest(),
        "sent_at": sent_at,
    }


def emit_dry_run(messages: Iterable[PlannedMessage]) -> None:
    for message in messages:
        record = _evidence_record(
            message,
            partition=message.partition,
            offset=None,
            sent_at=datetime.now(timezone.utc).isoformat(),
        )
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))


def deliver(messages: Iterable[PlannedMessage], *, bootstrap: str) -> None:
    """逐条等待 delivery callback，确认成功后才输出证据行。"""

    from confluent_kafka import Producer

    producer = Producer({"bootstrap.servers": bootstrap, "acks": "all"})
    for message in messages:
        reports: list[tuple[Any, Any]] = []

        def delivery_report(error: Any, delivered_message: Any) -> None:
            reports.append((error, delivered_message))

        produce_kwargs: dict[str, Any] = {
            "key": message.key.encode("utf-8"),
            "value": message.encoded_payload(),
            "callback": delivery_report,
        }
        if message.partition is not None:
            produce_kwargs["partition"] = message.partition

        producer.produce(message.topic, **produce_kwargs)
        remaining = producer.flush(30)
        if remaining != 0 or len(reports) != 1:
            raise DeliveryError(
                f"delivery callback incomplete for key={message.key}"
            )
        error, delivered_message = reports[0]
        if error is not None:
            raise DeliveryError(f"delivery failed for key={message.key}: {error}")

        record = _evidence_record(
            message,
            partition=delivered_message.partition(),
            offset=delivered_message.offset(),
            sent_at=datetime.now(timezone.utc).isoformat(),
        )
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Produce deterministic WORK-PVAM-02 UAT messages",
    )
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("--period", type=int, required=True)
    parser.add_argument("--user-id", default="U-UAT-001")
    parser.add_argument("--bv", default="1500.99")
    parser.add_argument("--amount")
    parser.add_argument("--drift-bv", default="1501.00")
    parser.add_argument("--order-id")
    parser.add_argument("--refund-order-id")
    parser.add_argument("--original-order-id")
    parser.add_argument("--approved-at")
    parser.add_argument("--seq", type=int, default=1)
    parser.add_argument("--partition", type=int, choices=(0, 1, 2))
    parser.add_argument(
        "--forbidden-field",
        action="append",
        choices=FORBIDDEN_FIELDS,
        help="repeat to emit a combination; default emits all three",
    )
    parser.add_argument(
        "--invalid-case",
        choices=INVALID_CASES,
        default="bv-number",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        bootstrap = os.environ.get("PVAM_KAFKA_BOOTSTRAP")
        if not bootstrap:
            raise ProducerConfigurationError("PVAM_KAFKA_BOOTSTRAP is required")
        plan = build_plan(args)
        if args.dry_run:
            emit_dry_run(plan)
        else:
            deliver(plan, bootstrap=bootstrap)
    except (ProducerConfigurationError, DeliveryError, ImportError, ValueError) as exc:
        print(f"uat_message_producer failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"uat_message_producer failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
