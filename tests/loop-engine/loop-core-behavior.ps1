param(
    [ValidateSet(
        "all",
        "test-01-opus-r1-bug",
        "test-02-opus-r2-bug",
        "test-03-opus-r3-bug",
        "test-04-opus-no-bug-fable",
        "test-05-fable-pass",
        "test-06-fable-reject",
        "test-07-next-cycle",
        "test-08-opus-findings-next-cycle",
        "test-09-fable-findings-next-cycle",
        "test-10-controller-only",
        "lc01-v20-fable-reject-missing-next-round",
        "lc01-v20-fable-reject-active-next-round",
        "lc01-v20-opus-three-rejects",
        "lc03-stale-fable-allocation-opus-reject",
        "r2-01-legacy-fable-reject-then-later-complete",
        "r2-01-schema4-self-heal-after-later-complete",
        "r2-02-pre-marker-fable-reject",
        "r3-01-fable-reject-then-later-fable-pass",
        "r3-03-paused-fable-reject-idempotent",
        "r4-01-completed-after-rework-idempotent",
        "r7-fable-reject-cannot-be-claimed-as-opus-bug",
        "r7-opus-reject-cannot-be-claimed-as-fable-reject",
        "r7-pass-cannot-carry-nonfinal-pass-results",
        "r7-blocked-source-mismatch-fails-closed",
        "r8-reconcile-opus-reject-ignores-retained-fable-marker",
        "r8-reconcile-round3-opus-reject-keeps-opus-round-limit",
        "r8-reconcile-opus-blocked-ignores-retained-fable-marker",
        "r8-reconcile-fable-pass-stays-final-pass",
        "r8-reconcile-fable-reject-stays-final-reject",
        "r8-reconcile-fable-blocked-stays-blocked"
    )]
    [string]$Scenario = "all"
)

$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$RepoRoot = $env:MAINREPO
if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$StateScript = Join-Path $RepoRoot ".loop-engine\loop-state.ps1"
$PoolFile = Join-Path $RepoRoot ".loop-engine\uat-period-pool.json"
if (-not (Test-Path -LiteralPath $StateScript -PathType Leaf)) { throw "loop-state.ps1 missing: $StateScript" }
if (-not (Test-Path -LiteralPath $PoolFile -PathType Leaf)) { throw "UAT period pool missing: $PoolFile" }
$PoolHash = (Get-FileHash -Algorithm SHA256 $PoolFile).Hash.ToLowerInvariant()
$BehaviorEnvironmentNames = @(
    "OUTDIR", "WORKTREE", "SSH_URL", "BRANCH", "UAT_PERIOD_POOL_FILE",
    "LOOP_STATE_FILE", "LOOP_CYCLES_DIR", "LOOP_MASTER_AGENTS_SHA256",
    "GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"
)
$originalEnvironment = @{}
foreach ($name in $BehaviorEnvironmentNames) {
    $originalEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

$Pool = [IO.File]::ReadAllText($PoolFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$Pairs = @($Pool.pairs | Sort-Object slot)
if ($Pairs.Count -lt 6) { throw "behavior suite requires at least 6 UAT period pairs" }

function Assert-Equal($Actual, $Expected, [string]$Message) {
    if ([string]$Actual -ne [string]$Expected) {
        throw "$Message expected='$Expected' actual='$Actual'"
    }
}

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Write-Json([string]$Path, $Object) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) { New-Item -ItemType Directory -Force $parent | Out-Null }
    [IO.File]::WriteAllText($Path, (($Object | ConvertTo-Json -Depth 80) + "`n"), $Utf8NoBom)
}

