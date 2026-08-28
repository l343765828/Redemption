from pathlib import Path
import hashlib
import re
import yaml

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / '.github' / 'workflows' / 'loop-engine.yml'
ROUND = ROOT / '.github' / 'workflows' / 'loop-round.yml'
STATE = ROOT / '.loop-engine' / 'loop-state.ps1'
PREPARE = ROOT / '.loop-engine' / 'prepare-verifier-state.ps1'
RUNNER = ROOT / '.loop-engine' / 'claude-verifier-runner.ps1'
PROTOCOL = ROOT / '.loop-engine' / 'verifier-checkpoint-protocol.md'
FABLE_PROXY = ROOT / '.loop-engine' / 'fable-uat-proxy.ps1'
PROTECTED_HASH = ROOT / '.loop-engine' / 'protected-evidence-hash.ps1'
README = ROOT / 'README-LOOP-ENGINE-FINAL.md'
V10_REVIEW = ROOT / 'REVIEW-FIXES-v10.md'
V10_DESIGN = ROOT / 'docs' / 'LOOP-ENGINE-V10-DESIGN.md'


def text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_workflows_yaml_parse_and_entrypoint_contract():
    with ENGINE.open('r', encoding='utf-8') as f:
        engine = yaml.safe_load(f)
    with ROUND.open('r', encoding='utf-8') as f:
        round_wf = yaml.safe_load(f)
    assert isinstance(engine, dict) and 'jobs' in engine
    assert isinstance(round_wf, dict) and 'jobs' in round_wf
    assert 'workflow_dispatch' in engine[True] if True in engine else 'workflow_dispatch' in engine['on']
    assert 'workflow_call' in round_wf[True] if True in round_wf else 'workflow_call' in round_wf['on']


def test_single_line_codex_verdict_is_forced_to_array():
    s = text(ROUND)
    assert re.search(r'\$lines\s*=\s*@\(\s*\$final\s+-split', s, re.S)
    assert '([string]$lines[-1]).Trim()' in s


def test_reconcile_never_discards_unverified_pushed_sha():
    s = text(STATE)
    assert 'pushed-sha.txt exists but remote verification failed' in s
    assert 'refusing to delete or reuse the recovery pointer' in s
    assert 'pushed-sha.txt does not match local/remote candidate' in s


def test_commit_without_pointer_is_detected_from_producer_base_sha():
    s = text(STATE)
    assert 'producer_base_sha' in s
    assert '[RECOVERY-BLOCKED] local HEAD advanced beyond producer_base_sha' in s
    assert 'Manually push HEAD to the candidate branch' in s
    round_text = text(ROUND)
    assert 'HEAD advanced beyond producer_base_sha' in round_text


def test_rerun_failed_job_guidance_is_explicit():
    s = text(STATE)
    assert 'Do not use GitHub Re-run failed jobs for a durable Loop Engine round' in s
    assert 'dispatch loop-engine.yml again with run_mode=auto' in s


def test_resume_verifier_has_phase_and_verdict_guard():
    s = text(STATE)
    assert 'resume-verifier is allowed only for phase VERIFYING or COMPLETE+BLOCKED' in s
    assert re.search(r'phase.*VERIFYING', s, re.S)
    assert re.search(r'phase.*COMPLETE.*verdict.*BLOCKED', s, re.S)


def test_loop_state_save_is_atomic_same_directory_replace():
    s = text(STATE)
    assert 'loop-state.tmp.' in s
    assert '[IO.File]::Replace' in s
    assert '[IO.File]::Move' in s


def test_begin_round_cleans_legacy_publish_clone():
    s = text(STATE)
    assert 'pvam-work02-publish' in s
    assert 'Remove-PathFailClosed $legacyPublish' in s


def test_resume_candidate_checks_loop_ledger_and_remote_before_verifier():
    s = text(ROUND)
    assert 'state candidate' in s.lower()
    assert 'remote branch SHA' in s
    assert 'Windows PowerShell contract smoke' in s
    assert 'does not match loop-state candidate' in s


def test_verifier_final_files_must_agree_with_ledger_before_skip():
    s = text(PREPARE)
    assert '[FINAL-CONSISTENCY]' in s
    assert 'disagrees with verifier-progress.json final_verdict' in s
    assert 'VERIFIER_RESULT_FILE' in s
    assert 'refusing to mark verifier already complete' in s


def test_readme_deploy_and_operator_recovery_contract_is_complete():
    s = text(README)
    assert '- `README-LOOP-ENGINE-FINAL.md`' in s
    assert '- `tests/loop-engine/test_final_bundle.py`' in s
    assert '- `tests/loop-engine/windows-smoke.ps1`' in s
    assert 'Do not use **Re-run failed jobs**' in s
    assert 'run_mode = auto' in s
    assert 'uat-result.txt` disagrees' in s
    assert 'Fresh run after PASS' in s
    assert 'remove the whole `.loop-output` durable state set' in s


def test_current_test_targets_multicycle_files():
    assert ENGINE.name == "loop-engine.yml"
    assert ROUND.name == "loop-round.yml"
    assert README.name == "README-LOOP-ENGINE-FINAL.md"


def test_existing_permission_and_native_stderr_p0_fixes_remain():
    prepare = text(PREPARE)
    runner = text(RUNNER)
    assert 'both OPUS and FABLE start from a fresh permission object' in prepare
    assert '$ErrorActionPreference = "Continue"' in runner
    assert '$previousErrorActionPreference' in runner


def test_multicycle_contract_stays_three_rounds_per_cycle_with_manual_cycle_boundary():
    # Formal Loop Core governance supersedes the historical v20 behavior:
    # Round 3 BUG_FOUND pauses; Cycle N+1 is only a workflow_dispatch next-cycle action.
    state = text(STATE)
    engine = text(ENGINE)
    assert '$MaxRoundsPerCycle = 3' in state
    assert 'next-cycle' in engine
    assert 'PAUSED_AWAITING_USER' in state
    assert 'OPUS_ROUND_LIMIT' in state


def test_file_replace_passes_real_null_backup_path_on_windows_powershell():
    state = text(STATE)
    smoke = text(ROOT / 'tests' / 'loop-engine' / 'windows-smoke.ps1')
    assert '[IO.File]::Replace($tempPath, $StateFile, [NullString]::Value)' in state
    assert '[IO.File]::Replace($temp, $target, [NullString]::Value)' in smoke
    assert '[IO.File]::Replace($tempPath, $StateFile, $null)' not in state
    assert '[IO.File]::Replace($temp, $target, $null)' not in smoke

POOL = ROOT / '.loop-engine' / 'uat-period-pool.json'
SMOKE = ROOT / 'tests' / 'loop-engine' / 'windows-smoke.ps1'


def test_v6_period_pool_is_explicit_finite_and_unique():
    assert POOL.exists(), 'v6 must ship an explicit UAT period pool'
    import json
    pool = json.loads(text(POOL))
    assert pool['schema_version'] == 1
    pairs = pool['pairs']
    assert len(pairs) == 10
    assert [p['slot'] for p in pairs] == list(range(1, 11))
    periods = []
    for pair in pairs:
        assert pair['primary_period'] > 0
        assert pair['secondary_period'] > 0
        assert pair['primary_period'] != pair['secondary_period']
        periods.extend([pair['primary_period'], pair['secondary_period']])
    assert len(periods) == len(set(periods))
    assert periods == list(range(990001, 990021))


