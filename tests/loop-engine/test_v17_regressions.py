from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
LOOP = ROOT / '.loop-engine'
WF = ROOT / '.github' / 'workflows' / 'loop-round.yml'

def text(path): return path.read_text(encoding='utf-8')

def test_proxy_has_no_ps_variable_colon_parse_trap():
    assert 'pvam:uat:work02:$ExecutionId:' not in text(LOOP/'uat-action-proxy.ps1')

def test_windows_smoke_builds_evidence_fields_as_single_strings_and_checks_specific_failures():
    smoke=text(ROOT/'tests'/'loop-engine'/'windows-smoke.ps1')
    assert "'stage_scope_sha256=' + $evScope" not in smoke
    assert 'stage_scope_sha256=$evScope' in smoke
    assert 'request hash mismatch' in smoke.lower()
    assert 'proxy evidence directory missing' in smoke.lower()

def test_proxy_evidence_gate_is_verdict_aware_for_opus_and_fable():
    wf=text(WF); verify=text(LOOP/'verify-proxy-period-evidence.ps1')
    assert wf.index('Gate Opus verifier verdict') < wf.index('Verify actual proxy period usage for Opus')
    assert wf.index('Gate Fable final verdict') < wf.index('Verify actual proxy period usage for Fable')
    assert all(x in verify for x in ['VerificationMode','ValidateExistingOnly','RequireComplete'])

def test_selected_pytest_allows_contract_path_and_rejects_traversal():
    policy=json.loads(text(LOOP/'uat-action-policy.json'))
    assert 'MessageConsumer/Test/test_pv_event_consumer.py' in policy['pytest_selected_exact']
    proxy=text(LOOP/'uat-action-proxy.ps1')
    assert 'Assert-PytestTargetAllowed' in proxy
    assert 'directory traversal' in proxy.lower()

def test_redis_exact_read_returns_typed_values_with_caps():
    import base64, re
    proxy=text(LOOP/'uat-action-proxy.ps1'); block=proxy[proxy.index('function Invoke-RedisExactRead'):proxy.index('function Invoke-RedisDbSize')]
    m=re.search(r'FromBase64String\("([A-Za-z0-9+/=]+)"\)', block)
    assert m, 'Redis exact-read Python payload must be encoded as a PS5.1-safe base64 literal'
    py=base64.b64decode(m.group(1)).decode('utf-8')
    for n in ['hscan_iter','lrange','sscan_iter','zrange','xrange','max_items','truncated']: assert n in py
    assert "{'type':r.type(k)}" not in py

def test_controller_gate_validates_semantics_not_only_action_names():
    verify=text(LOOP/'verify-proxy-period-evidence.ps1')
    for n in ['semantic_json_b64','GitAuditResult','RedisDbSizeResult','RedisDeleteResult','KafkaScenarioResult','worktree_clean','remote_head','remaining_count','phase']: assert n in verify
    assert 'ExpectedCandidateSha' in verify and 'ExpectedBaselineSha' in verify

def test_kafka_and_cleanup_share_controller_known_delivery_identity():
    proxy=text(LOOP/'uat-action-proxy.ps1')
    assert 'Get-DeliveredKafkaKeysFromControllerEvidence' in proxy
    assert 'delivered_keys' in proxy
    assert "scenario -eq 'drain-sentinel'" in proxy
    assert 'exact delivered Kafka identity' in proxy

def test_redis_delete_verifies_post_delete_absence():
    proxy=text(LOOP/'uat-action-proxy.ps1'); block=proxy[proxy.index('function Invoke-RedisExactCleanup'):proxy.index('function Invoke-RedisExactRead')]
    for n in ['remaining','deleted_count','remaining_count']: assert n in block

def test_policy_requires_dbsize_before_after_semantics_and_selected_contract_test():
    policy=json.loads(text(LOOP/'uat-action-policy.json'))
    assert policy['redis_dbsize_required_phases']==['before','after']
    assert 'MessageConsumer/Test/test_pv_event_consumer.py' in policy['pytest_selected_exact']

def test_redis_exact_read_embeds_real_multiline_python_without_literal_backslash_n():
    block=text(LOOP/'uat-action-proxy.ps1')
    block=block[block.index('function Invoke-RedisExactRead'):block.index('function Invoke-RedisDbSize')]
    assert 'FromBase64String' in block
    assert r';\nfor k in ks:' not in block

def test_complete_gate_requires_meaningful_redis_delete_not_zero_delete_only():
    verify=text(LOOP/'verify-proxy-period-evidence.ps1')
    assert 'totalDeleted' in verify
    assert 'Redis cleanup produced no actual deletion' in verify


def test_complete_gate_requires_contract_selected_pytest_target_semantically():
    policy=json.loads(text(LOOP/'uat-action-policy.json'))
    assert policy['pytest_selected_required_targets']==[
        'MessageConsumer/Test/test_pv_event_consumer.py',
        'User/Test/test_amount_dtype_migration.py',
    ]
    verify=text(LOOP/'verify-proxy-period-evidence.ps1')
    assert 'successfulSelectedTargets' in verify
    assert 'required selected pytest target has no SUCCESS evidence' in verify
