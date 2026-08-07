#!/usr/bin/env bash
# shellcheck shell=bash
pvam_prepare_tmpdir() {
  local fallback=${1:-"$PWD/.pvam_tmp"}
  local candidate
  for candidate in "${TMPDIR:-}" "$fallback" /tmp; do
    [[ -n "$candidate" ]] || continue
    if [[ ! -d "$candidate" ]]; then
      mkdir -p "$candidate" 2>/dev/null || continue
    fi
    if [[ -w "$candidate" ]]; then
      TMPDIR=$(cd "$candidate" && pwd)
      export TMPDIR
      return 0
    fi
  done
  echo "BLOCKED_ENV_CAPABILITY: no writable temporary directory; set TMPDIR" >&2
  return 78
}
