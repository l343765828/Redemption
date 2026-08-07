#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


class GovernanceError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise GovernanceError(message)


def read(path: Path) -> str:
    if not path.is_file():
        fail(f"missing file: {path}")
    return path.read_text(encoding="utf-8")

AC_ID = re.compile(r"AC-[0-9]{2}")
TASK_ID = re.compile(r"TASK-PVAM-(?:07A|07B|0[1-8])(?![0-9A-Z])")
WORK_ID = re.compile(r"WORK-PVAM-(?:07A|07B|0[1-8])(?![0-9A-Z])")
CORE_ISSUE_ID = re.compile(r"\bR-\d{3}(?:A|B)?\b")
NON_CORE_ISSUE_ID = re.compile(
    r"\b(?:RISK|UV|OPT)-\d{3}\b|\bGAP-[A-Z0-9-]+\b|\bFIX-\d{3}\b"
)
DECISION_ID = re.compile(r"\bDEC-\d{3}\b")
TABLE_SEPARATOR = re.compile(r"^:?-{3,}:?$")


def table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    body = stripped[1:-1]
    cells: list[str] = []
    current: list[str] = []
    code_delimiter: int | None = None
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body) and body[index + 1] == "|":
            current.extend((char, "|"))
            index += 2
            continue
        if char == "`":
            end = index
            while end < len(body) and body[end] == "`":
                end += 1
            run = end - index
            if code_delimiter is None:
                code_delimiter = run
            elif code_delimiter == run:
                code_delimiter = None
            current.extend("`" * run)
            index = end
            continue
        if char == "|" and code_delimiter is None:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return cells


def is_separator_row(cells: list[str] | None) -> bool:
    return bool(cells) and all(TABLE_SEPARATOR.fullmatch(cell) for cell in cells)