def test_v6_loop_state_allocates_and_persists_period_pair_per_round():
    s = text(STATE)
    assert 'UAT_PERIOD_POOL_FILE' in s
    assert 'uat_period_slot' in s
    assert 'uat_period_primary' in s
    assert 'uat_period_secondary' in s
    assert 'uat_period_pool_sha256' in s
    assert 'PERIOD_POOL_EXHAUSTED' in s
    assert 'Get-UsedPeriodSlots' in s
    assert 'Ensure-RoundPeriodAllocation' in s
    assert 'LOOP_UAT_PERIOD_PRIMARY' in s
    assert 'LOOP_UAT_PERIOD_SECONDARY' in s
    assert 'schema_version = 3' in s


def test_v6_verifier_fingerprint_and_ledger_are_bound_to_period_allocation():
    s = text(PREPARE)
    for token in (
        'LOOP_UAT_PERIOD_SLOT',
        'LOOP_UAT_PERIOD_PRIMARY',
        'LOOP_UAT_PERIOD_SECONDARY',
        'LOOP_UAT_PERIOD_POOL_SHA256',
        'uat_period_slot',
        'uat_period_primary',
        'uat_period_secondary',
        'uat_period_pool_sha256',
    ):
        assert token in s
    assert 'schema=8' in s


def test_v6_claude_prompt_has_authoritative_period_override_for_old_literals():
    s = text(RUNNER)
    assert 'AUTHORITATIVE LOOP UAT PERIOD ALLOCATION' in s
    assert '990001' in s and '990002' in s
    assert 'LOOP_UAT_PERIOD_PRIMARY' in s
    assert 'LOOP_UAT_PERIOD_SECONDARY' in s
    assert 'Do not allocate a new period pair while resuming this verifier stage' in s


def test_v6_checkpoint_protocol_requires_immutable_round_period_pair():
    s = text(PROTOCOL)
    assert 'UAT period allocation' in s
    assert 'LOOP_UAT_PERIOD_PRIMARY' in s
    assert 'LOOP_UAT_PERIOD_SECONDARY' in s
    assert 'must not change on resume' in s.lower()


def test_v6_controller_does_not_start_downstream_jobs_after_cancel():
    s = text(ENGINE)
    assert s.count('!cancelled()') >= 3
    # Controller-level always() was the cancellation hazard; it must be gone.
    assert 'always() &&' not in s


def test_v6_artifacts_are_minimal_retained_and_non_authoritative():
    round_text = text(ROUND)
    engine_text = text(ENGINE)
    assert 'retention-days: 14' in round_text
    assert 'retention-days: 14' in engine_text
    assert 'continue-on-error: true' in round_text
    assert 'continue-on-error: true' in engine_text
    # Never upload the entire runtime tree as an artifact.
    assert 'path: D:\\Redemption\\Redemption\\.loop-output\\\n' not in round_text
    assert 'path: D:\\Redemption\\Redemption\\.loop-output\\\n' not in engine_text
    assert 'py311-deps' not in round_text
    assert 'loop-state.json' in round_text
    assert 'verifier-state' in round_text


def test_v6_windows_smoke_validates_period_pool_before_codex():
    s = text(SMOKE)
    assert 'UAT_PERIOD_POOL_FILE' in s
    assert 'PERIOD-POOL-SMOKE' in s
    assert 'primary_period' in s
    assert 'secondary_period' in s


def test_v6_legacy_verifier_metadata_is_bound_before_final_reconcile():
    s = text(STATE)
    assert 'Bind-LegacyVerifierPeriodMetadata' in s
    assert 'legacy verifier progress bound to durable UAT period allocation' in s
    assert re.search(r'Ensure-RoundPeriodAllocation.*Bind-LegacyVerifierPeriodMetadata', s, re.S)


def test_v6_durable_state_rejects_duplicate_period_slots_across_rounds():
    s = text(STATE)
    assert 'Assert-NoDuplicateRoundPeriodAllocations' in s
    assert 'duplicate durable UAT period slot' in s
    assert re.search(r'Upgrade-StatePeriodSchema.*Assert-NoDuplicateRoundPeriodAllocations', s, re.S)


def test_v7_legacy_verifier_period_binding_uses_atomic_write():
    s = text(STATE)
    assert 'function Write-Utf8NoBomAtomic' in s
    assert 'Write-Utf8NoBomAtomic $progressPath' in s
    assert 'Write-Utf8NoBom $progressPath' not in s


def test_v7_prepare_uploads_reconciled_cycle_evidence():
    s = text(ENGINE)
    prepare_block = s.split('  prepare:', 1)[1].split('\n  round1:', 1)[0]
    assert 'Upload reconciled cycle evidence' in prepare_block
    assert 'continue-on-error: true' in prepare_block
    assert 'retention-days: 14' in prepare_block
    assert '.loop-output\\loop-state.json' in prepare_block
    assert '.loop-output\\cycles\\cycle-${{ steps.state.outputs.cycle }}\\' in prepare_block


def test_v7_round_uses_local_master_agents_snapshot_for_both_agents():
    round_text = text(ROUND)
    runner = text(RUNNER)
    assert 'MASTER_AGENTS_FILE: D:\\Redemption\\Redemption\\AGENTS.md' in round_text
    assert 'Bind local master AGENTS.md snapshot' in round_text
    assert 'rev-parse --abbrev-ref HEAD' in round_text
    assert 'must be on local master' in round_text
    assert 'master-AGENTS.md' in round_text
    assert 'LOOP_MASTER_AGENTS_SNAPSHOT' in round_text
    assert 'LOOP_MASTER_AGENTS_SHA256' in round_text
    assert 'AUTHORITATIVE LOCAL MASTER AGENTS.md' in round_text
    assert 'AUTHORITATIVE LOCAL MASTER AGENTS.md' in runner
    assert 'LOOP_MASTER_AGENTS_SNAPSHOT' in runner
    assert 'LOOP_MASTER_AGENTS_SHA256' in runner


def test_v7_verifier_fingerprint_includes_master_agents_snapshot_hash():
    s = text(PREPARE)
    assert 'LOOP_MASTER_AGENTS_SNAPSHOT' in s
    assert 'LOOP_MASTER_AGENTS_SHA256' in s
    assert 'master_agents_sha256=' in s


def test_v7_same_round_resume_reuses_existing_master_agents_snapshot():
    s = text(ROUND)
    assert 'reusing pinned master AGENTS snapshot for this logical round' in s
    assert 'new logical round snapshots local master AGENTS.md once' in s


def test_v7_readme_documents_master_agents_and_prepare_artifact_contract():
    s = text(README)
    assert 'local master `AGENTS.md`' in s
    assert 'same Round' in s and 'snapshot' in s
    assert 'prepare reconcile artifact' in s


def test_v7_round_ledger_binds_master_agents_hash_and_summary_records_it():
    s = text(STATE)
    assert 'master_agents_sha256' in s
    assert 'pinned master AGENTS snapshot hash differs from durable round ledger' in s
    assert 'master_agents_sha256 = [string]$RoundObject.master_agents_sha256' in s


