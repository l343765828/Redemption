"""WORK-PVAM-01C / TC-FLAG-01～13、22、23 DEV tests。

FakeRedis 只证明 Provider 与 Lua 调用合同的 DEV 行为；它不构成真实 Redis UAT。
"""

from __future__ import annotations

import ast
import os
import sys
import threading
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Redishelper.PVAmountConfigBootstrap import (
    PUBLISH_SNAPSHOT_LUA,
    publish_manual_bootstrap,
)
from Redishelper.PVAmountConfigProvider import (
    ACTIVE_POINTER_KEY,
    AR_CONFIG_SOURCE,
    CHECKSUM_FIELD,
    LOAD_MODE_FIELD,
    LOAD_SNAPSHOT_LUA,
    MANUAL_BOOTSTRAP_MODE,
    PVAmountConfigError,
    PVAmountConfigProvider,
    PVAmountRunConfig,
    PVAmountRunSession,
    READ_FIELD,
    SNAPSHOT_KEY_PREFIX,
    SOURCE_FIELD,
    VERSION_FIELD,
    WRITE_FIELD,
    admit_production_run_config,
    compute_snapshot_checksum,
)


# region Fake Redis 原子边界


class FakeRedis:
    """只模拟本卡两个 Lua script 的 server-side 原子结果。"""

    def __init__(self):
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.lock = threading.Lock()
        self.eval_calls: list[str] = []
        self.publish_count = 0
        self.fail_with: Exception | None = None

    def eval(self, script, numkeys, *args):
        if self.fail_with is not None:
            raise self.fail_with
        if numkeys != 1:
            raise AssertionError("本合同只允许单 key 声明的 Lua 调用")

        with self.lock:
            if "PVAM_LOAD_SNAPSHOT_V1" in script:
                self.eval_calls.append("load")
                return self._eval_load(*args)
            if "PVAM_PUBLISH_SNAPSHOT_V1" in script:
                self.eval_calls.append("publish")
                return self._eval_publish(*args)
            raise AssertionError("未知 Lua script")

    def _eval_load(self, active_key, snapshot_prefix):
        pointer = self.strings.get(active_key)
        if pointer is None:
            return ["ERR", "ACTIVE_SNAPSHOT_MISSING"]
        if pointer.count(":") != 1:
            return ["ERR", "ACTIVE_POINTER_INVALID"]

        version, _ = pointer.split(":", 1)
        snapshot_key = snapshot_prefix + version
        snapshot = self.hashes.get(snapshot_key)
        if snapshot is None:
            return ["ERR", "SNAPSHOT_MISSING"]

        flat: list[str] = []
        for field, value in snapshot.items():
            flat.extend((field, value))
        return ["OK", pointer, snapshot_key, *flat]

    def _eval_publish(
            self,
            active_key,
            snapshot_prefix,
            new_version,
            expected_token,
            read_value,
            write_value,
            load_mode,
            source,
            checksum,
    ):
        self.publish_count += 1
        pointer = self.strings.get(active_key)

        if expected_token == "INITIAL":
            if pointer is not None:
                return ["ERR", "STALE_CONFIG_VERSION"]
        else:
            if pointer is None:
                return ["ERR", "ACTIVE_SNAPSHOT_MISSING"]
            if pointer.count(":") != 1:
                return ["ERR", "ACTIVE_POINTER_INVALID"]
            active_version, active_checksum = pointer.split(":", 1)
            if len(active_checksum) != 64:
                return ["ERR", "ACTIVE_POINTER_INVALID"]
            if active_version != expected_token:
                return ["ERR", "STALE_CONFIG_VERSION"]
            if int(new_version) <= int(active_version):
                return ["ERR", "STALE_CONFIG_VERSION"]

        snapshot_key = snapshot_prefix + new_version
        if snapshot_key in self.hashes:
            return ["ERR", "SNAPSHOT_ALREADY_EXISTS"]

        self.hashes[snapshot_key] = {
            READ_FIELD: read_value,
            WRITE_FIELD: write_value,
            VERSION_FIELD: new_version,
            LOAD_MODE_FIELD: load_mode,
            SOURCE_FIELD: source,
            CHECKSUM_FIELD: checksum,
        }
        pointer = f"{new_version}:{checksum}"
        self.strings[active_key] = pointer
        return ["OK", pointer, snapshot_key]

    def seed(
            self,
            *,
            read_v2: bool,
            write_v2: bool,
            version: int,
            fields_override: dict[str, str] | None = None,
    ) -> dict[str, str]:
        checksum = compute_snapshot_checksum(
            read_v2=read_v2,
            write_v2=write_v2,
            config_version=version,
            load_mode=MANUAL_BOOTSTRAP_MODE,
            source=AR_CONFIG_SOURCE,
        )
        fields = {
            READ_FIELD: "true" if read_v2 else "false",
            WRITE_FIELD: "true" if write_v2 else "false",
            VERSION_FIELD: str(version),
            LOAD_MODE_FIELD: MANUAL_BOOTSTRAP_MODE,
            SOURCE_FIELD: AR_CONFIG_SOURCE,
            CHECKSUM_FIELD: checksum,
        }
        if fields_override:
            fields.update(fields_override)
        self.hashes[f"{SNAPSHOT_KEY_PREFIX}{version}"] = fields
        self.strings[ACTIVE_POINTER_KEY] = f"{version}:{checksum}"
        return fields


