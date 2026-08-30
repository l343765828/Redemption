"""Loop v21 PVAM v2 configuration and role-isolation contracts."""

import json
import base64
import hashlib
import shutil
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ROLE_CONTRACT = REPO / ".loop-engine" / "agent-skill-contract.ps1"
PERIOD_VERIFIER = REPO / ".loop-engine" / "verify-proxy-period-evidence.ps1"
FINALIZER = REPO / ".loop-engine" / "finalize-pvam-v2-uat.ps1"
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
