---
name: architecture-to-plan
description: Use when the user requests an Implementation Plan grounded in an already-approved local architecture/design file and a local Git working tree, before implementation begins.
---

# Architecture to Plan

## Purpose

Translate an approved architecture into an executable Implementation Plan while preserving the architecture's scope, assumptions, invariants, and non-scope. Treat planning as constrained delta analysis, not as an opportunity to redesign the system.

## Required inputs

Require both inputs before planning:

- `architecture_path`: local path to the approved architecture/design document.
- `repository_root`: local path to the Git working tree that will be modified later.

If either path is missing, ask only for the missing path. If the runtime cannot access a path the user already supplied, explain that host-local filesystem access is unavailable and stop; do not repeatedly ask for the same path. Do not substitute GitHub, `origin/master`, `origin/main`, or another remote source.

Optional inputs:

- approved Reality Lock / operational facts;
- explicit user decisions or non-scope register;
- a requested output path/name;
- explicit permission to inspect a GitHub remote. Remote access remains opt-in.

## Runtime prerequisites

Baseline capture requires:

- Python 3.10+;
- a local Git CLI available on `PATH`;
- read access to `architecture_path` and the complete local working tree at `repository_root`.

For the Redemption repository on Windows, bind `<PYTHON_EXECUTABLE>` to
`<repository_root>\.venv\Scripts\python.exe`. Require that exact file to exist and
report Python 3.10 or later before baseline capture. Do not silently fall back to
`python`, `python3`, `py`, a PyCharm or WSL interpreter, or a Codex-bundled runtime.
If validation fails, stop with `PYTHON_RUNTIME_INVALID`.

The baseline script intentionally rejects incomplete/unsafe layouts it cannot fingerprint without side effects, including effective local/worktree partial/promisor configuration, missing blobs referenced by HEAD/index, unmerged indexes, sparse checkouts, assume-unchanged/skip-worktree index entries, tracked submodules/gitlinks, untracked nested repositories reported as directory entries, unsafe symlink/junction/reparse ancestors, unsupported Windows junction/reparse-point entries, and tracked custom Git filter attributes. On POSIX it fingerprints the actual executable-bit state even when Git is configured with `core.fileMode=false`; on Windows it records local file attributes instead of pretending POSIX execute bits are portable.

## Hard rules

1. Treat the approved architecture as target truth and the local repository working tree as current reality.
2. Do not redesign the architecture while writing the plan.
3. Do not invent human actors, approval chains, concurrency models, states, operations, security boundaries, branches, execution models, or infrastructure capabilities that the architecture does not authorize.
4. Never equate technical principals, service accounts, OS identities, AI roles, or credentials with distinct human operators unless the user explicitly says so.
5. Never assume local files are committed. Capture Git HEAD, index state, tracked worktree state, and untracked state separately.
6. Never read GitHub remote state, use `origin/master` or `origin/main` as the baseline, or assume remote parity unless the user explicitly requests remote comparison.
7. Never silently resolve uncertainty. Apply the diagnostic protocol.
8. Preserve explicit non-scope. Do not turn optional improvements into required work.
9. Use fail-closed planning: unresolved material uncertainty blocks only the affected scope by default, or the whole plan when global impact applies.
10. Phase 2 is forbidden until the user approves Phase 1.
11. A Reality Lock fact is not automatically an Architecture amendment. Only an explicit user decision that clearly amends/overrides an approved architecture requirement may change target truth.

## Source precedence and conflict handling

Use these rules instead of silently choosing whichever source is newest:

1. An explicit user decision that clearly states it amends or overrides an approved architecture requirement takes precedence for the affected requirement.
2. Otherwise, the approved architecture/design specification defines the target.
3. Approved Reality Lock facts define current operational reality but do **not** silently cancel architecture contracts.
4. Local repository evidence at `repository_root` defines current implementation reality.
5. Review/audit material is evidence only when the user supplies it as planning input; reviewer text is not an automatic requirement.

If a Reality Lock fact and an approved architecture contract cannot both be satisfied without changing governance, security, human-separation, lifecycle, or other material behavior, register an `ARCHITECTURE_GAP` and stop the affected scope. Use `GLOBAL` when the conflict changes a global governance/security boundary or materially affects multiple Work Packages. Do not infer that the Reality Lock itself authorizes an Architecture downgrade.

Use the architecture to determine the **target**. Use repository evidence to determine the **current state**. A difference between them is normally a delta to classify, not permission to rewrite either source.

