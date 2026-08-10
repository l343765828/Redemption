"""WORK-PVAM-01 图 Actor 输出合同回归测试。"""

from __future__ import annotations

import ast
import copy
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


# region 测试替身


class FakeFrame:
    """仅实现目标函数所需的最小 DataFrame 协议。"""

    def __init__(self, columns, records):
        self.columns = list(columns)
        self.records = [dict(record) for record in records]

    def __len__(self):
        return len(self.records)

    def rename(self, *, columns):
        return FakeFrame(
            [columns.get(name, name) for name in self.columns],
            [
                {columns.get(name, name): value for name, value in record.items()}
                for record in self.records
            ],
        )

    def sort_values(self, name, ascending=True):
        return FakeFrame(
            self.columns,
            sorted(
                self.records,
                key=lambda record: record[name],
                reverse=not ascending,
            ),
        )

    def __getitem__(self, names):
        return FakeFrame(
            names,
            [{name: record[name] for name in names} for record in self.records],
        )

    def astype(self, conversions):
        if isinstance(conversions, dict):
            convert = lambda name, value: conversions[name](value)
        else:
            convert = lambda _name, value: conversions(value)
        return FakeFrame(
            self.columns,
            [
                {name: convert(name, value) for name, value in record.items()}
                for record in self.records
            ],
        )

    def to_dict(self, orient):
        if orient != "records":
            raise AssertionError(f"unexpected orient: {orient}")
        return [dict(record) for record in self.records]


class FakeFuture:
    def __init__(self, value):
        self.value = value

    def result(self):
        return self.value


class FakeActor:
    def __init__(self, frame):
        self.frame = frame

    def get_allparent(self, _user_id):
        return FakeFuture(self.frame)


class FakeDatasetClient:
    def __init__(self, actor):
        self.actor = actor

    def get_dataset(self, name):
        if name != "graph_actor":
            raise AssertionError(f"unexpected dataset: {name}")
        return FakeFuture(self.actor)


# endregion


# region 真实方法提取


def load_method(path: Path, class_name: str, method_name: str):
    """从真实生产文件提取目标方法，隔离 Redis/Dask 等外部依赖执行。"""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method_node = next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    probe_class = ast.ClassDef(
        name="Probe",
        bases=[],
        keywords=[],
        body=[copy.deepcopy(method_node)],
        decorator_list=[],
    )
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            probe_class,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["Probe"]


# endregion


class GraphActorContractTests(unittest.TestCase):
    def setUp(self):
        self.frame = FakeFrame(
            ["level", "ancestor", "predecessor"],
            [
                {"level": 3, "ancestor": "4", "predecessor": "3"},
                {"level": 1, "ancestor": "1", "predecessor": "9"},
                {"level": 2, "ancestor": "3", "predecessor": "1"},
            ],
        )

    def test_user_stats_normalizes_actor_ancestor_column(self):
        probe_class = load_method(
            PROJECT_ROOT / "User" / "UserStatsService.py",
            "UserStatsService",
            "_load_ancestors_info",
        )

        rows = probe_class()._load_ancestors_info(
            "9",
            graph_actor=FakeActor(self.frame),
        )

        self.assertEqual(
            rows,
            [
                {"descendant": "1", "predecessor": "9", "level": 1},
                {"descendant": "3", "predecessor": "1", "level": 2},
                {"descendant": "4", "predecessor": "3", "level": 3},
            ],
        )

    def test_elite_bonus_accepts_actor_ancestor_column(self):
        probe_class = load_method(
            PROJECT_ROOT / "User" / "EliteBonusService.py",
            "EliteBonusService",
            "_propagate_upward",
        )
        probe = probe_class()
        probe.dask_client = FakeDatasetClient(
            FakeActor(FakeFrame(self.frame.columns, []))
        )

        probe._propagate_upward(
            user_id="9",
            initial_delta=0,
            pv_delta=0,
            processed_nodes={},
            models_to_save=[],
            acquired_locks=[],
            run_config=None,
        )

    def test_consumers_fail_loud_when_actor_schema_is_incomplete(self):
        incomplete = FakeFrame(
            ["level", "predecessor"],
            [{"level": 1, "predecessor": "9"}],
        )
        user_stats_class = load_method(
            PROJECT_ROOT / "User" / "UserStatsService.py",
            "UserStatsService",
            "_load_ancestors_info",
        )
        with self.assertRaisesRegex(RuntimeError, "ancestor"):
            user_stats_class()._load_ancestors_info(
                "9",
                graph_actor=FakeActor(incomplete),
            )

        elite_bonus_class = load_method(
            PROJECT_ROOT / "User" / "EliteBonusService.py",
            "EliteBonusService",
            "_propagate_upward",
        )
        elite_probe = elite_bonus_class()
        elite_probe.dask_client = FakeDatasetClient(FakeActor(incomplete))
        with self.assertRaisesRegex(RuntimeError, "ancestor"):
            elite_probe._propagate_upward(
                user_id="9",
                initial_delta=0,
                pv_delta=0,
                processed_nodes={},
                models_to_save=[],
                acquired_locks=[],
                run_config=None,
            )


if __name__ == "__main__":
    unittest.main()
