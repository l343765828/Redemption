"""WORK-PVAM-01 / TC-FLAG-14～21 条件化工厂与版本域 DEV tests。"""

from __future__ import annotations

import ast
import copy
import inspect
import re
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Common.AmountModelAdapter import (
    AmountRecordState,
    build_factory_amount_fields,
    classify_amount_record,
    require_v2_amount_record,
)
from Common.PvAmount import AMOUNT_ENCODING_VERSION_V2
from Redishelper.PVAmountConfigProvider import (
    AR_CONFIG_SOURCE,
    MANUAL_BOOTSTRAP_MODE,
    PVAmountConfigError,
    PVAmountRunConfig,
    PVAmountRunSession,
    admit_production_run_config,
    compute_snapshot_checksum,
)


# region 测试常量与源码扫描辅助

USER_STATS_SHARED_FIELDS = {
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
}

ELITE_SHARED_FIELDS = {
    "pv_pcs",
    "gpv",
    "gpv_real",
    "contrib_to_parent",
}

_EXCLUDED_NAME = re.compile(r"(?:_bak\d*|_final)", re.IGNORECASE)


def make_config(read_v2: bool, write_v2: bool, version: int) -> PVAmountRunConfig:
    checksum = compute_snapshot_checksum(
        read_v2=read_v2,
        write_v2=write_v2,
        config_version=version,
        load_mode=MANUAL_BOOTSTRAP_MODE,
        source=AR_CONFIG_SOURCE,
    )
    return PVAmountRunConfig(
        read_v2=read_v2,
        write_v2=write_v2,
        config_version=version,
        load_mode=MANUAL_BOOTSTRAP_MODE,
        source=AR_CONFIG_SOURCE,
        checksum=checksum,
    )


def effective_production_sources():
    """遵循项目 file-filter，动态扫描 User 生产 Python，而非预列工厂名。"""
    for path in sorted((PROJECT_ROOT / "User").rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT)
        if (
            "Test" in relative.parts
            or "__pycache__" in relative.parts
            or _EXCLUDED_NAME.search(path.name)
            or path.name == "GraphService.py"
        ):
            continue
        yield path


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_module_main_guard(node: ast.If) -> bool:
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.left, ast.Name) or test.left.id != "__name__":
        return False
    if not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
        return False
    right = test.comparators[0]
    return isinstance(right, ast.Constant) and right.value == "__main__"


class FactoryCallVisitor(ast.NodeVisitor):
    """发现所有有效生产源码中的模型构造点并区分纯反序列化。"""

    def __init__(self, path: Path):
        self.path = path
        self.function_stack: list[str] = []
        self.in_main_guard = 0
        self.factories: list[tuple[ast.Call, str, str]] = []
        self.deserializers: list[tuple[ast.Call, str, str]] = []

    def visit_FunctionDef(self, node):
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node):
        is_main = _is_module_main_guard(node)
        if is_main:
            self.in_main_guard += 1
        for child in node.body:
            self.visit(child)
        if is_main:
            self.in_main_guard -= 1
        for child in node.orelse:
            self.visit(child)

    def visit_Call(self, node):
        model_name = _call_name(node.func)
        if model_name in {"UserStats", "EliteBonusStats"} and not self.in_main_guard:
            function_name = self.function_stack[-1] if self.function_stack else "<module>"
            explicit_keywords = [kw for kw in node.keywords if kw.arg is not None]
            expanded_keywords = [kw for kw in node.keywords if kw.arg is None]
            is_deserializer = not explicit_keywords and len(expanded_keywords) == 1
            target = self.deserializers if is_deserializer else self.factories
            target.append((node, model_name, function_name))
        self.generic_visit(node)


def discover_factory_calls():
    factories = []
    deserializers = []
    for path in effective_production_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = FactoryCallVisitor(path)
        visitor.visit(tree)
        factories.extend((path, *item) for item in visitor.factories)
        deserializers.extend((path, *item) for item in visitor.deserializers)
    return factories, deserializers


