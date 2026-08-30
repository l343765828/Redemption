from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[2]
LOOP_STATE = (ROOT/'.loop-engine/loop-state.ps1').read_text(encoding='utf-8')
PREPARE = (ROOT/'.loop-engine/prepare-verifier-state.ps1').read_text(encoding='utf-8')
PROXY = (ROOT/'.loop-engine/uat-action-proxy.ps1').read_text(encoding='utf-8')
PROTECTED = (ROOT/'.loop-engine/protected-evidence-hash.ps1').read_text(encoding='utf-8')
WORKFLOW = (ROOT/'.github/workflows/loop-engine.yml').read_text(encoding='utf-8')
ROUND = (ROOT/'.github/workflows/loop-round.yml').read_text(encoding='utf-8')
SMOKE = (ROOT/'tests/loop-engine/windows-smoke.ps1').read_text(encoding='utf-8')
POLICY = json.loads((ROOT/'.loop-engine/uat-action-policy.json').read_text(encoding='utf-8'))


def test_v15_smoke_uses_numeric_authorization_run_id():
    assert 'AuthorizationRunId "smoke-run"' not in SMOKE
    ids = re.findall(r'-AuthorizationRunId\s+"([^"]+)"', SMOKE)
    assert ids
    assert all(re.fullmatch(r'[0-9]{1,32}', x) for x in ids)


def test_v15_proxy_resolves_period_pair_by_verifier_stage():
    assert 'function Get-StageUatPeriodContext' in PROXY
    assert 'LOOP_FINAL_UAT_PERIOD_PRIMARY' in PROXY
    assert 'LOOP_FINAL_UAT_PERIOD_SECONDARY' in PROXY
    assert 'LOOP_FINAL_UAT_PERIOD_SLOT' in PROXY
    assert 'LOOP_UAT_AUTHORIZATION_STAGE' in PROXY
    # Profile expansion and Kafka payload validation must consume the resolved
    # stage context rather than reading the Opus variables directly.
    expand = PROXY.split('function Expand-ProfileCommand',1)[1].split('function Find-GitRepoByRemote',1)[0]
    assert 'Get-StageUatPeriodContext' in expand
    assert 'LOOP_UAT_PERIOD_PRIMARY' not in expand
    kafka = PROXY.split('function Invoke-KafkaScenarioProduce',1)[1].split('function Invoke-RedisExactCleanup',1)[0]
    assert 'Get-StageUatPeriodContext' in kafka
    assert 'LOOP_UAT_PERIOD_PRIMARY' not in kafka
    assert 'stage_period_primary=' in PROXY
    assert 'stage_period_secondary=' in PROXY


def test_v15_protected_hash_excludes_only_volatile_opus_checkpoint_files():
    assert 'Add-OpusStableEvidenceRecords' in PROTECTED
    for name in ('verifier-progress.json', 'resume-context.md', 'claude-session.txt'):
        assert name in PROTECTED
    # It must still bind immutable Opus evidence and the two pre-Fable snapshots.
    for token in ('UAT_REPORT.pre-fable.md', 'loop-state.pre-fable.json', 'Join-Path $opusRoot "evidence"', 'Join-Path $opusRoot "logs"'):
        assert token in PROTECTED
    assert 'Add-TreeRecords (Join-Path $OutDir "verifier-state\\opus")' not in PROTECTED


def test_v15_policy_supports_remaining_work_pvam02_read_and_operational_actions():
    # Read-only UAT evidence paths needed by V/U checks.
    for action in ('Get', 'GetJsonPath', 'Logs', 'Describe', 'List', 'Wait', 'RolloutStatus'):
        assert f'"{action}"' in PROXY
    # Structured operational paths needed by deployment/Dask UAT.
    for action in ('Restart', 'Scale', 'GitUpdate', 'KafkaScenarioProduce', 'RedisDeleteExactKeys', 'RedisReadExactKeys'):
        assert f'"{action}"' in PROXY
    profiles = POLICY.get('exec_profiles') or {}
    # At minimum, Dask worker/scheduler identity and GPU checks must be available
    # without opening arbitrary shell execution.
    for profile in ('dask-scheduler-info', 'dask-client-versions', 'gpu-runtime-probe'):
        assert profile in profiles
    assert POLICY.get('set_image_allowlist') == []


