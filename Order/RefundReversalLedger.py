"""整单退款只产生一次负向 PV delta 的原子权威接口。"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Protocol

from Common.PvAmount import require_units_int


APPLIED = "APPLIED"
DUPLICATE_NOOP = "DUPLICATE_NOOP"
CONFLICT = "CONFLICT"
NOT_REFUNDABLE = "NOT_REFUNDABLE"


class RefundReversalConflict(RuntimeError):
    """同一原订单出现不一致的整单退款事实。"""


class OriginalOrderUnavailable(RuntimeError):
    """原订单权威记录不存在或暂时不可取得。"""


class OriginalOrderNotRefundable(RuntimeError):
    """权威订单状态不允许自动整单冲销。"""


@dataclass(frozen=True)
class OriginalOrderSnapshot:
    """退款边界所需的最小权威订单快照，不解释具体业务状态枚举。"""

    original_order_id: str
    amount_units: int
    refundable: bool

    def __post_init__(self) -> None:
        _require_nonempty_string(
            self.original_order_id,
            field_name="original_order_id",
        )
        amount_units = require_units_int(
            self.amount_units,
            field_name="authoritative_original_amount_units",
        )
        if amount_units < 0:
            raise ValueError("authoritative original order amount cannot be negative")
        if type(self.refundable) is not bool:
            raise TypeError("refundable must be bool")


class OriginalOrderRepository(Protocol):
    def get_refundable_order(self, original_order_id: str) -> OriginalOrderSnapshot:
        ...


class MappingOriginalOrderRepository:
    """DEV 固定数据适配器；生产必须由部署层提供真实订单 repository。"""

    def __init__(self, records: Mapping[str, Mapping[str, Any]]):
        if not isinstance(records, Mapping):
            raise TypeError("records must be a mapping")
        self._records = dict(records)

    def get_refundable_order(self, original_order_id: str) -> OriginalOrderSnapshot:
        original_order_id = _require_nonempty_string(
            original_order_id,
            field_name="original_order_id",
        )
        record = self._records.get(original_order_id)
        if record is None:
            raise OriginalOrderUnavailable(
                f"authoritative original order is unavailable: {original_order_id}"
            )
        if not isinstance(record, Mapping):
            raise TypeError("authoritative original order record must be a mapping")
        return OriginalOrderSnapshot(
            original_order_id=original_order_id,
            amount_units=record.get("amount_units"),
            refundable=record.get("refundable"),
        )


@dataclass(frozen=True)
class RefundClaim:
    disposition: str
    original_amount_units: int

    def __post_init__(self) -> None:
        if self.disposition not in {APPLIED, DUPLICATE_NOOP}:
            raise ValueError(f"unsupported refund disposition: {self.disposition!r}")
        require_units_int(
            self.original_amount_units,
            field_name="original_amount_units",
        )


class RefundReversalLedger(Protocol):
    def claim_whole_order(
        self,
        *,
        original_order_id: str,
        source_event_id: str,
        payload_hash: str,
        original_amount_units: int,
        original_order_refundable: bool,
    ) -> RefundClaim:
        ...


def _require_nonempty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


class InMemoryRefundReversalLedger:
    """DEV 测试替身；线程锁只模拟单进程 CAS，不代表真实 Redis UAT。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._claims: Dict[str, Dict[str, Any]] = {}

    def claim_whole_order(
        self,
        *,
        original_order_id: str,
        source_event_id: str,
        payload_hash: str,
        original_amount_units: int,
        original_order_refundable: bool,
    ) -> RefundClaim:
        original_order_id = _require_nonempty_string(
            original_order_id,
            field_name="original_order_id",
        )
        source_event_id = _require_nonempty_string(
            source_event_id,
            field_name="source_event_id",
        )
        payload_hash = _require_nonempty_string(
            payload_hash,
            field_name="payload_hash",
        )
        original_amount_units = require_units_int(
            original_amount_units,
            field_name="original_amount_units",
        )
        if original_amount_units < 0:
            raise ValueError("original_amount_units cannot be negative")
        if type(original_order_refundable) is not bool:
            raise TypeError("original_order_refundable must be bool")

        with self._lock:
            current = self._claims.get(original_order_id)
            if current is None:
                if not original_order_refundable:
                    raise OriginalOrderNotRefundable(
                        f"authoritative original order is not refundable: {original_order_id}"
                    )
                self._claims[original_order_id] = {
                    "source_event_id": source_event_id,
                    "payload_hash": payload_hash,
                    "original_amount_units": original_amount_units,
                }
                return RefundClaim(APPLIED, original_amount_units)
            if current["original_amount_units"] != original_amount_units:
                raise RefundReversalConflict(
                    "whole-order refund amount conflicts with the existing reversal claim"
                )
            return RefundClaim(DUPLICATE_NOOP, original_amount_units)


