#!/usr/bin/env bash
set -euo pipefail
ROOT=${1:?package root}
C="$ROOT/05_CONTROL"
source "$C/ensure_temp_root.sh"
pvam_prepare_tmpdir "$(dirname "$ROOT")/.pvam_tmp"
W="$ROOT/04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件"
T="$ROOT/03_MODPLAN/MODPLAN-PVAM_v1.2_终稿修改方案套件"
PLAN="$ROOT/01_PLAN/Redemption_PV_Amount_Migration_d74_检查方案_v1.15.md"
REPORT="$ROOT/02_REPORT/REPORT-PVAM-v1.5.md"
MOD="$T/MODPLAN-PVAM_v1.2_总方案.md"
V="$C/validate_traceability_v3.py"
BASE_ARGS=(--manifest "$C/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$REPORT" --modplan "$MOD" --task-dir "$T" --work-dir "$W")
python "$V" "${BASE_ARGS[@]}"
TMP=$(mktemp -d "$TMPDIR/pvam-trace-v3.XXXXXX")
trap 'rm -rf "$TMP" >/dev/null 2>&1 || true' EXIT

expect_fail() {
  local label=$1; shift
  if "$@" >"$TMP/$label.stdout" 2>"$TMP/$label.stderr"; then
    echo "negative traceability case unexpectedly passed: $label" >&2
    exit 40
  fi
  grep -q 'TRACEABILITY_V3_FAIL' "$TMP/$label.stderr"
  echo "TRACE_NEGATIVE_PASS $label"
}

expect_fail_contains() {
  local label=$1
  local expected=$2
  shift 2
  if "$@" >"$TMP/$label.stdout" 2>"$TMP/$label.stderr"; then
    echo "negative traceability case unexpectedly passed: $label" >&2
    exit 41
  fi
  grep -q 'TRACEABILITY_V3_FAIL' "$TMP/$label.stderr"
  if ! grep -Fq "$expected" "$TMP/$label.stderr"; then
    echo "negative traceability case failed for the wrong reason: $label" >&2
    cat "$TMP/$label.stderr" >&2
    exit 42
  fi
  echo "TRACE_AUTHORITY_NEGATIVE_PASS $label"
}

# WORK-side local TC orphan.
cp -a "$W" "$TMP/work-tc"
python - "$TMP/work-tc/WORK-PVAM-01_金额编码公共层与基础模型适配器.md" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text(encoding='utf-8')
needle='### 9.2 开发环境自动验证'
s=s.replace(needle,'| TC-PVAM-01-99 | orphan | x | x | x | x | DEV | NOT_RUN |\n\n'+needle,1)
p.write_text(s,encoding='utf-8')
PY
expect_fail work_tc_orphan python "$V" "${BASE_ARGS[@]:0:10}" --work-dir "$TMP/work-tc"

# WORK-side EV orphan.
cp -a "$W" "$TMP/work-ev"
python - "$TMP/work-ev/WORK-PVAM-01_金额编码公共层与基础模型适配器.md" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text(encoding='utf-8')
needle='## 13. '
s=s.replace(needle,'| EV-PVAM-01-99 | orphan | STEP-PVAM-01-01 | evidence/orphan/ | QA | PENDING |\n\n'+needle,1)
p.write_text(s,encoding='utf-8')
PY
expect_fail work_ev_orphan python "$V" "${BASE_ARGS[@]:0:10}" --work-dir "$TMP/work-ev"

# REPORT-side orphan issue.
cp "$REPORT" "$TMP/report.md"
printf '\n| R-999 | injected orphan | P0 | CHK-DATA-001 | fake | FAIL |\n' >> "$TMP/report.md"
expect_fail report_issue_orphan python "$V" --manifest "$C/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$TMP/report.md" --modplan "$MOD" --task-dir "$T" --work-dir "$W"

# TASK single-side CHK deletion.
cp -a "$T" "$TMP/tasks"
python - "$TMP/tasks/TASK-PVAM-07A_Consumer_ACK紧急修复.md" <<'PY'
from pathlib import Path
import sys,re
p=Path(sys.argv[1]); s=p.read_text(encoding='utf-8')
pat=r'(\| 来源检查项 \|[^\n]*)CHK-TEST-001、?'
s2,n=re.subn(pat,lambda m:m.group(1).replace('CHK-TEST-001、','').replace('、CHK-TEST-001','').replace('CHK-TEST-001',''),s,count=1)
if n!=1: raise SystemExit('source check row not modified')
p.write_text(s2,encoding='utf-8')
PY
expect_fail task_edge_missing python "$V" --manifest "$C/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$REPORT" --modplan "$TMP/tasks/MODPLAN-PVAM_v1.2_总方案.md" --task-dir "$TMP/tasks" --work-dir "$W"

