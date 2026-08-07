#!/usr/bin/env bash
set -euo pipefail
usage(){ cat >&2 <<'EOF'
usage: validate_work_dev.sh --repo REPO --base SHA --parent-commit SHA --parent-tree TREEISH \
  --parent-provenance FILE --approved-registry FILE --work-commit SHA --work-id ID \
  --scope JSON --test-command-file FILE --out DIR [--stage A|B]
EOF
exit 64; }
REPO= BASE= PARENT_COMMIT= PARENT_TREE= PARENT_PROVENANCE= APPROVED_REGISTRY=
WORK_COMMIT= WORK_ID= SCOPE= TEST_FILE= OUT= STAGE=
while (($#)); do case "$1" in
  --repo) REPO=$2; shift 2;; --base) BASE=$2; shift 2;; --parent-commit) PARENT_COMMIT=$2; shift 2;;
  --parent-tree) PARENT_TREE=$2; shift 2;; --parent-provenance) PARENT_PROVENANCE=$2; shift 2;;
  --approved-registry) APPROVED_REGISTRY=$2; shift 2;; --work-commit) WORK_COMMIT=$2; shift 2;;
  --work-id) WORK_ID=$2; shift 2;; --scope) SCOPE=$2; shift 2;; --test-command-file) TEST_FILE=$2; shift 2;;
  --out) OUT=$2; shift 2;; --stage) STAGE=$2; shift 2;; *) usage;; esac; done
[[ -n "$REPO" && -n "$BASE" && -n "$PARENT_COMMIT" && -n "$PARENT_TREE" && -n "$PARENT_PROVENANCE" && \
   -n "$APPROVED_REGISTRY" && -n "$WORK_COMMIT" && -n "$WORK_ID" && -n "$SCOPE" && -n "$TEST_FILE" && -n "$OUT" ]] || usage
ROOT=$(git -C "$REPO" rev-parse --show-toplevel); CONTROL_DIR=$(cd "$(dirname "$0")" && pwd)
OUT_DIR=$(mkdir -p "$OUT" && cd "$OUT" && pwd); TEST_ABS=$(cd "$(dirname "$TEST_FILE")" && pwd)/$(basename "$TEST_FILE")
[[ -f "$TEST_ABS" ]] || { echo "missing test command file: $TEST_ABS" >&2; exit 20; }
PATCH_OUT="$OUT_DIR/patch_gate"
ARGS=(--repo "$ROOT" --base "$BASE" --parent-commit "$PARENT_COMMIT" --parent-tree "$PARENT_TREE" \
  --parent-provenance "$PARENT_PROVENANCE" --approved-registry "$APPROVED_REGISTRY" --work-commit "$WORK_COMMIT" \
  --work-id "$WORK_ID" --scope "$SCOPE" --out "$PATCH_OUT")
