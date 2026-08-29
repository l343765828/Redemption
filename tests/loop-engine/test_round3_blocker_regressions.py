"""Regression coverage for the Cycle 1 / Round 3 environment blockers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CONTROLLER_PATH = ROOT / ".loop-engine" / "consumer-runtime-controller-r9.py"
PROXY_PATH = ROOT / ".loop-engine" / "uat-action-proxy.ps1"
POLICY_PATH = ROOT / ".loop-engine" / "uat-action-policy.json"
VERIFY_PATH = ROOT / ".loop-engine" / "verify-proxy-period-evidence.ps1"


def _load_controller():
    spec = importlib.util.spec_from_file_location(
        "round3_consumer_runtime_controller", CONTROLLER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_state(tmp_path: Path) -> tuple[dict[str, str], Path]:
    execution_id = "TEST-EXECUTION-0001"
    run_dir = tmp_path / execution_id
    run_dir.mkdir()
    state_path = run_dir / "runtime.json"
    state_path.write_text(
        json.dumps(
            {
                "execution_id": execution_id,
                "module": "MessageConsumer.PvEventConsumer",
                "pid": 699,
            }
        ),
        encoding="utf-8",
    )
    return {"execution_id": execution_id, "runtime_root": str(tmp_path)}, state_path


class Round3BlockerRegressionTests(unittest.TestCase):
    def test_stop_treats_a_zombie_as_already_exited(self) -> None:
        controller = _load_controller()
        with tempfile.TemporaryDirectory() as temp_dir:
            payload, state_path = _runtime_state(Path(temp_dir))
            with (
                mock.patch.object(controller, "_proc_state", return_value="Z", create=True),
                mock.patch.object(controller, "_proc_args", return_value=[]),
                mock.patch.object(controller, "_args_run_module", return_value=False),
                mock.patch.object(
                    controller.os,
                    "kill",
                    side_effect=AssertionError("a zombie process must not be signalled"),
                ),
            ):
                result = controller._stop(payload)

            self.assertTrue(result["stopped"])
            self.assertTrue(result["already_absent"])
            self.assertEqual("Z", result["process_state"])
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(saved["stopped"])
            self.assertEqual("zombie", saved["stopped_reason"])

    def test_startup_failure_reports_exit_code_and_log_tail(self) -> None:
        controller = _load_controller()
        with tempfile.TemporaryDirectory() as temp_dir:
            payload, state_path = _runtime_state(Path(temp_dir))
            run_dir = state_path.parent
            state_path.unlink()
            (run_dir / "consumer.log").write_text("diagnostic-line\n", encoding="utf-8")
            contract = {
                "execution_id": payload["execution_id"],
                "repo_path": temp_dir,
                "module": "MessageConsumer.PvEventConsumer",
                "candidate_sha": "a" * 40,
                "role": "primary",
                "bound_period": 990007,
                "calc_month": 209906,
                "ledger_prefix": f"pvam:uat:work02:{payload['execution_id']}:",
            }

            class ExitedProcess:
                pid = 123
                returncode = 7

                @staticmethod
                def poll():
                    return 7

            with (
                mock.patch.object(controller, "_validated_start_contract", return_value=contract),
                mock.patch.object(controller, "_build_child_environment", return_value={}),
                mock.patch.object(controller, "_module_pids", return_value=[]),
                mock.patch.object(controller.subprocess, "Popen", return_value=ExitedProcess()),
                mock.patch.object(controller.time, "sleep"),
            ):
                with self.assertRaises(controller.RuntimeContractError) as raised:
                    controller._start(payload)

            message = str(raised.exception)
            self.assertIn("exit_code=7", message)
            self.assertIn("diagnostic-line", message)

    def test_stop_is_idempotent_after_runtime_was_already_restored(self) -> None:
        controller = _load_controller()
        with tempfile.TemporaryDirectory() as temp_dir:
            payload, state_path = _runtime_state(Path(temp_dir))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state.update({"stopped": True, "stopped_reason": "already_absent"})
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with (
                mock.patch.object(
                    controller,
                    "_proc_args",
                    side_effect=AssertionError("a restored PID must not be inspected"),
                ),
                mock.patch.object(
                    controller.os,
                    "kill",
                    side_effect=AssertionError("a restored PID must not be signalled"),
                ),
            ):
                result = controller._stop(payload)

            self.assertTrue(result["stopped"])
            self.assertTrue(result["already_absent"])

    def test_repo_backed_profiles_do_not_create_python_or_pytest_caches(self) -> None:
        proxy = PROXY_PATH.read_text(encoding="utf-8")

        self.assertIn("PYTHONDONTWRITEBYTECODE", proxy)
        self.assertIn("sys.dont_write_bytecode=True", proxy)
        self.assertIn("no:cacheprovider", proxy)
        self.assertIn("function Test-GitStatusLineIsGeneratedCache", proxy)
        self.assertGreaterEqual(proxy.count("Test-GitStatusLineIsGeneratedCache"), 3)
        self.assertIn("(^|/)__pycache__/", proxy)
        self.assertIn("(^|/)\\.pytest_cache(/|$)", proxy)

    def test_controller_producer_uses_the_candidate_payload_hash_contract(self) -> None:
        proxy = PROXY_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "json.dumps(item['payload'],ensure_ascii=False,sort_keys=True,"
            "separators=(',',':'),allow_nan=False)",
            proxy,
        )

    def test_lifecycle_logs_and_failed_action_output_are_auditable(self) -> None:
        proxy = PROXY_PATH.read_text(encoding="utf-8")

        self.assertIn("@('bind-primary','bind-secondary','status','restore','logs')", proxy)
        self.assertIn("elseif($op -eq 'logs')", proxy)
        self.assertIn("operation='logs'", proxy)
        self.assertIn("ErrorMessage", proxy)
        self.assertIn("ConsumerObserveDiagnostic", proxy)
        self.assertIn("consumer_log_sha256", proxy)
        self.assertIn("@($runtimeLogs.lines)", proxy)

    def test_userstats_business_record_is_exactly_governed_and_required_for_cleanup(self) -> None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        proxy = PROXY_PATH.read_text(encoding="utf-8")
        verifier = VERIFY_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "user_stats:Model.User.UserStats.UserStats:{period}:",
            policy["redis_exact_cleanup_prefixes"],
        )
        self.assertIn("function Test-KeyMatchesDeliveredBusinessRecord", proxy)
        self.assertIn(
            "user_stats:Model.User.UserStats.UserStats:${period}:$userId", verifier
        )
        self.assertIn("user_id=$userId", verifier)

    def test_dask_diagnostic_profiles_bound_client_waits(self) -> None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

        for name in ("dask-scheduler-info", "dask-actor-inventory", "dask-list-datasets"):
            command = " ".join(policy["exec_profiles"][name]["command"])
            self.assertIn("timeout='10s'", command)


if __name__ == "__main__":
    unittest.main()
