"""Controller-owned lifecycle helper for the UAT PvEventConsumer process.

The file is base64-transferred by ``uat-action-proxy.ps1`` and executed in
the current Dask scheduler container.  It never prints connection values or
persists them in the runtime state file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Any


RESULT_KIND = "ConsumerRuntimeControllerResult"
DEFAULT_RUNTIME_ROOT = "/tmp/pvam-uat-consumer"
EXECUTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{2,127}$")


class RuntimeContractError(RuntimeError):
    """Raised when the governed runtime contract is not satisfied."""


def _emit(result: dict[str, Any]) -> None:
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


def _require_text(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value or any(char in value for char in "\x00\r\n"):
        raise RuntimeContractError(f"{name} is missing or invalid")
    return value


def _execution_id(payload: dict[str, Any]) -> str:
    value = _require_text(payload, "execution_id")
    if not EXECUTION_ID_RE.fullmatch(value):
        raise RuntimeContractError("execution_id is outside the governed format")
    return value


def _runtime_paths(payload: dict[str, Any]) -> tuple[Path, Path, Path]:
    execution_id = _execution_id(payload)
    root = Path(str(payload.get("runtime_root") or DEFAULT_RUNTIME_ROOT))
    if not root.is_absolute():
        raise RuntimeContractError("runtime_root must be absolute")
    run_dir = root / execution_id
    return run_dir, run_dir / "runtime.json", run_dir / "consumer.log"


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def _read_state(path: Path, execution_id: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeContractError("runtime state is unreadable") from exc
    if not isinstance(state, dict) or state.get("execution_id") != execution_id:
        raise RuntimeContractError("runtime state execution identity mismatch")
    return state


def _proc_args(pid: int) -> list[str] | None:
    proc_path = Path("/proc") / str(pid) / "cmdline"
    if proc_path.is_file():
        try:
            return [
                item.decode("utf-8", errors="replace")
                for item in proc_path.read_bytes().split(b"\0")
                if item
            ]
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            return None
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return None
    return []


def _args_run_module(args: list[str] | None, module: str) -> bool:
    if args is None:
        return False
    if not args:
        return os.name == "nt"
    return any(
        args[index] == "-m"
        and index + 1 < len(args)
        and args[index + 1] == module
        for index in range(len(args))
    )


def _module_pids(module: str) -> list[int]:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    matches: list[int] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if _args_run_module(_proc_args(pid), module):
            matches.append(pid)
    return sorted(matches)


def _state_status(payload: dict[str, Any]) -> dict[str, Any]:
    execution_id = _execution_id(payload)
    _, state_path, _ = _runtime_paths(payload)
    state = _read_state(state_path, execution_id)
    if not state:
        return {
            "kind": RESULT_KIND,
            "operation": "status",
            "execution_id": execution_id,
            "running": False,
            "pid": None,
        }
    pid = int(state.get("pid") or 0)
    module = str(state.get("module") or "")
    running = pid > 0 and bool(module) and _args_run_module(_proc_args(pid), module)
    return {
        "kind": RESULT_KIND,
        "operation": "status",
        "execution_id": execution_id,
        "running": running,
        "pid": pid if running else None,
        "role": state.get("role"),
        "bound_period": state.get("bound_period"),
        "calc_month": state.get("calc_month"),
        "candidate_sha": state.get("candidate_sha"),
        "ledger_prefix": state.get("ledger_prefix"),
    }


def _validated_start_contract(payload: dict[str, Any]) -> dict[str, Any]:
    execution_id = _execution_id(payload)
    repo = Path(_require_text(payload, "repo_path"))
    if not repo.is_absolute() or not repo.is_dir():
        raise RuntimeContractError("repo_path must be an existing absolute directory")
    module = _require_text(payload, "module")
    if not MODULE_RE.fullmatch(module):
        raise RuntimeContractError("module is outside the governed format")
    candidate = _require_text(payload, "candidate_sha").lower()
    if not SHA_RE.fullmatch(candidate):
        raise RuntimeContractError("candidate_sha is invalid")
    role = _require_text(payload, "role").lower()
    if role not in {"primary", "secondary"}:
        raise RuntimeContractError("role must be primary or secondary")
    bound_period = int(payload.get("bound_period") or 0)
    calc_month = int(payload.get("calc_month") or 0)
    if bound_period < 1:
        raise RuntimeContractError("bound_period must be positive")
    if not re.fullmatch(r"[0-9]{6}", str(calc_month)) or not 1 <= calc_month % 100 <= 12:
        raise RuntimeContractError("calc_month must use YYYYMM format")
    ledger_prefix = _require_text(payload, "ledger_prefix")
    expected_prefix = f"pvam:uat:work02:{execution_id}:"
    if ledger_prefix != expected_prefix:
        raise RuntimeContractError("ledger_prefix is not bound to execution_id")
    kafka_bootstrap = _require_text(payload, "kafka_bootstrap")
    elite_rate_percent = _require_text(payload, "elite_rate_percent")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", elite_rate_percent):
        raise RuntimeContractError("elite_rate_percent is invalid")

    head = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={repo}",
            "-C",
            str(repo),
            "rev-parse",
            "HEAD",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if head.returncode != 0 or head.stdout.strip().lower() != candidate:
        raise RuntimeContractError("runtime repository candidate SHA mismatch")

    return {
        "execution_id": execution_id,
        "repo_path": str(repo),
        "module": module,
        "candidate_sha": candidate,
        "role": role,
        "bound_period": bound_period,
        "calc_month": calc_month,
        "ledger_prefix": ledger_prefix,
        "kafka_bootstrap": kafka_bootstrap,
        "elite_rate_percent": elite_rate_percent,
    }


def _build_child_environment(contract: dict[str, Any]) -> dict[str, str]:
    repo = contract["repo_path"]
    sys.path.insert(0, repo)
    try:
        from Model import Config as runtime_config
    finally:
        if sys.path and sys.path[0] == repo:
            sys.path.pop(0)

    values = {
        "PVAM_DASK_SCHEDULER": runtime_config.SCHEDULE_ADDRESS,
        "PVAM_REDIS_HOST": runtime_config.REDIS_HOST,
        "PVAM_REDIS_PORT": runtime_config.REDIS_PORT,
        "PVAM_REDIS_DB": runtime_config.REDIS_DB,
        "PVAM_REDIS_PASSWORD": runtime_config.REDIS_PASSWORD,
    }
    if any(value is None or str(value) == "" for value in values.values()):
        raise RuntimeContractError("runtime Model.Config is incomplete")

    env = os.environ.copy()
    existing_python_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = repo + (os.pathsep + existing_python_path if existing_python_path else "")
    env.update({name: str(value) for name, value in values.items()})
    env.update(
        {
            "PVAM_KAFKA_BOOTSTRAP": contract["kafka_bootstrap"],
            "PVAM_BOUND_PERIOD": str(contract["bound_period"]),
            "PVAM_CALC_MONTH": str(contract["calc_month"]),
            "PVAM_ELITE_RATE_PERCENT": contract["elite_rate_percent"],
            "PVAM_LEDGER_KEY_PREFIX": contract["ledger_prefix"],
            "LOOP_UAT_EXECUTION_ID": contract["execution_id"],
        }
    )
    return env


def _start(payload: dict[str, Any]) -> dict[str, Any]:
    contract = _validated_start_contract(payload)
    run_dir, state_path, log_path = _runtime_paths(payload)
    existing = _read_state(state_path, contract["execution_id"])
    if existing:
        pid = int(existing.get("pid") or 0)
        module = str(existing.get("module") or "")
        if pid > 0 and _args_run_module(_proc_args(pid), module):
            comparable = ("module", "candidate_sha", "role", "bound_period", "calc_month", "ledger_prefix")
            if all(existing.get(key) == contract.get(key) for key in comparable):
                result = _state_status(payload)
                result["operation"] = "start"
                result["reused"] = True
                return result
            raise RuntimeContractError("an existing governed Consumer has a different binding")

    foreign_pids = _module_pids(contract["module"])
    if foreign_pids:
        raise RuntimeContractError("an unmanaged PvEventConsumer process is already running")

    run_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    child_env = _build_child_environment(contract)
    with log_path.open("ab", buffering=0) as log_file:
        process = subprocess.Popen(
            [sys.executable, "-m", contract["module"]],
            cwd=contract["repo_path"],
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

    state = {
        key: contract[key]
        for key in (
            "execution_id",
            "repo_path",
            "module",
            "candidate_sha",
            "role",
            "bound_period",
            "calc_month",
            "ledger_prefix",
        )
    }
    state.update({"pid": process.pid, "started_at": time.time()})
    _atomic_write_json(state_path, state)
    time.sleep(float(payload.get("startup_probe_seconds") or 2.0))
    if process.poll() is not None:
        state.update({"stopped_at": time.time(), "exit_code": process.returncode})
        _atomic_write_json(state_path, state)
        raise RuntimeContractError("PvEventConsumer exited during startup probe")
    return {
        "kind": RESULT_KIND,
        "operation": "start",
        "execution_id": contract["execution_id"],
        "running": True,
        "pid": process.pid,
        "role": contract["role"],
        "bound_period": contract["bound_period"],
        "calc_month": contract["calc_month"],
        "candidate_sha": contract["candidate_sha"],
        "ledger_prefix": contract["ledger_prefix"],
        "reused": False,
    }


def _stop(payload: dict[str, Any]) -> dict[str, Any]:
    execution_id = _execution_id(payload)
    _, state_path, _ = _runtime_paths(payload)
    state = _read_state(state_path, execution_id)
    if not state:
        return {
            "kind": RESULT_KIND,
            "operation": "stop",
            "execution_id": execution_id,
            "stopped": True,
            "pid": None,
            "already_absent": True,
        }
    pid = int(state.get("pid") or 0)
    module = str(state.get("module") or "")
    args = _proc_args(pid) if pid > 0 else None
    if args is not None and not _args_run_module(args, module):
        raise RuntimeContractError("runtime PID no longer belongs to the governed module")
    if args is not None:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + float(payload.get("stop_timeout_seconds") or 30)
        while time.monotonic() < deadline and _proc_args(pid) is not None:
            time.sleep(0.2)
        if _proc_args(pid) is not None:
            os.kill(pid, signal.SIGKILL)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and _proc_args(pid) is not None:
                time.sleep(0.1)
        if _proc_args(pid) is not None:
            raise RuntimeContractError("PvEventConsumer did not terminate")
    state.update({"stopped_at": time.time(), "stopped": True})
    _atomic_write_json(state_path, state)
    return {
        "kind": RESULT_KIND,
        "operation": "stop",
        "execution_id": execution_id,
        "stopped": True,
        "pid": pid or None,
        "already_absent": args is None,
    }


def _logs(payload: dict[str, Any]) -> dict[str, Any]:
    execution_id = _execution_id(payload)
    _, _, log_path = _runtime_paths(payload)
    if not log_path.is_file():
        lines: list[str] = []
    else:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    safe_lines = [
        line.replace("\x00", "").replace("\r", "")[:4000]
        for line in lines
    ]
    return {
        "kind": RESULT_KIND,
        "operation": "logs",
        "execution_id": execution_id,
        "line_count": len(safe_lines),
        "lines": safe_lines,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 2:
        raise RuntimeContractError("usage: controller.py <operation> <payload-json>")
    operation = arguments[0].strip().lower()
    try:
        payload = json.loads(arguments[1])
    except (TypeError, ValueError) as exc:
        raise RuntimeContractError("payload JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise RuntimeContractError("payload JSON must be an object")

    if operation == "status":
        result = _state_status(payload)
    elif operation == "start":
        result = _start(payload)
    elif operation == "replace":
        _stop(payload)
        result = _start(payload)
        result["operation"] = "replace"
    elif operation == "stop":
        result = _stop(payload)
    elif operation == "logs":
        result = _logs(payload)
    else:
        raise RuntimeContractError("operation must be start, replace, status, stop, or logs")
    _emit(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "kind": RESULT_KIND,
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
