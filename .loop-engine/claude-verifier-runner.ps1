$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force $parent | Out-Null
    }
    [IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Compact-Text($Value, [int]$Limit = 1600) {
    if ($null -eq $Value) { return "" }
    if ($Value -is [string]) {
        $text = $Value
    }
    else {
        try { $text = $Value | ConvertTo-Json -Depth 20 -Compress }
        catch { $text = [string]$Value }
    }
    $text = $text.Trim()
    if ($text.Length -le $Limit) { return $text }
    $half = [Math]::Floor(($Limit - 80) / 2)
    return $text.Substring(0, $half) + "`n... [truncated in live view; full data is in raw JSONL] ...`n" + $text.Substring($text.Length - $half)
}

function Tool-Label($Block) {
    $name = [string]$Block.name
    $toolInput = $Block.input
    switch ($name) {
        "Bash" {
            if ($toolInput.command) { return "[EXEC] " + (Compact-Text $toolInput.command 1200) }
        }
        "Read" {
            if ($toolInput.file_path) { return "[READ] $($toolInput.file_path)" }
        }
        "Edit" {
            if ($toolInput.file_path) { return "[EDIT] $($toolInput.file_path)" }
        }
        "Write" {
            if ($toolInput.file_path) { return "[EDIT] $($toolInput.file_path)" }
        }
        "Grep" {
            return "[SEARCH] pattern='$($toolInput.pattern)' path='$($toolInput.path)'"
        }
        "Glob" {
            return "[SEARCH] glob='$($toolInput.pattern)' path='$($toolInput.path)'"
        }
        "Agent" {
            if ($toolInput.description) { return "[AGENT] $($toolInput.description)" }
            if ($toolInput.prompt) { return "[AGENT] " + (Compact-Text $toolInput.prompt 800) }
        }
        "Task" {
            if ($toolInput.description) { return "[AGENT] $($toolInput.description)" }
            if ($toolInput.prompt) { return "[AGENT] " + (Compact-Text $toolInput.prompt 800) }
        }
    }
    return "[TOOL] $name " + (Compact-Text $toolInput 900)
}

function Tool-Result-Text($Block) {
    $content = $Block.content
    if ($content -is [string]) { return $content }
    if ($null -eq $content) { return "" }
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($item in @($content)) {
        if ($item -is [string]) { $parts.Add($item); continue }
        if ($item.text) { $parts.Add([string]$item.text); continue }
        try { $parts.Add(($item | ConvertTo-Json -Depth 10 -Compress)) }
        catch { $parts.Add([string]$item) }
    }
    return ($parts -join "`n")
}

function Read-TailText([string]$Path, [int]$MaxChars = 65536) {
    if (-not (Test-Path $Path)) { return "" }
    $text = [IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    if ($text.Length -le $MaxChars) { return $text }
    return $text.Substring($text.Length - $MaxChars)
}

function Test-ResumeSessionInvalid([string]$Text) {
    if (-not $Text) { return $false }
    $lower = $Text.ToLowerInvariant()

    # Never open a second session for quota/auth/network failures. Those are not
    # evidence that the saved session ID itself is invalid.
    $noFallbackMarkers = @(
        "session limit",
        "rate limit",
        "usage limit",
        "quota",
        "authentication",
        "unauthorized",
        "forbidden",
        "network",
        "connection",
        "timed out",
        "timeout"
    )
    foreach ($marker in $noFallbackMarkers) {
        if ($lower.Contains($marker)) { return $false }
    }

    $invalidPatterns = @(
        "(session|conversation)[^`r`n]{0,160}(not found|does not exist|invalid|expired|unavailable|cannot be resumed|can't be resumed)",
        "(not found|does not exist|invalid|expired)[^`r`n]{0,160}(session|conversation)"
    )
    foreach ($pattern in $invalidPatterns) {
        if ($lower -match $pattern) { return $true }
    }
    return $false
}

Set-Location $env:MAINREPO

if ($env:VERIFIER_STAGE -notin @("OPUS", "FABLE")) { throw "VERIFIER_STAGE must be OPUS or FABLE" }
if (-not $env:VERIFIER_RESULT_FILE) { throw "VERIFIER_RESULT_FILE is required" }

$required = @(
    $env:VERIFIER_OVERRIDE,
    $env:VERIFIER_PROMPT,
    $env:VERIFIER_PROTOCOL,
    $env:VERIFIER_RESUME_CONTEXT,
    $env:VERIFIER_EFFECTIVE_SETTINGS,
    $env:VERIFIER_PROGRESS,
    $env:LOOP_MASTER_AGENTS_SNAPSHOT
)
foreach ($path in $required) {
    if (-not (Test-Path $path)) { throw "required verifier runtime file missing: $path" }
}

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    throw "claude CLI is not available on PATH"
}

$override = [IO.File]::ReadAllText($env:VERIFIER_OVERRIDE, [System.Text.Encoding]::UTF8)
$prompt = [IO.File]::ReadAllText($env:VERIFIER_PROMPT, [System.Text.Encoding]::UTF8)
$protocol = [IO.File]::ReadAllText($env:VERIFIER_PROTOCOL, [System.Text.Encoding]::UTF8)
$resumeContext = [IO.File]::ReadAllText($env:VERIFIER_RESUME_CONTEXT, [System.Text.Encoding]::UTF8)

if (-not $env:LOOP_MASTER_AGENTS_SHA256) { throw "LOOP_MASTER_AGENTS_SHA256 is required before Claude" }
$masterAgentsHash = (Get-FileHash -Algorithm SHA256 $env:LOOP_MASTER_AGENTS_SNAPSHOT).Hash.ToLowerInvariant()
if ($masterAgentsHash -ne ([string]$env:LOOP_MASTER_AGENTS_SHA256).ToLowerInvariant()) { throw "pinned master AGENTS snapshot hash mismatch before Claude" }
$masterAgents = [IO.File]::ReadAllText($env:LOOP_MASTER_AGENTS_SNAPSHOT, [System.Text.Encoding]::UTF8)
$masterAgentsContext = @"
# AUTHORITATIVE LOCAL MASTER AGENTS.md

Source: local master snapshot pinned for this logical Loop Engine round
SHA-256: $masterAgentsHash

This exact snapshot is shared with Codex and Claude for the whole logical round. A verifier resume MUST reuse it; do not silently switch to a newer AGENTS.md mid-round. Apply it as authoritative project guidance unless a higher-priority runtime instruction conflicts.

$masterAgents
"@

if ($env:VERIFIER_STAGE -eq "FABLE") {
    foreach ($name in @("LOOP_FINAL_UAT_PERIOD_SLOT", "LOOP_FINAL_UAT_PERIOD_PRIMARY", "LOOP_FINAL_UAT_PERIOD_SECONDARY", "LOOP_FINAL_UAT_PERIOD_POOL_SHA256")) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not $value) { throw "required durable Fable final-audit UAT period environment missing before Claude: $name" }
    }
    $activePeriodSlot = $env:LOOP_FINAL_UAT_PERIOD_SLOT
    $activePeriodPrimary = $env:LOOP_FINAL_UAT_PERIOD_PRIMARY
    $activePeriodSecondary = $env:LOOP_FINAL_UAT_PERIOD_SECONDARY
    $activePeriodPoolSha = $env:LOOP_FINAL_UAT_PERIOD_POOL_SHA256
    $periodPurpose = "Fable final-audit"
}
else {
    foreach ($name in @("LOOP_UAT_PERIOD_SLOT", "LOOP_UAT_PERIOD_PRIMARY", "LOOP_UAT_PERIOD_SECONDARY", "LOOP_UAT_PERIOD_POOL_SHA256")) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not $value) { throw "required durable Opus UAT period environment missing before Claude: $name" }
    }
    $activePeriodSlot = $env:LOOP_UAT_PERIOD_SLOT
    $activePeriodPrimary = $env:LOOP_UAT_PERIOD_PRIMARY
    $activePeriodSecondary = $env:LOOP_UAT_PERIOD_SECONDARY
    $activePeriodPoolSha = $env:LOOP_UAT_PERIOD_POOL_SHA256
    $periodPurpose = "Opus iterative-verifier"
}

