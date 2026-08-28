from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[2]
PROXY = (ROOT / '.loop-engine' / 'uat-action-proxy.ps1').read_text(encoding='utf-8')
POLICY = json.loads((ROOT / '.loop-engine' / 'uat-action-policy.json').read_text(encoding='utf-8'))
VERIFY = (ROOT / '.loop-engine' / 'verify-proxy-period-evidence.ps1').read_text(encoding='utf-8')
PREP = (ROOT / '.loop-engine' / 'prepare-verifier-state.ps1').read_text(encoding='utf-8')
WF = (ROOT / '.github' / 'workflows' / 'loop-round.yml').read_text(encoding='utf-8')
RUNNER = (ROOT / '.loop-engine' / 'claude-verifier-runner.ps1').read_text(encoding='utf-8')


def test_policy_schema_and_controller_evidence_are_versioned():
    assert POLICY['schema_version'] >= 6
    assert 'controller_evidence_schema' in POLICY
    schema = str(POLICY['controller_evidence_schema'])
    assert f'$ControllerEvidenceSchema = "{schema}"' in PROXY
    assert 'controller-evidence\\schema-{0}\\cycle-{1}\\round-{2}\\{3}' in PROXY
    assert f'controller-evidence\\schema-{schema}\\cycle-' in WF
    assert 'schema=8' in PREP


def test_consumer_lifecycle_is_structured_and_required():
    assert '"ConsumerLifecycle"' in PROXY
    assert 'PVAM_BOUND_PERIOD' in PROXY
    assert 'PVAM_CALC_MONTH' in PROXY
    assert 'PVAM_LEDGER_KEY_PREFIX' in PROXY
    assert 'ConsumerLifecycleResult' in PROXY
    assert 'bind-primary' in PROXY and 'bind-secondary' in PROXY
    assert 'ConsumerLifecycle' in POLICY['required_success_actions_by_stage']['OPUS']
    assert 'ConsumerLifecycle' in POLICY['required_success_actions_by_stage']['FABLE']
    opus_ops = POLICY['required_consumer_lifecycle_ops_by_stage']['OPUS']
    assert opus_ops[:2] == ['bind-primary', 'bind-secondary']
    if int(POLICY['controller_evidence_schema']) >= 9:
        assert opus_ops[-1] == 'restore'


def test_all_three_incremental_idempotency_namespaces_are_governed():
    prefixes = POLICY['redis_exact_cleanup_prefixes']
    reads = POLICY['redis_read_prefixes']
    for template in [
        'system:idempotency:{period}:',
        'system:idempotency:placement:{period}:',
        'system:idempotency:elite:{period}:',
    ]:
        assert template in prefixes
        assert template in reads
    assert 'required_idempotency_namespaces' in POLICY
    assert set(POLICY['required_idempotency_namespaces']) == {'userstats','placement','elite'}
    assert 'missing idempotency cleanup namespace' in VERIFY


def test_runtime_candidate_sha_gate_requires_gitupdate_and_runtime_verification():
    for stage in ('OPUS','FABLE'):
        assert 'GitUpdate' in POLICY['required_success_actions_by_stage'][stage]
    assert 'GitUpdateResult' in PROXY
    assert 'pod_head' in PROXY and 'host_head' in PROXY and 'remote_head' in PROXY
    assert 'runtime candidate SHA mismatch' in VERIFY


def test_gitaudit_handoff_and_change_allowlist_are_hard_gates():
    assert 'git_change_allowlist' in POLICY
    assert POLICY['git_change_allowlist']
    assert 'IMPLEMENTATION_HANDOFF.md' in PROXY
    assert 'handoff_candidate_sha' in PROXY
    assert 'changed_files' in PROXY
    assert 'unauthorized changed file' in PROXY
    assert 'handoff candidate SHA mismatch' in VERIFY
    assert 'changed file allowlist' in VERIFY
    assert 'CONTROLLER CANDIDATE CONTRACT' in WF


def test_post_kafka_semantics_are_required():
    for stage in ('OPUS','FABLE'):
        required = POLICY['required_success_actions_by_stage'][stage]
        for action in ['RedisReadExactKeys','ConsumerObserve']:
            assert action in required
    assert 'ConsumerObserveResult' in PROXY
    assert 'delivery_status' in PROXY
    assert 'idempotency_namespaces' in PROXY
    assert 'required consumer observation missing' in VERIFY
    assert 'delivery ledger is not DISPATCHED' in VERIFY


def test_upgrade_does_not_scan_old_controller_evidence():
    assert 'controller_evidence_schema' in POLICY
    assert 'controller-evidence\\schema-' in PROXY
    assert 'controller-evidence\\schema-' in WF
    assert 'archive legacy controller evidence' in PREP.lower() or 'controller evidence schema' in PREP.lower()