# PLAN orphan controlled test.
cp "$PLAN" "$TMP/plan.md"
printf '\n| TC-999 | CHK-DATA-001 | injected orphan | DEV |\n' >> "$TMP/plan.md"
expect_fail plan_test_orphan python "$V" --manifest "$C/TRACEABILITY_MANIFEST.json" --plan "$TMP/plan.md" --report "$REPORT" --modplan "$MOD" --task-dir "$T" --work-dir "$W"

make_bad_control() {
  local name=$1
  mkdir -p "$TMP/$name/control"
  cp "$C/TRACEABILITY_MANIFEST.json" "$TMP/$name/control/TRACEABILITY_MANIFEST.json"
  cp "$C/TRACEABILITY_MANIFEST.md" "$TMP/$name/control/TRACEABILITY_MANIFEST.md"
  cp "$V" "$TMP/$name/control/validate_traceability_v3.py"
}

# Manifest-side local node orphan.
make_bad_control manifest_orphan
python - "$TMP/manifest_orphan/control/TRACEABILITY_MANIFEST.json" <<'PY'
import json,sys
p=sys.argv[1];d=json.load(open(p,encoding='utf-8'));d['core_edges'][0]['local_tests'].append('TC-PVAM-01-99');json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
PY
expect_fail manifest_orphan python "$TMP/manifest_orphan/control/validate_traceability_v3.py" --manifest "$TMP/manifest_orphan/control/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$REPORT" --modplan "$MOD" --task-dir "$T" --work-dir "$W"

# Wrong non-core status.
make_bad_control noncore_status
python - "$TMP/noncore_status/control/TRACEABILITY_MANIFEST.json" <<'PY'
import json,sys
p=sys.argv[1];d=json.load(open(p,encoding='utf-8'));d['non_core_edges'][0]['status']='ACCEPTED';json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
PY
expect_fail noncore_status python "$TMP/noncore_status/control/validate_traceability_v3.py" --manifest "$TMP/noncore_status/control/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$REPORT" --modplan "$MOD" --task-dir "$T" --work-dir "$W"

# TC-020 omission.
make_bad_control tc020_missing
python - "$TMP/tc020_missing/control/TRACEABILITY_MANIFEST.json" <<'PY'
import json,sys
p=sys.argv[1];d=json.load(open(p,encoding='utf-8'))
for row in d['controlled_test_mappings']:
 row['controlled_tc']=[x for x in row['controlled_tc'] if x!='TC-020']
json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
PY
expect_fail tc020_missing python "$TMP/tc020_missing/control/validate_traceability_v3.py" --manifest "$TMP/tc020_missing/control/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$REPORT" --modplan "$MOD" --task-dir "$T" --work-dir "$W"

# Wrong R-012 parent and duplicate edge ID.
make_bad_control parent_wrong
python - "$TMP/parent_wrong/control/TRACEABILITY_MANIFEST.json" <<'PY'
import json,sys
p=sys.argv[1];d=json.load(open(p,encoding='utf-8'));d['core_edges'][11]['parent_issue_id']='R-011';json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
PY
expect_fail parent_wrong python "$TMP/parent_wrong/control/validate_traceability_v3.py" --manifest "$TMP/parent_wrong/control/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$REPORT" --modplan "$MOD" --task-dir "$T" --work-dir "$W"

make_bad_control duplicate_issue
python - "$TMP/duplicate_issue/control/TRACEABILITY_MANIFEST.json" <<'PY'
import json,sys,copy
p=sys.argv[1];d=json.load(open(p,encoding='utf-8'));d['core_edges'].append(copy.deepcopy(d['core_edges'][0]));json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
PY
expect_fail duplicate_issue python "$TMP/duplicate_issue/control/validate_traceability_v3.py" --manifest "$TMP/duplicate_issue/control/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$REPORT" --modplan "$MOD" --task-dir "$T" --work-dir "$W"