def test_v7_prepare_verifier_state_saves_progress_atomically():
    s = text(PREPARE)
    assert 'verifier-progress.tmp.' in s
    assert '[IO.File]::Replace($tempPath, $Path, [NullString]::Value)' in s
    assert '[IO.File]::Move($tempPath, $Path)' in s


def test_v7_checkpoint_protocol_pins_master_agents_per_round():
    s = text(PROTOCOL)
    assert 'master AGENTS.md snapshot' in s
    assert 'must not change on resume' in s.lower()
    assert 'LOOP_MASTER_AGENTS_SHA256' in s


def test_v7_verifier_resume_checks_master_agents_hash_against_ledger():
    s = text(PREPARE)
    assert 'verifier-progress.json master_agents_sha256 disagrees with the pinned Round snapshot' in s


def test_v8_declares_opus_iterative_verifier_and_fable_final_auditor_models():
    s = text(ROUND)
    assert 'OPUS_CLAUDE_MODEL: opus' in s
    assert 'FABLE_CLAUDE_MODEL: fable' in s
    assert 'OPUS_CLAUDE_EFFORT:' in s
    assert 'FABLE_CLAUDE_EFFORT:' in s


def test_v8_opus_result_contract_never_grants_final_pass():
    s = text(ROUND)
    assert 'opus-result.txt' in s
    assert 'PRECHECK_PASS' in s
    assert re.search(r'@\("PRECHECK_PASS",\s*"REJECTED",\s*"BLOCKED"\)', s)
    opus_gate = s.split('Gate Opus verifier verdict', 1)[1].split('Allocate Fable final-audit period', 1)[0]
    assert '"PASS"' not in opus_gate
    assert 'run_fable' in opus_gate


def test_v8_fable_is_only_path_to_final_pass():
    s = text(ROUND)
    assert 'Fable final audit' in s
    assert re.search(r'@\("PASS",\s*"REJECTED",\s*"BLOCKED"\)', s)
    assert "steps.opus_gate.outputs.run_fable == 'true'" in s
    assert 'FABLE_CLAUDE_MODEL' in s


def test_v8_keeps_single_formal_uat_report_filename():
    all_text = '\n'.join(text(p) for p in (ROUND, STATE, PREPARE, RUNNER, PROTOCOL))
    assert 'UAT_REPORT.md' in all_text
    assert 'OPUS_UAT_REPORT.md' not in all_text
    assert 'FABLE_FINAL_AUDIT_REPORT.md' not in all_text


def test_v8_loop_state_allocates_fresh_final_audit_period_pair():
    s = text(STATE)
    assert 'AllocateFinalAuditPeriod' in s
    assert 'final_audit_uat_period_slot' in s
    assert 'final_audit_uat_period_primary' in s
    assert 'final_audit_uat_period_secondary' in s
    assert 'LOOP_FINAL_UAT_PERIOD_PRIMARY' in s
    assert 'LOOP_FINAL_UAT_PERIOD_SECONDARY' in s
    assert 'PERIOD_POOL_EXHAUSTED' in s


def test_v8_duplicate_period_guard_covers_opus_and_fable_allocations():
    s = text(STATE)
    assert 'final_audit_uat_period_slot' in s
    assert 'duplicate durable UAT period slot' in s
    assert 'Get-UsedPeriodSlots' in s
    assert re.search(r'Get-UsedPeriodSlots.*final_audit_uat_period_slot', s, re.S)


def test_v8_verifier_checkpoint_is_stage_aware_and_separate():
    s = text(PREPARE)
    assert 'VERIFIER_STAGE' in s
    assert 'verifier_stage=' in s
    assert 'schema=8' in s
    round_text = text(ROUND)
    assert r'.loop-output\verifier-state\opus' in round_text
    assert r'.loop-output\verifier-state\fable' in round_text
    assert r'.loop-output\verifier-history\opus' in round_text
    assert r'.loop-output\verifier-history\fable' in round_text


def test_v8_runner_has_explicit_stage_roles_and_result_contracts():
    s = text(RUNNER)
    assert 'OPUS ITERATIVE VERIFIER' in s
    assert 'FABLE FINAL AUDITOR' in s
    assert 'PRECHECK_PASS' in s
    assert 'Fable is the only verifier stage allowed to produce final PASS' in s
    assert 'preserve the exact existing UAT_REPORT.md content' in s


def test_v8_fable_uses_fresh_final_audit_period_context():
    s = text(RUNNER)
    assert 'LOOP_FINAL_UAT_PERIOD_SLOT' in s
    assert 'LOOP_FINAL_UAT_PERIOD_PRIMARY' in s
    assert 'LOOP_FINAL_UAT_PERIOD_SECONDARY' in s
    assert 'FABLE' in s and 'final-audit' in s.lower()


def test_v8_workflow_pins_opus_report_before_fable_and_checks_prefix_preservation():
    s = text(ROUND)
    assert 'Pin Opus UAT_REPORT before Fable' in s
    assert 'UAT_REPORT.pre-fable.md' in s
    assert 'Verify Fable preserved Opus report' in s
    assert '.StartsWith(' in s


def test_v8_opus_rejection_skips_fable_and_becomes_round_result():
    s = text(ROUND)
    gate = s.split('Gate Opus verifier verdict', 1)[1].split('Allocate Fable final-audit period', 1)[0]
    assert 'REJECTED' in gate and 'BLOCKED' in gate
    assert 'uat-result.txt' in gate
    assert 'run_fable=false' in gate


def test_loop_core_fable_rejection_pauses_instead_of_reworking_next_round():
    # Supersedes the v8 behavior. The formal Loop Core decision is now that
    # Fable FINAL_REJECT is a Cycle governance boundary, never an automatic
    # Codex rework trigger. Only Opus BUG_FOUND may advance Round 1->2->3.
    engine = text(ENGINE)
    state = text(STATE)
    assert "needs.round1.outputs.opus_result == 'BUG_FOUND'" in engine
    assert "needs.round2.outputs.opus_result == 'BUG_FOUND'" in engine
    assert "needs.round1.outputs.verdict == 'REJECTED'" not in engine
    assert "needs.round2.outputs.verdict == 'REJECTED'" not in engine
    assert 'FABLE_FINAL_REJECT' in state
    assert 'PAUSED_AWAITING_USER' in state


def test_v8_legacy_v6_v7_direct_verifier_checkpoint_is_archived_for_opus_migration():
    s = text(PREPARE)
    assert 'legacy verifier-progress.json' in s
    assert 'legacy-pre-v8' in s
    assert 'VERIFIER_STAGE -eq "OPUS"' in s
    assert 'starting v8 Opus under the new staged verifier contract' in s


def test_v8_readme_documents_dual_stage_and_inflight_v6_migration():
    s = text(README)
    assert 'Opus' in s
    assert 'Fable' in s
    assert 'PRECHECK_PASS' in s
    assert 'UAT_REPORT.md' in s
    assert 'v6' in s.lower()
    assert '同一个 Candidate' in s or 'same Candidate' in s


