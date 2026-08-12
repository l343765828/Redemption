"""跨 PV 增量 stage 传递的不可变金额事件。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from Common.PeriodResolver import PeriodSnapshot
from Common.PvAmount import AMOUNT_ENCODING_VERSION_V2, require_amount_version, require_units_int


_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_DISPOSITIONS = frozenset({"APPLY", "DUPLICATE_NOOP"})
_ALLOWED_EVENT_KINDS = frozenset({"ORDER", "REFUND"})


def _require_nonempty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


def _require_revision(value: object, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


@dataclass(frozen=True)
class NormalizedPvEvent:
    """金额只以 signed int64 units 表达，raw 字段不会进入业务 stage。"""

    source_system: str
    source_event_id: str
    payload_hash: str
    business_revision: int
    previous_business_revision: Optional[int]
    effective_pv_delta_units: int
    period_snapshot: PeriodSnapshot
    amount_encoding_version: int = AMOUNT_ENCODING_VERSION_V2
    disposition: str = "APPLY"
    event_kind: str = "ORDER"
    original_order_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_nonempty_string(self.source_system, field_name="source_system")
        _require_nonempty_string(self.source_event_id, field_name="source_event_id")
        if not isinstance(self.payload_hash, str) or not _SHA256_HEX.fullmatch(
            self.payload_hash
        ):
            raise ValueError("payload_hash must be a lowercase SHA-256 hex digest")
        _require_revision(self.business_revision, field_name="business_revision")
        if self.previous_business_revision is not None:
            _require_revision(
                self.previous_business_revision,
                field_name="previous_business_revision",
            )
        require_units_int(
            self.effective_pv_delta_units,
            field_name="effective_pv_delta_units",
        )
        require_amount_version(self.amount_encoding_version)
        if not isinstance(self.period_snapshot, PeriodSnapshot):
            raise TypeError("period_snapshot must be PeriodSnapshot")
        if self.disposition not in _ALLOWED_DISPOSITIONS:
            raise ValueError(f"unsupported disposition: {self.disposition!r}")
        if self.event_kind not in _ALLOWED_EVENT_KINDS:
            raise ValueError(f"unsupported event_kind: {self.event_kind!r}")
        if self.event_kind == "REFUND":
            _require_nonempty_string(
                self.original_order_id,
                field_name="original_order_id",
            )
        elif self.original_order_id is not None:
            raise ValueError("original_order_id is only valid for REFUND events")
        if self.disposition == "DUPLICATE_NOOP" and self.effective_pv_delta_units != 0:
            raise ValueError("DUPLICATE_NOOP must carry a zero effective delta")

    @property
    def identity(self) -> str:
        return f"{self.source_system}:{self.source_event_id}"


def require_normalized_pv_event(value: object) -> NormalizedPvEvent:
    if not isinstance(value, NormalizedPvEvent):
        raise TypeError("normalized_event must be NormalizedPvEvent")
    # dataclass 构造时已完成全部字段验证；此函数为 stage 入口提供统一显式门禁。
    return value
