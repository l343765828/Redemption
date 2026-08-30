"""Loop v21 PVAM v2 configuration and role-isolation contracts."""

import json
import base64
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ROLE_CONTRACT = REPO / ".loop-engine" / "agent-skill-contract.ps1"
PERIOD_VERIFIER = REPO / ".loop-engine" / "verify-proxy-period-evidence.ps1"
FINALIZER = REPO / ".loop-engine" / "finalize-pvam-v2-uat.ps1"
PREPARE_VERIFIER_STATE = REPO / ".loop-engine" / "prepare-verifier-state.ps1"
ROUND_WORKFLOW = REPO / ".github" / "workflows" / "loop-round.yml"
POOL_SHA = "a" * 64
SCOPE_SHA = "b" * 64
CANDIDATE_SHA = "c" * 40
ORIGINAL_CHECKSUM = "d" * 64
ACTIVATED_CHECKSUM = "e" * 64
EXECUTION_ID = "v21-config-test"


def policy():
    return json.loads(
        (REPO / ".loop-engine" / "uat-action-policy.json").read_text(
            encoding="utf-8",
        )
    )


def run_role_contract(role, project_skill_path=None):
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    assert powershell, "PowerShell runtime is required for Loop contract tests"
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROLE_CONTRACT),
        "-Role",
        role,
    ]
    if project_skill_path:
        command.extend(["-ProjectCommentSkillPath", project_skill_path])
    return subprocess.check_output(
        command,
        universal_newlines=True,
    )


def powershell_executable():
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    assert powershell, "PowerShell runtime is required for Loop contract tests"
    return powershell


def write_action_evidence(path, ordinal, action, request_body, required, semantic):
    request = json.dumps(
        request_body,
        separators=(",", ":"),
        sort_keys=True,
    )
    request_bytes = request.encode("utf-8")
    semantic_json = json.dumps(semantic, separators=(",", ":"), sort_keys=True)
    fields = [
        ("stage", "OPUS"),
        ("action", action),
        ("request_sha256", hashlib.sha256(request_bytes).hexdigest()),
        ("request_json_b64", base64.b64encode(request_bytes).decode("ascii")),
        ("stage_scope_sha256", SCOPE_SHA),
        ("uat_execution_id", EXECUTION_ID),
        ("stage_period_slot", "1"),
        ("stage_period_primary", "209906"),
        ("stage_period_secondary", "209907"),
        ("stage_period_pool_sha256", POOL_SHA),
        ("authorized_actions", "exec,test-data-write"),
        ("required_tokens", required),
        ("outcome", "SUCCESS"),
        ("exit_code", "0"),
        (
            "semantic_json_b64",
            base64.b64encode(semantic_json.encode("utf-8")).decode("ascii"),
        ),
    ]
    text = "".join("{}={}\n".format(key, value) for key, value in fields)
    (path / "action-{:03d}.log".format(ordinal)).write_text(
        text,
        encoding="utf-8",
    )


def write_empty_denied_evidence(path, ordinal, include_request_field=False, **overrides):
    fields = {
        "stage": "OPUS",
        "action": "",
        "request_sha256": hashlib.sha256(b"").hexdigest(),
        "stage_scope_sha256": SCOPE_SHA,
        "uat_execution_id": EXECUTION_ID,
        "stage_period_slot": "1",
        "stage_period_primary": "209906",
        "stage_period_secondary": "209907",
        "stage_period_pool_sha256": POOL_SHA,
        "authorized_actions": "exec",
        "required_tokens": "",
        "outcome": "DENIED",
        "error_class": "UAT_ACTION_POLICY_DENIED",
        "exit_code": "1",
    }
    fields.update(overrides)
    if include_request_field:
        fields["request_json_b64"] = ""
    path.mkdir(parents=True, exist_ok=True)
    text = "".join("{}={}\n".format(key, value) for key, value in fields.items())
    (path / "action-empty-{:03d}.log".format(ordinal)).write_text(
        text,
        encoding="utf-8",
    )


