$ErrorActionPreference = "Stop"

Write-Host "=== LOOP ENGINE WINDOWS POWERSHELL SMOKE ==="
Write-Host "PowerShell=$($PSVersionTable.PSVersion)"

# R6: validate the machine-readable environment contract without requiring
# FullUat capabilities. Loop Core validity is independent from unavailable
# Consumer lifecycle automation or unverified real-DB period occupancy.
if (-not $env:UAT_READINESS_FILE) { throw "UAT_READINESS_FILE is required" }
if (-not $env:UAT_READINESS_SCRIPT) { throw "UAT_READINESS_SCRIPT is required" }
if (-not (Test-Path $env:UAT_READINESS_SCRIPT)) { throw "UAT readiness script missing: $env:UAT_READINESS_SCRIPT" }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $env:UAT_READINESS_SCRIPT -Mode Core -ReadinessFile $env:UAT_READINESS_FILE -PolicyFile $env:UAT_ACTION_POLICY_FILE
if ($LASTEXITCODE -ne 0) { throw "R6 Core UAT readiness contract validation failed" }
Write-Host "[UAT-READINESS-CORE-SMOKE] PASS"

# Validate the governed UAT period pool before any Codex/Claude token spend.
if (-not $env:UAT_PERIOD_POOL_FILE) { throw "UAT_PERIOD_POOL_FILE is required" }
if (-not (Test-Path $env:UAT_PERIOD_POOL_FILE)) { throw "UAT period pool missing: $env:UAT_PERIOD_POOL_FILE" }
$pool = [IO.File]::ReadAllText($env:UAT_PERIOD_POOL_FILE, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
if ([int]$pool.schema_version -ne 1) { throw "unsupported UAT period pool schema" }
$pairs = @($pool.pairs)
if ($pairs.Count -lt 10) { throw "UAT period pool must retain the initial 10 reviewed pairs; found $($pairs.Count)" }
$slots = @{}
$periods = @{}
foreach ($pair in $pairs) {
    $slot = [int]$pair.slot
    $primary = [int]$pair.primary_period
    $secondary = [int]$pair.secondary_period
    if ($slot -lt 1 -or $primary -lt 1 -or $secondary -lt 1 -or $primary -eq $secondary) { throw "invalid UAT period pair in slot $slot" }
    if ($slots.ContainsKey($slot)) { throw "duplicate UAT period slot: $slot" }
    $slots[$slot] = $true
    foreach ($period in @($primary, $secondary)) {
        if ($periods.ContainsKey($period)) { throw "duplicate UAT period value: $period" }
        $periods[$period] = $true
    }
}
Write-Host "[PERIOD-POOL-SMOKE] PASS pairs=$($pairs.Count) unique_periods=$($periods.Count)"

# PowerShell regex regression: use regex-engine escapes, not backtick escapes in
# single-quoted strings. Normal branch/path/image inputs must pass; real CR/LF/NUL
# must be rejected.
$forbiddenInline = '[\x00\r\n ]'
$forbiddenControl = '[\x00\r\n]'
foreach ($valid in @(
    "codex/pvam-work02-uat-candidate-20260813",
    "/mnt/redemption/Redemption",
    "registry.local/flannel:v0.26.1"
)) {
    if ($valid -match $forbiddenInline) { throw "regex smoke rejected valid value: $valid" }
}
foreach ($invalid in @("bad branch", "bad`rbranch", "bad`nbranch", ("bad" + [char]0 + "branch"))) {
    if ($invalid -notmatch $forbiddenInline) { throw "regex smoke accepted invalid branch/image value" }
}
foreach ($invalid in @("bad`rpath", "bad`npath", ("bad" + [char]0 + "path"))) {
    if ($invalid -notmatch $forbiddenControl) { throw "regex smoke accepted invalid path value" }
}
Write-Host "[CONTROL-REGEX-SMOKE] PASS"


# v20 static controller contract smoke. Do not touch Kubernetes here; this runs
# before verifier work and exists to catch packaging/version drift on PS5.1.
$proxyContractPath = Join-Path $env:MAINREPO ".loop-engine\uat-action-proxy.ps1"
$policyContractPath = Join-Path $env:MAINREPO ".loop-engine\uat-action-policy.json"
$consumerRuntimeControllerPath = Join-Path $env:MAINREPO ".loop-engine\consumer-runtime-controller-r9.py"
$protectedHashContractPath = Join-Path $env:MAINREPO ".loop-engine\protected-evidence-hash.ps1"
if (-not (Test-Path -LiteralPath $proxyContractPath -PathType Leaf)) { throw "v20 proxy contract missing" }
if (-not (Test-Path -LiteralPath $policyContractPath -PathType Leaf)) { throw "v20 policy contract missing" }
if (-not (Test-Path -LiteralPath $consumerRuntimeControllerPath -PathType Leaf)) { throw "R9 consumer-runtime-controller-r9.py missing" }
if (-not (Test-Path -LiteralPath $protectedHashContractPath -PathType Leaf)) { throw "v20 protected evidence hash contract missing" }
$proxyContractText = [IO.File]::ReadAllText($proxyContractPath, [System.Text.Encoding]::UTF8)
foreach ($needle in @(
    'controller-evidence\schema-{0}\cycle-{1}\round-{2}\{3}',
    'ConsumerLifecycle calc_month is controller governed',
    "runtime_mode='scheduler-pod-temporary-process'",
    'function Invoke-ConsumerRuntimeController'
)) {
    if (-not $proxyContractText.Contains($needle)) { throw "v20 proxy contract missing: $needle" }
}
$protectedHashContractText = [IO.File]::ReadAllText($protectedHashContractPath, [System.Text.Encoding]::UTF8)
if (-not $protectedHashContractText.Contains('controller-evidence\schema-10\cycle-{0}\round-{1}\opus')) { throw "v20 protected digest does not bind schema-10 Opus controller evidence" }
if ($protectedHashContractText.Contains('controller-evidence\schema-9\cycle-{0}\round-{1}\opus')) { throw "v20 protected digest still binds schema-9 controller evidence" }
$policyContract = [IO.File]::ReadAllText($policyContractPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
if ([int]$policyContract.schema_version -ne 8 -or [int]$policyContract.controller_evidence_schema -ne 10) { throw "v20 policy/controller evidence schema mismatch" }
if ([string]$policyContract.consumer_runtime_target.mode -ne 'scheduler-pod-temporary-process') { throw "v20 scheduler Pod Consumer runtime target missing" }
$namespaces = @($policyContract.required_idempotency_namespaces | ForEach-Object { [string]$_ })
foreach ($requiredNs in @('userstats','placement','elite')) {
    if ($namespaces -notcontains $requiredNs) { throw "v20 required idempotency namespace missing: $requiredNs" }
}
Write-Host "[V20-CONTROLLER-CONTRACT-SMOKE] PASS"

$proxyRuntimeRegression = Join-Path $env:MAINREPO "tests\loop-engine\proxy-runtime-regressions.ps1"
if (-not (Test-Path -LiteralPath $proxyRuntimeRegression -PathType Leaf)) { throw "proxy runtime regression script missing" }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $proxyRuntimeRegression -Case all -ProxyPath $proxyContractPath
if ($LASTEXITCODE -ne 0) { throw "proxy runtime behavior regressions failed" }
Write-Host "[PROXY-RUNTIME-BEHAVIOR-SMOKE] PASS"

# Regression: a single non-empty producer verdict line must remain an array item,
# never degrade to a scalar string whose [-1] access returns a Char.
$single = "READY_FOR_UAT`r`n"
$singleLines = @(
    $single -split "`r?`n" | Where-Object { $_.Trim() -ne "" }
)
if ($singleLines.Count -ne 1) { throw "single-line verdict parse count mismatch: $($singleLines.Count)" }
$singleVerdict = ([string]$singleLines[-1]).Trim()
if ($singleVerdict -ne "READY_FOR_UAT") { throw "single-line verdict parse failed: '$singleVerdict'" }
Write-Host "[SMOKE] single-line producer verdict PASS"

$multi = "note one`r`nnote two`r`nREADY_FOR_UAT`r`n"
$multiLines = @(
    $multi -split "`r?`n" | Where-Object { $_.Trim() -ne "" }
)
$multiVerdict = ([string]$multiLines[-1]).Trim()
if ($multiVerdict -ne "READY_FOR_UAT") { throw "multi-line verdict parse failed: '$multiVerdict'" }
Write-Host "[SMOKE] multi-line producer verdict PASS"

# Verify the .NET atomic replacement primitive used by loop-state.ps1 is available
# on the actual Windows runner runtime.
$dir = Join-Path $env:TEMP ("loop-engine-smoke-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $dir | Out-Null
$target = Join-Path $dir "loop-state.json"
$temp = Join-Path $dir "loop-state.tmp.json"
try {
    [IO.File]::WriteAllText($target, "old", (New-Object System.Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($temp, "new", (New-Object System.Text.UTF8Encoding($false)))
    [IO.File]::Replace($temp, $target, [NullString]::Value)
    $value = [IO.File]::ReadAllText($target, [System.Text.Encoding]::UTF8)
    if ($value -ne "new") { throw "atomic replace smoke failed: '$value'" }
    Write-Host "[SMOKE] File.Replace atomic state write PASS"

    # Native argv regression for Windows PowerShell 5.1. Empty standalone argv
    # values are dropped by Windows PowerShell, so Fable must pass the empty
    # setting-source list as one non-empty token: --setting-sources=.
    $probeSource = @"
using System;
using System.IO;
public static class LoopNativeProbe {
    public static int Main(string[] args) {
        if (args.Length < 1) return 99;
        if (args[0] == "argv") {
            if (args.Length < 3) return 98;
            File.WriteAllLines(args[1], args);
            return 0;
        }
        if (args[0] == "stderr") {
            Console.Out.WriteLine("native-stdout");
            Console.Error.WriteLine("native-warning");
            return 7;
        }
        return 97;
    }
}
"@
    $probeExe = Join-Path $dir "loop-native-probe.exe"
    Add-Type -TypeDefinition $probeSource -Language CSharp -OutputAssembly $probeExe -OutputType ConsoleApplication
    $argvFile = Join-Path $dir "argv.txt"
    & $probeExe "argv" $argvFile "--setting-sources="
    if ($LASTEXITCODE -ne 0) { throw "native argv probe failed: $LASTEXITCODE" }
    $argvSeen = @(Get-Content -LiteralPath $argvFile)
    if ($argvSeen.Count -lt 3 -or $argvSeen[2] -ne "--setting-sources=") {
        throw "PowerShell did not preserve --setting-sources= as one native argv token: $($argvSeen -join '|')"
    }
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { throw "claude CLI is required for setting-sources parser smoke" }
    $prevEap = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $claudeHelp = @(& claude "--setting-sources=" --help 2>&1)
        $claudeHelpExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
    if ($claudeHelpExit -ne 0) { throw "claude CLI rejected --setting-sources=: exit=$claudeHelpExit output=$($claudeHelp -join ' ')" }
    Write-Host "[CLAUDE-ARGV-SMOKE] PASS"

    # Native stderr regression: with script-wide Stop, a negative native command
    # must still expose stdout/stderr and the real exit code instead of throwing
    # NativeCommandError before evidence capture can run.
    $prevEap = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $nativeOutput = @(& $probeExe "stderr" 2>&1)
        $nativeExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
    $nativeText = ($nativeOutput | ForEach-Object { [string]$_ }) -join "`n"
    if ($nativeExit -ne 7 -or $nativeText -notmatch 'native-warning' -or $nativeText -notmatch 'native-stdout') {
        throw "native stderr capture regression failed: exit=$nativeExit output=$nativeText"
    }
    Write-Host "[NATIVE-STDERR-SMOKE] PASS"
}
finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $dir
}

# PowerShell 5.1 must preserve array shape for singleton Redis exact-key requests.
$singletonKeys = @("pvam:event_delivery:uat-1-smoke")
$singletonJson = ConvertTo-Json -InputObject $singletonKeys -Compress
if (-not $singletonJson.TrimStart().StartsWith("[", [StringComparison]::Ordinal)) {
    throw "Redis singleton array serialization regression: $singletonJson"
}
$roundTripKeys = @($singletonJson | ConvertFrom-Json)
if ($roundTripKeys.Count -ne 1 -or [string]$roundTripKeys[0] -ne [string]$singletonKeys[0]) {
    throw "Redis singleton array roundtrip regression: $singletonJson"
}
Write-Host "[REDIS-ARRAY-SHAPE-SMOKE] PASS"

# Execute the real loop-state.ps1 allocation chain under Windows PowerShell 5.1.
# This specifically guards Generic.List[object] enumeration/interoperability and
# final-audit allocation before any Codex/Claude token spend.
if (-not $env:MAINREPO) { throw "MAINREPO is required for state-machine smoke" }
$stateScript = Join-Path $env:MAINREPO ".loop-engine\loop-state.ps1"
if (-not (Test-Path $stateScript)) { throw "loop-state.ps1 missing for state-machine smoke: $stateScript" }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git is required for state-machine smoke" }

# Loop Core behavior contract: execute the real loop-state.ps1 against synthetic
# durable ledgers before any Codex/Claude token spend.  This covers TEST-01..10
# plus the v20 migration/resume regressions from the architecture review.
$coreBehaviorScript = Join-Path $env:MAINREPO "tests\loop-engine\loop-core-behavior.ps1"
if (-not (Test-Path -LiteralPath $coreBehaviorScript -PathType Leaf)) { throw "Loop Core behavior smoke missing: $coreBehaviorScript" }
& $coreBehaviorScript -Scenario all
if ($LASTEXITCODE -ne 0) { throw "Loop Core behavior smoke failed: exit=$LASTEXITCODE" }
Write-Host "[LOOP-CORE-BEHAVIOR-SMOKE] PASS"

$smokeRoot = Join-Path $env:TEMP ("loop-engine-state-smoke-" + [Guid]::NewGuid().ToString("N"))
$smokeRepo = Join-Path $smokeRoot "repo"
$smokeOut = Join-Path $smokeRoot "out"
$smokeCycles = Join-Path $smokeOut "cycles"
$smokeState = Join-Path $smokeOut "loop-state.json"
$smokeGithubEnv = Join-Path $smokeRoot "github-env.txt"
$smokeGithubOutput = Join-Path $smokeRoot "github-output.txt"
$utf8 = New-Object System.Text.UTF8Encoding($false)

$envNames = @(
    "OUTDIR", "WORKTREE", "SSH_URL", "BRANCH", "LOOP_STATE_FILE",
    "LOOP_CYCLES_DIR", "LOOP_MASTER_AGENTS_SHA256", "GITHUB_ENV", "GITHUB_OUTPUT"
)
$savedEnv = @{}
foreach ($name in $envNames) { $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name) }

try {
    New-Item -ItemType Directory -Force -Path @($smokeRepo, $smokeOut) | Out-Null
    git -C $smokeRepo init -q
    if ($LASTEXITCODE -ne 0) { throw "git init failed in state-machine smoke" }
    git -C $smokeRepo config user.email "loop-smoke@example.invalid"
    git -C $smokeRepo config user.name "Loop Smoke"
    [IO.File]::WriteAllText((Join-Path $smokeRepo "README.txt"), "smoke`n", $utf8)
    git -C $smokeRepo add README.txt
    git -C $smokeRepo commit -q -m "smoke baseline"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed in state-machine smoke" }
    git -C $smokeRepo branch -M smoke
    if ($LASTEXITCODE -ne 0) { throw "git branch rename failed in state-machine smoke" }
    $candidate = (git -C $smokeRepo rev-parse HEAD).Trim().ToLowerInvariant()
    if ($candidate -notmatch '^[0-9a-f]{40}$') { throw "invalid smoke candidate SHA: $candidate" }

    $env:OUTDIR = $smokeOut
    $env:WORKTREE = $smokeRepo
    $env:SSH_URL = "smoke://unused"
    $env:BRANCH = "smoke"
    $env:LOOP_STATE_FILE = $smokeState
    $env:LOOP_CYCLES_DIR = $smokeCycles
    $env:LOOP_MASTER_AGENTS_SHA256 = (("a" * 64) -join "")
    $env:GITHUB_ENV = $smokeGithubEnv
    $env:GITHUB_OUTPUT = $smokeGithubOutput

    & $stateScript -Operation Prepare -RunMode auto
    if ($LASTEXITCODE -ne 0) { throw "state-machine smoke Prepare failed: $LASTEXITCODE" }

    # v13 authorization model: one workflow_dispatch binds a durable Cycle grant.
    # No verifier stage is allowed to invent or expand authorization interactively.
    $missingCycleAuthBlocked = $false
    try {
        & $stateScript -Operation BindCycleUatAuthorization -Cycle 1 `
            -AuthorizationConfirmed "false" `
            -AuthorizationId "" `
            -AuthorizedActions "none" `
            -AuthorizationActor "smoke" `
            -AuthorizationRunId "1" `
            -AuthorizationRunAttempt "1" `
            -TargetNamespace "pvam-uat" `
            -ResourceScope "node/node3,pod/node-debugger-*" `
            -TargetBranch "smoke" `
            -ImpactScope "isolated-uat-only"
    }
    catch {
        if ($_.Exception.Message -notmatch "UAT_WRITE_AUTHORIZATION_REQUIRED") { throw }
        $missingCycleAuthBlocked = $true
    }
    if (-not $missingCycleAuthBlocked) { throw "missing Cycle UAT authorization did not fail closed" }

    & $stateScript -Operation BindCycleUatAuthorization -Cycle 1 `
        -AuthorizationConfirmed "true" `
        -AuthorizationId "SMOKE-AUTH-1" `
        -AuthorizedActions "test-data-write,exec,debug,git-update" `
        -AuthorizationActor "smoke" `
        -AuthorizationRunId "1" `
        -AuthorizationRunAttempt "1" `
        -TargetNamespace "pvam-uat" `
        -ResourceScope "node/node3,pod/node-debugger-*" `
        -TargetBranch "smoke" `
        -ImpactScope "isolated-uat-only"
    if ($LASTEXITCODE -ne 0) { throw "Cycle UAT authorization smoke bind failed: $LASTEXITCODE" }
    $cycleAuthState = [IO.File]::ReadAllText($smokeState, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $cycleAuth = @($cycleAuthState.cycles)[0].uat_cycle_authorization
    if ([string]$cycleAuth.authorization_id -ne "SMOKE-AUTH-1") { throw "Cycle authorization ID not persisted" }
    if ([string]$cycleAuth.cycle_scope_sha256 -notmatch '^[0-9a-f]{64}$') { throw "Cycle authorization scope hash not persisted" }
    Write-Host "[CYCLE-AUTHORIZATION-SMOKE] PASS missing grant blocked; explicit Cycle grant bound"

    # Fault injection: a locked stale Fable checkpoint must block BeginRound before
    # the durable ledger advances. This reproduces the Windows PowerShell 5.1
    # failure mode that silent cleanup used to hide.
    $lockedDir = Join-Path $smokeOut "verifier-state\fable"
    New-Item -ItemType Directory -Force $lockedDir | Out-Null
    $lockedFile = Join-Path $lockedDir "locked.txt"
    [IO.File]::WriteAllText($lockedFile, "locked`n", $utf8)
    $stateBeforeLocked = (Get-FileHash -Algorithm SHA256 $smokeState).Hash.ToLowerInvariant()
    $lockedHandle = [IO.File]::Open($lockedFile, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    $beginBlocked = $false
    try {
        & $stateScript -Operation BeginRound -Cycle 1 -Round 1 -RoundAction construct
    }
    catch {
        $beginBlocked = $true
        Write-Host "[LOCKED-CLEANUP-SMOKE] expected BeginRound block: $($_.Exception.Message)"
    }
    finally {
        $lockedHandle.Dispose()
    }
    if (-not $beginBlocked) { throw "locked stale verifier state did not block BeginRound" }
    if (-not (Test-Path $lockedFile)) { throw "fault injection did not preserve the locked stale verifier file" }
    $stateAfterLocked = (Get-FileHash -Algorithm SHA256 $smokeState).Hash.ToLowerInvariant()
    if ($stateBeforeLocked -ne $stateAfterLocked) { throw "durable state advanced despite locked cleanup failure" }
    Remove-Item -LiteralPath $lockedDir -Recurse -Force -ErrorAction Stop
    if (Test-Path $lockedDir) { throw "locked cleanup smoke could not clear stale Fable state after handle release" }
    Write-Host "[LOCKED-CLEANUP-SMOKE] PASS"

    & $stateScript -Operation BeginRound -Cycle 1 -Round 1 -RoundAction construct
    if ($LASTEXITCODE -ne 0) { throw "state-machine smoke BeginRound failed: $LASTEXITCODE" }
    & $stateScript -Operation SetCandidate -Cycle 1 -Round 1 -CandidateSha $candidate
    if ($LASTEXITCODE -ne 0) { throw "state-machine smoke SetCandidate failed: $LASTEXITCODE" }

    & $stateScript -Operation BindUatWriteAuthorization -Cycle 1 -Round 1 -VerifierStage "OPUS"
    if ($LASTEXITCODE -ne 0) { throw "Opus UAT authorization smoke bind failed: $LASTEXITCODE" }
    $authorizedState = [IO.File]::ReadAllText($smokeState, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $authorizedRound = @($authorizedState.cycles[0].rounds)[0]
    if ([string]$authorizedRound.uat_write_authorization_opus.authorization_id -ne "SMOKE-AUTH-1") { throw "Opus authorization ID not persisted" }
    if ([string]$authorizedRound.uat_write_authorization_opus_sha256 -notmatch '^[0-9a-f]{64}$') { throw "Opus authorization scope hash not persisted" }
    if ([string]$authorizedRound.uat_write_authorization_opus.uat_execution_id -notmatch '^c1-r1-opus-s[0-9]+-[0-9a-f]{12}$') { throw "Opus durable uat_execution_id not persisted" }
    Write-Host "[UAT-AUTHORIZATION-SMOKE] Opus stage grant derived from durable Cycle authorization execution=$($authorizedRound.uat_write_authorization_opus.uat_execution_id)"

    $state = [IO.File]::ReadAllText($smokeState, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $round = @($state.cycles[0].rounds)[0]
    $opusProgressPath = Join-Path $smokeOut "verifier-state\opus\verifier-progress.json"
    $opusDir = Split-Path -Parent $opusProgressPath
    New-Item -ItemType Directory -Force $opusDir | Out-Null
    $opusProgress = [ordered]@{
        schema_version = 5
        verifier_stage = "OPUS"
        candidate_sha = $candidate
        uat_period_slot = [int]$round.uat_period_slot
        uat_period_primary = [int]$round.uat_period_primary
        uat_period_secondary = [int]$round.uat_period_secondary
        uat_period_pool_sha256 = [string]$round.uat_period_pool_sha256
        status = "COMPLETE"
        final_verdict = "PRECHECK_PASS"
    }
    [IO.File]::WriteAllText($opusProgressPath, (($opusProgress | ConvertTo-Json -Depth 20) + "`n"), $utf8)
    [IO.File]::WriteAllText((Join-Path $smokeOut "opus-result.txt"), "PRECHECK_PASS`n", $utf8)

    & $stateScript -Operation AllocateFinalAuditPeriod -Cycle 1 -Round 1
    if ($LASTEXITCODE -ne 0) { throw "state-machine smoke AllocateFinalAuditPeriod failed: $LASTEXITCODE" }
    & $stateScript -Operation BindUatWriteAuthorization -Cycle 1 -Round 1 -VerifierStage "FABLE"
    if ($LASTEXITCODE -ne 0) { throw "Fable UAT authorization smoke bind failed: $LASTEXITCODE" }
    $finalState = [IO.File]::ReadAllText($smokeState, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $finalRound = @($finalState.cycles[0].rounds)[0]
    if (-not [string]$finalRound.final_audit_uat_period_slot) { throw "state-machine smoke did not allocate Fable final-audit slot" }
    if ([int]$finalRound.final_audit_uat_period_slot -eq [int]$finalRound.uat_period_slot) { throw "state-machine smoke reused Opus period slot for Fable" }
    if ([string]$finalRound.uat_write_authorization_fable.authorization_id -ne "SMOKE-AUTH-1") { throw "Fable authorization ID not persisted" }
    if ([string]$finalRound.uat_write_authorization_fable_sha256 -notmatch '^[0-9a-f]{64}$') { throw "Fable authorization scope hash not persisted" }
    if ([string]$finalRound.uat_write_authorization_fable.uat_execution_id -notmatch '^c1-r1-fable-s[0-9]+-[0-9a-f]{12}$') { throw "Fable durable uat_execution_id not persisted" }
    if ([string]$finalRound.uat_write_authorization_fable.uat_execution_id -eq [string]$authorizedRound.uat_write_authorization_opus.uat_execution_id) { throw "Opus/Fable durable UAT execution IDs must differ by stage" }
    Write-Host "[UAT-AUTHORIZATION-SMOKE] PASS stage grants bound to candidate and period allocations"
    Write-Host "[STATE-MACHINE-SMOKE] PASS Prepare -> BindCycleUatAuthorization -> BeginRound -> SetCandidate -> BindUatWriteAuthorization -> AllocateFinalAuditPeriod"

    # Build a real final-audit BLOCKED state, complete it through the state
    # machine, then reopen it with auto/resume-verifier. The old final evidence
    # marker proves only the blocked attempt and must be cleared so a later
    # PASS/REJECTED can bind new verified evidence for the same Round.
    $uatReport = Join-Path $smokeOut "UAT_REPORT.md"
    [IO.File]::WriteAllText($uatReport, "# smoke UAT`n`n## Opus Verification`nPRECHECK_PASS`n", $utf8)
    $reportHash = (Get-FileHash -Algorithm SHA256 $uatReport).Hash.ToLowerInvariant()
    $reportLength = (Get-Item -LiteralPath $uatReport).Length
    & $stateScript -Operation BindOpusReportBaseline -Cycle 1 -Round 1 -OpusReportSha256 $reportHash -OpusReportLength $reportLength
    if ($LASTEXITCODE -ne 0) { throw "BLOCKED resume smoke BindOpusReportBaseline failed: $LASTEXITCODE" }

    $blockedSetupState = [IO.File]::ReadAllText($smokeState, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $blockedSetupRound = @($blockedSetupState.cycles[0].rounds)[0]
    $fableDir = Join-Path $smokeOut "verifier-state\fable"
    New-Item -ItemType Directory -Force $fableDir | Out-Null
    $fableBlocked = [ordered]@{
        schema_version = 5
        verifier_stage = "FABLE"
        candidate_sha = $candidate
        uat_period_slot = [int]$blockedSetupRound.final_audit_uat_period_slot
        uat_period_primary = [int]$blockedSetupRound.final_audit_uat_period_primary
        uat_period_secondary = [int]$blockedSetupRound.final_audit_uat_period_secondary
        uat_period_pool_sha256 = [string]$blockedSetupRound.final_audit_uat_period_pool_sha256
        status = "BLOCKED"
        final_verdict = "BLOCKED"
    }
    [IO.File]::WriteAllText((Join-Path $fableDir "verifier-progress.json"), (($fableBlocked | ConvertTo-Json -Depth 20) + "`n"), $utf8)
    [IO.File]::AppendAllText($uatReport, "`n## Fable Final Audit`nBLOCKED`n", $utf8)
    [IO.File]::WriteAllText((Join-Path $smokeOut "uat-result.txt"), "BLOCKED`n", $utf8)
    $protectedHash = (("c" * 64) -join "")
    & $stateScript -Operation BindProtectedEvidenceBaseline -Cycle 1 -Round 1 -ProtectedEvidenceSha256 $protectedHash
    if ($LASTEXITCODE -ne 0) { throw "BLOCKED resume smoke BindProtectedEvidenceBaseline failed: $LASTEXITCODE" }
    & $stateScript -Operation MarkFinalAuditEvidenceVerified -Cycle 1 -Round 1 -Verdict BLOCKED -ProtectedEvidenceSha256 $protectedHash
    if ($LASTEXITCODE -ne 0) { throw "BLOCKED resume smoke MarkFinalAuditEvidenceVerified failed: $LASTEXITCODE" }
    & $stateScript -Operation CompleteRound -Cycle 1 -Round 1 -Verdict BLOCKED
    if ($LASTEXITCODE -ne 0) { throw "BLOCKED resume smoke CompleteRound failed: $LASTEXITCODE" }

    $completedBlocked = [IO.File]::ReadAllText($smokeState, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $completedBlockedRound = @($completedBlocked.cycles[0].rounds)[0]
    if ([string]$completedBlocked.status -ne "BLOCKED" -or [string]$completedBlockedRound.phase -ne "COMPLETE" -or [string]$completedBlockedRound.final_audit_evidence_verified_verdict -ne "BLOCKED") {
        throw "BLOCKED resume smoke did not produce a canonical completed BLOCKED Round"
    }

    & $stateScript -Operation Prepare -RunMode auto
    if ($LASTEXITCODE -ne 0) { throw "BLOCKED resume smoke Prepare failed: $LASTEXITCODE" }
    & $stateScript -Operation BeginRound -Cycle 1 -Round 1 -RoundAction resume-verifier
    if ($LASTEXITCODE -ne 0) { throw "BLOCKED resume smoke BeginRound failed: $LASTEXITCODE" }
    $resumedState = [IO.File]::ReadAllText($smokeState, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $resumedRound = @($resumedState.cycles[0].rounds)[0]
    if ([string]$resumedRound.phase -ne "VERIFYING") { throw "BLOCKED resume did not reopen VERIFYING" }
    if ([string]$resumedRound.verdict) { throw "BLOCKED resume retained stale verdict" }
    foreach ($markerName in @("final_audit_evidence_verified", "final_audit_evidence_verified_verdict", "final_audit_evidence_verified_protected_sha256", "final_audit_evidence_verified_at")) {
        if ([string]$resumedRound.$markerName) { throw "BLOCKED resume retained stale marker $markerName=$($resumedRound.$markerName)" }
    }
    Write-Host "[BLOCKED-RESUME-SMOKE] PASS"

    # The reopened Round can bind a different verified verdict using the same
    # protected baseline. Then tamper a protected Round field and prove Prepare /
    # Reconcile cannot accept the marked PASS after the contract changes.
    $resumedForPass = [IO.File]::ReadAllText($smokeState, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $resumedPassRound = @($resumedForPass.cycles[0].rounds)[0]
    $fablePass = [ordered]@{
        schema_version = 5
        verifier_stage = "FABLE"
        candidate_sha = $candidate
        uat_period_slot = [int]$resumedPassRound.final_audit_uat_period_slot
        uat_period_primary = [int]$resumedPassRound.final_audit_uat_period_primary
        uat_period_secondary = [int]$resumedPassRound.final_audit_uat_period_secondary
        uat_period_pool_sha256 = [string]$resumedPassRound.final_audit_uat_period_pool_sha256
        status = "COMPLETE"
        final_verdict = "PASS"
    }
    [IO.File]::WriteAllText((Join-Path $fableDir "verifier-progress.json"), (($fablePass | ConvertTo-Json -Depth 20) + "`n"), $utf8)
    [IO.File]::WriteAllText((Join-Path $smokeOut "uat-result.txt"), "PASS`n", $utf8)
    & $stateScript -Operation MarkFinalAuditEvidenceVerified -Cycle 1 -Round 1 -Verdict PASS -ProtectedEvidenceSha256 $protectedHash
    if ($LASTEXITCODE -ne 0) { throw "contract smoke MarkFinalAuditEvidenceVerified PASS failed after BLOCKED resume: $LASTEXITCODE" }

    $tampered = [IO.File]::ReadAllText($smokeState, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $tamperedRound = @($tampered.cycles[0].rounds)[0]
    $tamperedRound.master_agents_sha256 = (("d" * 64) -join "")
    [IO.File]::WriteAllText($smokeState, (($tampered | ConvertTo-Json -Depth 50) + "`n"), $utf8)
    & $stateScript -Operation Prepare -RunMode auto
    if ($LASTEXITCODE -ne 0) { throw "contract tamper Prepare should remain recoverable, exit=$LASTEXITCODE" }
    $afterTamper = [IO.File]::ReadAllText($smokeState, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $afterTamperRound = @($afterTamper.cycles[0].rounds)[0]
    if ([string]$afterTamperRound.phase -eq "COMPLETE" -or [string]$afterTamper.status -eq "COMPLETED") {
        throw "tampered protected Round contract was accepted as PASS"
    }
    Write-Host "[ROUND-CONTRACT-TAMPER-SMOKE] PASS"
}
finally {
    foreach ($name in $envNames) {
        $value = $savedEnv[$name]
        if ($null -eq $value) { [Environment]::SetEnvironmentVariable($name, $null) }
        else { [Environment]::SetEnvironmentVariable($name, [string]$value) }
    }
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $smokeRoot
}


# Integration regression: execute the real verifier preparation script for a
# synthetic Fable checkpoint and validate the generated effective settings with
# the same proxy rule contract used by loop-round.yml.
$prepareScript = Join-Path $env:MAINREPO ".loop-engine\prepare-verifier-state.ps1"
if (-not (Test-Path $prepareScript)) { throw "prepare-verifier-state.ps1 missing for permission integration smoke: $prepareScript" }
$permRoot = Join-Path $env:TEMP ("loop-engine-permission-smoke-" + [Guid]::NewGuid().ToString("N"))
$permRepo = Join-Path $permRoot "repo"
$permBare = Join-Path $permRoot "remote.git"
$permOut = Join-Path $permRoot "out"
$permState = Join-Path $permOut "verifier-state\fable"
$permRuntime = Join-Path $permOut "verifier-runtime\fable"
$permHistory = Join-Path $permOut "verifier-history\fable"
$permGithubEnv = Join-Path $permRoot "github-env.txt"
$permPrompt = Join-Path $permRoot "prompt.md"
$permOverride = Join-Path $permRoot "override.md"
$permProtocol = Join-Path $permRoot "protocol.md"
$permSettings = Join-Path $permRoot "settings.json"
$permAgents = Join-Path $permRoot "master-AGENTS.md"
$permUtf8 = New-Object System.Text.UTF8Encoding($false)
$permEnvNames = @(
    "OUTDIR", "WORKTREE", "SSH_URL", "BRANCH", "VERIFIER_STAGE", "VERIFIER_RESULT_FILE",
    "CLAUDE_MODEL", "CLAUDE_EFFORT", "VERIFIER_PROMPT", "VERIFIER_OVERRIDE", "VERIFIER_PROTOCOL",
    "VERIFIER_SETTINGS", "VERIFIER_RUNTIME_DIR", "VERIFIER_HISTORY_DIR", "VERIFIER_STATE_DIR",
    "VERIFIER_PROGRESS", "VERIFIER_RESUME_CONTEXT", "LOOP_FINAL_UAT_PERIOD_SLOT",
    "LOOP_FINAL_UAT_PERIOD_PRIMARY", "LOOP_FINAL_UAT_PERIOD_SECONDARY", "LOOP_FINAL_UAT_PERIOD_POOL_SHA256",
    "LOOP_UAT_AUTHORIZATION_ID", "LOOP_UAT_AUTHORIZED_ACTIONS", "LOOP_UAT_AUTHORIZATION_SCOPE_SHA256",
    "LOOP_UAT_AUTHORIZATION_ACTOR", "LOOP_UAT_AUTHORIZATION_STAGE", "LOOP_UAT_CYCLE_SCOPE_SHA256", "LOOP_UAT_EXECUTION_ID",
    "LOOP_UAT_TARGET_NAMESPACE", "LOOP_UAT_RESOURCE_SCOPE", "LOOP_UAT_TARGET_BRANCH", "LOOP_UAT_IMPACT_SCOPE",
    "LOOP_MASTER_AGENTS_SNAPSHOT", "LOOP_MASTER_AGENTS_SHA256", "UAT_ACTION_PROXY_ALLOW",
    "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_ENV"
)
$permSavedEnv = @{}
foreach ($name in $permEnvNames) { $permSavedEnv[$name] = [Environment]::GetEnvironmentVariable($name) }
try {
    New-Item -ItemType Directory -Force -Path @($permRepo, $permOut, $permState, $permRuntime, $permHistory) | Out-Null
    git -C $permRepo init -q
    if ($LASTEXITCODE -ne 0) { throw "permission smoke git init failed" }
    git -C $permRepo config user.email "loop-permission-smoke@example.invalid"
    git -C $permRepo config user.name "Loop Permission Smoke"
    [IO.File]::WriteAllText((Join-Path $permRepo "README.txt"), "permission-smoke`n", $permUtf8)
    git -C $permRepo add README.txt
    git -C $permRepo commit -q -m "permission smoke"
    if ($LASTEXITCODE -ne 0) { throw "permission smoke git commit failed" }
    $permCandidate = (git -C $permRepo rev-parse HEAD).Trim().ToLowerInvariant()
    git init --bare -q $permBare
    if ($LASTEXITCODE -ne 0) { throw "permission smoke bare git init failed" }
    git -C $permRepo push -q $permBare "HEAD:refs/heads/smoke"
    if ($LASTEXITCODE -ne 0) { throw "permission smoke git push failed" }

    [IO.File]::WriteAllText((Join-Path $permOut "pushed-sha.txt"), "$permCandidate`n", $permUtf8)
    [IO.File]::WriteAllText($permPrompt, "prompt`n", $permUtf8)
    [IO.File]::WriteAllText($permOverride, "override`n", $permUtf8)
    [IO.File]::WriteAllText($permProtocol, "protocol`n", $permUtf8)
    [IO.File]::WriteAllText($permSettings, "{}`n", $permUtf8)
    [IO.File]::WriteAllText($permAgents, "# agents`n", $permUtf8)
    $opusPinDir = Join-Path $permOut "verifier-state\opus"
    New-Item -ItemType Directory -Force $opusPinDir | Out-Null
    [IO.File]::WriteAllText((Join-Path $opusPinDir "UAT_REPORT.pre-fable.md"), "# report`n", $permUtf8)

    $permProxyAllow = "Bash(powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/Redemption/Redemption/.loop-engine/uat-action-proxy.ps1)"
    $permAgentsSha = (Get-FileHash -Algorithm SHA256 $permAgents).Hash.ToLowerInvariant()
    $env:OUTDIR = $permOut
    $env:WORKTREE = $permRepo
    $env:SSH_URL = $permBare
    $env:BRANCH = "smoke"
    $env:VERIFIER_STAGE = "FABLE"
    $env:VERIFIER_RESULT_FILE = Join-Path $permOut "uat-result.txt"
    $env:CLAUDE_MODEL = "fable"
    $env:CLAUDE_EFFORT = "ultracode"
    $env:VERIFIER_PROMPT = $permPrompt
    $env:VERIFIER_OVERRIDE = $permOverride
    $env:VERIFIER_PROTOCOL = $permProtocol
    $env:VERIFIER_SETTINGS = $permSettings
    $env:VERIFIER_RUNTIME_DIR = $permRuntime
    $env:VERIFIER_HISTORY_DIR = $permHistory
    $env:VERIFIER_STATE_DIR = $permState
    $env:VERIFIER_PROGRESS = Join-Path $permState "verifier-progress.json"
    $env:VERIFIER_RESUME_CONTEXT = Join-Path $permState "resume-context.md"
    $env:LOOP_FINAL_UAT_PERIOD_SLOT = "10"
    $env:LOOP_FINAL_UAT_PERIOD_PRIMARY = "990019"
    $env:LOOP_FINAL_UAT_PERIOD_SECONDARY = "990020"
    $env:LOOP_FINAL_UAT_PERIOD_POOL_SHA256 = ("b" * 64)
    $env:LOOP_UAT_AUTHORIZATION_ID = "SMOKE-AUTH-FABLE"
    $env:LOOP_UAT_AUTHORIZED_ACTIONS = "test-data-write,exec,debug,git-update"
    $env:LOOP_UAT_AUTHORIZATION_SCOPE_SHA256 = ("c" * 64)
    $env:LOOP_UAT_AUTHORIZATION_ACTOR = "smoke"
    $env:LOOP_UAT_AUTHORIZATION_STAGE = "FABLE"
    $env:LOOP_UAT_CYCLE_SCOPE_SHA256 = ("d" * 64)
    $env:LOOP_UAT_EXECUTION_ID = "c1-r1-fable-s10-$($permCandidate.Substring(0,12))"
    $env:LOOP_UAT_TARGET_NAMESPACE = "pvam-uat"
    $env:LOOP_UAT_RESOURCE_SCOPE = "node/node3,pod/node-debugger-*"
    $env:LOOP_UAT_TARGET_BRANCH = "smoke"
    $env:LOOP_UAT_IMPACT_SCOPE = "isolated-uat-only"
    $env:LOOP_MASTER_AGENTS_SNAPSHOT = $permAgents
    $env:LOOP_MASTER_AGENTS_SHA256 = $permAgentsSha
    $env:UAT_ACTION_PROXY_ALLOW = $permProxyAllow
    $env:GITHUB_RUN_ID = "123456"
    $env:GITHUB_RUN_ATTEMPT = "1"
    $env:GITHUB_ENV = $permGithubEnv

    & $prepareScript
    if ($LASTEXITCODE -ne 0) { throw "permission integration prepare failed: $LASTEXITCODE" }
    $effectiveSettingsPath = Join-Path $permRuntime "verifier-settings.effective.json"
    if (-not (Test-Path $effectiveSettingsPath)) { throw "permission integration effective settings missing" }
    $effectiveSettings = [IO.File]::ReadAllText($effectiveSettingsPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    $allow = @($effectiveSettings.permissions.allow)
    $deny = @($effectiveSettings.permissions.deny)
    foreach ($required in @("Edit(.loop-output/UAT_REPORT.md)", "Edit(.loop-output/uat-result.txt)", "Edit(.loop-output/verifier-state/fable/**)", $permProxyAllow)) {
        if ($allow -notcontains $required) { throw "permission integration missing Fable allow: $required" }
    }
    $shellAllows = @($allow | Where-Object { ([string]$_) -match '^(Bash|PowerShell)' })
    if ($shellAllows.Count -ne 1 -or [string]$shellAllows[0] -ne $permProxyAllow) {
        throw "permission integration shell allow mismatch: $($shellAllows -join '|')"
    }
    foreach ($protected in @("Edit(.loop-output/verifier-state/opus/**)", "Edit(.loop-output/loop-state.json)", "Edit(.loop-output/controller-evidence/**)")) {
        if ($allow -contains $protected -or $deny -notcontains $protected) { throw "permission integration protected evidence mismatch: $protected" }
    }
    Write-Host "[FABLE-PERMISSION-INTEGRATION-SMOKE] PASS"
}
finally {
    foreach ($name in $permEnvNames) {
        $value = $permSavedEnv[$name]
        if ($null -eq $value) { [Environment]::SetEnvironmentVariable($name, $null) }
        else { [Environment]::SetEnvironmentVariable($name, [string]$value) }
    }
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $permRoot
}


# Controller-evidence behavior regression: missing evidence and forged request hashes
# must fail closed; a complete controller-owned record must pass.
$verifyProxyScript = Join-Path $env:MAINREPO ".loop-engine\verify-proxy-period-evidence.ps1"
if (-not (Test-Path $verifyProxyScript)) { throw "verify-proxy-period-evidence.ps1 missing: $verifyProxyScript" }
$evidenceSmokeRoot = Join-Path $env:TEMP ("loop-engine-proxy-evidence-smoke-" + [Guid]::NewGuid().ToString("N"))
$evidenceDir = Join-Path $evidenceSmokeRoot "evidence"
$policyPath = Join-Path $evidenceSmokeRoot "policy.json"
$evUtf8 = New-Object System.Text.UTF8Encoding($false)
$evPool = ("a" * 64)
$evScope = ("b" * 64)
$evExecution = "c1-r1-opus-s1-0123456789ab"
$evCandidate = ("c" * 40)
try {
    New-Item -ItemType Directory -Force $evidenceSmokeRoot | Out-Null
    [IO.File]::WriteAllText($policyPath, '{"schema_version":8,"controller_evidence_schema":10,"required_success_actions_by_stage":{"OPUS":[],"FABLE":[]},"redis_dbsize_required_phases":[],"pytest_selected_required_targets":[],"required_idempotency_namespaces":[],"git_change_allowlist":[],"kafka_topics":[],"required_kafka_scenarios_by_stage":{"OPUS":[],"FABLE":[]},"required_consumer_lifecycle_ops_by_stage":{"OPUS":[],"FABLE":[]},"consumer_observation_required_scenarios_by_stage":{"OPUS":[],"FABLE":[]},"scenarios_require_dispatched_three_chain":[],"scenarios_require_no_redis_side_effects":[],"scenario_expected_exception_reason":{},"scenario_expected_offset_semantics":{},"mandatory_uat_proofs_by_stage":{"OPUS":[],"FABLE":[]},"required_redis_proofs_by_stage":{"OPUS":[],"FABLE":[]},"redis_proof_contracts":{},"dispatch_p99_sample_count":20,"dispatch_p99_max_ms":5000}' + "`n", $evUtf8)

    $missingBlocked = $false
    try {
        & $verifyProxyScript -Stage OPUS -EvidenceDir $evidenceDir -ExpectedSlot 1 -ExpectedPrimary 990001 -ExpectedSecondary 990002 -ExpectedPoolSha256 $evPool -ExpectedAuthorizationScopeSha256 $evScope -ExpectedExecutionId $evExecution -PolicyPath $policyPath -VerificationMode RequireComplete -ExpectedCandidateSha $evCandidate | Out-Null
    }
    catch { $missingBlocked = $_.Exception.Message -like '*proxy evidence directory missing*' }
    if (-not $missingBlocked) { throw "missing controller proxy evidence did not fail closed with proxy evidence directory missing" }

    New-Item -ItemType Directory -Force $evidenceDir | Out-Null
    $requestRaw = '{"action":"Readyz"}'
    $requestB64 = [Convert]::ToBase64String($evUtf8.GetBytes($requestRaw))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $requestHash = ([BitConverter]::ToString($sha.ComputeHash($evUtf8.GetBytes($requestRaw)))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    $record = @(
        'stage=OPUS',
        'action=Readyz',
        "request_sha256=$('0' * 64)",
        "request_json_b64=$requestB64",
        "stage_scope_sha256=$evScope",
        "uat_execution_id=$evExecution",
        'stage_period_slot=1',
        'stage_period_primary=990001',
        'stage_period_secondary=990002',
        "stage_period_pool_sha256=$evPool",
        'authorized_actions=exec',
        'required_tokens=',
        'outcome=SUCCESS',
        'exit_code=0'
    )
    $recordPath = Join-Path $evidenceDir 'action-forged.log'
    [IO.File]::WriteAllText($recordPath, (($record -join "`n") + "`n"), $evUtf8)
    $forgedBlocked = $false
    try {
        & $verifyProxyScript -Stage OPUS -EvidenceDir $evidenceDir -ExpectedSlot 1 -ExpectedPrimary 990001 -ExpectedSecondary 990002 -ExpectedPoolSha256 $evPool -ExpectedAuthorizationScopeSha256 $evScope -ExpectedExecutionId $evExecution -PolicyPath $policyPath -VerificationMode ValidateExistingOnly -ExpectedCandidateSha $evCandidate | Out-Null
    }
    catch { $forgedBlocked = $_.Exception.Message -like '*request hash mismatch*' }
    if (-not $forgedBlocked) { throw "forged proxy request SHA did not fail closed with request hash mismatch" }

    $record[2] = "request_sha256=$requestHash"
    [IO.File]::WriteAllText($recordPath, (($record -join "`n") + "`n"), $evUtf8)
    & $verifyProxyScript -Stage OPUS -EvidenceDir $evidenceDir -ExpectedSlot 1 -ExpectedPrimary 990001 -ExpectedSecondary 990002 -ExpectedPoolSha256 $evPool -ExpectedAuthorizationScopeSha256 $evScope -ExpectedExecutionId $evExecution -PolicyPath $policyPath -VerificationMode ValidateExistingOnly -ExpectedCandidateSha $evCandidate | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "valid controller proxy evidence did not pass" }
    Write-Host "[PROXY-EVIDENCE-SMOKE] PASS missing/forged fail closed; valid record passes"
}
finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $evidenceSmokeRoot
}

Write-Host "=== WINDOWS POWERSHELL SMOKE PASS ==="


# V20-SECURITY-STATIC-GATES
# These are static gates only; the target runner still executes the real runtime checks.
$stateContract = [IO.File]::ReadAllText((Join-Path $env:MAINREPO ".loop-engine\loop-state.ps1"), [Text.Encoding]::UTF8)
$roundContract = [IO.File]::ReadAllText((Join-Path $env:MAINREPO ".github\workflows\loop-round.yml"), [Text.Encoding]::UTF8)
$proxyContract = [IO.File]::ReadAllText((Join-Path $env:MAINREPO ".loop-engine\uat-action-proxy.ps1"), [Text.Encoding]::UTF8)
$consumerRuntimeContract = [IO.File]::ReadAllText((Join-Path $env:MAINREPO ".loop-engine\consumer-runtime-controller-r9.py"), [Text.Encoding]::UTF8)
$verifyContract = [IO.File]::ReadAllText((Join-Path $env:MAINREPO ".loop-engine\verify-proxy-period-evidence.ps1"), [Text.Encoding]::UTF8)
$policyV20 = [IO.File]::ReadAllText((Join-Path $env:MAINREPO ".loop-engine\uat-action-policy.json"), [Text.Encoding]::UTF8) | ConvertFrom-Json
if ($stateContract -notmatch 'LOOP_CANDIDATE_SHA') { throw "v20 candidate SHA export missing" }
if ($roundContract -notmatch 'controller-evidence\\schema-10') { throw "v20 schema-10 workflow root missing" }
if ($proxyContract -notmatch 'output_json_b64') { throw "v20 base64 output evidence missing" }
if ($proxyContract -match '\$lines\.Add\("output_(begin|end)"\)') { throw "v20 legacy raw output sentinel remains" }
if ($proxyContract -notmatch 'scheduler-pod-temporary-process') { throw "v20 scheduler Pod Consumer runtime mode missing" }
if ($consumerRuntimeContract -notmatch 'DEFAULT_RUNTIME_ROOT = "/tmp/pvam-uat-consumer"') { throw "v20 execution-scoped Consumer runtime state missing" }
if ($proxyContract -notmatch 'ConsumerLifecycle.*restore' -and $proxyContract -notmatch "operation='restore'") { throw "v20 ConsumerLifecycle restore missing" }
if ($verifyContract -notmatch 'function Read-ProxyEvidenceFields') { throw "v20 strict evidence parser missing" }
if ($verifyContract -match 'if\s*\(\s*\$ExpectedCandidateSha\s+(-and|\))') { throw "v20 optional candidate guard remains" }
if ([int]$policyV20.schema_version -ne 8 -or [int]$policyV20.controller_evidence_schema -ne 10) { throw "v20 policy/schema mismatch" }
if ($null -eq $policyV20.consumer_runtime_target -or [string]$policyV20.consumer_runtime_target.mode -ne 'scheduler-pod-temporary-process') { throw "v20 consumer_runtime_target missing" }
if (-not $policyV20.git_hunk_allowlist.'User/UserStatsService.py') { throw "v20 UserStats line-level Git hunk guard missing" }
if (-not $policyV20.git_hunk_allowlist.'User/EliteBonusService.py') { throw "v20 EliteBonus line-level Git hunk guard missing" }
if (@($policyV20.pytest_selected_required_targets) -notcontains 'User/Test/test_amount_dtype_migration.py') { throw "v20 amount dtype migration required pytest target missing" }
if ($proxyContract -notmatch 'function Invoke-ControllerUatProducer') { throw "v20 controller-owned UAT producer missing" }
if ($proxyContract -match 'tests/pvam/WORK-PVAM-02/uat_message_producer.py') { throw "v20 Candidate-owned UAT producer path remains" }
if ($proxyContract -notmatch 'business_value_proof_ok') { throw "v20 UserStats business-value proof missing" }
if ($verifyContract -notmatch 'mandatory UAT proof missing') { throw "v20 mandatory UAT proof verifier gate missing" }
$opusProofs = @($policyV20.mandatory_uat_proofs_by_stage.OPUS | ForEach-Object { [string]$_ })
foreach ($proof in @('cross-period-refund-routing','duplicate-no-double','pending-dispatched-recovery','int64-end-to-end','pause-rebalance','dispatch-p99')) {
    if ($opusProofs -notcontains $proof) { throw "v20 mandatory OPUS proof missing: $proof" }
}
Write-Host "[V20-SECURITY-STATIC-GATES] PASS"


# V20-EVIDENCE-INJECTION-SMOKE
# Prove on the Windows runtime that raw sentinel lines and duplicate metadata
# cannot be reinterpreted as trusted controller fields under schema 10.
$v20EvidenceSmokeRoot = Join-Path $env:TEMP ("loop-engine-v20-evidence-injection-" + [Guid]::NewGuid().ToString("N"))
$v20EvidenceDir = Join-Path $v20EvidenceSmokeRoot "evidence"
$v20PolicyPath = Join-Path $v20EvidenceSmokeRoot "policy.json"
$v20VerifyProxyScript = Join-Path $env:MAINREPO ".loop-engine\verify-proxy-period-evidence.ps1"
$v20Utf8 = New-Object System.Text.UTF8Encoding($false)
$v20Pool = ("a" * 64)
$v20Scope = ("b" * 64)
$v20Candidate = ("c" * 40)
$v20Execution = "c1-r1-opus-s1-cccccccccccc"
try {
    New-Item -ItemType Directory -Force $v20EvidenceDir | Out-Null
    $v20PolicyJson = '{"schema_version":8,"controller_evidence_schema":10,"required_success_actions_by_stage":{"OPUS":[],"FABLE":[]},"redis_dbsize_required_phases":[],"pytest_selected_required_targets":[],"required_idempotency_namespaces":[],"git_change_allowlist":[],"kafka_topics":[],"required_kafka_scenarios_by_stage":{"OPUS":[],"FABLE":[]},"required_consumer_lifecycle_ops_by_stage":{"OPUS":[],"FABLE":[]},"consumer_observation_required_scenarios_by_stage":{"OPUS":[],"FABLE":[]},"scenarios_require_dispatched_three_chain":[],"scenarios_require_no_redis_side_effects":[],"scenario_expected_exception_reason":{},"scenario_expected_offset_semantics":{},"mandatory_uat_proofs_by_stage":{"OPUS":[],"FABLE":[]},"required_redis_proofs_by_stage":{"OPUS":[],"FABLE":[]},"redis_proof_contracts":{},"dispatch_p99_sample_count":20,"dispatch_p99_max_ms":5000}' + "`n"
    [IO.File]::WriteAllText($v20PolicyPath, $v20PolicyJson, $v20Utf8)

    $v20RequestRaw = '{"action":"Readyz"}'
    $v20RequestB64 = [Convert]::ToBase64String($v20Utf8.GetBytes($v20RequestRaw))
    $v20Sha = [Security.Cryptography.SHA256]::Create()
    try { $v20RequestHash = ([BitConverter]::ToString($v20Sha.ComputeHash($v20Utf8.GetBytes($v20RequestRaw)))).Replace('-', '').ToLowerInvariant() }
    finally { $v20Sha.Dispose() }
    $v20Base = @(
        'stage=OPUS',
        'action=Readyz',
        "request_sha256=$v20RequestHash",
        "request_json_b64=$v20RequestB64",
        "stage_scope_sha256=$v20Scope",
        "uat_execution_id=$v20Execution",
        'stage_period_slot=1',
        'stage_period_primary=990001',
        'stage_period_secondary=990002',
        "stage_period_pool_sha256=$v20Pool",
        'authorized_actions=exec',
        'required_tokens=',
        'outcome=DENIED',
        'exit_code=1'
    )
    $v20RecordPath = Join-Path $v20EvidenceDir 'action-injection.log'

    [IO.File]::WriteAllText($v20RecordPath, ((($v20Base + @('output_end','action=GitUpdate','outcome=SUCCESS','exit_code=0')) -join "`n") + "`n"), $v20Utf8)
    $v20SentinelBlocked = $false
    try {
        & $v20VerifyProxyScript -Stage OPUS -EvidenceDir $v20EvidenceDir -ExpectedSlot 1 -ExpectedPrimary 990001 -ExpectedSecondary 990002 -ExpectedPoolSha256 $v20Pool -ExpectedAuthorizationScopeSha256 $v20Scope -ExpectedExecutionId $v20Execution -ExpectedCandidateSha $v20Candidate -PolicyPath $v20PolicyPath -VerificationMode ValidateExistingOnly | Out-Null
    }
    catch { $v20SentinelBlocked = $_.Exception.Message -like '*PROXY_EVIDENCE_INVALID*' }
    if (-not $v20SentinelBlocked) { throw "v20 raw output_end injection was not rejected" }

    [IO.File]::WriteAllText($v20RecordPath, ((($v20Base + @('action=GitUpdate')) -join "`n") + "`n"), $v20Utf8)
    $v20DuplicateBlocked = $false
    try {
        & $v20VerifyProxyScript -Stage OPUS -EvidenceDir $v20EvidenceDir -ExpectedSlot 1 -ExpectedPrimary 990001 -ExpectedSecondary 990002 -ExpectedPoolSha256 $v20Pool -ExpectedAuthorizationScopeSha256 $v20Scope -ExpectedExecutionId $v20Execution -ExpectedCandidateSha $v20Candidate -PolicyPath $v20PolicyPath -VerificationMode ValidateExistingOnly | Out-Null
    }
    catch { $v20DuplicateBlocked = $_.Exception.Message -like '*duplicate field*' }
    if (-not $v20DuplicateBlocked) { throw "v20 duplicate metadata injection was not rejected" }
    Write-Host "[V20-EVIDENCE-INJECTION-SMOKE] PASS"
}
finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $v20EvidenceSmokeRoot
}
