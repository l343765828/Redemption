#!/usr/bin/env python3
"""Validate a WORK parent tree against the release-anchored approved registry."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

HEX64 = re.compile(r"[0-9a-f]{64}")
EVIDENCE_FIELDS = (
    ("patch_path", "patch_sha256"),
    ("scope_result_path", "scope_result_sha256"),
    ("parent_provenance_path", "parent_provenance_sha256"),
    ("approval_record_path", "approval_record_sha256"),
)


class ProvenanceError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ProvenanceError(message)


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path, label: str) -> dict:
    if not path.is_file() or path.is_symlink():
        fail(f"missing or unsafe {label}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {label}: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def lexical_absolute(path: Path) -> Path:
    """Return an absolute, lexically normalised path without following symlinks."""
    return Path(os.path.abspath(os.fspath(path)))


def require_no_symlink_chain(path: Path, anchor: Path, label: str) -> Path:
    """Reject symlinks in *path* or any component at/below *anchor*.

    This check intentionally runs on lexical paths before any ``Path.resolve()``
    call.  Resolving first would erase the link identity and make a later
    ``is_symlink()`` check ineffective.
    """
    target = lexical_absolute(path)
    root = lexical_absolute(anchor)
    try:
        relative = target.relative_to(root)
    except ValueError:
        fail(f"{label} is outside the trusted package root: {target}")

    current = root
    candidates = [current]
    for component in relative.parts:
        current = current / component
        candidates.append(current)

    for candidate in candidates:
        try:
            mode = candidate.lstat().st_mode
        except FileNotFoundError:
            fail(f"{label} path component does not exist: {candidate}")
        except OSError as exc:
            fail(f"cannot inspect {label} path component {candidate}: {exc}")
        if stat.S_ISLNK(mode):
            fail(f"{label} path contains a symlink: {candidate}")
    return target


def package_trust_root(registry_arg: Path) -> tuple[Path, Path, str]:
    """Resolve the canonical package root from this validator, never from caller input."""
    script_lexical = lexical_absolute(Path(__file__))
    control_lexical = script_lexical.parent
    package_lexical = control_lexical.parent
    if control_lexical.name != "05_CONTROL":
        fail(f"validator is not installed at canonical control path: {control_lexical}")
    require_no_symlink_chain(
        script_lexical, package_lexical, "parent provenance validator"
    )

    canonical_registry_lexical = (
        control_lexical / "WORK_APPROVED_COMMIT_REGISTRY.json"
    )
    require_no_symlink_chain(
        canonical_registry_lexical,
        package_lexical,
        "canonical approved registry",
    )

    if ".." in registry_arg.parts:
        fail("approved registry path must not contain '..'")
    supplied_lexical = lexical_absolute(registry_arg)
    if supplied_lexical != canonical_registry_lexical:
        fail(
            "approved registry must be the canonical release file "
            f"{canonical_registry_lexical}; got {supplied_lexical}"
        )
    require_no_symlink_chain(
        supplied_lexical, package_lexical, "supplied approved registry"
    )

    package_root = package_lexical.resolve(strict=True)
    control_dir = control_lexical.resolve(strict=True)
    canonical_registry = canonical_registry_lexical.resolve(strict=True)
    if not canonical_registry.is_file():
        fail("canonical approved registry is missing or is a symlink")

    actual = sha256_file(canonical_registry)
    document_manifest = read_json(
        package_root / "DOCUMENT_MANIFEST.json", "DOCUMENT_MANIFEST.json"
    )
    version_manifest = read_json(
        control_dir / "VERSION_REFERENCE_MANIFEST.json",
        "VERSION_REFERENCE_MANIFEST.json",
    )
    doc_anchor = document_manifest.get("approved_commit_registry")
    ver_anchor = version_manifest.get("artifact_hashes", {}).get(
        "approved_commit_registry"
    )
    for label, anchor in (
        ("DOCUMENT_MANIFEST", doc_anchor),
        ("VERSION_REFERENCE_MANIFEST", ver_anchor),
    ):
        if not isinstance(anchor, dict):
            fail(f"{label} approved_commit_registry trust anchor is missing")
        if anchor.get("path") != "05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json":
            fail(f"{label} registry canonical path mismatch")
        if anchor.get("sha256") != actual:
            fail(
                f"{label} registry SHA-256 mismatch: "
                f"{anchor.get('sha256')} != {actual}"
            )
        if anchor.get("schema_version") != 2:
            fail(f"{label} registry schema anchor must be 2")
    if document_manifest.get("approved_commit_registry_sha256") != actual:
        fail("DOCUMENT_MANIFEST flat registry SHA-256 field mismatch")
    return package_root, canonical_registry, actual


def safe_evidence_path(package_root: Path, raw: object, label: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        fail(f"{label} path is required")
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts:
        fail(f"{label} must be a safe package-relative path: {raw}")
    lexical = require_no_symlink_chain(
        package_root / rel, package_root, f"{label} evidence"
    )
    resolved = lexical.resolve(strict=True)
    try:
        resolved.relative_to(package_root)
    except ValueError:
        fail(f"{label} escapes package root: {raw}")
    if not resolved.is_file():
        fail(f"{label} evidence file does not exist or is a symlink: {raw}")
    return resolved


def verify_entry_evidence(
    package_root: Path, entry: dict, work_id: str
) -> dict[str, dict[str, str]]:
    verified: dict[str, dict[str, str]] = {}
    for path_field, hash_field in EVIDENCE_FIELDS:
        expected = entry.get(hash_field)
        if not isinstance(expected, str) or not HEX64.fullmatch(expected):
            fail(f"trusted registry {work_id}.{hash_field} must be a 64-hex SHA-256")
        evidence = safe_evidence_path(
            package_root, entry.get(path_field), f"{work_id}.{path_field}"
        )
        actual = sha256_file(evidence)
        if actual != expected:
            fail(
                f"trusted registry evidence hash mismatch for "
                f"{work_id}.{path_field}: {actual} != {expected}"
            )
        verified[path_field.removesuffix("_path")] = {
            "path": evidence.relative_to(package_root).as_posix(),
            "sha256": actual,
        }
    return verified


def direct_prerequisites(
    scope: dict, work_id: str, stage: str | None = None
) -> set[str]:
    rule = scope.get("works", {}).get(work_id)
    if rule is None:
        fail(f"unknown work_id in scope: {work_id}")
    if work_id == "WORK-PVAM-08":
        stage_map = rule.get("stage_prerequisites", {})
        if stage not in stage_map:
            fail("WORK-PVAM-08 requires --stage A or --stage B")
        return set(stage_map[stage])
    if stage is not None:
        fail(f"{work_id} does not accept --stage")
    return set(rule.get("prerequisites", []))


def prerequisite_closure(
    scope: dict, work_id: str, stage: str | None
) -> set[str]:
    closure: set[str] = set()
    visiting: set[str] = set()

    def visit(current: str, current_stage: str | None = None) -> None:
        if current in visiting:
            fail(f"prerequisite cycle detected at {current}")
        visiting.add(current)
        for dependency in direct_prerequisites(scope, current, current_stage):
            if dependency not in closure:
                closure.add(dependency)
                visit(dependency, None)
        visiting.remove(current)

    visit(work_id, stage)
    return closure


def load_registry(
    path: Path, base_sha: str
) -> tuple[dict[str, dict], str, dict, Path]:
    package_root, canonical, trust_sha = package_trust_root(path)
    data = read_json(canonical, "WORK_APPROVED_COMMIT_REGISTRY.json")
    if data.get("schema_version") != 2:
        fail("approved commit registry schema_version must be 2")
    if data.get("registry_id") != "WORK-APPROVED-COMMIT-REGISTRY-PVAM-v2":
        fail("approved commit registry_id mismatch")
    if data.get("canonical_path") != "05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json":
        fail("approved commit registry canonical_path mismatch")
    if data.get("baseline_commit") != base_sha:
        fail("approved commit registry baseline mismatch")
    entries = data.get("entries")
    if not isinstance(entries, list):
        fail("approved commit registry entries must be a list")

    by_id: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("work_id"), str):
            fail(f"invalid approved registry entry: {entry!r}")
        wid = entry["work_id"]
        if wid in by_id:
            fail(f"duplicate approved registry entry: {wid}")
        by_id[wid] = entry
        status = entry.get("approval_status")
        if status not in {"PENDING", "APPROVED", "REVOKED"}:
            fail(f"invalid approval_status for {wid}: {status!r}")
        if status == "APPROVED":
            if not isinstance(entry.get("commit_sha"), str) or not isinstance(
                entry.get("tree_sha"), str
            ):
                fail(f"APPROVED registry entry lacks commit/tree: {wid}")
            verify_entry_evidence(package_root, entry, wid)
        elif any(
            entry.get(field) is not None
            for pair in EVIDENCE_FIELDS
            for field in pair
        ):
            fail(
                f"non-APPROVED registry entry must not carry evidence bindings: {wid}"
            )
    return by_id, trust_sha, data, package_root


def require_approved_entry(
    package_root: Path,
    entry: dict,
    work_id: str,
    commit_sha: str,
    tree_sha: str,
) -> dict:
    if entry.get("approval_status") != "APPROVED":
        fail(f"prerequisite WORK is not APPROVED in trusted registry: {work_id}")
    if entry.get("commit_sha") != commit_sha or entry.get("tree_sha") != tree_sha:
        fail(f"trusted registry commit/tree mismatch for {work_id}")
    for field in ("approver_identity", "approver_role", "approved_at"):
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            fail(f"trusted registry {work_id}.{field} is required")
    return verify_entry_evidence(package_root, entry, work_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--parent-commit", required=True)
    parser.add_argument("--parent-tree", required=True)
    parser.add_argument("--work-commit", required=True)
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--approved-registry", required=True)
    parser.add_argument("--stage")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    repo = Path(git(Path(args.repo), "rev-parse", "--show-toplevel"))
    scope = read_json(Path(args.scope), "WORK_SCOPE_ALLOWLIST")
    provenance = read_json(Path(args.provenance), "PARENT_PROVENANCE")
    if scope.get("schema_version") != 3:
        fail("WORK_SCOPE_ALLOWLIST schema_version must be 3")

    base_sha = git(repo, "rev-parse", f"{args.base}^{{commit}}")
    registry_by_id, registry_sha, registry_doc, package_root = load_registry(
        Path(args.approved_registry), base_sha
    )

    direct_expected = direct_prerequisites(scope, args.work_id, args.stage)
    closure_expected = prerequisite_closure(scope, args.work_id, args.stage)
    if provenance.get("schema_version") != 2:
        fail("parent provenance schema_version must be 2")
    if provenance.get("work_id") != args.work_id:
        fail("parent provenance work_id mismatch")
    if provenance.get("stage") != args.stage:
        fail(
            f"parent provenance stage mismatch: "
            f"{provenance.get('stage')!r} != {args.stage!r}"
        )
    if provenance.get("approved_commit_registry_sha256") != registry_sha:
        fail("parent provenance approved_commit_registry_sha256 mismatch")

    parent_commit_sha = git(repo, "rev-parse", f"{args.parent_commit}^{{commit}}")
    parent_tree_sha = git(repo, "rev-parse", f"{args.parent_tree}^{{tree}}")
    parent_actual_tree = git(repo, "rev-parse", f"{parent_commit_sha}^{{tree}}")
    work_commit_sha = git(repo, "rev-parse", f"{args.work_commit}^{{commit}}")
    work_tree_sha = git(repo, "rev-parse", f"{work_commit_sha}^{{tree}}")
    work_first_parent = git(repo, "rev-parse", f"{work_commit_sha}^1")

    for field, actual in (
        ("root_baseline_sha", base_sha),
        ("parent_commit_sha", parent_commit_sha),
        ("parent_tree_sha", parent_tree_sha),
        ("work_commit_sha", work_commit_sha),
    ):
        if provenance.get(field) != actual:
            fail(f"parent provenance {field} mismatch")
    if parent_actual_tree != parent_tree_sha:
        fail("parent commit tree does not equal supplied parent tree")
    if work_first_parent != parent_commit_sha:
        fail(
            f"WORK commit first parent mismatch: "
            f"{work_first_parent} != {parent_commit_sha}"
        )

    direct_actual = provenance.get("direct_prerequisites")
    if not isinstance(direct_actual, list) or len(direct_actual) != len(
        set(direct_actual)
    ):
        fail("direct_prerequisites must be a unique list")
    if set(direct_actual) != direct_expected:
        fail(
            "direct prerequisite set mismatch: "
            f"missing={sorted(direct_expected-set(direct_actual))} "
            f"extra={sorted(set(direct_actual)-direct_expected)}"
        )

    included = provenance.get("included_works")
    order = provenance.get("integration_order")
    if not isinstance(included, list) or not isinstance(order, list):
        fail("included_works and integration_order must be lists")
    by_id: dict[str, dict] = {}
    for entry in included:
        if not isinstance(entry, dict) or not isinstance(entry.get("work_id"), str):
            fail(f"invalid included WORK entry: {entry!r}")
        wid = entry["work_id"]
        if wid in by_id:
            fail(f"duplicate included WORK: {wid}")
        by_id[wid] = entry
    if set(by_id) != closure_expected:
        fail(
            "included prerequisite closure mismatch: "
            f"missing={sorted(closure_expected-set(by_id))} "
            f"extra={sorted(set(by_id)-closure_expected)}"
        )
    if len(order) != len(set(order)) or set(order) != closure_expected:
        fail("integration_order must contain the prerequisite closure exactly once")

    if closure_expected and (
        registry_doc.get("registry_status") != "ACTIVE"
        or registry_doc.get("authorization_status") != "APPROVED_FOR_CONSTRUCTION"
    ):
        fail(
            "trusted registry must be ACTIVE and APPROVED_FOR_CONSTRUCTION "
            "for dependent WORK execution"
        )

    resolved: dict[str, dict[str, str]] = {}
    matched_registry_entries: list[dict] = []
    for wid, entry in by_id.items():
        commit_value, tree_value = entry.get("commit_sha"), entry.get("tree_sha")
        if not isinstance(commit_value, str) or not isinstance(tree_value, str):
            fail(f"missing commit/tree for included WORK {wid}")
        commit_sha = git(repo, "rev-parse", f"{commit_value}^{{commit}}")
        tree_sha = git(repo, "rev-parse", f"{tree_value}^{{tree}}")
        if git(repo, "rev-parse", f"{commit_sha}^{{tree}}") != tree_sha:
            fail(f"included WORK tree mismatch: {wid}")
        registry_entry = registry_by_id.get(wid)
        if registry_entry is None:
            fail(f"missing trusted registry entry for prerequisite WORK {wid}")
        evidence = require_approved_entry(
            package_root, registry_entry, wid, commit_sha, tree_sha
        )
        resolved[wid] = {
            "work_id": wid,
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
        }
        matched_registry_entries.append(
            {
                "work_id": wid,
                "commit_sha": commit_sha,
                "tree_sha": tree_sha,
                "approver_identity": registry_entry["approver_identity"],
                "approved_at": registry_entry["approved_at"],
                "evidence": evidence,
            }
        )

    history = [
        line
        for line in git(
            repo,
            "rev-list",
            "--first-parent",
            "--reverse",
            f"{base_sha}..{parent_commit_sha}",
        ).splitlines()
        if line
    ]
    expected_history = [resolved[wid]["commit_sha"] for wid in order]
    if history != expected_history:
        fail(
            f"parent first-parent history mismatch: "
            f"actual={history} expected={expected_history}"
        )
    if closure_expected:
        if parent_commit_sha != expected_history[-1]:
            fail("parent commit must be the last prerequisite integration commit")
    elif parent_commit_sha != base_sha:
        fail("a WORK without prerequisites must use the root baseline as parent commit")

    position = {wid: index for index, wid in enumerate(order)}
    for wid in order:
        for prerequisite in direct_prerequisites(scope, wid, None):
            if prerequisite not in position or position[prerequisite] >= position[wid]:
                fail(f"integration_order violates prerequisite edge {prerequisite} -> {wid}")

    result = {
        "work_id": args.work_id,
        "stage": args.stage,
        "root_baseline_sha": base_sha,
        "direct_prerequisites": sorted(direct_expected),
        "prerequisite_closure": sorted(closure_expected),
        "integration_order": order,
        "included_works": [resolved[wid] for wid in order],
        "approved_commit_registry_path": "05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json",
        "approved_commit_registry_sha256": registry_sha,
        "matched_registry_entries": sorted(
            matched_registry_entries, key=lambda value: value["work_id"]
        ),
        "parent_commit_sha": parent_commit_sha,
        "parent_tree_sha": parent_tree_sha,
        "work_commit_sha": work_commit_sha,
        "work_tree_sha": work_tree_sha,
        "provenance_status": "PASS",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"PARENT_PROVENANCE_PASS {args.work_id} parent={parent_commit_sha} "
        f"direct={len(direct_expected)} closure={len(closure_expected)} "
        f"registry={registry_sha}"
    )


if __name__ == "__main__":
    try:
        main()
    except (ProvenanceError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"PARENT_PROVENANCE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2)
