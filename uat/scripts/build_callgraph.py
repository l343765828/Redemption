#!/usr/bin/env python3
"""Build a conservative static call/import graph for named production targets.

Static source evidence is classified as production, test, or demo.  A source
hit is never promoted to proven production reachability without a launch or
deployment reference, and runtime proof remains an explicit external blocker.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from collections import deque
from pathlib import Path
from typing import Iterable, Optional


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "evidence",
}
LAUNCH_SUFFIXES = {".sh", ".ps1", ".bat", ".cmd", ".yaml", ".yml", ".toml"}
LAUNCH_NAMES = {"dockerfile", "crontab", "procfile"}


def _excluded(path: Path) -> bool:
    lowered = path.name.lower()
    if "_bak" in lowered or "_final" in lowered:
        return True
    return any(part.lower() in SKIP_DIRS for part in path.parts)


def classify_path(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    if (
        "test" in parts
        or "tests" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
    ):
        return "test"
    if (
        "demo" in parts
        or "demos" in parts
        or "example" in parts
        or "examples" in parts
        or "sample" in parts
        or "samples" in parts
        or "demo" in name
        or "example" in name
    ):
        return "demo"
    return "production"


def module_name(relative_path: Path) -> str:
    parts = list(relative_path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _has_main_guard(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        if not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
            continue
        left, right = test.left, test.comparators[0]
        if (
            isinstance(left, ast.Name)
            and left.id == "__name__"
            and isinstance(right, ast.Constant)
            and right.value == "__main__"
        ):
            return True
    return False


def _imports(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _target_hits(tree: ast.AST, targets: set[str]) -> list[tuple[str, int, str]]:
    hits: set[tuple[str, int, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in targets:
                hits.add((node.name, node.lineno, "definition"))
        elif isinstance(node, ast.Name) and node.id in targets:
            hits.add((node.id, node.lineno, "name_reference"))
        elif isinstance(node, ast.Attribute) and node.attr in targets:
            hits.add((node.attr, node.lineno, "attribute_reference"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                leaf = alias.name.rsplit(".", 1)[-1]
                if leaf in targets:
                    hits.add((leaf, node.lineno, "import_reference"))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in targets:
                    hits.add((alias.name, node.lineno, "import_reference"))
    return sorted(hits)


def _git_commit(repo: Path) -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _reachable(imports: dict[str, set[str]], start: str, target: str) -> bool:
    queue = deque([start])
    seen = set()
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        if current == target:
            return True
        for imported in imports.get(current, set()):
            # An import may name a symbol below the actual module. Walk both
            # exact and longest known module prefixes.
            if imported in imports:
                queue.append(imported)
            parts = imported.split(".")
            while len(parts) > 1:
                parts.pop()
                candidate = ".".join(parts)
                if candidate in imports:
                    queue.append(candidate)
                    break
    return False


class CallgraphBuilder:
    def __init__(self, repo: Path, targets: Iterable[str]) -> None:
        self.repo = repo.resolve()
        self.targets = tuple(sorted(set(targets)))
        if not self.targets:
            raise ValueError("at least one target symbol is required")

    def _python_evidence(self) -> tuple[
        list[dict[str, object]], dict[str, set[str]], list[dict[str, object]]
    ]:
        references: list[dict[str, object]] = []
        import_graph: dict[str, set[str]] = {}
        entrypoints: list[dict[str, object]] = []
        target_set = set(self.targets)

        for path in sorted(self.repo.rglob("*.py")):
            relative = path.relative_to(self.repo)
            if _excluded(relative):
                continue
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(relative))
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                references.append(
                    {
                        "path": relative.as_posix(),
                        "classification": classify_path(relative),
                        "parse_error": type(exc).__name__,
                    }
                )
                continue
            module = module_name(relative)
            import_graph[module] = _imports(tree)
            if _has_main_guard(tree):
                entrypoints.append(
                    {
                        "module": module,
                        "path": relative.as_posix(),
                        "classification": classify_path(relative),
                        "evidence": "python_main_guard",
                    }
                )
            for target, line, kind in _target_hits(tree, target_set):
                references.append(
                    {
                        "target": target,
                        "module": module,
                        "path": relative.as_posix(),
                        "line": line,
                        "kind": kind,
                        "classification": classify_path(relative),
                    }
                )
        return references, import_graph, entrypoints

    def _deployment_evidence(self) -> list[dict[str, object]]:
        evidence = []
        needles = tuple(target.lower() for target in self.targets)
        for path in sorted(self.repo.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.repo)
            if _excluded(relative):
                continue
            if (
                path.suffix.lower() not in LAUNCH_SUFFIXES
                and path.name.lower() not in LAUNCH_NAMES
            ):
                continue
            try:
                if path.stat().st_size > 1024 * 1024:
                    continue
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, 1):
                lowered = line.lower()
                if any(needle in lowered for needle in needles):
                    evidence.append(
                        {
                            "path": relative.as_posix(),
                            "line": line_number,
                            "classification": classify_path(relative),
                            "evidence": "launch_text_reference",
                            "text": line.strip()[:300],
                        }
                    )
        return evidence

    def data(self) -> dict[str, object]:
        raw_references, imports, entrypoints = self._python_evidence()
        parse_errors = [item for item in raw_references if "parse_error" in item]
        references = [item for item in raw_references if "target" in item]
        deployment = self._deployment_evidence()
        by_class = {"production": [], "test": [], "demo": []}
        for item in references:
            by_class[str(item["classification"])].append(item)

        production_modules = {
            str(item["module"]) for item in by_class["production"]
        }
        source_paths = []
        for entry in entrypoints:
            if entry["classification"] != "production":
                continue
            for target_module in production_modules:
                if _reachable(imports, str(entry["module"]), target_module):
                    source_paths.append(
                        {
                            "entry_module": entry["module"],
                            "target_module": target_module,
                            "evidence": "static_import_path",
                        }
                    )

        if deployment and source_paths:
            confidence = "DEPLOYMENT_REFERENCE_AND_SOURCE_PATH"
        elif source_paths:
            confidence = "SOURCE_ENTRYPOINT_PATH_ONLY"
        elif by_class["production"]:
            confidence = "STATIC_REFERENCE_ONLY"
        else:
            confidence = "NO_PRODUCTION_STATIC_REFERENCE"

        blockers = [
            "fixed source archive SHA-256 not supplied to this static scan",
            "signed deployment manifest not supplied",
            "runtime trace not supplied",
        ]
        return {
            "schema_version": "1.0",
            "work_id": "WORK-PVAM-08",
            "artifact_status": "AVAILABLE",
            "validation_status": "BLOCKED",
            "reason": "static graph generated; production reachability needs external deployment and runtime evidence",
            "source_commit": _git_commit(self.repo),
            "targets": list(self.targets),
            "CALLGRAPH_CONFIDENCE": confidence,
            "references": by_class,
            "entrypoints": entrypoints,
            "static_import_paths": source_paths,
            "deployment_evidence": deployment,
            "parse_errors": parse_errors,
            "blockers": blockers,
        }

    def build(self, output: Path) -> dict[str, object]:
        data = self.data()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument(
        "--target", action="append", default=[], help="target symbol (repeatable)"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("uat/callgraph_manifest.json")
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    targets = args.target or ["TopologyMutationService"]
    data = CallgraphBuilder(args.repo, targets).build(args.output)
    counts = {key: len(value) for key, value in data["references"].items()}
    print(
        json.dumps(
            {
                "output": str(args.output),
                "CALLGRAPH_CONFIDENCE": data["CALLGRAPH_CONFIDENCE"],
                "reference_counts": counts,
                "validation_status": data["validation_status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
