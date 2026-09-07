# Planning Diagnostic Protocol

Use this protocol only for Implementation Plan generation from an approved architecture.

## 1. Deterministic classification order

Always classify in this order:

1. **Determine the target.** Ask whether the approved Architecture plus any explicit user-approved Architecture amendment uniquely determines the planning-relevant target behavior.
   - If no, use `ARCHITECTURE_GAP`.
   - If a Reality Lock fact conflicts with an approved Architecture contract and the user has not explicitly amended the Architecture, also use `ARCHITECTURE_GAP`; do not silently let current reality cancel the approved contract.
2. **Map the clear target to repository reality.** Only after the target is clear, inspect the local Repository.
   - If the mapping is clear and the Repository simply has not reached the target, use `REPOSITORY_MISMATCH / EXPECTED_DELTA`.
   - If the target is clear but repository responsibilities cannot be mapped without a new design decision, use `REPOSITORY_MISMATCH / UNRESOLVED_CONFLICT`.

This order is authoritative. Do not classify an undefined authorization/concurrency/security choice as a repository conflict merely because implementation would eventually touch the repository.

## 2. ARCHITECTURE_GAP

Use when the target cannot be uniquely determined from the approved Architecture plus explicit Architecture amendments/user decisions.

Also use when approved Reality Lock facts and an approved Architecture contract cannot both be satisfied without deciding whether to amend the Architecture or change the operating reality.

Do not use merely because implementation details are not spelled out. Use it only when choosing among plausible implementations would change behavior, scope, architecture, state, authorization, security, human-duty separation, concurrency, execution identity/lifecycle, evidence semantics, or acceptance criteria.

Examples:

- authorization model is not specified and different choices change authority/security semantics;
- concurrency model is not specified and different choices change execution topology;
- Reality Lock says one human operator, while approved Architecture explicitly requires two distinct human decision-makers, and there is no explicit Architecture amendment resolving the conflict.

Template:

```text
ID: AG-###
Type: ARCHITECTURE_GAP
Affected scope: <Task/WP/global>
Architecture source: <section(s)>
Reality source: <decision(s), if any>
Known facts: ...
Missing decision / unresolved contract: ...
Why it cannot be safely inferred: ...
Impact if guessed: ...
Required decision: ...
Stop scope: LOCAL | GLOBAL
Affected tasks/WPs: ...
```

Action:

- Never fill the gap with a preferred design.
- Never treat a Reality Lock fact as an implicit Architecture amendment.
- Freeze affected scope.
- Ask the smallest concrete question needed to resolve it.

## 3. REPOSITORY_MISMATCH

Use only after the target is clear, when local Repository reality differs from that target or from an Architecture assumption relevant to planning.

### EXPECTED_DELTA

Use when the Architecture target is explicit, repository responsibility is unambiguous, and the Repository simply has not reached the target yet.

Examples:

- Architecture requires a new resolver file and it does not exist;
- Architecture removes a legacy operation and the Repository still contains it;
- Architecture requires per-execution output but current code uses a root singleton.

Template:

```text
ID: RM-###
Type: REPOSITORY_MISMATCH
Classification: EXPECTED_DELTA
Architecture source: ...
Repository baseline: <HEAD + local-state fingerprint>
Observed current reality: ...
Target: ...
Plan treatment: <create/modify/remove/test task>
Stop required: NO
```

Action: convert the delta into authorized Plan work.

### UNRESOLVED_CONFLICT

Use when the target is already clear but cannot be mapped onto Repository reality without a new design/mapping decision.

Examples:

- Architecture says to modify component A, but A no longer exists and its responsibility is split across B/C with no approved mapping;
- Architecture assumes one authoritative controller boundary, but Repository reality implements two competing authoritative controllers and the approved Architecture does not say which current implementation should be retained/migrated.

Do **not** use this category merely because authorization, concurrency, state, or another target behavior was never specified. Undefined target behavior is `ARCHITECTURE_GAP`.

Template:

```text
ID: RM-###
Type: REPOSITORY_MISMATCH
Classification: UNRESOLVED_CONFLICT
Architecture source: ...
Repository baseline: <HEAD + local-state fingerprint>
Observed current reality: ...
Conflict: ...
Why planner cannot choose safely: ...
Required decision: ...
Stop scope: LOCAL | GLOBAL
Affected tasks/WPs: ...
```

Action: freeze affected scope and ask for a decision.

## 4. Stop-scope decision

Default to `LOCAL`.

Use `GLOBAL` when the issue changes or makes uncertain any of the following:

- global architecture/topology;
- human-vs-technical actor model when it affects governance;
- authorization/security boundary;
- state-machine vocabulary or legal transitions;
- execution identity or lifecycle;
- global concurrency model;
- Candidate/evidence trust boundary;
- ordering/dependencies across multiple Work Packages;
- acceptance semantics shared by multiple Work Packages.

A local blocker does not authorize the planner to omit it silently. Keep it in the register and mark affected skeleton/task entries as blocked.

## 5. What is not a diagnostic

Do not create a Gap/Mismatch for behavior-neutral choices that can safely follow existing Repository convention, such as markdown heading depth, formatting, import ordering, or equivalent local naming details when no contract depends on them.

## 6. Human/technical-role guard

Never infer that distinct technical principals imply distinct humans.

Examples of technical principals:

- Windows service accounts;
- SYSTEM;
- GitHub actor identity;
- SSH credentials;
- Codex/Opus/Fable roles;
- Kubernetes credentials;
- publisher/approver/broker service identities.

Only model multiple human operators when explicit user facts or approved Architecture require them. If a Reality Lock fact and an approved Architecture human-separation contract conflict, apply the `ARCHITECTURE_GAP` rule above rather than silently choosing one.
