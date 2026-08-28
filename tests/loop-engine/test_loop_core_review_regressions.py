"""Regressions for the Loop Core external architecture review.

These are deliberately narrow source/packaging guards. Runtime state-machine
behavior is exercised by loop-core-behavior.ps1 on Windows PowerShell and is
wired into windows-smoke.ps1.
"""
from pathlib import Path
import json
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".loop-engine" / "loop-state.ps1"
SMOKE = ROOT / "tests" / "loop-engine" / "windows-smoke.ps1"
BEHAVIOR = ROOT / "tests" / "loop-engine" / "loop-core-behavior.ps1"


def text(path):
    return path.read_text(encoding="utf-8")


def function_body(source, function_name, next_function_name):
    start = source.index("function {}".format(function_name))
    end = source.index("function {}".format(next_function_name), start)
    return source[start:end]


def test_r2_01_migration_keeps_fable_reject_barrier_against_later_opus_rounds():
    state = text(STATE)
    upgrade = function_body(state, "Upgrade-CoreStateSchema", "Validate-Candidate")
    assert "fableTerminalRounds" in upgrade
    assert "latestFableTerminalRoundObject" in upgrade
    assert '@("FINAL_PASS", "FINAL_REJECT")' in upgrade
    assert '[string]$latestFableTerminalRoundObject.fable_result -eq "FINAL_REJECT"' in upgrade
    # Governance is based on the latest Fable terminal result, not the latest
    # completed Round, so a later Opus BUG_FOUND cannot erase FINAL_REJECT.
    assert 'latestCompletedRoundObject.fable_result -eq "FINAL_REJECT"' not in upgrade


def test_r2_02_legacy_classifier_uses_marker_presence_then_pre_marker_fable_slot_fallback():
    state = text(STATE)
    classifier = function_body(state, "Get-LegacyCoreResults", "Upgrade-CoreStateSchema")
    assert 'PSObject.Properties.Name -contains "final_audit_evidence_verified_verdict"' in classifier
    assert "final_audit_evidence_verified_verdict" in classifier
    assert "final_audit_uat_period_slot" in classifier




def test_r3_01_latest_fable_terminal_result_can_supersede_earlier_reject():
    state = text(STATE)
    upgrade = function_body(state, "Upgrade-CoreStateSchema", "Validate-Candidate")
    assert "fableTerminalRounds" in upgrade
    assert "latestFableTerminalRoundObject" in upgrade
    assert '[string]$latestFableTerminalRoundObject.fable_result -eq "FINAL_PASS"' in upgrade
    assert '[string]$latestFableTerminalRoundObject.fable_result -eq "FINAL_REJECT"' in upgrade
    # A historical reject must not be an unconditional first branch once a later
    # Fable FINAL_PASS exists in the same Cycle.
    assert 'if ($latestFableRejectedRoundObject)' not in upgrade


def test_r3_03_terminal_governance_rewrite_is_idempotent():
    state = text(STATE)
    upgrade = function_body(state, "Upgrade-CoreStateSchema", "Validate-Candidate")
    assert "$terminalGovernanceNeedsRewrite" in upgrade
    pass_start = upgrade.index('if ($latestFableTerminalRoundObject -and [string]$latestFableTerminalRoundObject.fable_result -eq "FINAL_PASS")')
    reject_start = upgrade.index('elseif ($latestFableTerminalRoundObject -and [string]$latestFableTerminalRoundObject.fable_result -eq "FINAL_REJECT")', pass_start)
    final_pass_branch = upgrade[pass_start:reject_start]
    assert "if ($terminalGovernanceNeedsRewrite)" in final_pass_branch

def test_lc04_windows_smoke_executes_real_loop_core_behavior_suite():
    smoke = text(SMOKE)
    assert BEHAVIOR.exists()
    assert "loop-core-behavior.ps1" in smoke
    assert "-Scenario all" in smoke