class RedisRefundReversalLedger:
    """使用单条 Lua 脚本执行 Redis 原子整单冲销 CAS。"""

    _CLAIM_SCRIPT = """
local key = KEYS[1]
local source_event_id = ARGV[1]
local payload_hash = ARGV[2]
local original_amount_units = ARGV[3]
local original_order_refundable = ARGV[4]

if redis.call('EXISTS', key) == 0 then
    if original_order_refundable ~= '1' then
        return {'NOT_REFUNDABLE', original_amount_units}
    end
    redis.call('HSET', key,
        'source_event_id', source_event_id,
        'payload_hash', payload_hash,
        'original_amount_units', original_amount_units)
    return {'APPLIED', original_amount_units}
end

local stored_amount = redis.call('HGET', key, 'original_amount_units')
if stored_amount ~= original_amount_units then
    return {'CONFLICT', stored_amount}
end
return {'DUPLICATE_NOOP', stored_amount}
"""

    def __init__(self, redis_conn: Any, *, key_prefix: str = "pvam:refund_reversal:"):
        if redis_conn is None:
            raise TypeError("redis_conn is required")
        if not isinstance(key_prefix, str) or not key_prefix:
            raise TypeError("key_prefix must be a non-empty string")
        self._redis_conn = redis_conn
        self._key_prefix = key_prefix

    def claim_whole_order(
        self,
        *,
        original_order_id: str,
        source_event_id: str,
        payload_hash: str,
        original_amount_units: int,
        original_order_refundable: bool,
    ) -> RefundClaim:
        original_order_id = _require_nonempty_string(
            original_order_id,
            field_name="original_order_id",
        )
        source_event_id = _require_nonempty_string(
            source_event_id,
            field_name="source_event_id",
        )
        payload_hash = _require_nonempty_string(
            payload_hash,
            field_name="payload_hash",
        )
        original_amount_units = require_units_int(
            original_amount_units,
            field_name="original_amount_units",
        )
        if original_amount_units < 0:
            raise ValueError("original_amount_units cannot be negative")
        if type(original_order_refundable) is not bool:
            raise TypeError("original_order_refundable must be bool")

        raw_result = self._redis_conn.eval(
            self._CLAIM_SCRIPT,
            1,
            f"{self._key_prefix}{original_order_id}",
            source_event_id,
            payload_hash,
            str(original_amount_units),
            "1" if original_order_refundable else "0",
        )
        if not isinstance(raw_result, (list, tuple)) or len(raw_result) != 2:
            raise RuntimeError("Redis refund CAS returned an invalid response")

        disposition = self._decode(raw_result[0])
        stored_amount_raw = self._decode(raw_result[1])
        try:
            stored_amount_units = int(stored_amount_raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Redis refund CAS returned an invalid amount") from exc

        if disposition == NOT_REFUNDABLE:
            raise OriginalOrderNotRefundable(
                f"authoritative original order is not refundable: {original_order_id}"
            )
        if disposition == CONFLICT:
            raise RefundReversalConflict(
                "whole-order refund amount conflicts with the Redis authority record"
            )
        if disposition not in {APPLIED, DUPLICATE_NOOP}:
            raise RuntimeError(
                f"Redis refund CAS returned an invalid disposition: {disposition!r}"
            )
        return RefundClaim(disposition, stored_amount_units)

    @staticmethod
    def _decode(value: Any) -> Any:
        return value.decode("utf-8") if isinstance(value, bytes) else value