def expand_numeric_ranges(text: str) -> str:
    pattern = re.compile(
        r"(?P<prefix>(?:RISK|UV|OPT|R|DEC)-)"
        r"(?P<start>\d{3})(?:～|~)"
        r"(?:(?P<prefix2>(?:RISK|UV|OPT|R|DEC)-))?"
        r"(?P<end>\d{3})"
    )

    def replace(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        if (match.group("prefix2") or prefix) != prefix:
            return match.group(0)
        start = int(match.group("start"))
        end = int(match.group("end"))
        if end < start or end - start > 999:
            return match.group(0)
        return "、".join(f"{prefix}{value:03d}" for value in range(start, end + 1))

    previous = None
    current = text
    while current != previous:
        previous = current
        current = pattern.sub(replace, current)
    return current


def token_set(text: str, pattern: re.Pattern[str]) -> set[str]:
    return set(pattern.findall(expand_numeric_ranges(text)))


def metadata_value(text: str, label: str, document: str) -> str:
    matches: list[str] = []
    for line in text.splitlines():
        cells = table_cells(line)
        if cells and cells[0].strip(" `") == label:
            if len(cells) < 2:
                fail(f"{document}: metadata row {label} has no value")
            matches.append(cells[1])
    if len(matches) != 1:
        fail(f"{document}: expected one metadata row {label}, got {len(matches)}")
    return matches[0]


def unique_token(value: str, pattern: re.Pattern[str], label: str) -> str:
    matches = pattern.findall(expand_numeric_ranges(value))
    if len(matches) != 1:
        fail(f"{label}: expected exactly one controlled ID, got {matches}")
    return matches[0]


def extract_work_source_contract(text: str, work_id: str) -> dict[str, object]:
    source_issues = metadata_value(text, "来源问题", work_id)
    return {
        "source_task_id": unique_token(
            metadata_value(text, "来源修改任务", work_id),
            TASK_ID,
            f"{work_id} 来源修改任务",
        ),
        "source_issues": token_set(source_issues, CORE_ISSUE_ID)
        | token_set(source_issues, NON_CORE_ISSUE_ID),
        "decisions": token_set(
            metadata_value(text, "关联决策", work_id), DECISION_ID
        ),
    }


def extract_work_index(text: str) -> dict[str, dict[str, object]]:
    heading = "### 4.1 专项施工任务索引"
    lines = text.splitlines()
    headings = [index for index, line in enumerate(lines) if line.strip() == heading]
    if len(headings) != 1:
        fail(f"WORK total: expected one {heading!r} heading, got {len(headings)}")
    start = headings[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        if re.match(r"^#{1,3}\s+", lines[index]):
            end = index
            break

    required = ["顺序", "施工任务", "来源修改任务", "来源问题", "关联决策"]
    candidates: list[tuple[list[str], int]] = []
    for index in range(start, max(start, end - 1)):
        header = table_cells(lines[index])
        separator = table_cells(lines[index + 1])
        if not header or not is_separator_row(separator):
            continue
        if all(name in header for name in required):
            candidates.append((header, index + 2))
    if len(candidates) != 1:
        fail(f"WORK total: expected one §4.1 index table, got {len(candidates)}")

    header, cursor = candidates[0]
    columns = {name: header.index(name) for name in required}
    result: dict[str, dict[str, object]] = {}
    while cursor < end:
        cells = table_cells(lines[cursor])
        if cells is None:
            break
        if len(cells) != len(header):
            fail(f"WORK total: malformed §4.1 row at line {cursor + 1}")
        work_id = unique_token(cells[columns["施工任务"]], WORK_ID, "WORK total index")
        if work_id in result:
            fail(f"WORK total: duplicate §4.1 row {work_id}")
        issues_cell = cells[columns["来源问题"]]
        result[work_id] = {
            "source_task_id": unique_token(
                cells[columns["来源修改任务"]],
                TASK_ID,
                f"WORK total {work_id} source TASK",
            ),
            "source_issues": token_set(issues_cell, CORE_ISSUE_ID)
            | token_set(issues_cell, NON_CORE_ISSUE_ID),
            "decisions": token_set(cells[columns["关联决策"]], DECISION_ID),
        }
        cursor += 1
    return result


def compare_work_index_field(
    work_id: str,
    field: str,
    index_value: object,
    document_value: object,
    contract_value: object,
) -> None:
    if field == "source_task_id":
        if not (
            isinstance(index_value, str)
            and index_value == document_value
            and index_value == contract_value
        ):
            fail(
                f"WORK total §4.1 {work_id}.{field} mismatch: "
                f"index={index_value!r} document={document_value!r} "
                f"contract={contract_value!r}"
            )
        return
    index_set = set(index_value) if isinstance(index_value, (set, list)) else set()
    document_set = set(document_value) if isinstance(document_value, (set, list)) else set()
    contract_set = set(contract_value) if isinstance(contract_value, list) else set()
    if index_set != document_set or index_set != contract_set:
        fail(
            f"WORK total §4.1 {work_id}.{field} mismatch: "
            f"index={sorted(index_set)} document={sorted(document_set)} "
            f"contract={sorted(contract_set)}"
        )


def extract_ac_contracts(text: str, label: str) -> dict[str, tuple[str, str]]:
    """Return AC_ID -> (source text, environment) from the canonical AC table."""
    lines = text.splitlines()
    tables: list[dict[str, tuple[str, str]]] = []
    for index in range(len(lines) - 2):
        header = table_cells(lines[index])
        separator = table_cells(lines[index + 1])
        if not header or not is_separator_row(separator):
            continue
        if header[0] not in {"AC", "验收编号"} or "环境" not in header:
            continue
        source_names = ["验收标准", "来源TASK验收项"]
        source_indexes = [header.index(name) for name in source_names if name in header]
        if len(source_indexes) != 1:
            fail(f"{label}: AC table must have exactly one source-text column")
        source_index = source_indexes[0]
        environment_index = header.index("环境")
        table: dict[str, tuple[str, str]] = {}
        cursor = index + 2
        while cursor < len(lines):
            cells = table_cells(lines[cursor])
            if cells is None:
                break
            if len(cells) != len(header):
                fail(f"{label}: malformed AC table row at line {cursor + 1}")
            ac_id = cells[0].strip("`")
            if AC_ID.fullmatch(ac_id):
                if ac_id in table:
                    fail(f"{label}: duplicate AC row {ac_id}")
                source_text = cells[source_index]
                environment = cells[environment_index].strip("`")
                if not source_text or not environment:
                    fail(f"{label}: empty AC source/environment for {ac_id}")
                table[ac_id] = (source_text, environment)
            cursor += 1
        if table:
            tables.append(table)
    if len(tables) != 1:
        fail(f"{label}: expected exactly one AC contract table, got {len(tables)}")
    return tables[0]


def validate_work01_ac06_detail(text: str) -> None:
    heading = "### 10.1 AC-06 实施细化 / 派生测试"
    lines = text.splitlines()
    indexes = [i for i, line in enumerate(lines) if line.strip() == heading]
    if len(indexes) != 1:
        fail(f"WORK-PVAM-01: expected exactly one dedicated AC-06 detail section, got {len(indexes)}")
    start = indexes[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^#{1,3}\s+", lines[index]):
            end = index
            break
    body = "\n".join(lines[start:end])
    for token in ('Decimal("sNaN")', 'Decimal("Infinity")', 'Decimal("-Infinity")'):
        if token not in body:
            fail(f"WORK-PVAM-01: dedicated AC-06 detail section missing {token}")

    tc_prefix = "| TC-PVAM-01-02 |"
    ev_prefix = "| EV-PVAM-01-06 |"
    if not any(line.strip().startswith(tc_prefix) for line in lines):
        fail("WORK-PVAM-01: AC-06 derived test lacks TC-PVAM-01-02 mapping")
    if not any(line.strip().startswith(ev_prefix) for line in lines):
        fail("WORK-PVAM-01: AC-06 derived test lacks EV-PVAM-01-06 mapping")

    derived_tokens = ("sNaN", "-Infinity", "±Infinity")
    for index, line in enumerate(lines):
        if not any(token in line for token in derived_tokens):
            continue
        in_detail = start <= index < end
        in_mapping = line.strip().startswith((tc_prefix, ev_prefix))
        if not in_detail and not in_mapping:
            fail(
                "WORK-PVAM-01: derived AC-06 token appears outside the dedicated "
                f"section or its TC/EV mappings at line {index + 1}"
            )

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    control = root / "05_CONTROL"
    mod_dir = root / "03_MODPLAN/MODPLAN-PVAM_v1.2_终稿修改方案套件"
    work_dir = root / "04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件"

    package = json.loads(read(root / "DOCUMENT_MANIFEST.json"))
    expected = {
        "document_status": "DRAFT",
        "document_technical_readiness": "APPROVED_FOR_CONSTRUCTION",
        "authorization_status": "PENDING_ORGANIZATIONAL_APPROVAL",
        "implementation_status": "BLOCKED",
        "validation_status": "PENDING_TEST_ENV",
        "code_audit_conclusion": "REJECTED",
        "dec_013": "OPEN",
        "gate_c": "OPEN",
    }
    for key, value in expected.items():
        if package.get(key) != value:
            fail(f"root manifest {key}={package.get(key)!r}, expected {value!r}")

    work_package = json.loads(read(work_dir / "DOCUMENT_MANIFEST.json"))
    if work_package.get("document_technical_readiness") != "APPROVED_FOR_CONSTRUCTION":
        fail("WORK package document technical readiness mismatch")
    if work_package.get("authorization_status") != "PENDING_ORGANIZATIONAL_APPROVAL":
        fail("WORK package authorization status must remain pending")

    for name in ["TRACEABILITY_MANIFEST.json", "TRACEABILITY_MANIFEST.md", "validate_traceability_v3.py"]:
        if not (control / name).is_file():
            fail(f"missing canonical control file: {name}")
    for name in ["TRACEABILITY_MANIFEST.v2.json", "TRACEABILITY_MANIFEST.v2.md", "validate_traceability_v2.py"]:
        if (control / name).exists():
            fail(f"superseded active alias remains: {name}")

    work_docs = sorted(p for p in work_dir.glob("WORK-PVAM-*.md") if "完整套件" not in p.name)
    if len(work_docs) != 9:
        fail(f"expected 9 WORK docs, got {len(work_docs)}")
    for path in work_docs:
        text = read(path)
        if "| 文档版本 | `v1.3` |" not in text:
            fail(f"WORK metadata version mismatch: {path.name}")
        if "来源于待组织批准的 `TASK-PVAM-" not in text:
            fail(f"pending-approval source wording missing: {path.name}")
        for token in [
            "--parent-commit \"$PARENT_COMMIT_SHA\"",
            "--parent-tree \"$PARENT_TREE_SHA\"",
            "--parent-provenance \"$PARENT_PROVENANCE_JSON\"",
            "05_CONTROL/check_baseline_preflight.sh",
            "05_CONTROL/validate_work_dev.sh",
        ]:
            if token not in text:
                fail(f"{path.name}: missing canonical DEV token {token}")

    task_docs = sorted(mod_dir.glob("TASK-PVAM-*.md"))
    if len(task_docs) != 9:
        fail(f"expected 9 TASK docs, got {len(task_docs)}")
    task_map = {path.name.split("_")[0].replace("TASK-", "WORK-"): path for path in task_docs}
    work_map = {path.name.split("_")[0]: path for path in work_docs}
    if set(task_map) != set(work_map):
        fail(f"TASK/WORK document ID mismatch: {sorted(set(task_map) ^ set(work_map))}")

    traceability = json.loads(read(control / "TRACEABILITY_MANIFEST.json"))
    work_contracts = traceability.get("work_contracts", {})
    work_index = extract_work_index(
        read(work_dir / "WORK-PLAN-PVAM_v1.3_施工总方案.md")
    )
    if set(work_contracts) != set(work_map) or set(work_index) != set(work_map):
        fail(
            "WORK total §4.1/document/contract ID mismatch: "
            f"index={sorted(work_index)} documents={sorted(work_map)} "
            f"contracts={sorted(work_contracts)}"
        )
    for work_id, path in sorted(work_map.items()):
        document_source = extract_work_source_contract(read(path), work_id)
        index_source = work_index[work_id]
        contract_source = work_contracts[work_id]
        for field in ("source_task_id", "source_issues", "decisions"):
            compare_work_index_field(
                work_id,
                field,
                index_source.get(field),
                document_source.get(field),
                contract_source.get(field),
            )

    total_ac = 0
    for work_id in sorted(work_map):
        task_ac = extract_ac_contracts(read(task_map[work_id]), f"{work_id} TASK")
        work_ac = extract_ac_contracts(read(work_map[work_id]), f"{work_id} WORK")
        task_triples = {(ac_id, *contract) for ac_id, contract in task_ac.items()}
        work_triples = {(ac_id, *contract) for ac_id, contract in work_ac.items()}
        if task_triples != work_triples:
            missing = sorted(task_triples - work_triples)
            extra = sorted(work_triples - task_triples)
            fail(
                f"{work_id} source AC triple mismatch: "
                f"missing_from_work={missing} extra_in_work={extra}"
            )
        total_ac += len(task_ac)
    if total_ac != 100:
        fail(f"expected 100 source AC rows, got {total_ac}")

    validate_work01_ac06_detail(read(work_map["WORK-PVAM-01"]))

    for script in sorted(control.glob("selftest_*.sh")):
        script_text = read(script)
        if "ensure_temp_root.sh" not in script_text or "pvam_prepare_tmpdir" not in script_text:
            fail(f"independent selftest lacks temp-root preflight: {script.name}")

    total = read(work_dir / "WORK-PLAN-PVAM_v1.3_施工总方案.md")
    row_a = "CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003 | R-012A"
    row_b = "CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003 | R-012B"
    if row_a not in total or row_b not in total:
        fail("WORK total R-012A/B CHK edges are incomplete")
    for token in ["validate_parent_provenance.py", "validate_work_patch.sh", "validate_work_dev.sh"]:
        if token not in total:
            fail(f"WORK total missing control entry: {token}")

    work08 = read(work_dir / "WORK-PVAM-08_UAT准入与证据治理.md")
    if 'manifest = {"status": "BLOCKED"' in work08:
        fail("WORK-08 still uses unqualified status=BLOCKED")
    if 'manifest = {"validation_status": "BLOCKED"' not in work08:
        fail("WORK-08 validation_status contract missing")
    if "artifact_status=PENDING" not in work08 or "validation_status=PENDING_TEST_ENV" not in work08:
        fail("WORK-08 status domains are incomplete")

    task08 = read(mod_dir / "TASK-PVAM-08_风险延期与UAT准入证据包.md")
    if "artifact_status=PENDING" not in task08 or "validation_status=PENDING_TEST_ENV" not in task08:
        fail("TASK-08 status domains are incomplete")

    work07b = read(work_dir / "WORK-PVAM-07B_事件路由与Stream保留.md")
    for weak in ["XLEN 门禁通过才可恢复固定 MAXLEN", "无 GHOST_IN_DOUBT 且 XLEN 门禁通过"]:
        if weak in work07b:
            fail(f"weak fixed MAXLEN rollback permission remains: {weak}")
    for strong in ["默认回滚**禁止**恢复", "运维负责人和架构负责人共同签署", "六类"]:
        if strong not in work07b:
            fail(f"strong fixed MAXLEN exception gate missing: {strong}")

    active_dirs = [root / "01_PLAN", root / "02_REPORT", mod_dir, work_dir]
    active_files = [root / "README.md", root / "FINAL_QA_REPORT.md"]
    for directory in active_dirs:
        active_files.extend(directory.glob("*.md"))
    for path in active_files:
        if not path.is_file() or "完整套件" in path.name:
            continue
        text = read(path)
        for obsolete in ["TRACEABILITY_MANIFEST.v2.json", "TRACEABILITY_MANIFEST.v2.md", "validate_traceability_v2.py"]:
            if obsolete in text:
                fail(f"active v2 control reference in {path}: {obsolete}")

    auth = read(control / "AUTHORIZATION_STATUS-PVAM-v2.md")
    if "authorization_status=PENDING_ORGANIZATIONAL_APPROVAL" not in auth:
        fail("authorization pending state missing")

    scope = json.loads(read(control / "WORK_SCOPE_ALLOWLIST.json"))
    if scope.get("schema_version") != 3:
        fail("scope schema_version must be 3")
    if "User/GlobalRecalculationService.py" not in scope["works"]["WORK-PVAM-02"]["exact"]:
        fail("WORK-02 allowlist missing GlobalRecalculationService.py")
    work08_scope = scope["works"]["WORK-PVAM-08"]
    if "evidence/manifest.schema.json" not in work08_scope["exact"]:
        fail("WORK-08 allowlist missing evidence/manifest.schema.json")
    if any("evidence_schema" in item for item in work08_scope.get("exact", []) + work08_scope.get("prefixes", [])):
        fail("obsolete evidence_schema path remains")

    print(
        f"DOCUMENT_GOVERNANCE_PASS work_docs={len(work_docs)} "
        f"source_ac_triples={total_ac} work_index_rows={len(work_index)}"
    )


if __name__ == "__main__":
    try:
        main()
    except (GovernanceError, KeyError, json.JSONDecodeError) as exc:
        print(f"DOCUMENT_GOVERNANCE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2)