## Baseline capture

Before analyzing plan content, capture the local planning baseline.

Resolve `<SKILL_ROOT>` to the directory containing this `SKILL.md`; do not resolve the script relative to `repository_root` or the caller's current working directory.

Run:

```powershell
& "<repository_root>\.venv\Scripts\python.exe" `
  "<SKILL_ROOT>\scripts\capture_baseline.py" `
  --architecture-path "<architecture_path>" `
  --repository-root "<repository_root>"
```

The script emits ASCII-safe JSON. Require `capture_valid=true` before using the baseline. If `capture_valid=false` or the process exits nonzero, stop planning and surface the structured `errors`; do not treat partial hashes as a valid baseline.

Use these returned values in Phase 1:

- canonical architecture path, byte size, and SHA-256;
- canonical repository root bound to the actual Git top-level;
- local Git HEAD SHA and branch/detached status;
- repository dirty flag, including POSIX executable-bit divergence hidden by `core.fileMode=false`;
- `repository_posix_exec_mode_differs_from_index`;
- `head_tracked_manifest_sha256`;
- `index_tracked_manifest_sha256`;
- `worktree_tracked_manifest_sha256`;
- `untracked_manifest_sha256`;
- `status_porcelain_sha256`;
- `repository_local_state_sha256` composite fingerprint;
- changed status entries and untracked path list;
- remote-access policy metadata.

The script captures HEAD/index/worktree/untracked state independently so staged and unstaged states cannot cancel into one net diff fingerprint. It uses a sanitized local Git environment, disables lazy fetch, evaluates effective repository config across local and enabled worktree scope, verifies that blobs referenced by HEAD/index are locally available, does not invoke remote subcommands, and fails on partial/promisor repositories rather than retrieving missing objects. Porcelain status is collected through a throwaway Git directory that does not load live repository-local filter commands, so a concurrent `.gitattributes` change cannot cause the baseline process to execute a configured clean/smudge/process filter. It also performs an end-of-capture stability recheck and fails closed if the Architecture source, branch/detached identity, repository state, or captured file content changed during baseline collection.

If the repository is dirty, explicitly state that `repository_head_sha` identifies only the committed base and that the plan is also grounded in the captured local state fingerprint. Never describe a dirty working tree as fully pinned by HEAD alone.

## Two-phase workflow

### Phase 1 — Planning Preflight + Plan Skeleton

Do not generate the detailed plan yet.

1. Capture and display the Planning Input Baseline before Architecture or repository planning analysis. If baseline capture is invalid, stop; do not inspect planning evidence or proceed to skeleton generation.
2. Read the architecture document completely enough to identify target components, invariants, exclusions, lifecycle/state contracts, acceptance criteria, and implementation staging, using the Architecture file bound by the valid baseline.
3. Inspect the local repository structure and the actual files relevant to those architecture requirements, using the local repository state bound by the valid baseline.
4. Build or reuse a Reality Lock:
   - Include only explicit user facts and architecture-supported operational facts.
   - Distinguish human actors from technical principals.
   - Treat Reality facts as current-state facts, not automatic Architecture amendments.
   - If a material operational fact or contract resolution is needed but not established, register an `ARCHITECTURE_GAP`; do not guess.
5. Apply the diagnostic protocol in `references/diagnostic-protocol.md`.
6. Produce:
   - `ARCHITECTURE_GAP Register`;
   - `REPOSITORY_MISMATCH Register` with `EXPECTED_DELTA` or `UNRESOLVED_CONFLICT`;
   - stop-scope decisions (`LOCAL` or `GLOBAL`);
   - a Plan Skeleton covering the architecture-derived scope: keep locally blocked Work Packages visible with `Status=BLOCKED`, do not expand their detailed tasks, and continue unblocked scope; a global blocker still stops the whole Plan.
7. For every proposed Work Package in the skeleton, show:
   - Architecture source(s);
   - goal;
   - repository evidence;
   - dependencies;
   - expected deliverable;
   - validation category;
   - explicit non-scope.
8. End with one of:
   - `PHASE_1_READY_FOR_APPROVAL` when no global blocker exists;
   - `PHASE_1_BLOCKED` when a global blocker exists.
9. Stop and wait for explicit user approval before Phase 2.

Do not treat approval of the architecture as automatic approval of the Phase 1 skeleton.

### Phase 2 — Detailed Implementation Plan

Enter Phase 2 only after explicit approval of Phase 1.

1. Freeze the approved Phase 1 baseline, Reality Lock, diagnostics, and Plan Skeleton.
2. Expand each Work Package into independently reviewable, testable tasks.
3. If `superpowers:writing-plans` is available, use its task-sizing, file-mapping, test-first, no-placeholder, and self-review practices **after** this skill's Phase 1 gate. This skill's fidelity/diagnostic rules take precedence.
4. For every task, include:
   - stable Task ID;
   - Architecture Source;
   - User/Reality Source when applicable;
   - Repository Evidence;
   - Required Scope;
   - Explicit Non-Scope;
   - exact files to create/modify/delete when determinable from evidence;
   - interfaces/dependencies;
   - ordered implementation steps;
   - positive tests;
   - negative/fail-closed tests where the architecture defines failure behavior;
   - acceptance criteria;
   - rollback/recovery notes when required by the architecture.
5. Do not invent an implementation detail when multiple choices would alter architecture, behavior, authorization, security, state, execution identity, or acceptance semantics. Register a new diagnostic instead.
6. Build both traceability directions:
   - Architecture -> Plan: every architecture requirement maps to one or more Plan tasks or an explicit non-implementation disposition.
   - Plan -> Architecture: every Plan task maps to an approved architecture/user source. A task with no source is unauthorized scope.
7. Run the fidelity self-review:
   - architecture coverage;
   - unauthorized additions;
   - Reality Lock consistency;
   - repository path/file reality;
   - placeholders/TODOs;
   - interface/name consistency;
   - test coverage for positive and negative architecture contracts;
   - non-scope leakage.
8. End with a Plan Readiness Verdict:
   - `PLAN_READY_FOR_REVIEW` only when no unresolved blocker remains;
   - otherwise `PLAN_BLOCKED` with exact diagnostics.

## Diagnostic protocol

Read `references/diagnostic-protocol.md` whenever an architecture omission, source conflict, or repository difference is encountered.

Apply this decision order:

1. **Is the target uniquely determined by approved Architecture plus explicit Architecture amendments?** If no, use `ARCHITECTURE_GAP`.
2. **If the target is clear, is the local repository mapping clear?**
   - clear but not yet implemented -> `REPOSITORY_MISMATCH / EXPECTED_DELTA`;
   - mapping cannot be chosen without a new design decision -> `REPOSITORY_MISMATCH / UNRESOLVED_CONFLICT`.

Stop rule:

- Default: `LOCAL` — freeze only affected tasks/Work Packages.
- Use `GLOBAL` when the issue changes global architecture, authorization/security boundary, state machine, execution identity/lifecycle, task ordering/dependencies, or materially affects multiple Work Packages.

Do not escalate cosmetic choices, formatting, naming that follows established repository convention, or other behavior-neutral details into diagnostics.

## Output structure

Use `references/output-template.md` for the Phase 1 and Phase 2 document structures.

## Local-first repository inspection

Prefer local filesystem and local Git evidence. Inspect relevant current working-tree files, not only blobs at HEAD. Use Git history only when needed to understand an architecture-required delta and only from the local clone unless the user authorizes remote access.

For every Git object/history/content read used after baseline capture, keep remote access explicitly disabled (including `GIT_NO_LAZY_FETCH=1`) unless the user has authorized a specific remote comparison. Do not run `fetch`, `pull`, `ls-remote`, or an equivalent remote-demanding command as part of local inspection. If a required object is unavailable locally, stop the affected inspection and report incomplete local evidence instead of allowing Git to lazy-fetch it.

When a file exists locally but differs from HEAD, reason from the working-tree file for current reality and record that the repository is dirty.

When the architecture names a target file that does not exist:

- if the architecture clearly requires creation, classify as `EXPECTED_DELTA`;
- if it assumes the file already exists or the intended responsibility cannot be located, classify as `UNRESOLVED_CONFLICT`.

When the repository contains a legacy feature that the architecture explicitly removes, classify as `EXPECTED_DELTA` and create a removal task. Do not preserve it merely because it currently exists.

## Plan fidelity principles

Use this mental model:

```text
Approved Target Architecture
          -
Local Current Repository Reality
          =
Authorized, Testable Implementation Delta
```

A Plan is not a second architecture document. It may decompose, sequence, test, and operationalize approved requirements; it may not create new requirements.
