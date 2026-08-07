#!/usr/bin/env python3
"""Validate the PVAM eight-level traceability contract.

The validator treats the canonical TRACEABILITY_MANIFEST.json as a contract and
independently parses PLAN, REPORT, MODPLAN, TASK and WORK Markdown documents.
It performs bidirectional set comparisons for nodes and directed edges. Any
missing, extra or duplicate controlled node exits non-zero.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

BASELINE = "2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb"

CHECK_RE = re.compile(r"\bCHK-[A-Z]+-\d{3}\b")
DEC_RE = re.compile(r"\bDEC-\d{3}\b")
CORE_ISSUE_RE = re.compile(r"\bR-\d{3}(?:A|B)?\b")
NON_CORE_RE = re.compile(r"\b(?:RISK|UV|OPT)-\d{3}\b|\bGAP-[A-Z0-9-]+\b|\bFIX-\d{3}\b")
TASK_RE = re.compile(r"TASK-PVAM-(?:07A|07B|0[1-8])(?![0-9A-Z])")
WORK_RE = re.compile(r"WORK-PVAM-(?:07A|07B|0[1-8])(?![0-9A-Z])")
REM_RE = re.compile(r"\bREM-\d{3}(?:A|B)?\b")
IMPL_RE = re.compile(r"\bW-\d{3}(?:A|B)?\b")
VERIFY_RE = re.compile(r"\bV-\d{3}(?:A|B)?\b")
STEP_RE = re.compile(r"^###\s+(STEP-PVAM-[0-9A-Z]+-[0-9]{2})[：:]", re.M)
LOCAL_TC_RE = re.compile(r"^\|\s*(TC-PVAM-[0-9A-Z]+-[0-9]{2})\s*\|", re.M)
EV_RE = re.compile(r"^\|\s*(EV-PVAM-[0-9A-Z]+-(?:[0-9]{2}|P[0-9]{2}))\s*\|", re.M)
CONTROLLED_TC_RE = re.compile(r"\bTC-\d{3}\b")

EXPECTED_TASKS = {
    "TASK-PVAM-01", "TASK-PVAM-02", "TASK-PVAM-03", "TASK-PVAM-04",
    "TASK-PVAM-05", "TASK-PVAM-06", "TASK-PVAM-07A",
    "TASK-PVAM-07B", "TASK-PVAM-08",
}
EXPECTED_WORKS = {task.replace("TASK-", "WORK-") for task in EXPECTED_TASKS}
EXPECTED_CORE = [f"R-{i:03d}" for i in range(1, 14)]
EXPECTED_SUBISSUES = {"R-012A", "R-012B"}
EXPECTED_NON_CORE_STATUS = {
    "RISK": "UAT_VERIFY",
    "UV": "UAT_VERIFY",
    "OPT": "ACCEPTED",
    "GAP": "DEFERRED",
    "FIX": "CONFIRMED_CLOSED",
}


class ValidationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def read(path: Path) -> str:
    if not path.is_file():
        fail(f"missing file: {path}")
    return path.read_text(encoding="utf-8")


def clean_cell(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`") and value.count("`") == 2:
        value = value[1:-1]
    return value.strip()


def markdown_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [clean_cell(cell) for cell in stripped[1:-1].split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells):
            continue
        rows.append(cells)
    return rows


def section(text: str, start: str, end: str | None = None) -> str:
    start_match = re.search(start, text, re.M)
    if not start_match:
        fail(f"missing section matching: {start}")
    tail = text[start_match.end():]
    if end is None:
        return tail
    end_match = re.search(end, tail, re.M)
    return tail[: end_match.start()] if end_match else tail


def duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def unique(values: Iterable[str], label: str) -> set[str]:
    vals = list(values)
    dup = duplicates(vals)
    if dup:
        fail(f"duplicate {label}: {sorted(dup)}")
    return set(vals)


def compare_sets(label: str, actual: Iterable[str], expected: Iterable[str]) -> None:
    actual_set = set(actual)
    expected_set = set(expected)
    missing = expected_set - actual_set
    extra = actual_set - expected_set
    if missing or extra:
        fail(f"{label}: missing={sorted(missing)} extra={sorted(extra)}")


def compare_mapping_sets(
    label: str,
    actual: Mapping[str, Iterable[str]],
    expected: Mapping[str, Iterable[str]],
) -> None:
    compare_sets(f"{label} keys", actual.keys(), expected.keys())
    for key in sorted(expected):
        compare_sets(f"{label}[{key}]", actual[key], expected[key])


def expand_numeric_ranges(text: str) -> str:
    """Expand forms such as TC-001～TC-032 and CHK-TEST-001～004."""
    pattern = re.compile(
        r"(?P<prefix>(?:CHK-[A-Z]+|TC|UV|RISK|OPT|R|REM|W|V|UAT)-)"
        r"(?P<start>\d{3})(?:～|~)"
        r"(?:(?P<prefix2>(?:CHK-[A-Z]+|TC|UV|RISK|OPT|R|REM|W|V|UAT)-))?"
        r"(?P<end>\d{3})"
    )

    def repl(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        prefix2 = match.group("prefix2") or prefix
        if prefix2 != prefix:
            return match.group(0)
        start = int(match.group("start"))
        end = int(match.group("end"))
        if end < start or end - start > 999:
            return match.group(0)
        return "、".join(f"{prefix}{number:03d}" for number in range(start, end + 1))

    previous = None
    current = text
    while previous != current:
        previous = current
        current = pattern.sub(repl, current)
    return current


def tokens(text: str, pattern: re.Pattern[str]) -> list[str]:
    return pattern.findall(expand_numeric_ranges(text))


def metadata_value(text: str, label: str) -> str:
    matches = [row for row in markdown_rows(text) if row and row[0] == label]
    if not matches:
        fail(f"missing metadata row: {label}")
    if len(matches) != 1:
        fail(f"duplicate metadata row: {label} count={len(matches)}")
    row = matches[0]
    if len(row) < 2:
        fail(f"metadata row has no value: {label}")
    return row[1]


def infer_doc_id(path: Path, pattern: re.Pattern[str]) -> str:
    match = pattern.search(path.name)
    if not match:
        fail(f"cannot infer controlled document ID from {path.name}")
    return match.group(0)


def load_docs(directory: Path, prefix: str, pattern: re.Pattern[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in sorted(directory.glob(f"{prefix}*.md")):
        if any(marker in path.name for marker in ("完整套件", "施工总方案", "总方案")):
            continue
        doc_id = infer_doc_id(path, pattern)
        if doc_id in result:
            fail(f"duplicate controlled document for {doc_id}: {path} and {result[doc_id]}")
        result[doc_id] = path
    return result


def normalise_first_id(cell: str, pattern: re.Pattern[str]) -> str | None:
    cleaned = cell.replace("（RETIRED）", "").strip(" `")
    match = pattern.fullmatch(cleaned)
    return match.group(0) if match else None


@dataclass(frozen=True)
class PlanContract:
    checks: set[str]
    retired_checks: set[str]
    controlled_tests: set[str]
    retired_tests: set[str]
    decisions: dict[str, str]
    test_to_checks: dict[str, set[str]]


def parse_plan(text: str) -> PlanContract:
    checks: list[str] = []
    retired_checks: list[str] = []
    tests: list[str] = []
    retired_tests: list[str] = []
    decisions: dict[str, str] = {}
    test_to_checks: dict[str, set[str]] = {}

    for row in markdown_rows(text):
        if not row:
            continue
        raw_first = row[0]
        check = normalise_first_id(raw_first, re.compile(r"CHK-[A-Z]+-\d{3}"))
        if check:
            checks.append(check)
            if "RETIRED" in raw_first:
                retired_checks.append(check)
            continue
        test = normalise_first_id(raw_first, re.compile(r"TC-\d{3}"))
        if test:
            tests.append(test)
            if len(row) < 2:
                fail(f"PLAN test row has no CHK edge: {test}")
            test_to_checks[test] = set(tokens(row[1], CHECK_RE))
            if "RETIRED" in " ".join(row):
                retired_tests.append(test)
            continue
        decision = normalise_first_id(raw_first, re.compile(r"DEC-\d{3}"))
        if decision:
            if decision in decisions:
                fail(f"duplicate PLAN decision row: {decision}")
            decisions[decision] = row[-1].strip(" `") if row else ""

    return PlanContract(
        checks=unique(checks, "PLAN CHK definitions"),
        retired_checks=unique(retired_checks, "PLAN retired CHK definitions"),
        controlled_tests=unique(tests, "PLAN TC definitions"),
        retired_tests=unique(retired_tests, "PLAN retired TC definitions"),
        decisions=decisions,
        test_to_checks=test_to_checks,
    )


@dataclass(frozen=True)
class ReportContract:
    core_issue_checks: dict[str, set[str]]
    core_issue_status: dict[str, str]
    subissue_checks: dict[str, set[str]]
    issue_remwv: dict[str, dict[str, set[str]]]
    all_issue_tokens: set[str]
    non_core_tokens: set[str]


def parse_report(text: str) -> ReportContract:
    core_issue_checks: dict[str, set[str]] = {}
    core_issue_status: dict[str, str] = {}
    subissue_checks: dict[str, set[str]] = {}
    issue_remwv: dict[str, dict[str, set[str]]] = {}

    for row in markdown_rows(text):
        if not row:
            continue
        first = row[0].strip(" `")
        if re.fullmatch(r"R-\d{3}", first):
            if first in core_issue_checks:
                fail(f"duplicate REPORT core issue definition: {first}")
            if len(row) < 6:
                fail(f"malformed REPORT core issue row: {first}")
            core_issue_checks[first] = set(tokens(row[3], CHECK_RE))
            core_issue_status[first] = row[5].strip(" `")
            continue
        if len(row) >= 5:
            second = row[1].strip(" `")
            sub_match = re.match(r"^(R-012[AB])(?:\s|（|\(|$)", second)
            if sub_match:
                subissue = sub_match.group(1)
                if subissue in subissue_checks:
                    fail(f"duplicate REPORT subissue row: {subissue}")
                subissue_checks[subissue] = set(tokens(row[0], CHECK_RE))
                issue_remwv[subissue] = {
                    "rem": set(tokens(row[2], REM_RE)),
                    "implementation": set(tokens(row[3], IMPL_RE)),
                    "verification": set(tokens(row[4], VERIFY_RE)),
                }
            elif re.fullmatch(r"R-\d{3}", second):
                if second in issue_remwv:
                    fail(f"duplicate REPORT REM/W/V edge: {second}")
                issue_remwv[second] = {
                    "rem": set(tokens(row[2], REM_RE)),
                    "implementation": set(tokens(row[3], IMPL_RE)),
                    "verification": set(tokens(row[4], VERIFY_RE)),
                }

    all_issue_tokens = set(tokens(text, CORE_ISSUE_RE))
    non_core_tokens = set(tokens(text, NON_CORE_RE))
    return ReportContract(
        core_issue_checks=core_issue_checks,
        core_issue_status=core_issue_status,
        subissue_checks=subissue_checks,
        issue_remwv=issue_remwv,
        all_issue_tokens=all_issue_tokens,
        non_core_tokens=non_core_tokens,
    )


@dataclass(frozen=True)
class ModplanContract:
    core_dispositions: dict[str, dict[str, object]]
    non_core_statuses: dict[str, str]
    decision_statuses: dict[str, str]
    task_tokens: set[str]
    issue_tokens: set[str]
    non_core_tokens: set[str]


def task_ids_from_short(cell: str) -> set[str]:
    values: set[str] = set()
    for item in re.findall(r"(?<!\d)(07A|07B|0?[1-8])(?!\d)", cell):
        suffix = item if item in {"07A", "07B"} else f"{int(item):02d}"
        values.add(f"TASK-PVAM-{suffix}")
    return values


def parse_modplan(text: str) -> ModplanContract:
    core: dict[str, dict[str, object]] = {}
    non_core_statuses: dict[str, str] = {}
    decision_statuses: dict[str, str] = {}

    for row in markdown_rows(text):
        if not row:
            continue
        first = row[0].strip(" `")
        decision_match = re.fullmatch(r"DEC-\d{3}", first)
        if decision_match:
            if first in decision_statuses:
                fail(f"duplicate MODPLAN DEC row: {first}")
            decision_statuses[first] = row[1].strip(" `") if len(row) > 1 else ""
            continue

        core_match = re.match(r"^(R-\d{3})(?:\s|$)", first)
        if core_match and "～" not in first and len(row) >= 7:
            issue = core_match.group(1)
            if issue in core:
                fail(f"duplicate MODPLAN core disposition: {issue}")
            core[issue] = {
                "status": row[2].strip(" `"),
                "rem": set(tokens(row[3], REM_RE)),
                "implementation": set(tokens(row[4], IMPL_RE)),
                "verification": set(tokens(row[5], VERIFY_RE)),
                "tasks": task_ids_from_short(row[6]),
            }
            continue

        non_match = re.match(r"^((?:RISK|UV|OPT)-\d{3}|GAP-[A-Z0-9-]+|FIX-\d{3})(?:\s|$)", first)
        if non_match:
            item = non_match.group(1)
            if item in non_core_statuses:
                fail(f"duplicate MODPLAN non-core disposition: {item}")
            if item.startswith(("RISK-", "UV-")) and len(row) >= 3:
                non_core_statuses[item] = row[2].strip(" `")
            elif len(row) >= 2:
                value = row[1].strip(" `")
                if value.startswith("N/A") and "CONFIRMED_CLOSED" in value:
                    value = "CONFIRMED_CLOSED"
                non_core_statuses[item] = value

    return ModplanContract(
        core_dispositions=core,
        non_core_statuses=non_core_statuses,
        decision_statuses=decision_statuses,
        task_tokens=set(tokens(text, re.compile(r"TASK-PVAM-(?:07A|07B|0[1-8])(?![0-9A-Z])"))),
        issue_tokens=set(tokens(text, CORE_ISSUE_RE)),
        non_core_tokens=set(tokens(text, NON_CORE_RE)),
    )


@dataclass(frozen=True)
class TaskContract:
    task_id: str
    source_checks: set[str]
    source_issues: set[str]
    decisions: set[str]
    rems: set[str]
    implementations: set[str]
    verifications: set[str]
    controlled_tests: set[str]


def parse_task(path: Path) -> TaskContract:
    text = read(path)
    task_id = infer_doc_id(path, TASK_RE)
    source_issues_text = metadata_value(text, "来源问题")
    return TaskContract(
        task_id=task_id,
        source_checks=set(tokens(metadata_value(text, "来源检查项"), CHECK_RE)),
        source_issues=set(tokens(source_issues_text, CORE_ISSUE_RE)) | set(tokens(source_issues_text, NON_CORE_RE)),
        decisions=set(tokens(metadata_value(text, "关联决策"), DEC_RE)),
        rems=set(tokens(metadata_value(text, "处置项"), REM_RE)),
        implementations=set(tokens(metadata_value(text, "施工项"), IMPL_RE)),
        verifications=set(tokens(metadata_value(text, "验证项"), VERIFY_RE)),
        controlled_tests=set(tokens(text, CONTROLLED_TC_RE)) - {"TC-000"},
    )


@dataclass(frozen=True)
class WorkContract:
    work_id: str
    source_task_id: str
    source_checks: set[str]
    source_issues: set[str]
    decisions: set[str]
    rems: set[str]
    implementations: set[str]
    verifications: set[str]
    version: str
    steps: set[str]
    local_tests: set[str]
    evidences: set[str]
    controlled_tests: set[str]


def parse_work(path: Path) -> WorkContract:
    text = read(path)
    work_id = infer_doc_id(path, WORK_RE)
    source_task_tokens = tokens(metadata_value(text, "来源修改任务"), TASK_RE)
    if len(source_task_tokens) != 1:
        fail(
            f"{work_id}: 来源修改任务 must contain exactly one TASK ID, "
            f"got {source_task_tokens}"
        )
    source_task_id = source_task_tokens[0]
    canonical_task_id = work_id.replace("WORK-", "TASK-", 1)
    if source_task_id != canonical_task_id:
        fail(
            f"{work_id}: source TASK identity mismatch: "
            f"declared={source_task_id} canonical={canonical_task_id}"
        )
    source_issues_text = metadata_value(text, "来源问题")
    trace_text = metadata_value(text, "复核闭环追踪号")
    test_section = section(text, r"^### 9\.1\b.*$", r"^### 9\.2\b.*$")
    evidence_section = section(text, r"^## 12\.\s.*$", r"^## 13\.\s.*$")
    mapping_lines = [line for line in test_section.splitlines() if "受控检查方案用例映射" in line]
    if len(mapping_lines) != 1:
        fail(f"{work_id}: expected exactly one controlled test mapping line, got {len(mapping_lines)}")
    return WorkContract(
        work_id=work_id,
        source_task_id=source_task_id,
        source_checks=set(tokens(metadata_value(text, "来源检查项"), CHECK_RE)),
        source_issues=set(tokens(source_issues_text, CORE_ISSUE_RE)) | set(tokens(source_issues_text, NON_CORE_RE)),
        decisions=set(tokens(metadata_value(text, "关联决策"), DEC_RE)),
        rems=set(tokens(trace_text, REM_RE)),
        implementations=set(tokens(trace_text, IMPL_RE)),
        verifications=set(tokens(trace_text, VERIFY_RE)),
        version=metadata_value(text, "文档版本").strip(" `"),
        steps=unique(STEP_RE.findall(text), f"{work_id} STEP definitions"),
        local_tests=unique(LOCAL_TC_RE.findall(test_section), f"{work_id} local TC definitions"),
        evidences=unique(EV_RE.findall(evidence_section), f"{work_id} EV definitions"),
        controlled_tests=set(tokens(mapping_lines[0], CONTROLLED_TC_RE)) - {"TC-000"},
    )


def serialise_contract(contract: TaskContract | WorkContract) -> dict[str, object]:
    result: dict[str, object] = {
        "source_checks": sorted(contract.source_checks),
        "source_issues": sorted(contract.source_issues),
        "decisions": sorted(contract.decisions),
        "rems": sorted(contract.rems),
        "implementations": sorted(contract.implementations),
        "verifications": sorted(contract.verifications),
        "controlled_tests": sorted(contract.controlled_tests),
    }
    if isinstance(contract, WorkContract):
        result.update({
            "source_task_id": contract.source_task_id,
            "version": contract.version,
            "steps": sorted(contract.steps),
            "local_tests": sorted(contract.local_tests),
            "evidences": sorted(contract.evidences),
        })
    return result


def compare_contract(label: str, actual: dict[str, object], expected: dict[str, object]) -> None:
    compare_sets(f"{label} fields", actual.keys(), expected.keys())
    for key in sorted(expected):
        av = actual[key]
        ev = expected[key]
        if isinstance(ev, list):
            compare_sets(f"{label}.{key}", av if isinstance(av, list) else [], ev)
        elif av != ev:
            fail(f"{label}.{key}: actual={av!r} expected={ev!r}")


def validate_canonical_control_identity(manifest_path: Path) -> None:
    control = manifest_path.parent
    forbidden_aliases = [
        control / "TRACEABILITY_MANIFEST.v2.json",
        control / "TRACEABILITY_MANIFEST.v2.md",
        control / "validate_traceability_v2.py",
    ]
    existing = [str(path.name) for path in forbidden_aliases if path.exists()]
    if existing:
        fail(f"superseded active control aliases still exist: {existing}")
    if manifest_path.name != "TRACEABILITY_MANIFEST.json":
        fail("canonical manifest filename must be TRACEABILITY_MANIFEST.json")
    if not (control / "TRACEABILITY_MANIFEST.md").is_file():
        fail("canonical markdown manifest TRACEABILITY_MANIFEST.md is missing")
    if not (control / "validate_traceability_v3.py").is_file():
        fail("canonical validator validate_traceability_v3.py is missing")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--modplan", required=True)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    validate_canonical_control_identity(manifest_path)
    manifest = json.loads(read(manifest_path))
    if manifest.get("schema_version") != 3:
        fail("schema_version must be 3")
    if manifest.get("manifest_id") != "TRACEABILITY-PVAM-v3":
        fail("manifest_id must be TRACEABILITY-PVAM-v3")
    if manifest.get("baseline_commit") != BASELINE:
        fail("baseline mismatch")

    plan_text = read(Path(args.plan))
    report_text = read(Path(args.report))
    modplan_text = read(Path(args.modplan))
    task_paths = load_docs(Path(args.task_dir), "TASK-PVAM-", TASK_RE)
    work_paths = load_docs(Path(args.work_dir), "WORK-PVAM-", WORK_RE)
    compare_sets("TASK documents", task_paths, EXPECTED_TASKS)
    compare_sets("WORK documents", work_paths, EXPECTED_WORKS)

    plan = parse_plan(plan_text)
    report = parse_report(report_text)
    modplan = parse_modplan(modplan_text)
    tasks = {task_id: parse_task(path) for task_id, path in task_paths.items()}
    works = {work_id: parse_work(path) for work_id, path in work_paths.items()}

    inventory = manifest.get("document_inventory", {})
    expected_plan = inventory.get("plan", {})
    compare_sets("PLAN checks", plan.checks, expected_plan.get("checks", []))
    compare_sets("PLAN retired checks", plan.retired_checks, expected_plan.get("retired_checks", []))
    compare_sets("PLAN tests", plan.controlled_tests, expected_plan.get("controlled_tests", []))
    compare_sets("PLAN retired tests", plan.retired_tests, expected_plan.get("retired_tests", []))
    compare_sets("PLAN decisions", plan.decisions, expected_plan.get("decisions", {}).keys())
    for decision, expected_status in expected_plan.get("decisions", {}).items():
        if plan.decisions[decision] != expected_status:
            fail(f"PLAN decision status mismatch {decision}: {plan.decisions[decision]} != {expected_status}")
    expected_test_edges = {key: set(value) for key, value in expected_plan.get("test_to_checks", {}).items()}
    compare_mapping_sets("PLAN test_to_checks", plan.test_to_checks, expected_test_edges)

    expected_report = inventory.get("report", {})
    compare_mapping_sets(
        "REPORT core issue checks",
        report.core_issue_checks,
        {key: set(value) for key, value in expected_report.get("core_issue_checks", {}).items()},
    )
    compare_mapping_sets(
        "REPORT subissue checks",
        report.subissue_checks,
        {key: set(value) for key, value in expected_report.get("subissue_checks", {}).items()},
    )
    compare_sets("REPORT issue tokens", report.all_issue_tokens, expected_report.get("issue_tokens", []))
    compare_sets("REPORT non-core tokens", report.non_core_tokens, expected_report.get("non_core_tokens", []))
    for issue, expected_status in expected_report.get("core_issue_status", {}).items():
        if report.core_issue_status.get(issue) != expected_status:
            fail(f"REPORT status mismatch {issue}: {report.core_issue_status.get(issue)} != {expected_status}")
    expected_remwv = expected_report.get("issue_remwv", {})
    compare_sets("REPORT REM/W/V issue keys", report.issue_remwv, expected_remwv)
    for issue, expected in expected_remwv.items():
        actual = report.issue_remwv[issue]
        for field in ("rem", "implementation", "verification"):
            compare_sets(f"REPORT {issue} {field}", actual[field], expected[field])

    expected_mod = inventory.get("modplan", {})
    compare_sets("MODPLAN core dispositions", modplan.core_dispositions, expected_mod.get("core_dispositions", {}).keys())
    for issue, expected in expected_mod.get("core_dispositions", {}).items():
        actual = modplan.core_dispositions[issue]
        if actual["status"] != expected["status"]:
            fail(f"MODPLAN {issue} status mismatch")
        for field in ("rem", "implementation", "verification", "tasks"):
            compare_sets(f"MODPLAN {issue} {field}", actual[field], expected[field])
    compare_sets("MODPLAN non-core items", modplan.non_core_statuses, expected_mod.get("non_core_statuses", {}).keys())
    for item, expected_status in expected_mod.get("non_core_statuses", {}).items():
        if modplan.non_core_statuses[item] != expected_status:
            fail(f"MODPLAN non-core status mismatch {item}: {modplan.non_core_statuses[item]} != {expected_status}")
    compare_sets("MODPLAN decisions", modplan.decision_statuses, expected_mod.get("decision_statuses", {}).keys())
    for decision, expected_status in expected_mod.get("decision_statuses", {}).items():
        if modplan.decision_statuses[decision] != expected_status:
            fail(f"MODPLAN decision status mismatch {decision}")
    compare_sets("MODPLAN TASK tokens", modplan.task_tokens, expected_mod.get("task_ids", []))
    compare_sets("MODPLAN issue tokens", modplan.issue_tokens, expected_mod.get("issue_tokens", []))
    compare_sets("MODPLAN non-core tokens", modplan.non_core_tokens, expected_mod.get("non_core_tokens", []))

    expected_task_contracts = manifest.get("task_contracts", {})
    compare_sets("Manifest task contracts", expected_task_contracts, EXPECTED_TASKS)
    for task_id, contract in tasks.items():
        compare_contract(f"TASK contract {task_id}", serialise_contract(contract), expected_task_contracts[task_id])

    expected_work_contracts = manifest.get("work_contracts", {})
    compare_sets("Manifest work contracts", expected_work_contracts, EXPECTED_WORKS)
    for work_id, contract in works.items():
        compare_contract(f"WORK contract {work_id}", serialise_contract(contract), expected_work_contracts[work_id])

    if manifest.get("core_issues") != EXPECTED_CORE:
        fail("core issue list mismatch")
    if manifest.get("subissues") != {"R-012": ["R-012A", "R-012B"]}:
        fail("R-012 parent/child mismatch")
    counting_rules = manifest.get("counting_rules", {})
    if counting_rules.get("bidirectional_validation_required") is not True:
        fail("bidirectional_validation_required must be true")
    if counting_rules.get("metadata_edge_equivalence_fields") != [
        "source_checks",
        "source_issues",
        "decisions",
    ]:
        fail("metadata_edge_equivalence_fields contract mismatch")
    if counting_rules.get("parent_issue_in_source_issues") is not True:
        fail("parent_issue_in_source_issues must be true")
    if counting_rules.get("cross_layer_authority_equivalence") != [
        "report_checks_equal_core_edge_checks",
        "modplan_tasks_equal_core_edge_task_aggregate",
        "work_source_task_equals_edge_task",
    ]:
        fail("cross_layer_authority_equivalence contract mismatch")

    core_edges = manifest.get("core_edges", [])
    core_ids = [row.get("issue_id") for row in core_edges]
    if len(core_ids) != 14 or len(set(core_ids)) != 14:
        fail("core_edges must contain 14 unique issue rows")
    compare_sets(
        "core edge issue IDs",
        core_ids,
        {f"R-{i:03d}" for i in range(1, 12)} | {"R-012A", "R-012B", "R-013"},
    )
    core_by_id = {row["issue_id"]: row for row in core_edges}
    if core_by_id["R-012A"].get("parent_issue_id") != "R-012":
        fail("R-012A parent_issue_id mismatch")
    if core_by_id["R-012B"].get("parent_issue_id") != "R-012":
        fail("R-012B parent_issue_id mismatch")
    compare_sets(
        "R-012A checks",
        core_by_id["R-012A"].get("checks", []),
        {"CHK-ARCH-002", "CHK-EVT-006", "CHK-EVT-007", "CHK-TEST-001", "CHK-TEST-003"},
    )
    compare_sets(
        "R-012B checks",
        core_by_id["R-012B"].get("checks", []),
        {"CHK-ARCH-002", "CHK-EVT-006", "CHK-EVT-007", "CHK-TEST-003"},
    )

    # Cross-layer authority is an equality contract. The manifest edge is not
    # allowed to become a self-authorising source: its CHK set comes from REPORT,
    # its TASK route comes from MODPLAN, and its WORK endpoint must declare that
    # same TASK as its unique source task.
    edge_tasks_by_modplan_issue: dict[str, set[str]] = defaultdict(set)
    for row in core_edges:
        issue = row["issue_id"]
        parent_issue = row.get("parent_issue_id")
        authority_issue = parent_issue or issue
        if parent_issue is None:
            authoritative_checks = report.core_issue_checks.get(issue)
        else:
            authoritative_checks = report.subissue_checks.get(issue)
        if authoritative_checks is None:
            fail(f"{issue}: no REPORT CHK authority row")
        compare_sets(
            f"{issue} REPORT check authority",
            row.get("checks", []),
            authoritative_checks,
        )

        disposition = modplan.core_dispositions.get(authority_issue)
        if disposition is None:
            fail(f"{issue}: no MODPLAN task authority for {authority_issue}")
        authorised_tasks = set(disposition["tasks"])
        task_id = row.get("task_id")
        if task_id not in authorised_tasks:
            fail(
                f"{issue} MODPLAN task authority: edge task {task_id!r} "
                f"not in {sorted(authorised_tasks)}"
            )
        edge_tasks_by_modplan_issue[authority_issue].add(task_id)

        work_id = row.get("work_id")
        if work_id not in works:
            fail(f"{issue}: unknown WORK endpoint {work_id!r}")
        if works[work_id].source_task_id != task_id:
            fail(
                f"{issue} WORK source task authority: {work_id} declares "
                f"{works[work_id].source_task_id}, edge declares {task_id}"
            )

    compare_sets(
        "MODPLAN/core-edge task authority issue keys",
        edge_tasks_by_modplan_issue,
        modplan.core_dispositions,
    )
    for issue, disposition in modplan.core_dispositions.items():
        compare_sets(
            f"{issue} MODPLAN/core-edge task authority",
            edge_tasks_by_modplan_issue[issue],
            disposition["tasks"],
        )

    non_core = manifest.get("non_core_edges", [])
    non_core_ids = [row.get("item_id") for row in non_core]
    compare_sets(
        "non-core item IDs",
        non_core_ids,
        {"RISK-001", "RISK-002", "UV-001", "UV-002", "UV-003", "UV-004", "UV-005", "OPT-001", "OPT-002", "GAP-DEC004-2B", "FIX-001"},
    )
    if len(non_core_ids) != len(set(non_core_ids)):
        fail("duplicate non-core item rows")
    for row in non_core:
        item = row["item_id"]
        domain = row.get("domain")
        expected_status = EXPECTED_NON_CORE_STATUS.get(domain)
        if expected_status is None:
            fail(f"unknown non-core domain {domain} for {item}")
        if row.get("status") != expected_status:
            fail(f"non-core domain status mismatch {item}: {row.get('status')} != {expected_status}")

    # Cross-check edge endpoints and directed links against parsed document contracts.
    # Upstream metadata is an equality contract, not a one-way containment check:
    # every CHK/R/DEC in TASK or WORK metadata must be represented by at least one
    # assigned execution edge, and every edge token must occur in both documents.
    metadata_fields = ("source_checks", "source_issues", "decisions")
    task_edge_metadata: dict[str, dict[str, set[str]]] = {
        task_id: {field: set() for field in metadata_fields}
        for task_id in EXPECTED_TASKS
    }
    work_edge_metadata: dict[str, dict[str, set[str]]] = {
        work_id: {field: set() for field in metadata_fields}
        for work_id in EXPECTED_WORKS
    }
    aggregate_steps: dict[str, set[str]] = {work_id: set() for work_id in EXPECTED_WORKS}
    aggregate_tests: dict[str, set[str]] = {work_id: set() for work_id in EXPECTED_WORKS}
    aggregate_evidences: dict[str, set[str]] = {work_id: set() for work_id in EXPECTED_WORKS}
    for row in core_edges:
        issue = row["issue_id"]
        work_id = row["work_id"]
        task_id = row["task_id"]
        if work_id not in works or task_id not in tasks:
            fail(f"unknown task/work edge for {issue}")
        linked_issues = {issue}
        parent_issue = row.get("parent_issue_id")
        if parent_issue is not None:
            linked_issues.add(parent_issue)
        edge_checks = set(row.get("checks", []))
        edge_decisions = set(row.get("decisions", []))
        unknown_checks = edge_checks - plan.checks
        unknown_decisions = edge_decisions - set(plan.decisions)
        if unknown_checks or unknown_decisions:
            fail(
                f"{issue} edge has unknown PLAN tokens: "
                f"checks={sorted(unknown_checks)} decisions={sorted(unknown_decisions)}"
            )
        if not linked_issues <= tasks[task_id].source_issues:
            fail(f"issue edge {sorted(linked_issues)} missing from {task_id} metadata")
        if not linked_issues <= works[work_id].source_issues:
            fail(f"issue edge {sorted(linked_issues)} missing from {work_id} metadata")
        if not edge_checks <= tasks[task_id].source_checks:
            fail(f"{issue} checks not contained by {task_id}")
        if not edge_checks <= works[work_id].source_checks:
            fail(f"{issue} checks not contained by {work_id}")
        if not edge_decisions <= tasks[task_id].decisions:
            fail(f"{issue} decisions not contained by {task_id}")
        if not edge_decisions <= works[work_id].decisions:
            fail(f"{issue} decisions not contained by {work_id}")
        for aggregate in (task_edge_metadata[task_id], work_edge_metadata[work_id]):
            aggregate["source_checks"].update(edge_checks)
            aggregate["source_issues"].update(linked_issues)
            aggregate["decisions"].update(edge_decisions)
        aggregate_steps[work_id].update(row.get("steps", []))
        aggregate_tests[work_id].update(row.get("local_tests", []))
        aggregate_evidences[work_id].update(row.get("evidences", []))

    for row in non_core:
        item = row["item_id"]
        edge_checks = set(row.get("checks", []))
        edge_decisions = set(row.get("decisions", []))
        unknown_checks = edge_checks - plan.checks
        unknown_decisions = edge_decisions - set(plan.decisions)
        if unknown_checks or unknown_decisions:
            fail(
                f"{item} edge has unknown PLAN tokens: "
                f"checks={sorted(unknown_checks)} decisions={sorted(unknown_decisions)}"
            )
        work_id = row.get("work_id")
        task_id = row.get("task_id")
        if work_id is None and task_id is None:
            continue
        if work_id not in works or task_id not in tasks:
            fail(f"unknown non-core task/work edge: {item}")
        if works[work_id].source_task_id != task_id:
            fail(
                f"{item} WORK source task authority: {work_id} declares "
                f"{works[work_id].source_task_id}, edge declares {task_id}"
            )
        if item not in tasks[task_id].source_issues:
            fail(f"non-core issue edge {item} missing from {task_id} metadata")
        if item not in works[work_id].source_issues:
            fail(f"non-core issue edge {item} missing from {work_id} metadata")
        if not edge_checks <= tasks[task_id].source_checks:
            fail(f"{item} checks not contained by {task_id}")
        if not edge_checks <= works[work_id].source_checks:
            fail(f"{item} checks not contained by {work_id}")
        if not edge_decisions <= tasks[task_id].decisions:
            fail(f"{item} decisions not contained by {task_id}")
        if not edge_decisions <= works[work_id].decisions:
            fail(f"{item} decisions not contained by {work_id}")
        for aggregate in (task_edge_metadata[task_id], work_edge_metadata[work_id]):
            aggregate["source_checks"].update(edge_checks)
            aggregate["source_issues"].add(item)
            aggregate["decisions"].update(edge_decisions)
        aggregate_steps[work_id].update(row.get("steps", []))
        aggregate_tests[work_id].update(row.get("local_tests", []))
        aggregate_evidences[work_id].update(row.get("evidences", []))

    for task_id, task in tasks.items():
        expected = task_edge_metadata[task_id]
        compare_sets(
            f"{task_id} source_checks edge equivalence",
            task.source_checks,
            expected["source_checks"],
        )
        compare_sets(
            f"{task_id} source_issues edge equivalence",
            task.source_issues,
            expected["source_issues"],
        )
        compare_sets(
            f"{task_id} decisions edge equivalence",
            task.decisions,
            expected["decisions"],
        )

    for work_id, work in works.items():
        expected = work_edge_metadata[work_id]
        compare_sets(
            f"{work_id} source_checks edge equivalence",
            work.source_checks,
            expected["source_checks"],
        )
        compare_sets(
            f"{work_id} source_issues edge equivalence",
            work.source_issues,
            expected["source_issues"],
        )
        compare_sets(
            f"{work_id} decisions edge equivalence",
            work.decisions,
            expected["decisions"],
        )

    for work_id, work in works.items():
        compare_sets(f"{work_id} STEP bidirectional", work.steps, aggregate_steps[work_id])
        compare_sets(f"{work_id} local TC bidirectional", work.local_tests, aggregate_tests[work_id])
        compare_sets(f"{work_id} EV bidirectional", work.evidences, aggregate_evidences[work_id])

    mappings = manifest.get("controlled_test_mappings", [])
    mapping_work_ids = [row.get("work_id") for row in mappings]
    compare_sets("controlled mapping WORK IDs", mapping_work_ids, EXPECTED_WORKS)
    if len(mapping_work_ids) != len(set(mapping_work_ids)):
        fail("duplicate controlled_test_mappings WORK row")
    mapped_controlled_union: set[str] = set()
    for row in mappings:
        work_id = row["work_id"]
        task_id = row["task_id"]
        if works[work_id].source_task_id != task_id:
            fail(
                f"{work_id} controlled-test mapping TASK {task_id} does not "
                f"match WORK source TASK {works[work_id].source_task_id}"
            )
        controlled = set(row.get("controlled_tc", []))
        local = set(row.get("local_tc", []))
        compare_sets(f"{work_id} mapping local TC", local, works[work_id].local_tests)
        compare_sets(f"{work_id} mapping controlled TC vs WORK", controlled, works[work_id].controlled_tests)
        compare_sets(f"{task_id} mapping controlled TC vs TASK", controlled, tasks[task_id].controlled_tests)
        mapped_controlled_union.update(controlled)
    active_plan_tests = plan.controlled_tests - plan.retired_tests
    compare_sets("controlled TC global coverage", mapped_controlled_union, active_plan_tests)
    if "TC-020" not in mapped_controlled_union:
        fail("TC-020 is not mapped")

    print(
        "TRACEABILITY_V3_PASS "
        f"plan_checks={len(plan.checks)} plan_tests={len(plan.controlled_tests)} "
        f"core_edges={len(core_edges)} non_core={len(non_core)} works={len(works)} "
        "metadata_equivalence=source_checks+source_issues+decisions "
        "authority_equivalence=report_checks+modplan_tasks+work_source_task"
    )


if __name__ == "__main__":
    try:
        main()
    except (ValidationError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"TRACEABILITY_V3_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2)
