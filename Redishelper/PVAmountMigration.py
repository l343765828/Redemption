"""PVAM V2 金额记录的显式、逐记录迁移入口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from Common.PvAmount import AMOUNT_ENCODING_VERSION_V2


# 延迟加载避免仅导入迁移工具时初始化 Redis 模型连接；测试可注入精确模型替身。
UserStats: Any = None
EliteBonusStats: Any = None


INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1

USER_STATS_AMOUNT_FIELDS = (
    "pv",
    "gpv",
    "gpv_real",
    "gpv_unreal",
    "contrib",
    "pv_1l",
    "pv_2l",
    "pre_surplus_1l",
    "pre_surplus_2l",
    "total_1l",
    "total_2l",
    "remain_surplus_1l",
    "remain_surplus_2l",
)

ELITE_BONUS_AMOUNT_FIELDS = (
    "pv_pcs",
    "gpv",
    "gpv_real",
    "contrib_to_parent",
)


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """单条迁移的脱敏结果；不包含连接信息或完整业务金额。"""

    record_type: str
    record_id: str
    period: str
    mode: str
    status: str
    code: str
    before_version: Any
    after_version: Any


def _normalize_target(period: object, record_id: object) -> tuple[str, str]:
    # region 精确目标验证
    if isinstance(period, bool) or not isinstance(period, (int, str)):
        raise ValueError("period must be an explicit positive integer")
    period_text = str(period)
    if not period_text.isdigit() or int(period_text) < 1:
        raise ValueError("period must be an explicit positive integer")
    if not isinstance(record_id, str) or not record_id:
        raise ValueError("record_id must be a non-empty exact model id")
    record_prefix = f"{period_text}:"
    if not record_id.startswith(record_prefix):
        raise ValueError("record_id does not belong to the explicit period")
    if len(record_id) == len(record_prefix):
        raise ValueError("record_id must include the exact record suffix")
    return period_text, record_id
    # endregion


def _mode(apply: object) -> str:
    if type(apply) is not bool:
        raise TypeError("apply must be an explicit bool")
    return "APPLY" if apply else "DRY_RUN"


def _resolve_user_stats_model() -> Any:
    if UserStats is not None:
        return UserStats
    from Model.User.UserStats import UserStats as model
    return model


def _resolve_elite_bonus_stats_model() -> Any:
    if EliteBonusStats is not None:
        return EliteBonusStats
    from Model.User.EliteBonusStats import EliteBonusStats as model
    return model


def _is_not_found(exc: Exception) -> bool:
    from redis_om import NotFoundError
    return isinstance(exc, NotFoundError)


def _validate_int64_fields(record: object, fields: Iterable[str]) -> str | None:
    # region 金额类型与边界验证
    for field in fields:
        value = getattr(record, field, None)
        if type(value) is not int:
            return f"INVALID_AMOUNT_FIELD:{field}"
        if value < INT64_MIN or value > INT64_MAX:
            return f"INT64_OUT_OF_RANGE:{field}"
    return None
    # endregion


def _fingerprint(record: object, fields: Iterable[str]) -> tuple[Any, ...]:
    return (
        getattr(record, "amount_encoding_version", None),
        *(getattr(record, field, None) for field in fields),
    )


def _result(
    record_type: str,
    record_id: str,
    period: str,
    mode: str,
    status: str,
    code: str,
    before_version: Any,
    after_version: Any,
) -> MigrationResult:
    return MigrationResult(
        record_type=record_type,
        record_id=record_id,
        period=period,
        mode=mode,
        status=status,
        code=code,
        before_version=before_version,
        after_version=after_version,
    )


def migrate_user_stats_record(
    period: object,
    record_id: object,
    *,
    apply: bool = False,
) -> MigrationResult:
    """验证并可选迁移一条精确指定的 UserStats；默认不写入。"""

    period_text, record_id_text = _normalize_target(period, record_id)
    mode = _mode(apply)

    # region 首次读取与完整验证
    model = _resolve_user_stats_model()
    try:
        record = model.get(record_id_text)
    except Exception as exc:
        if not _is_not_found(exc):
            raise
        return _result("UserStats", record_id_text, period_text, mode, "REJECTED", "NOT_FOUND", None, None)

    before_version = getattr(record, "amount_encoding_version", None)
    if str(getattr(record, "period", "")) != period_text:
        return _result("UserStats", record_id_text, period_text, mode, "REJECTED", "PERIOD_MISMATCH", before_version, before_version)
    invalid_code = _validate_int64_fields(record, USER_STATS_AMOUNT_FIELDS)
    if invalid_code:
        return _result("UserStats", record_id_text, period_text, mode, "REJECTED", invalid_code, before_version, before_version)
    if before_version == AMOUNT_ENCODING_VERSION_V2:
        return _result("UserStats", record_id_text, period_text, mode, "ALREADY_V2", "ALREADY_V2", before_version, before_version)
    if before_version is not None:
        return _result("UserStats", record_id_text, period_text, mode, "REJECTED", "INCOMPATIBLE_VERSION", before_version, before_version)
    initial_fingerprint = _fingerprint(record, USER_STATS_AMOUNT_FIELDS)
    # endregion

    if not apply:
        return _result("UserStats", record_id_text, period_text, mode, "READY", "READY", before_version, AMOUNT_ENCODING_VERSION_V2)

    # region 写入前重新读取，禁止覆盖并发变化
    try:
        fresh = model.get(record_id_text)
    except Exception as exc:
        if not _is_not_found(exc):
            raise
        return _result("UserStats", record_id_text, period_text, mode, "REJECTED", "STALE_RECORD", before_version, before_version)
    if str(getattr(fresh, "period", "")) != period_text:
        return _result("UserStats", record_id_text, period_text, mode, "REJECTED", "STALE_RECORD", before_version, getattr(fresh, "amount_encoding_version", None))
    if _fingerprint(fresh, USER_STATS_AMOUNT_FIELDS) != initial_fingerprint:
        return _result("UserStats", record_id_text, period_text, mode, "REJECTED", "STALE_RECORD", before_version, getattr(fresh, "amount_encoding_version", None))
    invalid_code = _validate_int64_fields(fresh, USER_STATS_AMOUNT_FIELDS)
    if invalid_code:
        return _result("UserStats", record_id_text, period_text, mode, "REJECTED", invalid_code, before_version, before_version)
    fresh.amount_encoding_version = AMOUNT_ENCODING_VERSION_V2
    fresh.save()
    # endregion

    return _result("UserStats", record_id_text, period_text, mode, "MIGRATED", "MIGRATED", before_version, AMOUNT_ENCODING_VERSION_V2)


def migrate_elite_bonus_stats_record(
    period: object,
    record_id: object,
    *,
    apply: bool = False,
) -> MigrationResult:
    """验证并可选迁移一条精确指定的 EliteBonusStats；默认不写入。"""

    period_text, record_id_text = _normalize_target(period, record_id)
    mode = _mode(apply)

    # region 首次读取与整数业绩验证
    model = _resolve_elite_bonus_stats_model()
    try:
        record = model.get(record_id_text)
    except Exception as exc:
        if not _is_not_found(exc):
            raise
        return _result("EliteBonusStats", record_id_text, period_text, mode, "REJECTED", "NOT_FOUND", None, None)

    before_version = getattr(record, "amount_encoding_version", None)
    if str(getattr(record, "period_num", "")) != period_text:
        return _result("EliteBonusStats", record_id_text, period_text, mode, "REJECTED", "PERIOD_MISMATCH", before_version, before_version)
    invalid_code = _validate_int64_fields(record, ELITE_BONUS_AMOUNT_FIELDS)
    if invalid_code:
        return _result("EliteBonusStats", record_id_text, period_text, mode, "REJECTED", invalid_code, before_version, before_version)

    legacy_bonus = getattr(record, "estimated_bonus", None)
    bonus_cents = getattr(record, "estimated_bonus_cents", None)
    if before_version == AMOUNT_ENCODING_VERSION_V2:
        cents_code = _validate_int64_fields(record, ("estimated_bonus_cents",))
        if cents_code or legacy_bonus is not None:
            return _result("EliteBonusStats", record_id_text, period_text, mode, "REJECTED", cents_code or "INVALID_V2_LEGACY_BONUS", before_version, before_version)
        return _result("EliteBonusStats", record_id_text, period_text, mode, "ALREADY_V2", "ALREADY_V2", before_version, before_version)
    if before_version is not None:
        return _result("EliteBonusStats", record_id_text, period_text, mode, "REJECTED", "INCOMPATIBLE_VERSION", before_version, before_version)
    if isinstance(legacy_bonus, bool) or not (
        legacy_bonus is None
        or (type(legacy_bonus) in {int, float} and legacy_bonus == 0)
    ):
        return _result("EliteBonusStats", record_id_text, period_text, mode, "RECALC_REQUIRED", "LEGACY_BONUS_NONZERO", before_version, before_version)
    if bonus_cents not in {None, 0} or isinstance(bonus_cents, bool):
        return _result("EliteBonusStats", record_id_text, period_text, mode, "REJECTED", "LEGACY_CENTS_NONZERO", before_version, before_version)
    initial_fingerprint = _fingerprint(
        record,
        (*ELITE_BONUS_AMOUNT_FIELDS, "estimated_bonus", "estimated_bonus_cents"),
    )
    # endregion

    if not apply:
        return _result("EliteBonusStats", record_id_text, period_text, mode, "READY", "READY", before_version, AMOUNT_ENCODING_VERSION_V2)

    # region 写入前重新读取，禁止猜测或覆盖奖金变化
    try:
        fresh = model.get(record_id_text)
    except Exception as exc:
        if not _is_not_found(exc):
            raise
        return _result("EliteBonusStats", record_id_text, period_text, mode, "REJECTED", "STALE_RECORD", before_version, before_version)
    if str(getattr(fresh, "period_num", "")) != period_text:
        return _result("EliteBonusStats", record_id_text, period_text, mode, "REJECTED", "STALE_RECORD", before_version, getattr(fresh, "amount_encoding_version", None))
    fresh_fingerprint = _fingerprint(
        fresh,
        (*ELITE_BONUS_AMOUNT_FIELDS, "estimated_bonus", "estimated_bonus_cents"),
    )
    if fresh_fingerprint != initial_fingerprint:
        return _result("EliteBonusStats", record_id_text, period_text, mode, "REJECTED", "STALE_RECORD", before_version, getattr(fresh, "amount_encoding_version", None))
    invalid_code = _validate_int64_fields(fresh, ELITE_BONUS_AMOUNT_FIELDS)
    if invalid_code:
        return _result("EliteBonusStats", record_id_text, period_text, mode, "REJECTED", invalid_code, before_version, before_version)
    fresh.estimated_bonus = None
    fresh.estimated_bonus_cents = 0
    fresh.amount_encoding_version = AMOUNT_ENCODING_VERSION_V2
    fresh.save()
    # endregion

    return _result("EliteBonusStats", record_id_text, period_text, mode, "MIGRATED", "MIGRATED", before_version, AMOUNT_ENCODING_VERSION_V2)


__all__ = [
    "ELITE_BONUS_AMOUNT_FIELDS",
    "MigrationResult",
    "USER_STATS_AMOUNT_FIELDS",
    "migrate_elite_bonus_stats_record",
    "migrate_user_stats_record",
]