prepare_cross_layer_case() {
  local name=$1
  local mode=$2
  make_bad_control "$name"
  cp -a "$T" "$TMP/$name/tasks"
  cp -a "$W" "$TMP/$name/works"
  python - \
    "$TMP/$name/control/TRACEABILITY_MANIFEST.json" \
    "$TMP/$name/tasks" \
    "$TMP/$name/works" \
    "$mode" <<'PY'
from pathlib import Path
import json
import re
import sys

manifest_path = Path(sys.argv[1])
task_dir = Path(sys.argv[2])
work_dir = Path(sys.argv[3])
mode = sys.argv[4]
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
edge = next(row for row in manifest["core_edges"] if row["issue_id"] == "R-001")

task_files = {
    path.name.split("_", 1)[0]: path for path in task_dir.glob("TASK-PVAM-*.md")
}
work_files = {
    path.name.split("_", 1)[0]: path
    for path in work_dir.glob("WORK-PVAM-*.md")
    if "完整套件" not in path.name
}

def replace_metadata(path: Path, label: str, values: set[str]) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^(\| {re.escape(label)} \| `)([^`]*)(` \|)$", re.M)
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"missing metadata row {label}: {path}")
    replacement = match.group(1) + "、".join(sorted(values)) + match.group(3)
    path.write_text(text[:match.start()] + replacement + text[match.end():], encoding="utf-8")

def recompute_changed_task_metadata() -> None:
    fields = ("source_checks", "source_issues", "decisions")
    aggregate = {
        task_id: {field: set() for field in fields}
        for task_id in task_files
    }
    for row in manifest["core_edges"]:
        linked = {row["issue_id"]}
        if row.get("parent_issue_id"):
            linked.add(row["parent_issue_id"])
        target = aggregate[row["task_id"]]
        target["source_checks"].update(row.get("checks", []))
        target["source_issues"].update(linked)
        target["decisions"].update(row.get("decisions", []))
    for row in manifest["non_core_edges"]:
        task_id = row.get("task_id")
        if task_id is None:
            continue
        target = aggregate[task_id]
        target["source_checks"].update(row.get("checks", []))
        target["source_issues"].add(row["item_id"])
        target["decisions"].update(row.get("decisions", []))
    labels = {
        "source_checks": "来源检查项",
        "source_issues": "来源问题",
        "decisions": "关联决策",
    }
    for task_id in ("TASK-PVAM-01", "TASK-PVAM-03"):
        for field, label in labels.items():
            replace_metadata(task_files[task_id], label, aggregate[task_id][field])
            manifest["task_contracts"][task_id][field] = sorted(aggregate[task_id][field])

if mode == "false_check":
    edge["checks"].append("CHK-BIZ-001")
    for contracts, doc_id in (
        ("task_contracts", "TASK-PVAM-01"),
        ("work_contracts", "WORK-PVAM-01"),
    ):
        manifest[contracts][doc_id]["source_checks"].append("CHK-BIZ-001")
        manifest[contracts][doc_id]["source_checks"].sort()
    replace_metadata(
        task_files["TASK-PVAM-01"],
        "来源检查项",
        set(manifest["task_contracts"]["TASK-PVAM-01"]["source_checks"]),
    )
    replace_metadata(
        work_files["WORK-PVAM-01"],
        "来源检查项",
        set(manifest["work_contracts"]["WORK-PVAM-01"]["source_checks"]),
    )
elif mode in {"wrong_route", "wrong_pair"}:
    edge["task_id"] = "TASK-PVAM-03"
    recompute_changed_task_metadata()
    if mode == "wrong_pair":
        modplan = task_dir / "MODPLAN-PVAM_v1.2_总方案.md"
        text = modplan.read_text(encoding="utf-8")
        old = "| R-001 amount version 缺失 | P0 | ACCEPTED | REM-001 | W-001 | V-001 | 01 |"
        new = "| R-001 amount version 缺失 | P0 | ACCEPTED | REM-001 | W-001 | V-001 | 03 |"
        if text.count(old) != 1:
            raise SystemExit("R-001 MODPLAN route row is not unique")
        modplan.write_text(text.replace(old, new, 1), encoding="utf-8")
        manifest["document_inventory"]["modplan"]["core_dispositions"]["R-001"]["tasks"] = [
            "TASK-PVAM-03"
        ]
else:
    raise SystemExit(f"unknown mutation mode {mode}")

manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

# A valid PLAN CHK synchronised into edge/TASK/WORK/contracts is still false
# when REPORT never assigned that CHK to the issue.
prepare_cross_layer_case false_report_check_edge false_check
expect_fail_contains false_report_check_edge "R-001 REPORT check authority" \
  python "$TMP/false_report_check_edge/control/validate_traceability_v3.py" \
  --manifest "$TMP/false_report_check_edge/control/TRACEABILITY_MANIFEST.json" \
  --plan "$PLAN" --report "$REPORT" \
  --modplan "$TMP/false_report_check_edge/tasks/MODPLAN-PVAM_v1.2_总方案.md" \
  --task-dir "$TMP/false_report_check_edge/tasks" \
  --work-dir "$TMP/false_report_check_edge/works"

# Reassigning an issue edge to a TASK outside MODPLAN's authoritative task set
# must fail even when TASK metadata and the JSON mirror are synchronised.
prepare_cross_layer_case wrong_issue_task_route wrong_route
expect_fail_contains wrong_issue_task_route "R-001 MODPLAN task authority" \
  python "$TMP/wrong_issue_task_route/control/validate_traceability_v3.py" \
  --manifest "$TMP/wrong_issue_task_route/control/TRACEABILITY_MANIFEST.json" \
  --plan "$PLAN" --report "$REPORT" \
  --modplan "$TMP/wrong_issue_task_route/tasks/MODPLAN-PVAM_v1.2_总方案.md" \
  --task-dir "$TMP/wrong_issue_task_route/tasks" \
  --work-dir "$TMP/wrong_issue_task_route/works"

# Even if MODPLAN and the edge are synchronised to a different TASK, a WORK
# that still declares its canonical source TASK must reject the mismatched pair.
prepare_cross_layer_case wrong_task_work_pair wrong_pair
expect_fail_contains wrong_task_work_pair "R-001 WORK source task authority" \
  python "$TMP/wrong_task_work_pair/control/validate_traceability_v3.py" \
  --manifest "$TMP/wrong_task_work_pair/control/TRACEABILITY_MANIFEST.json" \
  --plan "$PLAN" --report "$REPORT" \
  --modplan "$TMP/wrong_task_work_pair/tasks/MODPLAN-PVAM_v1.2_总方案.md" \
  --task-dir "$TMP/wrong_task_work_pair/tasks" \
  --work-dir "$TMP/wrong_task_work_pair/works"

prepare_reverse_orphan_case() {
  local name=$1
  local field=$2
  local label=$3
  local token=$4
  make_bad_control "$name"
  cp -a "$T" "$TMP/$name/tasks"
  cp -a "$W" "$TMP/$name/works"
  python - \
    "$TMP/$name/tasks/TASK-PVAM-01_金额编码公共层与基础模型适配器.md" \
    "$TMP/$name/works/WORK-PVAM-01_金额编码公共层与基础模型适配器.md" \
    "$TMP/$name/control/TRACEABILITY_MANIFEST.json" \
    "$field" "$label" "$token" <<'PY'
from pathlib import Path
import json
import re
import sys

task_path, work_path, manifest_path = map(Path, sys.argv[1:4])
field, label, token = sys.argv[4:7]

def add_metadata_token(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^(\| {re.escape(label)} \| `)([^`]*)(` \|)$", re.M)
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"missing metadata row {label} in {path}")
    values = match.group(2)
    if token in values:
        raise SystemExit(f"test token already present in {path}")
    replacement = match.group(1) + values + "、" + token + match.group(3)
    path.write_text(text[:match.start()] + replacement + text[match.end():], encoding="utf-8")

