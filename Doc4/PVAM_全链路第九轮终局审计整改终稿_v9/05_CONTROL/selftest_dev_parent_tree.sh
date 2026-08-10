#!/usr/bin/env bash
set -euo pipefail
C=$(cd "$(dirname "$0")" && pwd)
source "$C/ensure_temp_root.sh"
PACKAGE_ROOT=$(cd "$C/.." && pwd)
pvam_prepare_tmpdir "$(dirname "$PACKAGE_ROOT")/.pvam_tmp"
TMP=$(mktemp -d "$TMPDIR/pvam-dev-parent.XXXXXX")
trap 'rm -rf "$TMP" >/dev/null 2>&1 || true' EXIT

R="$TMP/repo"
mkdir -p "$R/User"
git -C "$R" init -q
git -C "$R" config user.email qa@example.invalid
git -C "$R" config user.name QA
printf 'def value():\n    return 1\n' > "$R/User/GlobalRecalculationService.py"
git -C "$R" add .
git -C "$R" commit -qm base
BASE=$(git -C "$R" rev-parse HEAD)
mkdir -p "$R/Common"
printf 'def units():\n    return 2\n' > "$R/Common/PvAmount.py"
git -C "$R" add .
git -C "$R" commit -qm work01
W1=$(git -C "$R" rev-parse HEAD)
T1=$(git -C "$R" rev-parse "$W1^{tree}")
printf 'def value():\n    return 2\n' > "$R/User/GlobalRecalculationService.py"
git -C "$R" add .
git -C "$R" commit -qm work02
W2=$(git -C "$R" rev-parse HEAD)

cat > "$TMP/scope.json" <<'JSON_SCOPE'
{"schema_version":3,"works":{"WORK-PVAM-01":{"exact":["Common/PvAmount.py"],"prefixes":[],"prerequisites":[]},"WORK-PVAM-02":{"exact":["User/GlobalRecalculationService.py"],"prefixes":[],"prerequisites":["WORK-PVAM-01"]}}}
JSON_SCOPE

