---
name: redemption-comment-style
description: Enforce Redemption's Python code-comment convention while Codex or any other AI agent creates, modifies, refactors, or fixes Redemption Python code. Use for production Python changes, especially business calculations, validation, idempotency, locking, retries, state transitions, graph traversal, persistence, and other multi-step logic. Match the Chinese comment style used by User/UserStatsService.py:update_elite_performance, including `# region ...` / `# endregion` blocks for coherent logic sections and Step separators for large multi-phase functions. Preserve comment accuracy and avoid low-value syntax narration.
---

# Redemption Comment Style

Write comments as part of the implementation, not as a later documentation pass.

Use the repository's current `User/UserStatsService.py` and especially `update_elite_performance` as the canonical local style example when that file is available. Read `references/comment-patterns.md` for the normalized rules and examples.

## Workflow

1. Read the target file before editing and preserve its surrounding terminology and indentation.
2. If available, inspect `User/UserStatsService.py:update_elite_performance` before substantial Python changes to refresh the canonical comment style.
3. Implement the requested behavior and comments together.
4. Divide non-trivial logic into cohesive business/technical phases.
5. Wrap each meaningful phase in a `# region <中文标题>` / `# endregion` pair.
6. For large functions with several major phases, add `Step N` separator headings, then use regions inside each phase.
7. Add short inline comments only where formulas, invariants, ordering, concurrency, fallback, or business meaning would otherwise be easy to misunderstand.
8. Re-read the modified code and verify every comment still describes the actual behavior.

## Region Rules

Use exactly this Python form:

```python
# region 参数验证
...
# endregion
```

Follow these rules:

- Write region titles in concise Simplified Chinese.
- Put `# region` and `# endregion` at the same indentation level as the code they delimit.
- Make one region correspond to one coherent responsibility or decision stage.
- Prefer business/action titles such as `参数验证`, `初始化`, `幂等验证`, `上订单锁`, `计算贡献差值`, `重新评定祖先等级`, `落库前最终校验`.
- Use a region for non-trivial validation, calculations, state changes, retry/lock handling, branching policy, persistence preparation, graph traversal, and other logic that forms a meaningful paragraph.
- A single guard may have its own region when it is an important stage, such as idempotency or settlement protection.
- Do not create a region around every assignment or obvious getter/setter operation.
- Avoid nested regions unless the surrounding file already requires them; prefer sibling regions with clearer boundaries.
- Close the region immediately after the logic it describes. Do not let one region silently cover unrelated operations.

## Step Separators for Large Functions

When a function contains multiple major phases, use the same visual structure as `update_elite_performance`:

```python
# ---------------------------------------------------------
# Step 1: 处理源用户
# ---------------------------------------------------------
```

Use Step headings for major phases only. Use regions for the smaller cohesive blocks inside each phase.

Typical candidates include:

- Step 1: load/normalize source state
- Step 2: perform the main bottom-up or top-down calculation
- Step 3: final validation and persistence

Choose names from the actual behavior; do not force these example names onto unrelated code.

## Inline Comment Rules

Inside a region, add inline comments when they explain information that code alone does not make safe to infer, such as:

- a bonus/business rule or threshold
- why a delta is computed in a particular direction
- a short-circuit or early-stop condition
- why a lock must be refreshed before a write
- an invariant maintained across a loop
- why in-memory state must be preferred over stale persisted state
- a formula whose domain meaning is not obvious
- a fallback that exists for correctness rather than convenience

Prefer comments that explain intent or correctness constraints.

Good:

```python
# 计算贡献差值：新的临时贡献度 - 当前已记录贡献度
next_delta_update = new_contrib - old_contrib
```

Avoid comments that only translate syntax.

Bad:

```python
# 给 count 加 1
count += 1
```

## Business-Rule Accuracy

Do not invent business semantics merely to make a comment sound complete.

For Redemption business logic:

- Respect the repository's `AGENTS.md` and applicable project skills.
- When a comment states a bonus/calculation rule and project requirement text conflicts with authoritative SQL, first check `AGENTS.md` and applicable project governance for any superseding user/business decision. Absent a superseding decision (for example, an approved and still-effective `DEC-*`), follow the repository's established SQL precedence rather than the rough `奖金制度.md` wording.
- If the implementation's intent cannot be established confidently, write a narrower technical comment or surface the ambiguity instead of fabricating a business explanation.
- Keep comments synchronized with the code in the same change. Never preserve a stale comment after logic changes.

## Editing Existing Code

When modifying an existing function:

- Keep correct existing region titles unless the responsibility changes.
- Update a region title when the block's meaning changes.
- Split an oversized region if it now contains multiple independent logical responsibilities.
- Merge or remove noisy regions only when doing so preserves the canonical style.
- Do not reformat unrelated parts of the file merely to increase comment density.

When adding new logic inside an existing region, decide whether it belongs to that region. If it introduces a new business/technical phase, create a new sibling region.

## Function-Level Guidance

For short, obvious helpers, a concise docstring or no extra block comment may be sufficient.

For non-trivial business functions, comments must expose the logical structure. A long function with validation, state loading, calculations, branching, retries, or persistence must not be left as an undifferentiated code block.

For complex control flow, use this hierarchy:

1. Optional function docstring for responsibility/contract.
2. Step separators for major phases when the function is large.
3. `region` blocks for logical paragraphs.
4. Inline comments for formulas/invariants/surprising local decisions.

## Guardrails

- Do not comment every line.
- Do not add English region titles when the surrounding Redemption Python code uses Chinese.
- Do not remove useful existing Chinese comments merely to shorten the file.
- Do not write comments that contradict code, SQL-backed business rules, or project contracts.
- Do not encode temporary guesses as authoritative business facts.
- Do not use comments as a substitute for clear variable/function names.
- Do not change runtime behavior solely to make commenting easier.
- Do not stage, commit, push, or create a PR unless the user explicitly asks for that Git action.

## Completion Check

Before finishing a code change, verify:

- Every newly added non-trivial logic phase has a clear comment boundary.
- Complex business logic is grouped into `# region` / `# endregion` paragraphs.
- Large multi-phase functions use Step separators where they materially improve navigation.
- Region titles are concise Chinese descriptions of intent.
- Inline comments explain business meaning, formulas, invariants, ordering, or failure behavior rather than syntax.
- Comments match the final code after all refactoring.
- No business rule was invented when evidence was insufficient.
- Unrelated code was not churned just to add comments.
