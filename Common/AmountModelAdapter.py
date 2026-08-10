from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from Common.PvAmount import AMOUNT_ENCODING_VERSION_V2


# =====================================================================
# 金额记录版本状态
# =====================================================================
# region 状态枚举
class AmountRecordState(str, Enum):
    """区分新编码、未知 legacy 与不兼容记录。"""
    NEW = "NEW"
    LEGACY_UNKNOWN = "LEGACY_UNKNOWN"
    INCOMPATIBLE = "INCOMPATIBLE"
# endregion


# =====================================================================
# 金额记录只读分类器
# =====================================================================
def classify_amount_record(record: object) -> AmountRecordState:
    """仅分类，不修改、缩放、重建或升级原始记录。"""
    # region 从 Mapping、模型属性或直接值中提取版本
    if isinstance(record, Mapping):
        version = record.get("amount_encoding_version")
    elif hasattr(record, "amount_encoding_version"):
        version = getattr(record, "amount_encoding_version")
    else:
        version = record

    # endregion

    # region 按版本值返回状态，不对 legacy 记录执行隐式升级
    if version is None:
        return AmountRecordState.LEGACY_UNKNOWN
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
    ):
        return AmountRecordState.INCOMPATIBLE
    if version == AMOUNT_ENCODING_VERSION_V2:
        return AmountRecordState.NEW
    return AmountRecordState.INCOMPATIBLE
    # endregion

# =====================================================================
# V2 金额域守卫与工厂字段
# =====================================================================
# region V2 计算入口守卫
def require_v2_amount_record(record: object) -> None:
    """仅在 V2 计算入口阻断 legacy/unknown 或不兼容记录。"""
    state = classify_amount_record(record)
    if state is not AmountRecordState.NEW:
        raise ValueError(f"V2_AMOUNT_RECORD_REQUIRED:{state.value}")
# endregion


# region 按冻结运行态构造新增金额字段
def build_factory_amount_fields(
    run_state: str,
    *,
    include_bonus_cents: bool = False,
) -> dict[str, int | None]:
    """为新记录生成条件化字段；不读取配置，也不改写 legacy 金额。"""
    if run_state in {"00", "01"}:
        fields: dict[str, int | None] = {"amount_encoding_version": None}
        if include_bonus_cents:
            fields["estimated_bonus_cents"] = None
        return fields
    if run_state == "10":
        raise ValueError("INVALID_STATE")
    if run_state == "11":
        fields = {"amount_encoding_version": AMOUNT_ENCODING_VERSION_V2}
        if include_bonus_cents:
            fields["estimated_bonus"] = None
            fields["estimated_bonus_cents"] = 0
        return fields
    raise ValueError("INVALID_STATE")
# endregion
