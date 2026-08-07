#!/usr/bin/env bash
set -euo pipefail
ROOT=${1:?package root}
C="$ROOT/05_CONTROL"
source "$C/ensure_temp_root.sh"
pvam_prepare_tmpdir "$(dirname "$ROOT")/.pvam_tmp"
python "$C/validate_traceability_v3.py" \
  --manifest "$C/TRACEABILITY_MANIFEST.json" \
  --plan "$ROOT/01_PLAN/Redemption_PV_Amount_Migration_d74_检查方案_v1.15.md" \
  --report "$ROOT/02_REPORT/REPORT-PVAM-v1.5.md" \
  --modplan "$ROOT/03_MODPLAN/MODPLAN-PVAM_v1.2_终稿修改方案套件/MODPLAN-PVAM_v1.2_总方案.md" \
  --task-dir "$ROOT/03_MODPLAN/MODPLAN-PVAM_v1.2_终稿修改方案套件" \
  --work-dir "$ROOT/04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件"
python "$C/validate_document_governance.py" --root "$ROOT"
python "$C/validate_version_references.py" --root "$ROOT" --manifest "$C/VERSION_REFERENCE_MANIFEST.json"
bash "$C/selftest_traceability_v3.sh" "$ROOT"
bash "$C/selftest_document_governance.sh" "$ROOT"
env -u OLDPWD bash "$C/selftest_patch_policy.sh"
bash "$C/selftest_dev_parent_tree.sh"
echo ALL_CONTROL_SELFTESTS_PASS
