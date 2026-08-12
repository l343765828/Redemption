#!/usr/bin/env python3
"""Validate WORK-PVAM-08 evidence contracts without external packages.

The validator deliberately separates an execution exit code from a reviewed
validation conclusion.  In particular, it never turns an exit code of zero
into PASS by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


VALIDATION_STATUSES = {
    "NOT_RUN",
    "PASS",
    "FAIL",
    "PENDING_TEST_ENV",
    "BLOCKED",
}
ARTIFACT_STATUSES = {"PENDING", "AVAILABLE", "SUPERSEDED"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_SECRET_KEYS = {
    "password",
    "passwd",
    "secret",
    "access_token",
    "private_key",
    "mysql_cnf_content",
}


class EvidenceValidationError(ValueError):
    """Raised when an evidence manifest violates the controlled contract."""


def _parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceValidationError(f"{field} must be a non-empty ISO timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EvidenceValidationError(f"{field} is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise EvidenceValidationError(f"{field} must include a timezone offset")
    return parsed


def _walk_keys(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key).lower()
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


class EvidenceValidator:
    """Validate a single evidence manifest and its referenced files."""

    def __init__(self, schema_path: Optional[Path] = None) -> None:
        self.schema_path = schema_path

    def validate(
        self,
        manifest: Mapping[str, Any],
        *,
        manifest_dir: Optional[Path] = None,
    ) -> None:
        if not isinstance(manifest, Mapping):
            raise EvidenceValidationError("manifest must be a JSON object")

        status = manifest.get("validation_status")
        if status not in VALIDATION_STATUSES:
            raise EvidenceValidationError(
                "validation_status must be one of "
                + ", ".join(sorted(VALIDATION_STATUSES))
            )

        reason = manifest.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise EvidenceValidationError("reason is required and cannot be blank")

        command = manifest.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part for part in command
        ):
            raise EvidenceValidationError("command must be a non-empty string array")

        exit_code = manifest.get("exit_code")
        if isinstance(exit_code, bool) or not (
            exit_code is None or isinstance(exit_code, int)
        ):
            raise EvidenceValidationError("exit_code must be an integer or null")

        artifact_status = manifest.get("artifact_status")
        if artifact_status is not None and artifact_status not in ARTIFACT_STATUSES:
            raise EvidenceValidationError(
                "artifact_status must be one of "
                + ", ".join(sorted(ARTIFACT_STATUSES))
            )
        attempt_id = manifest.get("attempt_id")
        if attempt_id is not None:
            if not isinstance(attempt_id, str) or not attempt_id:
                raise EvidenceValidationError("attempt_id must be a non-empty string")
            if artifact_status is None:
                raise EvidenceValidationError("an attempt requires artifact_status")
            repository = manifest.get("repository")
            if not isinstance(repository, Mapping):
                raise EvidenceValidationError("an attempt requires repository metadata")
            commit = repository.get("commit")
            if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise EvidenceValidationError("repository.commit must be a full Git SHA")
            environment = manifest.get("environment")
            if not isinstance(environment, Mapping) or not environment:
                raise EvidenceValidationError("an attempt requires environment metadata")
            started = _parse_timestamp(manifest.get("started_at"), "started_at")
            finished = _parse_timestamp(manifest.get("finished_at"), "finished_at")
            if finished < started:
                raise EvidenceValidationError("finished_at cannot precede started_at")
            links = manifest.get("evidence_links")
            if not isinstance(links, list) or not links:
                raise EvidenceValidationError("an attempt requires evidence_links")

        forbidden = FORBIDDEN_SECRET_KEYS.intersection(_walk_keys(manifest))
        if forbidden:
            raise EvidenceValidationError(
                "manifest contains forbidden secret-bearing keys: "
                + ", ".join(sorted(forbidden))
            )

        if status == "PASS":
            if exit_code != 0:
                raise EvidenceValidationError("PASS requires exit_code 0")
            if artifact_status != "AVAILABLE":
                raise EvidenceValidationError("PASS requires artifact_status AVAILABLE")
            started = _parse_timestamp(manifest.get("started_at"), "started_at")
            finished = _parse_timestamp(manifest.get("finished_at"), "finished_at")
            if finished < started:
                raise EvidenceValidationError("finished_at cannot precede started_at")
            links = manifest.get("evidence_links")
            if not isinstance(links, list) or not links:
                raise EvidenceValidationError("PASS requires at least one evidence link")

        hashes = manifest.get("sha256", {})
        if hashes is not None and not isinstance(hashes, Mapping):
            raise EvidenceValidationError("sha256 must be an object")
        if isinstance(hashes, Mapping):
            for rel_path, expected in hashes.items():
                if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
                    raise EvidenceValidationError(
                        f"sha256[{rel_path!r}] must be a lowercase SHA-256"
                    )
                if manifest_dir is None:
                    continue
                target = (manifest_dir / str(rel_path)).resolve()
                root = manifest_dir.resolve()
                if root != target and root not in target.parents:
                    raise EvidenceValidationError(
                        f"sha256 path escapes attempt directory: {rel_path!r}"
                    )
                if not target.is_file():
                    raise EvidenceValidationError(
                        f"sha256 target is missing: {rel_path!r}"
                    )
                actual = hashlib.sha256(target.read_bytes()).hexdigest()
                if actual != expected:
                    raise EvidenceValidationError(
                        f"sha256 mismatch for {rel_path!r}: {actual} != {expected}"
                    )
        if attempt_id is not None and manifest_dir is not None:
            links = manifest.get("evidence_links", [])
            hash_keys = set(hashes) if isinstance(hashes, Mapping) else set()
            for rel_path in links:
                if not isinstance(rel_path, str) or not rel_path:
                    raise EvidenceValidationError("evidence link must be a non-empty string")
                if rel_path not in hash_keys:
                    raise EvidenceValidationError(
                        f"evidence link has no SHA-256 entry: {rel_path!r}"
                    )


def validate_schema_contract(schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        raise EvidenceValidationError("schema properties object is missing")
    validation_enum = properties.get("validation_status", {}).get("enum")
    if set(validation_enum or []) != VALIDATION_STATUSES:
        raise EvidenceValidationError("schema validation_status enum is incomplete")
    artifact_enum = properties.get("artifact_status", {}).get("enum")
    if set(artifact_enum or []) != ARTIFACT_STATUSES:
        raise EvidenceValidationError("schema artifact_status enum is incomplete")
    required = set(schema.get("required", []))
    if not {"validation_status", "reason", "command", "exit_code"}.issubset(required):
        raise EvidenceValidationError("schema is missing mandatory evidence fields")


def validate_pack(root: Path, validator: EvidenceValidator) -> int:
    if not root.is_dir():
        raise EvidenceValidationError(f"evidence root does not exist: {root}")

    manifests = []
    seen_attempt_ids = set()
    for path in sorted(root.rglob("*.json")):
        if path.name == "manifest.schema.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EvidenceValidationError(f"invalid JSON {path}: {exc}") from exc
        if not isinstance(data, Mapping) or "validation_status" not in data:
            continue
        if "command" not in data:
            continue
        validator.validate(data, manifest_dir=path.parent)
        attempt_id = data.get("attempt_id")
        if attempt_id:
            if attempt_id in seen_attempt_ids:
                raise EvidenceValidationError(
                    f"duplicate immutable attempt_id: {attempt_id!r}"
                )
            seen_attempt_ids.add(attempt_id)
        manifests.append(path)

    if not manifests:
        raise EvidenceValidationError("no evidence attempt manifests were found")
    return len(manifests)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("evidence/manifest.schema.json"),
        help="evidence JSON schema",
    )
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--root", type=Path, help="evidence attempt root")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    validate_schema_contract(args.schema)
    if args.schema_only:
        print(json.dumps({"schema": str(args.schema), "status": "VALID"}))
        return 0
    if args.root is None:
        raise SystemExit("--root is required unless --schema-only is used")
    count = validate_pack(args.root, EvidenceValidator(args.schema))
    print(json.dumps({"root": str(args.root), "validated_manifests": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
