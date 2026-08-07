#!/usr/bin/env python3
"""Validate PVAM version references, token uniqueness and package closure."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


HEX64 = re.compile(r"[0-9a-f]{64}")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TABLE_SEPARATOR = re.compile(r"^:?-{3,}:?$")
ROOT_SHA_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")

CANONICAL_MAIN_FILES = (
    "01_PLAN/Redemption_PV_Amount_Migration_d74_检查方案_v1.15.md",
    "02_REPORT/REPORT-PVAM-v1.5.md",
    "03_MODPLAN/MODPLAN-PVAM_v1.2_终稿修改方案套件/MODPLAN-PVAM_v1.2_总方案.md",
    "04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PLAN-PVAM_v1.3_施工总方案.md",
)
CANONICAL_CURRENT_INPUTS = {
    "audit_report": "06_HISTORY/全链路项目工程文档七轮终局审查与核验报告.md",
    "current_disposition": "00_B7-01-B7-06_真实性核验与反驳表.md",
    "prior_disposition": "06_HISTORY/00_S6-01-S6-06_真实性核验与反驳表.md",
}
CANONICAL_CURRENT_DELIVERIES = {
    "final_qa_report": {
        "path": "FINAL_QA_REPORT.md",
        "official_title": "PVAM 第九轮终局审计意见核验、定点修补与终稿交付 QA 报告",
        "file_role": "CURRENT_ROUND_FINAL_QA_REPORT",
    },
    "remediation_compilation": {
        "path": "PVAM_全链路第八轮定点修订全文.md",
        "official_title": "PVAM 全链路第八轮终局审计整改全文",
        "file_role": "CURRENT_ROUND_CUMULATIVE_REMEDIATION_COMPILATION",
    },
}
CANONICAL_TASK_GLOB = (
    "03_MODPLAN/MODPLAN-PVAM_v1.2_终稿修改方案套件/TASK-PVAM-*.md"
)
CANONICAL_WORK_GLOB = (
    "04_WORKPLAN/WORK-PLAN-PVAM_v1.3_终稿施工方案套件/WORK-PVAM-*.md"
)


@dataclass(frozen=True)
class HeadingInfo:
    level: int
    title: str
    line: int


@dataclass(frozen=True)
class MarkdownTable:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    line: int
    context: HeadingInfo | None


def fail(message: str) -> None:
    print(f"VERSION_REFERENCE_FAIL: {message}", file=sys.stderr)
    raise SystemExit(2)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        fail(f"missing or unsafe JSON: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON {path}: {exc}")
    if not isinstance(value, dict):
        fail(f"JSON must be object: {path}")
    return value


def read_markdown(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        fail(f"missing or unsafe Markdown: {path}")
    return path.read_text(encoding="utf-8")


def clean_cell(value: str) -> str:
    result = value.strip()
    pairs = (("`", "`"), ("**", "**"), ("__", "__"))
    changed = True
    while changed:
        changed = False
        for left, right in pairs:
            if result.startswith(left) and result.endswith(right) and len(result) > len(left) + len(right):
                result = result[len(left) : -len(right)].strip()
                changed = True
    return result


def visible_lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    fence: str | None = None
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        marker = None
        if stripped.startswith("```"):
            marker = "```"
        elif stripped.startswith("~~~"):
            marker = "~~~"
        if marker is not None:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is None:
            result.append((line_number, line))
    return result


def parse_headings(text: str) -> list[HeadingInfo]:
    result: list[HeadingInfo] = []
    for line_number, line in visible_lines(text):
        match = HEADING.fullmatch(line.strip())
        if not match:
            continue
        title = re.sub(r"\s+#+\s*$", "", match.group(2)).strip()
        result.append(HeadingInfo(len(match.group(1)), title, line_number))
    return result


def table_cells(line: str) -> tuple[str, ...] | None:
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
    return tuple(cells)


def is_separator(cells: tuple[str, ...] | None) -> bool:
    return bool(cells) and all(TABLE_SEPARATOR.fullmatch(cell) for cell in cells)


def parse_tables(text: str) -> list[MarkdownTable]:
    lines = visible_lines(text)
    headings = parse_headings(text)
    heading_by_line = {heading.line: heading for heading in headings}
    current_heading: HeadingInfo | None = None
    result: list[MarkdownTable] = []
    index = 0
    while index < len(lines):
        line_number, line = lines[index]
        if line_number in heading_by_line:
            current_heading = heading_by_line[line_number]
        header = table_cells(line)
        if index + 1 >= len(lines):
            break
        next_number, next_line = lines[index + 1]
        separator = table_cells(next_line) if next_number == line_number + 1 else None
        if not header or not is_separator(separator) or len(header) != len(separator):
            index += 1
            continue
        rows: list[tuple[str, ...]] = []
        cursor = index + 2
        expected_line = next_number + 1
        while cursor < len(lines) and lines[cursor][0] == expected_line:
            row = table_cells(lines[cursor][1])
            if row is None:
                break
            rows.append(row)
            cursor += 1
            expected_line += 1
        result.append(MarkdownTable(header, tuple(rows), line_number, current_heading))
        index = cursor
    return result


def require_unique_heading(
    text: str, *, level: int, title: str, label: str
) -> HeadingInfo:
    matches = [
        heading
        for heading in parse_headings(text)
        if heading.level == level and heading.title == title
    ]
    if len(matches) != 1:
        fail(f"{label}: expected one level-{level} heading {title!r}, got {len(matches)}")
    return matches[0]


def require_only_one_h1(text: str, expected: str, label: str) -> None:
    h1 = [heading for heading in parse_headings(text) if heading.level == 1]
    if len(h1) != 1 or h1[0].title != expected:
        fail(f"{label}: H1 mismatch: {[heading.title for heading in h1]}")


def require_leading_document_title(text: str, expected: str, label: str) -> None:
    """Require the first H1 to be the unique occurrence of the document title."""
    h1 = [heading for heading in parse_headings(text) if heading.level == 1]
    matching = [heading for heading in h1 if heading.title == expected]
    if not h1 or h1[0].title != expected or len(matching) != 1:
        fail(f"{label}: leading document title mismatch: {[heading.title for heading in h1]}")


def rows_in_context(
    text: str, *, heading_fragment: str, field: str
) -> list[tuple[str, ...]]:
    matches: list[tuple[str, ...]] = []
    for table in parse_tables(text):
        if table.context is None or heading_fragment not in table.context.title:
            continue
        for row in table.rows:
            if clean_cell(row[0]) == field:
                matches.append(row)
    return matches


def require_field(
    text: str,
    *,
    heading_fragment: str,
    field: str,
    expected: str,
    label: str,
    contains: bool = False,
) -> None:
    rows = rows_in_context(text, heading_fragment=heading_fragment, field=field)
    if len(rows) != 1 or len(rows[0]) < 2:
        fail(f"{label}: expected exactly one structured field {field!r}, got {len(rows)}")
    actual = clean_cell(rows[0][1])
    valid = expected in actual if contains else actual == expected
    if not valid:
        fail(f"{label}: structured field {field!r}={actual!r}, expected {expected!r}")


def require_revision(
    text: str, *, version: str, required_text: str, label: str
) -> None:
    revision_headings = [
        heading for heading in parse_headings(text) if "版本记录" in heading.title
    ]
    if len(revision_headings) != 1:
        fail(f"{label}: expected exactly one version-history heading, got {len(revision_headings)}")
    revision_heading = revision_headings[0]
    rows: list[tuple[str, ...]] = []
    for table in parse_tables(text):
        if table.context != revision_heading or clean_cell(table.header[0]) != "版本":
            continue
        rows.extend(row for row in table.rows if clean_cell(row[0]) == version)
    if len(rows) != 1:
        fail(f"{label}: expected exactly one {version} row in the version-history table")
    if required_text not in " | ".join(rows[0]):
        fail(f"{label}: {version} revision row does not contain {required_text!r}")


def expected_controlled_token_occurrences(
    root: Path, works: list[Path]
) -> list[dict[str, object]]:
    """Return the fixed allowlist of raw-text tokens that must be unique.

    Occurrence counting intentionally uses the complete Markdown source, including
    fenced blocks and comments. A controlled token therefore has exactly one raw
    occurrence and that occurrence must also satisfy its structural locator.
    """
    revision_location = {
        "kind": "revision_row",
        "required_text": "七轮 B7",
    }
    rules: list[dict[str, object]] = [
        {
            "path": CANONICAL_MAIN_FILES[2],
            "token": "v1.2-r8",
            "expected_count": 1,
            "location": {
                **revision_location,
                "version": "v1.2-r8",
            },
        },
        {
            "path": CANONICAL_MAIN_FILES[3],
            "token": "Traceability Manifest v3",
            "expected_count": 1,
            "location": {
                "kind": "heading",
                "level": 4,
                "title": "Traceability Manifest v3",
            },
        },
        {
            "path": CANONICAL_MAIN_FILES[3],
            "token": "v1.3-r8",
            "expected_count": 1,
            "location": {
                **revision_location,
                "version": "v1.3-r8",
            },
        },
        {
            "path": CANONICAL_MAIN_FILES[3],
            "token": "v1.3-r9",
            "expected_count": 1,
            "location": {
                "kind": "revision_row",
                "required_text": "九轮 P0-TRACE-CHAIN-09-01 / P1-WORK-INDEX-09-02",
                "version": "v1.3-r9",
            },
        },
    ]
    for path in works:
        rules.append(
            {
                "path": path.relative_to(root).as_posix(),
                "token": "v1.3-r8",
                "expected_count": 1,
                "location": {
                    **revision_location,
                    "version": "v1.3-r8",
                },
            }
        )
    rules.append(
        {
            "path": "05_CONTROL/AUTHORIZATION_STATUS-PVAM-v2.md",
            "token": "第八轮技术就绪声明",
            "expected_count": 1,
            "location": {
                "kind": "heading",
                "level": 2,
                "title": "第八轮技术就绪声明",
            },
        }
    )
    return rules


def validate_controlled_token_occurrences(
    root: Path, manifest: dict, works: list[Path]
) -> int:
    expected = expected_controlled_token_occurrences(root, works)
    rules = manifest.get("controlled_token_occurrences")
    if rules != expected:
        fail("controlled_token_occurrences must equal the fixed path/token allowlist")

    seen: set[tuple[str, str]] = set()
    for rule in rules:
        relative = safe_relative(rule.get("path"), "controlled token path")
        token = rule.get("token")
        if not isinstance(token, str) or not token:
            fail(f"{relative}: controlled token must be a non-empty string")
        identity = (relative, token)
        if identity in seen:
            fail(f"duplicate controlled token rule: {identity!r}")
        seen.add(identity)
        if rule.get("expected_count") != 1:
            fail(f"{relative}: controlled token expected_count must be exactly 1")

        text = read_markdown(root / relative)
        count = text.count(token)
        if count != 1:
            fail(
                f"{relative}: controlled token {token!r} expected exactly "
                f"1 raw occurrence, got {count}"
            )

        location = rule.get("location")
        if not isinstance(location, dict):
            fail(f"{relative}: controlled token location must be an object")
        kind = location.get("kind")
        if kind == "heading":
            level = location.get("level")
            title = location.get("title")
            if not isinstance(level, int) or not isinstance(title, str):
                fail(f"{relative}: invalid heading locator")
            if title != token:
                fail(f"{relative}: heading locator title must equal its token")
            require_unique_heading(
                text,
                level=level,
                title=title,
                label=f"controlled token {relative}",
            )
        elif kind == "revision_row":
            version = location.get("version")
            required_text = location.get("required_text")
            if version != token or not isinstance(required_text, str):
                fail(f"{relative}: invalid revision-row locator")
            require_revision(
                text,
                version=version,
                required_text=required_text,
                label=f"controlled token {relative}",
            )
        else:
            fail(f"{relative}: unsupported controlled token location kind {kind!r}")
    return len(rules)


def require_prefix_h1(text: str, prefix: str, label: str) -> None:
    h1 = [heading for heading in parse_headings(text) if heading.level == 1]
    if len(h1) != 1 or not h1[0].title.startswith(prefix + " "):
        fail(f"{label}: expected one H1 beginning with {prefix!r}")


def safe_relative(raw: object, label: str) -> str:
    if not isinstance(raw, str) or not raw:
        fail(f"{label}: path is required")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or "\\" in raw:
        fail(f"{label}: unsafe package-relative path {raw!r}")
    return raw


def validate_root_sha256(root: Path, document_manifest: dict) -> int:
    root_sha = root / "SHA256SUMS.txt"
    if not root_sha.is_file() or root_sha.is_symlink():
        fail("missing or unsafe root SHA256SUMS.txt")

    entries: dict[str, str] = {}
    for line_number, line in enumerate(root_sha.read_text(encoding="utf-8").splitlines(), 1):
        match = ROOT_SHA_LINE.fullmatch(line)
        if not match:
            fail(f"invalid root SHA256SUMS line {line_number}: {line!r}")
        digest, raw_path = match.groups()
        relative = safe_relative(raw_path, f"root SHA line {line_number}")
        if relative == "SHA256SUMS.txt" or relative in entries:
            fail(f"root SHA contains self-reference or duplicate path: {relative}")
        entries[relative] = digest

    actual_files: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            fail(f"package contains symlink: {path.relative_to(root).as_posix()}")
        if path.is_file():
            actual_files.add(path.relative_to(root).as_posix())
    expected_files = actual_files - {"SHA256SUMS.txt"}
    missing = sorted(expected_files - set(entries))
    extra = sorted(set(entries) - expected_files)
    if missing or extra:
        fail(f"root SHA file-set mismatch: missing={missing} extra={extra}")

    total = len(actual_files)
    excluding_root = len(expected_files)
    if document_manifest.get("package_file_count_total") != total:
        fail("DOCUMENT_MANIFEST package_file_count_total does not match physical files")
    if document_manifest.get("package_file_count_excluding_root_sha256") != excluding_root:
        fail("DOCUMENT_MANIFEST package_file_count_excluding_root_sha256 mismatch")
    if document_manifest.get("root_sha256_entry_count") != len(entries):
        fail("DOCUMENT_MANIFEST root_sha256_entry_count mismatch")

    for relative, expected in entries.items():
        actual = sha256(root / relative)
        if actual != expected:
            fail(f"root SHA mismatch for {relative}: {actual} != {expected}")
    return len(entries)


def validate_current_inputs(root: Path, manifest: dict) -> None:
    current = manifest.get("current_review_inputs")
    if current != CANONICAL_CURRENT_INPUTS:
        fail(
            "current review input roles/paths must equal the canonical mapping: "
            f"{CANONICAL_CURRENT_INPUTS!r}"
        )

    audit = read_markdown(root / CANONICAL_CURRENT_INPUTS["audit_report"])
    require_leading_document_title(
        audit,
        "全链路项目工程文档七轮终局审查与核验报告",
        "current audit report",
    )
    require_field(
        audit,
        heading_fragment="全链路项目工程文档七轮终局审查与核验报告",
        field="审查轮次",
        expected="第七轮终局闭环审查与交叉核验",
        label="current audit report",
    )

    disposition = read_markdown(root / CANONICAL_CURRENT_INPUTS["current_disposition"])
    require_only_one_h1(
        disposition,
        "B7-01～B7-06 七轮审计意见真实性核验与反驳表",
        "current disposition",
    )
    require_field(
        disposition,
        heading_fragment="B7-01～B7-06 七轮审计意见真实性核验与反驳表",
        field="处置编号",
        expected="DISPOSITION-PVAM-B7-v1",
        label="current disposition",
    )
    require_field(
        disposition,
        heading_fragment="B7-01～B7-06 七轮审计意见真实性核验与反驳表",
        field="审计来源",
        expected="《全链路项目工程文档七轮终局审查与核验报告》",
        label="current disposition",
    )

    prior = read_markdown(root / CANONICAL_CURRENT_INPUTS["prior_disposition"])
    require_only_one_h1(
        prior,
        "S6-01～S6-06 六轮审计意见真实性核验与反驳表",
        "prior disposition",
    )


def validate_current_deliveries(
    root: Path, manifest: dict, document_manifest: dict
) -> None:
    registered = manifest.get("current_round_delivery_files")
    if registered != CANONICAL_CURRENT_DELIVERIES:
        fail(
            "VERSION_REFERENCE_MANIFEST current_round_delivery_files must equal "
            f"{CANONICAL_CURRENT_DELIVERIES!r}"
        )
    if document_manifest.get("current_round_delivery_files") != CANONICAL_CURRENT_DELIVERIES:
        fail(
            "DOCUMENT_MANIFEST current_round_delivery_files must equal the "
            "canonical current-round delivery mapping"
        )

    final_qa_info = CANONICAL_CURRENT_DELIVERIES["final_qa_report"]
    final_qa = read_markdown(root / final_qa_info["path"])
    require_only_one_h1(
        final_qa,
        final_qa_info["official_title"],
        "current final QA report",
    )
    compilation_info = CANONICAL_CURRENT_DELIVERIES["remediation_compilation"]
    compilation = read_markdown(root / compilation_info["path"])
    require_leading_document_title(
        compilation,
        compilation_info["official_title"],
        "current remediation compilation",
    )


def validate_main_documents(root: Path, manifest: dict) -> tuple[list[Path], list[Path]]:
    if tuple(manifest.get("main_files", [])) != CANONICAL_MAIN_FILES:
        fail("main_files must match the four canonical role paths in order")
    if manifest.get("task_glob") != CANONICAL_TASK_GLOB:
        fail("task_glob is not canonical")
    if manifest.get("work_glob") != CANONICAL_WORK_GLOB:
        fail("work_glob is not canonical")

    plan_path, report_path, mod_path, work_total_path = [
        root / relative for relative in CANONICAL_MAIN_FILES
    ]
    plan = read_markdown(plan_path)
    report = read_markdown(report_path)
    mod = read_markdown(mod_path)
    work_total = read_markdown(work_total_path)

    require_only_one_h1(
        plan,
        "Redemption 项目检查方案（PV Amount Migration · 2475c6c4 基线）",
        "PLAN",
    )
    require_field(
        plan,
        heading_fragment="文档控制",
        field="文档编号",
        expected="PLAN-PVAM-v1.15",
        label="PLAN",
    )
    require_field(
        plan,
        heading_fragment="文档控制",
        field="文档版本",
        expected="v1.15",
        label="PLAN",
    )

    require_only_one_h1(report, "Redemption PV Amount Migration 复核报告 v1.5", "REPORT")
    require_field(
        report,
        heading_fragment="文档控制",
        field="报告编号",
        expected="REPORT-PVAM-v1.5",
        label="REPORT",
    )
    require_field(
        report,
        heading_fragment="文档控制",
        field="报告版本",
        expected="v1.5",
        label="REPORT",
    )

    require_only_one_h1(
        mod,
        "Redemption PV Amount Migration 本轮修改方案 v1.2（主控总方案）",
        "MODPLAN",
    )
    require_field(
        mod,
        heading_fragment="文档控制",
        field="文档编号",
        expected="MODPLAN-PVAM_v1.2",
        label="MODPLAN",
    )
    require_field(
        mod,
        heading_fragment="文档控制",
        field="文档版本",
        expected="v1.2",
        label="MODPLAN",
    )
    require_field(
        mod,
        heading_fragment="文档控制",
        field="七轮终局审计",
        expected="全链路项目工程文档七轮终局审查与核验报告.md",
        label="MODPLAN",
    )
    require_field(
        mod,
        heading_fragment="文档控制",
        field="B7-01～B7-06 当前处置",
        expected="00_B7-01-B7-06_真实性核验与反驳表.md",
        label="MODPLAN",
    )
    require_revision(mod, version="v1.2-r8", required_text="七轮 B7", label="MODPLAN")

    require_only_one_h1(
        work_total,
        "WORK-PLAN-PVAM_v1.3 Redemption PV Amount Migration 施工总方案",
        "WORK total",
    )
    require_field(
        work_total,
        heading_fragment="文档信息",
        field="文档编号",
        expected="WORK-PLAN-PVAM_v1.3",
        label="WORK total",
    )
    require_field(
        work_total,
        heading_fragment="文档信息",
        field="七轮审查",
        expected="B7-01～B7-06",
        label="WORK total",
        contains=True,
    )
    require_unique_heading(
        work_total,
        level=4,
        title="Traceability Manifest v3",
        label="WORK total",
    )
    require_revision(
        work_total, version="v1.3-r8", required_text="七轮 B7", label="WORK total"
    )

    tasks = sorted(root.glob(CANONICAL_TASK_GLOB))
    works = sorted(
        path for path in root.glob(CANONICAL_WORK_GLOB) if "完整套件" not in path.name
    )
    if len(tasks) != 9 or len(works) != 9:
        fail(f"expected 9 TASK and 9 WORK files, got {len(tasks)}/{len(works)}")

    for path in tasks:
        text = read_markdown(path)
        task_id = path.name.split("_", 1)[0]
        require_prefix_h1(text, task_id, path.name)
        require_field(
            text,
            heading_fragment="文档信息",
            field="任务编号",
            expected=task_id,
            label=path.name,
        )
        require_field(
            text,
            heading_fragment="文档信息",
            field="所属总方案",
            expected="MODPLAN-PVAM_v1.2",
            label=path.name,
        )

    for path in works:
        text = read_markdown(path)
        work_id = path.name.split("_", 1)[0]
        require_prefix_h1(text, work_id, path.name)
        require_field(
            text,
            heading_fragment="文档信息与追溯关系",
            field="施工任务编号",
            expected=work_id,
            label=path.name,
        )
        require_field(
            text,
            heading_fragment="文档信息与追溯关系",
            field="文档版本",
            expected="v1.3",
            label=path.name,
        )
        require_revision(
            text, version="v1.3-r8", required_text="七轮 B7", label=path.name
        )

    files = [plan_path, report_path, mod_path, work_total_path, *tasks, *works]
    for path in files:
        text = read_markdown(path)
        if "2475c6c4..2475c6c4" in text:
            fail(f"self compare in {path}")
        for alias in manifest["forbidden_active_control_aliases"]:
            if alias in text:
                fail(f"active obsolete control alias {alias} in {path}")
    return tasks, works


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest)
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != 5:
        fail("version manifest schema must be 5")

    expected_contract = {
        "markdown_structure": "h1+document_info_table+version_history_table",
        "current_input_path_policy": "fixed_role_allowlist",
        "shadow_token_policy": "reject",
        "occurrence_count_policy": "exactly_one_raw_occurrence_including_fences_and_comments",
        "authorization_round_heading": "第八轮技术就绪声明",
        "root_sha256_policy": "all_non_root_regular_files",
    }
    if manifest.get("structured_validation") != expected_contract:
        fail("VERSION_REFERENCE_MANIFEST structured_validation contract mismatch")

    tasks, works = validate_main_documents(root, manifest)
    validate_current_inputs(root, manifest)
    controlled_token_count = validate_controlled_token_occurrences(
        root, manifest, works
    )

    control = root / "05_CONTROL"
    for relative in manifest["canonical_control_files"]:
        path = root / safe_relative(relative, "canonical control file")
        if not path.is_file() or path.is_symlink():
            fail(f"missing canonical control file {relative}")
    for alias in manifest["forbidden_active_control_aliases"]:
        if (control / alias).exists():
            fail(f"superseded alias exists in active control directory: {alias}")

    for key, info in manifest.get("artifact_hashes", {}).items():
        if not isinstance(info, dict):
            fail(f"artifact {key} metadata must be an object")
        path = root / safe_relative(info.get("path"), f"artifact {key}")
        if not path.is_file() or path.is_symlink():
            fail(f"missing artifact {key}: {path}")
        actual = sha256(path)
        if actual != info.get("sha256"):
            fail(f"artifact hash mismatch {key}: {actual} != {info.get('sha256')}")

    root_readme = read_markdown(root / "README.md")
    require_only_one_h1(
        root_readme, "PVAM 全链路第九轮审计整改终稿套件", "root README"
    )
    if (
        "B7-01～B7-06" not in root_readme
        or "E8-01～E8-06" not in root_readme
        or "P0-TRACE-CHAIN-09-01" not in root_readme
        or "P1-WORK-INDEX-09-02" not in root_readme
    ):
        fail("root README round provenance is incomplete")

    auth = read_markdown(control / "AUTHORIZATION_STATUS-PVAM-v2.md")
    require_only_one_h1(auth, "PVAM 组织授权状态", "authorization status")
    require_unique_heading(
        auth,
        level=2,
        title="第八轮技术就绪声明",
        label="authorization status",
    )
    if "document_technical_readiness=APPROVED_FOR_CONSTRUCTION" not in auth:
        fail("authorization status lacks approved document technical readiness")

    document_manifest = read_json(root / "DOCUMENT_MANIFEST.json")
    validate_current_deliveries(root, manifest, document_manifest)
    registry_anchor = manifest["artifact_hashes"]["approved_commit_registry"]
    if document_manifest.get("approved_commit_registry") != registry_anchor:
        fail("DOCUMENT_MANIFEST registry trust anchor mismatch")
    if document_manifest.get("approved_commit_registry_sha256") != registry_anchor["sha256"]:
        fail("DOCUMENT_MANIFEST flat registry SHA mismatch")
    if document_manifest.get("document_technical_readiness") != "APPROVED_FOR_CONSTRUCTION":
        fail("DOCUMENT_MANIFEST document technical readiness mismatch")
    if document_manifest.get("code_audit_conclusion") != "REJECTED":
        fail("code audit conclusion must remain REJECTED")
    if document_manifest.get("validation_status") != "PENDING_TEST_ENV":
        fail("validation status must remain PENDING_TEST_ENV")
    if document_manifest.get("gate_c") != "OPEN":
        fail("Gate C must remain OPEN")

    root_sha_entries = validate_root_sha256(root, document_manifest)
    print(
        f"VERSION_REFERENCE_PASS files={4 + len(tasks) + len(works)} "
        f"controls={len(manifest['canonical_control_files'])} "
        f"artifacts={len(manifest['artifact_hashes'])} "
        f"controlled_tokens={controlled_token_count} "
        f"current_deliveries={len(CANONICAL_CURRENT_DELIVERIES)} "
        f"root_sha_entries={root_sha_entries} structured=true"
    )


if __name__ == "__main__":
    main()
