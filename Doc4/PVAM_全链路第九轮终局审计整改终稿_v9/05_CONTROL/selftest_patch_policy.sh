#!/usr/bin/env bash
set -euo pipefail
C=$(cd "$(dirname "$0")" && pwd)
source "$C/ensure_temp_root.sh"
PACKAGE_ROOT=$(cd "$C/.." && pwd)
pvam_prepare_tmpdir "$(dirname "$PACKAGE_ROOT")/.pvam_tmp"
TMP=$(mktemp -d "$TMPDIR/pvam-patch-selftest.XXXXXX")
trap 'rm -rf "$TMP" >/dev/null 2>&1 || true' EXIT

R="$TMP/repo"
mkdir -p "$R/MessageConsumer"
git -C "$R" init -q
git -C "$R" config user.email qa@example.invalid
git -C "$R" config user.name QA
printf 'def f():\n    return 1\n' > "$R/MessageConsumer/RecalcStreamConsumer.py"
git -C "$R" add .
git -C "$R" commit -qm base
BASE=$(git -C "$R" rev-parse HEAD)
BASE_TREE=$(git -C "$R" rev-parse "$BASE^{tree}")
printf 'def f():\n    return 2\n' > "$R/MessageConsumer/RecalcStreamConsumer.py"
git -C "$R" add .
git -C "$R" commit -qm work07a
WORK=$(git -C "$R" rev-parse HEAD)
cat > "$TMP/scope.json" <<'JSON_SCOPE'
{"schema_version":3,"works":{"WORK-PVAM-07A":{"exact":["MessageConsumer/RecalcStreamConsumer.py"],"prefixes":[],"prerequisites":[]}}}
JSON_SCOPE

PKG="$TMP/pkg"
mkdir -p "$PKG/05_CONTROL"
cp "$C/validate_parent_provenance.py" "$C/validate_work_patch.sh" "$C/validate_patch_scope.py" "$PKG/05_CONTROL/"
cat > "$PKG/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json" <<JSON_REGISTRY
{"schema_version":2,"registry_id":"WORK-APPROVED-COMMIT-REGISTRY-PVAM-v2","baseline_commit":"$BASE","registry_status":"PENDING_ORGANIZATIONAL_APPROVAL","authorization_status":"PENDING_ORGANIZATIONAL_APPROVAL","canonical_path":"05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json","entries":[]}
JSON_REGISTRY
REGSHA=$(sha256sum "$PKG/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json" | awk '{print $1}')
cat > "$PKG/DOCUMENT_MANIFEST.json" <<JSON_DOCUMENT
{"approved_commit_registry":{"path":"05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json","sha256":"$REGSHA","schema_version":2},"approved_commit_registry_sha256":"$REGSHA"}
JSON_DOCUMENT
cat > "$PKG/05_CONTROL/VERSION_REFERENCE_MANIFEST.json" <<JSON_VERSION
{"artifact_hashes":{"approved_commit_registry":{"path":"05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json","sha256":"$REGSHA","schema_version":2}}}
JSON_VERSION
cat > "$TMP/provenance.json" <<JSON_PROVENANCE
{"schema_version":2,"work_id":"WORK-PVAM-07A","stage":null,"root_baseline_sha":"$BASE","approved_commit_registry_sha256":"$REGSHA","direct_prerequisites":[],"included_works":[],"integration_order":[],"parent_commit_sha":"$BASE","parent_tree_sha":"$BASE_TREE","work_commit_sha":"$WORK"}
JSON_PROVENANCE

bash "$PKG/05_CONTROL/validate_work_patch.sh" \
  --repo "$R" --base "$BASE" --parent-commit "$BASE" --parent-tree "$BASE_TREE" \
  --parent-provenance "$TMP/provenance.json" \
  --approved-registry "$PKG/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json" \
  --work-commit "$WORK" --work-id WORK-PVAM-07A --scope "$TMP/scope.json" \
  --out "$TMP/out"
test -s "$TMP/out/WORK-PVAM-07A.patch"

git -C "$R" checkout -q "$BASE"
git -C "$R" mv MessageConsumer/RecalcStreamConsumer.py outside.py
git -C "$R" commit -qm bad-rename
BAD=$(git -C "$R" rev-parse HEAD)
python - "$TMP/provenance.json" "$BAD" <<'PY_EDIT_END'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
data["work_commit_sha"] = sys.argv[2]
json.dump(data, open(path, "w", encoding="utf-8"), indent=2)
PY_EDIT_END
if bash "$PKG/05_CONTROL/validate_work_patch.sh" \
  --repo "$R" --base "$BASE" --parent-commit "$BASE" --parent-tree "$BASE_TREE" \
  --parent-provenance "$TMP/provenance.json" \
  --approved-registry "$PKG/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json" \
  --work-commit "$BAD" --work-id WORK-PVAM-07A --scope "$TMP/scope.json" \
  --out "$TMP/bad" >/dev/null 2>&1; then
  echo 'out-of-scope rename unexpectedly passed' >&2
  exit 43
fi

echo PATCH_POLICY_SELFTEST_PASS
