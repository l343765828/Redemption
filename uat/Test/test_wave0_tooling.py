import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from uat.scripts.build_callgraph import CallgraphBuilder
from uat.scripts.build_traceability_manifest import TraceabilityBuilder
from uat.scripts.verify_evidence_pack import (
    EvidenceValidationError,
    EvidenceValidator,
    validate_schema_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_evidence_and_traceability_contract(tmp_path: Path) -> None:
    evidence_validator = EvidenceValidator(
        REPO_ROOT / "evidence" / "manifest.schema.json"
    )
    manifest = {
        "validation_status": "BLOCKED",
        "reason": "DEC-013 not approved",
        "command": ["pytest", "-q"],
        "exit_code": None,
    }
    evidence_validator.validate(manifest)
    out = tmp_path / "traceability.json"
    TraceabilityBuilder().build(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["retired_tests"] == ["TC-000"]
    assert data["orphan_required_nodes"] == []


class EvidenceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = EvidenceValidator(
            REPO_ROOT / "evidence" / "manifest.schema.json"
        )

    def test_schema_declares_separate_status_domains(self) -> None:
        schema_path = REPO_ROOT / "evidence" / "manifest.schema.json"
        validate_schema_contract(schema_path)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertNotEqual(
            set(schema["properties"]["validation_status"]["enum"]),
            set(schema["properties"]["artifact_status"]["enum"]),
        )

    def test_pass_cannot_be_inferred_from_exit_code_alone(self) -> None:
        with self.assertRaises(EvidenceValidationError):
            self.validator.validate(
                {
                    "validation_status": "PASS",
                    "reason": "only an exit code was captured",
                    "command": ["python", "-m", "pytest", "-q"],
                    "exit_code": 0,
                }
            )

    def test_referenced_artifact_hash_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "stdout.log"
            artifact.write_text("captured output\n", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.validator.validate(
                {
                    "artifact_status": "AVAILABLE",
                    "validation_status": "BLOCKED",
                    "reason": "review signature is still missing",
                    "command": ["pytest", "-q"],
                    "exit_code": 0,
                    "sha256": {"stdout.log": digest},
                },
                manifest_dir=root,
            )

    def test_manifest_rejects_secret_bearing_keys(self) -> None:
        with self.assertRaises(EvidenceValidationError):
            self.validator.validate(
                {
                    "validation_status": "BLOCKED",
                    "reason": "external database is unavailable",
                    "command": ["probe"],
                    "exit_code": None,
                    "environment": {"password": "must-not-be-recorded"},
                }
            )


class TraceabilityContractTests(unittest.TestCase):
    def test_every_required_node_is_linked_and_tc_000_is_retired(self) -> None:
        data = TraceabilityBuilder().data()
        self.assertEqual(["TC-000"], data["retired_tests"])
        self.assertEqual([], data["orphan_required_nodes"])
        self.assertEqual(14, len(data["acceptance_criteria"]))
        for mapping in data["acceptance_criteria"].values():
            self.assertTrue(mapping["steps"])
            self.assertTrue(mapping["tests"])
            self.assertTrue(mapping["evidence"])


class CallgraphContractTests(unittest.TestCase):
    def test_test_and_demo_references_do_not_become_production_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "service.py").write_text(
                "class TopologyMutationService:\n    pass\n",
                encoding="utf-8",
            )
            (root / "entry.py").write_text(
                "from service import TopologyMutationService\n"
                "if __name__ == '__main__':\n"
                "    TopologyMutationService()\n",
                encoding="utf-8",
            )
            (root / "tests").mkdir()
            (root / "tests" / "test_topology.py").write_text(
                "from service import TopologyMutationService\n",
                encoding="utf-8",
            )
            (root / "demo").mkdir()
            (root / "demo" / "topology_demo.py").write_text(
                "from service import TopologyMutationService\n",
                encoding="utf-8",
            )
            (root / "old_bak.py").write_text(
                "TopologyMutationService()\n", encoding="utf-8"
            )

            data = CallgraphBuilder(root, ["TopologyMutationService"]).data()
            self.assertTrue(data["references"]["production"])
            self.assertTrue(data["references"]["test"])
            self.assertTrue(data["references"]["demo"])
            all_paths = [
                item["path"]
                for group in data["references"].values()
                for item in group
            ]
            self.assertNotIn("old_bak.py", all_paths)
            self.assertEqual("BLOCKED", data["validation_status"])
            self.assertIn("runtime trace not supplied", data["blockers"])
            self.assertNotEqual("HIGH", data["CALLGRAPH_CONFIDENCE"])


class InitialManifestTests(unittest.TestCase):
    def test_external_manifests_do_not_claim_pass(self) -> None:
        for relative in [
            "environment_manifest.yaml",
            "schema_manifest.yaml",
            "config_snapshot_manifest.yaml",
            "test_run_manifest.yaml",
        ]:
            content = (REPO_ROOT / "uat" / relative).read_text(encoding="utf-8")
            self.assertNotIn("validation_status: PASS", content)
        callgraph = json.loads(
            (REPO_ROOT / "uat" / "callgraph_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("BLOCKED", callgraph["validation_status"])


if __name__ == "__main__":
    unittest.main()
