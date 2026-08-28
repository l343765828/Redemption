from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
LOOP = ROOT / '.loop-engine'
WF = ROOT / '.github' / 'workflows' / 'loop-round.yml'


def text(path):
    return path.read_text(encoding='utf-8')


def test_proxy_evidence_is_controller_owned_and_missing_is_fatal():
    proxy = text(LOOP / 'uat-action-proxy.ps1')
    verify = text(LOOP / 'verify-proxy-period-evidence.ps1')
    wf = text(WF)
    assert 'controller-evidence' in proxy
    assert 'verifier-state\\{0}\\evidence\\proxy' not in proxy
    assert 'no proxy evidence directory; no proxy action used' not in verify
    assert 'no proxy action evidence; no actual cluster period use to validate' not in verify
    assert 'CONTROLLER_PROXY_EVIDENCE_ROOT' in wf


def test_proxy_evidence_verifier_checks_integrity_scope_pool_outcome_and_required_actions():
    verify = text(LOOP / 'verify-proxy-period-evidence.ps1')
    for needle in [
        'ExpectedPoolSha256', 'ExpectedAuthorizationScopeSha256', 'ExpectedExecutionId',
        'request_json_b64', 'request_sha256', 'stage_period_pool_sha256',
        'stage_scope_sha256', 'uat_execution_id', 'outcome', 'exit_code',
        'required_success_actions'
    ]:
        assert needle in verify
    assert 'SUCCESS' in verify


def test_policy_has_work02_git_pytest_dask_and_redis_hard_gates():
    policy = json.loads(text(LOOP / 'uat-action-policy.json'))
    assert policy['schema_version'] >= 4
    actions = set(policy['required_success_actions_by_stage']['OPUS'])
    for required in ['GitAudit','PytestFull','PytestSelected','DaskListDatasets','RedisDbSize','KafkaScenarioProduce','RedisDeleteExactKeys']:
        assert required in actions
    assert 'environment-summary' not in policy.get('exec_profiles', {})
    assert 'dask-list-datasets' in policy.get('exec_profiles', {})
    rebuild = policy['exec_profiles']['dask-actor-rebuild']
    assert rebuild.get('repo_cwd') is True
    assert rebuild['command'][:3] == ['python3','-m','User.UserService']


def test_kafka_uses_controller_owned_uat_producer_not_candidate_code():
    proxy = text(LOOP / 'uat-action-proxy.ps1')
    assert 'KafkaScenarioProduce' in proxy
    assert 'function Invoke-ControllerUatProducer' in proxy
    assert "producer_authority='controller-owned-v20'" in proxy
    assert 'tests/pvam/WORK-PVAM-02/uat_message_producer.py' not in proxy
    assert 'from confluent_kafka import Producer' in proxy


def test_redis_contract_includes_execution_prefix_idempotency_and_dbsize():
    policy = json.loads(text(LOOP / 'uat-action-policy.json'))
    prefixes = policy['redis_exact_cleanup_prefixes']
    assert 'pvam:uat:work02:{uat_execution_id}:' in prefixes
    assert 'system:idempotency:{period}:' in prefixes
    proxy = text(LOOP / 'uat-action-proxy.ps1')
    assert 'RedisDbSize' in proxy
    assert 'LOOP_UAT_EXECUTION_ID' in proxy
    assert 'GITHUB_RUN_ID' not in proxy[proxy.find('function Invoke-RedisExactCleanup'):proxy.find('function Invoke-RedisExactRead')]


def test_durable_uat_execution_id_is_in_stage_grant_and_scope_hash():
    state = text(LOOP / 'loop-state.ps1')
    assert 'uat_execution_id' in state
    assert 'LOOP_UAT_EXECUTION_ID' in state
    assert 'schema_version = 3' in state


def test_protected_digest_uses_round_snapshot_not_live_agents():
    script = text(LOOP / 'protected-evidence-hash.ps1')
    assert 'context' in script.lower()
    assert '"AGENTS.md"' not in script


def test_environment_evidence_is_whitelisted_and_bounded():
    policy = json.loads(text(LOOP / 'uat-action-policy.json'))
    assert 'environment-summary' not in policy.get('exec_profiles', {})
    assert 'runtime-summary' in policy.get('exec_profiles', {})
    proxy = text(LOOP / 'uat-action-proxy.ps1')
    assert 'MaxAuditOutputBytes' in proxy
    assert 'MaxAuditOutputLines' in proxy


def test_controller_evidence_is_uploaded_but_not_verifier_editable():
    wf = text(WF)
    prep = text(LOOP / 'prepare-verifier-state.ps1')
    assert '.loop-output\\controller-evidence\\' in wf
    assert '"Edit(.loop-output/controller-evidence/**)"' in prep
    assert 'allow += "Edit(.loop-output/controller-evidence/**)"' not in prep


def test_git_audit_and_selected_pytest_are_structured_actions():
    proxy = text(LOOP / 'uat-action-proxy.ps1')
    for action in ['GitAudit','PytestFull','PytestSelected','DaskListDatasets']:
        assert f'"{action}"' in proxy
    for cmd in ['git status --porcelain', 'ls-remote', 'merge-base']:
        assert cmd in proxy or cmd.replace(' ', '", "') in proxy
    assert 'pytest.main' in proxy



def test_proxy_evidence_verifier_has_ps51_safe_complete_hashtable_keys():
    verify = text(LOOP / 'verify-proxy-period-evidence.ps1')
    assert "$fields['stage']_" not in verify
    for key in [
        'stage_scope_sha256','stage_period_slot','stage_period_primary',
        'stage_period_secondary','stage_period_pool_sha256'
    ]:
        assert f"$fields['{key}']" in verify


def test_windows_smoke_covers_v16_execution_identity_and_controller_evidence_deny():
    smoke = text(ROOT / 'tests' / 'loop-engine' / 'windows-smoke.ps1')
    assert 'LOOP_UAT_EXECUTION_ID' in smoke
    assert 'durable uat_execution_id not persisted' in smoke
    assert 'Edit(.loop-output/controller-evidence/**)' in smoke


def test_windows_smoke_exercises_controller_evidence_negative_probes():
    smoke = text(ROOT / 'tests' / 'loop-engine' / 'windows-smoke.ps1')
    assert '[PROXY-EVIDENCE-SMOKE] PASS' in smoke
    assert 'missing controller proxy evidence did not fail closed' in smoke
    assert 'forged proxy request SHA did not fail closed' in smoke