def class_field_defaults(path: Path, class_name: str) -> dict[str, ast.AST | None]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.target.id: item.value
                for item in node.body
                if isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
            }
    raise AssertionError(f"class not found: {class_name}")


# endregion


class ConditionalFactoryContractTests(unittest.TestCase):

    # region TC-FLAG-14：READ=false 审计读取不改变 legacy 业务值

    def test_tc_flag_14_audit_classification_is_read_only(self):
        record = {
            "amount_encoding_version": None,
            "pv": 125,
            "gpv": 375,
            "estimated_bonus": 12.5,
        }
        before = copy.deepcopy(record)
        legacy_result_before = record["pv"] + record["gpv"]

        state = classify_amount_record(record)

        self.assertIs(AmountRecordState.LEGACY_UNKNOWN, state)
        self.assertEqual(before, record)
        self.assertEqual(legacy_result_before, record["pv"] + record["gpv"])

    # endregion

    # region TC-FLAG-15～16：00/01 不 stamping 2，动态覆盖全部生产工厂

    def test_tc_flag_15_state_00_legacy_factory_does_not_stamp_v2(self):
        fields = build_factory_amount_fields("00")
        self.assertIsNone(fields["amount_encoding_version"])

    def test_tc_flag_16_state_01_all_discovered_shared_key_factories_are_conditional(self):
        fields = build_factory_amount_fields("01")
        elite_fields = build_factory_amount_fields(
            "01",
            include_bonus_cents=True,
        )
        self.assertIsNone(fields["amount_encoding_version"])
        self.assertIsNone(elite_fields["amount_encoding_version"])
        self.assertIsNone(elite_fields["estimated_bonus_cents"])

        factories, deserializers = discover_factory_calls()
        self.assertGreater(len(factories), 0)
        self.assertGreater(len(deserializers), 0)

        violations = []
        for path, call, model_name, function_name in factories:
            helpers = [
                kw.value
                for kw in call.keywords
                if kw.arg is None
                and isinstance(kw.value, ast.Call)
                and _call_name(kw.value.func) == "build_factory_amount_fields"
            ]
            if len(helpers) != 1:
                violations.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{call.lineno}:"
                    f"{function_name}:{model_name}:missing conditional helper"
                )
                continue

            helper = helpers[0]
            if (
                not helper.args
                or not isinstance(helper.args[0], ast.Attribute)
                or not isinstance(helper.args[0].value, ast.Name)
                or helper.args[0].value.id != "run_config"
                or helper.args[0].attr != "state"
            ):
                violations.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{call.lineno}:"
                    f"{function_name}:{model_name}:not tied to frozen run_config"
                )

            if model_name == "EliteBonusStats":
                include = [
                    kw.value
                    for kw in helper.keywords
                    if kw.arg == "include_bonus_cents"
                ]
                if (
                    len(include) != 1
                    or not isinstance(include[0], ast.Constant)
                    or include[0].value is not True
                ):
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{call.lineno}:"
                        f"{function_name}:{model_name}:missing additive cents init"
                    )

        self.assertEqual([], violations)

    # endregion

    # region TC-FLAG-17：精确共享字段锚点

    def test_tc_flag_17_exact_shared_fields_and_additive_fields_exist(self):
        user_defaults = class_field_defaults(
            PROJECT_ROOT / "Model" / "User" / "UserStats.py",
            "UserStats",
        )
        elite_defaults = class_field_defaults(
            PROJECT_ROOT / "Model" / "User" / "EliteBonusStats.py",
            "EliteBonusStats",
        )

        self.assertTrue(USER_STATS_SHARED_FIELDS <= set(user_defaults))
        self.assertTrue(ELITE_SHARED_FIELDS <= set(elite_defaults))
        self.assertIn("amount_encoding_version", user_defaults)
        self.assertIn("amount_encoding_version", elite_defaults)
        self.assertIn("estimated_bonus", elite_defaults)
        self.assertIn("estimated_bonus_cents", elite_defaults)

        self.assertIsInstance(user_defaults["amount_encoding_version"], ast.Constant)
        self.assertIsNone(user_defaults["amount_encoding_version"].value)
        self.assertIsInstance(elite_defaults["amount_encoding_version"], ast.Constant)
        self.assertIsNone(elite_defaults["amount_encoding_version"].value)
        self.assertIsInstance(elite_defaults["estimated_bonus_cents"], ast.Constant)
        self.assertIsNone(elite_defaults["estimated_bonus_cents"].value)

    # endregion

    # region TC-FLAG-18～19：禁止 float 洗白，0 仅为 V2 blank/init

    def test_tc_flag_18_no_legacy_float_to_cents_wash(self):
        violations = []
        paths = list(effective_production_sources()) + [
            PROJECT_ROOT / "Common" / "AmountModelAdapter.py",
            PROJECT_ROOT / "Model" / "User" / "EliteBonusStats.py",
        ]
        for path in paths:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))

            if re.search(
                r"estimated_bonus_cents\s*=.*(?:estimated_bonus|float\s*\(|round\s*\()",
                source,
            ):
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:text conversion")

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    if keyword.arg != "estimated_bonus_cents":
                        continue
                    if not (
                        isinstance(keyword.value, ast.Constant)
                        and keyword.value.value in {None, 0}
                    ):
                        violations.append(
                            f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}:constructor conversion"
                        )

        self.assertEqual([], violations)

    def test_tc_flag_19_zero_only_proves_v2_blank_not_bonus_parity(self):
        v2_blank = build_factory_amount_fields(
            "11",
            include_bonus_cents=True,
        )
        legacy_bonus = 12.34

        self.assertEqual(0, v2_blank["estimated_bonus_cents"])
        self.assertNotEqual(legacy_bonus, v2_blank["estimated_bonus_cents"])
        self.assertIsNone(v2_blank["estimated_bonus"])

    # endregion

    # region TC-FLAG-20～21：TEST-ONLY 11 与 production admission 隔离

    def test_tc_flag_20_direct_unit_domain_11_can_stamp_but_production_rejects(self):
        test_fixture = make_config(True, True, 77)
        fields = build_factory_amount_fields(
            test_fixture.state,
            include_bonus_cents=True,
        )

        self.assertEqual(
            AMOUNT_ENCODING_VERSION_V2,
            fields["amount_encoding_version"],
        )
        self.assertEqual(0, fields["estimated_bonus_cents"])
        require_v2_amount_record(fields)

        with self.assertRaises(PVAmountConfigError) as captured:
            admit_production_run_config(test_fixture)
        self.assertEqual("V2_STATE_NOT_AUTHORIZED", captured.exception.code)

    def test_tc_flag_21_production_has_no_test_only_bypass(self):
        self.assertEqual(
            ["config"],
            list(inspect.signature(admit_production_run_config).parameters),
        )
        self.assertEqual(
            ["provider"],
            [
                name
                for name in inspect.signature(PVAmountRunSession.start).parameters
                if name != "cls"
            ],
        )

        paths = [
            PROJECT_ROOT / "Redishelper" / "PVAmountConfigProvider.py",
            PROJECT_ROOT / "Redishelper" / "PVAmountConfigBootstrap.py",
            PROJECT_ROOT / "Common" / "AmountModelAdapter.py",
            *effective_production_sources(),
        ]
        violations = []
        for path in paths:
            source = path.read_text(encoding="utf-8").lower()
            for token in ("test_only", "test-only", "bypass"):
                if token in source:
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{token}"
                    )
        self.assertEqual([], violations)

    # endregion


if __name__ == "__main__":
    unittest.main(verbosity=2)
