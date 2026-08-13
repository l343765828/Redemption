"""本系统已消费订单的退款金额与周期权威账本。"""

from __future__ import annotations

import threading
from typing import Any, Dict, Protocol

from Common.PvAmount import require_units_int
from Order.RefundReversalLedger import (
    OriginalOrderRepository,
    OriginalOrderSnapshot,
    OriginalOrderUnavailable,
)


RECORDED = "RECORDED"
DUPLICATE_NOOP = "DUPLICATE_NOOP"
CONFLICT = "CONFLICT"
FOUND = "FOUND"
MISSING = "MISSING"


class ConsumedOrderConflict(RuntimeError):
    """同一 order_id 对应了不同金额或周期。"""


class ConsumedOrderLedger(OriginalOrderRepository, Protocol):
    def record_order(self, order_id: str, amount_units: int, period: int) -> None:
        ...

    def get_order_period(self, original_order_id: str) -> int:
        ...

    def purge_periods_before(self, period: int) -> None:
        ...


def _require_order_id(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("order_id must be a non-empty string")
    return value


def _require_amount_units(value: object) -> int:
    amount_units = require_units_int(value, field_name="amount_units")
    if amount_units < 0:
        raise ValueError("amount_units cannot be negative")
    return amount_units


def _require_period(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("period must be int")
    if value < 1:
        raise ValueError("period must be greater than or equal to 1")
    return value


class InMemoryConsumedOrderLedger:
    """DEV 测试替身；线程锁只模拟单进程原子语义。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._orders: Dict[str, Dict[str, int]] = {}

    def record_order(self, order_id: str, amount_units: int, period: int) -> None:
        # region 参数验证
        order_id = _require_order_id(order_id)
        amount_units = _require_amount_units(amount_units)
        period = _require_period(period)
        # endregion

        # region 幂等记录订单权威
        with self._lock:
            current = self._orders.get(order_id)
            if current is None:
                self._orders[order_id] = {
                    "amount_units": amount_units,
                    "period": period,
                }
                return
            if (
                current["amount_units"] != amount_units
                or current["period"] != period
            ):
                raise ConsumedOrderConflict(
                    "the same order_id was recorded with a different amount or period"
                )
        # endregion

    def get_refundable_order(self, original_order_id: str) -> OriginalOrderSnapshot:
        original_order_id, record = self._read_order(original_order_id)
        # DEC-011 D5：上游发出且本系统已消费的订单即视为业务已批。
        return OriginalOrderSnapshot(
            original_order_id=original_order_id,
            amount_units=record["amount_units"],
            refundable=True,
        )

    def get_order_period(self, original_order_id: str) -> int:
        _, record = self._read_order(original_order_id)
        return record["period"]

    def purge_periods_before(self, period: int) -> None:
        period = _require_period(period)
        cutoff = period - 2
        # DEC-011 D5 只保留当期与上一期；等于 N-2 的订单已超出退款窗口。
        with self._lock:
            expired_order_ids = [
                order_id
                for order_id, record in self._orders.items()
                if record["period"] <= cutoff
            ]
            for order_id in expired_order_ids:
                del self._orders[order_id]

    def _read_order(self, original_order_id: str) -> tuple[str, Dict[str, int]]:
        original_order_id = _require_order_id(original_order_id)
        with self._lock:
            record = self._orders.get(original_order_id)
            if record is None:
                raise OriginalOrderUnavailable(
                    f"consumed original order is unavailable: {original_order_id}"
                )
            return original_order_id, dict(record)


class RedisConsumedOrderLedger:
    """使用 Redis Lua 原子维护 order_id 金额、周期与清理索引。"""

    _RECORD_SCRIPT = """
local order_key = KEYS[1]
local period_index_key = KEYS[2]
local order_id = ARGV[1]
local amount_units = ARGV[2]
local period = ARGV[3]

if redis.call('EXISTS', order_key) == 0 then
    redis.call('HSET', order_key, 'amount_units', amount_units, 'period', period)
    redis.call('ZADD', period_index_key, period, order_id)
    return 'RECORDED'
end

local stored_amount = redis.call('HGET', order_key, 'amount_units')
local stored_period = redis.call('HGET', order_key, 'period')
if stored_amount ~= amount_units or stored_period ~= period then
    return 'CONFLICT'
end
redis.call('ZADD', period_index_key, period, order_id)
return 'DUPLICATE_NOOP'
"""

    _READ_SCRIPT = """
local order_key = KEYS[1]
if redis.call('EXISTS', order_key) == 0 then
    return {'MISSING', '', ''}
end
return {
    'FOUND',
    redis.call('HGET', order_key, 'amount_units'),
    redis.call('HGET', order_key, 'period')
}
"""

    _PURGE_SCRIPT = """
local period_index_key = KEYS[1]
local order_key_prefix = ARGV[1]
local cutoff = ARGV[2]
local order_ids = redis.call('ZRANGEBYSCORE', period_index_key, '-inf', cutoff)
for _, order_id in ipairs(order_ids) do
    redis.call('DEL', order_key_prefix .. order_id)
end
if #order_ids > 0 then
    redis.call('ZREM', period_index_key, unpack(order_ids))
end
return #order_ids
"""

    def __init__(self, redis_conn: Any, *, key_prefix: str = "pvam:order_ledger:"):
        if redis_conn is None:
            raise TypeError("redis_conn is required")
        if not isinstance(key_prefix, str) or not key_prefix:
            raise TypeError("key_prefix must be a non-empty string")
        self._redis_conn = redis_conn
        self._key_prefix = key_prefix
        self._period_index_key = f"{key_prefix}__period_index__"

    def record_order(self, order_id: str, amount_units: int, period: int) -> None:
        # region 参数验证
        order_id = _require_order_id(order_id)
        amount_units = _require_amount_units(amount_units)
        period = _require_period(period)
        # endregion

        # region 原子记录订单与周期索引
        raw_result = self._redis_conn.eval(
            self._RECORD_SCRIPT,
            2,
            f"{self._key_prefix}{order_id}",
            self._period_index_key,
            order_id,
            str(amount_units),
            str(period),
        )
        disposition = self._decode(raw_result)
        if disposition == CONFLICT:
            raise ConsumedOrderConflict(
                "the same order_id conflicts with the Redis amount or period record"
            )
        if disposition not in {RECORDED, DUPLICATE_NOOP}:
            raise RuntimeError(
                f"Redis consumed order ledger returned an invalid disposition: {disposition!r}"
            )
        # endregion

    def get_refundable_order(self, original_order_id: str) -> OriginalOrderSnapshot:
        original_order_id, amount_units, _ = self._read_order(original_order_id)
        return OriginalOrderSnapshot(
            original_order_id=original_order_id,
            amount_units=amount_units,
            refundable=True,
        )

    def get_order_period(self, original_order_id: str) -> int:
        _, _, period = self._read_order(original_order_id)
        return period

    def purge_periods_before(self, period: int) -> None:
        period = _require_period(period)
        cutoff = period - 2
        raw_result = self._redis_conn.eval(
            self._PURGE_SCRIPT,
            1,
            self._period_index_key,
            self._key_prefix,
            str(cutoff),
        )
        try:
            deleted_count = int(self._decode(raw_result))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Redis consumed order purge returned an invalid count"
            ) from exc
        if deleted_count < 0:
            raise RuntimeError("Redis consumed order purge returned a negative count")

    def _read_order(self, original_order_id: str) -> tuple[str, int, int]:
        original_order_id = _require_order_id(original_order_id)
        raw_result = self._redis_conn.eval(
            self._READ_SCRIPT,
            1,
            f"{self._key_prefix}{original_order_id}",
        )
        if not isinstance(raw_result, (list, tuple)) or len(raw_result) != 3:
            raise RuntimeError("Redis consumed order lookup returned an invalid response")

        status = self._decode(raw_result[0])
        if status == MISSING:
            raise OriginalOrderUnavailable(
                f"consumed original order is unavailable: {original_order_id}"
            )
        if status != FOUND:
            raise RuntimeError(
                f"Redis consumed order lookup returned an invalid status: {status!r}"
            )
        try:
            amount_units = _require_amount_units(int(self._decode(raw_result[1])))
            period = _require_period(int(self._decode(raw_result[2])))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Redis consumed order lookup returned invalid amount or period data"
            ) from exc
        return original_order_id, amount_units, period

    @staticmethod
    def _decode(value: Any) -> Any:
        return value.decode("utf-8") if isinstance(value, bytes) else value