$periodContext = @"
# AUTHORITATIVE LOOP UAT PERIOD ALLOCATION

This block overrides any hardcoded UAT period literals in the base verifier prompt for this verifier stage.

Cycle: $env:LOOP_CYCLE
Round: $env:LOOP_ROUND
Verifier stage: $env:VERIFIER_STAGE
Purpose: $periodPurpose
Period pool slot: $activePeriodSlot
Primary PVAM_BOUND_PERIOD: $activePeriodPrimary
Secondary PVAM_BOUND_PERIOD: $activePeriodSecondary
Period pool SHA-256: $activePeriodPoolSha

Mandatory mapping:
- Wherever the base verifier prompt would use literal PVAM_BOUND_PERIOD=990001, use PVAM_BOUND_PERIOD=$activePeriodPrimary instead.
- Wherever the base verifier prompt would use literal PVAM_BOUND_PERIOD=990002, use PVAM_BOUND_PERIOD=$activePeriodSecondary instead.
- Do not use any other UAT period for this stage unless the durable loop ledger explicitly lists it.
- Do not allocate a new period pair while resuming this verifier stage. Resume MUST reuse this exact primary/secondary pair.
- Record the stage, slot, both periods, and pool SHA-256 in UAT_REPORT.md and the relevant evidence.
- If the target environment cannot safely use this exact allocation, return BLOCKED; never reuse an earlier stage's periods.
"@

