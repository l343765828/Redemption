from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping

from Common.PvAmount import RATE_PPM_SCALE, require_int64


BONUS_CONFIG_SNAPSHOT_V2 = "BONUS_CONFIG_SNAPSHOT_V2"
CONFIG_REQUIREMENTS_VERSION = "PVAM-CONFIG-REQUIREMENTS-v1"

_CANONICAL_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_PERCENT_TO_PPM = RATE_PPM_SCALE // 100


class MissingPolicy(str, Enum):
    ZERO = "ZERO"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class ConfigRequirement:
    """单个奖项配置键的读取合同，不承载任何业务默认值。"""

    config_name: str
    type_exact: str | None
    missing_policy: MissingPolicy
    duplicate_is_error: bool
    exact_raw_name: bool = False
    exact_raw_type: bool = False
    allow_negative: bool = True
    value_encoding: str = "PERCENT_PPM"

    @property
    def is_prefix(self) -> bool:
        return self.config_name.endswith("*")

    @property
    def name_token(self) -> str:
        return self.config_name[:-1] if self.is_prefix else self.config_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_name": self.config_name,
            "type_exact": self.type_exact,
            "missing_policy": self.missing_policy.value,
            "duplicate_is_error": self.duplicate_is_error,
            "exact_raw_name": self.exact_raw_name,
            "exact_raw_type": self.exact_raw_type,
            "allow_negative": self.allow_negative,
            "value_encoding": self.value_encoding,
        }


# SQL 中 MIN/IFNULL 或 LEFT JOIN 明确给出缺失为 0 的键使用 ZERO。Country
# 行不属于费率，且 SE 与 EAB/LB 分别保留 exact-raw 和上游校验豁免语义。
CONFIG_REQUIREMENT_MATRIX: Mapping[str, tuple[ConfigRequirement, ...]] = MappingProxyType({
    "PE": (
        ConfigRequirement("proEliteRate", "bonus", MissingPolicy.ZERO, False),
    ),
    "ELITE": (
        ConfigRequirement("eliteRate", "bonus", MissingPolicy.ZERO, False),
    ),
    "SE": (
        ConfigRequirement(
            "superEliteRate", "bonus", MissingPolicy.ZERO, False,
            exact_raw_name=True, exact_raw_type=True,
        ),
        ConfigRequirement(
            "Country*", "bonus", MissingPolicy.ZERO, True,
            exact_raw_name=True, exact_raw_type=True, value_encoding="RAW",
        ),
    ),
    "EAB": (
        ConfigRequirement("eabRate", "bonus", MissingPolicy.ZERO, False),
        ConfigRequirement(
            "Country*", "bonus", MissingPolicy.ZERO, False,
            value_encoding="RAW",
        ),
    ),
    "LB": (
        ConfigRequirement("leadershipRate*", "bonus", MissingPolicy.ZERO, False),
        ConfigRequirement(
            "Country*", "bonus", MissingPolicy.ZERO, False,
            value_encoding="RAW",
        ),
    ),
    "TB": (
        ConfigRequirement("teamBisectRate", "bonus", MissingPolicy.ZERO, False),
        ConfigRequirement("teamTouchRate*", "bonus", MissingPolicy.ZERO, False),
        ConfigRequirement(
            "teamTouchCapping*", "bonus", MissingPolicy.ZERO, False,
            value_encoding="DECIMAL",
        ),
    ),
})


def parse_signed_percent_to_ppm(raw: Decimal | str) -> int:
    """把 AR_CONFIG 百分数原值精确转换为 signed ppm。

    这里只实施十进制格式、ppm 精度和 int64 技术边界。业务最大值由上游
    管理，不在本解析器中新增二次上限。
    """
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, str) and _CANONICAL_DECIMAL.fullmatch(raw):
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError("config percent is not a decimal") from exc
    else:
        raise TypeError("config percent must be Decimal or canonical decimal string")

    if not value.is_finite():
        raise ValueError("config percent must be finite")

    scaled = value * _PERCENT_TO_PPM
    if scaled != scaled.to_integral_value():
        raise ValueError("config percent has precision finer than ppm")

    return require_int64(int(scaled), field_name="config_rate_ppm")


