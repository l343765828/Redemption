"""PVAM 期间解析的唯一公共合同。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence


class PeriodResolutionError(ValueError):
    """AR_PERIOD 无法唯一、完整地解析目标期间。"""


def _require_plain_int(value: Any, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be int, got {type(value).__name__}")
    return value


@dataclass(frozen=True)
class PeriodSnapshot:
    """一次业务处理使用的不可变 AR_PERIOD 快照。"""

    period_num: int
    calc_year: Optional[int]
    calc_month: Optional[int]
    first_period_num: int
    previous_period_num: Optional[int]
    source_checksum: str

    def __post_init__(self) -> None:
        _require_plain_int(self.period_num, field_name="period_num")
        if (self.calc_year is None) != (self.calc_month is None):
            raise PeriodResolutionError(
                "calc_year and calc_month must be both present or both None"
            )
        if self.calc_year is not None:
            _require_plain_int(self.calc_year, field_name="calc_year")
        if self.calc_month is not None:
            _require_plain_int(self.calc_month, field_name="calc_month")
        _require_plain_int(self.first_period_num, field_name="first_period_num")
        if self.previous_period_num is not None:
            _require_plain_int(
                self.previous_period_num,
                field_name="previous_period_num",
            )
        if self.calc_month is not None and not 1 <= self.calc_month <= 12:
            raise PeriodResolutionError("calc_month must be between 1 and 12")
        if self.first_period_num > self.period_num:
            raise PeriodResolutionError(
                "first_period_num cannot be greater than period_num"
            )
        if self.period_num == self.first_period_num:
            if self.previous_period_num is not None:
                raise PeriodResolutionError(
                    "the first AR_PERIOD row cannot have a previous period"
                )
        elif self.previous_period_num is None:
            raise PeriodResolutionError(
                "a non-first AR_PERIOD row must reference a real previous row"
            )
        elif not self.first_period_num <= self.previous_period_num < self.period_num:
            raise PeriodResolutionError(
                "previous_period_num must reference an earlier AR_PERIOD row"
            )
        if not isinstance(self.source_checksum, str) or not self.source_checksum:
            raise TypeError("source_checksum must be a non-empty string")


class PeriodRepository(Protocol):
    """数据库适配器合同；具体 ORM/驱动由部署层实现。"""

    def resolve_current(self, period_num: int) -> PeriodSnapshot:
        ...

class PeriodResolver:
    """校验 repository 按消息期号返回的不可变期间快照。"""

    def __init__(self, repository: PeriodRepository):
        if repository is None:
            raise TypeError("period repository is required")
        self._repository = repository

    def resolve_current(self, period_num: int) -> PeriodSnapshot:
        period_num = _require_plain_int(period_num, field_name="period_num")
        snapshot = self._require_snapshot(
            self._repository.resolve_current(period_num)
        )
        if snapshot.period_num != period_num:
            raise PeriodResolutionError(
                "repository returned a snapshot for a different period"
            )
        return snapshot

    @staticmethod
    def _require_snapshot(value: Any) -> PeriodSnapshot:
        if not isinstance(value, PeriodSnapshot):
            raise TypeError("period repository must return PeriodSnapshot")
        return value


class ContractPeriodRepository:
    """DEC-020 消息周期适配器；生产归期只读取消息中的整数 period。"""

    def resolve_current(self, period_num: int) -> PeriodSnapshot:
        period_num = _require_plain_int(period_num, field_name="period_num")
        if period_num < 1:
            raise PeriodResolutionError("period_num must be greater than or equal to 1")

        # 功能性合同标识沿用初始编号；修改会改变既有 source_checksum。
        checksum_payload = {
            "contract": "DEC-011",
            "period": period_num,
        }
        source_checksum = hashlib.sha256(
            json.dumps(
                checksum_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return PeriodSnapshot(
            period_num=period_num,
            calc_year=None,
            calc_month=None,
            first_period_num=1,
            previous_period_num=period_num - 1 if period_num > 1 else None,
            source_checksum=source_checksum,
        )

class MappingPeriodRepository:
    """用于 DEV/测试的确定性 AR_PERIOD 行适配器。

    仅按唯一 PERIOD_NUM 构造快照；本适配器不连接数据库，也不承担生产归期。
    """

    def __init__(self, rows: Iterable[Mapping[str, Any]]):
        self._rows = tuple(self._normalize_row(row) for row in rows)
        if not self._rows:
            raise PeriodResolutionError("AR_PERIOD rows cannot be empty")

    def resolve_current(self, period_num: int) -> PeriodSnapshot:
        period_num = _require_plain_int(period_num, field_name="period_num")
        matches = [row for row in self._rows if row["period_num"] == period_num]
        return self._snapshot_from_unique(matches, lookup=f"period_num={period_num}")

    def _snapshot_from_unique(
        self,
        matches: Sequence[Mapping[str, int]],
        *,
        lookup: str,
    ) -> PeriodSnapshot:
        if len(matches) != 1:
            raise PeriodResolutionError(
                f"AR_PERIOD lookup must return exactly one row ({lookup}); got {len(matches)}"
            )

        current = matches[0]
        period_nums = sorted(row["period_num"] for row in self._rows)
        if len(period_nums) != len(set(period_nums)):
            raise PeriodResolutionError("AR_PERIOD PERIOD_NUM must be unique")

        first_period_num = period_nums[0]
        earlier = [value for value in period_nums if value < current["period_num"]]
        previous_period_num = max(earlier) if earlier else None
        checksum_payload = {
            "current": current,
            "first_period_num": first_period_num,
            "previous_period_num": previous_period_num,
        }
        source_checksum = hashlib.sha256(
            json.dumps(
                checksum_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return PeriodSnapshot(
            period_num=current["period_num"],
            calc_year=current["calc_year"],
            calc_month=current["calc_month"],
            first_period_num=first_period_num,
            previous_period_num=previous_period_num,
            source_checksum=source_checksum,
        )

    @classmethod
    def _normalize_row(cls, row: Mapping[str, Any]) -> Mapping[str, int]:
        if not isinstance(row, Mapping):
            raise TypeError("each AR_PERIOD row must be a mapping")
        return {
            "period_num": cls._read_int(row, "period_num", "PERIOD_NUM"),
            "calc_year": cls._read_int(row, "calc_year", "CALC_YEAR"),
            "calc_month": cls._read_int(row, "calc_month", "CALC_MONTH"),
        }

    @staticmethod
    def _read_int(row: Mapping[str, Any], lower: str, upper: str) -> int:
        if lower in row:
            value = row[lower]
        elif upper in row:
            value = row[upper]
        else:
            raise PeriodResolutionError(f"AR_PERIOD row is missing {upper}")
        return _require_plain_int(value, field_name=upper)
