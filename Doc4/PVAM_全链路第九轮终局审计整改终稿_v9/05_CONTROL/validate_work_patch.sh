#!/usr/bin/env bash
set -euo pipefail
usage(){ cat >&2 <<'EOF'
usage: validate_work_patch.sh --repo REPO --base SHA --parent-commit SHA --parent-tree TREEISH \
  --parent-provenance FILE --approved-registry FILE --work-commit SHA --work-id ID \
  --scope JSON --out DIR [--stage A|B]
EOF
exit 64; }
REPO_ARG= BASE_ARG= PARENT_COMMIT_ARG= PARENT_TREE_ARG= PARENT_PROVENANCE_ARG= APPROVED_REGISTRY_ARG=
WORK_ARG= WORK_ID= SCOPE_ARG= OUT_ARG= STAGE=
while (($#)); do case "$1" in
  --repo) REPO_ARG=$2; shift 2;; --base) BASE_ARG=$2; shift 2;;
  --parent-commit) PARENT_COMMIT_ARG=$2; shift 2;; --parent-tree) PARENT_TREE_ARG=$2; shift 2;;
  --parent-provenance) PARENT_PROVENANCE_ARG=$2; shift 2;; --approved-registry) APPROVED_REGISTRY_ARG=$2; shift 2;;
  --work-commit) WORK_ARG=$2; shift 2;; --work-id) WORK_ID=$2; shift 2;; --scope) SCOPE_ARG=$2; shift 2;;
  --out) OUT_ARG=$2; shift 2;; --stage) STAGE=$2; shift 2;; *) usage;; esac; done
[[ -n "$REPO_ARG" && -n "$BASE_ARG" && -n "$PARENT_COMMIT_ARG" && -n "$PARENT_TREE_ARG" && \
   -n "$PARENT_PROVENANCE_ARG" && -n "$APPROVED_REGISTRY_ARG" && -n "$WORK_ARG" && -n "$WORK_ID" && \
   -n "$SCOPE_ARG" && -n "$OUT_ARG" ]] || usage
REPO_ROOT=$(git -C "$REPO_ARG" rev-parse --show-toplevel)
CONTROL_DIR=$(cd "$(dirname "$0")" && pwd)
SCOPE_FILE=$(cd "$(dirname "$SCOPE_ARG")" && pwd)/$(basename "$SCOPE_ARG")
PROVENANCE_FILE=$(cd "$(dirname "$PARENT_PROVENANCE_ARG")" && pwd)/$(basename "$PARENT_PROVENANCE_ARG")
REGISTRY_FILE=$(cd "$(dirname "$APPROVED_REGISTRY_ARG")" && pwd)/$(basename "$APPROVED_REGISTRY_ARG")
OUT_DIR=$(mkdir -p "$OUT_ARG" && cd "$OUT_ARG" && pwd)
BASE_SHA=$(git -C "$REPO_ROOT" rev-parse "$BASE_ARG^{commit}")
PARENT_COMMIT_SHA=$(git -C "$REPO_ROOT" rev-parse "$PARENT_COMMIT_ARG^{commit}")
PARENT_TREE_SHA=$(git -C "$REPO_ROOT" rev-parse "$PARENT_TREE_ARG^{tree}")
WORK_SHA=$(git -C "$REPO_ROOT" rev-parse "$WORK_ARG^{commit}")
WORK_TREE_SHA=$(git -C "$REPO_ROOT" rev-parse "$WORK_SHA^{tree}")
PROVENANCE_OUT="$OUT_DIR/parent_provenance_validation.json"
ARGS=(--repo "$REPO_ROOT" --base "$BASE_SHA" --parent-commit "$PARENT_COMMIT_SHA" --parent-tree "$PARENT_TREE_SHA" \
  --work-commit "$WORK_SHA" --work-id "$WORK_ID" --scope "$SCOPE_FILE" --provenance "$PROVENANCE_FILE" \
  --approved-registry "$REGISTRY_FILE" --out "$PROVENANCE_OUT")
[[ -z "$STAGE" ]] || ARGS+=(--stage "$STAGE")
python "$CONTROL_DIR/validate_parent_provenance.py" "${ARGS[@]}"
PATCH="$OUT_DIR/${WORK_ID}.patch"; STATUS_FILE="$OUT_DIR/changed_status.tsv"; FILES_FILE="$OUT_DIR/changed_files.txt"
mkdir -p "$OUT_DIR/tmp"
TMP_ROOT=$(mktemp -d "$OUT_DIR/tmp/pvam-patch.XXXXXX"); CHECK_TREE="$TMP_ROOT/tree"
cleanup(){ if git -C "$REPO_ROOT" worktree list --porcelain | grep -Fqx "worktree $CHECK_TREE"; then git -C "$REPO_ROOT" worktree remove --force "$CHECK_TREE" >/dev/null 2>&1 || true; fi; rm -rf "$TMP_ROOT"; }
trap cleanup EXIT INT TERM
git -C "$REPO_ROOT" diff --name-status --find-renames "$PARENT_COMMIT_SHA" "$WORK_SHA" > "$STATUS_FILE"
git -C "$REPO_ROOT" diff --name-only --find-renames "$PARENT_COMMIT_SHA" "$WORK_SHA" > "$FILES_FILE"
python "$CONTROL_DIR/validate_patch_scope.py" --scope "$SCOPE_FILE" --work-id "$WORK_ID" --changed-status "$STATUS_FILE" > "$OUT_DIR/scope_result.json"
git -C "$REPO_ROOT" diff --full-index --binary "$PARENT_COMMIT_SHA" "$WORK_SHA" -- > "$PATCH"
test -s "$PATCH" || { echo 'empty direct WORK patch' >&2; exit 11; }
git -C "$REPO_ROOT" worktree add --detach "$CHECK_TREE" "$PARENT_COMMIT_SHA" >/dev/null
git -C "$CHECK_TREE" apply --check --index "$PATCH"; git -C "$CHECK_TREE" apply --index "$PATCH"
APPLIED_TREE=$(git -C "$CHECK_TREE" write-tree); [[ "$APPLIED_TREE" == "$WORK_TREE_SHA" ]] || { echo "tree mismatch: $APPLIED_TREE != $WORK_TREE_SHA" >&2; exit 12; }
PATCH_SHA=$(sha256sum "$PATCH"|awk '{print $1}'); PROVENANCE_SHA=$(sha256sum "$PROVENANCE_FILE"|awk '{print $1}'); REGISTRY_SHA=$(sha256sum "$REGISTRY_FILE"|awk '{print $1}')
[[ -n "$STAGE" ]] && STAGE_JSON="\"$STAGE\"" || STAGE_JSON=null
cat > "$OUT_DIR/patch_validation.json" <<JSON
{"work_id":"$WORK_ID","stage":$STAGE_JSON,"root_baseline_sha":"$BASE_SHA","parent_commit_sha":"$PARENT_COMMIT_SHA","parent_tree_sha":"$PARENT_TREE_SHA","parent_provenance_sha256":"$PROVENANCE_SHA","approved_commit_registry_sha256":"$REGISTRY_SHA","work_commit_sha":"$WORK_SHA","work_tree_sha":"$WORK_TREE_SHA","patch_sha256":"$PATCH_SHA","applied_tree_hash":"$APPLIED_TREE","git_apply_check_exit":0,"scope_check":"PASS"}
JSON
printf '%s  %s\n' "$PATCH_SHA" "$(basename "$PATCH")" > "$PATCH.sha256"
echo "PATCH_VALIDATION_PASS $WORK_ID $PATCH_SHA parent=$PARENT_COMMIT_SHA registry=$REGISTRY_SHA"