@dataclass(frozen=True, slots=True)
class ConfigRow:
    """保留业务字段原值的不可变配置行。"""

    fields: tuple[tuple[str, Any], ...]

    def get(self, key: str, default: Any = None) -> Any:
        normalized = key.lower()
        for field, value in self.fields:
            if field == normalized:
                return value
        return default

    def to_dict(self) -> dict[str, Any]:
        return dict(self.fields)


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    """单次奖金 run 使用的不可变配置快照。"""

    period_num: int | str | None
    calc_month: int | None
    source: str
    source_version: str
    loaded_at: str
    raw_row_count: int
    raw_rows_checksum: str
    requirements_version: str
    canonical_values: tuple[tuple[str, str, str], ...]
    canonical_checksum: str
    snapshot_id: str
    _rows: tuple[ConfigRow, ...]

    @classmethod
    def from_rows(
        cls,
        rows: Any,
        *,
        period_num: int | str | None = None,
        calc_month: int | None = None,
        source: str = "controlled-fixture",
        source_version: str = "unversioned",
        loaded_at: str | None = None,
        requirements_version: str = CONFIG_REQUIREMENTS_VERSION,
    ) -> "ConfigSnapshot":
        frozen_rows = _freeze_rows(rows)
        raw_tokens = sorted(_stable_row_token(row) for row in frozen_rows)
        raw_checksum = _sha256_json(raw_tokens)

        canonical_values = tuple(sorted(
            (
                _canonical_text(row.get("config_name")),
                _canonical_text(row.get("type")),
                _canonical_text(row.get("value")),
            )
            for row in frozen_rows
        ))
        canonical_checksum = _sha256_json(canonical_values)
        snapshot_id = _sha256_json({
            "period_num": period_num,
            "calc_month": calc_month,
            "source": source,
            "source_version": source_version,
            "raw_rows_checksum": raw_checksum,
            "requirements_version": requirements_version,
            "canonical_checksum": canonical_checksum,
        })

        return cls(
            period_num=period_num,
            calc_month=calc_month,
            source=str(source),
            source_version=str(source_version),
            loaded_at=loaded_at or datetime.now(timezone.utc).isoformat(),
            raw_row_count=len(frozen_rows),
            raw_rows_checksum=raw_checksum,
            requirements_version=str(requirements_version),
            canonical_values=canonical_values,
            canonical_checksum=canonical_checksum,
            snapshot_id=snapshot_id,
            _rows=frozen_rows,
        )

    @property
    def checksum(self) -> str:
        """兼容施工单示例；配置消费者应记录 canonical checksum。"""
        return self.canonical_checksum

    @property
    def raw_rows(self) -> tuple[ConfigRow, ...]:
        return self._rows

    def assert_run(self, period_num: int | str, calc_month: int | None = None) -> None:
        if self.period_num is not None and str(self.period_num) != str(period_num):
            raise ValueError(
                f"config snapshot period mismatch: {self.period_num!r} != {period_num!r}"
            )
        if (
            calc_month is not None
            and self.calc_month is not None
            and int(self.calc_month) != int(calc_month)
        ):
            raise ValueError(
                f"config snapshot calc_month mismatch: {self.calc_month!r} != {calc_month!r}"
            )

    def requirement(self, award: str, config_name: str) -> ConfigRequirement:
        award_key = str(award).upper()
        requirements = CONFIG_REQUIREMENT_MATRIX.get(award_key)
        if requirements is None:
            raise KeyError(f"unknown config award: {award}")
        for requirement in requirements:
            if requirement.is_prefix:
                if config_name.startswith(requirement.name_token):
                    return requirement
            elif requirement.config_name == config_name:
                return requirement
        raise KeyError(f"{config_name!r} is not declared for award {award_key}")

    def rows_for(self, requirement: ConfigRequirement) -> tuple[ConfigRow, ...]:
        matches = tuple(row for row in self._rows if _row_matches(row, requirement))
        if requirement.duplicate_is_error:
            counts: dict[str, int] = {}
            for row in matches:
                raw_name = row.get("config_name")
                duplicate_key = (
                    raw_name
                    if requirement.exact_raw_name
                    else raw_name.strip().casefold()
                )
                counts[duplicate_key] = counts.get(duplicate_key, 0) + 1
            duplicates = sorted(name for name, count in counts.items() if count > 1)
            if duplicates:
                raise ValueError(
                    f"duplicate config rows for {requirement.config_name}: {duplicates}"
                )
        return matches

    def require_ppm(self, config_name: str, *, award: str | None = None) -> int:
        requirement = (
            self.requirement(award, config_name)
            if award is not None
            else _find_unique_requirement(config_name)
        )
        if requirement.value_encoding != "PERCENT_PPM":
            raise TypeError(f"{config_name} is not a percent configuration")

        matches = self.rows_for(requirement)
        if not matches:
            if requirement.missing_policy is MissingPolicy.ZERO:
                return 0
            raise KeyError(f"required config is missing: {config_name}")

        values = [parse_signed_percent_to_ppm(row.get("value")) for row in matches]
        result = min(values) if len(values) > 1 else values[0]
        if result < 0 and not requirement.allow_negative:
            raise ValueError(f"negative config is not allowed: {config_name}")
        return result

    def rate_decimal(self, config_name: str, *, award: str | None = None) -> Decimal:
        return Decimal(self.require_ppm(config_name, award=award)) / Decimal(RATE_PPM_SCALE)

    def iter_ppm_rows(self, award: str, config_name_pattern: str) -> tuple[tuple[str, int], ...]:
        requirement = self.requirement(award, config_name_pattern)
        if requirement.value_encoding != "PERCENT_PPM":
            raise TypeError(f"{config_name_pattern} is not a percent configuration")
        result = []
        for row in self.rows_for(requirement):
            name = row.get("config_name")
            if not isinstance(name, str):
                raise TypeError("config_name must be a string")
            ppm = parse_signed_percent_to_ppm(row.get("value"))
            if ppm < 0 and not requirement.allow_negative:
                raise ValueError(f"negative config is not allowed: {name}")
            if requirement.exact_raw_name:
                canonical_name = name
            else:
                normalized_name = name.strip()
                suffix = normalized_name[len(requirement.name_token):]
                canonical_name = f"{requirement.name_token}{suffix}"
            result.append((canonical_name, ppm))
        return tuple(result)

    def country_rows(self, award: str) -> tuple[dict[str, Any], ...]:
        requirement = self.requirement(award, "Country*")
        result = []
        for row in self.rows_for(requirement):
            record = row.to_dict()
            if not requirement.exact_raw_name:
                raw_name = record["config_name"].strip()
                suffix = raw_name[len(requirement.name_token):]
                record["config_name"] = f"{requirement.name_token}{suffix}"
            if requirement.type_exact is not None and not requirement.exact_raw_type:
                record["type"] = requirement.type_exact
            result.append(record)
        return tuple(result)

    def to_records(self) -> list[dict[str, Any]]:
        return [row.to_dict() for row in self._rows]

    def to_pandas(self, *, uppercase_columns: bool = False):
        import pandas as pd

        records = self.to_records()
        if records:
            frame = pd.DataFrame(records)
        else:
            frame = pd.DataFrame(columns=["config_name", "type", "value"])
        if uppercase_columns:
            frame = frame.rename(columns=str.upper)
        return frame

    def manifest(self) -> dict[str, Any]:
        return {
            "period_num": self.period_num,
            "calc_month": self.calc_month,
            "source": self.source,
            "source_version": self.source_version,
            "loaded_at": self.loaded_at,
            "raw_row_count": self.raw_row_count,
            "raw_rows_checksum": self.raw_rows_checksum,
            "requirements_version": self.requirements_version,
            "canonical_values": [list(value) for value in self.canonical_values],
            "canonical_checksum": self.canonical_checksum,
            "snapshot_id": self.snapshot_id,
        }


