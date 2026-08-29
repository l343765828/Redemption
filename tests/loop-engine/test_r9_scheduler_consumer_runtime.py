"""Regression contract for the R9 scheduler-hosted UAT Consumer runtime."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / ".loop-engine" / "uat-action-policy.json"
READINESS_PATH = ROOT / ".loop-engine" / "uat-environment-readiness.json"
READINESS_GATE = ROOT / ".loop-engine" / "assert-uat-environment-readiness.ps1"
PROXY_PATH = ROOT / ".loop-engine" / "uat-action-proxy.ps1"
RUNTIME_CONTROLLER = ROOT / ".loop-engine" / "consumer-runtime-controller-r9.py"


def _function(source: str, name: str) -> str:
    match = re.search(rf"(?m)^function\s+{re.escape(name)}\b[^\n]*\{{", source)
    if not match:
        raise AssertionError(f"PowerShell function not found: {name}")
    brace = source.find("{", match.start())
    depth = 0
    quote = None
    escaped = False
    for index in range(brace, len(source)):
        char = source[index]
        if escaped:
            escaped = False
            continue
        if char == "`":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
    raise AssertionError(f"PowerShell function not closed: {name}")


def test_policy_targets_the_real_scheduler_runtime() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    target = policy["consumer_runtime_target"]

    assert target["mode"] == "scheduler-pod-temporary-process"
    assert target["namespace"] == "dask-operator"
    assert target["host_deployment"] == "dask-cluster-scheduler"
    assert target["container"] == "scheduler"
    assert target["pod_name_prefix"] == "dask-cluster-scheduler-"
    assert target["repo_path"] == "/mnt/dask/Redemption/Redemption"
    assert target["module"] == "MessageConsumer.PvEventConsumer"
    assert target["kafka_bootstrap"] == "my-cluster-kafka-bootstrap.kafka-prod.svc:9092"
    assert target["dask_scheduler"] == "tcp://192.168.18.149:38786"
    assert target["redis_host"] == "192.168.18.149"
    assert target["redis_port"] == 36378
    assert target["redis_db"] == 0
    assert "redis_password" not in target
    assert target["calc_month_by_role"] == {
        "primary": 209906,
        "secondary": 209907,
    }
    assert target["elite_rate_percent"] == "15"


def test_readiness_describes_available_scheduler_process_lifecycle() -> None:
    readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    runtime = readiness["consumer_runtime"]

    assert runtime["status"] == "AVAILABLE"
    assert runtime["mode"] == "scheduler-pod-temporary-process"
    assert runtime["namespace"] == "dask-operator"
    assert runtime["host_deployment"] == "dask-cluster-scheduler"
    assert runtime["targets_configured"] is True
    assert runtime["deployment_required"] is False


def test_readiness_gate_accepts_confirmed_pool_and_scheduler_runtime(tmp_path: Path) -> None:
    shell = shutil.which("powershell")
    if not shell:
        pytest.skip("Windows PowerShell 5.1 is required")

    readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    readiness["period_pool"]["real_pvam_db_occupancy"] = "CONFIRMED"
    runtime_readiness = tmp_path / "readiness.json"
    runtime_readiness.write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(READINESS_GATE),
            "-Mode",
            "FullUat",
            "-Stage",
            "OPUS",
            "-ReadinessFile",
            str(runtime_readiness),
            "-PolicyFile",
            str(POLICY_PATH),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    assert proc.returncode == 0, proc.stdout
    assert "UAT_ENVIRONMENT_READINESS=READY mode=FullUat stage=OPUS" in proc.stdout


def test_consumer_lifecycle_controls_a_temporary_process_not_a_deployment() -> None:
    proxy = PROXY_PATH.read_text(encoding="utf-8")
    lifecycle = _function(proxy, "Invoke-ConsumerLifecycle")

    assert "consumer-runtime-controller-r9.py" in proxy
    assert "scheduler-pod-temporary-process" in lifecycle
    assert "runtime_mode='scheduler-pod-temporary-process'" in lifecycle
    assert "set','env" not in lifecycle
    assert "'scale'" not in lifecycle
    assert "'rollout','restart'" not in lifecycle
    assert "Assert-RequiredTokens @('exec') 'ConsumerLifecycle'" in lifecycle


def test_pod_git_checks_use_the_exact_repo_as_safe_directory() -> None:
    proxy = PROXY_PATH.read_text(encoding="utf-8")
    find_repo = _function(proxy, "Find-PodGitRepoByRemote")
    verify_repo = _function(proxy, "Verify-PodGitView")

    assert '"-c", ("safe.directory={0}" -f $repo)' in find_repo
    assert '"-c", ("safe.directory={0}" -f $repo)' in verify_repo


def test_runtime_controller_has_safe_status_and_stop_cli(tmp_path: Path) -> None:
    assert RUNTIME_CONTROLLER.exists()
    payload = {
        "execution_id": "TEST-EXECUTION-0001",
        "runtime_root": str(tmp_path),
    }
    proc = subprocess.run(
        ["python", str(RUNTIME_CONTROLLER), "status", json.dumps(payload)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    assert proc.returncode == 0, proc.stdout
    status = json.loads(proc.stdout.strip().splitlines()[-1])
    assert status["kind"] == "ConsumerRuntimeControllerResult"
    assert status["operation"] == "status"
    assert status["running"] is False
    assert "redis_password" not in proc.stdout.lower()


def test_auxiliary_python_loads_runtime_config_without_secret_arguments() -> None:
    proxy = PROXY_PATH.read_text(encoding="utf-8")
    wrapper = _function(proxy, "Invoke-RuntimePythonCommand")

    assert "from Model import Config as runtime_config" in wrapper
    assert '"PVAM_REDIS_PASSWORD"' in wrapper
    assert "runtime_config.REDIS_PASSWORD" in wrapper
    assert "Invoke-PodCommand" in wrapper
    assert "REDIS_PASSWORD" not in _function(proxy, "New-ConsumerRuntimePayload")

    for name in (
        "Invoke-ControllerUatProducer",
        "Invoke-RedisExactCleanup",
        "Invoke-RedisExactRead",
        "Invoke-RedisDbSize",
        "Invoke-PendingRecoveryProof",
        "Invoke-DispatchP99Proof",
        "Invoke-ConsumerObserve",
    ):
        assert "Invoke-RuntimePythonCommand" in _function(proxy, name), name


def test_scheduler_dask_profiles_use_policy_pinned_target() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    profiles = policy["exec_profiles"]

    for name in ("dask-scheduler-info", "dask-actor-inventory", "dask-list-datasets"):
        profile = profiles[name]
        assert profile["repo_cwd"] is True
        assert profile["runtime_target"] == "dask_scheduler"
        command = " ".join(profile["command"])
        assert "from Model import Config" not in command
        assert "sys.argv[1]" in command


def test_lifecycle_requires_the_discovered_repo_to_match_policy() -> None:
    lifecycle = _function(PROXY_PATH.read_text(encoding="utf-8"), "Invoke-ConsumerLifecycle")

    assert "Consumer runtime repository path mismatch" in lifecycle
    assert "target.repo_path" in lifecycle


def test_runtime_actions_resolve_the_unique_scheduler_pod_from_policy() -> None:
    proxy = PROXY_PATH.read_text(encoding="utf-8")
    resolver = _function(proxy, "Resolve-ConsumerRuntimeTarget")

    assert "Get-ConsumerLifecycleSelectedPods" in resolver
    assert "runtime pod is controller governed" in resolver
    assert "runtime container is controller governed" in resolver
    assert "runtime repository path mismatch" in resolver
    for name in (
        "Invoke-KafkaScenarioProduce",
        "Invoke-ConsumerObserve",
        "Invoke-RedisExactCleanup",
        "Invoke-RedisExactRead",
        "Invoke-RedisDbSize",
    ):
        assert "Resolve-ConsumerRuntimeTarget" in _function(proxy, name), name
