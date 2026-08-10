#!/usr/bin/env bash
set -euo pipefail
ROOT=${1:?package root}
C="$ROOT/05_CONTROL"
source "$C/ensure_temp_root.sh"
pvam_prepare_tmpdir "$(dirname "$ROOT")/.pvam_tmp"
python "$C/validate_document_governance.py" --root "$ROOT"
TMP=$(mktemp -d "$TMPDIR/pvam-governance.XXXXXX")
trap 'rm -rf "$TMP" >/dev/null 2>&1 || true' EXIT
cp -a "$ROOT" "$TMP/pkg"
reset_pkg() {
  local attempt
  for attempt in {1..20}; do
    if rm -rf "$TMP/pkg" 2>/dev/null; then
      cp -a "$ROOT" "$TMP/pkg"
      return 0
    fi
    sleep 0.1
  done
  echo "BLOCKED_ENV_CAPABILITY: unable to reset governance selftest package" >&2
  return 79
}
TARGET="$TMP/pkg/04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PVAM-01_金额编码公共层与基础模型适配器.md"
sed -i 's/| 文档版本 | `v1.3` |/| 文档版本 | `v1.2` |/' "$TARGET"
if python "$TMP/pkg/05_CONTROL/validate_document_governance.py" --root "$TMP/pkg" >/dev/null 2>&1; then
  echo 'old WORK metadata version was not rejected' >&2
  exit 41
fi
reset_pkg
TARGET="$TMP/pkg/04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PVAM-07B_事件路由与Stream保留.md"
printf '\n无 GHOST_IN_DOUBT 且 XLEN 门禁通过才可恢复固定 MAXLEN。\n' >> "$TARGET"
if python "$TMP/pkg/05_CONTROL/validate_document_governance.py" --root "$TMP/pkg" >/dev/null 2>&1; then
  echo 'weak fixed MAXLEN path was not rejected' >&2
  exit 42
fi
echo DOCUMENT_GOVERNANCE_SELFTEST_PASS

# TASK/WORK source AC text drift must fail.
reset_pkg
TARGET="$TMP/pkg/04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PVAM-01_金额编码公共层与基础模型适配器.md"
sed -i 's/NaN、Infinity、指数文本/NaN、sNaN、Infinity、指数文本/' "$TARGET"
if python "$TMP/pkg/05_CONTROL/validate_document_governance.py" --root "$TMP/pkg" >/dev/null 2>&1; then
  echo 'AC source drift was not rejected' >&2
  exit 47
fi
echo DOCUMENT_GOVERNANCE_AC_NEGATIVE_PASS

# TASK/WORK AC environment drift must fail independently of source-text drift.
reset_pkg
TARGET="$TMP/pkg/04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PVAM-01_金额编码公共层与基础模型适配器.md"
sed -i '/^| AC-06 |/ s/| DEV |/| UAT |/' "$TARGET"
if python "$TMP/pkg/05_CONTROL/validate_document_governance.py" --root "$TMP/pkg" >/dev/null 2>&1; then
  echo 'AC environment drift was not rejected' >&2
  exit 48
fi
echo DOCUMENT_GOVERNANCE_AC_ENV_NEGATIVE_PASS

# The dedicated AC-06 derived-test carrier is mandatory and unique.
reset_pkg
TARGET="$TMP/pkg/04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PVAM-01_金额编码公共层与基础模型适配器.md"
sed -i 's/^### 10\.1 AC-06 实施细化 \/ 派生测试$/### 10.1 AC-06 派生测试说明/' "$TARGET"
if python "$TMP/pkg/05_CONTROL/validate_document_governance.py" --root "$TMP/pkg" >/dev/null 2>&1; then
  echo 'missing dedicated AC-06 detail section was not rejected' >&2
  exit 49
fi
echo DOCUMENT_GOVERNANCE_AC06_SECTION_NEGATIVE_PASS

# The WORK total §4.1 index is a controlled mirror of specialised WORK metadata
# and TRACEABILITY_MANIFEST.work_contracts. Reintroducing the stale WORK-08 row
# must be rejected independently of the root SHA layer.
reset_pkg
TARGET="$TMP/pkg/04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PLAN-PVAM_v1.3_施工总方案.md"
sed -i \
  's/RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002、GAP-DEC004-2B | DEC-004、DEC-009、DEC-010、DEC-012、DEC-013、DEC-017、DEC-018/RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002 | DEC-009、DEC-010、DEC-012、DEC-013、DEC-015、DEC-017/' \
  "$TARGET"
if python "$TMP/pkg/05_CONTROL/validate_document_governance.py" --root "$TMP/pkg" >/dev/null 2>&1; then
  echo 'stale WORK-08 total index was not rejected' >&2
  exit 52
fi
echo DOCUMENT_GOVERNANCE_WORK_INDEX_NEGATIVE_PASS

