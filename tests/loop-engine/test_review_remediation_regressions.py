"""Regression tests for the F-01/F-03/F-05 review remediation."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
ROUND_WORKFLOW = WORKFLOWS / "loop-round.yml"
POLICY_PATH = ROOT / ".loop-engine" / "uat-action-policy.json"
CONTROLLER_PATH = ROOT / ".loop-engine" / "consumer-runtime-controller-r9.py"
WINDOWS_SMOKE = ROOT / "tests" / "loop-engine" / "windows-smoke.ps1"
PRODUCER_OVERRIDE = ROOT / ".loop-engine" / "producer-override.md"
REWORK_OVERRIDE = ROOT / ".loop-engine" / "producer-rework-override.md"


def _load_runtime_controller():
    spec = importlib.util.spec_from_file_location(
        "loop_engine_consumer_runtime_controller_r9", CONTROLLER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_one_manual_workflow_is_a_loop_controller() -> None:
    controllers = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        source = path.read_text(encoding="utf-8")
        if (
            "workflow_dispatch:" in source
            and (
                (
                    "& codex exec" in source
                    and "VERIFIER_RUNNER_SCRIPT" in source
                )
                or "uses: ./.github/workflows/loop-round.yml" in source
            )
        ):
            controllers.append(path.name)

    assert controllers == ["loop-engine.yml"]
    assert not (WORKFLOWS / "loop-engine-once.yml").exists()


def test_runtime_endpoints_are_policy_pinned_and_dask_profiles_use_them() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    target = policy["consumer_runtime_target"]

    assert target["dask_scheduler"] == "tcp://192.168.18.149:38786"
    assert target["redis_host"] == "192.168.18.149"
    assert target["redis_port"] == 36378
    assert target["redis_db"] == 0
    assert "redis_password" not in target

    for name in ("dask-scheduler-info", "dask-actor-inventory", "dask-list-datasets"):
        profile = policy["exec_profiles"][name]
        assert profile["runtime_target"] == "dask_scheduler"
        command = " ".join(profile["command"])
        assert "from Model import Config" not in command
        assert "sys.argv[1]" in command


def test_candidate_config_cannot_redirect_policy_pinned_runtime(tmp_path: Path) -> None:
    model = tmp_path / "Model"
    model.mkdir()
    (model / "__init__.py").write_text("", encoding="utf-8")
    (model / "Config.py").write_text(
        "\n".join(
            (
                "SCHEDULE_ADDRESS = 'tcp://192.168.18.149:38786'",
                "REDIS_HOST = '192.168.18.149'",
                "REDIS_PORT = 36378",
                "REDIS_DB = 9",
                "REDIS_PASSWORD = 'candidate-secret'",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    controller = _load_runtime_controller()
    contract = {
        "repo_path": str(tmp_path),
        "dask_scheduler": "tcp://192.168.18.149:38786",
        "redis_host": "192.168.18.149",
        "redis_port": 36378,
        "redis_db": 0,
        "kafka_bootstrap": "kafka:9092",
        "bound_period": 990001,
        "calc_month": 209906,
        "elite_rate_percent": "15",
        "ledger_prefix": "pvam:uat:work02:TEST-EXECUTION-0001:",
        "execution_id": "TEST-EXECUTION-0001",
    }

    sys.modules.pop("Model.Config", None)
    sys.modules.pop("Model", None)
    try:
        with pytest.raises(
            controller.RuntimeContractError,
            match="runtime Model.Config does not match policy-pinned endpoints",
        ):
            controller._build_child_environment(contract)
    finally:
        sys.modules.pop("Model.Config", None)
        sys.modules.pop("Model", None)


def test_windows_smoke_does_not_reject_append_only_pool_growth() -> None:
    smoke = WINDOWS_SMOKE.read_text(encoding="utf-8")

    assert "$pairs.Count -lt 10" in smoke
    assert "$pairs.Count -ne 10" not in smoke


def test_producer_staging_is_bound_only_after_the_runner_starts() -> None:
    workflow = yaml.safe_load(ROUND_WORKFLOW.read_text(encoding="utf-8"))
    round_job = workflow["jobs"]["round"]

    assert "PRODUCER_OUTDIR" not in round_job["env"]

    bind_step = next(
        step
        for step in round_job["steps"]
        if step.get("name") == "Bind producer staging directory"
    )
    script = bind_step["run"]
    assert "$env:RUNNER_TEMP" in script
    assert "$env:GITHUB_ENV" in script
    assert "-Encoding utf8 -Append" in script


def test_producer_can_write_only_to_controller_staging() -> None:
    workflow = ROUND_WORKFLOW.read_text(encoding="utf-8")

    assert "--add-dir $env:PRODUCER_OUTDIR" in workflow
    assert "--add-dir $env:OUTDIR" not in workflow
    assert '--output-last-message "$env:PRODUCER_OUTDIR\\codex-final.txt"' in workflow
    assert '$finalPath = "$env:PRODUCER_OUTDIR\\codex-final.txt"' in workflow
    assert 'Join-Path $env:PRODUCER_OUTDIR "IMPLEMENTATION_HANDOFF.md"' in workflow
    assert "producer staging directory must be outside the candidate worktree" in workflow
    assert '[IO.File]::Copy($handoffPath, "$env:OUTDIR\\IMPLEMENTATION_HANDOFF.md", $true)' in workflow

    for override_path in (PRODUCER_OVERRIDE, REWORK_OVERRIDE):
        override = override_path.read_text(encoding="utf-8")
        assert "PRODUCER_OUTDIR" in override
        assert "D:\\Redemption\\Redemption\\.loop-output\\IMPLEMENTATION_HANDOFF.md" not in override