PKG="$TMP/pkg"
mkdir -p "$PKG/05_CONTROL" "$PKG/evidence/WORK-PVAM-01/approved"
cp "$C/validate_parent_provenance.py" "$C/validate_work_patch.sh" "$C/validate_work_dev.sh" "$C/validate_patch_scope.py" "$PKG/05_CONTROL/"
printf 'synthetic work01 patch\n' > "$PKG/evidence/WORK-PVAM-01/approved/work.patch"
printf '{"scope_check":"PASS"}\n' > "$PKG/evidence/WORK-PVAM-01/approved/scope_result.json"
printf '{"provenance_status":"PASS"}\n' > "$PKG/evidence/WORK-PVAM-01/approved/parent_provenance.json"
printf '{"work_id":"WORK-PVAM-01","approval":"APPROVED","approver":"QA Synthetic Approver"}\n' > "$PKG/evidence/WORK-PVAM-01/approved/approval_record.json"
ph(){ sha256sum "$1" | awk '{print $1}'; }
PATCHH=$(ph "$PKG/evidence/WORK-PVAM-01/approved/work.patch")
SCOPEH=$(ph "$PKG/evidence/WORK-PVAM-01/approved/scope_result.json")
PROVH=$(ph "$PKG/evidence/WORK-PVAM-01/approved/parent_provenance.json")
APPROVALH=$(ph "$PKG/evidence/WORK-PVAM-01/approved/approval_record.json")
cat > "$PKG/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json" <<JSON_REGISTRY
{"schema_version":2,"registry_id":"WORK-APPROVED-COMMIT-REGISTRY-PVAM-v2","baseline_commit":"$BASE","registry_status":"ACTIVE","authorization_status":"APPROVED_FOR_CONSTRUCTION","canonical_path":"05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json","entries":[{"work_id":"WORK-PVAM-01","approval_status":"APPROVED","commit_sha":"$W1","tree_sha":"$T1","patch_path":"evidence/WORK-PVAM-01/approved/work.patch","patch_sha256":"$PATCHH","scope_result_path":"evidence/WORK-PVAM-01/approved/scope_result.json","scope_result_sha256":"$SCOPEH","parent_provenance_path":"evidence/WORK-PVAM-01/approved/parent_provenance.json","parent_provenance_sha256":"$PROVH","approval_record_path":"evidence/WORK-PVAM-01/approved/approval_record.json","approval_record_sha256":"$APPROVALH","approver_identity":"QA Synthetic Approver","approver_role":"test-fixture","approved_at":"2026-08-06T00:00:00Z"}]}
JSON_REGISTRY
REGSHA=$(ph "$PKG/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json")
cat > "$PKG/DOCUMENT_MANIFEST.json" <<JSON_DOCUMENT
{"approved_commit_registry":{"path":"05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json","sha256":"$REGSHA","schema_version":2},"approved_commit_registry_sha256":"$REGSHA"}
JSON_DOCUMENT
cat > "$PKG/05_CONTROL/VERSION_REFERENCE_MANIFEST.json" <<JSON_VERSION
{"artifact_hashes":{"approved_commit_registry":{"path":"05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json","sha256":"$REGSHA","schema_version":2}}}
JSON_VERSION
cat > "$TMP/provenance.json" <<JSON_PROVENANCE
{"schema_version":2,"work_id":"WORK-PVAM-02","stage":null,"root_baseline_sha":"$BASE","approved_commit_registry_sha256":"$REGSHA","direct_prerequisites":["WORK-PVAM-01"],"included_works":[{"work_id":"WORK-PVAM-01","commit_sha":"$W1","tree_sha":"$T1"}],"integration_order":["WORK-PVAM-01"],"parent_commit_sha":"$W1","parent_tree_sha":"$T1","work_commit_sha":"$W2"}
JSON_PROVENANCE
cat > "$TMP/test.sh" <<'TEST_SCRIPT_END'
#!/usr/bin/env bash
set -euo pipefail
python - <<'PY_TEST_END'
from User.GlobalRecalculationService import value
from Common.PvAmount import units
assert value() == 2 and units() == 2
PY_TEST_END
printf '<testsuite tests="1" failures="0"/>\n' > "$PVAM_EVIDENCE_DIR/junit.xml"
TEST_SCRIPT_END
chmod +x "$TMP/test.sh"

ARGS=(
  --repo "$R" --base "$BASE" --parent-commit "$W1" --parent-tree "$T1"
  --parent-provenance "$TMP/provenance.json"
  --approved-registry "$PKG/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json"
  --work-commit "$W2" --work-id WORK-PVAM-02 --scope "$TMP/scope.json"
  --test-command-file "$TMP/test.sh"
)
bash "$PKG/05_CONTROL/validate_work_dev.sh" "${ARGS[@]}" --out "$TMP/out"
test -s "$TMP/out/dev_validation.json"
test -s "$TMP/out/junit.xml"

mkdir -p "$TMP/forged"
cp "$PKG/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json" "$TMP/forged/WORK_APPROVED_COMMIT_REGISTRY.json"
if bash "$PKG/05_CONTROL/validate_work_dev.sh" \
  --repo "$R" --base "$BASE" --parent-commit "$W1" --parent-tree "$T1" \
  --parent-provenance "$TMP/provenance.json" \
  --approved-registry "$TMP/forged/WORK_APPROVED_COMMIT_REGISTRY.json" \
  --work-commit "$W2" --work-id WORK-PVAM-02 --scope "$TMP/scope.json" \
  --test-command-file "$TMP/test.sh" --out "$TMP/forged-out" >/dev/null 2>&1; then
  echo 'forged caller registry unexpectedly passed' >&2
  exit 44
fi
echo TRUST_ROOT_NEGATIVE_PASS forged_registry_path