add_metadata_token(task_path)
add_metadata_token(work_path)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
for contracts, doc_id in (
    ("task_contracts", "TASK-PVAM-01"),
    ("work_contracts", "WORK-PVAM-01"),
):
    values = manifest[contracts][doc_id][field]
    values.append(token)
    values.sort()
manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

# Synchronising an extra valid token across TASK metadata, WORK metadata and both
# manifest contracts must still fail when no execution edge references it.
prepare_reverse_orphan_case reverse_dec_orphan decisions 关联决策 DEC-001
expect_fail reverse_dec_orphan \
  python "$TMP/reverse_dec_orphan/control/validate_traceability_v3.py" \
  --manifest "$TMP/reverse_dec_orphan/control/TRACEABILITY_MANIFEST.json" \
  --plan "$PLAN" --report "$REPORT" --modplan "$TMP/reverse_dec_orphan/tasks/MODPLAN-PVAM_v1.2_总方案.md" \
  --task-dir "$TMP/reverse_dec_orphan/tasks" --work-dir "$TMP/reverse_dec_orphan/works"

prepare_reverse_orphan_case reverse_check_orphan source_checks 来源检查项 CHK-BIZ-001
expect_fail reverse_check_orphan \
  python "$TMP/reverse_check_orphan/control/validate_traceability_v3.py" \
  --manifest "$TMP/reverse_check_orphan/control/TRACEABILITY_MANIFEST.json" \
  --plan "$PLAN" --report "$REPORT" --modplan "$TMP/reverse_check_orphan/tasks/MODPLAN-PVAM_v1.2_总方案.md" \
  --task-dir "$TMP/reverse_check_orphan/tasks" --work-dir "$TMP/reverse_check_orphan/works"

