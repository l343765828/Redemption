"""PV 事件从待投递到三条增量链完成的持久状态机。"""

from __future__ import annotations

import threading
from typing import Any, Dict, Protocol


PENDING = "PENDING"
DISPATCHED = "DISPATCHED"
CONFLICT = "CONFLICT"
MISSING = "MISSING"


class DeliveryIdentityConflict(RuntimeError):
    """同一事件 identity 对应了不同 payload hash。"""


class DeliveryStateUnavailable(RuntimeError):
    """事件尚未建立 PENDING 状态，不能直接确认完成。"""


class PvEventDeliveryLedger(Protocol):
    def prepare_delivery(self, identity: str, payload_hash: str) -> str:
        ...

    def mark_dispatched(self, identity: str, payload_hash: str) -> str:
        ...


def _require_nonempty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


class InMemoryPvEventDeliveryLedger:
    """DEV 测试替身；线程锁只模拟单进程原子状态转换。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._deliveries: Dict[str, Dict[str, str]] = {}

    def prepare_delivery(self, identity: str, payload_hash: str) -> str:
        # region 参数验证
        identity = _require_nonempty_string(identity, field_name="identity")
        payload_hash = _require_nonempty_string(
            payload_hash,
            field_name="payload_hash",
        )
        # endregion

        # region 建立持久待投递状态
        with self._lock:
            current = self._deliveries.get(identity)
            if current is None:
                self._deliveries[identity] = {
                    "payload_hash": payload_hash,
                    "status": PENDING,
                }
                return PENDING
            if current["payload_hash"] != payload_hash:
                raise DeliveryIdentityConflict(
                    "the same delivery identity has a different payload hash"
                )
            return current["status"]
        # endregion

    def mark_dispatched(self, identity: str, payload_hash: str) -> str:
        # region 参数验证
        identity = _require_nonempty_string(identity, field_name="identity")
        payload_hash = _require_nonempty_string(
            payload_hash,
            field_name="payload_hash",
        )
        # endregion

        # region 确认三条增量链已完成
        with self._lock:
            current = self._deliveries.get(identity)
            if current is None:
                raise DeliveryStateUnavailable(
                    "delivery must be PENDING before it can be acknowledged"
                )
            if current["payload_hash"] != payload_hash:
                raise DeliveryIdentityConflict(
                    "the delivery acknowledgement payload hash conflicts"
                )
            current["status"] = DISPATCHED
            return DISPATCHED
        # endregion


class RedisPvEventDeliveryLedger:
    """使用 Redis Lua 原子维护 PENDING → DISPATCHED 投递状态。"""

    _PREPARE_SCRIPT = """
local key = KEYS[1]
local payload_hash = ARGV[1]

if redis.call('EXISTS', key) == 0 then
    redis.call('HSET', key, 'payload_hash', payload_hash, 'status', 'PENDING')
    return 'PENDING'
end

local stored_hash = redis.call('HGET', key, 'payload_hash')
if stored_hash ~= payload_hash then
    return 'CONFLICT'
end
return redis.call('HGET', key, 'status')
"""

    _ACK_SCRIPT = """
local key = KEYS[1]
local payload_hash = ARGV[1]

if redis.call('EXISTS', key) == 0 then
    return 'MISSING'
end

local stored_hash = redis.call('HGET', key, 'payload_hash')
if stored_hash ~= payload_hash then
    return 'CONFLICT'
end
redis.call('HSET', key, 'status', 'DISPATCHED')
return 'DISPATCHED'
"""

    def __init__(
        self,
        redis_conn: Any,
        *,
        key_prefix: str = "pvam:event_delivery:",
    ) -> None:
        if redis_conn is None:
            raise TypeError("redis_conn is required")
        if not isinstance(key_prefix, str) or not key_prefix:
            raise TypeError("key_prefix must be a non-empty string")
        self._redis_conn = redis_conn
        self._key_prefix = key_prefix

    def prepare_delivery(self, identity: str, payload_hash: str) -> str:
        identity = _require_nonempty_string(identity, field_name="identity")
        payload_hash = _require_nonempty_string(
            payload_hash,
            field_name="payload_hash",
        )
        raw_status = self._redis_conn.eval(
            self._PREPARE_SCRIPT,
            1,
            f"{self._key_prefix}{identity}",
            payload_hash,
        )
        return self._require_status(raw_status, allow_missing=False)

    def mark_dispatched(self, identity: str, payload_hash: str) -> str:
        identity = _require_nonempty_string(identity, field_name="identity")
        payload_hash = _require_nonempty_string(
            payload_hash,
            field_name="payload_hash",
        )
        raw_status = self._redis_conn.eval(
            self._ACK_SCRIPT,
            1,
            f"{self._key_prefix}{identity}",
            payload_hash,
        )
        return self._require_status(raw_status, allow_missing=True)

    @staticmethod
    def _require_status(raw_status: Any, *, allow_missing: bool) -> str:
        status = (
            raw_status.decode("utf-8")
            if isinstance(raw_status, bytes)
            else raw_status
        )
        if status == CONFLICT:
            raise DeliveryIdentityConflict(
                "delivery identity conflicts with the Redis payload hash"
            )
        if allow_missing and status == MISSING:
            raise DeliveryStateUnavailable(
                "delivery must be PENDING before it can be acknowledged"
            )
        if status not in {PENDING, DISPATCHED}:
            raise RuntimeError(
                f"Redis delivery ledger returned an invalid status: {status!r}"
            )
        return status
