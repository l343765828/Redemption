"""订单与整单退款 raw payload 的严格 schema 边界。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from Common.PvAmount import parse_external_decimal_to_units


def _require_mapping(payload: object) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError("PV event payload must be a mapping")
    return payload


def _require_nonempty_string(
    payload: Mapping[str, Any],
    field_name: str,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


def _require_revision(payload: Mapping[str, Any], field_name: str, default: Any) -> Any:
    value = payload.get(field_name, default)
    if value is None and field_name == "previous_business_revision":
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _parse_approved_at(raw: object) -> datetime:
    if not isinstance(raw, str) or not raw:
        raise TypeError("approved_at must be a non-empty ISO-8601 string")
    try:
        value = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValueError("approved_at must be a valid ISO-8601 timestamp") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("approved_at must include a timezone")
    return value


def _parse_amount_units(
    payload: Mapping[str, Any],
    field_name: str = "amount",
) -> int:
    if field_name not in payload:
        raise ValueError(f"{field_name} is required")
    # 公共解析器同时拒绝 JSON number/bool/null、空白、指数、NaN/Infinity 和超两位小数。
    amount_units = parse_external_decimal_to_units(
        payload[field_name],
        max_decimals=2,
    )
    if amount_units < 0:
        raise ValueError(f"raw {field_name} cannot be negative")
    return amount_units


def _parse_period_num(payload: Mapping[str, Any]) -> int:
    if "period" not in payload:
        raise ValueError("period is required")
    value = payload["period"]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("period must be int")
    if value < 1:
        raise ValueError("period must be greater than or equal to 1")
    return value


@dataclass(frozen=True)
class ValidatedOrderPayload:
    source_event_id: str
    user_id: str
    amount_units: int
    previous_amount_units: Optional[int]
    period_num: int
    business_revision: int
    previous_business_revision: Optional[int]


@dataclass(frozen=True)
class ValidatedRefundPayload:
    source_event_id: str
    user_id: str
    original_order_id: str
    original_amount_units: int
    period_num: int
    approved_at: Optional[datetime]
    business_revision: int
    previous_business_revision: Optional[int]


def validate_order_payload(payload: object) -> ValidatedOrderPayload:
    raw = _require_mapping(payload)
    period_num = _parse_period_num(raw)
    business_revision = _require_revision(raw, "business_revision", 1)
    previous_business_revision = _require_revision(
        raw,
        "previous_business_revision",
        None,
    )
    if previous_business_revision is None:
        if "previous_amount" in raw:
            raise ValueError("previous_amount requires previous_business_revision")
        previous_amount_units = None
    else:
        previous_amount_units = _parse_amount_units(raw, "previous_amount")

    return ValidatedOrderPayload(
        source_event_id=_require_nonempty_string(raw, "order_id"),
        user_id=_require_nonempty_string(raw, "user_id"),
        amount_units=_parse_amount_units(raw, "bv"),
        previous_amount_units=previous_amount_units,
        period_num=period_num,
        business_revision=business_revision,
        previous_business_revision=previous_business_revision,
    )


def validate_refund_payload(payload: object) -> ValidatedRefundPayload:
    raw = _require_mapping(payload)
    approved_at = (
        _parse_approved_at(raw["approved_at"])
        if "approved_at" in raw
        else None
    )
    return ValidatedRefundPayload(
        source_event_id=_require_nonempty_string(raw, "order_id"),
        user_id=_require_nonempty_string(raw, "user_id"),
        original_order_id=_require_nonempty_string(raw, "original_order_id"),
        original_amount_units=_parse_amount_units(raw),
        period_num=_parse_period_num(raw),
        approved_at=approved_at,
        business_revision=_require_revision(raw, "business_revision", 1),
        previous_business_revision=_require_revision(
            raw,
            "previous_business_revision",
            None,
        ),
    )