def test_v8_fable_period_allocation_requires_durable_opus_precheck_pass():
    s = text(STATE)
    block = s.split('function Allocate-FinalAuditPeriod', 1)[1].split('function Complete-Round', 1)[0]
    assert 'opus-result.txt' in block
    assert 'PRECHECK_PASS' in block
    assert 'verifier-state\\opus\\verifier-progress.json' in block
    assert 'final_verdict' in block
    assert 'status' in block and 'COMPLETE' in block


def test_v8_state_upgrade_validates_existing_fable_allocation_without_allocating_new_one():
    s = text(STATE)
    block = s.split('function Upgrade-StatePeriodSchema', 1)[1].split('function New-CycleObject', 1)[0]
    assert 'final_audit_uat_period_slot' in block
    assert 'Ensure-FinalAuditPeriodAllocation' in block
    assert re.search(r'if \(\$hasFinalAuditAllocation\).*Ensure-FinalAuditPeriodAllocation', block, re.S)


def test_v8_opus_report_pin_is_created_atomically_before_fable():
    s = text(ROUND)
    block = s.split('Pin Opus UAT_REPORT before Fable', 1)[1].split('Select Fable final auditor stage', 1)[0]
    assert '$pin.tmp.$PID.' in block
    assert '[IO.File]::Move($temp, $pin)' in block
    assert 'finally' in block


def test_v8_round_archive_preserves_opus_stage_result():
    s = text(STATE)
    archive = s.split('function Archive-Round', 1)[1].split('function Complete-RoundInternal', 1)[0]
    assert 'opus-result.txt' in archive
    assert 'Copy-Item -Force' in archive


def test_v8_fable_report_marker_must_be_in_appended_suffix_not_opus_prefix():
    s = text(ROUND)
    block = s.split('Verify Fable preserved Opus report', 1)[1].split('Complete round and expose outputs', 1)[0]
    assert '## Fable Final Audit' in block
    assert 'suffix' in block.lower()
    assert 'expectedLength' in block


def test_v8_readme_warns_dual_stage_consumes_extra_period_slot_without_changing_pool_file():
    s = text(README)
    assert 'byte-for-byte' in s
    assert 'Fable consumes a second pool slot' in s
    assert 'five fully audited rounds' in s


def test_v8_inflight_legacy_verifier_rotates_to_fresh_opus_period_before_restarting_review():
    s = text(STATE)
    assert 'RotateLegacyVerifierPeriod' in s
    block = s.split('function Rotate-LegacyVerifierPeriod', 1)[1].split('function Allocate-FinalAuditPeriod', 1)[0]
    assert r'verifier-state\verifier-progress.json' in block
    assert 'retired_uat_period_allocations' in block
    assert 'Ensure-RoundPeriodAllocation' in block
    assert 'Export-RoundPeriodEnvironment' in block


def test_v8_retired_legacy_periods_remain_reserved_and_cannot_be_reused():
    s = text(STATE)
    block = s.split('function Get-RoundPeriodAllocations', 1)[1].split('function Get-UsedPeriodSlots', 1)[0]
    assert 'retired_uat_period_allocations' in block
    assert 'legacy retired' in block.lower()


def test_v8_workflow_rotates_legacy_period_before_opus_checkpoint_migration():
    s = text(ROUND)
    rotate_pos = s.index('Rotate legacy verifier UAT period for v8 Opus')
    opus_select_pos = s.index('Select Opus verifier stage')
    opus_prepare_pos = s.index('Prepare Opus verifier checkpoint')
    assert rotate_pos < opus_select_pos < opus_prepare_pos
    assert '-Operation RotateLegacyVerifierPeriod' in s[rotate_pos:opus_select_pos]


def test_v8_round_summary_records_retired_legacy_period_allocations():
    s = text(STATE)
    archive = s.split('function Archive-Round', 1)[1].split('function Complete-RoundInternal', 1)[0]
    assert 'retired_uat_period_allocations = @($RoundObject.retired_uat_period_allocations)' in archive


def test_v8_legacy_progress_matching_retired_period_is_accepted_after_rotation_crash_window():
    s = text(STATE)
    block = s.split('function Bind-LegacyVerifierPeriodMetadata', 1)[1].split('function Export-RoundPeriodEnvironment', 1)[0]
    assert 'retired_uat_period_allocations' in block
    assert 'matches a retired legacy UAT allocation' in block


def test_v8_period_pool_bytes_remain_v6_v7_compatible():
    assert hashlib.sha256(POOL.read_bytes()).hexdigest() == 'bc57a5276ebe23e73503dd3658ba715e859df33b98847fdd9663a2a50a9f08ba'

V9_REVIEW = ROOT / 'REVIEW-FIXES-v9.md'
AUTO_OVERRIDE = ROOT / '.loop-engine' / 'automated-override.md'
V9_DESIGN = ROOT / 'docs' / 'LOOP-ENGINE-V9-DESIGN.md'


def test_v9_windows_powershell_generic_list_returns_toarray():
    s = text(STATE)
    block = s.split('function Get-RoundPeriodAllocations', 1)[1].split('function Get-UsedPeriodSlots', 1)[0]
    assert 'return $items.ToArray()' in block
    assert 'return @($items)' not in block


def test_v9_windows_smoke_executes_real_state_machine_chain():
    s = text(SMOKE)
    assert '-Operation Prepare' in s
    assert '-Operation BeginRound' in s
    assert '-Operation SetCandidate' in s
    assert '-Operation AllocateFinalAuditPeriod' in s
    assert 'PRECHECK_PASS' in s
    assert 'verifier-state\\opus\\verifier-progress.json' in s
    assert '[STATE-MACHINE-SMOKE] PASS' in s


def test_v9_kubernetes_contract_uses_repo_k8s_paths_and_readyz():
    s = text(ROUND)
    assert r'KUBECTL_PATH: D:\Redemption\Redemption\K8S\kubectl.exe' in s
    assert r'KUBECONFIG_PATH: D:\Redemption\Redemption\K8S\admin.conf' in s
    assert 'get --raw=/readyz' in s or "get --raw='/readyz'" in s
    assert r'C:\Users\Administrator\AppData\Local\Temp\codex-pvam-kubectl\kubectl.exe' not in s


def test_v9_runner_overrides_legacy_base_prompt_kubernetes_paths():
    s = text(RUNNER)
    assert 'AUTHORITATIVE KUBERNETES RUNTIME CONTRACT' in s
    assert r'K8S\kubectl.exe' in s
    assert r'K8S\admin.conf' in s
    assert 'readyz' in s
    assert 'supersedes any root-level admin.conf' in s


def test_v9_ships_stage_aware_automated_override_without_legacy_result_conflict():
    assert AUTO_OVERRIDE.exists()
    s = text(AUTO_OVERRIDE)
    assert 'VERIFIER_STAGE' in s
    assert 'opus-result.txt' in s
    assert 'uat-result.txt' in s
    assert 'OPUS' in s and 'FABLE' in s
    assert 'OPUS MUST NOT write `.loop-output/uat-result.txt`' in s
    readme = text(README)
    assert '- `.loop-engine/automated-override.md`' in readme
    keep_block = readme.split('Keep your existing project-specific files:', 1)[1].split('Disable/remove', 1)[0]
    assert '.loop-engine/automated-override.md' not in keep_block