class ConfigSnapshotLoader:
    """从调用方提供的只读行源加载一次快照；本类不连接 MySQL。"""

    def __init__(self, source: Any | Callable[[], Any]):
        self._source = source

    def load(
        self,
        *,
        period_num: int | str | None = None,
        calc_month: int | None = None,
        source: str = "controlled-fixture",
        source_version: str = "unversioned",
    ) -> ConfigSnapshot:
        rows = self._source() if callable(self._source) else self._source
        return ConfigSnapshot.from_rows(
            rows,
            period_num=period_num,
            calc_month=calc_month,
            source=source,
            source_version=source_version,
        )


def ensure_config_snapshot(
    value: ConfigSnapshot | Any,
    *,
    period_num: int | str | None = None,
    calc_month: int | None = None,
    source: str = "legacy-dataframe-fixture",
) -> ConfigSnapshot:
    """把受控 fixture 适配为快照；生产编排应直接传入同一个 snapshot。"""
    if isinstance(value, ConfigSnapshot):
        if period_num is not None:
            value.assert_run(period_num, calc_month)
        return value
    return ConfigSnapshot.from_rows(
        value,
        period_num=period_num,
        calc_month=calc_month,
        source=source,
    )


def requirement_matrix_manifest() -> dict[str, list[dict[str, Any]]]:
    return {
        award: [requirement.to_dict() for requirement in requirements]
        for award, requirements in CONFIG_REQUIREMENT_MATRIX.items()
    }


