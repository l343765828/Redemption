$ErrorActionPreference = "Stop"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force $parent | Out-Null
    }
    [IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Append-GitHubEnv([string]$Name, [string]$Value) {
    if (-not $env:GITHUB_ENV) { return }
    [IO.File]::AppendAllText($env:GITHUB_ENV, "$Name=$Value`n", $Utf8NoBom)
}

function Get-FileSha256([string]$Path) {
    if (-not (Test-Path $Path)) { throw "required file missing: $Path" }
    return (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
}

function Get-TextSha256([string]$Text) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $Utf8NoBom.GetBytes($Text)
        $hash = $sha.ComputeHash($bytes)
        return ([BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Ensure-Property($Object, [string]$Name, $Value) {
    if ($Object.PSObject.Properties.Name -contains $Name) {
        $Object.$Name = $Value
    }
    else {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

function Remove-PathFailClosed([string]$Path, [int]$MaxAttempts = 4) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return }
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        }
        catch {
            if ($attempt -ge $MaxAttempts) { throw "failed to remove stale verifier path after $MaxAttempts attempts: $Path : $($_.Exception.Message)" }
        }
        if (-not (Test-Path -LiteralPath $Path)) { return }
        if ($attempt -lt $MaxAttempts) { Start-Sleep -Milliseconds 250 }
    }
    if (Test-Path -LiteralPath $Path) { throw "stale verifier path still exists after cleanup: $Path" }
}

function Save-State($State, [string]$Path) {
    $json = $State | ConvertTo-Json -Depth 50
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force $parent | Out-Null
    }
    $tempPath = Join-Path $parent ("verifier-progress.tmp.$PID.$([Guid]::NewGuid().ToString('N')).json")
    try {
        [IO.File]::WriteAllText($tempPath, $json + "`n", $Utf8NoBom)
        if (Test-Path $Path) {
            [IO.File]::Replace($tempPath, $Path, [NullString]::Value)
        }
        else {
            [IO.File]::Move($tempPath, $Path)
        }
    }
    finally {
        if (Test-Path $tempPath) { Remove-Item -Force -ErrorAction SilentlyContinue $tempPath }
    }
}

if ($env:VERIFIER_STAGE -notin @("OPUS", "FABLE")) { throw "VERIFIER_STAGE must be OPUS or FABLE" }
if (-not $env:VERIFIER_RESULT_FILE) { throw "VERIFIER_RESULT_FILE is required" }
if (-not $env:CLAUDE_MODEL) { throw "CLAUDE_MODEL is required" }
if (-not $env:CLAUDE_EFFORT) { throw "CLAUDE_EFFORT is required" }

# v6/v7 stored one verifier checkpoint directly under verifier-state. v8 has
# stage-specific subdirectories. Archive the old checkpoint before starting
# v8 Opus so a half-finished Fable session cannot be mistaken for Opus state.
if ($env:VERIFIER_STAGE -eq "OPUS") {
    $legacyStateRoot = Join-Path $env:OUTDIR "verifier-state"
    $legacyProgress = Join-Path $legacyStateRoot "verifier-progress.json"
    if ((Test-Path $legacyProgress) -and $env:VERIFIER_PROGRESS -ne $legacyProgress) {
        $legacyHistoryRoot = Join-Path $env:OUTDIR "verifier-history\legacy-pre-v8"
        New-Item -ItemType Directory -Force $legacyHistoryRoot | Out-Null
        $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
        $archive = Join-Path $legacyHistoryRoot "$stamp-run-$env:GITHUB_RUN_ID-attempt-$env:GITHUB_RUN_ATTEMPT"
        Move-Item -Force $legacyStateRoot $archive
        foreach ($name in @("UAT_REPORT.md", "uat-result.txt")) {
            $src = Join-Path $env:OUTDIR $name
            if (Test-Path $src) { Copy-Item -Force $src (Join-Path $archive $name) }
        }
        Write-Host "[V8-MIGRATION] archived legacy verifier-progress.json to $archive; starting v8 Opus under the new staged verifier contract"
    }
}

New-Item -ItemType Directory -Force $env:OUTDIR | Out-Null
New-Item -ItemType Directory -Force $env:VERIFIER_RUNTIME_DIR | Out-Null
New-Item -ItemType Directory -Force $env:VERIFIER_HISTORY_DIR | Out-Null

$required = @(
    $env:VERIFIER_PROMPT,
    $env:VERIFIER_OVERRIDE,
    $env:VERIFIER_PROTOCOL,
    $env:VERIFIER_SETTINGS,
    "$env:OUTDIR\pushed-sha.txt"
)
foreach ($path in $required) {
    if (-not (Test-Path $path)) { throw "required verifier input missing: $path" }
}

$candidate = ([IO.File]::ReadAllText("$env:OUTDIR\pushed-sha.txt", [System.Text.Encoding]::UTF8)).Trim()
if ($candidate -notmatch '^[0-9a-fA-F]{40}$') { throw "invalid candidate SHA in pushed-sha.txt: '$candidate'" }
$candidate = $candidate.ToLowerInvariant()

$local = (git -C $env:WORKTREE rev-parse HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0) { throw "git rev-parse failed" }
if ($local -ne $candidate) { throw "local worktree HEAD $local does not equal candidate $candidate" }

$remoteLine = git -C $env:WORKTREE ls-remote $env:SSH_URL "refs/heads/$env:BRANCH"
if ($LASTEXITCODE -ne 0) { throw "git ls-remote failed" }
$remoteParts = @($remoteLine -split '\s+' | Where-Object { $_ })
if ($remoteParts.Count -lt 1) { throw "candidate branch not found on remote: $env:BRANCH" }
$remote = $remoteParts[0].Trim().ToLowerInvariant()
if ($remote -ne $candidate) { throw "remote branch SHA $remote does not equal candidate $candidate" }

if ($env:VERIFIER_STAGE -eq "FABLE") {
    $periodEnvNames = @(
        "LOOP_FINAL_UAT_PERIOD_SLOT",
        "LOOP_FINAL_UAT_PERIOD_PRIMARY",
        "LOOP_FINAL_UAT_PERIOD_SECONDARY",
        "LOOP_FINAL_UAT_PERIOD_POOL_SHA256"
    )
    foreach ($name in $periodEnvNames) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not $value) { throw "required durable Fable final-audit UAT period environment missing: $name" }
    }
    $uatPeriodSlot = [int]$env:LOOP_FINAL_UAT_PERIOD_SLOT
    $uatPeriodPrimary = [int]$env:LOOP_FINAL_UAT_PERIOD_PRIMARY
    $uatPeriodSecondary = [int]$env:LOOP_FINAL_UAT_PERIOD_SECONDARY
    $uatPeriodPoolSha256 = ([string]$env:LOOP_FINAL_UAT_PERIOD_POOL_SHA256).ToLowerInvariant()
}
else {
    $periodEnvNames = @(
        "LOOP_UAT_PERIOD_SLOT",
        "LOOP_UAT_PERIOD_PRIMARY",
        "LOOP_UAT_PERIOD_SECONDARY",
        "LOOP_UAT_PERIOD_POOL_SHA256"
    )
    foreach ($name in $periodEnvNames) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not $value) { throw "required durable Opus UAT period environment missing: $name" }
    }
    $uatPeriodSlot = [int]$env:LOOP_UAT_PERIOD_SLOT
    $uatPeriodPrimary = [int]$env:LOOP_UAT_PERIOD_PRIMARY
    $uatPeriodSecondary = [int]$env:LOOP_UAT_PERIOD_SECONDARY
    $uatPeriodPoolSha256 = ([string]$env:LOOP_UAT_PERIOD_POOL_SHA256).ToLowerInvariant()
}
if ($uatPeriodSlot -lt 1 -or $uatPeriodPrimary -lt 1 -or $uatPeriodSecondary -lt 1) { throw "invalid durable UAT period allocation" }
if ($uatPeriodPrimary -eq $uatPeriodSecondary) { throw "primary and secondary UAT periods must differ" }
if ($uatPeriodPoolSha256 -notmatch '^[0-9a-f]{64}$') { throw "invalid UAT period pool SHA-256" }