def test_v9_stage_aware_compatibility_context_explicitly_resolves_base_prompt_conflicts():
    s = text(RUNNER)
    assert 'BASE PROMPT COMPATIBILITY OVERRIDES' in s
    assert 'legacy instruction' in s.lower()
    assert 'opus-result.txt' in s
    assert 'uat-result.txt' in s
    assert 'K8S\\admin.conf' in s


def test_v9_effective_permissions_are_stage_scoped_not_broad_loop_output_write():
    s = text(PREPARE)
    assert 'Edit(.loop-output/**)' not in s
    assert 'Edit(.loop-output/UAT_REPORT.md)' in s
    assert 'Edit(.loop-output/opus-result.txt)' in s
    assert 'Edit(.loop-output/uat-result.txt)' in s
    assert 'Edit(.loop-output/verifier-state/opus/**)' in s
    assert 'Edit(.loop-output/verifier-state/fable/**)' in s
    assert 'Edit(.loop-output/loop-state.json)' in s
    assert 'Agent' in s


def test_v9_fable_permission_smoke_rejects_opus_and_loop_state_write_access():
    s = text(ROUND)
    block = s.split('Fable final auditor permission smoke gate', 1)[1].split('Fable final-audit environment preflight', 1)[0]
    assert 'Edit(.loop-output/UAT_REPORT.md)' in block
    assert 'Edit(.loop-output/uat-result.txt)' in block
    assert 'Edit(.loop-output/verifier-state/fable/**)' in block
    assert 'Edit(.loop-output/verifier-state/opus/**)' in block
    assert 'Edit(.loop-output/loop-state.json)' in block
    assert 'Agent' in block


def test_v9_opus_report_baseline_is_hashed_and_bound_to_durable_round_state():
    s = text(STATE)
    assert 'BindOpusReportBaseline' in s
    assert 'opus_report_sha256' in s
    assert 'opus_report_length' in s
    round_text = text(ROUND)
    pin = round_text.split('Pin Opus UAT_REPORT before Fable', 1)[1].split('Select Fable final auditor stage', 1)[0]
    assert '-Operation BindOpusReportBaseline' in pin
    assert 'Get-FileHash -Algorithm SHA256' in pin


def test_v9_fable_report_verification_uses_durable_hash_not_mutable_pin_only():
    s = text(ROUND)
    block = s.split('Verify Fable preserved Opus report', 1)[1].split('Complete round and expose outputs', 1)[0]
    assert 'opus_report_sha256' in block
    assert 'opus_report_length' in block
    assert 'ComputeHash' in block
    assert 'pinned Opus baseline hash differs from durable loop ledger' in block
    assert 'Fable modified the Opus report byte prefix' in block


def test_v9_new_round_clears_prior_stage_state_before_opus_can_reject():
    s = text(STATE)
    block = s.split('if ($ActionName -ne "resume-verifier")', 1)[1].split('Save-State $state', 1)[0]
    assert r'verifier-state\opus' in block
    assert r'verifier-state\fable' in block
    assert 'Remove-PathFailClosed $stageState' in block


def test_deployment_list_points_to_current_v12_not_historical_versions():
    s = text(README)
    deploy = s.split('## Deployment', 1)[1].split('## First Windows runner smoke run', 1)[0]
    assert 'REVIEW-FIXES-v14.md' in deploy
    assert 'docs/LOOP-ENGINE-V14-DESIGN.md' in deploy
    assert 'uat-action-proxy.ps1' in deploy
    assert 'uat-action-policy.json' in deploy

def test_v9_docs_exist_and_record_accepted_red_team_findings():
    assert V9_REVIEW.exists()
    assert V9_DESIGN.exists()
    review = text(V9_REVIEW)
    for token in ('PowerShell 5.1', 'K8S/kubectl.exe', 'automated-override.md', 'immutable', 'v7'):
        assert token in review


def test_v9_effective_permissions_strip_all_preexisting_edit_write_allows_before_stage_rules():
    s = text(PREPARE)
    # v13 is stronger than v9: neither stage inherits any local allow list.
    assert 'both OPUS and FABLE start from a fresh permission object' in s
    assert 'UAT_ACTION_PROXY_ALLOW' in s

def test_v9_opus_pin_exports_immutable_hash_and_length_as_step_outputs():
    s = text(ROUND)
    block = s.split('Pin Opus UAT_REPORT before Fable', 1)[1].split('Select Fable final auditor stage', 1)[0]
    assert 'id: opus_pin' in block
    assert 'report_sha256=' in block
    assert 'report_length=' in block
    assert '$env:GITHUB_OUTPUT' in block


def test_v9_fable_report_verification_cross_checks_pin_hash_against_github_step_output():
    s = text(ROUND)
    block = s.split('Verify Fable preserved Opus report', 1)[1].split('Complete round and expose outputs', 1)[0]
    assert '${{ steps.opus_pin.outputs.report_sha256 }}' in block
    assert '${{ steps.opus_pin.outputs.report_length }}' in block
    assert 'workflow step output' in block.lower()


def test_v9_windows_smoke_builds_single_64_character_agents_hash_and_safe_directory_list():
    s = text(SMOKE)
    assert '(("a" * 64) -join "")' in s or "(('a' * 64) -join '')" in s
    assert 'New-Item -ItemType Directory -Force -Path @($smokeRepo, $smokeOut)' in s
    assert 'New-Item -ItemType Directory -Force $smokeRepo, $smokeOut' not in s



def test_v10_new_round_cleanup_is_fail_closed_and_verified():
    s = text(STATE)
    assert 'function Remove-PathFailClosed' in s
    helper = s.split('function Remove-PathFailClosed', 1)[1].split('function ', 1)[0]
    assert '-ErrorAction Stop' in helper
    assert 'Test-Path' in helper
    assert 'throw' in helper
    assert 'Start-Sleep' in helper
    block = s.split('if ($ActionName -ne "resume-verifier")', 1)[1].split('Save-State $state', 1)[0]
    assert 'Remove-PathFailClosed $stageState' in block
    assert 'Remove-PathFailClosed $legacyPublish' in block
    assert 'Remove-PathFailClosed (Join-Path $env:OUTDIR "uat-result.txt")' in block
    assert '-ErrorAction SilentlyContinue $stageState' not in block


def test_v10_windows_smoke_fault_injects_locked_fable_cleanup_and_requires_block():
    s = text(SMOKE)
    assert '[LOCKED-CLEANUP-SMOKE]' in s
    assert '[System.IO.FileShare]::None' in s
    assert 'verifier-state\\fable' in s
    assert 'BeginRound' in s
    assert 'locked stale verifier state did not block BeginRound' in s
    assert 'durable state advanced despite locked cleanup failure' in s


def test_v10_fable_permissions_are_rebuilt_without_inheriting_shell_allows():
    s = text(PREPARE)
    assert 'both OPUS and FABLE start from a fresh permission object' in s
    assert 'UAT_ACTION_PROXY_ALLOW' in s
    assert 'fable-uat-proxy.ps1' not in s

def test_v10_fable_uat_proxy_is_fixed_path_and_rejects_local_copy_actions():
    assert FABLE_PROXY.exists()
    s = text(FABLE_PROXY)
    assert 'ValidateSet("Readyz", "Get", "Describe", "Logs", "Exec", "Debug", "Wait", "ApiResources", "Version")' in s
    assert 'K8S\\kubectl.exe' in s
    assert 'K8S\\admin.conf' in s
    assert 'verifier-state\\fable\\evidence\\proxy' in s
    assert 'Unsupported kubectl subcommand' in s
    assert '"cp"' in s
    assert 'OutputPath' not in s


