#!/usr/bin/env bash
set -euo pipefail
C=$(cd "$(dirname "$0")" && pwd)
source "$C/ensure_temp_root.sh"
PACKAGE_ROOT=$(cd "$C/.." && pwd)
pvam_prepare_tmpdir "$(dirname "$PACKAGE_ROOT")/.pvam_tmp"
exec bash "$C/selftest_dev_parent_tree.sh"