BAD="$TMP/badpkg"
cp -a "$PKG" "$BAD"
rm "$BAD/evidence/WORK-PVAM-01/approved/work.patch"
if bash "$BAD/05_CONTROL/validate_work_dev.sh" \
  --repo "$R" --base "$BASE" --parent-commit "$W1" --parent-tree "$T1" \
  --parent-provenance "$TMP/provenance.json" \
  --approved-registry "$BAD/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json" \
  --work-commit "$W2" --work-id WORK-PVAM-02 --scope "$TMP/scope.json" \
  --test-command-file "$TMP/test.sh" --out "$TMP/missing-out" >/dev/null 2>&1; then
  echo 'missing registry evidence unexpectedly passed' >&2
  exit 45
fi
echo TRUST_ROOT_NEGATIVE_PASS missing_evidence

TAMP="$TMP/tamperpkg"
cp -a "$PKG" "$TAMP"
printf ' ' >> "$TAMP/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json"
if bash "$TAMP/05_CONTROL/validate_work_dev.sh" \
  --repo "$R" --base "$BASE" --parent-commit "$W1" --parent-tree "$T1" \
  --parent-provenance "$TMP/provenance.json" \
  --approved-registry "$TAMP/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json" \
  --work-commit "$W2" --work-id WORK-PVAM-02 --scope "$TMP/scope.json" \
  --test-command-file "$TMP/test.sh" --out "$TMP/tamper-out" >/dev/null 2>&1; then
  echo 'tampered registry unexpectedly passed release trust root' >&2
  exit 46
fi
echo TRUST_ROOT_NEGATIVE_PASS registry_hash_tamper

run_symlink_negative() {
  local pkg=$1
  local label=$2
  if bash "$pkg/05_CONTROL/validate_work_dev.sh" \
    --repo "$R" --base "$BASE" --parent-commit "$W1" --parent-tree "$T1" \
    --parent-provenance "$TMP/provenance.json" \
    --approved-registry "$pkg/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json" \
    --work-commit "$W2" --work-id WORK-PVAM-02 --scope "$TMP/scope.json" \
    --test-command-file "$TMP/test.sh" --out "$TMP/${label}-out" >/dev/null 2>&1; then
    echo "symlink trust-root negative unexpectedly passed: $label" >&2
    exit 48
  fi
  echo "TRUST_ROOT_SYMLINK_NEGATIVE_PASS $label"
}

REG_LINK="$TMP/registry-symlink-pkg"
cp -a "$PKG" "$REG_LINK"
mv "$REG_LINK/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json" \
  "$REG_LINK/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.target.json"
ln -s "WORK_APPROVED_COMMIT_REGISTRY.target.json" \
  "$REG_LINK/05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json"
run_symlink_negative "$REG_LINK" registry_file

for evidence_name in \
  work.patch \
  scope_result.json \
  parent_provenance.json \
  approval_record.json
do
  label=${evidence_name//./_}
  LINK_PKG="$TMP/evidence-symlink-$label"
  cp -a "$PKG" "$LINK_PKG"
  evidence_path="$LINK_PKG/evidence/WORK-PVAM-01/approved/$evidence_name"
  mv "$evidence_path" "$evidence_path.target"
  ln -s "$evidence_name.target" "$evidence_path"
  run_symlink_negative "$LINK_PKG" "evidence_$label"
done

DIR_LINK="$TMP/evidence-directory-symlink-pkg"
cp -a "$PKG" "$DIR_LINK"
mv "$DIR_LINK/evidence/WORK-PVAM-01/approved" \
  "$DIR_LINK/evidence/WORK-PVAM-01/approved.target"
ln -s "approved.target" "$DIR_LINK/evidence/WORK-PVAM-01/approved"
run_symlink_negative "$DIR_LINK" evidence_directory_component

echo DEV_PARENT_TREE_RELEASE_TRUST_ROOT_SELFTEST_PASS