def test_v10_whole_protected_surface_digest_is_pinned_in_step_output_and_verified_after_fable():
    assert PROTECTED_HASH.exists()
    h = text(PROTECTED_HASH)
    for token in ('loop-state.json', 'verifier-state\\opus', 'cycles', 'pushed-sha.txt', 'codex-final.txt', 'IMPLEMENTATION_HANDOFF.md'):
        assert token in h
    assert 'git status --porcelain' in h
    r = text(ROUND)
    pre = r.split('Capture protected evidence surface before Fable', 1)[1].split('Select Fable final auditor stage', 1)[0]
    assert 'id: protected_pin' in pre
    assert 'protected_digest=' in pre
    post = r.split('Verify protected evidence surface after Fable', 1)[1].split('Verify Fable preserved Opus report', 1)[0]
    assert '${{ steps.protected_pin.outputs.protected_digest }}' in post
    assert 'protected evidence surface changed during Fable' in post


def test_v10_fable_compatibility_block_explicitly_overrides_legacy_manual_confirmation():
    s = text(RUNNER)
    compat = s.split('# BASE PROMPT COMPATIBILITY OVERRIDES', 1)[1].split('"@', 1)[0]
    assert 'do not wait for operator confirmation' in compat.lower()
    assert '阶段二' in compat or 'stage two' in compat.lower()
    assert 'continue automatically' in compat.lower()


def test_v10_historical_docs_remain_and_v11_readme_keeps_v10_components():
    assert V10_REVIEW.exists()
    assert V10_DESIGN.exists()
    s = text(README)
    assert 'fable-uat-proxy.ps1' in s
    assert 'protected-evidence-hash.ps1' in s


def test_v10_fable_runner_disables_user_project_local_setting_sources():
    s = text(RUNNER)
    assert '--setting-sources' in s
    assert '$env:VERIFIER_STAGE -eq "FABLE"' in s
    assert 'setting sources' in s.lower()
    assert 'user,project,local' not in s.split('$baseClaudeArgs =', 1)[1].split('function ', 1)[0]


def test_v10_protected_surface_baseline_is_durable_across_fable_resume():
    s = text(STATE)
    assert 'BindProtectedEvidenceBaseline' in s
    assert 'protected_evidence_sha256' in s
    assert 'protected_round_contract_sha256' in s
    r = text(ROUND)
    pre = r.split('Capture protected evidence surface before Fable', 1)[1].split('Select Fable final auditor stage', 1)[0]
    assert '-Operation BindProtectedEvidenceBaseline' in pre
    assert 'loop-state.pre-fable.json' in pre
    post = r.split('Verify protected evidence surface after Fable', 1)[1].split('Verify Fable preserved Opus report', 1)[0]
    assert 'protected_evidence_sha256' in post
    h = text(PROTECTED_HASH)
    assert 'Add-FileRecord (Join-Path $OutDir "loop-state.json")' not in h


def test_v10_reconcile_requires_durable_fable_evidence_gate_marker_before_completion():
    s = text(STATE)
    assert 'MarkFinalAuditEvidenceVerified' in s
    canonical = s.split('function Test-CanonicalVerifierComplete', 1)[1].split('function Write-CycleSummary', 1)[0]
    assert 'final_audit_evidence_verified' in canonical
    assert 'final_audit_evidence_verified_verdict' in canonical
    assert 'final_audit_evidence_verified_protected_sha256' in canonical
    marker = s.split('function Mark-FinalAuditEvidenceVerified', 1)[1].split('function Complete-Round', 1)[0]
    assert 'protected_evidence_sha256' in marker
    assert 'Test-ProgressMatchesAllocation' in marker
    assert 'Test-ProgressVerdictComplete' in marker
    r = text(ROUND)
    verify = r.split('Verify Fable preserved Opus report', 1)[1].split('Complete round and expose outputs', 1)[0]
    assert '-Operation MarkFinalAuditEvidenceVerified' in verify
    assert '-ProtectedEvidenceSha256' in verify


def test_v11_fable_setting_sources_is_single_ps51_safe_cli_token():
    s = text(RUNNER)
    assert '"--setting-sources="' in s
    assert '@("--setting-sources", "")' not in s
    smoke = text(SMOKE)
    assert '"--setting-sources="' in smoke
    assert '[CLAUDE-ARGV-SMOKE]' in smoke


def test_v11_blocked_resume_clears_stale_final_audit_evidence_marker():
    s = text(STATE)
    block = s.split('if ($phaseNow -eq "COMPLETE" -and $verdictNow -eq "BLOCKED")', 1)[1].split('}', 1)[0]
    for token in (
        'final_audit_evidence_verified',
        'final_audit_evidence_verified_verdict',
        'final_audit_evidence_verified_protected_sha256',
        'final_audit_evidence_verified_at',
    ):
        assert token in block
    smoke = text(SMOKE)
    assert '[BLOCKED-RESUME-SMOKE]' in smoke


def test_v11_canonical_recomputes_protected_round_contract_before_accepting_fable_result():
    s = text(STATE)
    canonical = s.split('function Test-CanonicalVerifierComplete', 1)[1].split('function Write-CycleSummary', 1)[0]
    assert 'Get-ProtectedRoundContractSha256' in canonical
    assert 'protected_round_contract_sha256' in canonical
    assert 'currentContractSha' in canonical or 'currentProtectedRoundContract' in canonical
    smoke = text(SMOKE)
    assert '[ROUND-CONTRACT-TAMPER-SMOKE]' in smoke


def test_v11_fable_proxy_captures_native_stderr_without_losing_exit_code_or_evidence():
    s = text(FABLE_PROXY)
    invoke = s.split('function Invoke-Kubectl', 1)[1].split('\n}', 1)[0]
    assert '$previousErrorActionPreference' in invoke
    assert '$ErrorActionPreference = "Continue"' in invoke
    assert '$LASTEXITCODE' in invoke
    assert 'finally' in invoke
    assert '$ErrorActionPreference = $previousErrorActionPreference' in invoke
    smoke = text(SMOKE)
    assert '[NATIVE-STDERR-SMOKE]' in smoke


def test_v11_all_governed_readyz_probes_use_15_second_timeout():
    workflow = text(ROUND)
    proxy = text(FABLE_PROXY)
    runner = text(RUNNER)
    assert workflow.count('get --raw=/readyz --request-timeout=15s') >= 2
    assert proxy.count('"--raw=/readyz", "--request-timeout=15s"') >= 2
    assert 'get --raw=/readyz --request-timeout=15s' in runner



def test_v11_workflow_readyz_native_stderr_handling_is_ps51_safe():
    s = text(ROUND)
    assert s.count('$previousReadyzErrorActionPreference = $ErrorActionPreference') >= 2
    assert s.count('$ErrorActionPreference = "Continue"') >= 2
    assert s.count('$readyzExit = $LASTEXITCODE') >= 2
    assert s.count('$ErrorActionPreference = $previousReadyzErrorActionPreference') >= 2


