#!/usr/bin/env python3
"""Capture a local-only Architecture + Git planning baseline.

The script is intentionally fail-closed. It never invokes a Git remote command,
refuses partial/promisor repositories that could lazy-fetch missing objects, and
captures HEAD, index, tracked worktree, and untracked state independently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Iterable

SCHEMA = "architecture-to-plan-baseline-v2"
CHUNK = 1024 * 1024

# Safe, non-executable Git configuration that materially affects ordinary
# working-tree/status semantics. Executable extension points such as filter.*,
# fsmonitor, hooks, credential helpers, aliases, and remote configuration are
# intentionally never copied into the sanitized status environment.
SAFE_STATUS_CONFIG_KEYS = (
    "core.autocrlf",
    "core.eol",
    "core.safecrlf",
    "core.symlinks",
    "core.ignorecase",
    "core.precomposeunicode",
    "core.filemode",
    "core.checkstat",
)


class CaptureError(RuntimeError):
    def __init__(self, code: str, message: str, *, path: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path

    def as_dict(self) -> dict[str, str]:
        out = {"code": self.code, "message": self.message}
        if self.path is not None:
            out["path"] = self.path
        return out


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(CHUNK), b""):
                total += len(chunk)
                h.update(chunk)
    except OSError as exc:
        raise CaptureError(
            "FILE_READ_FAILED",
            f"failed to read file: {type(exc).__name__}: {exc}",
            path=str(path),
        ) from exc
    return h.hexdigest(), total


def emit_json(payload: dict) -> None:
    # ASCII-only JSON stays machine-readable even when the host stdout code page
    # is not UTF-8 (for example legacy Windows PowerShell pipelines).
    raw = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def _clean_git_env() -> dict[str, str]:
    env = os.environ.copy()
    # Remove variables that can redirect repository identity, index/object
    # sources, executable/config roots, or credential/network behavior.
    exact_remove = {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_PREFIX",
        "GIT_NAMESPACE",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_EXEC_PATH",
        "GIT_TEMPLATE_DIR",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_GLOBAL",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_ASKPASS",
        "SSH_ASKPASS",
    }
    for key in list(env):
        if key in exact_remove or key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
            env.pop(key, None)

    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_ATTR_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    # Supported by current Git versions. Partial/promisor repositories are also
    # rejected explicitly before object-demanding operations, so this is defense
    # in depth rather than the only remote-access control.
    env["GIT_NO_LAZY_FETCH"] = "1"
    return env


def _config_read_git_env() -> dict[str, str]:
    """Return an environment for read-only effective Git config inspection.

    Repository identity/config redirection variables are removed, but normal
    system/global/local/worktree config precedence is retained so we can copy a
    small whitelist of non-executable status semantics into the throwaway Git
    directory. `git config` only reads configuration; it does not execute filter
    drivers, hooks, credential helpers, or remote transports.
    """
    env = os.environ.copy()
    exact_remove = {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_PREFIX",
        "GIT_NAMESPACE",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_EXEC_PATH",
        "GIT_TEMPLATE_DIR",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_ATTR_NOSYSTEM",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_ASKPASS",
        "SSH_ASKPASS",
    }
    for key in list(env):
        if key in exact_remove or key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
            env.pop(key, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    return env


class LocalGit:
    def __init__(self, repo: Path):
        self.repo = repo
        self._tmp = tempfile.TemporaryDirectory(prefix="architecture-to-plan-git-")
        self.empty_hooks = Path(self._tmp.name) / "hooks"
        self.empty_hooks.mkdir()
        self.env = _clean_git_env()

    def close(self) -> None:
        self._tmp.cleanup()

    def _cmd(self, *args: str) -> list[str]:
        return [
            "git",
            # 仅为当前 Git 子进程信任已解析的目标仓库，兼容隔离账号且不修改全局配置。
            "-c",
            f"safe.directory={self.repo}",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"core.hooksPath={self.empty_hooks}",
            "-C",
            str(self.repo),
            *args,
        ]

    def run(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        optional: bool = False,
    ) -> bytes | None:
        cmd = self._cmd(*args)
        try:
            p = subprocess.run(
                cmd,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.env,
                check=False,
            )
        except OSError as exc:
            raise CaptureError("GIT_EXEC_FAILED", f"failed to execute Git: {exc}") from exc
        if p.returncode != 0:
            if optional:
                return None
            err = p.stderr.decode("utf-8", errors="replace").strip()
            raise CaptureError("GIT_COMMAND_FAILED", f"Git command failed ({' '.join(cmd)}): {err}")
        return p.stdout

    def _run_config_read(self, *args: str, optional: bool = False) -> bytes | None:
        """Read effective Git config without inheriting repository redirect env."""
        cmd = self._cmd(*args)
        try:
            p = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_config_read_git_env(),
                check=False,
            )
        except OSError as exc:
            raise CaptureError("GIT_EXEC_FAILED", f"failed to execute Git config read: {exc}") from exc
        if p.returncode != 0:
            if optional:
                return None
            err = p.stderr.decode("utf-8", errors="replace").strip()
            raise CaptureError("GIT_COMMAND_FAILED", f"Git config read failed ({' '.join(cmd)}): {err}")
        return p.stdout

    def _effective_config_value(self, key: str, *, path_value: bool = False) -> str | None:
        args = ["config"]
        if path_value:
            args.append("--path")
        args.extend(["--get", key])
        raw = self._run_config_read(*args, optional=True)
        if not raw:
            return None
        return raw.decode("utf-8", errors="surrogateescape").rstrip("\r\n")

    @staticmethod
    def _read_optional_bytes(path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CaptureError(
                "FILE_READ_FAILED",
                f"failed to read Git semantic file: {type(exc).__name__}: {exc}",
                path=str(path),
            ) from exc

    def capture_status_semantics(self) -> dict[str, object]:
        """Snapshot legitimate non-executable Git status/ignore semantics.

        The sanitized status process must behave like ordinary Git for benign
        line-ending, symlink, file-mode, case, and ignore configuration while
        still never loading executable filter/fsmonitor/hook configuration.
        """
        common_dir_raw = self.run("rev-parse", "--git-common-dir")
        assert common_dir_raw is not None
        common_dir_text = common_dir_raw.decode("utf-8", errors="surrogateescape").strip()
        common_dir = Path(common_dir_text)
        if not common_dir.is_absolute():
            common_dir = (self.repo / common_dir).resolve()
        else:
            common_dir = common_dir.resolve()

        config_values: dict[str, str] = {}
        for key in SAFE_STATUS_CONFIG_KEYS:
            value = self._effective_config_value(key)
            if value is not None:
                config_values[key] = value

        excludes_path_text = self._effective_config_value("core.excludesFile", path_value=True)
        attributes_path_text = self._effective_config_value("core.attributesFile", path_value=True)

        def resolve_optional_config_path(value: str | None) -> Path | None:
            if value is None or value == "":
                return None
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                candidate = self.repo / candidate
            return candidate.resolve(strict=False)

        excludes_path = resolve_optional_config_path(excludes_path_text)
        attributes_path = resolve_optional_config_path(attributes_path_text)
        info_exclude = self._read_optional_bytes(common_dir / "info" / "exclude")
        info_attributes = self._read_optional_bytes(common_dir / "info" / "attributes")
        global_excludes = self._read_optional_bytes(excludes_path) if excludes_path is not None else None
        global_attributes = self._read_optional_bytes(attributes_path) if attributes_path is not None else None

        material = bytearray(b"ATP-STATUS-SEMANTICS-V1\0")
        for key, value in sorted(config_values.items()):
            key_b = key.encode("utf-8")
            value_b = value.encode("utf-8", errors="surrogateescape")
            material += len(key_b).to_bytes(4, "big") + key_b
            material += len(value_b).to_bytes(8, "big") + value_b
        for label, payload in (
            (b"INFO_EXCLUDE", info_exclude),
            (b"INFO_ATTRIBUTES", info_attributes),
            (b"GLOBAL_EXCLUDES", global_excludes),
            (b"GLOBAL_ATTRIBUTES", global_attributes),
        ):
            material += len(label).to_bytes(4, "big") + label
            if payload is None:
                material += (0).to_bytes(1, "big")
            else:
                material += (1).to_bytes(1, "big")
                material += len(payload).to_bytes(8, "big") + payload

        return {
            "config_values": config_values,
            "info_exclude": info_exclude,
            "info_attributes": info_attributes,
            "global_excludes": global_excludes,
            "global_attributes": global_attributes,
            "fingerprint": sha256_bytes(bytes(material)),
        }

    def run_sanitized_status(
        self,
        head_sha: str,
        semantics: dict[str, object],
        tracked_paths: list[str],
    ) -> tuple[bytes, bytes]:
        """Collect status/untracked evidence with safe ordinary Git semantics.

        A throwaway Git directory prevents repository-defined executable filters,
        hooks, fsmonitor, include.path, credentials, and remote configuration from
        affecting the subprocess. A narrow snapshot of non-executable Git
        semantics is copied in so legitimate `core.autocrlf`, `core.symlinks`,
        repository info excludes/attributes, and global excludes/attributes keep
        ordinary clean/dirty behavior.
        """
        git_dir_raw = self.run("rev-parse", "--absolute-git-dir")
        common_dir_raw = self.run("rev-parse", "--git-common-dir")
        assert git_dir_raw is not None and common_dir_raw is not None

        git_dir = Path(git_dir_raw.decode("utf-8", errors="surrogateescape").strip())
        common_dir_text = common_dir_raw.decode("utf-8", errors="surrogateescape").strip()
        common_dir = Path(common_dir_text)
        if not common_dir.is_absolute():
            common_dir = (self.repo / common_dir).resolve()
        else:
            common_dir = common_dir.resolve()

        index_path = git_dir / "index"
        object_dir = common_dir / "objects"
        if not index_path.is_file():
            raise CaptureError(
                "GIT_INDEX_MISSING",
                "Git index file is unavailable for sanitized status collection",
                path=str(index_path),
            )
        if not object_dir.is_dir():
            raise CaptureError(
                "GIT_OBJECT_DIRECTORY_MISSING",
                "Git object directory is unavailable for sanitized status collection",
                path=str(object_dir),
            )

        status_root = Path(tempfile.mkdtemp(prefix="status-", dir=self._tmp.name))
        safe_git_dir = status_root / "gitdir"
        safe_git_dir.mkdir()
        (safe_git_dir / "objects").mkdir()
        (safe_git_dir / "refs" / "heads").mkdir(parents=True)
        (safe_git_dir / "info").mkdir()
        (safe_git_dir / "HEAD").write_text(head_sha + "\n", encoding="ascii")
        (safe_git_dir / "config").write_text(
            "[core]\n\trepositoryformatversion = 0\n\tbare = false\n",
            encoding="utf-8",
        )

        def write_semantic_file(name: str, payload: object) -> Path | None:
            if payload is None:
                return None
            if not isinstance(payload, bytes):
                raise CaptureError("INTERNAL_ERROR", f"invalid status semantic payload for {name}")
            path = status_root / name
            path.write_bytes(payload)
            return path

        info_exclude = semantics.get("info_exclude")
        info_attributes = semantics.get("info_attributes")
        if isinstance(info_exclude, bytes):
            (safe_git_dir / "info" / "exclude").write_bytes(info_exclude)
        if isinstance(info_attributes, bytes):
            (safe_git_dir / "info" / "attributes").write_bytes(info_attributes)
        copied_global_excludes = write_semantic_file("global-excludes", semantics.get("global_excludes"))
        copied_global_attributes = write_semantic_file("global-attributes", semantics.get("global_attributes"))

        env = self.env.copy()
        env["GIT_INDEX_FILE"] = str(index_path)
        env["GIT_OBJECT_DIRECTORY"] = str(object_dir)

        safe_config_args: list[str] = []
        config_values = semantics.get("config_values")
        if not isinstance(config_values, dict):
            raise CaptureError("INTERNAL_ERROR", "invalid status semantic config snapshot")
        for key, value in sorted(config_values.items()):
            if key not in SAFE_STATUS_CONFIG_KEYS or not isinstance(value, str):
                raise CaptureError("INTERNAL_ERROR", f"unsafe status semantic config key: {key}")
            safe_config_args.extend(["-c", f"{key}={value}"])
        if copied_global_excludes is not None:
            safe_config_args.extend(["-c", f"core.excludesFile={copied_global_excludes}"])
        if copied_global_attributes is not None:
            safe_config_args.extend(["-c", f"core.attributesFile={copied_global_attributes}"])

        base_cmd = [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"core.hooksPath={self.empty_hooks}",
            *safe_config_args,
            f"--git-dir={safe_git_dir}",
            f"--work-tree={self.repo}",
        ]

        def run_safe(*args: str, input_bytes: bytes | None = None) -> bytes:
            cmd = [*base_cmd, *args]
            try:
                p = subprocess.run(
                    cmd,
                    input=input_bytes,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=False,
                )
            except OSError as exc:
                raise CaptureError("GIT_EXEC_FAILED", f"failed to execute sanitized Git command: {exc}") from exc
            if p.returncode != 0:
                err = p.stderr.decode("utf-8", errors="replace").strip()
                raise CaptureError(
                    "GIT_COMMAND_FAILED",
                    f"sanitized Git command failed ({' '.join(cmd)}): {err}",
                )
            return p.stdout

        # Check tracked filter attributes through the same sanitized effective
        # attribute view used by status. This includes repository .gitattributes,
        # copied info/attributes, and copied effective core.attributesFile, while
        # filter.* executable drivers remain unavailable in this throwaway Git dir.
        if tracked_paths:
            filter_input = b"".join(
                path.encode("utf-8", errors="surrogateescape") + b"\0"
                for path in tracked_paths
            )
            filter_raw = run_safe(
                "check-attr",
                "-z",
                "--stdin",
                "filter",
                input_bytes=filter_input,
            )
            raise_on_external_filter_attributes(filter_raw)

        status_raw = run_safe(
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
        untracked_raw = run_safe("ls-files", "--others", "--exclude-standard", "-z")
        return status_raw, untracked_raw


def pack_record(kind: bytes, *fields: bytes) -> bytes:
    """Unambiguous canonical binary record with length-prefixed fields."""
    out = bytearray()
    all_fields = (kind, *fields)
    out += len(all_fields).to_bytes(4, "big")
    for field in all_fields:
        out += len(field).to_bytes(8, "big")
        out += field
    return bytes(out)


def manifest_hash(records: Iterable[bytes]) -> str:
    material = bytearray(b"ATP-MANIFEST-V2\0")
    records_list = list(records)
    material += len(records_list).to_bytes(8, "big")
    for record in records_list:
        material += len(record).to_bytes(8, "big")
        material += record
    return sha256_bytes(bytes(material))


def decode_git_path(raw: bytes) -> str:
    return raw.decode("utf-8", errors="surrogateescape")


def validate_repo_relative_path(path_text: str) -> tuple[str, ...]:
    pp = PurePosixPath(path_text)
    if pp.is_absolute() or not pp.parts or any(part in ("", ".", "..") for part in pp.parts):
        raise CaptureError("INVALID_GIT_PATH", "Git path is not a safe repository-relative path", path=path_text)
    return tuple(pp.parts)


def local_path(repo: Path, path_text: str) -> Path:
    parts = validate_repo_relative_path(path_text)
    return repo.joinpath(*parts)


def _safe_ancestor_chain(repo: Path, path_text: str) -> bool:
    """Validate every parent component without following links/reparse points.

    Return False when an ancestor is missing, which means the final repository
    path is also missing. Reject existing non-directory or redirecting ancestors.
    """
    parts = validate_repo_relative_path(path_text)
    current = repo
    for part in parts[:-1]:
        current = current / part
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise CaptureError(
                "LSTAT_FAILED",
                f"failed to inspect path ancestor without following links: {type(exc).__name__}: {exc}",
                path=path_text,
            ) from exc

        reparse_kind = _reparse_kind(current, st)
        if reparse_kind in {"junction", "reparse-point"}:
            raise CaptureError(
                "UNSAFE_PATH_ANCESTOR",
                f"repository path traverses unsupported Windows {reparse_kind} ancestor",
                path=path_text,
            )
        if stat.S_ISLNK(st.st_mode):
            raise CaptureError(
                "UNSAFE_PATH_ANCESTOR",
                "repository path traverses a symlink ancestor; external target reads are forbidden",
                path=path_text,
            )
        if not stat.S_ISDIR(st.st_mode):
            raise CaptureError(
                "UNSUPPORTED_PATH_ANCESTOR",
                "repository path has a non-directory ancestor",
                path=path_text,
            )
    return True


def _reparse_kind(path: Path, st: os.stat_result) -> str | None:
    attrs = getattr(st, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if not reparse_flag or not (attrs & reparse_flag):
        return None
    if path.is_symlink():
        return "symlink"
    isjunction = getattr(os.path, "isjunction", None)
    if callable(isjunction) and isjunction(path):
        return "junction"
    return "reparse-point"


def fs_record(repo: Path, path_text: str, *, category: bytes) -> bytes:
    path = local_path(repo, path_text)
    path_raw = path_text.encode("utf-8", errors="surrogateescape")
    if not _safe_ancestor_chain(repo, path_text):
        return pack_record(category + b"_MISSING", path_raw)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return pack_record(category + b"_MISSING", path_raw)
    except OSError as exc:
        raise CaptureError(
            "LSTAT_FAILED",
            f"failed to inspect path without following links: {type(exc).__name__}: {exc}",
            path=path_text,
        ) from exc

    reparse_kind = _reparse_kind(path, st)
    if reparse_kind in {"junction", "reparse-point"}:
        raise CaptureError(
            "UNSUPPORTED_REPARSE_POINT",
            f"unsupported Windows {reparse_kind}; baseline would not have a proven repository read boundary",
            path=path_text,
        )

    if stat.S_ISLNK(st.st_mode):
        try:
            target = os.readlink(path)
        except OSError as exc:
            raise CaptureError("READLINK_FAILED", f"failed to read symlink target: {exc}", path=path_text) from exc
        target_raw = os.fsencode(target)
        # Record the link object identity only. Never follow or read its target.
        return pack_record(category + b"_SYMLINK", path_raw, target_raw)

    if stat.S_ISREG(st.st_mode):
        digest, size = sha256_file(path)
        if os.name == "nt":
            # POSIX executable bits are not Windows execution semantics. Record
            # stable Windows file attributes instead so local filesystem state is
            # still represented without pretending mode bits are portable.
            attrs = int(getattr(st, "st_file_attributes", 0))
            behavior_mode = pack_record(b"WINDOWS_FILE_ATTRIBUTES", str(attrs).encode("ascii"))
        else:
            # Git may intentionally ignore executable-bit changes when
            # core.fileMode=false. The planner still needs those behavior-relevant
            # local states to produce distinct baselines.
            executable = b"1" if (stat.S_IMODE(st.st_mode) & 0o111) else b"0"
            behavior_mode = pack_record(b"POSIX_EXECUTABLE", executable)
        return pack_record(
            category + b"_FILE",
            path_raw,
            behavior_mode,
            str(size).encode("ascii"),
            digest.encode("ascii"),
        )

    if stat.S_ISDIR(st.st_mode):
        raise CaptureError(
            "UNSUPPORTED_DIRECTORY_ENTRY",
            "Git returned a directory entry that is not content-complete (commonly an untracked nested repository)",
            path=path_text,
        )

    raise CaptureError(
        "UNSUPPORTED_FILE_TYPE",
        "unsupported filesystem object type; baseline cannot prove complete content",
        path=path_text,
    )


def parse_ls_tree(raw: bytes) -> list[tuple[bytes, bytes, bytes, str]]:
    entries: list[tuple[bytes, bytes, bytes, str]] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        meta, path_raw = item.split(b"\t", 1)
        mode, obj_type, oid = meta.split(b" ", 2)
        entries.append((mode, obj_type, oid, decode_git_path(path_raw)))
    return entries


def parse_ls_files_stage(raw: bytes) -> list[tuple[bytes, bytes, int, str]]:
    entries: list[tuple[bytes, bytes, int, str]] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        meta, path_raw = item.split(b"\t", 1)
        mode, oid, stage_raw = meta.split(b" ", 2)
        entries.append((mode, oid, int(stage_raw), decode_git_path(path_raw)))
    return entries


def canonical_head_records(entries: list[tuple[bytes, bytes, bytes, str]]) -> list[bytes]:
    records = []
    for mode, obj_type, oid, path_text in entries:
        path_raw = path_text.encode("utf-8", errors="surrogateescape")
        records.append(pack_record(b"HEAD", mode, obj_type, oid, path_raw))
    return records


def canonical_index_records(entries: list[tuple[bytes, bytes, int, str]]) -> list[bytes]:
    records = []
    for mode, oid, stage_no, path_text in entries:
        path_raw = path_text.encode("utf-8", errors="surrogateescape")
        records.append(pack_record(b"INDEX", mode, oid, str(stage_no).encode("ascii"), path_raw))
    return records


def normalized_head_vs_index(entries: list[tuple[bytes, bytes, bytes, str]]) -> list[bytes]:
    out = []
    for mode, _obj_type, oid, path_text in entries:
        path_raw = path_text.encode("utf-8", errors="surrogateescape")
        out.append(pack_record(b"TRACKED", mode, oid, b"0", path_raw))
    return out


def normalized_index(entries: list[tuple[bytes, bytes, int, str]]) -> list[bytes]:
    out = []
    for mode, oid, stage_no, path_text in entries:
        path_raw = path_text.encode("utf-8", errors="surrogateescape")
        out.append(pack_record(b"TRACKED", mode, oid, str(stage_no).encode("ascii"), path_raw))
    return out


def _config_bool_is_true(git: LocalGit, key: str) -> bool:
    raw = git.run("config", "--bool", "--get", key, optional=True)
    return bool(raw and raw.strip().lower() == b"true")


def _effective_config_keys(git: LocalGit, pattern: str) -> list[str]:
    raw = git.run("config", "--name-only", "--get-regexp", pattern, optional=True)
    if not raw:
        return []
    keys: set[str] = set()
    for line in raw.splitlines():
        if not line:
            continue
        try:
            keys.add(line.decode("utf-8", errors="strict"))
        except UnicodeDecodeError as exc:
            raise CaptureError(
                "GIT_CONFIG_PARSE_FAILED",
                "could not decode Git configuration key as UTF-8",
            ) from exc
    return sorted(keys)


def check_no_partial_clone(git: LocalGit) -> None:
    # Read effective repository config, not only --local. With
    # extensions.worktreeConfig=true, Git may store remote promisor/partial
    # markers in config.worktree; those values are part of the repository's
    # effective behavior and must be rejected as well. Global/system config is
    # disabled in LocalGit.env, so this remains local-only.
    for key in _effective_config_keys(git, r"^remote\..*\.promisor$"):
        normalized = git.run("config", "--bool", "--get", key)
        assert normalized is not None
        if normalized.strip().lower() == b"true":
            raise CaptureError(
                "PARTIAL_CLONE_UNSUPPORTED",
                "partial/promisor repositories are rejected because missing objects could require remote lazy fetch",
            )

    for key in _effective_config_keys(git, r"^remote\..*\.partialclonefilter$"):
        value = git.run("config", "--get", key)
        assert value is not None
        if value.strip():
            raise CaptureError(
                "PARTIAL_CLONE_UNSUPPORTED",
                "partial/promisor repositories are rejected because missing objects could require remote lazy fetch",
            )

    extension = git.run("config", "--get", "extensions.partialClone", optional=True)
    if extension and extension.strip():
        raise CaptureError(
            "PARTIAL_CLONE_UNSUPPORTED",
            "partial/promisor repositories are rejected because missing objects could require remote lazy fetch",
        )


def check_no_sparse_checkout(git: LocalGit) -> None:
    if _config_bool_is_true(git, "core.sparseCheckout"):
        raise CaptureError(
            "SPARSE_CHECKOUT_UNSUPPORTED",
            "sparse checkout is rejected because the Skill requires a complete local working tree",
        )


def check_no_unmerged_index(index_entries: list[tuple[bytes, bytes, int, str]]) -> None:
    unmerged = sorted({path for _mode, _oid, stage_no, path in index_entries if stage_no != 0})
    if unmerged:
        raise CaptureError(
            "UNMERGED_INDEX_UNSUPPORTED",
            "unmerged index entries are rejected because conflict worktree content is not represented by a stage-0 entry",
            path=unmerged[0],
        )


def check_referenced_git_objects(
    git: LocalGit,
    head_entries: list[tuple[bytes, bytes, bytes, str]],
    index_entries: list[tuple[bytes, bytes, int, str]],
) -> None:
    """Require all blobs referenced by HEAD/index to exist in the local object DB."""
    expected: dict[bytes, tuple[bytes, str]] = {}
    for _mode, obj_type, oid, path_text in head_entries:
        expected.setdefault(oid, (obj_type, path_text))
    for _mode, oid, stage_no, path_text in index_entries:
        if stage_no == 0:
            expected.setdefault(oid, (b"blob", path_text))
    if not expected:
        return

    ordered = sorted(expected)
    request = b"\n".join(ordered) + b"\n"
    raw = git.run(
        "cat-file",
        "--batch-check=%(objectname) %(objecttype)",
        input_bytes=request,
    )
    assert raw is not None
    lines = raw.splitlines()
    if len(lines) != len(ordered):
        raise CaptureError(
            "GIT_OBJECT_CHECK_FAILED",
            "Git object availability check returned an unexpected number of results",
        )

    for requested_oid, line in zip(ordered, lines):
        parts = line.split()
        _expected_type, path_text = expected[requested_oid]
        if len(parts) == 2 and parts[1] == b"missing":
            raise CaptureError(
                "MISSING_GIT_OBJECT",
                "a blob referenced by HEAD or the index is unavailable locally; remote lazy fetch is forbidden",
                path=path_text,
            )
        if len(parts) != 2:
            raise CaptureError(
                "GIT_OBJECT_CHECK_FAILED",
                "could not parse Git object availability result",
                path=path_text,
            )
        returned_oid, returned_type = parts
        if returned_oid.lower() != requested_oid.lower():
            raise CaptureError(
                "GIT_OBJECT_CHECK_FAILED",
                "Git object availability result did not match the requested object",
                path=path_text,
            )
        if returned_type != b"blob":
            raise CaptureError(
                "INVALID_GIT_OBJECT_TYPE",
                "a path referenced by HEAD or the index does not resolve to a blob object",
                path=path_text,
            )


def check_no_hidden_index_flags(git: LocalGit) -> None:
    raw = git.run("ls-files", "-v", "-z")
    assert raw is not None
    for item in raw.split(b"\0"):
        if not item:
            continue
        if len(item) < 3 or item[1:2] != b" ":
            raise CaptureError("GIT_INDEX_PARSE_FAILED", "could not parse git ls-files -v output")
        tag = item[:1]
        path = decode_git_path(item[2:])
        # With `git ls-files -v`, lowercase tags mean assume-unchanged and
        # `S` means skip-worktree. Both can make `git status` hide local
        # content changes, so the baseline must fail closed.
        if tag.islower():
            raise CaptureError(
                "ASSUME_UNCHANGED_UNSUPPORTED",
                "assume-unchanged index entries are rejected because they can hide local changes from Git status",
                path=path,
            )
        if tag == b"S":
            raise CaptureError(
                "SKIP_WORKTREE_UNSUPPORTED",
                "skip-worktree index entries are rejected because they can hide or omit local working-tree content",
                path=path,
            )


def posix_exec_mode_differs_from_index(
    repo: Path,
    index_entries: list[tuple[bytes, bytes, int, str]],
) -> bool:
    """Detect behavior-relevant executable-bit divergence hidden by Git config."""
    if os.name == "nt":
        return False
    for mode, _oid, stage_no, path_text in index_entries:
        if stage_no != 0 or mode not in {b"100644", b"100755"}:
            continue
        if not _safe_ancestor_chain(repo, path_text):
            continue
        path = local_path(repo, path_text)
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise CaptureError(
                "LSTAT_FAILED",
                f"failed to inspect tracked file mode: {type(exc).__name__}: {exc}",
                path=path_text,
            ) from exc
        if not stat.S_ISREG(st.st_mode):
            continue
        actual_exec = bool(stat.S_IMODE(st.st_mode) & 0o111)
        index_exec = mode == b"100755"
        if actual_exec != index_exec:
            return True
    return False


def check_no_gitlinks(head_entries, index_entries) -> None:
    paths = []
    for mode, _obj_type, _oid, path_text in head_entries:
        if mode == b"160000":
            paths.append(path_text)
    for mode, _oid, _stage_no, path_text in index_entries:
        if mode == b"160000":
            paths.append(path_text)
    if paths:
        raise CaptureError(
            "SUBMODULE_UNSUPPORTED",
            "tracked Gitlinks/submodules are not content-complete in the parent repository baseline; plan that scope separately",
            path=sorted(set(paths))[0],
        )


def raise_on_external_filter_attributes(raw: bytes) -> None:
    parts = raw.split(b"\0")
    # Output is path, attribute, value triples.
    for i in range(0, len(parts) - 2, 3):
        path_raw, attr_raw, value_raw = parts[i : i + 3]
        if not path_raw or attr_raw != b"filter":
            continue
        value = value_raw.decode("utf-8", errors="replace")
        if value not in {"unspecified", "unset"}:
            raise CaptureError(
                "EXTERNAL_FILTER_UNSUPPORTED",
                f"tracked path uses Git filter attribute '{value}'; baseline will not execute external clean/smudge/process filters",
                path=decode_git_path(path_raw),
            )


def check_no_external_filter_attributes(git: LocalGit, paths: list[str]) -> None:
    if not paths:
        return
    input_bytes = b"".join(p.encode("utf-8", errors="surrogateescape") + b"\0" for p in paths)
    raw = git.run("check-attr", "-z", "--stdin", "filter", input_bytes=input_bytes)
    assert raw is not None
    raise_on_external_filter_attributes(raw)


def parse_status_entries(raw: bytes) -> list[str]:
    # Preserve Git porcelain records for human diagnosis. Rename/copy records use
    # an additional NUL-delimited path; retaining each token is unambiguous in
    # JSON and the raw status hash below is the canonical machine fingerprint.
    return [item.decode("utf-8", errors="surrogateescape") for item in raw.split(b"\0") if item]


def capture(architecture: Path, repo: Path) -> dict:
    arch_digest, arch_size = sha256_file(architecture)
    git = LocalGit(repo)
    try:
        inside = git.run("rev-parse", "--is-inside-work-tree")
        assert inside is not None
        if inside.strip().lower() != b"true":
            raise CaptureError("NOT_GIT_WORKTREE", "repository_root is not a Git working tree")

        top_raw = git.run("rev-parse", "--show-toplevel")
        assert top_raw is not None
        actual_top = Path(top_raw.decode("utf-8", errors="surrogateescape").strip()).resolve()
        if actual_top != repo:
            raise CaptureError(
                "REPOSITORY_ROOT_MISMATCH",
                f"repository_root must be the Git top-level; actual top-level is {actual_top}",
                path=str(repo),
            )

        check_no_partial_clone(git)
        check_no_sparse_checkout(git)

        head_raw = git.run("rev-parse", "--verify", "HEAD^{commit}")
        assert head_raw is not None
        head = head_raw.decode("ascii", errors="strict").strip().lower()

        branch_raw = git.run("symbolic-ref", "--quiet", "--short", "HEAD", optional=True)
        branch = branch_raw.decode("utf-8", errors="surrogateescape").strip() if branch_raw else ""
        detached = not bool(branch)

        head_tree_raw = git.run("ls-tree", "-r", "-z", "--full-tree", "HEAD")
        index_raw = git.run("ls-files", "--stage", "-z")
        assert head_tree_raw is not None and index_raw is not None
        head_entries = parse_ls_tree(head_tree_raw)
        index_entries = parse_ls_files_stage(index_raw)
        check_no_gitlinks(head_entries, index_entries)
        check_no_unmerged_index(index_entries)
        check_referenced_git_objects(git, head_entries, index_entries)
        check_no_hidden_index_flags(git)

        tracked_paths = sorted({path for _mode, _oid, stage_no, path in index_entries if stage_no == 0})
        check_no_external_filter_attributes(git, tracked_paths)

        # Status/untracked evidence is collected through a throwaway Git
        # directory. Preserve a narrow snapshot of legitimate non-executable Git
        # semantics while excluding filter/hook/fsmonitor/remote side effects.
        status_semantics = git.capture_status_semantics()
        status_raw, untracked_raw = git.run_sanitized_status(head, status_semantics, tracked_paths)

        untracked_paths = sorted(
            decode_git_path(raw) for raw in untracked_raw.split(b"\0") if raw
        )

        head_manifest_sha = manifest_hash(canonical_head_records(head_entries))
        index_manifest_sha = manifest_hash(canonical_index_records(index_entries))
        index_differs_from_head = manifest_hash(normalized_head_vs_index(head_entries)) != manifest_hash(
            normalized_index(index_entries)
        )

        tracked_worktree_records = [fs_record(repo, p, category=b"TRACKED") for p in tracked_paths]
        tracked_worktree_sha = manifest_hash(tracked_worktree_records)

        untracked_records = [fs_record(repo, p, category=b"UNTRACKED") for p in untracked_paths]
        untracked_sha = manifest_hash(untracked_records)

        status_sha = sha256_bytes(status_raw)
        changed_entries = parse_status_entries(status_raw)
        executable_mode_differs = posix_exec_mode_differs_from_index(repo, index_entries)
        dirty = bool(status_raw) or executable_mode_differs

        # Capture stability gate. A Planning Input Baseline must not combine the
        # Architecture target, Git identity/index/status, or filesystem content
        # from different instants. Re-read all baseline-defining inputs after
        # hashing. Any difference means the source changed during capture, so fail
        # closed instead of returning a mixed-time baseline.
        check_no_partial_clone(git)
        check_no_sparse_checkout(git)
        head_after_raw = git.run("rev-parse", "--verify", "HEAD^{commit}")
        branch_after_raw = git.run("symbolic-ref", "--quiet", "--short", "HEAD", optional=True)
        index_after_raw = git.run("ls-files", "--stage", "-z")
        status_semantics_after = git.capture_status_semantics()
        status_after_raw, untracked_after_raw = git.run_sanitized_status(
            head_after_raw.decode("ascii", errors="strict").strip().lower()
            if head_after_raw is not None
            else head,
            status_semantics_after,
            tracked_paths,
        )
        assert head_after_raw is not None and index_after_raw is not None

        head_after = head_after_raw.decode("ascii", errors="strict").strip().lower()
        branch_after = (
            branch_after_raw.decode("utf-8", errors="surrogateescape").strip()
            if branch_after_raw
            else ""
        )
        detached_after = not bool(branch_after)
        index_entries_after = parse_ls_files_stage(index_after_raw)
        check_no_gitlinks(head_entries, index_entries_after)
        check_no_unmerged_index(index_entries_after)
        check_no_hidden_index_flags(git)
        untracked_paths_after = sorted(
            decode_git_path(raw) for raw in untracked_after_raw.split(b"\0") if raw
        )
        index_manifest_sha_after = manifest_hash(canonical_index_records(index_entries_after))
        executable_mode_differs_after = posix_exec_mode_differs_from_index(repo, index_entries_after)

        if (
            head_after != head
            or branch_after != branch
            or detached_after != detached
            or index_manifest_sha_after != index_manifest_sha
            or status_semantics_after.get("fingerprint") != status_semantics.get("fingerprint")
            or status_after_raw != status_raw
            or untracked_paths_after != untracked_paths
            or executable_mode_differs_after != executable_mode_differs
        ):
            raise CaptureError(
                "REPOSITORY_CHANGED_DURING_CAPTURE",
                "repository state changed while the planning baseline was being captured; retry when local writes are quiescent",
                path=str(repo),
            )

        # Re-evaluate filter attributes after all status collection. Sanitized
        # status may preserve non-executable attributes/ignore semantics but never
        # imports filter.* commands, so repository filters cannot execute. This
        # final check keeps the policy that active tracked filter attributes are
        # unsupported baseline state.
        check_no_external_filter_attributes(git, tracked_paths)

        tracked_worktree_sha_after = manifest_hash(
            [fs_record(repo, p, category=b"TRACKED") for p in tracked_paths]
        )
        untracked_sha_after = manifest_hash(
            [fs_record(repo, p, category=b"UNTRACKED") for p in untracked_paths_after]
        )
        if (
            tracked_worktree_sha_after != tracked_worktree_sha
            or untracked_sha_after != untracked_sha
        ):
            raise CaptureError(
                "REPOSITORY_CHANGED_DURING_CAPTURE",
                "repository file content changed while the planning baseline was being captured; retry when local writes are quiescent",
                path=str(repo),
            )

        arch_digest_after, arch_size_after = sha256_file(architecture)
        if arch_digest_after != arch_digest or arch_size_after != arch_size:
            raise CaptureError(
                "ARCHITECTURE_CHANGED_DURING_CAPTURE",
                "architecture source changed while the planning baseline was being captured; retry with a stable approved Architecture file",
                path=str(architecture),
            )

        state_material = b"".join(
            [
                pack_record(b"HEAD_SHA", head.encode("ascii")),
                pack_record(b"HEAD_MANIFEST", head_manifest_sha.encode("ascii")),
                pack_record(b"INDEX_MANIFEST", index_manifest_sha.encode("ascii")),
                pack_record(b"WORKTREE_TRACKED_MANIFEST", tracked_worktree_sha.encode("ascii")),
                pack_record(b"UNTRACKED_MANIFEST", untracked_sha.encode("ascii")),
                pack_record(b"STATUS", status_sha.encode("ascii")),
            ]
        )

        return {
            "schema": SCHEMA,
            "capture_valid": True,
            "errors": [],
            "architecture_path": str(architecture),
            "architecture_sha256": arch_digest,
            "architecture_size_bytes": arch_size,
            "repository_root": str(repo),
            "repository_head_sha": head,
            "repository_branch": branch or None,
            "repository_detached": detached,
            "repository_worktree_dirty": dirty,
            "repository_posix_exec_mode_differs_from_index": executable_mode_differs,
            "repository_index_differs_from_head": index_differs_from_head,
            "head_tracked_manifest_sha256": head_manifest_sha,
            "index_tracked_manifest_sha256": index_manifest_sha,
            "worktree_tracked_manifest_sha256": tracked_worktree_sha,
            "untracked_manifest_sha256": untracked_sha,
            "status_porcelain_sha256": status_sha,
            "repository_local_state_sha256": sha256_bytes(state_material),
            "changed_status_entries": changed_entries,
            "untracked_paths": untracked_paths,
            "remote_access_policy": "forbidden",
            "remote_git_subcommands_issued": [],
            "partial_clone_supported": False,
        }
    finally:
        git.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--architecture-path", required=True)
    ap.add_argument("--repository-root", required=True)
    ns = ap.parse_args()

    architecture_arg = Path(ns.architecture_path).expanduser()
    repo_arg = Path(ns.repository_root).expanduser()

    context = {
        "schema": SCHEMA,
        "capture_valid": False,
        "errors": [],
        "architecture_path": str(architecture_arg),
        "repository_root": str(repo_arg),
    }

    try:
        architecture = architecture_arg.resolve(strict=True)
        if not architecture.is_file():
            raise CaptureError("ARCHITECTURE_NOT_FILE", "architecture_path is not a regular file", path=str(architecture))
        repo = repo_arg.resolve(strict=True)
        if not repo.is_dir():
            raise CaptureError("REPOSITORY_NOT_DIRECTORY", "repository_root is not a directory", path=str(repo))
        payload = capture(architecture, repo)
        emit_json(payload)
        return 0
    except FileNotFoundError as exc:
        err = CaptureError("PATH_NOT_FOUND", f"input path does not exist: {exc.filename}", path=str(exc.filename))
        context["errors"] = [err.as_dict()]
        emit_json(context)
        return 2
    except CaptureError as exc:
        context["errors"] = [exc.as_dict()]
        emit_json(context)
        return 2
    except OSError as exc:
        err = CaptureError("OS_ERROR", f"operating-system error: {type(exc).__name__}: {exc}")
        context["errors"] = [err.as_dict()]
        emit_json(context)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