def write_proxy_evidence(path, ordinal, operation, semantic):
    required = "exec" if operation == "snapshot" else "exec,test-data-write"
    write_action_evidence(
        path,
        ordinal,
        "PVAmountV2Config",
        {"action": "PVAmountV2Config", "operation": operation},
        required,
        semantic,
    )


def write_config_evidence(path, operations):
    path.mkdir(parents=True, exist_ok=True)
    original_pointer = "7:{}".format(ORIGINAL_CHECKSUM)
    activated_pointer = "8:{}".format(ACTIVATED_CHECKSUM)
    semantics = {
        "snapshot": {
            "kind": "PVAmountV2ConfigResult",
            "operation": "snapshot",
            "original_pointer": original_pointer,
            "active_pointer": original_pointer,
            "state": "01",
            "config_version": 7,
            "checksum": ORIGINAL_CHECKSUM,
            "candidate_sha": CANDIDATE_SHA,
        },
        "activate": {
            "kind": "PVAmountV2ConfigResult",
            "operation": "activate",
            "original_pointer": original_pointer,
            "active_pointer": activated_pointer,
            "state": "11",
            "config_version": 8,
            "checksum": ACTIVATED_CHECKSUM,
            "candidate_sha": CANDIDATE_SHA,
            "snapshot_key": "pvam:amount_config:snapshot:8",
        },
        "restore": {
            "kind": "PVAmountV2ConfigResult",
            "operation": "restore",
            "original_pointer": original_pointer,
            "activated_pointer": activated_pointer,
            "active_pointer": original_pointer,
            "state": "01",
            "config_version": 7,
            "checksum": ORIGINAL_CHECKSUM,
            "candidate_sha": CANDIDATE_SHA,
            "snapshot_key": "pvam:amount_config:snapshot:8",
            "restored": True,
            "snapshot_deleted": True,
        },
    }
    for ordinal, operation in enumerate(operations, 1):
        write_proxy_evidence(path, ordinal, operation, semantics[operation])


