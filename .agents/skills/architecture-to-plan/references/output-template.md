# Output Templates

## Phase 1 — Planning Preflight + Plan Skeleton

```markdown
# <System/Feature> Implementation Plan — Phase 1 Preflight & Skeleton

## 0. Planning Input Baseline
- Baseline capture valid: true
- Baseline capture errors: NONE
- Architecture path:
- Architecture SHA-256:
- Architecture size bytes:
- Repository root (verified Git top-level):
- Repository HEAD SHA:
- Repository branch/detached:
- Repository dirty:
- repository_posix_exec_mode_differs_from_index:
- Repository index differs from HEAD:
- HEAD tracked manifest SHA-256:
- Index tracked manifest SHA-256:
- Worktree tracked manifest SHA-256:
- Untracked manifest SHA-256:
- Porcelain status SHA-256:
- Local repository state SHA-256:
- Remote access policy: forbidden unless explicitly authorized
- Planning timestamp/context if relevant:

If baseline capture is invalid, stop here and present the structured errors. Do not generate a Plan Skeleton from an incomplete baseline.

## 1. Source of Truth & Precedence
[State the precedence actually used. Distinguish explicit Architecture amendments from Reality Lock facts; Reality facts do not silently override approved Architecture contracts.]

## 2. Reality Lock
| ID | Confirmed fact | Source | Architecture-amendment status | Planning effect |
|---|---|---|---|---|

## 3. Explicit Non-Scope
| ID | Non-scope | Source |
|---|---|---|

## 4. ARCHITECTURE_GAP Register
[Use diagnostic-protocol.md template. State NONE if none.]

## 5. REPOSITORY_MISMATCH Register
[Use EXPECTED_DELTA / UNRESOLVED_CONFLICT templates. State NONE if none.]

## 6. Stop-Scope Assessment
- Local blockers:
- Global blockers:
- Decision: PHASE_1_READY_FOR_APPROVAL | PHASE_1_BLOCKED

## 7. Plan Skeleton
| WP | Goal | Architecture source | Repository evidence | Dependencies | Deliverable | Validation | Explicit non-scope | Status |
|---|---|---|---|---|---|---|---|---|

## 8. Phase 1 Approval Request
[Summarize what the user is approving: baseline, Reality Lock, diagnostics, and skeleton only.]
```

Stop after Phase 1. Do not append detailed tasks until explicit user approval.

## Phase 2 — Detailed Implementation Plan

```markdown
# <System/Feature> Implementation Plan

## 0. Approved Planning Baseline
[Copy the approved Phase 1 baseline and diagnostics; do not silently change them.]

## 1. Goal

## 2. Architecture Summary
[2–4 paragraphs maximum; reference the Architecture instead of rewriting it.]

## 3. Global Constraints
[Exact approved constraints and non-scope.]

## 4. File/Component Change Map
| Path | Action | Responsibility | Architecture source | WP/Task |
|---|---|---|---|---|

## 5. Work Packages and Tasks

### WP-01 <name>
**Architecture source:** ...
**Reality/User source:** ...
**Repository evidence:** ...
**Dependencies:** ...
**Required scope:** ...
**Explicit non-scope:** ...

#### TASK-01-01 <name>
**Architecture source:** ...
**Reality/User source:** ...
**Repository evidence:** ...
**Required scope:** ...
**Explicit non-scope:** ...

**Files:**
- Create/Modify/Delete: `exact/path`

**Interfaces:**
- Consumes: ...
- Produces: ...

**Implementation sequence:**
1. ...
2. ...

**Positive verification:**
- ...

**Negative / fail-closed verification:**
- ...

**Acceptance criteria:**
- ...

**Rollback/recovery:**
- ...

[Repeat tasks/WPs.]

## 6. Architecture -> Plan Traceability
| Architecture requirement | Plan task(s) | Test/verification | Disposition |
|---|---|---|---|

## 7. Plan -> Architecture Traceability
| Plan task | Architecture/User source | Repository evidence | Authorized? |
|---|---|---|---|

## 8. Remaining Diagnostics
[Must be empty for PLAN_READY_FOR_REVIEW, or clearly list blockers.]

## 9. Fidelity Self-Review
- Architecture coverage:
- Unauthorized additions:
- Reality Lock consistency:
- Repository reality check:
- Placeholder scan:
- Interface/name consistency:
- Positive/negative test coverage:
- Non-scope leakage:

## 10. Plan Readiness Verdict
PLAN_READY_FOR_REVIEW | PLAN_BLOCKED
```