def _find_unique_requirement(config_name: str) -> ConfigRequirement:
    found = []
    for requirements in CONFIG_REQUIREMENT_MATRIX.values():
        for requirement in requirements:
            if not requirement.is_prefix and requirement.config_name == config_name:
                found.append(requirement)
    if len(found) != 1:
        raise KeyError(f"config requirement is not uniquely declared: {config_name}")
    return found[0]


def _row_matches(row: ConfigRow, requirement: ConfigRequirement) -> bool:
    raw_name = row.get("config_name")
    raw_type = row.get("type")
    if not isinstance(raw_name, str):
        return False

    name = raw_name if requirement.exact_raw_name else raw_name.strip().casefold()
    token = (
        requirement.name_token
        if requirement.exact_raw_name
        else requirement.name_token.casefold()
    )
    name_matches = name.startswith(token) if requirement.is_prefix else name == token
    if not name_matches:
        return False

    if requirement.type_exact is None:
        return True
    if not isinstance(raw_type, str):
        return False
    actual_type = raw_type if requirement.exact_raw_type else raw_type.strip().casefold()
    expected_type = (
        requirement.type_exact
        if requirement.exact_raw_type
        else requirement.type_exact.casefold()
    )
    return actual_type == expected_type


def _freeze_rows(rows: Any) -> tuple[ConfigRow, ...]:
    if hasattr(rows, "to_pandas"):
        rows = rows.to_pandas()
    if hasattr(rows, "compute"):
        rows = rows.compute()
    if hasattr(rows, "to_dict") and not isinstance(rows, Mapping):
        try:
            rows = rows.to_dict(orient="records")
        except TypeError:
            rows = rows.to_dict("records")

    if isinstance(rows, Mapping):
        rows = [rows]
    try:
        source_rows = list(rows)
    except TypeError as exc:
        raise TypeError("config rows must be an iterable of mappings") from exc

    frozen = []
    for index, source_row in enumerate(source_rows):
        if not isinstance(source_row, Mapping):
            raise TypeError(f"config row {index} must be a mapping")
        normalized: dict[str, Any] = {}
        for key, value in source_row.items():
            normalized_key = str(key).lower()
            if normalized_key in normalized:
                raise ValueError(
                    f"config row {index} has duplicate case-insensitive column {normalized_key!r}"
                )
            normalized[normalized_key] = _freeze_value(value)
        missing = {"config_name", "type", "value"} - set(normalized)
        if missing:
            raise ValueError(f"config row {index} misses columns: {sorted(missing)}")
        frozen.append(ConfigRow(tuple(sorted(normalized.items()))))
    return tuple(frozen)


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _freeze_value(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (str, int, bool, Decimal)) or value is None:
        return value
    if isinstance(value, float):
        return value
    if hasattr(value, "item"):
        try:
            return _freeze_value(value.item())
        except (TypeError, ValueError):
            pass
    return value


def _stable_row_token(row: ConfigRow) -> str:
    return json.dumps(
        [(key, _typed_json_value(value)) for key, value in row.fields],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _typed_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": format(value, "f")}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": repr(value)}
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, tuple):
        return {"type": "tuple", "value": [_typed_json_value(item) for item in value]}
    return {"type": type(value).__name__, "value": repr(value)}


def _canonical_text(value: Any) -> str:
    return json.dumps(_typed_json_value(value), ensure_ascii=False, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