$authorizationContext = @"
# AUTHORITATIVE UAT WRITE AUTHORIZATION (v16 NON-INTERACTIVE CYCLE GRANT)

The workflow_dispatch that created this durable Cycle grant is the operator's explicit non-interactive preauthorization decision for all later Round/Candidate verifier stages in this Cycle. Do not ask for interactive confirmation.

Authorization ID: $env:LOOP_UAT_AUTHORIZATION_ID
Authorization actor: $env:LOOP_UAT_AUTHORIZATION_ACTOR
Cycle scope SHA-256: $env:LOOP_UAT_CYCLE_SCOPE_SHA256
Stage scope SHA-256: $env:LOOP_UAT_AUTHORIZATION_SCOPE_SHA256
Durable UAT execution ID: $env:LOOP_UAT_EXECUTION_ID
Controller evidence schema: schema-10
Verifier stage: $env:LOOP_UAT_AUTHORIZATION_STAGE
Authorized actions: $env:LOOP_UAT_AUTHORIZED_ACTIONS
Target namespace: $env:LOOP_UAT_TARGET_NAMESPACE
Resource scope: $env:LOOP_UAT_RESOURCE_SCOPE
Target branch: $env:LOOP_UAT_TARGET_BRANCH
Impact scope: $env:LOOP_UAT_IMPACT_SCOPE