expect_version_failure() {
  local pkg=$1
  local expected=$2
  local label=$3
  local stdout="$TMP/${label}.stdout"
  local stderr="$TMP/${label}.stderr"
  if python "$pkg/05_CONTROL/validate_version_references.py" \
    --root "$pkg" --manifest "$pkg/05_CONTROL/VERSION_REFERENCE_MANIFEST.json" \
    >"$stdout" 2>"$stderr"; then
    echo "version-reference negative unexpectedly passed: $label" >&2
    exit 50
  fi
  if ! grep -Fq "$expected" "$stderr"; then
    echo "version-reference negative failed for the wrong reason: $label" >&2
    cat "$stderr" >&2
    exit 51
  fi
  echo "VERSION_REFERENCE_NEGATIVE_PASS $label"
}

refresh_root_sha_entry() {
  local pkg=$1
  local relative=$2
  python - "$pkg" "$relative" <<'PY'
from hashlib import sha256
from pathlib import Path
import sys

root = Path(sys.argv[1])
relative = sys.argv[2]
target = root / relative
digest = sha256(target.read_bytes()).hexdigest()
manifest = root / "SHA256SUMS.txt"
lines = manifest.read_text(encoding="utf-8").splitlines()
suffix = "  " + relative
matches = [index for index, line in enumerate(lines) if line.endswith(suffix)]
if len(matches) != 1:
    raise SystemExit(f"expected one root SHA entry for {relative}, got {len(matches)}")
lines[matches[0]] = digest + suffix
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

# Current input roles are an allowlist, not caller-selected existing paths.
reset_pkg
sed -i 's#06_HISTORY/全链路项目工程文档七轮终局审查与核验报告.md#README.md#' \
  "$TMP/pkg/05_CONTROL/VERSION_REFERENCE_MANIFEST.json"
expect_version_failure "$TMP/pkg" 'current review input roles/paths' current_input_role

# A floating token cannot repair an incorrect structural heading.
reset_pkg
TARGET="$TMP/pkg/04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PLAN-PVAM_v1.3_施工总方案.md"
sed -i 's/^#### Traceability Manifest v3$/#### Traceability Manifest v2/' "$TARGET"
printf '\nTraceability Manifest v3\n' >> "$TARGET"
expect_version_failure "$TMP/pkg" 'level-4 heading' shadow_traceability_heading

# A floating revision token cannot replace a row in the version-history table.
reset_pkg
TARGET="$TMP/pkg/04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PVAM-01_金额编码公共层与基础模型适配器.md"
sed -i '/^| v1\.3-r8 |/d' "$TARGET"
printf '\nv1.3-r8\n' >> "$TARGET"
expect_version_failure "$TMP/pkg" 'expected exactly one v1.3-r8 row' shadow_revision_token

# The active authorization round must be a real H2, not a floating token.
reset_pkg
TARGET="$TMP/pkg/05_CONTROL/AUTHORIZATION_STATUS-PVAM-v2.md"
sed -i 's/^## 第八轮技术就绪声明$/## 第七轮技术就绪声明/' "$TARGET"
printf '\n第八轮技术就绪声明\n' >> "$TARGET"
expect_version_failure "$TMP/pkg" 'level-2 heading' shadow_authorization_round

# A valid structural occurrence plus one extra raw occurrence must fail. Root
# SHA is refreshed so these cases prove token semantics rather than hash drift.
reset_pkg
RELATIVE='04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PLAN-PVAM_v1.3_施工总方案.md'
printf '\nTraceability Manifest v3\n' >> "$TMP/pkg/$RELATIVE"
refresh_root_sha_entry "$TMP/pkg" "$RELATIVE"
expect_version_failure "$TMP/pkg" 'expected exactly 1 raw occurrence, got 2' shadow_traceability_extra_occurrence

reset_pkg
RELATIVE='04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PVAM-01_金额编码公共层与基础模型适配器.md'
printf '\nv1.3-r8\n' >> "$TMP/pkg/$RELATIVE"
refresh_root_sha_entry "$TMP/pkg" "$RELATIVE"
expect_version_failure "$TMP/pkg" 'expected exactly 1 raw occurrence, got 2' shadow_revision_extra_occurrence

reset_pkg
RELATIVE='05_CONTROL/AUTHORIZATION_STATUS-PVAM-v2.md'
printf '\n第八轮技术就绪声明\n' >> "$TMP/pkg/$RELATIVE"
refresh_root_sha_entry "$TMP/pkg" "$RELATIVE"
expect_version_failure "$TMP/pkg" 'expected exactly 1 raw occurrence, got 2' shadow_authorization_extra_occurrence

# Root SHA coverage is a bidirectional physical-file set comparison.
reset_pkg
sed -i '\#03_MODPLAN/MODPLAN-PVAM_v1.2_终稿修改方案套件/SHA256SUMS.txt$#d' \
  "$TMP/pkg/SHA256SUMS.txt"
expect_version_failure "$TMP/pkg" 'root SHA file-set mismatch' root_sha_missing_entry

# Package count fields are verified against the physical package.
reset_pkg
sed -E -i 's/"package_file_count_total":[[:space:]]*[0-9]+/"package_file_count_total": 999999/' \
  "$TMP/pkg/DOCUMENT_MANIFEST.json"
expect_version_failure "$TMP/pkg" 'package_file_count_total does not match physical files' package_count_drift