function Write-Text([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) { New-Item -ItemType Directory -Force $parent | Out-Null }
    [IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function New-TestContext([string]$Name) {
    $root = Join-Path $env:TEMP ("loop-core-behavior-" + $Name + "-" + [Guid]::NewGuid().ToString("N"))
    $repo = Join-Path $root "repo"
    $out = Join-Path $root "out"
    New-Item -ItemType Directory -Force -Path @($repo, $out) | Out-Null
    git -C $repo init -q
    if ($LASTEXITCODE -ne 0) { throw "git init failed for $Name" }
    git -C $repo config user.email "loop-core-behavior@example.invalid"
    git -C $repo config user.name "Loop Core Behavior"
    Write-Text (Join-Path $repo "README.txt") "loop core behavior`n"
    git -C $repo add README.txt
    git -C $repo commit -q -m "baseline"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed for $Name" }
    git -C $repo branch -M smoke
    if ($LASTEXITCODE -ne 0) { throw "git branch rename failed for $Name" }
    $sha = (git -C $repo rev-parse HEAD).Trim().ToLowerInvariant()
    if ($sha -notmatch '^[0-9a-f]{40}$') { throw "invalid test candidate SHA: $sha" }

    return [pscustomobject][ordered]@{
        name = $Name
        root = $root
        repo = $repo
        out = $out
        state = (Join-Path $out "loop-state.json")
        cycles = (Join-Path $out "cycles")
        github_output = (Join-Path $root "github-output.txt")
        github_env = (Join-Path $root "github-env.txt")
        sha = $sha
        branch = "smoke"
    }
}

function Use-TestContext($Context) {
    $env:OUTDIR = $Context.out
    $env:WORKTREE = $Context.repo
    $env:SSH_URL = "smoke://unused"
    $env:BRANCH = $Context.branch
    $env:UAT_PERIOD_POOL_FILE = $PoolFile
    $env:LOOP_STATE_FILE = $Context.state
    $env:LOOP_CYCLES_DIR = $Context.cycles
    $env:LOOP_MASTER_AGENTS_SHA256 = ("a" * 64)
    $env:GITHUB_OUTPUT = $Context.github_output
    $env:GITHUB_ENV = $Context.github_env
    $env:GITHUB_RUN_ID = "1"
    $env:GITHUB_RUN_ATTEMPT = "1"
    Write-Text $Context.github_output ""
    Write-Text $Context.github_env ""
}

function Reset-StepOutput($Context) { Write-Text $Context.github_output "" }

function Get-StepOutput($Context, [string]$Name) {
    if (-not (Test-Path $Context.github_output)) { return "" }
    $prefix = $Name + "="
    $matches = @(Get-Content -LiteralPath $Context.github_output | Where-Object { ([string]$_).StartsWith($prefix, [StringComparison]::Ordinal) })
    if ($matches.Count -lt 1) { return "" }
    return ([string]$matches[-1]).Substring($prefix.Length)
}

function Read-State($Context) {
    return ([IO.File]::ReadAllText($Context.state, [System.Text.Encoding]::UTF8) | ConvertFrom-Json)
}

function New-Report($Context, [int]$Cycle, [int]$Round, [string]$Label) {
    $path = Join-Path $Context.cycles ("cycle-{0}\round-{1}\UAT_REPORT.md" -f $Cycle, $Round)
    Write-Text $path ("# " + $Label + "`n")
    return $path
}

function New-RoundObject(
    $Context,
    [int]$Round,
    [string]$Phase,
    [string]$Action,
    [string]$Verdict,
    [string]$OpusResult,
    [string]$FableResult,
    [string]$ReportPath,
    [string]$PreviousReport,
    [string]$FindingsSource,
    [string]$FindingsRef,
    [bool]$WithCandidate = $true
) {
    return [pscustomobject][ordered]@{
        round = $Round
        action = $Action
        phase = $Phase
        producer_base_sha = $Context.sha
        previous_report = $PreviousReport
        findings_source = $FindingsSource
        findings_ref = $FindingsRef
        master_agents_sha256 = ("a" * 64)
        candidate_sha = $(if ($WithCandidate) { $Context.sha } else { $null })
        opus_result = $(if ($OpusResult) { $OpusResult } else { $null })
        fable_result = $(if ($FableResult) { $FableResult } else { $null })
        verdict = $(if ($Verdict) { $Verdict } else { $null })
        report_path = $(if ($ReportPath) { $ReportPath } else { $null })
        started_at = "2026-08-24T00:00:00Z"
        completed_at = $(if ($Phase -eq "COMPLETE") { "2026-08-24T00:01:00Z" } else { $null })
        last_run_id = "1"
        last_run_attempt = "1"
    }
}

function New-StateObject($Context, [int]$Schema, [string]$Status, [string]$Stage, [int]$CurrentRound, [object[]]$Rounds, [string]$PauseReason = "", [string]$FindingsSource = "", [string]$FindingsRef = "") {
    $cycle = [pscustomobject][ordered]@{
        cycle = 1
        status = $Status
        candidate_branch = $Context.branch
        cycle_start_sha = $Context.sha
        current_candidate_sha = $Context.sha
        findings_source = $(if ($FindingsSource) { $FindingsSource } else { $null })
        findings_ref = $(if ($FindingsRef) { $FindingsRef } else { $null })
        previous_cycle_report = ""
        started_at = "2026-08-24T00:00:00Z"
        completed_at = $null
        rounds = @($Rounds)
    }
    return [pscustomobject][ordered]@{
        schema_version = $Schema
        work_id = "WORK-PVAM-02"
        uat_period_pool_sha256 = $PoolHash
        max_rounds_per_cycle = 3
        candidate_branch = $Context.branch
        current_candidate_sha = $Context.sha
        current_cycle = 1
        current_round = $CurrentRound
        stage = $Stage
        status = $Status
        pause_reason = $(if ($PauseReason) { $PauseReason } else { $null })
        opus_result = $null
        fable_result = $null
        findings_source = $(if ($FindingsSource) { $FindingsSource } else { $null })
        findings_ref = $(if ($FindingsRef) { $FindingsRef } else { $null })
        created_at = "2026-08-24T00:00:00Z"
        updated_at = "2026-08-24T00:00:00Z"
        cycles = @($cycle)
    }
}

function Add-LegacyPeriodFields($RoundObject, [int]$OpusSlot, [int]$FableSlot = 0, [string]$FinalVerdict = "") {
    $opusPair = @($Pairs | Where-Object { [int]$_.slot -eq $OpusSlot } | Select-Object -First 1)[0]
    $RoundObject | Add-Member -NotePropertyName uat_period_slot -NotePropertyValue ([int]$opusPair.slot) -Force
    $RoundObject | Add-Member -NotePropertyName uat_period_primary -NotePropertyValue ([int]$opusPair.primary_period) -Force
    $RoundObject | Add-Member -NotePropertyName uat_period_secondary -NotePropertyValue ([int]$opusPair.secondary_period) -Force
    $RoundObject | Add-Member -NotePropertyName uat_period_pool_sha256 -NotePropertyValue $PoolHash -Force
    if ($FableSlot -gt 0) {
        $fablePair = @($Pairs | Where-Object { [int]$_.slot -eq $FableSlot } | Select-Object -First 1)[0]
        $RoundObject | Add-Member -NotePropertyName final_audit_uat_period_slot -NotePropertyValue ([int]$fablePair.slot) -Force
        $RoundObject | Add-Member -NotePropertyName final_audit_uat_period_primary -NotePropertyValue ([int]$fablePair.primary_period) -Force
        $RoundObject | Add-Member -NotePropertyName final_audit_uat_period_secondary -NotePropertyValue ([int]$fablePair.secondary_period) -Force
        $RoundObject | Add-Member -NotePropertyName final_audit_uat_period_pool_sha256 -NotePropertyValue $PoolHash -Force
    }
    if ($FinalVerdict) {
        $RoundObject | Add-Member -NotePropertyName final_audit_evidence_verified -NotePropertyValue "true" -Force
        $RoundObject | Add-Member -NotePropertyName final_audit_evidence_verified_verdict -NotePropertyValue $FinalVerdict -Force
        $RoundObject | Add-Member -NotePropertyName final_audit_evidence_verified_protected_sha256 -NotePropertyValue ("c" * 64) -Force
        $RoundObject | Add-Member -NotePropertyName final_audit_evidence_verified_at -NotePropertyValue "2026-08-24T00:01:00Z" -Force
    }
}

function Invoke-Prepare($Context, [string]$Mode) {
    Reset-StepOutput $Context
    & $StateScript -Operation Prepare -RunMode $Mode
    if ($LASTEXITCODE -ne 0) { throw "Prepare $Mode failed for $($Context.name): exit=$LASTEXITCODE" }
}

function Invoke-Scenario01 {
    $c = New-TestContext "test01"
    try {
        Use-TestContext $c
        $report = New-Report $c 1 1 "Opus BUG_FOUND"
        $r1 = New-RoundObject $c 1 "COMPLETE" "construct" "REJECTED" "BUG_FOUND" "" $report "" "" ""
        $state = New-StateObject $c 4 "RUNNING" "OPUS_REVIEW" 1 @($r1)
        Write-Json $c.state $state
        Invoke-Prepare $c "auto"
        Assert-Equal (Get-StepOutput $c "start_round") "2" "TEST-01 start_round"
        Assert-Equal (Get-StepOutput $c "start_action") "rework" "TEST-01 start_action"
        Assert-Equal (Get-StepOutput $c "findings_source") "OPUS" "TEST-01 findings source"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-Scenario02 {
    $c = New-TestContext "test02"
    try {
        Use-TestContext $c
        $report1 = New-Report $c 1 1 "Opus BUG_FOUND r1"
        $report2 = New-Report $c 1 2 "Opus BUG_FOUND r2"
        $r1 = New-RoundObject $c 1 "COMPLETE" "construct" "REJECTED" "BUG_FOUND" "" $report1 "" "" ""
        $r2 = New-RoundObject $c 2 "COMPLETE" "rework" "REJECTED" "BUG_FOUND" "" $report2 $report1 "OPUS" $report1
        $state = New-StateObject $c 4 "RUNNING" "OPUS_REVIEW" 2 @($r1, $r2) "" "OPUS" $report2
        Write-Json $c.state $state
        Invoke-Prepare $c "auto"
        Assert-Equal (Get-StepOutput $c "start_round") "3" "TEST-02 start_round"
        Assert-Equal (Get-StepOutput $c "start_action") "rework" "TEST-02 start_action"
        Assert-Equal (Get-StepOutput $c "findings_source") "OPUS" "TEST-02 findings source"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-Scenario03 {
    $c = New-TestContext "test03"
    try {
        Use-TestContext $c
        $reports = @()
        $rounds = @()
        for ($i = 1; $i -le 3; $i++) {
            $reports += New-Report $c 1 $i ("Opus BUG_FOUND r" + $i)
            $prior = if ($i -gt 1) { $reports[$i - 2] } else { "" }
            $source = if ($i -gt 1) { "OPUS" } else { "" }
            $rounds += New-RoundObject $c $i "COMPLETE" $(if ($i -eq 1) { "construct" } else { "rework" }) "REJECTED" "BUG_FOUND" "" $reports[$i - 1] $prior $source $prior
        }
        $state = New-StateObject $c 4 "RUNNING" "OPUS_REVIEW" 3 $rounds "" "OPUS" $reports[2]
        Write-Json $c.state $state
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        Assert-Equal $after.status "PAUSED_AWAITING_USER" "TEST-03 status"
        Assert-Equal $after.pause_reason "OPUS_ROUND_LIMIT" "TEST-03 pause_reason"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "TEST-03 start_action"
        Assert-Equal ([int]$after.current_cycle) 1 "TEST-03 must not create cycle 2"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-Scenario04 {
    $c = New-TestContext "test04"
    try {
        Use-TestContext $c
        $r1 = New-RoundObject $c 1 "VERIFYING" "construct" "" "" "" "" "" "" ""
        $state = New-StateObject $c 4 "RUNNING" "OPUS_REVIEW" 1 @($r1)
        Write-Json $c.state $state
        Invoke-Prepare $c "auto"
        $state = Read-State $c
        $round = @($state.cycles[0].rounds)[0]
        $opusDir = Join-Path $c.out "verifier-state\opus"
        New-Item -ItemType Directory -Force $opusDir | Out-Null
        $progress = [ordered]@{
            schema_version = 5
            verifier_stage = "OPUS"
            candidate_sha = $c.sha
            uat_period_slot = [int]$round.uat_period_slot
            uat_period_primary = [int]$round.uat_period_primary
            uat_period_secondary = [int]$round.uat_period_secondary
            uat_period_pool_sha256 = [string]$round.uat_period_pool_sha256
            status = "COMPLETE"
            final_verdict = "PRECHECK_PASS"
        }
        Write-Json (Join-Path $opusDir "verifier-progress.json") $progress
        Write-Text (Join-Path $c.out "opus-result.txt") "PRECHECK_PASS`n"
        & $StateScript -Operation AllocateFinalAuditPeriod -Cycle 1 -Round 1
        if ($LASTEXITCODE -ne 0) { throw "TEST-04 AllocateFinalAuditPeriod failed" }
        $after = Read-State $c
        Assert-Equal $after.stage "FABLE_FINAL_REVIEW" "TEST-04 stage"
        Assert-Equal $after.status "RUNNING" "TEST-04 status"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-Scenario05 {
    $c = New-TestContext "test05"
    try {
        Use-TestContext $c
        $r1 = New-RoundObject $c 1 "COMPLETE" "construct" "PASS" "NO_BUG" "FINAL_PASS" "" "" "" ""
        $state = New-StateObject $c 4 "RUNNING" "FABLE_FINAL_REVIEW" 1 @($r1)
        Write-Json $c.state $state
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        Assert-Equal $after.status "COMPLETED" "TEST-05 status"
        Assert-Equal $after.stage "COMPLETED" "TEST-05 stage"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "TEST-05 start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-Scenario06 {
    $c = New-TestContext "test06"
    try {
        Use-TestContext $c
        $report = New-Report $c 1 1 "Fable FINAL_REJECT"
        $r1 = New-RoundObject $c 1 "COMPLETE" "construct" "REJECTED" "NO_BUG" "FINAL_REJECT" $report "" "" ""
        $state = New-StateObject $c 4 "RUNNING" "FABLE_FINAL_REVIEW" 1 @($r1)
        Write-Json $c.state $state
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        Assert-Equal $after.status "PAUSED_AWAITING_USER" "TEST-06 status"
        Assert-Equal $after.pause_reason "FABLE_FINAL_REJECT" "TEST-06 pause_reason"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "TEST-06 start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function New-PausedState($Context, [string]$Reason, [string]$Source, [int]$RoundNumber) {
    $report = New-Report $Context 1 $RoundNumber ($Source + " findings")
    $opus = if ($Source -eq "OPUS") { "BUG_FOUND" } else { "NO_BUG" }
    $fable = if ($Source -eq "FABLE") { "FINAL_REJECT" } else { "" }
    $r = New-RoundObject $Context $RoundNumber "COMPLETE" $(if ($RoundNumber -eq 1) { "construct" } else { "rework" }) "REJECTED" $opus $fable $report "" "" ""
    $state = New-StateObject $Context 4 "PAUSED_AWAITING_USER" "PAUSED_AWAITING_USER" $RoundNumber @($r) $Reason $Source $report
    $state.cycles[0].status = "PAUSED_AWAITING_USER"
    $state.cycles[0].findings_source = $Source
    $state.cycles[0].findings_ref = $report
    $state.opus_result = $opus
    $state.fable_result = $(if ($fable) { $fable } else { $null })
    return [pscustomobject]@{ state = $state; report = $report }
}

function Invoke-Scenario07 {
    $c = New-TestContext "test07"
    try {
        Use-TestContext $c
        $paused = New-PausedState $c "OPUS_ROUND_LIMIT" "OPUS" 3
        Write-Json $c.state $paused.state
        Invoke-Prepare $c "next-cycle"
        $after = Read-State $c
        Assert-Equal ([int]$after.current_cycle) 2 "TEST-07 cycle"
        Assert-Equal ([int]$after.current_round) 1 "TEST-07 round"
        Assert-Equal $after.candidate_branch $c.branch "TEST-07 branch"
        Assert-Equal $after.current_candidate_sha $c.sha "TEST-07 current_candidate_sha"
        Assert-Equal $after.cycles[1].cycle_start_sha $c.sha "TEST-07 cycle_start_sha"
        Assert-Equal (Get-StepOutput $c "start_action") "rework" "TEST-07 start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-Scenario08 {
    $c = New-TestContext "test08"
    try {
        Use-TestContext $c
        $paused = New-PausedState $c "OPUS_ROUND_LIMIT" "OPUS" 3
        Write-Json $c.state $paused.state
        Invoke-Prepare $c "next-cycle"
        $after = Read-State $c
        Assert-Equal $after.findings_source "OPUS" "TEST-08 state findings source"
        Assert-Equal $after.findings_ref $paused.report "TEST-08 state findings ref"
        Assert-Equal $after.cycles[1].findings_source "OPUS" "TEST-08 cycle findings source"
        Assert-Equal $after.cycles[1].findings_ref $paused.report "TEST-08 cycle findings ref"
        Assert-Equal (Get-StepOutput $c "previous_report") $paused.report "TEST-08 previous report"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-Scenario09 {
    $c = New-TestContext "test09"
    try {
        Use-TestContext $c
        $paused = New-PausedState $c "FABLE_FINAL_REJECT" "FABLE" 1
        Write-Json $c.state $paused.state
        Invoke-Prepare $c "next-cycle"
        Assert-Equal (Get-StepOutput $c "findings_source") "FABLE" "TEST-09 findings source"
        Assert-Equal (Get-StepOutput $c "previous_report") $paused.report "TEST-09 previous report"
        & $StateScript -Operation BeginRound -Cycle 2 -Round 1 -RoundAction rework -PreviousReport $paused.report
        if ($LASTEXITCODE -ne 0) { throw "TEST-09 BeginRound failed" }
        & $StateScript -Operation SetCandidate -Cycle 2 -Round 1 -CandidateSha $c.sha
        if ($LASTEXITCODE -ne 0) { throw "TEST-09 SetCandidate failed" }
        $after = Read-State $c
        Assert-Equal $after.stage "OPUS_REVIEW" "TEST-09 must return to Opus"
        Assert-Equal $after.cycles[1].rounds[0].findings_source "FABLE" "TEST-09 round consumed findings source"
        Assert-Equal $after.cycles[1].rounds[0].findings_ref $paused.report "TEST-09 round consumed findings ref"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-Scenario10 {
    $engine = [IO.File]::ReadAllText((Join-Path $RepoRoot ".github\workflows\loop-engine.yml"), [System.Text.Encoding]::UTF8)
    $round = [IO.File]::ReadAllText((Join-Path $RepoRoot ".github\workflows\loop-round.yml"), [System.Text.Encoding]::UTF8)
    $runner = [IO.File]::ReadAllText((Join-Path $RepoRoot ".loop-engine\claude-verifier-runner.ps1"), [System.Text.Encoding]::UTF8)
    $rework = [IO.File]::ReadAllText((Join-Path $RepoRoot ".loop-engine\producer-rework-override.md"), [System.Text.Encoding]::UTF8)
    Assert-True ($engine.Contains('uses: ./.github/workflows/loop-round.yml')) "TEST-10 top-level Controller does not invoke reusable round workflow"
    Assert-True ($round.Contains('& codex exec')) "TEST-10 Codex invocation missing from Controller workflow"
    Assert-True ($round.Contains('& $env:VERIFIER_RUNNER_SCRIPT')) "TEST-10 verifier invocation missing from Controller workflow"
    Assert-True (-not $runner.ToLowerInvariant().Contains('codex exec')) "TEST-10 Claude runner directly invokes Codex"
    Assert-True (-not $rework.ToLowerInvariant().Contains('codex exec')) "TEST-10 producer prompt directly invokes Codex"
    Assert-True (-not $rework.ToLowerInvariant().Contains('claude --')) "TEST-10 producer prompt directly invokes Claude"
}

function New-V20FableRejectState($Context, [bool]$CreateNextRound) {
    $report = New-Report $Context 1 1 "v20 Fable FINAL_REJECT"
    $r1 = New-RoundObject $Context 1 "COMPLETE" "construct" "REJECTED" "" "" $report "" "" ""
    Add-LegacyPeriodFields $r1 1 2 "REJECTED"
    # Remove schema-4-only normalized fields to match a v20 ledger.
    $r1.PSObject.Properties.Remove("opus_result")
    $r1.PSObject.Properties.Remove("fable_result")
    $r1.PSObject.Properties.Remove("findings_source")
    $r1.PSObject.Properties.Remove("findings_ref")
    $rounds = @($r1)
    if ($CreateNextRound) {
        $r2 = New-RoundObject $Context 2 "PRODUCING" "rework" "" "" "" "" $report "" "" $false
        Add-LegacyPeriodFields $r2 3 0 ""
        $r2.PSObject.Properties.Remove("opus_result")
        $r2.PSObject.Properties.Remove("fable_result")
        $r2.PSObject.Properties.Remove("findings_source")
        $r2.PSObject.Properties.Remove("findings_ref")
        $rounds += $r2
    }
    $state = New-StateObject $Context 3 "IN_PROGRESS" "" 2 $rounds
    $state.PSObject.Properties.Remove("stage")
    $state.PSObject.Properties.Remove("pause_reason")
    $state.PSObject.Properties.Remove("opus_result")
    $state.PSObject.Properties.Remove("fable_result")
    $state.PSObject.Properties.Remove("findings_source")
    $state.PSObject.Properties.Remove("findings_ref")
    $state.cycles[0].PSObject.Properties.Remove("candidate_branch")
    $state.cycles[0].PSObject.Properties.Remove("cycle_start_sha")
    $state.cycles[0].PSObject.Properties.Remove("current_candidate_sha")
    $state.cycles[0].PSObject.Properties.Remove("findings_source")
    $state.cycles[0].PSObject.Properties.Remove("findings_ref")
    return [pscustomobject]@{ state = $state; report = $report }
}

function Invoke-LC01MissingNextRound {
    $c = New-TestContext "lc01-missing"
    try {
        Use-TestContext $c
        $legacy = New-V20FableRejectState $c $false
        Write-Json $c.state $legacy.state
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        Assert-Equal $after.status "PAUSED_AWAITING_USER" "LC-01 missing-next status"
        Assert-Equal $after.stage "PAUSED_AWAITING_USER" "LC-01 missing-next stage"
        Assert-Equal $after.pause_reason "FABLE_FINAL_REJECT" "LC-01 missing-next pause_reason"
        Assert-Equal ([int]$after.current_round) 1 "LC-01 missing-next current_round"
        Assert-Equal $after.findings_source "FABLE" "LC-01 missing-next findings_source"
        Assert-Equal $after.findings_ref $legacy.report "LC-01 missing-next findings_ref"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "LC-01 missing-next start_action"

        Invoke-Prepare $c "next-cycle"
        $cycle2 = Read-State $c
        Assert-Equal ([int]$cycle2.current_cycle) 2 "LC-02 recovery cycle"
        Assert-Equal $cycle2.cycles[1].cycle_start_sha $c.sha "LC-02 recovery cycle_start_sha"
        Assert-Equal $cycle2.cycles[1].findings_source "FABLE" "LC-02 recovery findings source"
        Assert-Equal (Get-StepOutput $c "start_action") "rework" "LC-02 recovery start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-LC01ActiveNextRound {
    $c = New-TestContext "lc01-active"
    try {
        Use-TestContext $c
        $legacy = New-V20FableRejectState $c $true
        Write-Json $c.state $legacy.state
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        Assert-Equal $after.status "PAUSED_AWAITING_USER" "LC-01 active-next status"
        Assert-Equal $after.pause_reason "FABLE_FINAL_REJECT" "LC-01 active-next pause_reason"
        Assert-Equal ([int]$after.current_round) 1 "LC-01 active-next current_round"
        Assert-Equal $after.findings_source "FABLE" "LC-01 active-next findings_source"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "LC-01 active-next start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-LC01OpusThreeRejects {
    $c = New-TestContext "lc01-opus3"
    try {
        Use-TestContext $c
        $rounds = @()
        $lastReport = ""
        for ($i = 1; $i -le 3; $i++) {
            $report = New-Report $c 1 $i ("v20 Opus REJECTED r" + $i)
            $r = New-RoundObject $c $i "COMPLETE" $(if ($i -eq 1) { "construct" } else { "rework" }) "REJECTED" "" "" $report $lastReport "" ""
            Add-LegacyPeriodFields $r $i 0 ""
            $r.PSObject.Properties.Remove("opus_result")
            $r.PSObject.Properties.Remove("fable_result")
            $r.PSObject.Properties.Remove("findings_source")
            $r.PSObject.Properties.Remove("findings_ref")
            $rounds += $r
            $lastReport = $report
        }
        $state = New-StateObject $c 3 "LOOP_EXHAUSTED" "" 3 $rounds
        $state.PSObject.Properties.Remove("stage")
        $state.PSObject.Properties.Remove("pause_reason")
        $state.PSObject.Properties.Remove("opus_result")
        $state.PSObject.Properties.Remove("fable_result")
        $state.PSObject.Properties.Remove("findings_source")
        $state.PSObject.Properties.Remove("findings_ref")
        Write-Json $c.state $state
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        Assert-Equal $after.status "PAUSED_AWAITING_USER" "LC-01 opus3 status"
        Assert-Equal $after.pause_reason "OPUS_ROUND_LIMIT" "LC-01 opus3 pause_reason"
        Assert-Equal $after.findings_source "OPUS" "LC-01 opus3 findings source"
        Assert-Equal ([int]$after.current_round) 3 "LC-01 opus3 current round"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "LC-01 opus3 start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-LC03StaleFableAllocationOpusReject {
    $c = New-TestContext "lc03-stale"
    try {
        Use-TestContext $c
        $r1 = New-RoundObject $c 1 "VERIFYING" "construct" "" "" "" "" "" "" ""
        Add-LegacyPeriodFields $r1 1 2 ""
        $r1 | Add-Member -NotePropertyName final_audit_evidence_verified -NotePropertyValue $null -Force
        $r1 | Add-Member -NotePropertyName final_audit_evidence_verified_verdict -NotePropertyValue $null -Force
        $r1 | Add-Member -NotePropertyName uat_write_authorization_opus_sha256 -NotePropertyValue ("b" * 64) -Force
        $state = New-StateObject $c 4 "RUNNING" "OPUS_REVIEW" 1 @($r1)
        Write-Json $c.state $state

        $opusDir = Join-Path $c.out "verifier-state\opus"
        New-Item -ItemType Directory -Force $opusDir | Out-Null
        $progress = [ordered]@{
            schema_version = 5
            verifier_stage = "OPUS"
            candidate_sha = $c.sha
            uat_period_slot = 1
            uat_period_primary = [int]$Pairs[0].primary_period
            uat_period_secondary = [int]$Pairs[0].secondary_period
            uat_period_pool_sha256 = $PoolHash
            status = "COMPLETE"
            final_verdict = "REJECTED"
        }
        Write-Json (Join-Path $opusDir "verifier-progress.json") $progress
        Write-Text (Join-Path $c.out "opus-result.txt") "REJECTED`n"
        Write-Text (Join-Path $c.out "uat-result.txt") "REJECTED`n"
        Write-Text (Join-Path $c.out "UAT_REPORT.md") "# Opus`nBUG_FOUND`n"

        Invoke-Prepare $c "auto"
        $after = Read-State $c
        $completed = @($after.cycles[0].rounds | Where-Object { [int]$_.round -eq 1 } | Select-Object -First 1)[0]
        Assert-Equal $completed.opus_result "BUG_FOUND" "LC-03 Opus result"
        Assert-True (-not [string]$completed.fable_result) "LC-03 stale Fable allocation produced a Fable result"
        Assert-Equal $after.status "RUNNING" "LC-03 status"
        Assert-Equal $after.stage "CODEX_REWORK" "LC-03 stage"
        Assert-Equal $after.findings_source "OPUS" "LC-03 findings source"
        Assert-Equal (Get-StepOutput $c "start_round") "2" "LC-03 start round"
        Assert-Equal (Get-StepOutput $c "start_action") "rework" "LC-03 start action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}


function New-LegacyFableRejectThenOpusRejectState($Context, [int]$Schema) {
    $fableReport = New-Report $Context 1 1 "legacy Fable FINAL_REJECT"
    $r1 = New-RoundObject $Context 1 "COMPLETE" "construct" "REJECTED" "" "" $fableReport "" "" ""
    Add-LegacyPeriodFields $r1 1 2 "REJECTED"

    $opusReport = New-Report $Context 1 2 "legacy Opus BUG_FOUND after invalid auto-continuation"
    $r2 = New-RoundObject $Context 2 "COMPLETE" "rework" "REJECTED" "" "" $opusReport $fableReport "" ""
    Add-LegacyPeriodFields $r2 3 0 ""

    if ($Schema -lt 4) {
        foreach ($r in @($r1, $r2)) {
            $r.PSObject.Properties.Remove("opus_result")
            $r.PSObject.Properties.Remove("fable_result")
            $r.PSObject.Properties.Remove("findings_source")
            $r.PSObject.Properties.Remove("findings_ref")
        }
        $state = New-StateObject $Context $Schema "IN_PROGRESS" "" 3 @($r1, $r2)
        foreach ($name in @("stage", "pause_reason", "opus_result", "fable_result", "findings_source", "findings_ref")) {
            $state.PSObject.Properties.Remove($name)
        }
    }
    else {
        $r1.opus_result = "NO_BUG"
        $r1.fable_result = "FINAL_REJECT"
        $r2.opus_result = "BUG_FOUND"
        $state = New-StateObject $Context 4 "RUNNING" "CODEX_REWORK" 3 @($r1, $r2)
    }
    return [pscustomobject]@{ state = $state; fable_report = $fableReport; opus_report = $opusReport }
}

function Invoke-R201LegacyLaterCompletedRound {
    $c = New-TestContext "r201-legacy-later-complete"
    try {
        Use-TestContext $c
        $legacy = New-LegacyFableRejectThenOpusRejectState $c 3
        Write-Json $c.state $legacy.state
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        Assert-Equal $after.status "PAUSED_AWAITING_USER" "R2-01 legacy later-complete status"
        Assert-Equal $after.stage "PAUSED_AWAITING_USER" "R2-01 legacy later-complete stage"
        Assert-Equal $after.pause_reason "FABLE_FINAL_REJECT" "R2-01 legacy later-complete pause_reason"
        Assert-Equal ([int]$after.current_round) 1 "R2-01 legacy later-complete governance round"
        Assert-Equal $after.findings_source "FABLE" "R2-01 legacy later-complete findings source"
        Assert-Equal $after.findings_ref $legacy.fable_report "R2-01 legacy later-complete findings ref"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "R2-01 legacy later-complete start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R201Schema4SelfHealAfterLaterCompletedRound {
    $c = New-TestContext "r201-schema4-selfheal"
    try {
        Use-TestContext $c
        $legacy = New-LegacyFableRejectThenOpusRejectState $c 4
        Write-Json $c.state $legacy.state
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        Assert-Equal $after.status "PAUSED_AWAITING_USER" "R2-01 schema4 self-heal status"
        Assert-Equal $after.pause_reason "FABLE_FINAL_REJECT" "R2-01 schema4 self-heal pause_reason"
        Assert-Equal ([int]$after.current_round) 1 "R2-01 schema4 self-heal governance round"
        Assert-Equal $after.findings_source "FABLE" "R2-01 schema4 self-heal findings source"
        Assert-Equal $after.findings_ref $legacy.fable_report "R2-01 schema4 self-heal findings ref"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "R2-01 schema4 self-heal start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R202PreMarkerFableReject {
    $c = New-TestContext "r202-premarker-fable"
    try {
        Use-TestContext $c
        $report = New-Report $c 1 1 "pre-marker Fable FINAL_REJECT"
        $r1 = New-RoundObject $c 1 "COMPLETE" "construct" "REJECTED" "" "" $report "" "" ""
        Add-LegacyPeriodFields $r1 1 2 ""
        foreach ($name in @("opus_result", "fable_result", "findings_source", "findings_ref")) { $r1.PSObject.Properties.Remove($name) }
        Assert-True (-not ($r1.PSObject.Properties.Name -contains "final_audit_evidence_verified_verdict")) "R2-02 fixture unexpectedly has marker property"
        $state = New-StateObject $c 3 "IN_PROGRESS" "" 2 @($r1)
        foreach ($name in @("stage", "pause_reason", "opus_result", "fable_result", "findings_source", "findings_ref")) { $state.PSObject.Properties.Remove($name) }
        Write-Json $c.state $state
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        $completed = @($after.cycles[0].rounds | Where-Object { [int]$_.round -eq 1 } | Select-Object -First 1)[0]
        Assert-Equal $completed.opus_result "NO_BUG" "R2-02 pre-marker opus result"
        Assert-Equal $completed.fable_result "FINAL_REJECT" "R2-02 pre-marker fable result"
        Assert-Equal $after.status "PAUSED_AWAITING_USER" "R2-02 pre-marker status"
        Assert-Equal $after.pause_reason "FABLE_FINAL_REJECT" "R2-02 pre-marker pause reason"
        Assert-Equal $after.findings_source "FABLE" "R2-02 pre-marker findings source"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "R2-02 pre-marker start action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}


function Invoke-R301FableRejectThenLaterFablePass {
    $c = New-TestContext "r301-reject-then-pass"
    try {
        Use-TestContext $c
        $rejectReport = New-Report $c 1 1 "legacy Fable FINAL_REJECT later superseded"
        $r1 = New-RoundObject $c 1 "COMPLETE" "construct" "REJECTED" "" "" $rejectReport "" "" ""
        Add-LegacyPeriodFields $r1 1 2 "REJECTED"

        $r2 = New-RoundObject $c 2 "COMPLETE" "rework" "PASS" "" "" "" $rejectReport "" ""
        Add-LegacyPeriodFields $r2 3 4 "PASS"
        foreach ($r in @($r1, $r2)) {
            foreach ($name in @("opus_result", "fable_result", "findings_source", "findings_ref")) { $r.PSObject.Properties.Remove($name) }
        }

        $state = New-StateObject $c 3 "PASS" "" 2 @($r1, $r2)
        foreach ($name in @("stage", "pause_reason", "opus_result", "fable_result", "findings_source", "findings_ref")) { $state.PSObject.Properties.Remove($name) }
        Write-Json $c.state $state
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        Assert-Equal $after.status "COMPLETED" "R3-01 later Fable PASS status"
        Assert-Equal $after.stage "COMPLETED" "R3-01 later Fable PASS stage"
        Assert-True (-not [string]$after.pause_reason) "R3-01 later Fable PASS pause_reason not cleared"
        Assert-Equal ([int]$after.current_round) 2 "R3-01 later Fable PASS governance round"
        Assert-Equal $after.fable_result "FINAL_PASS" "R3-01 later Fable PASS fable result"
        Assert-True (-not [string]$after.findings_source) "R3-01 later Fable PASS stale findings source"
        Assert-True (-not [string]$after.findings_ref) "R3-01 later Fable PASS stale findings ref"
        Assert-Equal $after.cycles[0].status "COMPLETED" "R3-01 later Fable PASS cycle status"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "R3-01 later Fable PASS start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R303PausedFableRejectIdempotent {
    $c = New-TestContext "r303-idempotent"
    try {
        Use-TestContext $c
        $paused = New-PausedState $c "FABLE_FINAL_REJECT" "FABLE" 1
        Write-Json $c.state $paused.state
        Invoke-Prepare $c "auto"
        Start-Sleep -Milliseconds 25
        $before = [IO.File]::ReadAllText($c.state, [System.Text.Encoding]::UTF8)
        Reset-StepOutput $c
        & $StateScript -Operation Prepare -RunMode auto
        if ($LASTEXITCODE -ne 0) { throw "R3-03 second Prepare failed: exit=$LASTEXITCODE" }
        $after = [IO.File]::ReadAllText($c.state, [System.Text.Encoding]::UTF8)
        Assert-Equal $after $before "R3-03 healthy PAUSED ledger was rewritten"
        $state = Read-State $c
        Assert-Equal $state.status "PAUSED_AWAITING_USER" "R3-03 status"
        Assert-Equal $state.pause_reason "FABLE_FINAL_REJECT" "R3-03 pause_reason"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "R3-03 start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R401CompletedAfterReworkIdempotent {
    $c = New-TestContext "r401-completed-idempotent"
    try {
        Use-TestContext $c
        $opusReport = New-Report $c 1 1 "Opus BUG_FOUND before final pass"
        $r1 = New-RoundObject $c 1 "COMPLETE" "construct" "REJECTED" "BUG_FOUND" "" $opusReport "" "" ""
        Add-LegacyPeriodFields $r1 1
        $r1 | Add-Member -NotePropertyName produced_findings_source -NotePropertyValue "OPUS" -Force
        $r1 | Add-Member -NotePropertyName produced_findings_ref -NotePropertyValue $opusReport -Force

        $r2 = New-RoundObject $c 2 "VERIFYING" "rework" "" "" "" "" $opusReport "OPUS" $opusReport
        Add-LegacyPeriodFields $r2 3 4 "PASS"
        $r2 | Add-Member -NotePropertyName produced_findings_source -NotePropertyValue $null -Force
        $r2 | Add-Member -NotePropertyName produced_findings_ref -NotePropertyValue $null -Force
        $r2 | Add-Member -NotePropertyName uat_write_authorization_opus_sha256 -NotePropertyValue ("b" * 64) -Force
        $r2 | Add-Member -NotePropertyName uat_write_authorization_fable_sha256 -NotePropertyValue ("d" * 64) -Force
        $state = New-StateObject $c 4 "RUNNING" "FABLE_FINAL_REVIEW" 2 @($r1, $r2) "" "OPUS" $opusReport
        $state.opus_result = "NO_BUG"
        Write-Json $c.state $state

        Write-Text (Join-Path $c.out "opus-result.txt") "PRECHECK_PASS`n"
        $fableDir = Join-Path $c.out "verifier-state\fable"
        New-Item -ItemType Directory -Force $fableDir | Out-Null
        $progress = [ordered]@{
            schema_version = 5
            verifier_stage = "FABLE"
            candidate_sha = $c.sha
            uat_period_slot = [int]$r2.final_audit_uat_period_slot
            uat_period_primary = [int]$r2.final_audit_uat_period_primary
            uat_period_secondary = [int]$r2.final_audit_uat_period_secondary
            uat_period_pool_sha256 = [string]$r2.final_audit_uat_period_pool_sha256
            status = "COMPLETE"
            final_verdict = "PASS"
        }
        Write-Json (Join-Path $fableDir "verifier-progress.json") $progress
        Write-Text (Join-Path $c.out "UAT_REPORT.md") "# Fable FINAL_PASS after rework`n"
        Write-Text (Join-Path $c.out "uat-result.txt") "PASS`n"

        $protected = "c" * 64
        & $StateScript -Operation BindProtectedEvidenceBaseline -Cycle 1 -Round 2 -ProtectedEvidenceSha256 $protected
        if ($LASTEXITCODE -ne 0) { throw "R4-01 BindProtectedEvidenceBaseline failed" }
        & $StateScript -Operation MarkFinalAuditEvidenceVerified -Cycle 1 -Round 2 -Verdict PASS -ProtectedEvidenceSha256 $protected
        if ($LASTEXITCODE -ne 0) { throw "R4-01 MarkFinalAuditEvidenceVerified failed" }

        & $StateScript -Operation CompleteRound -Cycle 1 -Round 2 -Verdict PASS -OpusResult NO_BUG -FableResult FINAL_PASS
        if ($LASTEXITCODE -ne 0) { throw "R4-01 CompleteRound failed: exit=$LASTEXITCODE" }

        $completed = Read-State $c
        Assert-Equal $completed.status "COMPLETED" "R4-01 completed status"
        Assert-True (-not [string]$completed.findings_source) "R4-01 state findings_source not cleared"
        Assert-True (-not [string]$completed.findings_ref) "R4-01 state findings_ref not cleared"
        Assert-True (-not [string]$completed.cycles[0].findings_source) "R4-01 cycle findings_source not cleared"
        Assert-True (-not [string]$completed.cycles[0].findings_ref) "R4-01 cycle findings_ref not cleared"

        $before = [IO.File]::ReadAllText($c.state, [System.Text.Encoding]::UTF8)
        Invoke-Prepare $c "auto"
        $afterFirst = [IO.File]::ReadAllText($c.state, [System.Text.Encoding]::UTF8)
        Assert-Equal $afterFirst $before "R4-01 first Prepare rewrote healthy COMPLETED ledger"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "R4-01 first Prepare start_action"

        Start-Sleep -Milliseconds 25
        Reset-StepOutput $c
        & $StateScript -Operation Prepare -RunMode auto
        if ($LASTEXITCODE -ne 0) { throw "R4-01 second Prepare failed: exit=$LASTEXITCODE" }
        $afterSecond = [IO.File]::ReadAllText($c.state, [System.Text.Encoding]::UTF8)
        Assert-Equal $afterSecond $afterFirst "R4-01 second Prepare rewrote healthy COMPLETED ledger"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "R4-01 second Prepare start_action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}


function Assert-CompleteRoundMismatchLeavesStateUntouched(
    $Context,
    [string]$Verdict,
    [string]$OpusResult,
    [string]$FableResult,
    [string]$ExpectedMessage
) {
    $beforeState = [IO.File]::ReadAllText($Context.state, [System.Text.Encoding]::UTF8)
    $roundDir = Join-Path $Context.cycles "cycle-1\round-1"
    $roundArchiveExistedBefore = Test-Path -LiteralPath $roundDir
    $caught = $false
    try {
        & $StateScript -Operation CompleteRound -Cycle 1 -Round 1 -Verdict $Verdict -OpusResult $OpusResult -FableResult $FableResult
    }
    catch {
        $caught = $true
        Assert-True ($_.Exception.Message -like ("*" + $ExpectedMessage + "*")) ("R7 mismatch error was not canonical: " + $_.Exception.Message)
    }
    Assert-True $caught "R7 expected CompleteRound mismatch to fail closed"
    $afterState = [IO.File]::ReadAllText($Context.state, [System.Text.Encoding]::UTF8)
    Assert-Equal $afterState $beforeState "R7 mismatch mutated loop-state.json"
    Assert-Equal (Test-Path -LiteralPath $roundDir) $roundArchiveExistedBefore "R7 mismatch created or removed the Round archive"
}

function New-R7OpusCanonicalEvidence($Context, [string]$Verdict) {
    Use-TestContext $Context
    $r1 = New-RoundObject $Context 1 "VERIFYING" "construct" "" "" "" "" "" "" ""
    Add-LegacyPeriodFields $r1 1
    $r1 | Add-Member -NotePropertyName uat_write_authorization_opus_sha256 -NotePropertyValue ("b" * 64) -Force
    $state = New-StateObject $Context 4 "RUNNING" "OPUS_REVIEW" 1 @($r1)
    Write-Json $Context.state $state

    $opusDir = Join-Path $Context.out "verifier-state\opus"
    New-Item -ItemType Directory -Force $opusDir | Out-Null
    $progress = [ordered]@{
        schema_version = 5
        verifier_stage = "OPUS"
        candidate_sha = $Context.sha
        uat_period_slot = [int]$r1.uat_period_slot
        uat_period_primary = [int]$r1.uat_period_primary
        uat_period_secondary = [int]$r1.uat_period_secondary
        uat_period_pool_sha256 = [string]$r1.uat_period_pool_sha256
        status = $(if ($Verdict -eq "BLOCKED") { "BLOCKED" } else { "COMPLETE" })
        final_verdict = $Verdict
    }
    Write-Json (Join-Path $opusDir "verifier-progress.json") $progress
    Write-Text (Join-Path $Context.out "opus-result.txt") ($Verdict + "`n")
    Write-Text (Join-Path $Context.out "uat-result.txt") ($Verdict + "`n")
    Write-Text (Join-Path $Context.out "UAT_REPORT.md") ("# Canonical Opus " + $Verdict + "`n")
}

function New-R7FableCanonicalEvidence($Context, [string]$Verdict) {
    Use-TestContext $Context
    $r1 = New-RoundObject $Context 1 "VERIFYING" "construct" "" "" "" "" "" "" ""
    Add-LegacyPeriodFields $r1 1 2
    $r1 | Add-Member -NotePropertyName uat_write_authorization_opus_sha256 -NotePropertyValue ("b" * 64) -Force
    $r1 | Add-Member -NotePropertyName uat_write_authorization_fable_sha256 -NotePropertyValue ("d" * 64) -Force
    $state = New-StateObject $Context 4 "RUNNING" "FABLE_FINAL_REVIEW" 1 @($r1)
    Write-Json $Context.state $state

    Write-Text (Join-Path $Context.out "opus-result.txt") "PRECHECK_PASS`n"
    $fableDir = Join-Path $Context.out "verifier-state\fable"
    New-Item -ItemType Directory -Force $fableDir | Out-Null
    $progress = [ordered]@{
        schema_version = 5
        verifier_stage = "FABLE"
        candidate_sha = $Context.sha
        uat_period_slot = [int]$r1.final_audit_uat_period_slot
        uat_period_primary = [int]$r1.final_audit_uat_period_primary
        uat_period_secondary = [int]$r1.final_audit_uat_period_secondary
        uat_period_pool_sha256 = [string]$r1.final_audit_uat_period_pool_sha256
        status = $(if ($Verdict -eq "BLOCKED") { "BLOCKED" } else { "COMPLETE" })
        final_verdict = $Verdict
    }
    Write-Json (Join-Path $fableDir "verifier-progress.json") $progress
    Write-Text (Join-Path $Context.out "uat-result.txt") ($Verdict + "`n")
    Write-Text (Join-Path $Context.out "UAT_REPORT.md") ("# Canonical Fable " + $Verdict + "`n")

    $protected = "c" * 64
    & $StateScript -Operation BindProtectedEvidenceBaseline -Cycle 1 -Round 1 -ProtectedEvidenceSha256 $protected
    if ($LASTEXITCODE -ne 0) { throw "R7 BindProtectedEvidenceBaseline failed" }
    & $StateScript -Operation MarkFinalAuditEvidenceVerified -Cycle 1 -Round 1 -Verdict $Verdict -ProtectedEvidenceSha256 $protected
    if ($LASTEXITCODE -ne 0) { throw "R7 MarkFinalAuditEvidenceVerified failed" }
}

function Invoke-R7FableRejectCannotBeClaimedAsOpusBug {
    $c = New-TestContext "r7-fable-reject-mismatch"
    try {
        New-R7FableCanonicalEvidence $c "REJECTED"
        Assert-CompleteRoundMismatchLeavesStateUntouched $c "REJECTED" "BUG_FOUND" "" "canonical Opus result mismatch"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R7OpusRejectCannotBeClaimedAsFableReject {
    $c = New-TestContext "r7-opus-reject-mismatch"
    try {
        New-R7OpusCanonicalEvidence $c "REJECTED"
        Assert-CompleteRoundMismatchLeavesStateUntouched $c "REJECTED" "NO_BUG" "FINAL_REJECT" "canonical Opus result mismatch"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R7PassCannotCarryNonFinalPassResults {
    $c = New-TestContext "r7-pass-mismatch"
    try {
        New-R7FableCanonicalEvidence $c "PASS"
        Assert-CompleteRoundMismatchLeavesStateUntouched $c "PASS" "NO_BUG" "FINAL_REJECT" "canonical Fable result mismatch"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}


function Invoke-R7BlockedSourceMismatchFailsClosed {
    $c = New-TestContext "r7-blocked-source-mismatch"
    try {
        New-R7OpusCanonicalEvidence $c "BLOCKED"
        Assert-CompleteRoundMismatchLeavesStateUntouched $c "BLOCKED" "NO_BUG" "" "canonical Opus result mismatch"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}


function Set-R8RetainedFableMarker($Context, [string]$Verdict) {
    $state = Read-State $Context
    $round = @($state.cycles[0].rounds | Where-Object { [int]$_.round -eq 1 } | Select-Object -First 1)[0]
    Add-LegacyPeriodFields $round 1 2 $Verdict
    Write-Json $Context.state $state
}

function Invoke-R8ReconcileOpusRejectIgnoresRetainedFableMarker {
    $c = New-TestContext "r8-reconcile-opus-reject-stale-fable"
    try {
        New-R7OpusCanonicalEvidence $c "REJECTED"
        Set-R8RetainedFableMarker $c "REJECTED"
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        $completed = @($after.cycles[0].rounds | Where-Object { [int]$_.round -eq 1 } | Select-Object -First 1)[0]
        Assert-Equal $completed.opus_result "BUG_FOUND" "R8 native Reconcile Opus reject result"
        Assert-True (-not [string]$completed.fable_result) "R8 native Reconcile Opus reject must not inherit stale Fable result"
        Assert-Equal $completed.produced_findings_source "OPUS" "R8 native Reconcile findings source"
        Assert-Equal $after.status "RUNNING" "R8 native Reconcile Opus reject status"
        Assert-Equal $after.stage "CODEX_REWORK" "R8 native Reconcile Opus reject stage"
        Assert-Equal $after.findings_source "OPUS" "R8 native Reconcile state findings source"
        Assert-Equal (Get-StepOutput $c "start_round") "2" "R8 native Reconcile start round"
        Assert-Equal (Get-StepOutput $c "start_action") "rework" "R8 native Reconcile start action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R8ReconcileRound3OpusRejectKeepsOpusRoundLimit {
    $c = New-TestContext "r8-reconcile-round3-opus-reject"
    try {
        Use-TestContext $c
        $report1 = New-Report $c 1 1 "prior Opus BUG_FOUND r1"
        $report2 = New-Report $c 1 2 "prior Opus BUG_FOUND r2"
        $r1 = New-RoundObject $c 1 "COMPLETE" "construct" "REJECTED" "BUG_FOUND" "" $report1 "" "" ""
        Add-LegacyPeriodFields $r1 1
        $r2 = New-RoundObject $c 2 "COMPLETE" "rework" "REJECTED" "BUG_FOUND" "" $report2 $report1 "OPUS" $report1
        Add-LegacyPeriodFields $r2 2
        $r3 = New-RoundObject $c 3 "VERIFYING" "rework" "" "" "" "" $report2 "OPUS" $report2
        Add-LegacyPeriodFields $r3 3 4 "REJECTED"
        $r3 | Add-Member -NotePropertyName uat_write_authorization_opus_sha256 -NotePropertyValue ("b" * 64) -Force
        $state = New-StateObject $c 4 "RUNNING" "OPUS_REVIEW" 3 @($r1, $r2, $r3) "" "OPUS" $report2
        Write-Json $c.state $state

        $opusDir = Join-Path $c.out "verifier-state\opus"
        New-Item -ItemType Directory -Force $opusDir | Out-Null
        $progress = [ordered]@{
            schema_version = 5
            verifier_stage = "OPUS"
            candidate_sha = $c.sha
            uat_period_slot = [int]$r3.uat_period_slot
            uat_period_primary = [int]$r3.uat_period_primary
            uat_period_secondary = [int]$r3.uat_period_secondary
            uat_period_pool_sha256 = [string]$r3.uat_period_pool_sha256
            status = "COMPLETE"
            final_verdict = "REJECTED"
        }
        Write-Json (Join-Path $opusDir "verifier-progress.json") $progress
        Write-Text (Join-Path $c.out "opus-result.txt") "REJECTED`n"
        Write-Text (Join-Path $c.out "uat-result.txt") "REJECTED`n"
        Write-Text (Join-Path $c.out "UAT_REPORT.md") "# Canonical Round 3 Opus REJECTED`n"

        Invoke-Prepare $c "auto"
        $after = Read-State $c
        $completed = @($after.cycles[0].rounds | Where-Object { [int]$_.round -eq 3 } | Select-Object -First 1)[0]
        Assert-Equal $completed.opus_result "BUG_FOUND" "R8 Round3 canonical Opus result"
        Assert-True (-not [string]$completed.fable_result) "R8 Round3 stale Fable marker produced a Fable result"
        Assert-Equal $completed.produced_findings_source "OPUS" "R8 Round3 findings source"
        Assert-Equal $after.status "PAUSED_AWAITING_USER" "R8 Round3 status"
        Assert-Equal $after.pause_reason "OPUS_ROUND_LIMIT" "R8 Round3 pause reason"
        Assert-Equal $after.findings_source "OPUS" "R8 Round3 state findings source"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "R8 Round3 next action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R8ReconcileOpusBlockedIgnoresRetainedFableMarker {
    $c = New-TestContext "r8-reconcile-opus-blocked-stale-fable"
    try {
        New-R7OpusCanonicalEvidence $c "BLOCKED"
        Set-R8RetainedFableMarker $c "BLOCKED"
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        $completed = @($after.cycles[0].rounds | Where-Object { [int]$_.round -eq 1 } | Select-Object -First 1)[0]
        Assert-True (-not [string]$completed.opus_result) "R8 native Opus BLOCKED must keep canonical empty Opus result"
        Assert-True (-not [string]$completed.fable_result) "R8 native Opus BLOCKED must keep canonical empty Fable result"
        Assert-Equal $after.status "BLOCKED" "R8 native Opus BLOCKED status"
        Assert-Equal $after.stage "OPUS_REVIEW" "R8 native Opus BLOCKED source stage"
        Assert-Equal (Get-StepOutput $c "start_action") "resume-verifier" "R8 native Opus BLOCKED resume action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R8ReconcileFablePassStaysFinalPass {
    $c = New-TestContext "r8-reconcile-fable-pass"
    try {
        New-R7FableCanonicalEvidence $c "PASS"
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        $completed = @($after.cycles[0].rounds | Where-Object { [int]$_.round -eq 1 } | Select-Object -First 1)[0]
        Assert-Equal $completed.opus_result "NO_BUG" "R8 Fable PASS Opus result"
        Assert-Equal $completed.fable_result "FINAL_PASS" "R8 Fable PASS result"
        Assert-Equal $after.status "COMPLETED" "R8 Fable PASS state status"
        Assert-Equal $after.stage "COMPLETED" "R8 Fable PASS state stage"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "R8 Fable PASS next action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R8ReconcileFableRejectStaysFinalReject {
    $c = New-TestContext "r8-reconcile-fable-reject"
    try {
        New-R7FableCanonicalEvidence $c "REJECTED"
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        $completed = @($after.cycles[0].rounds | Where-Object { [int]$_.round -eq 1 } | Select-Object -First 1)[0]
        Assert-Equal $completed.opus_result "NO_BUG" "R8 Fable REJECT Opus result"
        Assert-Equal $completed.fable_result "FINAL_REJECT" "R8 Fable REJECT result"
        Assert-Equal $after.status "PAUSED_AWAITING_USER" "R8 Fable REJECT state status"
        Assert-Equal $after.pause_reason "FABLE_FINAL_REJECT" "R8 Fable REJECT pause reason"
        Assert-Equal $after.findings_source "FABLE" "R8 Fable REJECT findings source"
        Assert-Equal (Get-StepOutput $c "start_action") "none" "R8 Fable REJECT next action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

function Invoke-R8ReconcileFableBlockedStaysBlocked {
    $c = New-TestContext "r8-reconcile-fable-blocked"
    try {
        New-R7FableCanonicalEvidence $c "BLOCKED"
        Invoke-Prepare $c "auto"
        $after = Read-State $c
        $completed = @($after.cycles[0].rounds | Where-Object { [int]$_.round -eq 1 } | Select-Object -First 1)[0]
        Assert-Equal $completed.opus_result "NO_BUG" "R8 Fable BLOCKED preserves prior Opus NO_BUG"
        Assert-True (-not [string]$completed.fable_result) "R8 Fable BLOCKED has no terminal Fable result"
        Assert-Equal $after.status "BLOCKED" "R8 Fable BLOCKED state status"
        Assert-Equal $after.stage "FABLE_FINAL_REVIEW" "R8 Fable BLOCKED source stage"
        Assert-Equal (Get-StepOutput $c "start_action") "resume-verifier" "R8 Fable BLOCKED resume action"
    }
    finally { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $c.root }
}

$allScenarios = @(
    "test-01-opus-r1-bug",
    "test-02-opus-r2-bug",
    "test-03-opus-r3-bug",
    "test-04-opus-no-bug-fable",
    "test-05-fable-pass",
    "test-06-fable-reject",
    "test-07-next-cycle",
    "test-08-opus-findings-next-cycle",
    "test-09-fable-findings-next-cycle",
    "test-10-controller-only",
    "lc01-v20-fable-reject-missing-next-round",
    "lc01-v20-fable-reject-active-next-round",
    "lc01-v20-opus-three-rejects",
    "lc03-stale-fable-allocation-opus-reject",
    "r2-01-legacy-fable-reject-then-later-complete",
    "r2-01-schema4-self-heal-after-later-complete",
    "r2-02-pre-marker-fable-reject",
    "r3-01-fable-reject-then-later-fable-pass",
    "r3-03-paused-fable-reject-idempotent",
    "r4-01-completed-after-rework-idempotent",
    "r7-fable-reject-cannot-be-claimed-as-opus-bug",
    "r7-opus-reject-cannot-be-claimed-as-fable-reject",
    "r7-pass-cannot-carry-nonfinal-pass-results",
    "r7-blocked-source-mismatch-fails-closed",
    "r8-reconcile-opus-reject-ignores-retained-fable-marker",
    "r8-reconcile-round3-opus-reject-keeps-opus-round-limit",
    "r8-reconcile-opus-blocked-ignores-retained-fable-marker",
    "r8-reconcile-fable-pass-stays-final-pass",
    "r8-reconcile-fable-reject-stays-final-reject",
    "r8-reconcile-fable-blocked-stays-blocked"
)

$selected = if ($Scenario -eq "all") { $allScenarios } else { @($Scenario) }
$passed = 0
$failures = @()
try {
    foreach ($name in $selected) {
        try {
            switch ($name) {
                "test-01-opus-r1-bug" { Invoke-Scenario01 }
                "test-02-opus-r2-bug" { Invoke-Scenario02 }
                "test-03-opus-r3-bug" { Invoke-Scenario03 }
                "test-04-opus-no-bug-fable" { Invoke-Scenario04 }
                "test-05-fable-pass" { Invoke-Scenario05 }
                "test-06-fable-reject" { Invoke-Scenario06 }
                "test-07-next-cycle" { Invoke-Scenario07 }
                "test-08-opus-findings-next-cycle" { Invoke-Scenario08 }
                "test-09-fable-findings-next-cycle" { Invoke-Scenario09 }
                "test-10-controller-only" { Invoke-Scenario10 }
                "lc01-v20-fable-reject-missing-next-round" { Invoke-LC01MissingNextRound }
                "lc01-v20-fable-reject-active-next-round" { Invoke-LC01ActiveNextRound }
                "lc01-v20-opus-three-rejects" { Invoke-LC01OpusThreeRejects }
                "lc03-stale-fable-allocation-opus-reject" { Invoke-LC03StaleFableAllocationOpusReject }
                "r2-01-legacy-fable-reject-then-later-complete" { Invoke-R201LegacyLaterCompletedRound }
                "r2-01-schema4-self-heal-after-later-complete" { Invoke-R201Schema4SelfHealAfterLaterCompletedRound }
                "r2-02-pre-marker-fable-reject" { Invoke-R202PreMarkerFableReject }
                "r3-01-fable-reject-then-later-fable-pass" { Invoke-R301FableRejectThenLaterFablePass }
                "r3-03-paused-fable-reject-idempotent" { Invoke-R303PausedFableRejectIdempotent }
                "r4-01-completed-after-rework-idempotent" { Invoke-R401CompletedAfterReworkIdempotent }
                "r7-fable-reject-cannot-be-claimed-as-opus-bug" { Invoke-R7FableRejectCannotBeClaimedAsOpusBug }
                "r7-opus-reject-cannot-be-claimed-as-fable-reject" { Invoke-R7OpusRejectCannotBeClaimedAsFableReject }
                "r7-pass-cannot-carry-nonfinal-pass-results" { Invoke-R7PassCannotCarryNonFinalPassResults }
                "r7-blocked-source-mismatch-fails-closed" { Invoke-R7BlockedSourceMismatchFailsClosed }
                "r8-reconcile-opus-reject-ignores-retained-fable-marker" { Invoke-R8ReconcileOpusRejectIgnoresRetainedFableMarker }
                "r8-reconcile-round3-opus-reject-keeps-opus-round-limit" { Invoke-R8ReconcileRound3OpusRejectKeepsOpusRoundLimit }
                "r8-reconcile-opus-blocked-ignores-retained-fable-marker" { Invoke-R8ReconcileOpusBlockedIgnoresRetainedFableMarker }
                "r8-reconcile-fable-pass-stays-final-pass" { Invoke-R8ReconcileFablePassStaysFinalPass }
                "r8-reconcile-fable-reject-stays-final-reject" { Invoke-R8ReconcileFableRejectStaysFinalReject }
                "r8-reconcile-fable-blocked-stays-blocked" { Invoke-R8ReconcileFableBlockedStaysBlocked }
                default { throw "unknown scenario: $name" }
            }
            $passed++
            Write-Host "[LOOP-CORE-BEHAVIOR] PASS $name"
        }
        catch {
            $failures += [pscustomobject][ordered]@{
                scenario = $name
                message = $_.Exception.Message
            }
            Write-Host "[LOOP-CORE-BEHAVIOR] FAIL $name :: $($_.Exception.Message)"
        }
    }

    Write-Host "[LOOP-CORE-BEHAVIOR] SUMMARY total=$($selected.Count) passed=$passed failed=$($failures.Count)"
    if ($failures.Count -gt 0) {
        $failedNames = @($failures | ForEach-Object { $_.scenario }) -join ","
        throw "Loop Core behavior scenarios failed: $($failures.Count) of $($selected.Count); failed=$failedNames"
    }
    Write-Host "[LOOP-CORE-BEHAVIOR] PASS scenarios=$passed"
}
finally {
    foreach ($name in $BehaviorEnvironmentNames) {
        [Environment]::SetEnvironmentVariable($name, $originalEnvironment[$name], "Process")
    }
}