def run_period_verifier(evidence_dir):
    return subprocess.Popen(
        [
            powershell_executable(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PERIOD_VERIFIER),
            "-Stage",
            "OPUS",
            "-EvidenceDir",
            str(evidence_dir),
            "-ExpectedSlot",
            "1",
            "-ExpectedPrimary",
            "209906",
            "-ExpectedSecondary",
            "209907",
            "-ExpectedPoolSha256",
            POOL_SHA,
            "-ExpectedAuthorizationScopeSha256",
            SCOPE_SHA,
            "-ExpectedExecutionId",
            EXECUTION_ID,
            "-PolicyPath",
            str(REPO / ".loop-engine" / "uat-action-policy.json"),
            "-VerificationMode",
            "ValidateExistingOnly",
            "-ExpectedCandidateSha",
            CANDIDATE_SHA,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    ).communicate()


def run_finalizer(evidence_dir):
    return subprocess.Popen(
        [
            powershell_executable(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(FINALIZER),
            "-EvidenceDir",
            str(evidence_dir),
            "-DryRun",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    ).communicate()


def test_real_role_contract_builder_isolates_skills():
    staged_skill = r"D:\staging\skills\redemption-comment-style\SKILL.md"
    producer = run_role_contract("PRODUCER", staged_skill)
    opus = run_role_contract("OPUS")
    fable = run_role_contract("FABLE")

    assert "superpowers:systematic-debugging" in producer
    assert "ponytail full" in producer.lower()
    assert "redemption-comment-style" in producer
    assert staged_skill in producer
    for reviewer in (opus, fable):
        assert "MUST NOT read, load, invoke, or claim" in reviewer
        assert "superpowers:systematic-debugging" not in reviewer
        assert "ponytail full" not in reviewer.lower()


def test_workflow_stages_project_skill_only_for_codex_producer():
    workflow = ROUND_WORKFLOW.read_text(encoding="utf-8")

    assert '".agents\\skills\\redemption-comment-style"' in workflow
    assert "Copy-Item -LiteralPath $projectSkillSource" in workflow
    assert "-ProjectCommentSkillPath $stagedProjectSkillEntry" in workflow
    assert "--add-dir $env:PRODUCER_OUTDIR" in workflow


def test_policy_change_starts_a_new_verifier_checkpoint():
    with tempfile.TemporaryDirectory(prefix="loop-policy-fingerprint-") as temp:
        root = Path(temp)
        worktree = root / "candidate"
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True)
        subprocess.run(["git", "init", str(worktree)], check=True)
        subprocess.run(
            ["git", "-C", str(worktree), "config", "user.email", "loop@test.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "config", "user.name", "Loop Test"],
            check=True,
        )
        (worktree / "README.md").write_text("checkpoint test\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(worktree), "add", "README.md"], check=True)
        subprocess.run(
            ["git", "-C", str(worktree), "commit", "-m", "checkpoint fixture"],
            check=True,
        )
        subprocess.run(["git", "-C", str(worktree), "branch", "-M", "smoke"], check=True)
        subprocess.run(
            ["git", "-C", str(worktree), "remote", "add", "origin", str(remote)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(worktree), "push", "-u", "origin", "smoke"],
            check=True,
        )
        candidate = subprocess.check_output(
            ["git", "-C", str(worktree), "rev-parse", "HEAD"],
            text=True,
        ).strip()

        outdir = root / "out"
        state_dir = outdir / "verifier-state" / "opus"
        history_dir = outdir / "verifier-history" / "opus"
        runtime_dir = outdir / "verifier-runtime" / "opus"
        inputs = root / "inputs"
        inputs.mkdir()
        for name in ("prompt.md", "override.md", "protocol.md"):
            (inputs / name).write_text(name + "\n", encoding="utf-8")
        (inputs / "settings.json").write_text(
            '{"permissions":{"allow":[],"deny":[]}}\n',
            encoding="utf-8",
        )
        policy = inputs / "policy.json"
        policy.write_text('{"version":1}\n', encoding="utf-8")
        master_agents = inputs / "AGENTS.md"
        master_agents.write_text("checkpoint fixture\n", encoding="utf-8")
        outdir.mkdir()
        (outdir / "pushed-sha.txt").write_text(candidate + "\n", encoding="utf-8")

        env = os.environ.copy()
        env.pop("PSModulePath", None)
        env.update(
            {
                "VERIFIER_STAGE": "OPUS",
                "VERIFIER_RESULT_FILE": str(outdir / "opus-result.txt"),
                "VERIFIER_STATE_DIR": str(state_dir),
                "VERIFIER_RUNTIME_DIR": str(runtime_dir),
                "VERIFIER_HISTORY_DIR": str(history_dir),
                "VERIFIER_PROGRESS": str(state_dir / "verifier-progress.json"),
                "VERIFIER_RESUME_CONTEXT": str(state_dir / "resume-context.md"),
                "VERIFIER_PROMPT": str(inputs / "prompt.md"),
                "VERIFIER_OVERRIDE": str(inputs / "override.md"),
                "VERIFIER_PROTOCOL": str(inputs / "protocol.md"),
                "VERIFIER_SETTINGS": str(inputs / "settings.json"),
                "UAT_ACTION_POLICY_FILE": str(policy),
                "UAT_ACTION_PROXY_ALLOW": "Bash(powershell.exe -File proxy.ps1)",
                "OUTDIR": str(outdir),
                "WORKTREE": str(worktree),
                "SSH_URL": str(remote),
                "BRANCH": "smoke",
                "CLAUDE_MODEL": "opus",
                "CLAUDE_EFFORT": "ultracode",
                "LOOP_UAT_PERIOD_SLOT": "1",
                "LOOP_UAT_PERIOD_PRIMARY": "990001",
                "LOOP_UAT_PERIOD_SECONDARY": "990002",
                "LOOP_UAT_PERIOD_POOL_SHA256": "a" * 64,
                "LOOP_UAT_AUTHORIZATION_ID": "TEST-AUTH",
                "LOOP_UAT_AUTHORIZED_ACTIONS": "debug,exec",
                "LOOP_UAT_AUTHORIZATION_SCOPE_SHA256": "b" * 64,
                "LOOP_UAT_AUTHORIZATION_ACTOR": "test-operator",
                "LOOP_UAT_AUTHORIZATION_STAGE": "OPUS",
                "LOOP_UAT_EXECUTION_ID": "c1-r1-opus-s1-" + candidate[:12],
                "LOOP_UAT_CYCLE_SCOPE_SHA256": "c" * 64,
                "LOOP_UAT_TARGET_NAMESPACE": "dask-operator",
                "LOOP_UAT_RESOURCE_SCOPE": "pod/dask-cluster-scheduler-*",
                "LOOP_UAT_TARGET_BRANCH": "smoke",
                "LOOP_UAT_IMPACT_SCOPE": "isolated-uat-only",
                "LOOP_MASTER_AGENTS_SNAPSHOT": str(master_agents),
                "LOOP_MASTER_AGENTS_SHA256": hashlib.sha256(
                    master_agents.read_bytes()
                ).hexdigest(),
                "GITHUB_ENV": str(root / "github-env.txt"),
                "GITHUB_RUN_ID": "1",
                "GITHUB_RUN_ATTEMPT": "1",
            }
        )
        command = [
            shutil.which("pwsh") or powershell_executable(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PREPARE_VERIFIER_STATE),
        ]

        subprocess.run(command, cwd=str(REPO), env=env, check=True)
        first = json.loads((state_dir / "verifier-progress.json").read_text("utf-8"))
        policy.write_text('{"version":2}\n', encoding="utf-8")
        env["GITHUB_RUN_ID"] = "2"
        subprocess.run(command, cwd=str(REPO), env=env, check=True)
        second = json.loads((state_dir / "verifier-progress.json").read_text("utf-8"))

        assert first["input_fingerprint"] != second["input_fingerprint"]
        assert second["uat_action_policy_sha256"] == hashlib.sha256(
            policy.read_bytes()
        ).hexdigest()
        assert any(history_dir.iterdir())
        github_env = (root / "github-env.txt").read_text(encoding="utf-8")
        assert github_env.rstrip().endswith("VERIFIER_ALREADY_COMPLETE=false")
        assert "VERIFIER_RESUME_MODE=NEW" in github_env.splitlines()[-5:]


def test_scheme_b_candidate_scope_is_exact_and_hunk_guards_are_removed():
    current = policy()
    required = {
        "Common/AmountModelAdapter.py",
        "Redishelper/PVAmountConfigProvider.py",
        "Redishelper/PVAmountConfigBootstrap.py",
        "Redishelper/PVAmountMigration.py",
        "User/UserStatsService.py",
        "User/PlacementIncrementalService.py",
        "User/EliteBonusService.py",
        "MessageConsumer/PvEventConsumer.py",
        "tests/pvam/WORK-PVAM-01/test_flag_factory_contract.py",
        "tests/pvam/WORK-PVAM-01C/test_flag_runtime_contract.py",
        "tests/pvam/WORK-PVAM-02/test_amount_migration.py",
        "tests/pvam/WORK-PVAM-02/test_three_chain_scheme_b.py",
    }

    assert required.issubset(set(current["git_change_allowlist"]))
    assert "tests/*" not in current["git_change_allowlist"]
    assert "tests/**" not in current["git_change_allowlist"]
    assert current["git_hunk_allowlist"] == {}


def test_period_verifier_accepts_complete_pvam_v2_config_transaction(tmpdir):
    evidence_dir = Path(str(tmpdir)) / "complete"
    write_config_evidence(evidence_dir, ["snapshot", "activate", "restore"])

    stdout, stderr = run_period_verifier(evidence_dir)

    assert "[PROXY-EVIDENCE] PASS" in stdout, stderr


def test_period_verifier_rejects_unrestored_pvam_v2_activation(tmpdir):
    evidence_dir = Path(str(tmpdir)) / "unrestored"
    write_config_evidence(evidence_dir, ["snapshot", "activate"])

    stdout, stderr = run_period_verifier(evidence_dir)

    assert "[PROXY-EVIDENCE] PASS" not in stdout
    assert "activation was not restored" in stderr


def test_period_verifier_accepts_controller_derived_empty_cleanup(tmpdir):
    evidence_dir = Path(str(tmpdir)) / "empty-controller-cleanup"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    write_action_evidence(
        evidence_dir,
        1,
        "RedisDeleteExactKeys",
        {"action": "RedisDeleteExactKeys", "controller_derived": True},
        "exec,test-data-write",
        {
            "kind": "RedisDeleteResult",
            "requested_count": 0,
            "deleted_count": 0,
            "remaining_count": 0,
            "remaining": [],
            "requested_keys": [],
            "cleanup_source": "controller-evidence",
        },
    )

    stdout, stderr = run_period_verifier(evidence_dir)

    assert "[PROXY-EVIDENCE] PASS" in stdout, stderr


def test_period_verifier_accepts_denied_empty_request_records(tmpdir):
    evidence_dir = Path(str(tmpdir)) / "denied-empty-request"
    write_empty_denied_evidence(evidence_dir, 1)
    write_empty_denied_evidence(evidence_dir, 2, include_request_field=True)

    stdout, stderr = run_period_verifier(evidence_dir)

    assert "[PROXY-EVIDENCE] PASS" in stdout, stderr
    assert "successful_actions=0" in stdout


def test_period_verifier_rejects_broader_missing_request_exceptions(tmpdir):
    mutations = [
        {"outcome": "FAILED"},
        {"error_class": "PROXY_FAILURE"},
        {"action": "Readyz"},
        {"request_sha256": "0" * 64},
        {"exit_code": "0"},
        {"outcome": "denied"},
        {"error_class": "uat_action_policy_denied"},
        {"request_sha256": hashlib.sha256(b"").hexdigest().upper()},
        {"exit_code": "01"},
        {"exit_code": "+1"},
        {"exit_code": "1.0"},
        {"exit_code": "1e0"},
        {"exit_code": " 1"},
    ]
    for ordinal, mutation in enumerate(mutations, 1):
        evidence_dir = Path(str(tmpdir)) / "invalid-empty-{:03d}".format(ordinal)
        write_empty_denied_evidence(evidence_dir, ordinal, **mutation)

        stdout, stderr = run_period_verifier(evidence_dir)

        assert "[PROXY-EVIDENCE] PASS" not in stdout
        assert "missing request_json_b64" in stderr


def test_finalizer_dry_run_reports_pending_activation(tmpdir):
    evidence_dir = Path(str(tmpdir)) / "pending-finalizer"
    write_config_evidence(evidence_dir, ["snapshot", "activate"])

    stdout, stderr = run_finalizer(evidence_dir)

    assert not stderr
    assert (
        "RedisDeleteExactKeys -> ConsumerLifecycle restore -> "
        "PVAmountV2Config restore"
    ) in stdout


def test_finalizer_dry_run_is_idempotent_after_restore(tmpdir):
    evidence_dir = Path(str(tmpdir)) / "restored-finalizer"
    write_config_evidence(evidence_dir, ["snapshot", "activate", "restore"])

    stdout, stderr = run_finalizer(evidence_dir)

    assert not stderr
    assert "PVAM_V2_FINALIZER no-op" in stdout
