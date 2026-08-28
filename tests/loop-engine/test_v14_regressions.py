from pathlib import Path
import json, re

ROOT = Path(__file__).resolve().parents[2]
LOOP_STATE = (ROOT/'.loop-engine/loop-state.ps1').read_text(encoding='utf-8')
PREPARE = (ROOT/'.loop-engine/prepare-verifier-state.ps1').read_text(encoding='utf-8')
PROXY = (ROOT/'.loop-engine/uat-action-proxy.ps1').read_text(encoding='utf-8')
WORKFLOW = (ROOT/'.github/workflows/loop-engine.yml').read_text(encoding='utf-8')
ROUND = (ROOT/'.github/workflows/loop-round.yml').read_text(encoding='utf-8')
PROTOCOL = (ROOT/'.loop-engine/verifier-checkpoint-protocol.md').read_text(encoding='utf-8')
POLICY = json.loads((ROOT/'.loop-engine/uat-action-policy.json').read_text(encoding='utf-8'))


def test_ps_regex_uses_regex_engine_control_escapes():
    for text in (LOOP_STATE, PREPARE, PROXY):
        assert "[`r`n`0" not in text
    assert r"'[\x00\r\n ]'" in LOOP_STATE
    assert r"'[\x00\r\n ]'" in PREPARE
    assert r"'[\x00\r\n ]'" in PROXY
    assert r"'[\x00\r\n]'" in PROXY


def test_workflow_dispatch_inputs_are_not_injected_into_powershell_run_body():
    # Inputs may appear in env mappings / if expressions, but not inside the
    # inline PowerShell body for the authorization binding step.
    bind = WORKFLOW.split('- name: Bind or reuse non-interactive Cycle UAT authorization', 1)[1]
    bind = bind.split('- name: Upload reconciled cycle evidence', 1)[0]
    run_body = bind.split('run: |', 1)[1]
    assert '${{ inputs.' not in run_body
    for envname in [
        'INPUT_AUTH_CONFIRMED','INPUT_AUTH_ID','INPUT_AUTH_ACTIONS','INPUT_AUTH_NAMESPACE',
        'INPUT_AUTH_RESOURCE_SCOPE','INPUT_AUTH_TARGET_BRANCH','INPUT_AUTH_IMPACT_SCOPE'
    ]:
        assert f'$env:{envname}' in run_body


def test_single_proxy_allow_rule_is_used_by_prepare_and_fable_gate():
    assert 'UAT_ACTION_PROXY_ALLOW' in ROUND
    assert '$env:UAT_ACTION_PROXY_ALLOW' in PREPARE
    fable = ROUND.split('- name: Fable final auditor permission smoke gate',1)[1]
    fable = fable.split('- name: Fable final-audit environment preflight',1)[0]
    assert '$env:UAT_ACTION_PROXY_ALLOW' in fable
    assert 'fable-uat-proxy.ps1' not in fable
    assert 'fable-uat-proxy.ps1' not in PROTOCOL


def test_debug_is_synchronous_uid_bound_and_ifnotpresent():
    required = [
        'metadata.uid',
        'containerStatuses',
        'state.terminated',
        'exitCode',
        'kubectl logs',
        'image-pull-policy=IfNotPresent',
        'DEBUG_POD_UID_MISMATCH',
    ]
    for token in required:
        assert token in PROXY
    # v13 bug: create-only result then immediate cleanup.
    assert '--attach=false' in PROXY
    assert 'Wait-DebugPodTermination' in PROXY


def test_policy_uses_flannel_discovery_not_busybox_dockerhub():
    assert POLICY.get('debug_image_mode') == 'discover-flannel-daemonset'
    assert POLICY.get('debug_image_pull_policy') == 'IfNotPresent'
    assert 'busybox' not in json.dumps(POLICY).lower()
    sources = POLICY.get('debug_image_sources') or []
    assert sources
    assert any('flannel' in (x.get('name','') + x.get('namespace','')).lower() for x in sources)


def test_proxy_has_governed_list_discovery_action():
    assert '"List"' in PROXY
    assert 'Assert-ListScopeAllowed' in PROXY


