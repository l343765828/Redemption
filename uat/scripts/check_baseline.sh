#!/usr/bin/env bash
set -euo pipefail

BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
EXPECTED_HEAD=""
REPO_ROOT="${REPO_ROOT:-}"

usage() {
  printf '%s\n' \
    "usage: check_baseline.sh [--repo PATH] [--base SHA] [--expected-head SHA]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_ROOT="${2:?--repo requires a path}"
      shift 2
      ;;
    --base)
      BASE_SHA="${2:?--base requires a SHA}"
      shift 2
      ;;
    --expected-head)
      EXPECTED_HEAD="${2:?--expected-head requires a SHA}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$EXPECTED_HEAD" ]]; then
  EXPECTED_HEAD="$BASE_SHA"
fi

: "${REPO_ROOT:?set REPO_ROOT or pass --repo}"

repo_root="$(git -C "$REPO_ROOT" rev-parse --show-toplevel)"
head_sha="$(git -C "$repo_root" rev-parse HEAD)"
base_sha="$(git -C "$repo_root" rev-parse "$BASE_SHA^{commit}")"
expected_head_sha="$(git -C "$repo_root" rev-parse "$EXPECTED_HEAD^{commit}")"

if [[ "$head_sha" != "$expected_head_sha" ]]; then
  printf 'BLOCK-PVAM-08-BASELINE: HEAD %s != expected %s\n' \
    "$head_sha" "$expected_head_sha" >&2
  exit 10
fi

if ! git -C "$repo_root" merge-base --is-ancestor "$base_sha" "$head_sha"; then
  printf 'BLOCK-PVAM-08-BASELINE: base %s is not an ancestor of HEAD %s\n' \
    "$base_sha" "$head_sha" >&2
  exit 11
fi

status_file="$(mktemp)"
valid_sql_file="$(mktemp)"
trap 'rm -f "$status_file" "$valid_sql_file"' EXIT

git -C "$repo_root" status --porcelain=v1 --untracked-files=all >"$status_file"
if [[ -s "$status_file" ]]; then
  printf '%s\n' 'BLOCK-PVAM-08-WORKTREE: index/worktree/untracked/rename state is not clean' >&2
  cat "$status_file" >&2
  exit 12
fi

base_sql_tree="$(git -C "$repo_root" rev-parse "$base_sha:sql_uat")"
head_sql_tree="$(git -C "$repo_root" rev-parse "$head_sha:sql_uat")"
if [[ "$base_sql_tree" != "$head_sql_tree" ]]; then
  printf 'BLOCK-PVAM-08-SQL-BLOB: %s != %s\n' \
    "$head_sql_tree" "$base_sql_tree" >&2
  exit 13
fi

while IFS= read -r sql_path; do
  sql_name="${sql_path##*/}"
  sql_name_lower="$(printf '%s' "$sql_name" | tr '[:upper:]' '[:lower:]')"
  case "$sql_name_lower" in
    *_bak*|*_final*)
      continue
      ;;
  esac
  case "$sql_path" in
    sql_uat/CALC_BE_1.sql|\
    sql_uat/CALC_BE_EAB_copy1.sql|\
    sql_uat/CALC_BE_LB.sql|\
    sql_uat/CALC_BE_REM_DATA_copy.sql|\
    sql_uat/CALC_BE_SE.sql|\
    sql_uat/CALC_BE_SFB_1.sql|\
    sql_uat/CALC_BONUS_copy.sql|\
    sql_uat/CALC_LV_HONOR_HIGH_copy.sql|\
    sql_uat/CALC_LV_HONOR_HIGH_V1.sql)
      continue
      ;;
  esac
  blob_sha="$(git -C "$repo_root" rev-parse "$head_sha:$sql_path")"
  printf '%s  %s\n' "$blob_sha" "$sql_path" >>"$valid_sql_file"
done < <(git -C "$repo_root" ls-tree -r --name-only "$head_sha" -- sql_uat)

valid_sql_sha256="$(sha256sum "$valid_sql_file" | awk '{print $1}')"
valid_sql_count="$(wc -l <"$valid_sql_file" | tr -d ' ')"

printf '{"validation_status":"NOT_RUN","reason":"baseline facts recorded; no test conclusion asserted","head":"%s","base":"%s","sql_tree":"%s","valid_sql_file_count":%s,"valid_sql_index_sha256":"%s","worktree_clean":true}\n' \
  "$head_sha" "$base_sha" "$head_sql_tree" "$valid_sql_count" "$valid_sql_sha256"