Mandatory enforcement:
- There is no interactive authorization step inside CLI execution. Never pause to ask the operator for per-command approval.
- For every Kubernetes/UAT command, write a structured request to .loop-output/verifier-state/$($env:VERIFIER_STAGE.ToLowerInvariant())/proxy-request.json, then invoke only:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/Redemption/Redemption/.loop-engine/uat-action-proxy.ps1
- Do not invoke kubectl, git, sh -c, bash -c, arbitrary PowerShell, or other mutable shell commands directly.
- The proxy is the enforcement boundary: it maps each mutable structured action to required tokens, namespace/resources/branch/impact scope, and fixed command templates.
- Use structured actions, not free-form commands. Important v20 actions: `List`/`Get`/`GetJsonPath`/`Describe`/`Logs`/`Wait`/`RolloutStatus` for scoped observation; `ExecProfile`/`DebugProfile` for versioned read/test profiles; `GitAudit` for fixed read-only git status/log/diff/ls-remote/merge-base; `PytestFull`/`PytestSelected` for governed repo tests; `DaskListDatasets` for the fixed dataset check; `ConsumerLifecycle` for governed primary/secondary Consumer binding; `KafkaScenarioProduce` for the project-delivered WORK-PVAM-02 scenario producer; `ConsumerObserve` for controller-owned delivery-ledger/three-chain/log/business-delta assertions; `RedisDbSize` and `RedisReadExactKeys` for Redis assertions; `UatProof` for mandatory controller-owned cross-period/duplicate/PENDING/int64/pause/p99 proofs; `RedisDeleteExactKeys` for exact durable-execution-marked cleanup; `SetImage`/`Restart`/`Scale`/`Delete` for scoped Kubernetes mutations; and `GitUpdate` for the candidate branch.
- `KafkaScenarioProduce` uses the controller-owned fixed producer embedded in `.loop-engine/uat-action-proxy.ps1`; Candidate-owned `tests/pvam/WORK-PVAM-02/*` is not authorized; use the durable execution identity `$env:LOOP_UAT_EXECUTION_ID`, not the current GitHub Run ID. Do not supply `period_role`; the controller-owned scenario-to-period/binding policy selects primary/secondary and requires the matching ConsumerLifecycle binding. Fable must use the final-audit period pair, never the Opus pair.
- `GitUpdate` requires `node` plus `verification_pod` (and optional `verification_container`). The proxy discovers the Redemption repo by exact remote URL, rejects a dirty host worktree before mutation, validates remote/host/pod HEAD equality to `pushed-sha.txt`, and performs mandatory UID-bound node-debugger cleanup.
- Before repo tests or Kafka UAT, run `GitUpdate`; every repo-backed proxy action independently re-verifies the Pod/NFS HEAD equals the Candidate SHA.
- Use `ConsumerLifecycle` `bind-primary` before primary-period scenarios and `bind-secondary` for the period-switch path. Do not supply `calc_month`, Deployment, container, or Pod unless repeating the exact version-controlled values: the controller resolves the unique Running+Ready scheduler Pod and starts/replaces `MessageConsumer.PvEventConsumer` there as a governed temporary process.
- After the final required ConsumerObserve and UatProof actions for the stage, invoke `ConsumerLifecycle restore`. Restore stops only the process owned by this durable execution ID; it does not restart or mutate the scheduler Deployment.
- ConsumerLifecycle runtime mode, namespace, scheduler host Deployment/container, Pod prefix, repository path, Kafka bootstrap, and role-specific calc months come from the version-controlled `consumer_runtime_target`. Never guess or broaden a target. Binding/status/restore require `exec`; the pending-recovery proof additionally requires `restart` because it intentionally replaces the governed Consumer process.
- For Kafka, Redis, ConsumerObserve, selected pytest, and Dask profile requests, omit Pod/container or repeat only the exact scheduler Pod/container resolved by the proxy. The proxy rejects stale or worker-Pod targets. Auxiliary Python commands load Redis/Dask connection settings from the Candidate `Model.Config` inside the scheduler process and never place credentials in request arguments or evidence.
- After Kafka scenarios, run `ConsumerObserve` for the required scenario set. Positive paths must prove `DISPATCHED` plus all three idempotency namespaces (`system:idempotency`, `placement`, `elite`) before exact cleanup.
- Opus must also execute every policy-required `UatProof`: `cross-period-refund-routing`, `duplicate-no-double`, `pending-dispatched-recovery`, `int64-end-to-end`, `pause-rebalance`, and `dispatch-p99`. Fable executes its policy-defined subset. These are controller evidence gates, not report prose.
- `RedisReadExactKeys` proof mode uses only controller-derived exact keys. For Opus run `cross-period-refund-ledgers` and `duplicate-ledgers`; Fable runs its policy-defined subset.
- Every `ConsumerObserve` must report `business_value_proof_ok=true`; cross-period and duplicate must carry exact UserStats business deltas, and negative scenarios must prove unchanged UserStats plus zero Redis residue.
- The `dask-actor-rebuild` ExecProfile is the only governed project actor rebuild entrypoint and runs `python3 -m User.UserService` from the discovered Redemption repository root; it requires both `exec` and `restart`.
- `DebugProfile` and `GitUpdate` are synchronous: a debug Pod is not success until its container terminates, logs/exit code are captured, and that exact Pod UID is cleaned.
- Any mutable action not listed in Authorized actions is NOT authorized; the proxy must deny it before execution.
- If a needed action/profile is outside the durable Cycle scope or absent from the governed policy, return BLOCKED with the missing action/profile. Do not bypass the proxy and do not infer broader authority.
- Do not create or edit `.loop-output/controller-evidence/**`; only the proxy/controller writes that audit surface. Record authorization ID, durable UAT execution ID, Cycle scope SHA, stage scope SHA, action name, required token(s), proxy evidence path, and the actual proxy stage period slot/primary/secondary in UAT_REPORT.md/evidence.
"@