def test_git_update_checks_clean_before_checkout_and_verifies_final_heads():
    assert 'status", "--porcelain' in PROXY
    assert 'GIT_WORKTREE_DIRTY' in PROXY
    assert 'rev-parse", "HEAD' in PROXY
    assert 'GIT_HEAD_MISMATCH' in PROXY
    assert 'GIT_BRANCH_MISMATCH' in PROXY
    assert 'Verify-NodeHostGitView' in PROXY
    assert '"reset", "--hard"' not in PROXY
    checkout_pos = PROXY.index('"checkout", "-B"')
    dirty_pos = PROXY.index('GIT_WORKTREE_DIRTY')
    assert dirty_pos < checkout_pos
    assert 'verification_pod is required' in PROXY
    assert 'GIT_POD_VIEW_FAILED' in PROXY


def test_proxy_writes_audit_evidence_for_denials_and_failures():
    assert 'try {' in PROXY
    assert 'catch {' in PROXY
    assert 'finally {' in PROXY
    assert 'Write-ProxyAuditRecord' in PROXY
    assert 'outcome=' in PROXY
    assert 'error_class=' in PROXY


def test_active_docs_do_not_claim_old_fable_proxy():
    assert 'fable-uat-proxy.ps1' not in PROTOCOL

def test_policy_has_structured_work_pvam02_write_capabilities_without_empty_profile_placeholders():
    raw = json.dumps(POLICY, sort_keys=True)
    assert 'test_data_write_profiles' not in POLICY
    assert 'git_update_host_repo_prefixes' not in POLICY
    assert POLICY.get('repo_remote_url') == 'git@github.com:l343765828/Redemption.git'
    assert set(POLICY.get('kafka_topics') or []) == {'pvam-pv-orders', 'pvam-pv-refunds'}
    assert {'pvam:event_delivery:', 'pvam:order_ledger:', 'pvam:refund_reversal:'} <= set(POLICY.get('redis_exact_cleanup_prefixes') or [])
    assert 'KafkaScenarioProduce' in PROXY
    assert 'RedisDeleteExactKeys' in PROXY
    assert 'uat-$ExecutionId-' in PROXY
    assert 'Invoke-ControllerUatProducer' in PROXY
    assert "producer_authority='controller-owned-v20'" in PROXY
    assert 'tests/pvam/WORK-PVAM-02/uat_message_producer.py' not in PROXY
    assert 'PVAM_REDIS_HOST' in PROXY


def test_git_update_discovers_repo_by_exact_remote_and_requires_pod_nfs_view():
    assert 'Find-GitRepoByRemote' in PROXY
    assert 'remote.origin.url' in PROXY
    assert 'repo_remote_url' in PROXY
    assert 'Verify-PodGitView' in PROXY
    assert 'verification_pod is required' in PROXY
    assert 'origin/{0}' in PROXY
    assert '"reset", "--hard"' not in PROXY


def test_proxy_audit_wraps_authorization_policy_readyz_and_command_failures():
    top = PROXY.split('$policy = $null', 1)[1]
    assert top.index('try {') < top.index('Assert-AuthorizationEnvelope')
    assert top.index('try {') < top.index('Assert-Readyz')
    assert 'Write-ProxyAuditRecord' in top.split('finally {',1)[1]
    assert 'outcome=DENIED' not in PROXY  # outcome is derived, not hard-coded fake success


def test_windows_smoke_has_behavioral_control_regex_probe():
    smoke = (ROOT/'tests/loop-engine/windows-smoke.ps1').read_text(encoding='utf-8')
    assert '[CONTROL-REGEX-SMOKE] PASS' in smoke
    assert '[char]0' in smoke
    assert 'codex/pvam-work02-uat-candidate-20260813' in smoke

def test_windows_smoke_executes_real_fable_prepare_and_checks_generated_settings():
    smoke = (ROOT/'tests/loop-engine/windows-smoke.ps1').read_text(encoding='utf-8')
    assert '[FABLE-PERMISSION-INTEGRATION-SMOKE] PASS' in smoke
    assert '& $prepareScript' in smoke
    assert 'verifier-settings.effective.json' in smoke
    assert '$env:UAT_ACTION_PROXY_ALLOW = $permProxyAllow' in smoke
    assert '$shellAllows.Count -ne 1' in smoke
