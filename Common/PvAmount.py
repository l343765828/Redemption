from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from numbers import Integral
from typing import Final

# =====================================================================
# PVAM 固定精度金额公共常量
# =====================================================================
# region 金额、费率及奖金分的缩放倍率
PV_SCALE: Final[int] = 1_000_000
RATE_PPM_SCALE: Final[int] = 1_000_000
BONUS_CENT_SCALE: Final[int] = 100
AMOUNT_ENCODING_VERSION_V2: Final[int] = 2
# endregion

# region legacy 隔离版本
# 仅供隔离 legacy adapter 返回；不得写入模型或事件。
LEGACY_ADAPTER_VERSION: Final[int] = 0
# endregion

# region signed int64 边界
INT64_MIN: Final[int] = -(2**63)
INT64_MAX: Final[int] = 2**63 - 1
# endregion

# region 规范十进制格式及舍入模式
_CANONICAL_DECIMAL = re.compile(
    r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"
)

_ROUNDING_MODE_TRUNCATE: Final[str] = "TRUNCATE"
_ROUNDING_MODE_HALF_UP: Final[str] = "ROUND_HALF_UP"
# endregion


# =====================================================================
# 基础整数与金额精度校验
# =====================================================================
def require_int64(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(
            f"{field_name} must be an integer, "
            f"got {type(value).__name__}"
        )

    result = int(value)

    if result < INT64_MIN or result > INT64_MAX:
        raise OverflowError(
            f"{field_name} is outside signed int64"
        )

    return result


def require_units_int(
    value: object,
    field_name: str = "amount_units",
) -> int:
    return require_int64(
        value,
        field_name=field_name,
    )


# =====================================================================
# 十进制精度转换
# =====================================================================
def _require_max_decimals(
    max_decimals: int,
) -> int:
    if (
        isinstance(max_decimals, bool)
        or not isinstance(max_decimals, int)
        or max_decimals < 0
    ):
        raise ValueError(
            "max_decimals must be a non-negative integer"
        )

    return max_decimals


def _decimal_to_units(
    value: Decimal,
    *,
    max_decimals: int,
    field_name: str,
) -> int:

    max_decimals = _require_max_decimals(
        max_decimals
    )

    decimal_places = max(
        0,
        -value.as_tuple().exponent,
    )

    if decimal_places > max_decimals:
        raise ValueError(
            f"{field_name} has "
            f"{decimal_places} decimal places; "
            f"maximum is {max_decimals}"
        )

    scaled = value * PV_SCALE

    if scaled != scaled.to_integral_value():
        raise ValueError(
            f"{field_name} has precision "
            f"finer than micro-units"
        )

    return require_int64(
        int(scaled),
        field_name=field_name,
    )


# =====================================================================
# 外部输入与数据库金额解析
# =====================================================================
def parse_external_decimal_to_units(
    raw: str,
    *,
    max_decimals: int = 2,
) -> int:

    if (
        not isinstance(raw, str)
        or not _CANONICAL_DECIMAL.fullmatch(raw)
    ):
        raise TypeError(
            "external amount must be "
            "a canonical decimal string"
        )

    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(
            "external amount is not a decimal"
        ) from exc

    return _decimal_to_units(
        value,
        max_decimals=max_decimals,
        field_name="external_amount",
    )


def parse_db_amount_to_units(
    raw: Decimal | str,
    *,
    max_decimals: int = 2,
) -> int:
    """解析 DB 金额边界；默认两位是来源精度策略，不是内部 scale 上限。

    已批准的更高精度来源必须显式传入 ``max_decimals``；``PV_SCALE`` 只定义
    内部 micro-units 分辨率，不能反向放宽外部数据库字段的精度合同。
    """

    if isinstance(raw, Decimal):
        value = raw

    elif (
        isinstance(raw, str)
        and _CANONICAL_DECIMAL.fullmatch(raw)
    ):
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError(
                "DB amount is not a decimal"
            ) from exc

    else:
        raise TypeError(
            "DB amount must be Decimal "
            "or canonical decimal string"
        )

    if not value.is_finite():
        raise ValueError(
            "DB amount must be finite"
        )

    return _decimal_to_units(
        value,
        max_decimals=max_decimals,
        field_name="db_amount",
    )


# =====================================================================
# 金额编码版本校验
# =====================================================================
def require_amount_version(
    value: object,
    *,
    allow_legacy: bool = False,
) -> int:

    if value is None:
        if allow_legacy:
            return LEGACY_ADAPTER_VERSION

        raise ValueError(
            "amount_encoding_version "
            "is missing/legacy"
        )

    if (
        isinstance(value, bool)
        or not isinstance(value, Integral)
    ):
        raise TypeError(
            "amount_encoding_version "
            "must be an integer"
        )

    normalized = int(value)

    if normalized != AMOUNT_ENCODING_VERSION_V2:
        raise ValueError(
            "unsupported "
            f"amount_encoding_version={normalized}"
        )

    return normalized


# =====================================================================
# 整数截断与规范化输出
# =====================================================================
def trunc_div_zero(
    numerator: int,
    denominator: int,
) -> int:
    """整数除法向零截断；支持任意非零分母。"""

    if denominator == 0:
        raise ZeroDivisionError(
            "denominator must not be zero"
        )

    quotient = (
        abs(numerator)
        // abs(denominator)
    )

    return (
        -quotient
        if (numerator < 0)
        ^ (denominator < 0)
        else quotient
    )


def units_to_decimal_string(units: int) -> str:
    normalized = require_units_int(units)
    sign = "-" if normalized < 0 else ""
    whole, remainder = divmod(abs(normalized), PV_SCALE)

    if remainder == 0:
        return f"{sign}{whole}"

    fraction = f"{remainder:06d}".rstrip("0")
    return f"{sign}{whole}.{fraction}"


# =====================================================================
# PPM 费率解析与 int64 安全算术
# =====================================================================
def parse_percent_to_ppm(raw: Decimal | str) -> int:
    """把百分数值转换为 ppm：15 表示 15%，0.15 表示 0.15%。

    本函数不接受“已除以 100 的比例值”语义；normalized fraction 必须由调用方
    在其获批边界显式处理，不能把 0.15（15% fraction）误传到这里。
    """
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, str) and _CANONICAL_DECIMAL.fullmatch(raw):
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError("percent is not a decimal") from exc
    else:
        raise TypeError(
            "percent must be Decimal or canonical decimal string"
        )

    if not value.is_finite():
        raise ValueError("percent must be finite")
    if abs(value) > Decimal(100):
        raise ValueError("percent magnitude must not exceed 100")

    scaled = value * (RATE_PPM_SCALE // 100)
    if scaled != scaled.to_integral_value():
        raise ValueError("percent has precision finer than ppm")

    return require_int64(int(scaled), field_name="rate_ppm")


def checked_add_int64(*values: int) -> int:
    total = 0
    for index, value in enumerate(values):
        normalized = require_int64(
            value,
            field_name=f"addend[{index}]",
        )
        total = require_int64(
            total + normalized,
            field_name="int64_sum",
        )
    return total


def checked_mul_int64(a: int, b: int) -> int:
    left = require_int64(a, field_name="multiplicand")
    right = require_int64(b, field_name="multiplier")
    return require_int64(
        left * right,
        field_name="int64_product",
    )


def _require_rate_ppm(ppm: int) -> int:
    normalized = require_int64(ppm, field_name="rate_ppm")
    if abs(normalized) > RATE_PPM_SCALE:
        raise ValueError("rate_ppm magnitude must not exceed 100 percent")
    return normalized


# =====================================================================
# DEV-PVAM-002：无大乘积的 divmod 分解
# =====================================================================
def _decomposed_nonnegative_mul_div(
    value: int,
    multiplier: int,
    denominator: int,
    *,
    field_name: str,
) -> tuple[int, int]:
    """Return quotient/remainder without materializing value * multiplier."""
    # region 按分母拆分并逐步执行 int64 检查
    # USER-DECISION-PVAM-01-INT64 要求合法输入域内不得产生超 int64 的已落域中间量。

    quotient, remainder = divmod(value, denominator)
    term_1 = checked_mul_int64(quotient, multiplier)
    remainder_product = checked_mul_int64(remainder, multiplier)
    term_2, final_remainder = divmod(remainder_product, denominator)
    magnitude = checked_add_int64(term_1, term_2)
    return (
        require_int64(magnitude, field_name=field_name),
        require_int64(final_remainder, field_name=f"{field_name}_remainder"),
    )
    # endregion


# =====================================================================
# 金额乘费率公共接口
# =====================================================================
# region divmod 计算、向零截断及最终 int64 落域
def mul_units_by_ppm(units: int, ppm: int) -> int:
    """按 ppm 计算金额并向零截断，全程不物化 units × ppm。"""
    normalized_units = require_units_int(units)
    normalized_ppm = _require_rate_ppm(ppm)
    sign = -1 if (normalized_units < 0) ^ (normalized_ppm < 0) else 1
    magnitude, _ = _decomposed_nonnegative_mul_div(
        abs(normalized_units),
        abs(normalized_ppm),
        RATE_PPM_SCALE,
        field_name="units_mul_ppm_magnitude",
    )
    return require_int64(
        sign * magnitude,
        field_name="units_mul_ppm",
    )
# endregion


# =====================================================================
# 金额与费率换算为奖金分
# =====================================================================
# region TRUNCATE 与最终一次 ROUND_HALF_UP
def units_ppm_to_bonus_cents(
    units: int,
    ppm: int,
    rounding_mode: str,
) -> int:
    """按指定舍入模式将金额和 signed ppm 费率一次换算为奖金分，不添加业务上限。"""
    normalized_units = require_units_int(units)
    normalized_ppm = require_int64(ppm, field_name="rate_ppm")
    if rounding_mode not in {
        _ROUNDING_MODE_TRUNCATE,
        _ROUNDING_MODE_HALF_UP,
    }:
        raise ValueError(f"unsupported rounding_mode={rounding_mode!r}")

    sign = -1 if (normalized_units < 0) ^ (normalized_ppm < 0) else 1
    units_per_cent = PV_SCALE // BONUS_CENT_SCALE
    denominator = checked_mul_int64(RATE_PPM_SCALE, units_per_cent)
    magnitude, remainder = _decomposed_nonnegative_mul_div(
        abs(normalized_units),
        abs(normalized_ppm),
        denominator,
        field_name="bonus_cents_magnitude",
    )

    if rounding_mode == _ROUNDING_MODE_HALF_UP:
        doubled_remainder = checked_mul_int64(remainder, 2)
        if doubled_remainder >= denominator:
            magnitude = checked_add_int64(magnitude, 1)

    return require_int64(
        sign * magnitude,
        field_name="bonus_cents",
    )
# endregion


# =====================================================================
# DataFrame 整数金额列边界校验
# =====================================================================
# region 逐列检查存在性与整数 dtype
def assert_integer_amount_dtype(df, columns, df_name: str) -> None:
    """进入 numpy/cuDF int64 边界前，拒绝浮点、unsigned 或缺失金额列。"""
    for column in columns:
        if column not in df.columns:
            raise KeyError(f"{df_name}.{column} is missing")

        dtype = df[column].dtype
        if getattr(dtype, "kind", None) != "i" or getattr(dtype, "itemsize", None) != 8:
            raise TypeError(
                f"{df_name}.{column} must use a signed int64 dtype, got {dtype}"
            )
# endregion
