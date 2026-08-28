"""Loop Engine v20 review-fix regression contract.

Python 3.6 syntax compatible on purpose: the Windows runner may expose 3.6 as
its default ``python``.  Runtime-only tests remain in windows-smoke.ps1.
"""
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def policy():
    return json.loads(read(".loop-engine/uat-action-policy.json"))


class V20ReviewContractTests(unittest.TestCase):
    def test_policy_and_controller_evidence_versions_are_advanced(self):
        p = policy()
        self.assertEqual(8, p["schema_version"])
        self.assertEqual(10, p["controller_evidence_schema"])
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        self.assertIn("schema_version -ne 8", proxy)
        self.assertIn("schema_version -ne 8", verifier)
        self.assertIn("controller_evidence_schema -ne 10", proxy)
        self.assertIn("controller_evidence_schema -ne 10", verifier)

    def test_git_allowlist_matches_later_work02_construction_contract(self):
        expected = [
            "Common/PeriodResolver.py",
            "Model/Order/NormalizedPvEvent.py",
            "MessageConsumer/PvEventSchema.py",
            "MessageConsumer/PvEventNormalizer.py",
            "MessageConsumer/PvEventConsumer.py",
            "User/UserStatsService.py",
            "User/EliteBonusService.py",
            "Model/Config.py",
            "Redishelper/BaseRedisModel.py",
            "MessageConsumer/Test/test_pv_event_consumer.py",
            "User/Test/test_period_resolver.py",
            "User/Test/test_pv_event_normalizer.py",
            "User/Test/test_amount_dtype_migration.py",
        ]
        self.assertEqual(expected, policy()["git_change_allowlist"])

    def test_git_line_scope_guards_exact_one_line_service_edits(self):
        p = policy()
        guards = p["git_hunk_allowlist"]
        self.assertEqual(
            [{"old_start": 32, "old_count": 1, "new_start": 32, "new_count": 1}],
            guards["User/UserStatsService.py"],
        )
        self.assertEqual(
            [{"old_start": 56, "old_count": 1, "new_start": 56, "new_count": 1}],
            guards["User/EliteBonusService.py"],
        )
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        self.assertIn("git diff --unified=0", proxy)
        self.assertIn("Test-GitChangedHunksAllowed", proxy)
        self.assertIn("line_scope_ok", proxy)
        self.assertIn("line_scope_ok", verifier)

    def test_negative_scenarios_require_zero_business_redis_side_effects(self):
        p = policy()
        self.assertEqual(
            ["forbidden-field", "schema-invalid", "expired-period"],
            p["scenarios_require_no_redis_side_effects"],
        )
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        self.assertIn("no_redis_side_effects_ok", proxy)
        self.assertIn("no_redis_side_effects_ok", verifier)
        self.assertIn("order_ledger_exists", proxy)
        self.assertIn("refund_reversal_exists", proxy)

    def test_future_period_requires_pause_barrier_and_secondary_replay(self):
        p = policy()
        self.assertIn("future-period-replay", p["consumer_observation_required_scenarios_by_stage"]["OPUS"])
        self.assertEqual("secondary", p["scenario_observe_bound_role"]["future-period-replay"])
        self.assertEqual("committed", p["scenario_expected_offset_semantics"]["future-period-replay"])
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        self.assertIn("pause_barrier_ok", proxy)
        self.assertIn("future_replay_ok", proxy)
        self.assertIn("pause_barrier_ok", verifier)
        self.assertIn("future_replay_ok", verifier)
        self.assertRegex(verifier, r"bind-primary.*future-period.*bind-secondary.*future-period-replay")

    def test_cross_period_and_duplicate_semantics_are_hard_gated(self):
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        for token in (
            "cross_period_refund_ok",
            "primary_order_amount_units",
            "refund_original_amount_units",
            "primary_refund_idempotency_absent",
            "duplicate_no_double_ok",
            "duplicate_delivery_count",
        ):
            self.assertIn(token, proxy)
            self.assertIn(token, verifier)

    def test_redis_read_is_scenario_bound_and_value_checked(self):
        p = policy()
        self.assertIn("redis_proof_contracts", p)
        self.assertIn("cross-period-refund-ledgers", p["redis_proof_contracts"])
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        for token in ("proof_id", "expectations_satisfied", "requested_keys_sha256", "values_sha256"):
            self.assertIn(token, proxy)
            self.assertIn(token, verifier)

    def test_mandatory_uat_proofs_are_required_for_opus(self):
        expected = [
            "cross-period-refund-routing",
            "duplicate-no-double",
            "pending-dispatched-recovery",
            "int64-end-to-end",
            "pause-rebalance",
            "dispatch-p99",
        ]
        p = policy()
        self.assertEqual(expected, p["mandatory_uat_proofs_by_stage"]["OPUS"])
        self.assertIn("UatProof", p["required_success_actions_by_stage"]["OPUS"])
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        self.assertIn("function Invoke-UatProof", proxy)
        self.assertIn("UatProofResult", verifier)
        self.assertIn("mandatory_uat_proofs_by_stage", verifier)

    def test_int64_migration_test_is_mandatory_selected_target(self):
        p = policy()
        self.assertIn("User/Test/test_amount_dtype_migration.py", p["pytest_selected_exact"])
        self.assertIn("User/Test/test_amount_dtype_migration.py", p["pytest_selected_required_targets"])

    def test_cleanup_requires_all_known_namespaces_for_every_delivered_identity(self):
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        self.assertIn("Get-LedgerCleanupKeys", verifier)
        self.assertIn("missing ledger cleanup key", verifier)
        self.assertIn("missing idempotency cleanup namespace", verifier)
        self.assertNotIn("foreach($identity in @($dispatchedIdentities.Keys))", verifier)

    def test_v19_regression_file_is_python36_parseable(self):
        text = read("tests/loop-engine/test_v19_regressions.py")
        self.assertNotIn("from __future__ import annotations", text)

    def test_v20_test_itself_avoids_future_annotations(self):
        lines = read("tests/loop-engine/test_v20_review_regressions.py").splitlines()
        self.assertNotIn("from " + "__future__ import annotations", lines)

    def test_active_verifier_contract_mentions_all_six_hard_proofs(self):
        text = read(".loop-engine/verifier-checkpoint-protocol.md")
        for proof in policy()["mandatory_uat_proofs_by_stage"]["OPUS"]:
            self.assertIn(proof, text)

    def test_controller_owned_producer_does_not_depend_on_candidate_tests_pvam(self):
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        self.assertIn("function Invoke-ControllerUatProducer", proxy)
        self.assertIn("producer_authority='controller-owned-v20'", proxy)
        self.assertNotIn("tests/pvam/WORK-PVAM-02/uat_message_producer.py", proxy)
        for rel in (
            ".loop-engine/automated-override.md",
            ".loop-engine/verifier-checkpoint-protocol.md",
            ".loop-engine/claude-verifier-runner.ps1",
        ):
            self.assertNotIn("tests/pvam/WORK-PVAM-02/uat_message_producer.py", read(rel))

    def test_business_value_deltas_are_controller_owned_hard_gates(self):
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        for token in (
            "business_snapshot_before",
            "business_snapshot_after",
            "primary_business_delta_units",
            "secondary_business_delta_units",
            "duplicate_business_delta_units",
            "business_value_proof_ok",
        ):
            self.assertIn(token, proxy)
            self.assertIn(token, verifier)

    def test_pending_recovery_models_completed_stages_before_ack_and_no_double(self):
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        for token in (
            "crash_window_injected",
            "business_unchanged_after_replay",
            "idempotency_present_before_restart",
        ):
            self.assertIn(token, proxy)
            self.assertIn(token, verifier)
        self.assertNotIn('status=None\\nwhile time.time()<end', proxy)

    def test_dispatch_p99_uses_fresh_nonce_and_per_sample_completion(self):
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        self.assertIn("p99_nonce", proxy)
        self.assertIn("sample_completed_at", proxy)
        self.assertIn("Guid]::NewGuid", proxy)

    def test_active_controller_docs_and_runner_use_v20_contract(self):
        for rel in (
            ".loop-engine/automated-override.md",
            ".loop-engine/verifier-checkpoint-protocol.md",
            ".loop-engine/claude-verifier-runner.ps1",
        ):
            text = read(rel)
            self.assertIn("UatProof", text)
            self.assertIn("schema-10", text)
            self.assertIn("controller-owned", text)


    def test_cleanup_covers_consumed_order_period_index(self):
        verifier = read(".loop-engine/verify-proxy-period-evidence.ps1")
        self.assertIn("order_ledger:__period_index__", verifier)

    def test_internal_restart_and_p99_reverify_candidate_sha(self):
        proxy = read(".loop-engine/uat-action-proxy.ps1")
        pending = proxy[proxy.index("function Invoke-PendingRecoveryProof"):proxy.index("function Invoke-DispatchP99Proof")]
        p99 = proxy[proxy.index("function Invoke-DispatchP99Proof"):proxy.index("function Invoke-UatProof")]
        self.assertIn("Verify-PodGitView $newPod", pending)
        self.assertIn("Get-CurrentCandidateSha", pending)
        self.assertIn("Verify-PodGitView $pod", p99)
        self.assertIn("Get-CurrentCandidateSha", p99)
        self.assertIn("Get-ConsumerLifecycleSelectedPods", p99)
        self.assertNotIn("$Request.pod", p99)
        self.assertNotIn("$Request.container", p99)


if __name__ == "__main__":
    unittest.main()