$kubernetesContext = @"
# AUTHORITATIVE KUBERNETES RUNTIME CONTRACT

The local master AGENTS.md contract governs Kubernetes access for this Loop Engine run:
- kubectl executable: D:\Redemption\Redemption\K8S\kubectl.exe
- kubeconfig: D:\Redemption\Redemption\K8S\admin.conf
- The first Kubernetes API operation in a verifier stage must be the read-only readyz probe:
  D:\Redemption\Redemption\K8S\kubectl.exe --kubeconfig D:\Redemption\Redemption\K8S\admin.conf get --raw=/readyz --request-timeout=15s
- This supersedes any root-level admin.conf, temporary cached kubectl path, or other Kubernetes path in the base verifier prompt.
- Do not copy credentials or kubeconfig contents into UAT_REPORT.md or evidence.
"@

$compatibilityContext = @"
# BASE PROMPT COMPATIBILITY OVERRIDES

The base verifier prompt predates the staged v15 verifier contract. Treat any conflicting legacy instruction as superseded by this runtime block:
- OPUS writes only .loop-output/opus-result.txt with PRECHECK_PASS, REJECTED, or BLOCKED. OPUS MUST NOT write .loop-output/uat-result.txt.
- FABLE writes the final .loop-output/uat-result.txt with PASS, REJECTED, or BLOCKED.
- There is still exactly one formal .loop-output/UAT_REPORT.md; Fable appends its final-audit section after the immutable Opus byte prefix.
- If the base prompt says to wait for operator confirmation before stage two or before individual writes, do not wait for operator confirmation: that legacy interactive rule is superseded by the durable Cycle preauthorization above. Continue automatically within the bound proxy-enforced scope; never request interactive approval from a CLI verifier.
- Kubernetes paths and first-connection behavior are defined by the AUTHORITATIVE KUBERNETES RUNTIME CONTRACT above, not by legacy root-level admin.conf examples.
"@