def test_lc05_round_keeps_consumed_findings_and_records_produced_findings_separately():
    state = text(STATE)
    complete = function_body(state, "Complete-RoundInternal", "Reconcile-State")
    assert 'Ensure-Property $RoundObject "produced_findings_source"' in complete
    assert 'Ensure-Property $RoundObject "produced_findings_ref"' in complete
    # Round-level findings_ref is the report consumed by Codex at BeginRound.
    assert 'Ensure-Property $RoundObject "findings_ref" $reportPath' not in complete


def test_r4_01_final_pass_clears_cycle_findings_cursor_at_write_time():
    state = text(STATE)
    complete = function_body(state, "Complete-RoundInternal", "Reconcile-State")
    start = complete.index('elseif ($OpusCoreResult -eq "NO_BUG" -and $FableCoreResult -eq "FINAL_PASS")')
    end = complete.index('elseif ($OpusCoreResult -eq "NO_BUG" -and $FableCoreResult -eq "FINAL_REJECT")', start)
    final_pass = complete[start:end]
    assert 'Ensure-Property $CycleObject "findings_source" $null' in final_pass
    assert 'Ensure-Property $CycleObject "findings_ref" $null' in final_pass


def test_r4_01_behavior_suite_covers_completed_after_rework_idempotence():
    behavior = text(BEHAVIOR)
    assert "r4-01-completed-after-rework-idempotent" in behavior
    assert "Invoke-R401CompletedAfterReworkIdempotent" in behavior


