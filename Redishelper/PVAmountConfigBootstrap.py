"""PVAM 金额版本开关的 MANUAL_BOOTSTRAP 原子发布入口。"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from Redishelper.PVAmountConfigProvider import (
    ACTIVE_POINTER_KEY,
    AR_CONFIG_SOURCE,
    MANUAL_BOOTSTRAP_MODE,
    PVAmountConfigError,
    PVAmountConfigProvider,
    PVAmountRunConfig,
    SNAPSHOT_KEY_PREFIX,
    _resolve_redis_client,
    compute_snapshot_checksum,
)


# region Redis Lua CAS 合同

# 所有字段校验、旧版本比较、immutable snapshot 写入与 active pointer 切换
# 位于同一个 server-side 原子边界内。十进制版本按字符串比较，避免 Lua
# number 在 2^53 以上丢失精度。
PUBLISH_SNAPSHOT_LUA = r"""
-- PVAM_PUBLISH_SNAPSHOT_V1
local function canonical_decimal(value)
    if value == "0" then
        return value
    end
    if string.match(value, "^[1-9][0-9]*$") then
        return value
    end
    return nil
end

local function compare_decimal(left, right)
    if #left < #right then
        return -1
    end
    if #left > #right then
        return 1
    end
    if left < right then
        return -1
    end
    if left > right then
        return 1
    end
    return 0
end

local new_version = canonical_decimal(ARGV[2])
if not new_version then
    return {"ERR", "INVALID_CONFIG_VERSION"}
end

local active_pointer = redis.call("GET", KEYS[1])
if ARGV[3] == "INITIAL" then
    if active_pointer then
        return {"ERR", "STALE_CONFIG_VERSION"}
    end
else
    if not active_pointer then
        return {"ERR", "ACTIVE_SNAPSHOT_MISSING"}
    end

    local separator = string.find(active_pointer, ":", 1, true)
    if not separator then
        return {"ERR", "ACTIVE_POINTER_INVALID"}
    end

    local active_version = canonical_decimal(
        string.sub(active_pointer, 1, separator - 1)
    )
    local active_checksum = string.sub(active_pointer, separator + 1)
    if not active_version or string.len(active_checksum) ~= 64 or
       not string.match(active_checksum, "^[0-9a-f]+$") then
        return {"ERR", "ACTIVE_POINTER_INVALID"}
    end

    local expected_version = canonical_decimal(ARGV[3])
    if not expected_version or active_version ~= expected_version then
        return {"ERR", "STALE_CONFIG_VERSION"}
    end
    if compare_decimal(new_version, active_version) <= 0 then
        return {"ERR", "STALE_CONFIG_VERSION"}
    end
end

local snapshot_key = ARGV[1] .. new_version
if redis.call("EXISTS", snapshot_key) ~= 0 then
    return {"ERR", "SNAPSHOT_ALREADY_EXISTS"}
end