foreach ($name in @(
    "LOOP_UAT_AUTHORIZATION_ID",
    "LOOP_UAT_AUTHORIZED_ACTIONS",
    "LOOP_UAT_AUTHORIZATION_SCOPE_SHA256",
    "LOOP_UAT_AUTHORIZATION_ACTOR",
    "LOOP_UAT_AUTHORIZATION_STAGE",
    "LOOP_UAT_EXECUTION_ID",
    "LOOP_UAT_CYCLE_SCOPE_SHA256",
    "LOOP_UAT_TARGET_NAMESPACE",
    "LOOP_UAT_RESOURCE_SCOPE",
    "LOOP_UAT_TARGET_BRANCH",
    "LOOP_UAT_IMPACT_SCOPE"
)) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if (-not $value) { throw "required durable UAT write authorization environment missing: $name" }
}
$uatAuthorizationId = ([string]$env:LOOP_UAT_AUTHORIZATION_ID).Trim()
$uatAuthorizedActions = ([string]$env:LOOP_UAT_AUTHORIZED_ACTIONS).Trim().ToLowerInvariant()
$uatAuthorizationScopeSha256 = ([string]$env:LOOP_UAT_AUTHORIZATION_SCOPE_SHA256).Trim().ToLowerInvariant()
$uatAuthorizationActor = ([string]$env:LOOP_UAT_AUTHORIZATION_ACTOR).Trim()
$uatAuthorizationStage = ([string]$env:LOOP_UAT_AUTHORIZATION_STAGE).Trim().ToUpperInvariant()
$uatExecutionId = ([string]$env:LOOP_UAT_EXECUTION_ID).Trim().ToLowerInvariant()
$uatCycleScopeSha256 = ([string]$env:LOOP_UAT_CYCLE_SCOPE_SHA256).Trim().ToLowerInvariant()
$uatTargetNamespace = ([string]$env:LOOP_UAT_TARGET_NAMESPACE).Trim().ToLowerInvariant()
$uatResourceScope = ([string]$env:LOOP_UAT_RESOURCE_SCOPE).Trim().ToLowerInvariant()
$uatTargetBranch = ([string]$env:LOOP_UAT_TARGET_BRANCH).Trim()
$uatImpactScope = ([string]$env:LOOP_UAT_IMPACT_SCOPE).Trim().ToLowerInvariant()
if ($uatAuthorizationScopeSha256 -notmatch '^[0-9a-f]{64}$') { throw "invalid UAT write authorization scope SHA-256" }
if ($uatCycleScopeSha256 -notmatch '^[0-9a-f]{64}$') { throw "invalid Cycle UAT authorization scope SHA-256" }
if ($uatAuthorizationStage -ne ([string]$env:VERIFIER_STAGE).Trim().ToUpperInvariant()) { throw "UAT write authorization stage does not match active verifier stage" }
if ($uatExecutionId -notmatch '^c[0-9]+-r[0-9]+-(opus|fable)-s[0-9]+-[0-9a-f]{12}$') { throw "invalid durable UAT execution ID" }
if (-not $uatAuthorizedActions -or $uatAuthorizedActions -eq "none") { throw "UAT_WRITE_AUTHORIZATION_REQUIRED: active verifier stage has no authorized mutable action scope" }
if (-not $uatTargetNamespace -or $uatTargetNamespace -notmatch '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$') { throw "invalid durable UAT target namespace" }
if (-not $uatResourceScope) { throw "durable UAT resource scope is empty" }
if (-not $uatTargetBranch -or $uatTargetBranch -match '[\x00\r\n ]') { throw "invalid durable UAT target branch" }
if ($uatImpactScope -ne 'isolated-uat-only') { throw "durable UAT impact scope must be isolated-uat-only" }

