param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('PRODUCER','OPUS','FABLE')]
    [string]$Role,
    [string]$ProjectCommentSkillPath='.agents/skills/redemption-comment-style/SKILL.md'
)

$ErrorActionPreference = 'Stop'

if ($Role -eq 'PRODUCER') {
    $contract=@'
# CODEX PRODUCER-ONLY SKILL CONTRACT

This contract applies only to the Loop Codex Producer construction/rework process.
Before editing Candidate code, read and use these skills in order:
1. `superpowers:using-superpowers`.
2. For rework, `superpowers:receiving-code-review`; independently verify every reviewer finding.
3. `superpowers:systematic-debugging` to prove the root cause.
4. `superpowers:test-driven-development` and its `writing-good-tests.md`; capture the expected RED before implementation.
5. `ponytail full`; reuse existing Provider, Bootstrap, Adapter, and test patterns and avoid speculative abstractions.
6. `{{PROJECT_COMMENT_SKILL_PATH}}` and its required reference before Python edits.
7. `superpowers:verification-before-completion` before returning `READY_FOR_UAT`.

Do not use `brainstorming`, `writing-plans`, `executing-plans`, or multi-agent skills inside this non-interactive Loop Round. The approved design and Controller prompt are the implementation input. In IMPLEMENTATION_HANDOFF.md, list the skill paths actually read, RED/GREEN commands and results, and the unnecessary design avoided under Ponytail.
'@
    $contract.Replace('{{PROJECT_COMMENT_SKILL_PATH}}',$ProjectCommentSkillPath)
    exit 0
}

@"
# $Role REVIEWER SKILL ISOLATION CONTRACT

This contract applies to the $Role verifier only.
- You MUST NOT read, load, invoke, or claim use of any Superpowers or Ponytail skill, plugin, instruction file, or methodology.
- Do not treat the Producer's skill-use report as correctness evidence.
- Judge independently from the pinned project rules, Candidate diff, raw test output, Controller evidence, and governed UAT results.
- Project Skills explicitly required by the pinned AGENTS.md remain applicable; this prohibition is limited to Superpowers and Ponytail.
"@