def test_v11_historical_docs_remain_while_v12_manifest_is_current():
    assert (ROOT / 'REVIEW-FIXES-v11.md').exists()
    assert (ROOT / 'docs' / 'LOOP-ENGINE-V11-DESIGN.md').exists()
    assert (ROOT / 'REVIEW-FIXES-v12.md').exists()
    assert (ROOT / 'docs' / 'LOOP-ENGINE-V12-DESIGN.md').exists()
    s = text(README)
    deploy = s.split('## Deployment', 1)[1].split('## First Windows runner smoke run', 1)[0]
    assert 'REVIEW-FIXES-v14.md' in deploy
    assert 'docs/LOOP-ENGINE-V14-DESIGN.md' in deploy
    assert '--setting-sources=' in s
    assert 'get --raw=/readyz --request-timeout=15s' in s

def test_v12_operator_entry_requires_explicit_uat_write_authorization_contract():
    s = text(ENGINE)
    for token in ('uat_write_authorization_confirmed','uat_authorization_id','uat_authorized_actions'):
        assert token in s
    assert 'default: false' in s
    assert 'BindCycleUatAuthorization' in s
    assert 'uat_target_namespace' in s and 'uat_resource_scope' in s

def test_v12_reusable_round_receives_and_binds_authorization_after_candidate():
    s = text(ROUND)
    assert 'BindUatWriteAuthorization' in s
    assert '-VerifierStage "OPUS"' in s
    assert '-VerifierStage "FABLE"' in s
    assert '-AuthorizationConfirmed' not in s
    assert s.index('SetCandidate') < s.index('BindUatWriteAuthorization')

def test_v12_state_authorization_is_candidate_round_stage_and_scope_bound():
    s = text(STATE)
    assert 'BindUatWriteAuthorization' in s
    assert 'function Bind-UatWriteAuthorization' in s
    for token in (
        'authorization_id',
        'authorized_actions',
        'authorization_actor',
        'candidate_sha',
        'cycle',
        'round',
        'verifier_stage',
        'scope_sha256',
        'uat_write_authorization_opus',
        'uat_write_authorization_fable',
    ):
        assert token in s
    assert 'UAT_WRITE_AUTHORIZATION_REQUIRED' in s
    assert 'test-data-write' in s
    assert 'git-update' in s
    assert 'deploy' in s and 'delete' in s and 'restart' in s and 'scale' in s
    # Authorization identity participates in the protected Round contract.
    assert 'uat_write_authorization_opus_sha256' in s
    assert 'uat_write_authorization_fable_sha256' in s


def test_v12_runner_injects_stage_authorization_and_fails_closed_for_unlisted_writes():
    s = text(RUNNER)
    assert 'AUTHORITATIVE UAT WRITE AUTHORIZATION' in s
    assert 'LOOP_UAT_AUTHORIZATION_ID' in s
    assert 'LOOP_UAT_AUTHORIZED_ACTIONS' in s
    assert 'LOOP_UAT_AUTHORIZATION_SCOPE_SHA256' in s
    assert 'Any mutable action not listed in Authorized actions is NOT authorized' in s
    assert 'uat-action-proxy.ps1' in s
    assert 'Do not invoke kubectl' in s
    assert 'do not wait for operator confirmation' in s.lower()

def test_v12_fable_proxy_enforces_authorized_exec_and_debug_actions():
    s = text(FABLE_PROXY)
    assert 'LOOP_UAT_AUTHORIZED_ACTIONS' in s
    assert 'UAT_WRITE_AUTHORIZATION_REQUIRED' in s
    assert '"Exec"' in s and '"exec"' in s
    assert '"Debug"' in s and '"debug"' in s


def test_v12_automated_override_identifies_v12_and_preserves_explicit_authorization_gate():
    s = text(ROOT / '.loop-engine' / 'automated-override.md')
    assert '# Loop Engine Automated Verifier Override v20' in s
    assert 'managed by Loop Engine v20' in s
    assert 'workflow_dispatch' in s
    assert 'non-interactive' in s.lower()
    assert 'uat-action-proxy.ps1' in s

def test_v12_windows_smoke_covers_authorization_binding_and_fail_closed_missing_grant():
    s = text(SMOKE)
    assert '[UAT-AUTHORIZATION-SMOKE]' in s
    assert 'BindUatWriteAuthorization' in s
    assert 'UAT_WRITE_AUTHORIZATION_REQUIRED' in s


V12_REVIEW = ROOT / 'REVIEW-FIXES-v12.md'
V12_DESIGN = ROOT / 'docs' / 'LOOP-ENGINE-V12-DESIGN.md'


def test_v12_docs_ship_current_review_and_design():
    assert V12_REVIEW.exists()
    assert V12_DESIGN.exists()
    readme = text(README)
    assert 'REVIEW-FIXES-v12.md' in readme
    assert 'LOOP-ENGINE-V12-DESIGN.md' in readme


def test_v12_durable_authorization_is_revalidated_before_resume_reuse():
    s = text(STATE)
    assert 'Assert-UatWriteAuthorizationGrantMatchesRound' in s
    assert 'grant does not match current Cycle/Round/Candidate/stage/period' in s
    assert 'Get-UatWriteAuthorizationScopeSha256' in s
    assert 'scope SHA-256 is invalid or changed' in s


def test_v12_authorization_changes_verifier_fingerprint_and_canonical_acceptance():
    prepare = text(PREPARE)
    state = text(STATE)
    for token in (
        'uat_authorization_id=',
        'uat_authorized_actions=',
        'uat_authorization_scope_sha256=',
        'uat_authorization_actor=',
    ):
        assert token in prepare
    assert 'uat_write_authorization_opus_sha256' in state
    assert 'uat_write_authorization_fable_sha256' in state
    assert "if ($opusAuthSha -notmatch '^[0-9a-f]{64}$') { return $false }" in state
    assert "if ($fableAuthSha -notmatch '^[0-9a-f]{64}$') { return $false }" in state

V13_REVIEW = ROOT / 'REVIEW-FIXES-v13.md'
V13_DESIGN = ROOT / 'docs' / 'LOOP-ENGINE-V13-DESIGN.md'
UAT_PROXY = ROOT / '.loop-engine' / 'uat-action-proxy.ps1'
UAT_POLICY = ROOT / '.loop-engine' / 'uat-action-policy.json'


def test_v13_dispatch_authorization_is_cycle_scoped_and_resource_bound():
    engine = text(ENGINE)
    state = text(STATE)
    for token in (
        'uat_target_namespace',
        'uat_resource_scope',
        'uat_target_branch',
        'uat_impact_scope',
    ):
        assert token in engine
    assert 'BindCycleUatAuthorization' in engine
    assert 'function Bind-CycleUatAuthorization' in state
    for token in (
        'uat_cycle_authorization',
        'target_namespace',
        'resource_scope',
        'target_branch',
        'impact_scope',
        'cycle_scope_sha256',
    ):
        assert token in state
    assert 'v13-cycle-uat-authorization' in state
    assert 'one workflow dispatch' in engine.lower() or 'current cycle' in engine.lower()


