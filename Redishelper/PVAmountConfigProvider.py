"""PVAM 金额版本开关的 Redis runtime Provider。

本模块属于 Redis infrastructure/config 层。它只负责原子读取、严格解析、
production run admission 与 run 内冻结；不查询 AR_CONFIG、不读取环境变量，
也不提供缺失配置的默认值或 stale cache。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Optional


# region Redis snapshot 合同

ACTIVE_POINTER_KEY = "pvam:amount_config:active"
SNAPSHOT_KEY_PREFIX = "pvam:amount_config:snapshot:"

READ_FIELD = "PV_AMOUNT_V2_READ"
WRITE_FIELD = "PV_AMOUNT_V2_WRITE"
VERSION_FIELD = "config_version"
LOAD_MODE_FIELD = "load_mode"
SOURCE_FIELD = "source"
CHECKSUM_FIELD = "checksum"

MANUAL_BOOTSTRAP_MODE = "MANUAL_BOOTSTRAP"
DELTA_SYNC_MODE = "DELTA_SYNC"
AR_CONFIG_SOURCE = "AR_CONFIG"

_CANONICAL_VERSION = re.compile(r"^(?:0|[1-9][0-9]*)$")
_CANONICAL_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")

# Redis 在同一个 Lua 执行边界内读取 active pointer 与 versioned snapshot。
# Provider 只接受该协议返回值，不使用 GET/HGET 的分步读取替代它。
LOAD_SNAPSHOT_LUA = r"""
-- PVAM_LOAD_SNAPSHOT_V1
local pointer = redis.call("GET", KEYS[1])
if not pointer then
    return {"ERR", "ACTIVE_SNAPSHOT_MISSING"}
end

local separator = string.find(pointer, ":", 1, true)
if not separator then
    return {"ERR", "ACTIVE_POINTER_INVALID"}
end

local version = string.sub(pointer, 1, separator - 1)
local checksum = string.sub(pointer, separator + 1)
if version == "" or checksum == "" then
    return {"ERR", "ACTIVE_POINTER_INVALID"}
end

local snapshot_key = ARGV[1] .. version
if redis.call("EXISTS", snapshot_key) == 0 then
    return {"ERR", "SNAPSHOT_MISSING"}
end

