#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-}"
RUN_ID="${RUN_ID:-}"
WORK_ID="${WORK_ID:-}"
WORK_COMMIT_SHA="${WORK_COMMIT_SHA:-}"
TEST_COMMAND_FILE="${TEST_COMMAND_FILE:-}"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BASE_SHA="${BASE_SHA:-3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2}"
DRY_RUN=0

usage() {
  printf '%s\n' \
    "usage: run_work_dev.sh [--repo PATH] [--run-id ID] [--work-id ID]" \
    "                       [--work-commit SHA] [--test-command-file PATH]" \
    "                       [--evidence-root PATH] [--dry-run]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_ROOT="${2:?}"; shift 2 ;;
    --run-id) RUN_ID="${2:?}"; shift 2 ;;
    --work-id) WORK_ID="${2:?}"; shift 2 ;;
    --work-commit) WORK_COMMIT_SHA="${2:?}"; shift 2 ;;
    --test-command-file) TEST_COMMAND_FILE="${2:?}"; shift 2 ;;
    --evidence-root) EVIDENCE_ROOT="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

: "${REPO_ROOT:?set REPO_ROOT or pass --repo}"
: "${RUN_ID:?set RUN_ID or pass --run-id}"
: "${WORK_ID:?set WORK_ID or pass --work-id}"
: "${WORK_COMMIT_SHA:?set WORK_COMMIT_SHA or pass --work-commit}"
: "${TEST_COMMAND_FILE:?set TEST_COMMAND_FILE or pass --test-command-file}"

if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf 'RUN_ID contains unsafe characters: %s\n' "$RUN_ID" >&2
  exit 2
fi
if [[ ! "$WORK_ID" =~ ^WORK-PVAM-[0-9A-Z-]+$ ]]; then
  printf 'WORK_ID is not controlled: %s\n' "$WORK_ID" >&2
  exit 2
fi

repo_root="$(git -C "$REPO_ROOT" rev-parse --show-toplevel)"
command_file="$(cd "$(dirname "$TEST_COMMAND_FILE")" && pwd)/$(basename "$TEST_COMMAND_FILE")"
if [[ ! -f "$command_file" ]]; then
  printf 'test command file not found: %s\n' "$command_file" >&2
  exit 2
fi

if [[ -z "$EVIDENCE_ROOT" ]]; then
  EVIDENCE_ROOT="$repo_root/evidence/$WORK_ID"
fi
attempt_dir="$EVIDENCE_ROOT/$RUN_ID"

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '{"dry_run":true,"repo":"%s","work_id":"%s","run_id":"%s","command_file":"%s","validation_status":"NOT_RUN"}\n' \
    "$repo_root" "$WORK_ID" "$RUN_ID" "$command_file"
  exit 0
fi

if [[ -e "$attempt_dir" ]]; then
  printf 'immutable attempt already exists: %s\n' "$attempt_dir" >&2
  exit 20
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$script_dir/check_baseline.sh" \
  --repo "$repo_root" \
  --base "$BASE_SHA" \
  --expected-head "$WORK_COMMIT_SHA"

mkdir -p "$attempt_dir"
stdout_file="$attempt_dir/02_stdout.log"
stderr_file="$attempt_dir/03_stderr.log"
exit_file="$attempt_dir/04_exit_code.txt"
manifest_file="$attempt_dir/00_manifest.json"
command_record="$attempt_dir/01_command.txt"

printf 'bash %q\n' "$command_file" >"$command_record"
started_at="$(date --iso-8601=seconds)"
export PVAM_EVIDENCE_DIR="$attempt_dir"

set +e
(
  cd "$repo_root"
  bash "$command_file"
) >"$stdout_file" 2>"$stderr_file"
exit_code=$?
set -e

finished_at="$(date --iso-8601=seconds)"
printf '%s\n' "$exit_code" >"$exit_file"
stdout_sha="$(sha256sum "$stdout_file" | awk '{print $1}')"
stderr_sha="$(sha256sum "$stderr_file" | awk '{print $1}')"
command_sha="$(sha256sum "$command_record" | awk '{print $1}')"
exit_sha="$(sha256sum "$exit_file" | awk '{print $1}')"
head_sha="$(git -C "$repo_root" rev-parse HEAD)"
tree_sha="$(git -C "$repo_root" rev-parse 'HEAD^{tree}')"

if [[ "$exit_code" -eq 0 ]]; then
  execution_status="EXIT_0"
  validation_status="BLOCKED"
  reason="command exited 0; controlled reviewer/gate has not signed a PASS conclusion"
else
  execution_status="EXIT_NONZERO"
  validation_status="FAIL"
  reason="command exited nonzero; inspect captured stdout/stderr"
fi

"$PYTHON_BIN" -c '
import json, sys
(
 manifest_path, work_id, attempt_id, status, reason, exit_code,
 started_at, finished_at, head_sha, tree_sha, command_file,
 execution_status, stdout_sha, stderr_sha, command_sha, exit_sha
) = sys.argv[1:]
data = {
 "schema_version": "1.0",
 "work_id": work_id,
 "attempt_id": attempt_id,
 "artifact_status": "AVAILABLE",
 "validation_status": status,
 "reason": reason,
 "command": ["bash", command_file],
 "exit_code": int(exit_code),
 "started_at": started_at,
 "finished_at": finished_at,
 "repository": {"commit": head_sha, "tree": tree_sha, "source_archive_sha256": None},
 "environment": {"kind": "DEV", "external_services": "NOT_RUN"},
 "execution_status": execution_status,
 "evidence_links": ["01_command.txt", "02_stdout.log", "03_stderr.log", "04_exit_code.txt"],
 "sha256": {
   "01_command.txt": command_sha,
   "02_stdout.log": stdout_sha,
   "03_stderr.log": stderr_sha,
   "04_exit_code.txt": exit_sha,
 },
}
with open(manifest_path, "x", encoding="utf-8") as stream:
 json.dump(data, stream, indent=2)
 stream.write("\n")
' "$manifest_file" "$WORK_ID" "$RUN_ID" "$validation_status" "$reason" \
  "$exit_code" "$started_at" "$finished_at" "$head_sha" "$tree_sha" \
  "$command_file" "$execution_status" "$stdout_sha" "$stderr_sha" \
  "$command_sha" "$exit_sha"

printf '{"attempt":"%s","execution_status":"%s","validation_status":"%s","exit_code":%s}\n' \
  "$attempt_dir" "$execution_status" "$validation_status" "$exit_code"
exit "$exit_code"