if ($env:VERIFIER_STAGE -eq "OPUS") {
    $stageContext = @"
# OPUS ITERATIVE VERIFIER

You are the iterative engineering verifier, not the final release auditor.
- Perform broad independent code review plus the real UAT required by the base verifier contract.
- For every Kubernetes/UAT command, use the unified structured `uat-action-proxy.ps1` contract from the authorization block; do not call kubectl or arbitrary shell directly.
- Drive the evidence/checkpoint plan to completion and aggressively find concrete implementation defects.
- The only allowed stage verdicts are PRECHECK_PASS, REJECTED, or BLOCKED. GitHub Actions maps PRECHECK_PASS to Loop Core NO_BUG and REJECTED to BUG_FOUND.
- If returning REJECTED/BUG_FOUND, every finding in UAT_REPORT.md must be structured with: ID, Severity, File, Location, Problem description, Why it is a problem, Required fix, and Acceptance criteria.
- PRECHECK_PASS means this candidate is stable enough to enter Fable final audit; it is NOT final PASS.
- You MUST NOT write final PASS and MUST NOT create or update .loop-output/uat-result.txt.
- Write the stage verdict as a bare word to: $env:VERIFIER_RESULT_FILE
- Keep the formal report filename exactly .loop-output/UAT_REPORT.md. Create/update the Opus verification body there and record all evidence needed by the later final auditor.
- Fable is the only verifier stage allowed to produce final PASS.
"@
}
else {
    $stageContext = @"
# FABLE FINAL AUDITOR

You are the independent final auditor, not the iterative debug verifier.
- Run only because Opus already returned PRECHECK_PASS for this exact candidate.
- Independently re-read the final candidate, pinned master AGENTS.md, governing contract, Opus UAT evidence, and coverage gaps. Do not merely endorse Opus.
- Audit evidence authenticity/sufficiency, search for shared blind spots and uncovered failure paths, and selectively rerun critical P0/P1 or suspicious real UAT using the dedicated fresh final-audit period pair above.
- Filesystem setting sources are disabled for this final-audit session to prevent inherited shell permissions. When the pinned AGENTS.md requires a project Skill, read the required .claude/skills/<skill>/SKILL.md file directly and follow it before the applicable review task.
- For every Kubernetes/UAT command, use the unified structured `uat-action-proxy.ps1` contract from the authorization block; do not call kubectl, git, git bundle, or arbitrary PowerShell directly.
- The only allowed final verdicts are PASS, REJECTED, or BLOCKED. You are the only stage allowed to produce final PASS.
- Write the final verdict as a bare word to: $env:VERIFIER_RESULT_FILE
- There is still exactly one formal report: .loop-output/UAT_REPORT.md. You MUST preserve the exact existing UAT_REPORT.md content produced by Opus and append a new section titled `## Fable Final Audit`; do not delete, rewrite, or reorder the Opus evidence prefix.
- If you find any defect, return REJECTED. GitHub Actions maps this to FINAL_REJECT and PAUSED_AWAITING_USER; it MUST NOT invoke Codex automatically. Only a later manual workflow_dispatch next-cycle may continue, and that Cycle runs Codex rework followed by Opus before Fable can be considered again.
"@
}

$freshPrompt = @"
$override

$masterAgentsContext

$prompt

$periodContext

$authorizationContext

$kubernetesContext

$compatibilityContext

$protocol

$stageContext

$resumeContext
"@

$resumePrompt = @"
$masterAgentsContext

$periodContext

$authorizationContext

$kubernetesContext

$compatibilityContext

$protocol

$stageContext

$resumeContext

Continue the existing verifier session from the durable checkpoint. The checkpoint ledger is authoritative. Do not repeat DONE tasks. For RETRY_REQUIRED tasks, verify durable evidence and observable target state before repeating side effects.
"@

$sessionFile = Join-Path $env:VERIFIER_STATE_DIR "claude-session.txt"
$reuseSession = ($env:CLAUDE_REUSE_SESSION -eq "true")
$resumeSessionId = $null
if ($reuseSession -and (Test-Path $sessionFile)) {
    $candidateSession = ([IO.File]::ReadAllText($sessionFile, [System.Text.Encoding]::UTF8)).Trim()
    if ($candidateSession) { $resumeSessionId = $candidateSession }
}

$logDir = Join-Path $env:VERIFIER_STATE_DIR "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$attemptTag = "$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT"
$exitPath = Join-Path $logDir "claude-exit-$attemptTag.txt"
$toolNames = @{}
$thinkingDeltaCount = 0