local fields = redis.call("HGETALL", snapshot_key)
local result = {"OK", pointer, snapshot_key}
for index = 1, #fields do
    result[#result + 1] = fields[index]
end
return result
"""

# endregion


# region 错误与 immutable run config


class PVAmountConfigError(RuntimeError):
    """所有配置合同错误的统一 fail-loud 异常。"""

    def __init__(self, code: str, detail: Optional[str] = None):
        self.code = str(code)
        self.detail = detail
        message = self.code if not detail else f"{self.code}: {detail}"
        super().__init__(message)


def _canonical_bool(value: bool) -> str:
    return "true" if value else "false"


def _require_canonical_version(value: str, *, error_code: str) -> int:
    if not _CANONICAL_VERSION.fullmatch(value):
        raise PVAmountConfigError(error_code, repr(value))
    return int(value)


def compute_snapshot_checksum(
        *,
        read_v2: bool,
        write_v2: bool,
        config_version: int,
        load_mode: str,
        source: str,
) -> str:
    """计算发布端/读取端一致性用 canonical SHA-256；它不是授权或 MAC。"""

    if type(read_v2) is not bool or type(write_v2) is not bool:
        raise PVAmountConfigError("INVALID_BOOL_TYPE")
    if type(config_version) is not int or config_version < 0:
        raise PVAmountConfigError("INVALID_CONFIG_VERSION")
    if not isinstance(load_mode, str) or not load_mode:
        raise PVAmountConfigError("INVALID_LOAD_MODE")
    if not isinstance(source, str) or not source:
        raise PVAmountConfigError("INVALID_SOURCE")

    payload = {
        READ_FIELD: _canonical_bool(read_v2),
        WRITE_FIELD: _canonical_bool(write_v2),
        VERSION_FIELD: str(config_version),
        LOAD_MODE_FIELD: load_mode,
        SOURCE_FIELD: source,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PVAmountRunConfig:
    """一次业务 run 使用的不可变金额版本配置。"""

    read_v2: bool
    write_v2: bool
    config_version: int
    load_mode: str
    source: str
    checksum: str

    def __post_init__(self) -> None:
        # region 数据验证
        if type(self.read_v2) is not bool or type(self.write_v2) is not bool:
            raise PVAmountConfigError("INVALID_BOOL_TYPE")
        if type(self.config_version) is not int or self.config_version < 0:
            raise PVAmountConfigError("INVALID_CONFIG_VERSION")
        if self.load_mode not in {MANUAL_BOOTSTRAP_MODE, DELTA_SYNC_MODE}:
            raise PVAmountConfigError("INVALID_LOAD_MODE", repr(self.load_mode))
        if self.source != AR_CONFIG_SOURCE:
            raise PVAmountConfigError("INVALID_SOURCE", repr(self.source))
        if not isinstance(self.checksum, str) or not _CANONICAL_CHECKSUM.fullmatch(
                self.checksum
        ):
            raise PVAmountConfigError("INVALID_CHECKSUM", repr(self.checksum))

        expected_checksum = compute_snapshot_checksum(
            read_v2=self.read_v2,
            write_v2=self.write_v2,
            config_version=self.config_version,
            load_mode=self.load_mode,
            source=self.source,
        )
        if self.checksum != expected_checksum:
            raise PVAmountConfigError("CHECKSUM_MISMATCH")
        # endregion

    @property
    def state(self) -> str:
        """返回正式四态编码：00、01、10 或 11。"""

        return f"{int(self.read_v2)}{int(self.write_v2)}"


# endregion


# region Provider 原子读取与严格解析


def _as_text(value: Any, *, error_code: str) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PVAmountConfigError(error_code, "non-UTF-8 Redis value") from exc
    if isinstance(value, str):
        return value
    raise PVAmountConfigError(error_code, f"unexpected type {type(value).__name__}")


def _parse_canonical_bool(value: str, *, field_name: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise PVAmountConfigError("INVALID_BOOL", f"{field_name}={value!r}")


def _resolve_redis_client(redis_client: Any = None) -> Any:
    """延迟复用项目唯一 Redis 连接，避免模块 import 时额外建连接。"""

    if redis_client is not None:
        return redis_client

    try:
        from Redishelper.BaseRedisModel import redis_conn
    except Exception as exc:  # pragma: no cover - 仅真实环境导入失败时触发
        raise PVAmountConfigError(
            "REDIS_UNAVAILABLE",
            f"default client import failed: {type(exc).__name__}",
        ) from exc
    return redis_conn


class PVAmountConfigProvider:
    """从 Redis 原子 snapshot 加载一次 immutable run config。"""

    def __init__(self, redis_client: Any = None):
        self._redis_client = redis_client

    def _client_for_io(self) -> Any:
        return _resolve_redis_client(self._redis_client)

    def load_run_config(self) -> PVAmountRunConfig:
        # region Redis 原子读取
        client = self._client_for_io()
        try:
            reply = client.eval(
                LOAD_SNAPSHOT_LUA,
                1,
                ACTIVE_POINTER_KEY,
                SNAPSHOT_KEY_PREFIX,
            )
        except PVAmountConfigError:
            raise
        except Exception as exc:
            raise PVAmountConfigError(
                "REDIS_UNAVAILABLE",
                f"{type(exc).__name__}: {exc}",
            ) from exc
        # endregion

        # region 原子协议验证
        if not isinstance(reply, (list, tuple)) or len(reply) < 2:
            raise PVAmountConfigError("ATOMIC_LOAD_PROTOCOL_INVALID")

        status = _as_text(reply[0], error_code="ATOMIC_LOAD_PROTOCOL_INVALID")
        if status == "ERR":
            code = _as_text(reply[1], error_code="ATOMIC_LOAD_PROTOCOL_INVALID")
            raise PVAmountConfigError(code)
        if status != "OK" or len(reply) < 3:
            raise PVAmountConfigError("ATOMIC_LOAD_PROTOCOL_INVALID")

        pointer = _as_text(reply[1], error_code="ACTIVE_POINTER_INVALID")
        snapshot_key = _as_text(reply[2], error_code="ATOMIC_LOAD_PROTOCOL_INVALID")
        flat_fields = list(reply[3:])
        if len(flat_fields) % 2 != 0:
            raise PVAmountConfigError("SNAPSHOT_INCOMPLETE")
        # endregion

        # region Snapshot 字段解析
        fields: dict[str, str] = {}
        for index in range(0, len(flat_fields), 2):
            field = _as_text(
                flat_fields[index],
                error_code="ATOMIC_LOAD_PROTOCOL_INVALID",
            )
            value = _as_text(
                flat_fields[index + 1],
                error_code="ATOMIC_LOAD_PROTOCOL_INVALID",
            )
            if field in fields:
                raise PVAmountConfigError("SNAPSHOT_DUPLICATE_FIELD", field)
            fields[field] = value

        required_codes = (
            (READ_FIELD, "READ_MISSING"),
            (WRITE_FIELD, "WRITE_MISSING"),
            (VERSION_FIELD, "CONFIG_VERSION_MISSING"),
            (LOAD_MODE_FIELD, "LOAD_MODE_MISSING"),
            (SOURCE_FIELD, "SOURCE_MISSING"),
            (CHECKSUM_FIELD, "CHECKSUM_MISSING"),
        )
        for field, code in required_codes:
            if field not in fields:
                raise PVAmountConfigError(code)
        # endregion

        # region Pointer/version/checksum 交叉验证
        if pointer.count(":") != 1:
            raise PVAmountConfigError("ACTIVE_POINTER_INVALID")
        pointer_version_text, pointer_checksum = pointer.split(":", 1)
        pointer_version = _require_canonical_version(
            pointer_version_text,
            error_code="ACTIVE_POINTER_INVALID",
        )
        if not _CANONICAL_CHECKSUM.fullmatch(pointer_checksum):
            raise PVAmountConfigError("ACTIVE_POINTER_INVALID")

        snapshot_version = _require_canonical_version(
            fields[VERSION_FIELD],
            error_code="INVALID_CONFIG_VERSION",
        )
        if snapshot_version != pointer_version:
            raise PVAmountConfigError("VERSION_MISMATCH")
        if snapshot_key != f"{SNAPSHOT_KEY_PREFIX}{pointer_version_text}":
            raise PVAmountConfigError("VERSION_MISMATCH")
        if fields[CHECKSUM_FIELD] != pointer_checksum:
            raise PVAmountConfigError("CHECKSUM_MISMATCH")
        # endregion

        # region Immutable run config
        return PVAmountRunConfig(
            read_v2=_parse_canonical_bool(
                fields[READ_FIELD],
                field_name=READ_FIELD,
            ),
            write_v2=_parse_canonical_bool(
                fields[WRITE_FIELD],
                field_name=WRITE_FIELD,
            ),
            config_version=snapshot_version,
            load_mode=fields[LOAD_MODE_FIELD],
            source=fields[SOURCE_FIELD],
            checksum=fields[CHECKSUM_FIELD],
        )
        # endregion


# endregion


# region Production admission 与 run-freeze


def admit_production_run_config(config: PVAmountRunConfig) -> None:
    """校验 production run 四态；允许 00/01/11，继续拒绝无效的 10。"""

    if not isinstance(config, PVAmountRunConfig):
        raise PVAmountConfigError("RUN_CONFIG_TYPE_INVALID")

    if config.read_v2 and not config.write_v2:
        raise PVAmountConfigError("INVALID_STATE")


@dataclass(frozen=True, slots=True)
class PVAmountRunSession:
    """业务处理开始前建立、随后不可刷新的一次性 run session。"""

    config: PVAmountRunConfig

    @classmethod
    def start(cls, provider: PVAmountConfigProvider) -> "PVAmountRunSession":
        # region 单次加载
        if not isinstance(provider, PVAmountConfigProvider):
            raise PVAmountConfigError("PROVIDER_TYPE_INVALID")
        config = provider.load_run_config()
        # endregion

        # region Production admission
        admit_production_run_config(config)
        # endregion

        # region Run 内冻结
        return cls(config=config)
        # endregion


# endregion


__all__ = [
    "ACTIVE_POINTER_KEY",
    "AR_CONFIG_SOURCE",
    "CHECKSUM_FIELD",
    "DELTA_SYNC_MODE",
    "LOAD_MODE_FIELD",
    "LOAD_SNAPSHOT_LUA",
    "MANUAL_BOOTSTRAP_MODE",
    "PVAmountConfigError",
    "PVAmountConfigProvider",
    "PVAmountRunConfig",
    "PVAmountRunSession",
    "READ_FIELD",
    "SNAPSHOT_KEY_PREFIX",
    "SOURCE_FIELD",
    "VERSION_FIELD",
    "WRITE_FIELD",
    "admit_production_run_config",
    "compute_snapshot_checksum",
]
