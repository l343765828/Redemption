"""WORK-PVAM-01 金额公共层 DEV tests（标准库 unittest）。"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import unittest
from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import Common.PvAmount as pv_amount
from Common.PvAmount import (
    INT64_MAX,
    INT64_MIN,
    RATE_PPM_SCALE,
    assert_integer_amount_dtype,
    checked_add_int64,
    checked_mul_int64,
    mul_units_by_ppm,
    parse_db_amount_to_units,
    parse_external_decimal_to_units,
    parse_percent_to_ppm,
    require_amount_version,
    require_units_int,
    trunc_div_zero,
    units_ppm_to_bonus_cents,
    units_to_decimal_string,
)


# region DataFrame dtype 最小替身


class _DType:
    def __init__(self, name, kind):
        self.name = name
        self.kind = kind

    def __str__(self):
        return self.name


class _Column:
    def __init__(self, dtype):
        self.dtype = dtype


class _Frame:
    def __init__(self, dtypes):
        self._columns = {name: _Column(dtype) for name, dtype in dtypes.items()}
        self.columns = list(self._columns)

    def __getitem__(self, column):
        return self._columns[column]


# endregion


class PvAmountCommonTests(unittest.TestCase):

    # region 外部输入、数据库边界与规范输出

    def test_external_decimal_to_units(self):
        cases = [
            ("1500.99", 1_500_990_000),
            ("30.00", 30_000_000),
            ("-100.25", -100_250_000),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(expected, parse_external_decimal_to_units(raw))

    def test_external_decimal_rejects_noncanonical_or_non_string(self):
        for raw in [0.1, True, "1e2", "NaN", "sNaN", "Infinity", "+1.00", "01.00"]:
            with self.subTest(raw=raw):
                with self.assertRaises(TypeError):
                    parse_external_decimal_to_units(raw)

    def test_db_decimal_must_be_finite(self):
        for raw in [
            Decimal("NaN"),
            Decimal("sNaN"),
            Decimal("Infinity"),
            Decimal("-Infinity"),
        ]:
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, "DB amount must be finite"):
                    parse_db_amount_to_units(raw)

    def test_decimal_precision_has_two_independent_gates(self):
        with self.assertRaisesRegex(ValueError, "maximum is 2"):
            parse_db_amount_to_units("1.234")
        with self.assertRaisesRegex(ValueError, "finer than micro-units"):
            parse_db_amount_to_units(Decimal("1.2345678"), max_decimals=7)

    def test_units_to_decimal_string(self):
        cases = [
            (0, "0"),
            (30_000_000, "30"),
            (1_500_990_000, "1500.99"),
            (-100_250_000, "-100.25"),
            (1, "0.000001"),
        ]
        for units, expected in cases:
            with self.subTest(units=units):
                self.assertEqual(expected, units_to_decimal_string(units))

    # endregion

    # region 金额版本与向零截断

    def test_amount_version_accepts_only_explicit_new_or_opt_in_legacy(self):
        cases = [(2, False, 2), (None, True, 0)]
        for value, allow_legacy, expected in cases:
            with self.subTest(value=value, allow_legacy=allow_legacy):
                self.assertEqual(
                    expected,
                    require_amount_version(value, allow_legacy=allow_legacy),
                )

    def test_amount_version_rejects_missing_or_unsupported(self):
        for value in [None, 1, 3]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    require_amount_version(value)

    def test_amount_version_rejects_non_integral_or_bool(self):
        for value in ["2", True, 2.0]:
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    require_amount_version(value)

    def test_trunc_div_zero_quadrants(self):
        cases = [
            (7, 2, 3),
            (-7, 2, -3),
            (7, -2, -3),
            (-7, -2, 3),
            (1, 3, 0),
            (-1, 3, 0),
        ]
        for numerator, denominator, expected in cases:
            with self.subTest(numerator=numerator, denominator=denominator):
                self.assertEqual(expected, trunc_div_zero(numerator, denominator))

    def test_trunc_div_zero_rejects_zero_denominator(self):
        with self.assertRaises(ZeroDivisionError):
            trunc_div_zero(1, 0)

    # endregion

    # region checked int64 与 DEV-PVAM-002 divmod 极值

    def test_checked_int64_arithmetic_boundaries(self):
        self.assertEqual(INT64_MAX, checked_add_int64(INT64_MAX, 0))
        self.assertEqual(INT64_MIN, checked_add_int64(INT64_MIN, 0))
        self.assertEqual(INT64_MAX, checked_mul_int64(INT64_MAX, 1))
        with self.assertRaises(OverflowError):
            checked_add_int64(INT64_MAX, 1)
        with self.assertRaises(OverflowError):
            checked_add_int64(INT64_MIN, -1)
        with self.assertRaises(OverflowError):
            checked_mul_int64(INT64_MAX, 2)

    def test_dev_pvam_002_extremes_match_oracle_and_all_landed_values_are_int64(self):
        original_require_int64 = pv_amount.require_int64
        for units in [INT64_MAX, -INT64_MAX]:
            for ppm in [0, 1, 297_000, 1_000_000]:
                with self.subTest(units=units, ppm=ppm):
                    landed_values = []

                    def recording_require_int64(value, *, field_name="amount"):
                        landed_values.append(value)
                        return original_require_int64(value, field_name=field_name)

                    sign = -1 if (units < 0) ^ (ppm < 0) else 1
                    expected = sign * (
                        (abs(units) * abs(ppm)) // RATE_PPM_SCALE
                    )
                    with patch.object(
                        pv_amount,
                        "require_int64",
                        side_effect=recording_require_int64,
                    ):
                        actual = mul_units_by_ppm(units, ppm)

                    self.assertEqual(expected, actual)
                    self.assertGreater(len(landed_values), 0)
                    self.assertTrue(
                        all(INT64_MIN <= value <= INT64_MAX for value in landed_values)
                    )

    def test_mul_units_by_ppm_is_signed_and_truncates_toward_zero(self):
        cases = [
            (7, 500_000, 3),
            (-7, 500_000, -3),
            (7, -500_000, -3),
            (-7, -500_000, 3),
        ]
        for units, ppm, expected in cases:
            with self.subTest(units=units, ppm=ppm):
                self.assertEqual(expected, mul_units_by_ppm(units, ppm))

    def test_mul_units_by_ppm_rejects_rate_above_100_percent(self):
        with self.assertRaisesRegex(ValueError, "100 percent"):
            mul_units_by_ppm(1, RATE_PPM_SCALE + 1)

    def test_mul_units_by_ppm_does_not_materialize_units_times_ppm(self):
        tree = ast.parse(inspect.getsource(pv_amount.mul_units_by_ppm))
        multiplied_names = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Mult):
                continue
            names = {
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name)
            }
            multiplied_names.append(names)
        self.assertFalse(
            any({"units", "ppm"} <= names for names in multiplied_names)
        )

    # endregion

    # region PPM 解析与奖金分舍入

    def test_parse_percent_to_ppm(self):
        cases = [
            ("0", 0),
            ("15", 150_000),
            (Decimal("29.7"), 297_000),
            ("-15", -150_000),
            ("100", 1_000_000),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(expected, parse_percent_to_ppm(raw))

    def test_parse_percent_to_ppm_rejects_invalid_input(self):
        for raw in [0.15, True, "1e2", Decimal("NaN"), "100.0001", "0.00001"]:
            with self.subTest(raw=raw):
                with self.assertRaises((TypeError, ValueError)):
                    parse_percent_to_ppm(raw)

    def test_units_ppm_to_bonus_cents(self):
        cases = [
            (1_500_990_000, 150_000, "TRUNCATE", 22_514),
            (-1_500_990_000, 150_000, "TRUNCATE", -22_514),
            (1_500_990_000, 150_000, "ROUND_HALF_UP", 22_515),
            (-1_500_990_000, 150_000, "ROUND_HALF_UP", -22_515),
            (1_000_000, 5_000, "ROUND_HALF_UP", 1),
            (0, 1_000_000, "TRUNCATE", 0),
        ]
        for units, ppm, mode, expected in cases:
            with self.subTest(units=units, ppm=ppm, mode=mode):
                self.assertEqual(
                    expected,
                    units_ppm_to_bonus_cents(units, ppm, mode),
                )

    def test_units_ppm_to_bonus_cents_rejects_unknown_rounding_mode(self):
        with self.assertRaisesRegex(ValueError, "unsupported rounding_mode"):
            units_ppm_to_bonus_cents(1, 1, "BANKERS")

    # endregion

    # region integer 类型与 DataFrame dtype

    def test_require_units_int_rejects_bool_and_float(self):
        with self.assertRaises(TypeError):
            require_units_int(True)
        with self.assertRaises(TypeError):
            require_units_int(1.0)

    def test_require_units_int_supports_numpy_integer_when_available(self):
        if importlib.util.find_spec("numpy") is None:
            self.skipTest("numpy is not installed")
        import numpy

        self.assertEqual(7, require_units_int(numpy.int64(7)))

    def test_assert_integer_amount_dtype_accepts_signed_and_unsigned_integer(self):
        frame = _Frame(
            {"pv": _DType("int64", "i"), "gpv": _DType("uint64", "u")}
        )
        assert_integer_amount_dtype(frame, ["pv", "gpv"], "amounts")

    def test_assert_integer_amount_dtype_rejects_float_and_missing_columns(self):
        frame = _Frame({"pv": _DType("float64", "f")})
        with self.assertRaisesRegex(TypeError, "integer dtype"):
            assert_integer_amount_dtype(frame, ["pv"], "amounts")
        with self.assertRaisesRegex(KeyError, "amounts.gpv is missing"):
            assert_integer_amount_dtype(frame, ["gpv"], "amounts")

    # endregion


if __name__ == "__main__":
    unittest.main(verbosity=2)