def test_runner_contract_mentions_lifecycle_and_semantic_assertions():
    assert 'ConsumerLifecycle' in RUNNER
    assert 'ConsumerObserve' in RUNNER
    assert 'GitUpdate' in RUNNER
    assert 'three idempotency namespaces' in RUNNER.lower() or 'placement' in RUNNER and 'elite' in RUNNER


def test_consumer_lifecycle_calc_month_and_runtime_sha_are_controller_owned():
    assert ('ConsumerLifecycle calc_month is controller-owned' in PROXY or
            'ConsumerLifecycle calc_month is controller governed' in PROXY)
    assert ('existing deployment PVAM_CALC_MONTH' in PROXY or
            'ConsumerLifecycle governed PVAM_CALC_MONTH' in PROXY)
    assert "Verify-PodGitView" in PROXY
    assert "pod_repo_heads" in PROXY
    assert "ConsumerLifecycle runtime candidate SHA mismatch" in VERIFY
    assert "ConsumerLifecycle Pod/NFS candidate SHA mismatch" in VERIFY


def test_consumer_observe_proves_offsets_and_expected_exception_reasons():
    expected = POLICY['scenario_expected_exception_reason']
    assert expected['payload-drift'] == 'EVENT_IDENTITY_CONFLICT'
    assert expected['forbidden-field'] == 'D9B_FORBIDDEN_FIELD'
    assert expected['schema-invalid'] == 'SCHEMA_VIOLATION'
    assert expected['expired-period'] == 'EXPIRED_PERIOD'
    assert POLICY['scenario_expected_offset_semantics']['future-period'] == 'not-committed'
    assert 'pvam-uat-observe-' in PROXY
    assert 'committed_offset' in PROXY
    assert 'expected exception reason' in PROXY
    assert 'ConsumerObserve expected exception reason missing' in VERIFY
    assert 'offset_semantics_ok' in VERIFY


def test_git_audit_controller_rechecks_change_allowlist_and_handoff():
    assert 'handoff_candidate_sha' in PROXY
    assert 'handoff changed file set does not equal git diff changed file allowlist set' in PROXY
    assert 'Test-ChangedPathAllowed' in VERIFY
    assert 'changed file outside controller allowlist' in VERIFY


def test_consumer_observe_single_delivery_is_serialized_as_json_array():
    assert 'ConvertTo-Json -Depth 20 -InputObject @($records' in PROXY


def test_consumer_rebind_reads_calc_month_without_probing_old_pods_first():
    assert 'function Get-DeploymentGovernedEnv' in PROXY
    lifecycle_start = PROXY.index('function Invoke-ConsumerLifecycle')
    bind_start = PROXY.index("if($op -in @('bind-primary','bind-secondary'))", lifecycle_start)
    set_pos = PROXY.index("$set=Invoke-Kubectl", bind_start)
    state_pos = PROXY.index("$state=Get-DeploymentConsumerState", set_pos)
    before_pos = PROXY.index('$before=Get-DeploymentGovernedEnv', lifecycle_start)
    assert lifecycle_start < before_pos < bind_start < set_pos < state_pos
    assert 'Get-DeploymentConsumerState' not in PROXY[lifecycle_start:set_pos]


def test_runner_does_not_tell_verifier_to_supply_controller_owned_calc_month():
    assert 'Do not supply `calc_month`' in RUNNER
    assert 'controller reads the governed Deployment' in RUNNER
    assert 'Supply the approved six-digit `calc_month`' not in RUNNER


def test_v18_invariants_survive_current_v20_managed_contract():
    override = (ROOT / '.loop-engine' / 'automated-override.md').read_text(encoding='utf-8')
    protocol = (ROOT / '.loop-engine' / 'verifier-checkpoint-protocol.md').read_text(encoding='utf-8')
    assert override.startswith('# Loop Engine Automated Verifier Override v20')
    assert 'managed by Loop Engine v20' in override
    assert '## v20 consumer lifecycle, evidence integrity, and runtime acceptance' in override
    assert '## v20 consumer lifecycle, three-chain, and evidence-schema contract' in protocol
    assert 'bind-primary' in override and 'bind-secondary' in override and 'restore' in override


def test_windows_smoke_covers_current_schema_and_lifecycle_contract_without_k8s_mutation():
    smoke = (ROOT / 'tests' / 'loop-engine' / 'windows-smoke.ps1').read_text(encoding='utf-8')
    assert '[V20-CONTROLLER-CONTRACT-SMOKE] PASS' in smoke
    assert 'controller-evidence\\schema-{0}\\cycle-{1}\\round-{2}\\{3}' in smoke
    assert 'ConsumerLifecycle calc_month is controller governed' in smoke
    assert 'Get-DeploymentGovernedEnv' in smoke
    assert 'controller-evidence\\schema-10\\cycle-{0}\\round-{1}\\opus' in smoke