redis.call(
    "HSET",
    snapshot_key,
    "PV_AMOUNT_V2_READ", ARGV[4],
    "PV_AMOUNT_V2_WRITE", ARGV[5],
    "config_version", new_version,
    "load_mode", ARGV[6],
    "source", ARGV[7],
    "checksum", ARGV[8]
)
local new_pointer = new_version .. ":" .. ARGV[8]
redis.call("SET", KEYS[1], new_pointer)
return {"OK", new_pointer, snapshot_key}
"""

_EXPECTED_VERSION_UNSET = object()

# endregion


# region MANUAL_BOOTSTRAP 发布


def _require_version(value: Any, *, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise PVAmountConfigError("INVALID_CONFIG_VERSION", field_name)
    return value


def _parse_publish_reply(reply: Any) -> tuple[str, str]:
    if not isinstance(reply, (list, tuple)) or len(reply) < 2:
        raise PVAmountConfigError("ATOMIC_PUBLISH_PROTOCOL_INVALID")

    def as_text(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        if isinstance(value, str):
            return value
        raise PVAmountConfigError("ATOMIC_PUBLISH_PROTOCOL_INVALID")

    status = as_text(reply[0])
    if status == "ERR":
        raise PVAmountConfigError(as_text(reply[1]))
    if status != "OK" or len(reply) != 3:
        raise PVAmountConfigError("ATOMIC_PUBLISH_PROTOCOL_INVALID")
    return as_text(reply[1]), as_text(reply[2])


def publish_manual_bootstrap(
        config_version: int,
        *,
        expected_active_version: Any = _EXPECTED_VERSION_UNSET,
        redis_client: Any = None,
) -> PVAmountRunConfig:
    """原子发布当前批准的 01 snapshot，并执行 read-after-write verify。

    第一次发布必须显式传入 expected_active_version=None。后续发布必须
    显式传入调用方所批准的 active version；Lua 在原子边界内做 CAS。
    """

    # region 发布前验证
    config_version = _require_version(
        config_version,
        field_name="config_version",
    )
    if expected_active_version is _EXPECTED_VERSION_UNSET:
        raise PVAmountConfigError("EXPECTED_ACTIVE_VERSION_REQUIRED")

    if expected_active_version is None:
        expected_token = "INITIAL"
    else:
        expected_active_version = _require_version(
            expected_active_version,
            field_name="expected_active_version",
        )
        if config_version <= expected_active_version:
            raise PVAmountConfigError("STALE_CONFIG_VERSION")
        expected_token = str(expected_active_version)

    read_v2 = False
    write_v2 = True
    checksum = compute_snapshot_checksum(
        read_v2=read_v2,
        write_v2=write_v2,
        config_version=config_version,
        load_mode=MANUAL_BOOTSTRAP_MODE,
        source=AR_CONFIG_SOURCE,
    )
    # endregion

    # region Lua/CAS 原子发布
    client = _resolve_redis_client(redis_client)
    try:
        reply = client.eval(
            PUBLISH_SNAPSHOT_LUA,
            1,
            ACTIVE_POINTER_KEY,
            SNAPSHOT_KEY_PREFIX,
            str(config_version),
            expected_token,
            "false",
            "true",
            MANUAL_BOOTSTRAP_MODE,
            AR_CONFIG_SOURCE,
            checksum,
        )
    except PVAmountConfigError:
        raise
    except Exception as exc:
        raise PVAmountConfigError(
            "REDIS_UNAVAILABLE",
            f"{type(exc).__name__}: {exc}",
        ) from exc

    pointer, snapshot_key = _parse_publish_reply(reply)
    expected_pointer = f"{config_version}:{checksum}"
    expected_snapshot_key = f"{SNAPSHOT_KEY_PREFIX}{config_version}"
    if pointer != expected_pointer or snapshot_key != expected_snapshot_key:
        raise PVAmountConfigError("ATOMIC_PUBLISH_PROTOCOL_INVALID")
    # endregion

    # region Read-after-write verify
    verified = PVAmountConfigProvider(client).load_run_config()
    expected = PVAmountRunConfig(
        read_v2=read_v2,
        write_v2=write_v2,
        config_version=config_version,
        load_mode=MANUAL_BOOTSTRAP_MODE,
        source=AR_CONFIG_SOURCE,
        checksum=checksum,
    )
    if verified != expected:
        raise PVAmountConfigError("READ_AFTER_WRITE_VERIFY_FAILED")
    return verified
    # endregion


# endregion


# region CLI


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Atomically publish the approved PVAM 01 Redis snapshot.",
    )
    parser.add_argument(
        "--config-version",
        type=int,
        required=True,
        help="strictly monotonic non-negative integer revision",
    )
    expected = parser.add_mutually_exclusive_group(required=True)
    expected.add_argument(
        "--initial-create",
        action="store_true",
        help="require that no active snapshot exists",
    )
    expected.add_argument(
        "--expected-active-version",
        type=int,
        help="CAS against this active version",
    )
    return parser


def main(argv: Any = None) -> int:
    args = build_argument_parser().parse_args(argv)
    expected_active_version = (
        None if args.initial_create else args.expected_active_version
    )
    try:
        config = publish_manual_bootstrap(
            args.config_version,
            expected_active_version=expected_active_version,
        )
    except PVAmountConfigError as exc:
        print(f"PVAM_BOOTSTRAP_FAIL {exc}", file=sys.stderr)
        return 2

    print(
        "PVAM_BOOTSTRAP_PASS "
        f"state={config.state} config_version={config.config_version} "
        f"checksum={config.checksum}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# endregion


__all__ = [
    "PUBLISH_SNAPSHOT_LUA",
    "build_argument_parser",
    "main",
    "publish_manual_bootstrap",
]