def test_lc07_package_hygiene_checker_is_executed_by_pytest_without_scanning_mutable_source(tmp_path):
    checker = ROOT / "tests" / "loop-engine" / "check-package-hygiene.py"
    assert checker.exists()

    clean_zip = tmp_path / "clean.zip"
    with zipfile.ZipFile(str(clean_zip), "w") as archive:
        archive.writestr("bundle/README.md", "clean\n")
    clean = subprocess.run(
        [sys.executable, str(checker), "--zip", str(clean_zip)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert clean.returncode == 0, clean.stdout
    assert "PACKAGE_HYGIENE=PASS" in clean.stdout

    dirty_zip = tmp_path / "dirty.zip"
    with zipfile.ZipFile(str(dirty_zip), "w") as archive:
        archive.writestr("bundle/tests/__pycache__/x.pyc", b"bad")
    dirty = subprocess.run(
        [sys.executable, str(checker), "--zip", str(dirty_zip)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert dirty.returncode == 1, dirty.stdout
    assert "PACKAGE_HYGIENE=FAIL" in dirty.stdout
    assert "__pycache__" in dirty.stdout


def test_preexisting_v20_candidate_sha_is_available_in_same_binding_step():
    state = text(STATE)
    exporter = function_body(state, "Export-UatWriteAuthorizationEnvironment", "New-UatWriteAuthorizationGrant")
    assert 'Write-GitHubEnv "LOOP_CANDIDATE_SHA" $candidateSha' in exporter
    assert '$env:LOOP_CANDIDATE_SHA = $candidateSha' in exporter


def test_consumer_proof_helpers_use_pod_prefix_and_string_pod_names_end_to_end():
    proxy = text(ROOT / ".loop-engine" / "uat-action-proxy.ps1")
    pending = function_body(proxy, "Invoke-PendingRecoveryProof", "Invoke-DispatchP99Proof")
    dispatch = function_body(proxy, "Invoke-DispatchP99Proof", "Invoke-UatProof")
    assert "Get-ConsumerLifecycleTarget $Policy $TargetNamespace $deployment $container" not in proxy
    assert proxy.count("Get-ConsumerLifecycleTarget $Policy $deployment $container") >= 2
    assert "Get-ConsumerLifecycleSelectedPods $deployment $target" not in pending
    assert "Get-ConsumerLifecycleSelectedPods $deployment $target" not in dispatch
    assert pending.count("Get-ConsumerLifecycleSelectedPods $deployment ([string]$target.pod_name_prefix)") == 2
    assert dispatch.count("Get-ConsumerLifecycleSelectedPods $deployment ([string]$target.pod_name_prefix)") == 1
    assert "$pods[0].Name" not in pending
    assert "$newPods[0].Name" not in pending
    assert "$pods[0].Name" not in dispatch


def test_behavior_suite_restores_caller_environment_after_windows_smoke_invocation():
    behavior = text(BEHAVIOR)
    assert "$originalEnvironment = @{}" in behavior
    assert "finally {" in behavior
    assert "SetEnvironmentVariable" in behavior



def test_r6_readiness_contract_records_only_confirmed_environment_facts():
    readiness_path = ROOT / ".loop-engine" / "uat-environment-readiness.json"
    assert readiness_path.exists()
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert readiness["schema_version"] == 1
    assert readiness["historical_compatibility"]["v8_v9_r2_history"] == "NOT_PRESENT"
    assert readiness["period_pool"]["reservation_status"] == "CONFIRMED"
    assert readiness["period_pool"]["real_pvam_db_occupancy"] == "NOT_VERIFIED"
    assert readiness["consumer_lifecycle"]["status"] == "UNAVAILABLE"
    assert readiness["consumer_lifecycle"]["targets_configured"] is False
    assert readiness["consumer_lifecycle"]["deployment_required"] is False
    assert readiness["windows_runtime_gate"] == "PENDING_SELF_HOSTED_RUNNER"


def test_r6_full_uat_gate_has_deterministic_fail_closed_blockers_without_invalidating_core():
    gate = ROOT / ".loop-engine" / "assert-uat-environment-readiness.ps1"
    assert gate.exists()
    source = text(gate)
    assert 'ValidateSet("Core", "FullUat")' in source
    assert 'UAT_PERIOD_DB_OCCUPANCY_NOT_CONFIRMED' in source
    assert 'CONSUMER_LIFECYCLE_UNAVAILABLE' in source
    assert 'UAT_ENVIRONMENT_READINESS=READY' in source
    assert 'UAT_ENVIRONMENT_READINESS=BLOCKED' in source
    assert 'if ($Mode -eq "Core")' in source
    assert 'exit 2' in source


def test_r6_workflow_runs_full_uat_readiness_gate_before_opus_and_fable_verifier_runner():
    workflow = text(ROOT / ".github" / "workflows" / "loop-round.yml")
    assert 'UAT_READINESS_FILE:' in workflow
    assert 'UAT_READINESS_SCRIPT:' in workflow
    assert workflow.count('-Mode FullUat -Stage "OPUS"') == 1
    assert workflow.count('-Mode FullUat -Stage "FABLE"') == 1
    opus_gate = workflow.index('-Mode FullUat -Stage "OPUS"')
    opus_runner = workflow.index('& $env:VERIFIER_RUNNER_SCRIPT', opus_gate)
    assert opus_gate < opus_runner
    fable_gate = workflow.index('-Mode FullUat -Stage "FABLE"')
    fable_runner = workflow.index('& $env:VERIFIER_RUNNER_SCRIPT', fable_gate)
    assert fable_gate < fable_runner


def test_r6_windows_smoke_validates_core_readiness_without_requiring_full_uat_environment():
    smoke = text(SMOKE)
    assert 'UAT_READINESS_FILE' in smoke
    assert 'UAT_READINESS_SCRIPT' in smoke
    assert '-Mode Core' in smoke
    assert '-Mode FullUat' not in smoke


def test_r7_complete_round_uses_canonical_core_results_and_treats_caller_results_as_assertions_only():
    state = text(STATE)
    assert "function Get-CanonicalCoreResults" in state
    complete = function_body(state, "Complete-Round", "Summarize-Loop")
    assert "$canonicalVerdict = Get-CanonicalVerdict" in complete
    assert "Get-CanonicalCoreResults $cycleObject $roundObject $canonicalVerdict" in complete
    assert "canonical Opus result mismatch" in complete
    assert "canonical Fable result mismatch" in complete
    assert "Complete-RoundInternal $state $cycleObject $roundObject $canonicalVerdict $canonicalOpusResult $canonicalFableResult" in complete
    assert "Complete-RoundInternal $state $cycleObject $roundObject $RoundVerdict $OpusCoreResult $FableCoreResult" not in complete


def test_r7_behavior_suite_covers_canonical_result_mismatch_fail_closed_cases():
    behavior = text(BEHAVIOR)
    for scenario in (
        "r7-fable-reject-cannot-be-claimed-as-opus-bug",
        "r7-opus-reject-cannot-be-claimed-as-fable-reject",
        "r7-pass-cannot-carry-nonfinal-pass-results",
        "r7-blocked-source-mismatch-fails-closed",
    ):
        assert scenario in behavior
    assert "Assert-CompleteRoundMismatchLeavesStateUntouched" in behavior


def test_r8_reconcile_native_rounds_use_canonical_core_results_not_legacy_classifier():
    state = text(STATE)
    reconcile = function_body(state, "Reconcile-State", "Initialize-LegacyState")
    assert "Test-CanonicalVerifierComplete" in reconcile
    assert "Get-CanonicalVerdict" in reconcile
    assert "Get-CanonicalCoreResults $cycleObject $roundObject $recoveredVerdict" in reconcile
    assert "Get-LegacyCoreResults" not in reconcile


def test_r8_complete_round_internal_never_reclassifies_intentionally_empty_canonical_results():
    state = text(STATE)
    complete = function_body(state, "Complete-RoundInternal", "Reconcile-State")
    assert "Get-LegacyCoreResults" not in complete
    assert "if (-not $OpusCoreResult)" not in complete
    assert "canonical BLOCKED result may intentionally leave Opus/Fable results empty" in complete


def test_r8_legacy_import_keeps_explicit_legacy_classifier_only_on_historical_path():
    state = text(STATE)
    legacy_import = function_body(state, "Initialize-LegacyState", "Prepare-Loop")
    assert "Get-LegacyCoreResults $roundObject $legacyVerdict" in legacy_import
    canonical = function_body(state, "Get-CanonicalCoreResults", "Write-CycleSummary")
    assert "legacy_imported_from_pre_v8" in canonical
    assert "return Get-LegacyCoreResults $RoundObject $CanonicalVerdict" in canonical


def test_r8_behavior_suite_covers_native_reconcile_canonical_source_cases():
    behavior = text(BEHAVIOR)
    for scenario in (
        "r8-reconcile-opus-reject-ignores-retained-fable-marker",
        "r8-reconcile-round3-opus-reject-keeps-opus-round-limit",
        "r8-reconcile-opus-blocked-ignores-retained-fable-marker",
        "r8-reconcile-fable-pass-stays-final-pass",
        "r8-reconcile-fable-reject-stays-final-reject",
        "r8-reconcile-fable-blocked-stays-blocked",
    ):
        assert scenario in behavior
    assert "Invoke-R8ReconcileOpusRejectIgnoresRetainedFableMarker" in behavior
    assert "Invoke-R8ReconcileRound3OpusRejectKeepsOpusRoundLimit" in behavior
    assert "Invoke-R8ReconcileOpusBlockedIgnoresRetainedFableMarker" in behavior


def test_r8_schema4_native_rounds_are_not_legacy_result_backfilled_after_reconcile():
    state = text(STATE)
    upgrade = function_body(state, "Upgrade-CoreStateSchema", "Validate-Candidate")
    assert "$allowLegacyResultBackfill" in upgrade
    assert "$schema -lt 4" in upgrade
    assert "legacy_imported_from_pre_v8" in upgrade
    assert 'if ($allowLegacyResultBackfill -and [string]$roundObject.verdict -and -not [string]$roundObject.opus_result)' in upgrade