def test_readme_deploys_v20_and_preserves_v18_v19_history():
    readme = (ROOT / 'README-LOOP-ENGINE-FINAL.md').read_text(encoding='utf-8')
    assert 'REVIEW-FIXES-v20.md' in readme
    assert 'docs/LOOP-ENGINE-V20-DESIGN.md' in readme
    assert 'tests/loop-engine/test_v20_review_regressions.py' in readme
    assert 'REVIEW-FIXES-v19.md' in readme and 'docs/LOOP-ENGINE-V19-DESIGN.md' in readme
    assert 'REVIEW-FIXES-v18.md' in readme and 'docs/LOOP-ENGINE-V18-DESIGN.md' in readme
    assert 'Before the first v20 `auto`' in readme
    assert 'controller-evidence/schema-10' in readme
    assert 'consumer_lifecycle_targets' in readme
    assert 'ConsumerLifecycle restore' in readme
    assert 'deploy,restart,scale' in readme
    assert 'immutable Cycle grant' in readme
    assert 'new Cycle' in readme


def test_protected_digest_hashes_active_schema10_opus_controller_evidence():
    protected = (ROOT / '.loop-engine' / 'protected-evidence-hash.ps1').read_text(encoding='utf-8')
    assert 'controller-evidence\\schema-10\\cycle-{0}\\round-{1}\\opus' in protected
    assert 'out/controller-evidence/schema-10/cycle-{0}/round-{1}/opus' in protected
    assert 'controller-evidence\\schema-9\\cycle-{0}\\round-{1}\\opus' not in protected
    assert 'controller-evidence\\schema-8\\cycle-{0}\\round-{1}\\opus' not in protected
    assert 'controller-evidence\\cycle-{0}\\round-{1}\\opus' not in protected


def test_opus_observes_every_required_kafka_scenario_end_to_end():
    required = set(POLICY['required_kafka_scenarios_by_stage']['OPUS'])
    observed = set(POLICY['consumer_observation_required_scenarios_by_stage']['OPUS'])
    assert required <= observed
    assert observed - required == {'future-period-replay'}
    assert {'forbidden-field', 'schema-invalid'} <= observed


def test_active_override_has_no_stale_unversioned_controller_evidence_contract():
    override = (ROOT / '.loop-engine' / 'automated-override.md').read_text(encoding='utf-8')
    assert '.loop-output/controller-evidence/cycle-N/round-M/<stage>/' not in override
    assert '.loop-output/controller-evidence/schema-10/cycle-N/round-M/<stage>/' in override
    for action in ['GitUpdate', 'ConsumerLifecycle', 'ConsumerObserve']:
        assert action in override


def test_protocol_has_no_stale_unversioned_controller_evidence_path():
    protocol = (ROOT / '.loop-engine' / 'verifier-checkpoint-protocol.md').read_text(encoding='utf-8')
    assert '.loop-output/controller-evidence/cycle-N/round-M/<stage>/' not in protocol
    assert '.loop-output/controller-evidence/schema-10/cycle-N/round-M/<stage>/' in protocol


def test_opus_lifecycle_sequence_requires_primary_drain_then_secondary():
    assert '$lifecycleOrder' in VERIFY
    assert '$observeOrder' in VERIFY
    assert 'ConsumerLifecycle operation order invalid' in VERIFY
    assert 'period-switch lifecycle sequence invalid' in VERIFY
    assert "'drain-sentinel'" in VERIFY


def test_drain_observation_checks_previous_container_logs_before_rebind():
    assert "'--previous'" in PROXY
    assert 'previousLogText' in PROXY
    assert "PERIOD DRAIN COMPLETE" in PROXY


def test_kafka_scenario_period_and_consumer_binding_are_controller_owned():
    roles = POLICY['scenario_period_role']
    binds = POLICY['scenario_required_bound_role']
    assert roles['future-period'] == 'secondary'
    assert roles['drain-sentinel'] == 'secondary'
    assert roles['expired-period'] == 'primary'
    assert binds['future-period'] == 'primary'
    assert binds['drain-sentinel'] == 'primary'
    assert binds['expired-period'] == 'secondary'
    assert binds['cross-period-refund'] == 'primary'
    assert 'period_role is controller-owned' in PROXY
    assert 'Get-LatestConsumerLifecycleSemantic' in PROXY
    assert 'scenario required Consumer binding mismatch' in PROXY


def test_consumer_observation_binding_is_controller_owned_per_scenario():
    observe = POLICY['scenario_observe_bound_role']
    assert observe['future-period'] == 'primary'
    assert observe['drain-sentinel'] == 'primary'
    assert observe['cross-period-refund'] == 'secondary'
    assert observe['expired-period'] == 'secondary'
    assert 'ConsumerObserve required Consumer binding mismatch' in PROXY


def test_runner_does_not_let_verifier_choose_kafka_period_role():
    assert 'Do not supply `period_role`' in RUNNER
    assert 'scenario-to-period/binding policy' in RUNNER
