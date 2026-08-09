"""WORK-PVAM-01 金额记录版本分类与 V2 入口守卫 tests。"""

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Common.AmountModelAdapter import (
    AmountRecordState,
    classify_amount_record,
    require_v2_amount_record,
)


class AmountModelVersionTests(unittest.TestCase):

    # region 新编码、未知 legacy 与不兼容记录

    def test_classify_amount_record_new_and_legacy(self):
        cases = [
            ({"amount_encoding_version": 2}, AmountRecordState.NEW),
            ({}, AmountRecordState.LEGACY_UNKNOWN),
            ({"amount_encoding_version": None}, AmountRecordState.LEGACY_UNKNOWN),
            (SimpleNamespace(amount_encoding_version=2), AmountRecordState.NEW),
            (
                SimpleNamespace(amount_encoding_version=None),
                AmountRecordState.LEGACY_UNKNOWN,
            ),
            (2, AmountRecordState.NEW),
            (None, AmountRecordState.LEGACY_UNKNOWN),
        ]
        for record, expected in cases:
            with self.subTest(record=record):
                self.assertIs(expected, classify_amount_record(record))

    def test_classify_amount_record_incompatible(self):
        records = [
            {"amount_encoding_version": 1},
            {"amount_encoding_version": 3},
            {"amount_encoding_version": "2"},
            {"amount_encoding_version": True},
            SimpleNamespace(amount_encoding_version=3),
        ]
        for record in records:
            with self.subTest(record=record):
                self.assertIs(
                    AmountRecordState.INCOMPATIBLE,
                    classify_amount_record(record),
                )

    def test_classification_never_mutates_legacy_mapping(self):
        record = {"pv": 100}
        before = dict(record)
        self.assertIs(
            AmountRecordState.LEGACY_UNKNOWN,
            classify_amount_record(record),
        )
        self.assertEqual(before, record)

    # endregion

    # region AC-03：守卫只在 V2 计算入口调用

    def test_v2_entry_accepts_only_explicit_version_2(self):
        require_v2_amount_record({"amount_encoding_version": 2})

        for record in [
            {},
            {"amount_encoding_version": None},
            {"amount_encoding_version": 1},
            {"amount_encoding_version": "2"},
        ]:
            with self.subTest(record=record):
                with self.assertRaisesRegex(
                    ValueError,
                    "V2_AMOUNT_RECORD_REQUIRED",
                ):
                    require_v2_amount_record(record)

    # endregion


if __name__ == "__main__":
    unittest.main(verbosity=2)
