#!/usr/bin/env bash
set -euo pipefail
usage() { echo "usage: $0 --repo REPO --base SHA --work-id ID" >&2; exit 64; }
REPO= BASE= WORK_ID=
while (($#)); do
  case "$1" in
    --repo) REPO=$2; shift 2;;
    --base) BASE=$2; shift 2;;
    --work-id) WORK_ID=$2; shift 2;;
    *) usage;;
  esac
done
[[ -n "$REPO" && -n "$BASE" && -n "$WORK_ID" ]] || usage
ROOT=$(git -C "$REPO" rev-parse --show-toplevel)
BASE_SHA=$(git -C "$ROOT" rev-parse "$BASE^{commit}")
[[ "$BASE_SHA" == "2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb" ]] || { echo "unexpected base $BASE_SHA" >&2; exit 2; }
# Only baseline-existing anchors are required here. Future directories are not checked.
for d in Model Order MessageConsumer User Redishelper sql_uat; do
  git -C "$ROOT" cat-file -e "$BASE_SHA:$d" || { echo "missing baseline directory $d" >&2; exit 3; }
done
echo "BASELINE_PREFLIGHT_PASS $WORK_ID $BASE_SHA"