[[ -z "$STAGE" ]] || ARGS+=(--stage "$STAGE")
bash "$CONTROL_DIR/validate_work_patch.sh" "${ARGS[@]}"
PATCH="$PATCH_OUT/${WORK_ID}.patch"; mkdir -p "$OUT_DIR/tmp"; TMP_ROOT=$(mktemp -d "$OUT_DIR/tmp/pvam-dev.XXXXXX"); TREE="$TMP_ROOT/tree"
cleanup(){ if git -C "$ROOT" worktree list --porcelain | grep -Fqx "worktree $TREE"; then git -C "$ROOT" worktree remove --force "$TREE" >/dev/null 2>&1 || true; fi; rm -rf "$TMP_ROOT"; }
trap cleanup EXIT INT TERM
BASE_SHA=$(git -C "$ROOT" rev-parse "$BASE^{commit}"); PARENT_COMMIT_SHA=$(git -C "$ROOT" rev-parse "$PARENT_COMMIT^{commit}"); PARENT_TREE_SHA=$(git -C "$ROOT" rev-parse "$PARENT_TREE^{tree}"); WORK_SHA=$(git -C "$ROOT" rev-parse "$WORK_COMMIT^{commit}"); WORK_TREE_SHA=$(git -C "$ROOT" rev-parse "$WORK_SHA^{tree}")
git -C "$ROOT" worktree add --detach "$TREE" "$PARENT_COMMIT_SHA" >/dev/null; git -C "$TREE" apply --index "$PATCH"
EXPECTED=$(git -C "$TREE" write-tree); [[ "$EXPECTED" == "$WORK_TREE_SHA" ]] || { echo "pre-test tree mismatch" >&2; exit 22; }
PY_LIST="$OUT_DIR/changed_python_files.txt"; awk 'NF && $0 ~ /\.py$/ {print}' "$PATCH_OUT/changed_files.txt" > "$PY_LIST"
while IFS= read -r file; do [[ -z "$file" || ! -f "$TREE/$file" ]] || PYTHONPYCACHEPREFIX="$OUT_DIR/pycache" python -m py_compile "$TREE/$file"; done < "$PY_LIST"
PATCH_SHA=$(sha256sum "$PATCH"|awk '{print $1}'); PROV_SHA=$(sha256sum "$PARENT_PROVENANCE"|awk '{print $1}'); REG_SHA=$(sha256sum "$APPROVED_REGISTRY"|awk '{print $1}')
( cd "$TREE"; export PVAM_BASE_SHA="$BASE_SHA" PVAM_PARENT_COMMIT_SHA="$PARENT_COMMIT_SHA" PVAM_PARENT_TREE_SHA="$PARENT_TREE_SHA" PVAM_PARENT_PROVENANCE_SHA256="$PROV_SHA" PVAM_APPROVED_COMMIT_REGISTRY_SHA256="$REG_SHA" PVAM_WORK_COMMIT_SHA="$WORK_SHA" PVAM_WORK_TREE_SHA="$WORK_TREE_SHA" PVAM_PATCH_SHA256="$PATCH_SHA" PVAM_EVIDENCE_DIR="$OUT_DIR" PYTHONDONTWRITEBYTECODE=1; mkdir -p "$OUT_DIR/test_tmp"; export TMPDIR="$OUT_DIR/test_tmp"; bash "$TEST_ABS" ) > "$OUT_DIR/test.stdout" 2> "$OUT_DIR/test.stderr"
git -C "$TREE" diff --exit-code -- . > "$OUT_DIR/post_test_unstaged_diff.txt"; git -C "$TREE" ls-files --others --exclude-standard > "$OUT_DIR/post_test_untracked.txt"; [[ ! -s "$OUT_DIR/post_test_untracked.txt" ]] || { echo 'tests created untracked files' >&2; exit 21; }
APPLIED=$(git -C "$TREE" write-tree); [[ "$APPLIED" == "$WORK_TREE_SHA" ]] || { echo 'tests changed applied tree' >&2; exit 22; }
PROVENANCE_FIELDS=$(python - "$PATCH_OUT/parent_provenance_validation.json" <<'PYJSON'
import json,sys
x=json.load(open(sys.argv[1])); print(json.dumps({k:x.get(k) for k in ('direct_prerequisites','prerequisite_closure','integration_order','included_works','approved_commit_registry_sha256','matched_registry_entries')},ensure_ascii=False,separators=(',',':')))
PYJSON
)
PYFILES=$(python - "$PY_LIST" <<'PYJSON'
import json,sys
print(json.dumps([x.strip() for x in open(sys.argv[1]) if x.strip()],ensure_ascii=False,separators=(',',':')))
PYJSON
)
[[ -n "$STAGE" ]] && STAGE_JSON="\"$STAGE\"" || STAGE_JSON=null
cat > "$OUT_DIR/dev_validation.json" <<JSON
{"work_id":"$WORK_ID","stage":$STAGE_JSON,"root_baseline_sha":"$BASE_SHA","parent_commit_sha":"$PARENT_COMMIT_SHA","parent_tree_sha":"$PARENT_TREE_SHA","parent_provenance_sha256":"$PROV_SHA","approved_commit_registry_sha256":"$REG_SHA","parent_provenance":$PROVENANCE_FIELDS,"work_commit_sha":"$WORK_SHA","work_tree_sha":"$WORK_TREE_SHA","patch_sha256":"$PATCH_SHA","applied_tree_hash":"$APPLIED","changed_python_files":$PYFILES,"test_exit":0,"validation_status":"PASS"}
JSON
echo "DEV_VALIDATION_PASS $WORK_ID $WORK_SHA parent=$PARENT_COMMIT_SHA registry=$REG_SHA"