def test_v15_git_update_fails_closed_when_debug_logs_are_unavailable():
    debug = PROXY.split('function Invoke-NodeDebugWithCleanup',1)[1].split('function Get-PolicyProfile',1)[0]
    assert 'DEBUG_LOGS_FAILED' in debug
    # No command that relies on stdout may be considered successful if logs failed.
    assert 'if ($logs.ExitCode -ne 0) { throw "DEBUG_LOGS_FAILED:' in debug


def test_v15_scale_requires_explicit_replicas_field():
    scale = PROXY.split('"Scale" {',1)[1].split('"Delete" {',1)[0]
    assert "PSObject.Properties.Name -notcontains 'replicas'" in scale
    assert '[int]::TryParse' in scale


def test_v15_setimage_is_exact_allowlist_guarded():
    block = PROXY.split('"SetImage" {',1)[1].split('"ExecProfile" {',1)[0]
    assert 'set_image_allowlist' in block
    assert 'SET_IMAGE_NOT_ALLOWLISTED' in block
    assert POLICY.get('set_image_allowlist') == []


def test_v15_legacy_single_verifier_can_only_reconcile_when_explicitly_imported():
    legacy = LOOP_STATE.split('# v6/v7 compatibility is accepted only',1)[1].split('function Write-CycleSummary',1)[0]
    assert 'legacy_imported_from_pre_v8' in legacy
    init = LOOP_STATE.split('function Initialize-LegacyState',1)[1].split('function Prepare-Loop',1)[0]
    assert 'legacy_imported_from_pre_v8' in init


def test_v15_resume_stale_verdict_cleanup_is_fail_closed():
    # prepare-verifier-state owns resume result cleanup; it must not silently
    # ignore locked stale verdict/report files.
    assert 'function Remove-PathFailClosed' in PREPARE
    cleanup = PREPARE.split('if (-not $alreadyComplete)',1)[1].split('$state = [IO.File]::ReadAllText',1)[0]
    assert 'Remove-PathFailClosed $env:VERIFIER_RESULT_FILE' in cleanup
    assert 'Remove-Item -Force -ErrorAction SilentlyContinue $env:VERIFIER_RESULT_FILE' not in cleanup


def test_v15_workflow_uses_stage_period_audit_and_stable_protected_digest_contract():
    assert 'Verify actual proxy period usage for Fable' in ROUND
    period_verifier = (ROOT/'.loop-engine/verify-proxy-period-evidence.ps1').read_text(encoding='utf-8')
    assert 'stage_period_primary' in period_verifier
    assert 'stage_period_secondary' in period_verifier
    assert 'protected evidence stable digest' in ROUND.lower()


def test_v15_protected_hash_uses_stable_cycle_contract_subset_not_mutable_archives():
    assert 'function Add-StableCycleContractRecords' in PROTECTED
    assert 'cycle-uat-authorization.json' in PROTECTED
    assert 'round-$roundNumber\\context' in PROTECTED or 'round-{0}\\context' in PROTECTED
    assert 'Add-TreeRecords (Join-Path $OutDir "cycles") "out/cycles"' not in PROTECTED
    assert 'MUTABLE_ARCHIVE_EXCLUDED' in PROTECTED


def test_v15_policy_has_governed_project_actor_rebuild_entrypoint():
    profile = (POLICY.get('exec_profiles') or {}).get('dask-actor-rebuild')
    assert profile is not None
    assert set(profile.get('required_tokens') or []) >= {'exec', 'restart'}
    assert profile.get('command') == ['python3', '-m', 'User.UserService']