# endregion


# region 测试辅助


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


class SequenceProvider(PVAmountConfigProvider):
    def __init__(self, configs):
        super().__init__(redis_client=object())
        self.configs = list(configs)
        self.calls = 0

    def load_run_config(self):
        config = self.configs[self.calls]
        self.calls += 1
        return config


# endregion


class FlagRuntimeContractTests(unittest.TestCase):

    def assert_config_error(self, code, operation):
        with self.assertRaises(PVAmountConfigError) as captured:
            operation()
        self.assertEqual(code, captured.exception.code)
        return captured.exception

    # region TC-FLAG-01～08：load 与 fail-loud

    def test_tc_flag_01_load_legal_01_snapshot_as_immutable_config(self):
        redis = FakeRedis()
        redis.seed(read_v2=False, write_v2=True, version=7)

        config = PVAmountConfigProvider(redis).load_run_config()

        self.assertEqual("01", config.state)
        self.assertEqual(7, config.config_version)
        self.assertEqual(["load"], redis.eval_calls)
        with self.assertRaises(FrozenInstanceError):
            config.config_version = 8

    def test_tc_flag_02_missing_active_snapshot_fails_loud(self):
        redis = FakeRedis()
        self.assert_config_error(
            "ACTIVE_SNAPSHOT_MISSING",
            lambda: PVAmountConfigProvider(redis).load_run_config(),
        )

    def test_tc_flag_03_read_missing_fails_loud(self):
        redis = FakeRedis()
        fields = redis.seed(read_v2=False, write_v2=True, version=3)
        del fields[READ_FIELD]
        self.assert_config_error(
            "READ_MISSING",
            lambda: PVAmountConfigProvider(redis).load_run_config(),
        )

    def test_tc_flag_04_write_missing_fails_loud(self):
        redis = FakeRedis()
        fields = redis.seed(read_v2=False, write_v2=True, version=3)
        del fields[WRITE_FIELD]
        self.assert_config_error(
            "WRITE_MISSING",
            lambda: PVAmountConfigProvider(redis).load_run_config(),
        )

    def test_tc_flag_05_version_missing_fails_loud(self):
        redis = FakeRedis()
        fields = redis.seed(read_v2=False, write_v2=True, version=3)
        del fields[VERSION_FIELD]
        self.assert_config_error(
            "CONFIG_VERSION_MISSING",
            lambda: PVAmountConfigProvider(redis).load_run_config(),
        )

    def test_tc_flag_06_non_canonical_bool_fails_loud(self):
        redis = FakeRedis()
        redis.seed(
            read_v2=False,
            write_v2=True,
            version=3,
            fields_override={READ_FIELD: "False"},
        )
        self.assert_config_error(
            "INVALID_BOOL",
            lambda: PVAmountConfigProvider(redis).load_run_config(),
        )

    def test_tc_flag_07_state_10_is_invalid_for_production(self):
        self.assert_config_error(
            "INVALID_STATE",
            lambda: admit_production_run_config(make_config(True, False, 8)),
        )

    def test_tc_flag_08_redis_exception_has_no_fallback(self):
        redis = FakeRedis()
        redis.fail_with = ConnectionError("redis unavailable")
        with patch.dict(
                os.environ,
                {
                    READ_FIELD: "false",
                    WRITE_FIELD: "true",
                },
                clear=False,
        ):
            error = self.assert_config_error(
                "REDIS_UNAVAILABLE",
                lambda: PVAmountConfigProvider(redis).load_run_config(),
            )

        self.assertIsInstance(error.__cause__, ConnectionError)
        self.assertEqual({}, redis.hashes)
        self.assertEqual({}, redis.strings)

    # endregion

    # region TC-FLAG-09～11：run-freeze 与 admission

    def test_tc_flag_09_run_freezes_01_when_provider_later_changes_to_11(self):
        provider = SequenceProvider(
            [
                make_config(False, True, 20),
                make_config(True, True, 21),
            ]
        )

        session = PVAmountRunSession.start(provider)

        self.assertEqual("01", session.config.state)
        self.assertEqual(20, session.config.config_version)
        self.assertEqual(1, provider.calls)
        self.assertFalse(hasattr(session, "refresh"))

    def test_tc_flag_10_next_production_run_rejects_unapproved_11(self):
        provider = SequenceProvider([make_config(True, True, 21)])

        self.assert_config_error(
            "V2_STATE_NOT_AUTHORIZED",
            lambda: PVAmountRunSession.start(provider),
        )
        self.assertEqual(1, provider.calls)

    def test_tc_flag_11_cross_version_or_checksum_fails_loud(self):
        for mutation, code in (
                ("pointer_version", "VERSION_MISMATCH"),
                ("snapshot_version", "VERSION_MISMATCH"),
                ("checksum", "CHECKSUM_MISMATCH"),
        ):
            with self.subTest(mutation=mutation):
                redis = FakeRedis()
                fields = redis.seed(read_v2=False, write_v2=True, version=30)

                if mutation == "pointer_version":
                    redis.hashes[f"{SNAPSHOT_KEY_PREFIX}31"] = fields
                    redis.strings[ACTIVE_POINTER_KEY] = (
                        "31:"
                        + redis.strings[ACTIVE_POINTER_KEY].split(":", 1)[1]
                    )
                elif mutation == "snapshot_version":
                    fields[VERSION_FIELD] = "31"
                else:
                    fields[CHECKSUM_FIELD] = "0" * 64

                self.assert_config_error(
                    code,
                    lambda: PVAmountConfigProvider(redis).load_run_config(),
                )

    # endregion

    # region TC-FLAG-12～13：bootstrap 与 consumer 静态检查

    def test_tc_flag_12_bootstrap_atomically_publishes_complete_01(self):
        redis = FakeRedis()

        config = publish_manual_bootstrap(
            1,
            expected_active_version=None,
            redis_client=redis,
        )

        self.assertEqual("01", config.state)
        self.assertEqual(1, config.config_version)
        self.assertEqual(["publish", "load"], redis.eval_calls)
        self.assertEqual(1, redis.publish_count)
        self.assertEqual(
            {
                READ_FIELD,
                WRITE_FIELD,
                VERSION_FIELD,
                LOAD_MODE_FIELD,
                SOURCE_FIELD,
                CHECKSUM_FIELD,
            },
            set(redis.hashes[f"{SNAPSHOT_KEY_PREFIX}1"]),
        )
        self.assertIn("redis.call", LOAD_SNAPSHOT_LUA)
        self.assertIn("redis.call", PUBLISH_SNAPSHOT_LUA)

    def test_tc_flag_13_consumers_do_not_read_flags_directly(self):
        root = Path(__file__).resolve().parents[3]
        excluded = {
            root / "Redishelper" / "PVAmountConfigProvider.py",
            root / "Redishelper" / "PVAmountConfigBootstrap.py",
        }
        violations = []

        for path in root.rglob("*.py"):
            relative = path.relative_to(root)
            if (
                    path in excluded
                    or "tests" in relative.parts
                    or "Test" in relative.parts
                    or "__pycache__" in relative.parts
            ):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value in {
                    READ_FIELD,
                    WRITE_FIELD,
                }:
                    violations.append(f"{relative}:{node.lineno}")

        self.assertEqual([], violations)

    # endregion

    # region TC-FLAG-22～23：stale 与并发 CAS

    def test_tc_flag_22_stale_publish_fails_and_active_is_unchanged(self):
        redis = FakeRedis()
        publish_manual_bootstrap(
            10,
            expected_active_version=None,
            redis_client=redis,
        )
        active_before = redis.strings[ACTIVE_POINTER_KEY]

        self.assert_config_error(
            "STALE_CONFIG_VERSION",
            lambda: publish_manual_bootstrap(
                10,
                expected_active_version=10,
                redis_client=redis,
            ),
        )
        self.assert_config_error(
            "STALE_CONFIG_VERSION",
            lambda: publish_manual_bootstrap(
                9,
                expected_active_version=10,
                redis_client=redis,
            ),
        )

        self.assertEqual(active_before, redis.strings[ACTIVE_POINTER_KEY])
        self.assertNotIn(f"{SNAPSHOT_KEY_PREFIX}9", redis.hashes)

    def test_tc_flag_23_concurrent_cas_has_no_lost_update(self):
        redis = FakeRedis()
        publish_manual_bootstrap(
            100,
            expected_active_version=None,
            redis_client=redis,
        )
        barrier = threading.Barrier(3)
        results = []
        results_lock = threading.Lock()

        def publish(version):
            barrier.wait()
            try:
                config = publish_manual_bootstrap(
                    version,
                    expected_active_version=100,
                    redis_client=redis,
                )
                result = ("ok", config.config_version)
            except PVAmountConfigError as exc:
                result = ("error", exc.code)
            with results_lock:
                results.append(result)

        threads = [
            threading.Thread(target=publish, args=(101,)),
            threading.Thread(target=publish, args=(102,)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

        successes = [value for status, value in results if status == "ok"]
        failures = [value for status, value in results if status == "error"]
        active_version = int(redis.strings[ACTIVE_POINTER_KEY].split(":", 1)[0])

        self.assertEqual(1, len(successes))
        self.assertEqual(["STALE_CONFIG_VERSION"], failures)
        self.assertEqual(successes[0], active_version)
        self.assertIn(active_version, {101, 102})
        self.assertEqual(
            active_version,
            PVAmountConfigProvider(redis).load_run_config().config_version,
        )
        self.assertIn("compare_decimal", PUBLISH_SNAPSHOT_LUA)
        self.assertNotIn("tonumber", PUBLISH_SNAPSHOT_LUA)

    # endregion


if __name__ == "__main__":
    unittest.main(verbosity=2)