if (-not $env:LOOP_MASTER_AGENTS_SNAPSHOT) { throw "LOOP_MASTER_AGENTS_SNAPSHOT is required" }
if (-not $env:LOOP_MASTER_AGENTS_SHA256) { throw "LOOP_MASTER_AGENTS_SHA256 is required" }
if (-not (Test-Path $env:LOOP_MASTER_AGENTS_SNAPSHOT)) { throw "pinned master AGENTS snapshot missing: $env:LOOP_MASTER_AGENTS_SNAPSHOT" }
$masterAgentsSha256 = (Get-FileSha256 $env:LOOP_MASTER_AGENTS_SNAPSHOT).ToLowerInvariant()
$expectedMasterAgentsSha256 = ([string]$env:LOOP_MASTER_AGENTS_SHA256).ToLowerInvariant()
if ($expectedMasterAgentsSha256 -notmatch '^[0-9a-f]{64}$') { throw "invalid LOOP_MASTER_AGENTS_SHA256" }
if ($masterAgentsSha256 -ne $expectedMasterAgentsSha256) { throw "pinned master AGENTS snapshot hash mismatch before verifier checkpoint preparation" }

# Build a stage-scoped effective settings file. In v13 both OPUS and FABLE start from a fresh permission object.
# Neither stage inherits local Bash/PowerShell/kubectl allow rules. Mutable and Kubernetes actions are reachable
# only through the fixed structured UAT action proxy.
$baseSettings = [IO.File]::ReadAllText($env:VERIFIER_SETTINGS, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$settings = [pscustomobject]@{
    permissions = [pscustomobject]@{
        allow = @()
        deny = @()
    }
}
$proxyAllow = ([string]$env:UAT_ACTION_PROXY_ALLOW).Trim()
if (-not $proxyAllow) { throw "UAT_ACTION_PROXY_ALLOW is required" }
$allow = @(
    "Edit(.loop-output/UAT_REPORT.md)",
    $proxyAllow
)
if ($env:VERIFIER_STAGE -eq "OPUS") {
    $allow += "Edit(.loop-output/opus-result.txt)"
    $allow += "Edit(.loop-output/verifier-state/opus/**)"
    $deny = @(
        "Edit(.loop-output/loop-state.json)",
        "Edit(.loop-output/cycles/**)",
        "Edit(.loop-output/controller-evidence/**)",
        "Edit(.loop-output/verifier-state/fable/**)",
        "Edit(.loop-output/uat-result.txt)",
        "Agent"
    )
}
else {
    $allow += "Edit(.loop-output/uat-result.txt)"
    $allow += "Edit(.loop-output/verifier-state/fable/**)"
    $deny = @(
        "Edit(.loop-output/loop-state.json)",
        "Edit(.loop-output/cycles/**)",
        "Edit(.loop-output/controller-evidence/**)",
        "Edit(.loop-output/verifier-state/opus/**)",
        "Edit(.loop-output/opus-result.txt)",
        "Edit(.loop-output/pushed-sha.txt)",
        "Edit(.loop-output/codex-final.txt)",
        "Edit(.loop-output/IMPLEMENTATION_HANDOFF.md)",
        "Agent"
    )
}
$settings.permissions.allow = @($allow | Select-Object -Unique)
$settings.permissions.deny = @($deny | Select-Object -Unique)

$effectiveSettings = Join-Path $env:VERIFIER_RUNTIME_DIR "verifier-settings.effective.json"
Write-Utf8NoBom $effectiveSettings (($settings | ConvertTo-Json -Depth 50) + "`n")

# Defense-in-depth smoke check before any long Claude/UAT execution.
$effectiveCheck = [IO.File]::ReadAllText($effectiveSettings, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$effectiveAllow = @($effectiveCheck.permissions.allow)
$effectiveDeny = @($effectiveCheck.permissions.deny)
foreach ($requiredRule in @("Edit(.loop-output/UAT_REPORT.md)", $proxyAllow)) {
    if ($effectiveAllow -notcontains $requiredRule) { throw "effective settings missing required allow: $requiredRule" }
}
if ($env:VERIFIER_STAGE -eq "OPUS") {
    foreach ($requiredRule in @("Edit(.loop-output/opus-result.txt)", "Edit(.loop-output/verifier-state/opus/**)")) {
        if ($effectiveAllow -notcontains $requiredRule) { throw "effective Opus settings missing required allow: $requiredRule" }
    }
}
else {
    foreach ($requiredRule in @("Edit(.loop-output/uat-result.txt)", "Edit(.loop-output/verifier-state/fable/**)")) {
        if ($effectiveAllow -notcontains $requiredRule) { throw "effective Fable settings missing required allow: $requiredRule" }
    }
}
foreach ($rule in $effectiveAllow) {
    $text = [string]$rule
    if (($text -match '^(Bash|PowerShell)') -and $text -ne $proxyAllow) {
        throw "effective verifier settings contain unauthorized shell allow: $text"
    }
    if ($text -match '(?i)\b(kubectl|git\s+bundle|sh\s+-c|bash\s+-c)\b') {
        throw "effective verifier settings contain unauthorized shell/orchestrator allow: $text"
    }
}
$conflictingDeny = @($effectiveDeny | Where-Object { $_ -eq "Edit" -or $_ -eq "Write" })
if ($conflictingDeny.Count -gt 0) { throw "effective settings still contain a bare Edit/Write deny: $($conflictingDeny -join ', ')" }
Write-Host "[PERMISSION-SMOKE] PASS: both verifier stages use the unified structured UAT proxy as the only shell mutation surface"

$promptHash = Get-FileSha256 $env:VERIFIER_PROMPT
$overrideHash = Get-FileSha256 $env:VERIFIER_OVERRIDE
$protocolHash = Get-FileSha256 $env:VERIFIER_PROTOCOL
$settingsHash = Get-FileSha256 $effectiveSettings
$fingerprintMaterial = @(
    "schema=8",
    "verifier_stage=$env:VERIFIER_STAGE",
    "candidate=$candidate",
    "uat_period_slot=$uatPeriodSlot",
    "uat_period_primary=$uatPeriodPrimary",
    "uat_period_secondary=$uatPeriodSecondary",
    "uat_period_pool_sha256=$uatPeriodPoolSha256",
    "uat_authorization_id=$uatAuthorizationId",
    "uat_authorized_actions=$uatAuthorizedActions",
    "uat_authorization_scope_sha256=$uatAuthorizationScopeSha256",
    "uat_execution_id=$uatExecutionId",
    "uat_authorization_actor=$uatAuthorizationActor",
    "uat_cycle_scope_sha256=$uatCycleScopeSha256",
    "uat_target_namespace=$uatTargetNamespace",
    "uat_resource_scope=$uatResourceScope",
    "uat_target_branch=$uatTargetBranch",
    "uat_impact_scope=$uatImpactScope",
    "master_agents_sha256=$masterAgentsSha256",
    "prompt=$promptHash",
    "override=$overrideHash",
    "protocol=$protocolHash",
    "settings=$settingsHash",
    "model=$env:CLAUDE_MODEL",
    "effort=$env:CLAUDE_EFFORT"
) -join "`n"
$fingerprint = Get-TextSha256 $fingerprintMaterial

$resumeMode = "NEW"
$alreadyComplete = $false
$state = $null

if (Test-Path $env:VERIFIER_PROGRESS) {
    try {
        $state = [IO.File]::ReadAllText($env:VERIFIER_PROGRESS, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    }
    catch {
        throw "existing verifier-progress.json is invalid JSON; refusing to guess recovery state: $($_.Exception.Message)"
    }

    # Controller evidence schema 10 is stored in a versioned controller-owned path.
    # Fingerprint upgrades archive verifier state while legacy unversioned/v17/schema-8 controller evidence remains outside the active v19 evidence directory.
    if ($state.input_fingerprint -ne $fingerprint -or $state.candidate_sha -ne $candidate) {
        $oldFp = [string]$state.input_fingerprint
        if (-not $oldFp) { $oldFp = "unknown" }
        $prefix = $oldFp.Substring(0, [Math]::Min(12, $oldFp.Length))
        $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
        $archive = Join-Path $env:VERIFIER_HISTORY_DIR "$stamp-$prefix"
        if (Test-Path $archive) { $archive = "$archive-$env:GITHUB_RUN_ATTEMPT" }
        Move-Item -Force $env:VERIFIER_STATE_DIR $archive
        foreach ($finalFile in @([IO.Path]::GetFileName($env:VERIFIER_RESULT_FILE), "UAT_REPORT.md")) {
            $src = Join-Path $env:OUTDIR $finalFile
            if (Test-Path $src) { Copy-Item -Force $src (Join-Path $archive $finalFile) }
        }
        Write-Host "[CHECKPOINT] fingerprint changed; archived old state to $archive"
        $state = $null
        $resumeMode = "NEW"
    }
    else {
        $resumeMode = "RESUME"
        if (-not ($state.PSObject.Properties.Name -contains "tasks")) {
            $state | Add-Member -NotePropertyName tasks -NotePropertyValue @()
        }

        if ([int]$state.uat_period_slot -ne $uatPeriodSlot -or
            [int]$state.uat_period_primary -ne $uatPeriodPrimary -or
            [int]$state.uat_period_secondary -ne $uatPeriodSecondary -or
            [string]$state.uat_period_pool_sha256 -ne $uatPeriodPoolSha256) {
            throw "[FINAL-CONSISTENCY] verifier-progress.json UAT period allocation disagrees with the durable loop round; refusing to resume or skip. Dispatch loop-engine.yml with run_mode=auto after restoring the authoritative ledger."
        }
        if ([string]$state.master_agents_sha256 -ne $masterAgentsSha256) {
            throw "[FINAL-CONSISTENCY] verifier-progress.json master_agents_sha256 disagrees with the pinned Round snapshot; refusing to resume or skip under mixed project instructions."
        }
        if ([string]$state.verifier_stage -ne $env:VERIFIER_STAGE) {
            throw "[FINAL-CONSISTENCY] verifier-progress.json verifier_stage disagrees with requested stage $env:VERIFIER_STAGE"
        }
        if ([string]$state.uat_cycle_scope_sha256 -ne $uatCycleScopeSha256 -or
            [string]$state.uat_target_namespace -ne $uatTargetNamespace -or
            [string]$state.uat_resource_scope -ne $uatResourceScope -or
            [string]$state.uat_target_branch -ne $uatTargetBranch -or
            [string]$state.uat_impact_scope -ne $uatImpactScope) {
            throw "[FINAL-CONSISTENCY] verifier-progress.json Cycle authorization boundary disagrees with the durable stage grant; refusing mixed authorization scope"
        }

        $finalVerdict = [string]$state.final_verdict
        $finalResultPath = $env:VERIFIER_RESULT_FILE
        $finalReportPath = "$env:OUTDIR\UAT_REPORT.md"
        $hasFinalResult = (Test-Path $finalResultPath)
        $allowedCompleteVerdicts = @("PASS", "REJECTED")
        $allowedAllVerdicts = @("PASS", "REJECTED", "BLOCKED")
        if ($env:VERIFIER_STAGE -eq "OPUS") {
            $allowedCompleteVerdicts = @("PRECHECK_PASS", "REJECTED")
            $allowedAllVerdicts = @("PRECHECK_PASS", "REJECTED", "BLOCKED")
        }
        $hasFinalReport = (Test-Path $finalReportPath)
        if ($state.status -eq "COMPLETE" -and $allowedCompleteVerdicts -contains $finalVerdict -and $hasFinalResult -and $hasFinalReport) {
            $actualFinalResult = ([IO.File]::ReadAllText($finalResultPath, [System.Text.Encoding]::UTF8)).Trim()
            if ($allowedAllVerdicts -notcontains $actualFinalResult) {
                throw "[FINAL-CONSISTENCY] $([IO.Path]::GetFileName($finalResultPath)) contains invalid verdict '$actualFinalResult'; refusing to mark verifier already complete"
            }
            if ($actualFinalResult -ne $finalVerdict) {
                throw "[FINAL-CONSISTENCY] $([IO.Path]::GetFileName($finalResultPath)) disagrees with verifier-progress.json final_verdict: file=$actualFinalResult ledger=$finalVerdict; refusing to mark verifier already complete."
            }
            Write-Host "[FINAL-CONSISTENCY] PASS: final files agree with verifier ledger verdict $finalVerdict"
            $alreadyComplete = $true
            $resumeMode = "COMPLETE"
            Ensure-Property $state "last_run_id" $env:GITHUB_RUN_ID
            Ensure-Property $state "last_run_attempt" ([int]$env:GITHUB_RUN_ATTEMPT)
            Ensure-Property $state "updated_at" ((Get-Date).ToUniversalTime().ToString("o"))
            Save-State $state $env:VERIFIER_PROGRESS
        }
        else {
            foreach ($task in @($state.tasks)) {
                if ($task.status -eq "RUNNING" -or $task.status -eq "BLOCKED" -or $task.status -eq "FAILED") {
                    $oldStatus = [string]$task.status
                    Ensure-Property $task "status" "RETRY_REQUIRED"
                    Ensure-Property $task "summary" "Previous verifier task state was $oldStatus; verify durable evidence and observable target state before repeating side effects."
                }
            }

            # If a previous COMPLETE ledger lost its final files, rerun only finalization.
            if ($state.status -eq "COMPLETE" -and (-not $hasFinalResult -or -not $hasFinalReport)) {
                foreach ($task in @($state.tasks)) {
                    if ($task.kind -eq "FINAL" -and $task.status -eq "DONE") {
                        Ensure-Property $task "status" "RETRY_REQUIRED"
                        Ensure-Property $task "summary" "Final output files are missing; rebuild finalization from durable evidence without rerunning completed review/UAT tasks."
                    }
                }
            }

            $resumeCount = 0
            if ($state.PSObject.Properties.Name -contains "resume_count") { $resumeCount = [int]$state.resume_count }
            Ensure-Property $state "resume_count" ($resumeCount + 1)
            Ensure-Property $state "status" "RESUMING"
            Ensure-Property $state "current_task_id" $null
            Ensure-Property $state "final_verdict" $null
            Ensure-Property $state "last_run_id" $env:GITHUB_RUN_ID
            Ensure-Property $state "last_run_attempt" ([int]$env:GITHUB_RUN_ATTEMPT)
            Ensure-Property $state "updated_at" ((Get-Date).ToUniversalTime().ToString("o"))
            Save-State $state $env:VERIFIER_PROGRESS
        }
    }
}

if (-not (Test-Path $env:VERIFIER_PROGRESS)) {
    New-Item -ItemType Directory -Force $env:VERIFIER_STATE_DIR | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $env:VERIFIER_STATE_DIR "evidence") | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $env:VERIFIER_STATE_DIR "logs") | Out-Null
    $now = (Get-Date).ToUniversalTime().ToString("o")
    $state = [ordered]@{
        schema_version = 8
        verifier_stage = $env:VERIFIER_STAGE
        candidate_sha = $candidate
        input_fingerprint = $fingerprint
        uat_period_slot = $uatPeriodSlot
        uat_period_primary = $uatPeriodPrimary
        uat_period_secondary = $uatPeriodSecondary
        uat_period_pool_sha256 = $uatPeriodPoolSha256
        uat_authorization_id = $uatAuthorizationId
        uat_authorized_actions = $uatAuthorizedActions
        uat_authorization_scope_sha256 = $uatAuthorizationScopeSha256
        uat_execution_id = $uatExecutionId
        uat_authorization_actor = $uatAuthorizationActor
        uat_cycle_scope_sha256 = $uatCycleScopeSha256
        uat_target_namespace = $uatTargetNamespace
        uat_resource_scope = $uatResourceScope
        uat_target_branch = $uatTargetBranch
        uat_impact_scope = $uatImpactScope
        master_agents_sha256 = $masterAgentsSha256
        prompt_sha256 = $promptHash
        override_sha256 = $overrideHash
        protocol_sha256 = $protocolHash
        settings_sha256 = $settingsHash
        claude_model = $env:CLAUDE_MODEL
        claude_effort = $env:CLAUDE_EFFORT
        status = "NEW"
        current_task_id = $null
        final_verdict = $null
        resume_count = 0
        created_at = $now
        updated_at = $now
        last_run_id = $env:GITHUB_RUN_ID
        last_run_attempt = [int]$env:GITHUB_RUN_ATTEMPT
        tasks = @()
    }
    Save-State $state $env:VERIFIER_PROGRESS
}

if (-not $alreadyComplete) {
    Remove-PathFailClosed $env:VERIFIER_RESULT_FILE
    if ($env:VERIFIER_STAGE -eq "OPUS") {
        Remove-PathFailClosed "$env:OUTDIR\uat-result.txt"
        if ($resumeMode -eq "NEW") {
            Remove-PathFailClosed "$env:OUTDIR\UAT_REPORT.md"
        }
    }
    # FABLE intentionally preserves the Opus report. If the Fable fingerprint
    # changed, restore the pinned Opus prefix before starting a fresh final audit
    # so a stale prior Fable section cannot become part of the new audit input.
    if ($env:VERIFIER_STAGE -eq "FABLE" -and $resumeMode -eq "NEW") {
        $opusPin = Join-Path $env:OUTDIR "verifier-state\opus\UAT_REPORT.pre-fable.md"
        if (-not (Test-Path $opusPin)) { throw "pinned Opus UAT report is required before a new Fable final audit" }
        $opusText = [IO.File]::ReadAllText($opusPin, [System.Text.Encoding]::UTF8)
        Write-Utf8NoBom "$env:OUTDIR\UAT_REPORT.md" $opusText
    }
}

$state = [IO.File]::ReadAllText($env:VERIFIER_PROGRESS, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# Verifier Resume Context")
$lines.Add("")
$lines.Add("Verifier stage: $env:VERIFIER_STAGE")
$lines.Add("Candidate SHA: $candidate")
$lines.Add("Input fingerprint: $fingerprint")
$lines.Add("UAT period slot: $uatPeriodSlot")
$lines.Add("UAT primary PVAM_BOUND_PERIOD: $uatPeriodPrimary")
$lines.Add("UAT secondary PVAM_BOUND_PERIOD: $uatPeriodSecondary")
$lines.Add("UAT period pool SHA-256: $uatPeriodPoolSha256")
$lines.Add("Cycle authorization scope SHA-256: $uatCycleScopeSha256")
$lines.Add("Durable UAT execution ID: $uatExecutionId")
$lines.Add("Authorized namespace: $uatTargetNamespace")
$lines.Add("Authorized resource scope: $uatResourceScope")
$lines.Add("Authorized target branch: $uatTargetBranch")
$lines.Add("Authorized impact scope: $uatImpactScope")
$lines.Add("Pinned local master AGENTS.md SHA-256: $masterAgentsSha256")
$lines.Add("Mode: $resumeMode")
$lines.Add("GitHub run: $env:GITHUB_RUN_ID attempt $env:GITHUB_RUN_ATTEMPT")
$lines.Add("")
$lines.Add("## Durable task state")
if (@($state.tasks).Count -eq 0) {
    $lines.Add("- No task plan exists yet. Build and persist the stable plan before executing review/UAT work.")
}
else {
    foreach ($task in @($state.tasks)) {
        $lines.Add("- [$($task.status)] $($task.id) | $($task.title) | $($task.summary)")
    }
}
$lines.Add("")
$lines.Add("## Resume rule")
$lines.Add("Skip DONE tasks. For RETRY_REQUIRED tasks, verify durable evidence and observable target state before repeating side effects.")
$lines.Add("The progress ledger is authoritative. Update it immediately before and after every atomic task according to the checkpoint protocol.")
Write-Utf8NoBom $env:VERIFIER_RESUME_CONTEXT (($lines -join "`n") + "`n")

Append-GitHubEnv "VERIFIER_EFFECTIVE_SETTINGS" $effectiveSettings
Append-GitHubEnv "VERIFIER_FINGERPRINT" $fingerprint
Append-GitHubEnv "VERIFIER_RESUME_MODE" $resumeMode
Append-GitHubEnv "VERIFIER_CANDIDATE_SHA" $candidate
Append-GitHubEnv "VERIFIER_ALREADY_COMPLETE" ($alreadyComplete.ToString().ToLowerInvariant())

Write-Host "=== VERIFIER CHECKPOINT ==="
Write-Host "verifier_stage=$env:VERIFIER_STAGE"
Write-Host "candidate=$candidate"
Write-Host "fingerprint=$fingerprint"
Write-Host "uat_period_slot=$uatPeriodSlot"
Write-Host "uat_periods=$uatPeriodPrimary/$uatPeriodSecondary"
Write-Host "uat_period_pool_sha256=$uatPeriodPoolSha256"
Write-Host "uat_authorization_id=$uatAuthorizationId"
Write-Host "uat_authorized_actions=$uatAuthorizedActions"
Write-Host "uat_authorization_scope_sha256=$uatAuthorizationScopeSha256"
Write-Host "uat_execution_id=$uatExecutionId"
Write-Host "master_agents_sha256=$masterAgentsSha256"
Write-Host "mode=$resumeMode"
Write-Host "already_complete=$alreadyComplete"
Write-Host "progress=$env:VERIFIER_PROGRESS"
Write-Host "effective_settings=$effectiveSettings"
if (@($state.tasks).Count -gt 0) {
    foreach ($task in @($state.tasks)) {
        Write-Host ("[{0}] {1} | {2}" -f $task.status, $task.id, $task.title)
    }
}