prepare_reverse_orphan_case reverse_issue_orphan source_issues 来源问题 R-003
expect_fail reverse_issue_orphan \
  python "$TMP/reverse_issue_orphan/control/validate_traceability_v3.py" \
  --manifest "$TMP/reverse_issue_orphan/control/TRACEABILITY_MANIFEST.json" \
  --plan "$PLAN" --report "$REPORT" --modplan "$TMP/reverse_issue_orphan/tasks/MODPLAN-PVAM_v1.2_总方案.md" \
  --task-dir "$TMP/reverse_issue_orphan/tasks" --work-dir "$TMP/reverse_issue_orphan/works"


# Duplicate TASK metadata shadow must fail.
cp -a "$T" "$TMP/tasks-dup-meta"
python - "$TMP/tasks-dup-meta/TASK-PVAM-07A_Consumer_ACK紧急修复.md" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text(encoding='utf-8'); marker='| 来源检查项 |'
line=next(x for x in s.splitlines() if x.startswith(marker))
s=s.replace(line, line+'\n| 来源检查项 | CHK-TEST-999 |',1); p.write_text(s,encoding='utf-8')
PY
expect_fail task_duplicate_metadata python "$V" --manifest "$C/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$REPORT" --modplan "$TMP/tasks-dup-meta/MODPLAN-PVAM_v1.2_总方案.md" --task-dir "$TMP/tasks-dup-meta" --work-dir "$W"

# Duplicate WORK metadata shadow must fail.
cp -a "$W" "$TMP/work-dup-meta"
python - "$TMP/work-dup-meta/WORK-PVAM-07A_Consumer_ACK紧急修复.md" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text(encoding='utf-8'); marker='| 来源检查项 |'
line=next(x for x in s.splitlines() if x.startswith(marker))
s=s.replace(line, line+'\n| 来源检查项 | CHK-TEST-999 |',1); p.write_text(s,encoding='utf-8')
PY
expect_fail work_duplicate_metadata python "$V" --manifest "$C/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$REPORT" --modplan "$MOD" --task-dir "$T" --work-dir "$TMP/work-dup-meta"

# Duplicate MODPLAN non-core status must fail even when the first row is correct.
cp "$MOD" "$TMP/mod-dup.md"
printf '\n| RISK-001 | P1 | ACCEPTED | injected duplicate | 08 | shadow |\n' >> "$TMP/mod-dup.md"
expect_fail mod_duplicate_noncore python "$V" --manifest "$C/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$REPORT" --modplan "$TMP/mod-dup.md" --task-dir "$T" --work-dir "$W"

# Duplicate REPORT REM/W/V edge must fail.
cp "$REPORT" "$TMP/report-dup.md"
printf '\n| CHK-DATA-001 | R-001 | REM-001 | W-001 | V-001 | injected duplicate |\n' >> "$TMP/report-dup.md"
expect_fail report_duplicate_edge python "$V" --manifest "$C/TRACEABILITY_MANIFEST.json" --plan "$PLAN" --report "$TMP/report-dup.md" --modplan "$MOD" --task-dir "$T" --work-dir "$W"

echo TRACEABILITY_V3_SELFTEST_PASS