def test_v13_round_stage_grants_are_derived_from_cycle_authorization_not_future_manual_prompts():
    state = text(STATE)
    round_wf = text(ROUND)
    bind = state.split('function Bind-UatWriteAuthorization', 1)[1].split('function Get-Cycle', 1)[0]
    assert 'uat_cycle_authorization' in bind
    assert 'Assert-CycleUatAuthorization' in bind
    assert 'cycle_scope_sha256' in bind
    assert 'AuthorizationConfirmed' not in bind
    assert '-AuthorizationConfirmed' not in round_wf
    assert 'UAT_WRITE_AUTHORIZATION_CONFIRMED' not in round_wf


def test_v13_opus_and_fable_shell_permissions_are_rebuilt_to_unified_proxy_only():
    s = text(PREPARE)
    assert 'UAT_ACTION_PROXY_ALLOW' in s
    assert 'both OPUS and FABLE start from a fresh permission object' in s
    assert 'other shell permissions are intentionally retained' not in s
    proxy_rule = 'Bash(powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/Redemption/Redemption/.loop-engine/uat-action-proxy.ps1)'
    assert '$env:UAT_ACTION_PROXY_ALLOW' in s
    assert proxy_rule in text(ROUND)
    assert 'Bash(git bundle' not in s
    assert 'PowerShell(git bundle' not in s
    # Any allowed shell rule outside the fixed proxy would reopen the boundary.
    smoke = s.split('Defense-in-depth smoke check', 1)[1]
    assert 'unauthorized shell allow' in smoke.lower()


def test_v13_unified_proxy_hard_maps_every_mutable_action_token_and_rejects_shell_wrappers():
    assert UAT_PROXY.exists()
    s = text(UAT_PROXY)
    for token in ('test-data-write', 'exec', 'debug', 'git-update', 'deploy', 'restart', 'scale', 'delete'):
        assert f'"{token}"' in s
    for action in ('ExecProfile', 'DebugProfile', 'KafkaScenarioProduce', 'RedisDeleteExactKeys', 'GitUpdate', 'SetImage', 'Restart', 'Scale', 'Delete'):
        assert f'"{action}"' in s
    assert 'RequiredTokens' in s
    assert 'Assert-RequiredTokens' in s
    assert 'sh -c' in s
    assert 'bash -c' in s
    assert 'cmd /c' in s
    assert 'powershell -command' in s.lower()
    assert 'Assert-ResourceAllowed' in s
    assert 'LOOP_UAT_TARGET_NAMESPACE' in s
    assert 'LOOP_UAT_RESOURCE_SCOPE' in s
    assert 'LOOP_UAT_TARGET_BRANCH' in s
    assert UAT_POLICY.exists()


def test_v13_debug_proxy_always_cleans_new_node_debugger_pods_without_granting_arbitrary_delete():
    s = text(UAT_PROXY)
    assert 'Invoke-NodeDebugWithCleanup' in s
    debug = s.split('function Invoke-NodeDebugWithCleanup', 1)[1].split('function ', 1)[0]
    assert 'finally' in debug
    assert 'Wait-NewDebugPod' in debug
    assert 'Wait-DebugPodTermination' in debug
    assert 'Remove-DebugPodByUid' in debug
    assert 'node-debugger-' in s
    assert 'metadata.uid' in s
    assert 'DEBUG_POD_UID_MISMATCH' in s
    assert 'Assert-RequiredTokens @("debug")' in s or 'debug' in s
    readme = text(README)
    assert 'debug includes mandatory cleanup' in readme.lower()
    assert 'delete is still separate' in readme.lower()


def test_v13_runner_forces_both_verifier_stages_through_unified_proxy():
    s = text(RUNNER)
    assert 'uat-action-proxy.ps1' in s
    assert 'for every kubernetes/uat command' in s.lower()
    assert 'OPUS ITERATIVE VERIFIER' in s
    assert 'FABLE FINAL AUDITOR' in s
    assert 'Do not invoke kubectl' in s
    assert 'arbitrary PowerShell' in s


def test_v13_docs_record_noninteractive_cycle_preauthorization_user_decision():
    assert V13_REVIEW.exists()
    assert V13_DESIGN.exists()
    for p in (README, V13_REVIEW, V13_DESIGN):
        s = text(p).lower()
        assert 'non-interactive' in s or 'noninteractive' in s
        assert 'cycle' in s
        assert 'namespace' in s
        assert 'resource scope' in s
        assert 'target branch' in s
        assert 'impact scope' in s
    override = text(ROOT / '.loop-engine' / 'automated-override.md')
    assert 'v20' in override.splitlines()[0].lower()


def test_v13_windows_smoke_binds_cycle_authorization_before_stage_grants():
    s = text(SMOKE)
    assert 'BindCycleUatAuthorization' in s
    assert '-TargetNamespace "pvam-uat"' in s
    assert '-ResourceScope "node/node3,pod/node-debugger-*"' in s
    assert '-TargetBranch "smoke"' in s
    assert '-ImpactScope "isolated-uat-only"' in s
    assert s.index('BindCycleUatAuthorization') < s.index('BindUatWriteAuthorization')
    # v13 stage grants are derived; the legacy per-stage authorization arguments must be gone.
    stage_lines = [line for line in s.splitlines() if 'BindUatWriteAuthorization' in line and '-Operation' in line]
    assert stage_lines
    assert all('AuthorizationConfirmed' not in line and 'AuthorizationId' not in line and 'AuthorizedActions' not in line for line in stage_lines)
    assert '[CYCLE-AUTHORIZATION-SMOKE]' in s


def test_v13_verifier_fingerprint_binds_cycle_scope_and_resource_boundaries():
    s = text(PREPARE)
    for env_name in (
        'LOOP_UAT_CYCLE_SCOPE_SHA256',
        'LOOP_UAT_TARGET_NAMESPACE',
        'LOOP_UAT_RESOURCE_SCOPE',
        'LOOP_UAT_TARGET_BRANCH',
        'LOOP_UAT_IMPACT_SCOPE',
    ):
        assert env_name in s
    for material in (
        'uat_cycle_scope_sha256=',
        'uat_target_namespace=',
        'uat_resource_scope=',
        'uat_target_branch=',
        'uat_impact_scope=',
    ):
        assert material in s
    assert 'uat_cycle_scope_sha256 = $uatCycleScopeSha256' in s
    assert 'uat_target_namespace = $uatTargetNamespace' in s
    assert 'uat_resource_scope = $uatResourceScope' in s
    assert 'uat_target_branch = $uatTargetBranch' in s
    assert 'uat_impact_scope = $uatImpactScope' in s


def test_v13_protected_evidence_surface_includes_unified_proxy_and_policy():
    s = text(ROOT / '.loop-engine' / 'protected-evidence-hash.ps1')
    assert '.loop-engine\\uat-action-proxy.ps1' in s
    assert '.loop-engine\\uat-action-policy.json' in s
    assert '.loop-engine\\consumer-runtime-controller.py' in s


def test_v13_cycle_authorization_target_branch_must_match_controller_branch():
    s = text(STATE)
    bind = s.split('function Bind-CycleUatAuthorization', 1)[1].split('function Get-UatWriteAuthorizationScopeSha256', 1)[0]
    assert '$env:BRANCH' in bind
    assert 'authorized target branch must match Loop Engine BRANCH' in bind