function Process-ClaudeLine([string]$Line, [System.IO.StreamWriter]$RawWriter) {
    $RawWriter.WriteLine($Line)
    if (-not $Line.Trim()) { return }

    try {
        $evt = $Line | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        Write-Host "[RAW] $(Compact-Text $Line 1200)"
        return
    }

    if ($evt.type -eq "system" -and $evt.subtype -eq "init") {
        if ($evt.session_id) {
            Write-Utf8NoBom $sessionFile ([string]$evt.session_id + "`n")
            Write-Host "[SESSION] $($evt.session_id)"
        }
        if ($evt.model) { Write-Host "[MODEL] $($evt.model)" }
        return
    }

    if ($evt.type -eq "system" -and $evt.subtype -eq "api_retry") {
        Write-Host "[API-RETRY] attempt=$($evt.attempt)/$($evt.max_retries) delay_ms=$($evt.retry_delay_ms) error=$($evt.error) status=$($evt.error_status)"
        return
    }

    if ($evt.type -eq "stream_event") {
        if ($evt.event.type -eq "content_block_start" -and $evt.event.content_block.type -eq "thinking") {
            Write-Host "[THINK] reasoning block started..."
            $script:thinkingDeltaCount = 0
            return
        }
        if ($evt.event.type -eq "content_block_delta" -and $evt.event.delta.type -eq "thinking_delta") {
            $script:thinkingDeltaCount++
            if (($script:thinkingDeltaCount % 250) -eq 0) {
                Write-Host "[THINK] still reasoning..."
            }
            return
        }
        return
    }

    if ($evt.type -eq "assistant") {
        $scope = "MAIN"
        if ($evt.parent_tool_use_id) { $scope = "SUBAGENT:$($evt.parent_tool_use_id)" }
        foreach ($block in @($evt.message.content)) {
            switch ($block.type) {
                "thinking" {
                    $text = Compact-Text $block.thinking 3000
                    if ($text) {
                        Write-Host ""
                        Write-Host "[THINK][$scope]"
                        Write-Host $text
                    }
                }
                "redacted_thinking" {
                    Write-Host "[THINK][$scope] redacted/omitted by model service"
                }
                "text" {
                    $text = Compact-Text $block.text 4000
                    if ($text) {
                        Write-Host ""
                        Write-Host "[CLAUDE][$scope]"
                        Write-Host $text
                    }
                }
                "tool_use" {
                    if ($block.id) { $script:toolNames[[string]$block.id] = [string]$block.name }
                    Write-Host ""
                    Write-Host (Tool-Label $block)
                }
            }
        }
        return
    }

    if ($evt.type -eq "user") {
        $scope = "MAIN"
        if ($evt.parent_tool_use_id) { $scope = "SUBAGENT:$($evt.parent_tool_use_id)" }
        foreach ($block in @($evt.message.content)) {
            if ($block.type -eq "tool_result") {
                $name = "tool"
                if ($block.tool_use_id -and $script:toolNames.ContainsKey([string]$block.tool_use_id)) {
                    $name = $script:toolNames[[string]$block.tool_use_id]
                }
                $status = "OK"
                if ($block.is_error -eq $true) { $status = "ERROR" }
                $resultText = Compact-Text (Tool-Result-Text $block) 1800
                Write-Host "[TOOL-RESULT][$scope][$status][$name]"
                if ($resultText) { Write-Host $resultText }
            }
        }
        return
    }

    if ($evt.type -eq "result") {
        if ($evt.session_id) {
            Write-Utf8NoBom $sessionFile ([string]$evt.session_id + "`n")
        }
        Write-Host ""
        Write-Host "[RESULT] subtype=$($evt.subtype) is_error=$($evt.is_error)"
        if ($evt.result) { Write-Host (Compact-Text $evt.result 5000) }
        if ($evt.total_cost_usd) { Write-Host "[COST] usd=$($evt.total_cost_usd)" }
        return
    }
}

$baseClaudeArgs = @(
    "-p",
    "--permission-mode", "dontAsk",
    "--model", $env:CLAUDE_MODEL,
    "--effort", $env:CLAUDE_EFFORT,
    "--output-format", "stream-json",
    "--verbose",
    "--include-partial-messages",
    "--forward-subagent-text",
    "--settings", $env:VERIFIER_EFFECTIVE_SETTINGS,
    "--add-dir", "D:\Redemption\Worktrees\pvam-work02-m2-float64-test",
    "--add-dir", "D:\Redemption\Worktrees\pvam-governance"
)

# v13 disables user/project/local setting sources for both verifier stages so a
# local Bash/PowerShell/kubectl allow cannot bypass the unified proxy. Pinned
# AGENTS.md and required project Skills are injected/read explicitly.
$baseClaudeArgs += @("--setting-sources=")
$env:CLAUDE_CODE_DISABLE_AUTO_MEMORY = "1"
Write-Host "[VERIFIER-ISOLATION] filesystem setting sources disabled for $env:VERIFIER_STAGE; unified proxy is authoritative"

