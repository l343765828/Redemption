"""Regression contract for the Loop Engineering Core refactor.

TEST-01..TEST-10 execute the real PowerShell state-machine behavior suite when
PowerShell is available (the production Windows self-hosted runner).  Static
contract tests below remain as supplemental guards.

Python 3.6-compatible by design because the Windows self-hosted runner may
expose Python 3.6 as its default interpreter.
"""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / ".github" / "workflows" / "loop-engine.yml"
ROUND = ROOT / ".github" / "workflows" / "loop-round.yml"
STATE = ROOT / ".loop-engine" / "loop-state.ps1"
RUNNER = ROOT / ".loop-engine" / "claude-verifier-runner.ps1"
REWORK = ROOT / ".loop-engine" / "producer-rework-override.md"
BEHAVIOR = ROOT / "tests" / "loop-engine" / "loop-core-behavior.ps1"


def text(path):
    return path.read_text(encoding="utf-8")


def run_behavior(scenario):
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell runtime is required for Loop Core behavior scenarios")
    env = os.environ.copy()
    env["MAINREPO"] = str(ROOT)
    proc = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BEHAVIOR), "-Scenario", scenario],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert proc.returncode == 0, proc.stdout


def test_01_opus_round1_bug_found_routes_only_to_codex_rework_round2():
    run_behavior("test-01-opus-r1-bug")


def test_02_opus_round2_bug_found_routes_only_to_codex_rework_round3():
    run_behavior("test-02-opus-r2-bug")


def test_03_opus_round3_bug_found_pauses_and_never_creates_cycle2_automatically():
    run_behavior("test-03-opus-r3-bug")


def test_04_any_opus_no_bug_enters_fable_final_review():
    run_behavior("test-04-opus-no-bug-fable")


def test_05_fable_final_pass_completes_work():
    run_behavior("test-05-fable-pass")


def test_06_fable_final_reject_pauses_and_never_auto_routes_to_codex():
    run_behavior("test-06-fable-reject")


def test_07_manual_next_cycle_reuses_branch_and_prior_candidate_sha():
    run_behavior("test-07-next-cycle")


def test_08_opus_round_limit_next_cycle_passes_original_work_plus_round3_findings():
    run_behavior("test-08-opus-findings-next-cycle")


def test_09_fable_reject_next_cycle_passes_fable_findings_then_returns_to_opus():
    run_behavior("test-09-fable-findings-next-cycle")


def test_10_agents_are_controller_invoked_and_never_directly_chain_each_other():
    run_behavior("test-10-controller-only")


def test_r2_01_legacy_fable_reject_remains_barrier_after_later_completed_opus_round():
    run_behavior("r2-01-legacy-fable-reject-then-later-complete")


def test_r2_01_schema4_self_heals_even_after_later_completed_opus_round():
    run_behavior("r2-01-schema4-self-heal-after-later-complete")


def test_r2_02_pre_marker_fable_reject_uses_legacy_period_provenance():
    run_behavior("r2-02-pre-marker-fable-reject")

def test_r3_01_later_fable_pass_supersedes_earlier_fable_reject():
    run_behavior("r3-01-fable-reject-then-later-fable-pass")


def test_r3_03_paused_fable_reject_prepare_is_idempotent():
    run_behavior("r3-03-paused-fable-reject-idempotent")


def test_r4_01_completed_after_rework_prepare_is_idempotent():
    run_behavior("r4-01-completed-after-rework-idempotent")


def test_normalized_machine_results_are_explicit_controller_outputs():
    round_text = text(ROUND)
    state = text(STATE)
    for token in ('opus_result', 'fable_result', 'NO_BUG', 'BUG_FOUND', 'FINAL_PASS', 'FINAL_REJECT'):
        assert token in round_text or token in state


def test_core_state_has_required_stage_names_and_pause_reason():
    state = text(STATE)
    for token in (
        'CODEX_PRODUCE',
        'CODEX_REWORK',
        'OPUS_REVIEW',
        'FABLE_FINAL_REVIEW',
        'PAUSED_AWAITING_USER',
        'COMPLETED',
        'pause_reason',
    ):
        assert token in state


def test_candidate_branch_is_work_level_and_not_cycle_suffixed():
    state = text(STATE)
    engine = text(ENGINE)
    assert 'candidate_branch' in state
    assert 'cycle_start_sha' in state
    assert 'work02-cycle' not in engine.lower()
    assert 'work02-cycle' not in state.lower()


def test_legacy_uat_verdicts_are_adapted_not_used_for_core_routing():
    engine = text(ENGINE)
    round_text = text(ROUND)
    # Retained v20 verification can still expose PRECHECK_PASS/REJECTED/PASS internally,
    # but top-level Loop Core routing must use normalized source-specific outputs.
    assert 'PRECHECK_PASS' in round_text
    assert 'REJECTED' in round_text
    assert "outputs.verdict == 'REJECTED'" not in engine
    assert "outputs.opus_result == 'BUG_FOUND'" in engine


def test_blocked_is_execution_status_not_a_third_reviewer_core_result():
    round_text = text(ROUND)
    state = text(STATE)
    assert '"BLOCKED" { "" }' in round_text
    assert 'STATUS=BLOCKED' in round_text
    assert '@("NO_BUG", "BUG_FOUND", "BLOCKED")' not in state
    assert '@("FINAL_PASS", "FINAL_REJECT", "BLOCKED")' not in state
