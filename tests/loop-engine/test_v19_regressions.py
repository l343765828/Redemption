"""Loop Engine v19 security regression contract.

Installed by the v18 -> v19 security upgrade. These tests are intentionally
static/fail-closed and are complemented by tests/loop-engine/windows-smoke.ps1
on the real Windows self-hosted runner.
"""
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def fn(src: str, name: str) -> str:
    m = re.search(rf"(?m)^function\s+{re.escape(name)}\b[^\n]*\{{", src)
    if not m:
        raise AssertionError(f"function not found: {name}")
    brace = src.find("{", m.start())
    depth = 0
    quote = None
    escaped = False
    for i in range(brace, len(src)):
        c = src[i]
        if escaped:
            escaped = False
            continue
        if c == "`":
            escaped = True
            continue
        if quote:
            if c == quote:
                quote = None
            continue
        if c in ("'", '"'):
            quote = c
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():i + 1]
    raise AssertionError(f"function not closed: {name}")


class LoopEngineV19SecurityRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = read(".loop-engine/loop-state.ps1")
        cls.workflow = read(".github/workflows/loop-round.yml")
        cls.verify = read(".loop-engine/verify-proxy-period-evidence.ps1")
        cls.proxy = read(".loop-engine/uat-action-proxy.ps1")
        cls.runtime_controller = read(".loop-engine/consumer-runtime-controller-r9.py")
        cls.policy = json.loads(read(".loop-engine/uat-action-policy.json"))

    def test_gate_01_missing_candidate_sha_is_rejected(self):
        self.assertIn('Write-GitHubEnv "LOOP_CANDIDATE_SHA" $candidateSha', self.state)
        self.assertIn("ExpectedCandidateSha missing/invalid", self.verify)
        self.assertGreaterEqual(self.workflow.count("LOOP_CANDIDATE_SHA missing/invalid after stage authorization binding"), 2)

    def test_gate_02_candidate_sha_checks_are_unconditional(self):
        self.assertNotRegex(self.verify, r"if\s*\(\s*\$ExpectedCandidateSha\s+-and")
        self.assertNotRegex(self.verify, r"if\s*\(\s*\$ExpectedCandidateSha\s*\)")
        self.assertIn("candidate_sha','remote_head','host_head','pod_head", self.verify)

    def test_gate_03_output_end_stdout_cannot_close_metadata_frame(self):
        self.assertNotIn('$lines.Add("output_begin")', self.proxy)
        self.assertNotIn('$lines.Add("output_end")', self.proxy)
        self.assertIn('output_json_b64=$outputB64', self.proxy)

    def test_gate_04_metadata_shaped_stdout_is_base64_payload_only(self):
        self.assertIn("ConvertTo-Json -InputObject @($outputLines.ToArray()) -Compress", self.proxy)
        self.assertIn("ToBase64String($Utf8NoBom.GetBytes($outputJson))", self.proxy)
        self.assertNotIn("$lines.Add($safeLine)", self.proxy)

    def test_gate_05_duplicate_metadata_is_invalid(self):
        for src in (self.proxy, self.verify):
            parser = fn(src, "Read-ProxyEvidenceFields")
            self.assertIn("ContainsKey", parser)
            self.assertIn("duplicate field", parser)
            self.assertIn("malformed line", parser)

    def test_gate_06_consumer_runtime_target_is_exact_and_missing_target_is_fail_closed(self):
        target_policy = self.policy.get("consumer_runtime_target")
        self.assertIsInstance(target_policy, dict)
        self.assertEqual(target_policy.get("mode"), "scheduler-pod-temporary-process")
        target = fn(self.proxy, "Get-ConsumerLifecycleTarget")
        self.assertIn("consumer_runtime_target is missing; lifecycle mutation is fail-closed", target)
        self.assertIn("runtime namespace mismatch", target)

    def test_gate_07_nonallowlisted_target_denied_before_mutation(self):
        lifecycle = fn(self.proxy, "Invoke-ConsumerLifecycle")
        mutation = lifecycle.index("Invoke-ConsumerRuntimeController $pod $container 'replace'")
        self.assertLess(lifecycle.index("Get-ConsumerLifecycleTarget"), mutation)
        self.assertLess(lifecycle.index('Assert-ResourceAllowed "deployment"'), mutation)

    def test_gate_08_missing_container_never_falls_back_to_first_container(self):
        selected = fn(self.proxy, "Get-ConsumerLifecycleSelectedPods")
        self.assertIn("Consumer runtime host container not found/ambiguous", selected)
        self.assertIn("matchingContainers.Count -ne 1", selected)
        self.assertNotIn("containerStatuses[0]", selected)

    def test_gate_09_consumer_binding_does_not_mutate_scheduler_deployment(self):
        lifecycle = fn(self.proxy, "Invoke-ConsumerLifecycle")
        self.assertNotIn("set','env", lifecycle)
        self.assertNotIn("'scale'", lifecycle)
        self.assertNotIn("'rollout','restart'", lifecycle)
        self.assertIn("Invoke-ConsumerRuntimeController", lifecycle)

    def test_gate_10_pod_prefix_and_cycle_scope_checked_before_mutation(self):
        lifecycle = fn(self.proxy, "Invoke-ConsumerLifecycle")
        mutation = lifecycle.index("Invoke-ConsumerRuntimeController $pod $container 'replace'")
        self.assertLess(lifecycle.index("Assert-ConsumerLifecyclePodPrefixCoveredByScope"), mutation)
        self.assertLess(lifecycle.index("Get-ConsumerLifecycleSelectedPods"), mutation)

    def test_gate_11_runtime_state_is_execution_scoped_and_secret_free(self):
        self.assertIn('DEFAULT_RUNTIME_ROOT = "/tmp/pvam-uat-consumer"', self.runtime_controller)
        self.assertIn('"execution_id"', self.runtime_controller)
        state_block = self.runtime_controller[
            self.runtime_controller.index("state = {"):
            self.runtime_controller.index("_atomic_write_json(state_path, state)")
        ]
        self.assertNotIn("REDIS_PASSWORD", state_block)
        self.assertNotIn("kafka_bootstrap", state_block)

    def test_gate_12_runtime_controller_failure_is_explicit_fail_closed(self):
        lifecycle = fn(self.proxy, "Invoke-ConsumerLifecycle")
        self.assertIn("ConsumerLifecycle runtime replace failed", lifecycle)
        self.assertIn("ConsumerLifecycle runtime binding verification failed", lifecycle)
        self.assertIn('"ok": False', self.runtime_controller)
        self.assertIn("raise SystemExit(1)", self.runtime_controller)

    def test_gate_13_controller_supports_explicit_process_restore(self):
        lifecycle = fn(self.proxy, "Invoke-ConsumerLifecycle")
        self.assertIn("Invoke-ConsumerRuntimeController $pod $container 'stop'", lifecycle)
        self.assertIn("matching_process_count=0", lifecycle)
        self.assertIn("operation='restore'", lifecycle)
        required = self.policy["required_consumer_lifecycle_ops_by_stage"]
        self.assertEqual(required["OPUS"][-1], "restore")
        self.assertEqual(required["FABLE"][-1], "restore")

    def test_gate_14_sidecar_env_cannot_be_changed_by_consumer_bind(self):
        lifecycle = fn(self.proxy, "Invoke-ConsumerLifecycle")
        selected = fn(self.proxy, "Get-ConsumerLifecycleSelectedPods")
        self.assertIn("$container", lifecycle.lower())
        self.assertIn("matchingContainers", selected)
        self.assertNotIn("-c '*'", lifecycle)
        self.assertNotIn("set','env", lifecycle)

    def test_gate_15_forged_stdout_cannot_satisfy_full_pass(self):
        self.assertEqual(self.policy.get("controller_evidence_schema"), 10)
        self.assertNotIn("output_begin", self.verify)
        self.assertNotIn("output_end", self.verify)
        self.assertIn("duplicate field", self.verify)
        self.assertIn("ExpectedCandidateSha missing/invalid", self.verify)
        self.assertGreaterEqual(self.workflow.count("LOOP_CANDIDATE_SHA disagrees with pushed-sha.txt"), 2)


    def test_gate_16_protected_digest_hashes_current_controller_evidence(self):
        protected = read(".loop-engine/protected-evidence-hash.ps1")
        self.assertIn("controller-evidence\\schema-10", protected)
        self.assertNotIn("controller-evidence\\schema-9", protected)
        self.assertNotIn("controller-evidence\\schema-8", protected)

    def test_gate_17_lifecycle_dispatch_token_metadata_matches_v19_operations(self):
        start = self.proxy.index('        "ConsumerLifecycle" {')
        end = self.proxy.index('        "ConsumerObserve" {', start)
        dispatch = self.proxy[start:end]
        self.assertIn("@('bind-primary','bind-secondary','status','restore','logs')", dispatch)
        self.assertIn("$required=@('exec')", dispatch)
        self.assertNotIn("@('deploy','restart','scale')", dispatch)
        self.assertNotIn("$op -eq 'stop'", dispatch)

    def test_gate_18_v19_lifecycle_invariants_survive_v20_schema10_contract(self):
        override = read(".loop-engine/automated-override.md")
        protocol = read(".loop-engine/verifier-checkpoint-protocol.md")
        self.assertTrue(override.startswith("# Loop Engine Automated Verifier Override v20"))
        for src in (override, protocol):
            self.assertIn("schema-10", src)
            self.assertIn("ConsumerLifecycle", src)
            self.assertIn("restore", src)
            self.assertIn("consumer_runtime_target", src)

    def test_gate_19_active_schema_comments_match_current_wire_format(self):
        prepare = read(".loop-engine/prepare-verifier-state.ps1")
        self.assertIn("Controller evidence schema 10", prepare)
        self.assertNotIn("active v18 evidence directory", prepare)
        self.assertIn("stronger v20 semantics", self.proxy)

    def test_gate_20_readme_preserves_v19_history_and_deploys_v20_surface(self):
        readme = read("README-LOOP-ENGINE-FINAL.md")
        self.assertIn("REVIEW-FIXES-v19.md", readme)
        self.assertIn("docs/LOOP-ENGINE-V19-DESIGN.md", readme)
        self.assertIn("tests/loop-engine/test_v19_regressions.py", readme)
        self.assertIn("REVIEW-FIXES-v20.md", readme)
        self.assertIn("docs/LOOP-ENGINE-V20-DESIGN.md", readme)
        self.assertIn("tests/loop-engine/test_v20_review_regressions.py", readme)
        self.assertIn("[V20-CONTROLLER-CONTRACT-SMOKE] PASS", readme)
        self.assertIn("controller-evidence/schema-10", readme)
        self.assertIn("consumer_runtime_target", readme)
        self.assertIn("ConsumerLifecycle restore", readme)


if __name__ == "__main__":
    unittest.main()