function Invoke-ClaudeAttempt([string]$PromptText, [object[]]$Args, [string]$Label) {
    $rawPath = Join-Path $logDir "claude-stream-$attemptTag-$Label.jsonl"
    $stderrPath = Join-Path $logDir "claude-stderr-$attemptTag-$Label.log"
    $rawWriter = New-Object System.IO.StreamWriter($rawPath, $false, $Utf8NoBom)
    $rawWriter.AutoFlush = $true
    $claudeExit = $null
    $previousErrorActionPreference = $ErrorActionPreference

    Write-Host ""
    Write-Host "=== CLAUDE ATTEMPT: $Label ==="
    Write-Host "raw_jsonl=$rawPath"

    try {
        # Windows PowerShell 5.1 can promote native stderr to NativeCommandError.
        # Claude --verbose may legitimately write stderr, so only the native
        # invocation is downgraded to Continue. Script logic remains Stop.
        $ErrorActionPreference = "Continue"
        $PromptText | & claude @Args 2> $stderrPath | ForEach-Object {
            Process-ClaudeLine ([string]$_) $rawWriter
        }
        $claudeExit = $LASTEXITCODE
    }
    catch {
        Write-Host "[CLAUDE-PIPELINE-ERROR] $($_.Exception.Message)"
        if ($null -eq $claudeExit) { $claudeExit = 1 }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        $rawWriter.Dispose()
    }

    if ($null -eq $claudeExit) { $claudeExit = 1 }
    $stderr = Read-TailText $stderrPath 65536
    if ($stderr.Trim()) {
        Write-Host ""
        Write-Host "[CLAUDE-STDERR][$Label]"
        Write-Host (Compact-Text $stderr 3000)
    }
    Write-Host "[CLAUDE-ATTEMPT-EXIT][$Label] $claudeExit"

    return [pscustomobject]@{
        ExitCode = [int]$claudeExit
        RawPath = $rawPath
        StderrPath = $stderrPath
        Stderr = $stderr
        Label = $Label
    }
}

Write-Host "=== CLAUDE VERIFIER LIVE VIEW ==="
Write-Host "verifier_stage=$env:VERIFIER_STAGE"
Write-Host "candidate=$env:VERIFIER_CANDIDATE_SHA"
Write-Host "fingerprint=$env:VERIFIER_FINGERPRINT"
Write-Host "checkpoint_mode=$env:VERIFIER_RESUME_MODE"

if ($resumeSessionId) {
    Write-Host "[RESUME] Claude session $resumeSessionId"
    $resumeArgs = @($baseClaudeArgs) + @("--resume", $resumeSessionId)
    $result = Invoke-ClaudeAttempt $resumePrompt $resumeArgs "resume"

    if ($result.ExitCode -ne 0) {
        $classificationText = $result.Stderr + "`n" + (Read-TailText $result.RawPath 65536)
        if (Test-ResumeSessionInvalid $classificationText) {
            Write-Host "[RESUME-FALLBACK] saved session is invalid/unavailable; starting a fresh session from the durable checkpoint"
            Remove-Item -Force -ErrorAction SilentlyContinue $sessionFile
            $result = Invoke-ClaudeAttempt $freshPrompt $baseClaudeArgs "fresh-fallback"
        }
        else {
            Write-Host "[RESUME-NO-FALLBACK] failure is not proven to be an invalid session; preserving checkpoint/session for a later retry"
        }
    }
}
else {
    Write-Host "[NEW] starting a new Claude verifier session"
    $result = Invoke-ClaudeAttempt $freshPrompt $baseClaudeArgs "fresh"
}

$claudeExit = $result.ExitCode
$exitText = "exit_code=$claudeExit`nlabel=$($result.Label)`nrun_id=$env:GITHUB_RUN_ID`nrun_attempt=$env:GITHUB_RUN_ATTEMPT`nended_at=$((Get-Date).ToUniversalTime().ToString('o'))`n"
Write-Utf8NoBom $exitPath $exitText

Write-Host ""
Write-Host "[CLAUDE-EXIT] $claudeExit"
Write-Host "[CHECKPOINT] $env:VERIFIER_PROGRESS"
if ($claudeExit -ne 0) {
    Write-Error "claude exited $claudeExit; durable verifier checkpoint is preserved for resume"
    exit $claudeExit
}
