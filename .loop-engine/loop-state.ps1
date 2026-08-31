param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Prepare", "BeginRound", "SetCandidate", "RotateLegacyVerifierPeriod", "AllocateFinalAuditPeriod", "BindCycleUatAuthorization", "BindUatWriteAuthorization", "BindOpusReportBaseline", "BindProtectedEvidenceBaseline", "MarkFinalAuditEvidenceVerified", "CompleteRound", "ReopenInvalidVerifierResult", "Summarize")]
    [string]$Operation,

    [ValidateSet("auto", "next-cycle", "new-cycle")]
    [string]$RunMode = "auto",

    [int]$Cycle = 0,
    [int]$Round = 0,

    [ValidateSet("construct", "rework", "resume-verifier")]
    [string]$RoundAction = "construct",

    [string]$PreviousReport = "",
    [string]$CandidateSha = "",

    [string]$Verdict = "",
    [string]$OpusResult = "",
    [string]$FableResult = "",

    [string]$OpusReportSha256 = "",
    [long]$OpusReportLength = 0,

    [string]$ProtectedEvidenceSha256 = "",

    [ValidateSet("CLAUDE_ARGUMENTS_DROPPED")]
    [string]$InvalidationReason = "",

    [ValidateSet("OPUS", "FABLE")]
    [string]$VerifierStage = "OPUS",
    [string]$AuthorizationConfirmed = "false",
    [string]$AuthorizationId = "",
    [string]$AuthorizedActions = "none",
    [string]$AuthorizationActor = "",
    [string]$AuthorizationRunId = "",
    [string]$AuthorizationRunAttempt = "",
    [string]$TargetNamespace = "",
    [string]$ResourceScope = "",
    [string]$TargetBranch = "",
    [string]$ImpactScope = ""
)

$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$MaxRoundsPerCycle = 3

if (-not $env:OUTDIR) { throw "OUTDIR is required" }
if (-not $env:WORKTREE) { throw "WORKTREE is required" }
if (-not $env:SSH_URL) { throw "SSH_URL is required" }
if (-not $env:BRANCH) { throw "BRANCH is required" }
if (-not $env:UAT_PERIOD_POOL_FILE) { throw "UAT_PERIOD_POOL_FILE is required" }

$StateFile = $env:LOOP_STATE_FILE
if (-not $StateFile) { $StateFile = Join-Path $env:OUTDIR "loop-state.json" }
$CyclesDir = $env:LOOP_CYCLES_DIR
if (-not $CyclesDir) { $CyclesDir = Join-Path $env:OUTDIR "cycles" }

function Utc-Now() {
    return (Get-Date).ToUniversalTime().ToString("o")
}

function Get-TextSha256([string]$Text) {
    $bytes = $Utf8NoBom.GetBytes($Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Get-ProtectedRoundContractSha256($CycleObject, $RoundObject) {
    $retired = New-Object System.Collections.Generic.List[object]
    foreach ($item in @($RoundObject.retired_uat_period_allocations | Sort-Object slot)) {
        if ($null -eq $item) { continue }
        $retired.Add([ordered]@{
            slot = [string]$item.slot
            primary = [string]$item.primary
            secondary = [string]$item.secondary
            pool_sha256 = [string]$item.pool_sha256
            reason = [string]$item.reason
            retired_at = [string]$item.retired_at
        })
    }
    $contract = [ordered]@{
        schema = "v12-protected-round-contract-2"
        cycle = [string]$CycleObject.cycle
        round = [string]$RoundObject.round
        action = [string]$RoundObject.action
        phase = [string]$RoundObject.phase
        candidate_sha = [string]$RoundObject.candidate_sha
        master_agents_sha256 = [string]$RoundObject.master_agents_sha256
        uat_period_slot = [string]$RoundObject.uat_period_slot
        uat_period_primary = [string]$RoundObject.uat_period_primary
        uat_period_secondary = [string]$RoundObject.uat_period_secondary
        uat_period_pool_sha256 = [string]$RoundObject.uat_period_pool_sha256
        final_audit_uat_period_slot = [string]$RoundObject.final_audit_uat_period_slot
        final_audit_uat_period_primary = [string]$RoundObject.final_audit_uat_period_primary
        final_audit_uat_period_secondary = [string]$RoundObject.final_audit_uat_period_secondary
        final_audit_uat_period_pool_sha256 = [string]$RoundObject.final_audit_uat_period_pool_sha256
        opus_report_sha256 = [string]$RoundObject.opus_report_sha256
        opus_report_length = [string]$RoundObject.opus_report_length
        uat_cycle_authorization_sha256 = [string]$CycleObject.uat_cycle_authorization_sha256
        uat_write_authorization_opus_sha256 = [string]$RoundObject.uat_write_authorization_opus_sha256
        uat_write_authorization_fable_sha256 = [string]$RoundObject.uat_write_authorization_fable_sha256
        retired_uat_period_allocations = $retired.ToArray()
    }
    return Get-TextSha256 (($contract | ConvertTo-Json -Depth 30 -Compress) + "`n")
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force $parent | Out-Null
    }
    [IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Write-Utf8NoBomAtomic([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force $parent | Out-Null
    }
    $leaf = [IO.Path]::GetFileName($Path)
    $tempPath = Join-Path $parent ("$leaf.tmp.$PID.$([Guid]::NewGuid().ToString('N'))")
    try {
        [IO.File]::WriteAllText($tempPath, $Text, $Utf8NoBom)
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

function Remove-PathFailClosed([string]$Path, [int]$MaxAttempts = 4, [int]$DelayMilliseconds = 250) {
    if (-not $Path) { throw "cleanup path is empty" }
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        if (-not (Test-Path -LiteralPath $Path)) { return }
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        }
        catch {
            if ($attempt -ge $MaxAttempts) {
                throw "failed to remove stale Loop Engine path after $MaxAttempts attempts: $Path : $($_.Exception.Message)"
            }
        }
        if (-not (Test-Path -LiteralPath $Path)) { return }
        if ($attempt -lt $MaxAttempts) { Start-Sleep -Milliseconds $DelayMilliseconds }
    }
    if (Test-Path -LiteralPath $Path) {
        throw "stale Loop Engine path still exists after cleanup: $Path"
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

function Save-State($State) {
    Ensure-Property $State "updated_at" (Utc-Now)
    $json = $State | ConvertTo-Json -Depth 80
    $parent = Split-Path -Parent $StateFile
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force $parent | Out-Null
    }

    # Write in the same directory and atomically replace the durable ledger.
    # This avoids leaving a truncated loop-state.json if the runner dies during a write.
    $tempName = "loop-state.tmp.$PID.$([Guid]::NewGuid().ToString('N')).json"
    $tempPath = Join-Path $parent $tempName
    try {
        [IO.File]::WriteAllText($tempPath, $json + "`n", $Utf8NoBom)
        if (Test-Path $StateFile) {
            [IO.File]::Replace($tempPath, $StateFile, [NullString]::Value)
        }
        else {
            [IO.File]::Move($tempPath, $StateFile)
        }
    }
    finally {
        if (Test-Path $tempPath) { Remove-Item -Force -ErrorAction SilentlyContinue $tempPath }
    }
}

function Load-State() {
    if (-not (Test-Path $StateFile)) { return $null }
    try {
        return [IO.File]::ReadAllText($StateFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    }
    catch {
        throw "loop-state.json is invalid JSON: $($_.Exception.Message)"
    }
}

function Write-StepOutput([string]$Name, [string]$Value) {
    if (-not $env:GITHUB_OUTPUT) { return }
    [IO.File]::AppendAllText($env:GITHUB_OUTPUT, "$Name=$Value`n", $Utf8NoBom)
}

function Write-GitHubEnv([string]$Name, [string]$Value) {
    if (-not $env:GITHUB_ENV) { return }
    [IO.File]::AppendAllText($env:GITHUB_ENV, "$Name=$Value`n", $Utf8NoBom)
}

$AllowedUatWriteActions = @(
    "test-data-write",
    "exec",
    "debug",
    "git-update",
    "deploy",
    "restart",
    "scale",
    "delete"
)

function Normalize-UatAuthorizedActions([string]$RawActions) {
    $raw = ([string]$RawActions).Trim().ToLowerInvariant()
    if (-not $raw -or $raw -eq "none") { return @() }
    $items = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($part in @($raw -split ',')) {
        $item = ([string]$part).Trim().ToLowerInvariant()
        if (-not $item) { continue }
        if ($AllowedUatWriteActions -notcontains $item) {
            throw "invalid UAT authorized action '$item'. Allowed: $($AllowedUatWriteActions -join ',')"
        }
        if (-not $seen.ContainsKey($item)) {
            $seen[$item] = $true
            $items.Add($item)
        }
    }
    return @($items.ToArray() | Sort-Object)
}

function Normalize-UatResourceScope([string]$RawScope) {
    $raw = ([string]$RawScope).Trim().ToLowerInvariant()
    if (-not $raw) { throw "UAT_WRITE_AUTHORIZATION_REQUIRED: uat_resource_scope is required" }
    $items = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($part in @($raw -split '[,;]')) {
        $item = ([string]$part).Trim().ToLowerInvariant()
        if (-not $item) { continue }
        if ($item -notmatch '^[a-z0-9.-]+/[a-z0-9._-]+\*?$') {
            throw "invalid UAT resource scope entry '$item'; expected kind/name or kind/prefix*"
        }
        if ($item -eq '*/*' -or $item.EndsWith('/*')) {
            throw "wildcard-all UAT resource scope is forbidden: $item"
        }
        if (-not $seen.ContainsKey($item)) { $seen[$item] = $true; $items.Add($item) }
    }
    if ($items.Count -lt 1) { throw "UAT_WRITE_AUTHORIZATION_REQUIRED: uat_resource_scope contains no usable entries" }
    return @($items.ToArray() | Sort-Object)
}

function Get-CycleUatAuthorizationScopeSha256($Grant) {
    $scope = [ordered]@{
        schema = "v13-cycle-uat-authorization-1"
        authorization_id = [string]$Grant.authorization_id
        authorization_actor = [string]$Grant.authorization_actor
        cycle = [string]$Grant.cycle
        authorized_actions = @($Grant.authorized_actions)
        target_namespace = [string]$Grant.target_namespace
        resource_scope = @($Grant.resource_scope)
        target_branch = [string]$Grant.target_branch
        impact_scope = [string]$Grant.impact_scope
    }
    return Get-TextSha256 (($scope | ConvertTo-Json -Depth 20 -Compress) + "`n")
}

function Assert-CycleUatAuthorization($Grant, $CycleObject) {
    if (-not $Grant) { throw "UAT_WRITE_AUTHORIZATION_REQUIRED: durable Cycle authorization is missing" }
    if ([int]$Grant.cycle -ne [int]$CycleObject.cycle) { throw "durable Cycle authorization is bound to a different cycle" }
    $stored = ([string]$Grant.cycle_scope_sha256).Trim().ToLowerInvariant()
    $computed = Get-CycleUatAuthorizationScopeSha256 $Grant
    if ($stored -notmatch '^[0-9a-f]{64}$' -or $stored -ne $computed) {
        throw "durable Cycle authorization scope SHA-256 is invalid or changed: stored=$stored computed=$computed"
    }
    if (([string]$CycleObject.uat_cycle_authorization_sha256).Trim().ToLowerInvariant() -ne $stored) {
        throw "Cycle authorization pointer does not match the durable grant"
    }
}

function Export-CycleUatAuthorizationEnvironment($Grant) {
    Write-GitHubEnv "LOOP_UAT_AUTHORIZATION_ID" ([string]$Grant.authorization_id)
    Write-GitHubEnv "LOOP_UAT_AUTHORIZATION_ACTOR" ([string]$Grant.authorization_actor)
    Write-GitHubEnv "LOOP_UAT_AUTHORIZED_ACTIONS" ((@($Grant.authorized_actions) -join ','))
    Write-GitHubEnv "LOOP_UAT_TARGET_NAMESPACE" ([string]$Grant.target_namespace)
    Write-GitHubEnv "LOOP_UAT_RESOURCE_SCOPE" ((@($Grant.resource_scope) -join ','))
    Write-GitHubEnv "LOOP_UAT_TARGET_BRANCH" ([string]$Grant.target_branch)
    Write-GitHubEnv "LOOP_UAT_IMPACT_SCOPE" ([string]$Grant.impact_scope)
    Write-GitHubEnv "LOOP_UAT_CYCLE_SCOPE_SHA256" ([string]$Grant.cycle_scope_sha256)
}

function New-CycleUatAuthorizationGrant($CycleObject, [string]$AuthId, [string[]]$Actions, [string]$Actor, [string]$RunId, [string]$RunAttempt, [string]$Namespace, [string[]]$Resources, [string]$Branch, [string]$Impact) {
    $grant = [pscustomobject][ordered]@{
        schema_version = 1
        authorization_id = $AuthId
        authorization_actor = $Actor
        authorization_run_id = $RunId
        authorization_run_attempt = $RunAttempt
        authorized_at = Utc-Now
        cycle = [int]$CycleObject.cycle
        authorized_actions = @($Actions)
        target_namespace = $Namespace
        resource_scope = @($Resources)
        target_branch = $Branch
        impact_scope = $Impact
        cycle_scope_sha256 = $null
    }
    $grant.cycle_scope_sha256 = Get-CycleUatAuthorizationScopeSha256 $grant
    return $grant
}

function Bind-CycleUatAuthorization([int]$CycleNumber, [string]$Confirmed, [string]$AuthId, [string]$ActionsRaw, [string]$Actor, [string]$RunId, [string]$RunAttempt, [string]$Namespace, [string]$ResourcesRaw, [string]$Branch, [string]$Impact) {
    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $cycleObject = Get-Cycle $state $CycleNumber
    if (-not $cycleObject) { throw "cycle $CycleNumber is missing" }
    $existing = $null
    if ($cycleObject.PSObject.Properties.Name -contains 'uat_cycle_authorization') { $existing = $cycleObject.uat_cycle_authorization }
    if ($existing) { Assert-CycleUatAuthorization $existing $cycleObject }

    $isConfirmed = (([string]$Confirmed).Trim().ToLowerInvariant() -eq 'true')
    if (-not $isConfirmed) {
        if ($existing) {
            Export-CycleUatAuthorizationEnvironment $existing
            Write-Host "[UAT-CYCLE-AUTHORIZATION] reusing durable cycle=$CycleNumber id=$($existing.authorization_id) scope=$($existing.cycle_scope_sha256)"
            return
        }
        throw "UAT_WRITE_AUTHORIZATION_REQUIRED: this CLI Loop has no durable Cycle authorization. workflow_dispatch is the single non-interactive authorization point; set uat_write_authorization_confirmed=true with explicit scope inputs."
    }

    $id = ([string]$AuthId).Trim()
    $actorValue = ([string]$Actor).Trim()
    $namespaceValue = ([string]$Namespace).Trim().ToLowerInvariant()
    $branchValue = ([string]$Branch).Trim()
    $impactValue = ([string]$Impact).Trim().ToLowerInvariant()
    if (-not $id) { throw "UAT_WRITE_AUTHORIZATION_REQUIRED: uat_authorization_id is required" }
    if ($id -notmatch '^[A-Za-z0-9._:/-]{1,128}$') { throw "invalid uat_authorization_id format" }
    if (-not $actorValue) { throw "UAT_WRITE_AUTHORIZATION_REQUIRED: authorization actor is required" }
    if ($actorValue -notmatch '^[A-Za-z0-9_.-]{1,128}$') { throw "invalid authorization actor format" }
    if (([string]$RunId).Trim() -notmatch '^[0-9]{1,32}$') { throw "invalid authorization run id" }
    if (([string]$RunAttempt).Trim() -notmatch '^[0-9]{1,10}$') { throw "invalid authorization run attempt" }
    if (-not $namespaceValue -or $namespaceValue -notmatch '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$') { throw "invalid uat_target_namespace: $Namespace" }
    if (-not $branchValue -or $branchValue -match '[\x00\r\n ]') { throw "invalid uat_target_branch" }
    $controllerBranch = ([string]$env:BRANCH).Trim()
    if (-not $controllerBranch -or $branchValue -ne $controllerBranch) { throw "authorized target branch must match Loop Engine BRANCH: authorized=$branchValue controller=$controllerBranch" }
    if ($impactValue -ne 'isolated-uat-only') { throw "uat_impact_scope must be isolated-uat-only" }
    foreach ($value in @($id, $actorValue, $branchValue)) { if ($value -match '[\x00\r\n]') { throw "authorization input contains a forbidden control character" } }
    $actions = @(Normalize-UatAuthorizedActions $ActionsRaw)
    if ($actions.Count -lt 1) { throw "UAT_WRITE_AUTHORIZATION_REQUIRED: at least one explicit mutable action must be authorized" }
    $resources = @(Normalize-UatResourceScope $ResourcesRaw)
    $requested = New-CycleUatAuthorizationGrant $cycleObject $id $actions $actorValue $RunId $RunAttempt $namespaceValue $resources $branchValue $impactValue

    if ($existing) {
        if (([string]$existing.cycle_scope_sha256).ToLowerInvariant() -ne ([string]$requested.cycle_scope_sha256).ToLowerInvariant()) {
            throw "UAT_CYCLE_AUTHORIZATION_IMMUTABLE: a Cycle authorization is already bound. A later dispatch may resume/reuse it but cannot silently expand or change actions, namespace, resources, branch, or impact scope within the same Cycle."
        }
        Export-CycleUatAuthorizationEnvironment $existing
        Write-Host "[UAT-CYCLE-AUTHORIZATION] existing grant matches requested scope id=$($existing.authorization_id)"
        return
    }

    Ensure-Property $cycleObject 'uat_cycle_authorization' $requested
    Ensure-Property $cycleObject 'uat_cycle_authorization_sha256' ([string]$requested.cycle_scope_sha256)
    $cycleDir = Join-Path $CyclesDir ("cycle-{0}" -f $CycleNumber)
    New-Item -ItemType Directory -Force $cycleDir | Out-Null
    Write-Utf8NoBomAtomic (Join-Path $cycleDir 'cycle-uat-authorization.json') (($requested | ConvertTo-Json -Depth 20) + "`n")
    Save-State $state
    Export-CycleUatAuthorizationEnvironment $requested
    Write-Host "[UAT-CYCLE-AUTHORIZATION] bound one workflow dispatch as non-interactive Cycle preauthorization cycle=$CycleNumber id=$id actions=$($actions -join ',') namespace=$namespaceValue resources=$($resources -join ',') branch=$branchValue impact=$impactValue scope=$($requested.cycle_scope_sha256)"
}

function Get-UatWriteAuthorizationScopeSha256($Grant) {
    $scope = [ordered]@{
        schema = "v16-uat-write-authorization-3"
        authorization_id = [string]$Grant.authorization_id
        authorization_actor = [string]$Grant.authorization_actor
        cycle = [string]$Grant.cycle
        cycle_scope_sha256 = [string]$Grant.cycle_scope_sha256
        round = [string]$Grant.round
        candidate_sha = [string]$Grant.candidate_sha
        verifier_stage = [string]$Grant.verifier_stage
        period_slot = [string]$Grant.period_slot
        period_primary = [string]$Grant.period_primary
        period_secondary = [string]$Grant.period_secondary
        period_pool_sha256 = [string]$Grant.period_pool_sha256
        uat_execution_id = [string]$Grant.uat_execution_id
        authorized_actions = @($Grant.authorized_actions)
        target_namespace = [string]$Grant.target_namespace
        resource_scope = @($Grant.resource_scope)
        target_branch = [string]$Grant.target_branch
        impact_scope = [string]$Grant.impact_scope
    }
    return Get-TextSha256 (($scope | ConvertTo-Json -Depth 20 -Compress) + "`n")
}

function Assert-UatWriteAuthorizationGrantMatchesRound($Grant, $CycleObject, $RoundObject, [string]$Stage) {
    if (-not $Grant) { throw "UAT write authorization grant is missing" }
    Assert-CycleUatAuthorization $CycleObject.uat_cycle_authorization $CycleObject
    $stageUpper = ([string]$Stage).ToUpperInvariant()
    $slot = [string]$RoundObject.uat_period_slot
    $primary = [string]$RoundObject.uat_period_primary
    $secondary = [string]$RoundObject.uat_period_secondary
    $poolSha = [string]$RoundObject.uat_period_pool_sha256
    if ($stageUpper -eq 'FABLE') {
        $slot = [string]$RoundObject.final_audit_uat_period_slot
        $primary = [string]$RoundObject.final_audit_uat_period_primary
        $secondary = [string]$RoundObject.final_audit_uat_period_secondary
        $poolSha = [string]$RoundObject.final_audit_uat_period_pool_sha256
    }
    $cycleGrant = $CycleObject.uat_cycle_authorization
    $mismatches = New-Object System.Collections.Generic.List[string]
    if ([int]$Grant.cycle -ne [int]$CycleObject.cycle) { $mismatches.Add('cycle') }
    if (([string]$Grant.cycle_scope_sha256).ToLowerInvariant() -ne ([string]$cycleGrant.cycle_scope_sha256).ToLowerInvariant()) { $mismatches.Add('cycle_scope_sha256') }
    if ([int]$Grant.round -ne [int]$RoundObject.round) { $mismatches.Add('round') }
    if (([string]$Grant.candidate_sha).ToLowerInvariant() -ne ([string]$RoundObject.candidate_sha).ToLowerInvariant()) { $mismatches.Add('candidate_sha') }
    if (([string]$Grant.verifier_stage).ToUpperInvariant() -ne $stageUpper) { $mismatches.Add('verifier_stage') }
    if ([string]$Grant.period_slot -ne $slot) { $mismatches.Add('period_slot') }
    if ([string]$Grant.period_primary -ne $primary) { $mismatches.Add('period_primary') }
    if ([string]$Grant.period_secondary -ne $secondary) { $mismatches.Add('period_secondary') }
    if (([string]$Grant.period_pool_sha256).ToLowerInvariant() -ne ([string]$poolSha).ToLowerInvariant()) { $mismatches.Add('period_pool_sha256') }
    $candidateShort = ([string]$RoundObject.candidate_sha).ToLowerInvariant().Substring(0, 12)
    $expectedExecutionId = ("c{0}-r{1}-{2}-s{3}-{4}" -f [int]$CycleObject.cycle, [int]$RoundObject.round, $stageUpper.ToLowerInvariant(), [string]$slot, $candidateShort)
    if ([string]$Grant.uat_execution_id -ne $expectedExecutionId) { $mismatches.Add('uat_execution_id') }
    foreach ($field in @('target_namespace','target_branch','impact_scope')) { if ([string]$Grant.$field -ne [string]$cycleGrant.$field) { $mismatches.Add($field) } }
    if ((@($Grant.authorized_actions) -join ',') -ne (@($cycleGrant.authorized_actions) -join ',')) { $mismatches.Add('authorized_actions') }
    if ((@($Grant.resource_scope) -join ',') -ne (@($cycleGrant.resource_scope) -join ',')) { $mismatches.Add('resource_scope') }
    if ($mismatches.Count -gt 0) { throw "durable UAT write authorization grant does not match current Cycle/Round/Candidate/stage/period/Cycle-scope: $($mismatches.ToArray() -join ',')" }
    $computed = Get-UatWriteAuthorizationScopeSha256 $Grant
    $stored = ([string]$Grant.scope_sha256).Trim().ToLowerInvariant()
    if ($stored -notmatch '^[0-9a-f]{64}$' -or $stored -ne $computed) { throw "durable UAT write authorization scope SHA-256 is invalid or changed: stored=$stored computed=$computed" }
}

function Export-UatWriteAuthorizationEnvironment($Grant) {
    if (-not $Grant) { throw "UAT write authorization grant is missing" }
    Write-GitHubEnv "LOOP_UAT_AUTHORIZATION_ID" ([string]$Grant.authorization_id)
    Write-GitHubEnv "LOOP_UAT_AUTHORIZED_ACTIONS" ((@($Grant.authorized_actions) -join ','))
    Write-GitHubEnv "LOOP_UAT_AUTHORIZATION_SCOPE_SHA256" ([string]$Grant.scope_sha256)
    Write-GitHubEnv "LOOP_UAT_AUTHORIZATION_ACTOR" ([string]$Grant.authorization_actor)
    Write-GitHubEnv "LOOP_UAT_AUTHORIZATION_STAGE" ([string]$Grant.verifier_stage)
    Write-GitHubEnv "LOOP_UAT_CYCLE_SCOPE_SHA256" ([string]$Grant.cycle_scope_sha256)
    Write-GitHubEnv "LOOP_UAT_TARGET_NAMESPACE" ([string]$Grant.target_namespace)
    Write-GitHubEnv "LOOP_UAT_RESOURCE_SCOPE" ((@($Grant.resource_scope) -join ','))
    Write-GitHubEnv "LOOP_UAT_TARGET_BRANCH" ([string]$Grant.target_branch)
    Write-GitHubEnv "LOOP_UAT_IMPACT_SCOPE" ([string]$Grant.impact_scope)
    Write-GitHubEnv "LOOP_UAT_EXECUTION_ID" ([string]$Grant.uat_execution_id)
    Write-StepOutput "uat_authorization_id" ([string]$Grant.authorization_id)
    Write-StepOutput "uat_authorized_actions" ((@($Grant.authorized_actions) -join ','))
    Write-StepOutput "uat_authorization_scope_sha256" ([string]$Grant.scope_sha256)

    # v19: the stage grant candidate is mandatory and exported as a controller-owned gate.
    $candidateSha = ([string]$Grant.candidate_sha).Trim().ToLowerInvariant()
    if ($candidateSha -notmatch '^[0-9a-f]{40}$') {
        throw "UAT write authorization grant candidate SHA is missing/invalid"
    }
    # GITHUB_ENV is visible only to later workflow steps.  The binding step
    # validates the candidate immediately after invoking this script, so also
    # publish it into the current PowerShell process environment.
    $env:LOOP_CANDIDATE_SHA = $candidateSha
    Write-GitHubEnv "LOOP_CANDIDATE_SHA" $candidateSha
    Write-StepOutput "candidate_sha" $candidateSha
}

function New-UatWriteAuthorizationGrant($CycleObject, $RoundObject, [string]$Stage) {
    if (-not $RoundObject.candidate_sha) { throw "cannot bind UAT write authorization before candidate SHA exists" }
    Assert-CycleUatAuthorization $CycleObject.uat_cycle_authorization $CycleObject
    $cycleGrant = $CycleObject.uat_cycle_authorization
    $slot = [string]$RoundObject.uat_period_slot
    $primary = [string]$RoundObject.uat_period_primary
    $secondary = [string]$RoundObject.uat_period_secondary
    $poolSha = [string]$RoundObject.uat_period_pool_sha256
    if ($Stage -eq 'FABLE') {
        $slot = [string]$RoundObject.final_audit_uat_period_slot
        $primary = [string]$RoundObject.final_audit_uat_period_primary
        $secondary = [string]$RoundObject.final_audit_uat_period_secondary
        $poolSha = [string]$RoundObject.final_audit_uat_period_pool_sha256
    }
    if (-not $slot -or -not $primary -or -not $secondary -or -not $poolSha) { throw "cannot bind $Stage UAT write authorization before the stage period allocation exists" }
    $grant = [pscustomobject][ordered]@{
        schema_version = 3
        authorization_id = [string]$cycleGrant.authorization_id
        authorization_actor = [string]$cycleGrant.authorization_actor
        authorization_run_id = [string]$cycleGrant.authorization_run_id
        authorization_run_attempt = [string]$cycleGrant.authorization_run_attempt
        authorized_at = Utc-Now
        cycle = [int]$CycleObject.cycle
        cycle_scope_sha256 = [string]$cycleGrant.cycle_scope_sha256
        round = [int]$RoundObject.round
        candidate_sha = [string]$RoundObject.candidate_sha
        verifier_stage = $Stage
        period_slot = [int]$slot
        period_primary = [int]$primary
        period_secondary = [int]$secondary
        period_pool_sha256 = $poolSha
        uat_execution_id = ("c{0}-r{1}-{2}-s{3}-{4}" -f [int]$CycleObject.cycle, [int]$RoundObject.round, $Stage.ToLowerInvariant(), [string]$slot, ([string]$RoundObject.candidate_sha).ToLowerInvariant().Substring(0, 12))
        authorized_actions = @($cycleGrant.authorized_actions)
        target_namespace = [string]$cycleGrant.target_namespace
        resource_scope = @($cycleGrant.resource_scope)
        target_branch = [string]$cycleGrant.target_branch
        impact_scope = [string]$cycleGrant.impact_scope
        scope_sha256 = $null
    }
    $grant.scope_sha256 = Get-UatWriteAuthorizationScopeSha256 $grant
    return $grant
}

function Bind-UatWriteAuthorization([int]$CycleNumber, [int]$RoundNumber, [string]$Stage) {
    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $cycleObject = Get-Cycle $state $CycleNumber
    $roundObject = Get-Round $cycleObject $RoundNumber
    if (-not $roundObject) { throw "round $CycleNumber/$RoundNumber is missing" }
    if (-not $roundObject.candidate_sha) { throw "cannot bind UAT write authorization without candidate SHA" }
    Assert-CycleUatAuthorization $cycleObject.uat_cycle_authorization $cycleObject
    $stageUpper = ([string]$Stage).Trim().ToUpperInvariant()
    if ($stageUpper -notin @('OPUS','FABLE')) { throw "invalid verifier stage for UAT authorization: $Stage" }
    $property = if ($stageUpper -eq 'OPUS') { 'uat_write_authorization_opus' } else { 'uat_write_authorization_fable' }
    $shaProperty = if ($stageUpper -eq 'OPUS') { 'uat_write_authorization_opus_sha256' } else { 'uat_write_authorization_fable_sha256' }
    $existing = $null
    if ($roundObject.PSObject.Properties.Name -contains $property) { $existing = $roundObject.$property }
    if ($existing) {
        $legacy = -not ($existing.PSObject.Properties.Name -contains 'cycle_scope_sha256') -or [int]$existing.schema_version -lt 3
        if (-not $legacy) {
            Assert-UatWriteAuthorizationGrantMatchesRound $existing $cycleObject $roundObject $stageUpper
            Export-UatWriteAuthorizationEnvironment $existing
            Write-Host "[UAT-AUTHORIZATION] reusing Candidate/period stage grant derived from Cycle authorization stage=$stageUpper execution=$($existing.uat_execution_id) scope=$($existing.scope_sha256)"
            return
        }
    }

    $grant = New-UatWriteAuthorizationGrant $cycleObject $roundObject $stageUpper
    if ($existing) {
        $history = @()
        if ($roundObject.PSObject.Properties.Name -contains 'uat_write_authorization_history') { $history = @($roundObject.uat_write_authorization_history) }
        Ensure-Property $roundObject 'uat_write_authorization_history' (@($history) + @($existing))
    }
    Ensure-Property $roundObject 'protected_evidence_sha256' $null
    Ensure-Property $roundObject 'protected_round_contract_sha256' $null
    Ensure-Property $roundObject 'protected_evidence_bound_at' $null
    Ensure-Property $roundObject 'final_audit_evidence_verified' $null
    Ensure-Property $roundObject 'final_audit_evidence_verified_verdict' $null
    Ensure-Property $roundObject 'final_audit_evidence_verified_protected_sha256' $null
    Ensure-Property $roundObject 'final_audit_evidence_verified_at' $null
    Ensure-Property $roundObject $property $grant
    Ensure-Property $roundObject $shaProperty ([string]$grant.scope_sha256)
    $contextDir = Join-Path $CyclesDir ("cycle-{0}\round-{1}\context" -f $CycleNumber, $RoundNumber)
    New-Item -ItemType Directory -Force $contextDir | Out-Null
    Write-Utf8NoBomAtomic (Join-Path $contextDir ("uat-write-authorization-{0}.json" -f $stageUpper.ToLowerInvariant())) (($grant | ConvertTo-Json -Depth 30) + "`n")
    Save-State $state
    Export-UatWriteAuthorizationEnvironment $grant
    Write-Host "[UAT-AUTHORIZATION] derived stage grant from durable Cycle authorization stage=$stageUpper cycle=$CycleNumber round=$RoundNumber candidate=$($roundObject.candidate_sha) execution=$($grant.uat_execution_id) actions=$(@($grant.authorized_actions) -join ',') scope=$($grant.scope_sha256)"
}

function Get-Cycle($State, [int]$Number) {
    return @($State.cycles | Where-Object { [int]$_.cycle -eq $Number } | Select-Object -First 1)[0]
}

function Get-Round($CycleObject, [int]$Number) {
    if (-not $CycleObject) { return $null }
    return @($CycleObject.rounds | Where-Object { [int]$_.round -eq $Number } | Select-Object -First 1)[0]
}

function Load-UatPeriodPool() {
    $path = $env:UAT_PERIOD_POOL_FILE
    if (-not (Test-Path $path)) { throw "UAT period pool missing: $path" }
    try {
        $pool = [IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    }
    catch {
        throw "UAT period pool is invalid JSON: $($_.Exception.Message)"
    }
    if ([int]$pool.schema_version -ne 1) { throw "unsupported UAT period pool schema_version: $($pool.schema_version)" }
    $pairs = @($pool.pairs)
    if ($pairs.Count -lt 1) { throw "UAT period pool contains no pairs" }

    $slotSeen = @{}
    $periodSeen = @{}
    foreach ($pair in $pairs) {
        $slot = [int]$pair.slot
        $primary = [int]$pair.primary_period
        $secondary = [int]$pair.secondary_period
        if ($slot -lt 1) { throw "UAT period pool slot must be >= 1" }
        if ($primary -lt 1 -or $secondary -lt 1) { throw "UAT period values must be positive" }
        if ($primary -eq $secondary) { throw "UAT period pool slot $slot reuses the same period twice" }
        if ($slotSeen.ContainsKey($slot)) { throw "duplicate UAT period pool slot: $slot" }
        $slotSeen[$slot] = $true
        foreach ($period in @($primary, $secondary)) {
            if ($periodSeen.ContainsKey($period)) { throw "duplicate UAT period value in pool: $period" }
            $periodSeen[$period] = $true
        }
    }
    return $pool
}

function Get-UatPeriodPoolSha256() {
    return (Get-FileHash -Algorithm SHA256 $env:UAT_PERIOD_POOL_FILE).Hash.ToLowerInvariant()
}

$UatPeriodPool = Load-UatPeriodPool
$UatPeriodPoolSha256 = Get-UatPeriodPoolSha256

function Assert-PeriodPoolStable($State) {
    if (-not $State) { return }
    $stored = [string]$State.uat_period_pool_sha256
    if ($stored -and $stored.ToLowerInvariant() -ne $UatPeriodPoolSha256) {
        foreach ($cycleObject in @($State.cycles)) {
            foreach ($roundObject in @($cycleObject.rounds)) {
                foreach ($allocation in @(Get-RoundPeriodAllocations $cycleObject $roundObject)) {
                    $slot = [int]$allocation.slot
                    $pair = Get-PeriodPairBySlot $slot
                    if (-not $pair) {
                        throw "allocated durable UAT period slot $slot is missing from the current pool ($($allocation.label))"
                    }
                    if ([int]$pair.primary_period -ne [int]$allocation.primary -or [int]$pair.secondary_period -ne [int]$allocation.secondary) {
                        throw "allocated durable UAT period slot $slot changed in the current pool ($($allocation.label)); ledger=$($allocation.primary)/$($allocation.secondary) current=$($pair.primary_period)/$($pair.secondary_period)"
                    }
                }
            }
        }
        Write-Host "[PERIOD-POOL] digest changed by an append-compatible update; all durable allocated pairs remain immutable"
    }
}

function Get-RoundPeriodAllocations($CycleObject, $RoundObject) {
    $items = New-Object System.Collections.Generic.List[object]
    $roundLabel = "cycle $($CycleObject.cycle) round $($RoundObject.round)"

    $slotText = [string]$RoundObject.uat_period_slot
    if ($slotText) {
        $items.Add([pscustomobject]@{
            slot = [int]$RoundObject.uat_period_slot
            primary = [int]$RoundObject.uat_period_primary
            secondary = [int]$RoundObject.uat_period_secondary
            label = "$roundLabel Opus"
        })
    }

    $finalSlotText = [string]$RoundObject.final_audit_uat_period_slot
    if ($finalSlotText) {
        $items.Add([pscustomobject]@{
            slot = [int]$RoundObject.final_audit_uat_period_slot
            primary = [int]$RoundObject.final_audit_uat_period_primary
            secondary = [int]$RoundObject.final_audit_uat_period_secondary
            label = "$roundLabel Fable final-audit"
        })
    }

    foreach ($retired in @($RoundObject.retired_uat_period_allocations)) {
        if ($null -eq $retired -or -not [string]$retired.slot) { continue }
        $items.Add([pscustomobject]@{
            slot = [int]$retired.slot
            primary = [int]$retired.primary
            secondary = [int]$retired.secondary
            label = "$roundLabel legacy retired slot $($retired.slot)"
        })
    }
    return $items.ToArray()
}

function Get-UsedPeriodSlots($State) {
    $used = @{}
    if (-not $State) { return $used }
    foreach ($cycleObject in @($State.cycles)) {
        foreach ($roundObject in @($cycleObject.rounds)) {
            foreach ($allocation in @(Get-RoundPeriodAllocations $cycleObject $roundObject)) {
                $used[[int]$allocation.slot] = $true
            }
        }
    }
    return $used
}

function Assert-NoDuplicateRoundPeriodAllocations($State) {
    $slots = @{}
    $periods = @{}
    foreach ($cycleObject in @($State.cycles)) {
        foreach ($roundObject in @($cycleObject.rounds)) {
            foreach ($allocation in @(Get-RoundPeriodAllocations $cycleObject $roundObject)) {
                $slot = [int]$allocation.slot
                $label = [string]$allocation.label
                if ($slots.ContainsKey($slot)) {
                    throw "duplicate durable UAT period slot $slot between $($slots[$slot]) and $label"
                }
                $slots[$slot] = $label
                foreach ($period in @([int]$allocation.primary, [int]$allocation.secondary)) {
                    if ($periods.ContainsKey($period)) {
                        throw "duplicate durable UAT period value $period between $($periods[$period]) and $label"
                    }
                    $periods[$period] = $label
                }
            }
        }
    }
}

function Get-PeriodPairBySlot([int]$Slot) {
    return @($UatPeriodPool.pairs | Where-Object { [int]$_.slot -eq $Slot } | Select-Object -First 1)[0]
}

function Ensure-RoundPeriodAllocation($State, $RoundObject) {
    if (-not $RoundObject) { throw "cannot allocate UAT periods without a round object" }
    Assert-PeriodPoolStable $State

    $slotText = [string]$RoundObject.uat_period_slot
    $primaryText = [string]$RoundObject.uat_period_primary
    $secondaryText = [string]$RoundObject.uat_period_secondary
    $hashText = [string]$RoundObject.uat_period_pool_sha256
    $hasAny = $slotText -or $primaryText -or $secondaryText -or $hashText
    $hasAll = $slotText -and $primaryText -and $secondaryText -and $hashText
    if ($hasAny -and -not $hasAll) {
        throw "round has a partial UAT period allocation; refusing to guess or repair it"
    }

    if ($hasAll) {
        $slot = [int]$RoundObject.uat_period_slot
        $pair = Get-PeriodPairBySlot $slot
        if (-not $pair) { throw "round references UAT period slot $slot which is absent from the configured pool" }
        if ([int]$pair.primary_period -ne [int]$RoundObject.uat_period_primary -or [int]$pair.secondary_period -ne [int]$RoundObject.uat_period_secondary) {
            throw "round UAT period allocation does not match configured pool slot $slot"
        }
        if ($hashText -notmatch '^[0-9a-fA-F]{64}$') {
            throw "round UAT period pool hash is invalid"
        }
        return $RoundObject
    }

    $used = Get-UsedPeriodSlots $State
    $available = @($UatPeriodPool.pairs | Sort-Object {[int]$_.slot} | Where-Object { -not $used.ContainsKey([int]$_.slot) } | Select-Object -First 1)
    if ($available.Count -lt 1) {
        throw "PERIOD_POOL_EXHAUSTED: no unused UAT period pair remains in $env:UAT_PERIOD_POOL_FILE. Do not reuse a prior period. Extend the governed pool before continuing."
    }
    $pair = $available[0]
    Ensure-Property $RoundObject "uat_period_slot" ([int]$pair.slot)
    Ensure-Property $RoundObject "uat_period_primary" ([int]$pair.primary_period)
    Ensure-Property $RoundObject "uat_period_secondary" ([int]$pair.secondary_period)
    Ensure-Property $RoundObject "uat_period_pool_sha256" $UatPeriodPoolSha256
    Write-Host "[PERIOD-ALLOC] slot=$($pair.slot) primary=$($pair.primary_period) secondary=$($pair.secondary_period)"
    return $RoundObject
}

function Ensure-FinalAuditPeriodAllocation($State, $RoundObject) {
    if (-not $RoundObject) { throw "cannot allocate Fable final-audit UAT periods without a round object" }
    Assert-PeriodPoolStable $State

    $slotText = [string]$RoundObject.final_audit_uat_period_slot
    $primaryText = [string]$RoundObject.final_audit_uat_period_primary
    $secondaryText = [string]$RoundObject.final_audit_uat_period_secondary
    $hashText = [string]$RoundObject.final_audit_uat_period_pool_sha256
    $hasAny = $slotText -or $primaryText -or $secondaryText -or $hashText
    $hasAll = $slotText -and $primaryText -and $secondaryText -and $hashText
    if ($hasAny -and -not $hasAll) {
        throw "round has a partial Fable final-audit UAT period allocation; refusing to guess or repair it"
    }

    if ($hasAll) {
        $slot = [int]$RoundObject.final_audit_uat_period_slot
        $pair = Get-PeriodPairBySlot $slot
        if (-not $pair) { throw "round references Fable final-audit UAT period slot $slot which is absent from the configured pool" }
        if ([int]$pair.primary_period -ne [int]$RoundObject.final_audit_uat_period_primary -or [int]$pair.secondary_period -ne [int]$RoundObject.final_audit_uat_period_secondary) {
            throw "round Fable final-audit UAT period allocation does not match configured pool slot $slot"
        }
        if ($hashText -notmatch '^[0-9a-fA-F]{64}$') {
            throw "round Fable final-audit UAT period pool hash is invalid"
        }
        return $RoundObject
    }

    $used = Get-UsedPeriodSlots $State
    $available = @($UatPeriodPool.pairs | Sort-Object {[int]$_.slot} | Where-Object { -not $used.ContainsKey([int]$_.slot) } | Select-Object -First 1)
    if ($available.Count -lt 1) {
        throw "PERIOD_POOL_EXHAUSTED: no unused UAT period pair remains for Fable final audit in $env:UAT_PERIOD_POOL_FILE. Do not reuse a prior period. Extend the governed pool before continuing."
    }
    $pair = $available[0]
    Ensure-Property $RoundObject "final_audit_uat_period_slot" ([int]$pair.slot)
    Ensure-Property $RoundObject "final_audit_uat_period_primary" ([int]$pair.primary_period)
    Ensure-Property $RoundObject "final_audit_uat_period_secondary" ([int]$pair.secondary_period)
    Ensure-Property $RoundObject "final_audit_uat_period_pool_sha256" $UatPeriodPoolSha256
    Write-Host "[FINAL-AUDIT-PERIOD-ALLOC] slot=$($pair.slot) primary=$($pair.primary_period) secondary=$($pair.secondary_period)"
    return $RoundObject
}

function Export-FinalAuditPeriodEnvironment($RoundObject) {
    Write-GitHubEnv "LOOP_FINAL_UAT_PERIOD_SLOT" ([string]$RoundObject.final_audit_uat_period_slot)
    Write-GitHubEnv "LOOP_FINAL_UAT_PERIOD_PRIMARY" ([string]$RoundObject.final_audit_uat_period_primary)
    Write-GitHubEnv "LOOP_FINAL_UAT_PERIOD_SECONDARY" ([string]$RoundObject.final_audit_uat_period_secondary)
    Write-GitHubEnv "LOOP_FINAL_UAT_PERIOD_POOL_SHA256" ([string]$RoundObject.final_audit_uat_period_pool_sha256)
    Write-StepOutput "final_audit_uat_period_slot" ([string]$RoundObject.final_audit_uat_period_slot)
    Write-StepOutput "final_audit_uat_period_primary" ([string]$RoundObject.final_audit_uat_period_primary)
    Write-StepOutput "final_audit_uat_period_secondary" ([string]$RoundObject.final_audit_uat_period_secondary)
    Write-StepOutput "final_audit_uat_period_pool_sha256" ([string]$RoundObject.final_audit_uat_period_pool_sha256)
}

function Bind-LegacyVerifierPeriodMetadata($RoundObject) {
    $progressPath = Join-Path $env:OUTDIR "verifier-state\verifier-progress.json"
    if (-not (Test-Path $progressPath)) { return }
    try {
        $progress = [IO.File]::ReadAllText($progressPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    }
    catch {
        return
    }
    if ([string]$progress.candidate_sha -ne [string]$RoundObject.candidate_sha) { return }

    $names = @("uat_period_slot", "uat_period_primary", "uat_period_secondary", "uat_period_pool_sha256")
    $present = @($names | Where-Object { $progress.PSObject.Properties.Name -contains $_ })
    if ($present.Count -gt 0 -and $present.Count -lt $names.Count) {
        throw "legacy verifier progress contains a partial UAT period allocation; refusing to guess"
    }
    if ($present.Count -eq $names.Count) {
        $matchesCurrent = ([int]$progress.uat_period_slot -eq [int]$RoundObject.uat_period_slot -and
            [int]$progress.uat_period_primary -eq [int]$RoundObject.uat_period_primary -and
            [int]$progress.uat_period_secondary -eq [int]$RoundObject.uat_period_secondary -and
            [string]$progress.uat_period_pool_sha256 -eq [string]$RoundObject.uat_period_pool_sha256)
        if ($matchesCurrent) { return }

        foreach ($retired in @($RoundObject.retired_uat_period_allocations)) {
            if ($null -eq $retired) { continue }
            $matchesRetired = ([int]$progress.uat_period_slot -eq [int]$retired.slot -and
                [int]$progress.uat_period_primary -eq [int]$retired.primary -and
                [int]$progress.uat_period_secondary -eq [int]$retired.secondary -and
                [string]$progress.uat_period_pool_sha256 -eq [string]$retired.pool_sha256)
            if ($matchesRetired) {
                Write-Host "[V8-PERIOD-MIGRATION] legacy verifier progress matches a retired legacy UAT allocation; allowing staged migration to continue"
                return
            }
        }
        throw "legacy verifier progress UAT period allocation conflicts with durable current and retired round allocations"
    }

    Ensure-Property $progress "uat_period_slot" ([int]$RoundObject.uat_period_slot)
    Ensure-Property $progress "uat_period_primary" ([int]$RoundObject.uat_period_primary)
    Ensure-Property $progress "uat_period_secondary" ([int]$RoundObject.uat_period_secondary)
    Ensure-Property $progress "uat_period_pool_sha256" ([string]$RoundObject.uat_period_pool_sha256)
    Write-Utf8NoBomAtomic $progressPath (($progress | ConvertTo-Json -Depth 50) + "`n")
    Write-Host "[PERIOD-MIGRATION] legacy verifier progress bound to durable UAT period allocation slot=$($RoundObject.uat_period_slot) periods=$($RoundObject.uat_period_primary)/$($RoundObject.uat_period_secondary)"
}

function Export-RoundPeriodEnvironment($RoundObject) {
    Write-GitHubEnv "LOOP_UAT_PERIOD_SLOT" ([string]$RoundObject.uat_period_slot)
    Write-GitHubEnv "LOOP_UAT_PERIOD_PRIMARY" ([string]$RoundObject.uat_period_primary)
    Write-GitHubEnv "LOOP_UAT_PERIOD_SECONDARY" ([string]$RoundObject.uat_period_secondary)
    Write-GitHubEnv "LOOP_UAT_PERIOD_POOL_SHA256" ([string]$RoundObject.uat_period_pool_sha256)
    Write-StepOutput "uat_period_slot" ([string]$RoundObject.uat_period_slot)
    Write-StepOutput "uat_period_primary" ([string]$RoundObject.uat_period_primary)
    Write-StepOutput "uat_period_secondary" ([string]$RoundObject.uat_period_secondary)
    Write-StepOutput "uat_period_pool_sha256" ([string]$RoundObject.uat_period_pool_sha256)
}

function Upgrade-StatePeriodSchema($State) {
    if (-not $State) { return $null }
    $changed = $false
    $schema = 0
    if ($State.PSObject.Properties.Name -contains "schema_version") { $schema = [int]$State.schema_version }
    if ($schema -gt 4) { throw "unsupported loop-state schema_version: $schema" }

    $stored = [string]$State.uat_period_pool_sha256
    if ($stored) {
        Assert-PeriodPoolStable $State
    }
    else {
        Ensure-Property $State "uat_period_pool_sha256" $UatPeriodPoolSha256
        $changed = $true
    }

    foreach ($cycleObject in @($State.cycles | Sort-Object cycle)) {
        foreach ($roundObject in @($cycleObject.rounds | Sort-Object round)) {
            $before = [string]$roundObject.uat_period_slot
            Ensure-RoundPeriodAllocation $State $roundObject | Out-Null
            Bind-LegacyVerifierPeriodMetadata $roundObject
            if (-not $before) { $changed = $true }

            $hasFinalAuditAllocation = ([string]$roundObject.final_audit_uat_period_slot) -or
                ([string]$roundObject.final_audit_uat_period_primary) -or
                ([string]$roundObject.final_audit_uat_period_secondary) -or
                ([string]$roundObject.final_audit_uat_period_pool_sha256)
            if ($hasFinalAuditAllocation) {
                Ensure-FinalAuditPeriodAllocation $State $roundObject | Out-Null
            }
        }
    }
    Assert-NoDuplicateRoundPeriodAllocations $State

    if ($schema -lt 3) {
        Ensure-Property $State "schema_version" 3
        $changed = $true
    }
    if ($changed) {
        Save-State $State
        Write-Host "[PERIOD-MIGRATION] durable loop state upgraded to schema 3 with staged Opus/Fable immutable UAT period allocations"
    }
    return $State
}

function Get-WorktreeHead() {
    $head = (git -C $env:WORKTREE rev-parse HEAD).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') { throw "git rev-parse failed while resolving current Candidate SHA" }
    return $head
}

function Get-WorktreeBranch() {
    $branch = (git -C $env:WORKTREE rev-parse --abbrev-ref HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $branch) { throw "git rev-parse --abbrev-ref HEAD failed while resolving Candidate Branch" }
    return $branch
}

function New-CycleObject([int]$Number, [string]$PreviousCycleReport, [string]$CycleStartSha = "", [string]$CandidateBranch = "", [string]$FindingsSource = "", [string]$FindingsRef = "") {
    return [pscustomobject][ordered]@{
        cycle = $Number
        status = "RUNNING"
        candidate_branch = $CandidateBranch
        cycle_start_sha = $CycleStartSha
        current_candidate_sha = $CycleStartSha
        findings_source = $FindingsSource
        findings_ref = $FindingsRef
        previous_cycle_report = $PreviousCycleReport
        started_at = Utc-Now
        completed_at = $null
        rounds = @()
    }
}

function New-State() {
    $head = Get-WorktreeHead
    $branch = Get-WorktreeBranch
    if ($branch -ne [string]$env:BRANCH) {
        throw "Candidate Branch mismatch before Loop initialization: workflow=$env:BRANCH worktree=$branch"
    }
    $cycleObject = New-CycleObject 1 "" $head $branch "" ""
    return [pscustomobject][ordered]@{
        schema_version = 4
        work_id = "WORK-PVAM-02"
        uat_period_pool_sha256 = $UatPeriodPoolSha256
        max_rounds_per_cycle = $MaxRoundsPerCycle
        candidate_branch = $branch
        current_candidate_sha = $head
        current_cycle = 1
        current_round = 1
        stage = "CODEX_PRODUCE"
        status = "RUNNING"
        pause_reason = $null
        opus_result = $null
        fable_result = $null
        findings_source = $null
        findings_ref = $null
        created_at = Utc-Now
        updated_at = Utc-Now
        cycles = @($cycleObject)
    }
}

function Get-LegacyCoreResults($RoundObject, [string]$LegacyVerdict) {
    $opus = ""
    $fable = ""
    # v10+ ledgers have an explicit final-audit verdict property.  When that
    # property exists, its value is authoritative: a retained Fable period slot
    # may survive BLOCKED/resume while the verified verdict is intentionally
    # cleared before Opus runs again.  Pre-v10 ledgers (notably v8-v9) predate
    # the marker entirely, so only for that older shape do we fall back to the
    # durable Fable period allocation as provenance.
    $hasVerifiedFinalAuditVerdictProperty = $RoundObject.PSObject.Properties.Name -contains "final_audit_evidence_verified_verdict"
    $verifiedFinalAuditVerdict = ([string]$RoundObject.final_audit_evidence_verified_verdict).Trim()
    $legacyFableAllocation = ([string]$RoundObject.final_audit_uat_period_slot).Trim()

    if ($LegacyVerdict -eq "PASS") {
        $opus = "NO_BUG"
        $fable = "FINAL_PASS"
    }
    elseif ($LegacyVerdict -eq "REJECTED") {
        $isFableReject = $false
        if ($hasVerifiedFinalAuditVerdictProperty) {
            $isFableReject = ($verifiedFinalAuditVerdict -eq "REJECTED")
        }
        elseif ($legacyFableAllocation) {
            $isFableReject = $true
        }

        if ($isFableReject) {
            $opus = "NO_BUG"
            $fable = "FINAL_REJECT"
        }
        else {
            $opus = "BUG_FOUND"
        }
    }
    elseif ($LegacyVerdict -eq "BLOCKED") {
        # BLOCKED is retained as an execution/environment status, not a reviewer result.
        if ($verifiedFinalAuditVerdict -eq "BLOCKED") { $opus = "NO_BUG" }
    }
    return [pscustomobject]@{ opus_result = $opus; fable_result = $fable }
}

function Upgrade-CoreStateSchema($State) {
    if (-not $State) { return $null }
    $changed = $false
    $schema = 0
    if ($State.PSObject.Properties.Name -contains "schema_version") { $schema = [int]$State.schema_version }
    if ($schema -gt 4) { throw "unsupported loop-state schema_version: $schema" }

    $candidateBranch = [string]$State.candidate_branch
    if (-not $candidateBranch) {
        $candidateBranch = $env:BRANCH
        Ensure-Property $State "candidate_branch" $candidateBranch
        $changed = $true
    }
    if ($candidateBranch -ne $env:BRANCH) {
        throw "Candidate Branch drift detected: ledger=$candidateBranch workflow=$env:BRANCH. A WORK must keep one Candidate Branch across Cycles."
    }

    $latestCandidate = ""
    foreach ($cycleObject in @($State.cycles | Sort-Object cycle)) {
        $cycleBranch = [string]$cycleObject.candidate_branch
        if (-not $cycleBranch) { Ensure-Property $cycleObject "candidate_branch" $candidateBranch; $changed = $true }
        elseif ($cycleBranch -ne $candidateBranch) { throw "Cycle $($cycleObject.cycle) Candidate Branch differs from WORK Candidate Branch" }

        foreach ($roundObject in @($cycleObject.rounds | Sort-Object round)) {
            if ([string]$roundObject.candidate_sha) { $latestCandidate = ([string]$roundObject.candidate_sha).ToLowerInvariant() }
            if (-not ($roundObject.PSObject.Properties.Name -contains "opus_result")) { Ensure-Property $roundObject "opus_result" $null; $changed = $true }
            if (-not ($roundObject.PSObject.Properties.Name -contains "fable_result")) { Ensure-Property $roundObject "fable_result" $null; $changed = $true }
            if (-not ($roundObject.PSObject.Properties.Name -contains "produced_findings_source")) { Ensure-Property $roundObject "produced_findings_source" $null; $changed = $true }
            if (-not ($roundObject.PSObject.Properties.Name -contains "produced_findings_ref")) { Ensure-Property $roundObject "produced_findings_ref" $null; $changed = $true }
            # Legacy result backfill is a migration operation, not a native
            # schema-4 recovery rule. A current staged BLOCKED Round may
            # intentionally have an empty canonical reviewer result; never
            # reinterpret that emptiness from retained historical markers.
            $explicitLegacyImport = (($roundObject.PSObject.Properties.Name -contains "legacy_imported_from_pre_v8") -and (([string]$roundObject.legacy_imported_from_pre_v8 -eq "true") -or ($roundObject.legacy_imported_from_pre_v8 -eq $true)))
            $allowLegacyResultBackfill = ($schema -lt 4) -or $explicitLegacyImport
            if ($allowLegacyResultBackfill -and [string]$roundObject.verdict -and -not [string]$roundObject.opus_result) {
                $legacyCore = Get-LegacyCoreResults $roundObject ([string]$roundObject.verdict)
                if ($legacyCore.opus_result) { Ensure-Property $roundObject "opus_result" $legacyCore.opus_result; $changed = $true }
                if ($legacyCore.fable_result) { Ensure-Property $roundObject "fable_result" $legacyCore.fable_result; $changed = $true }
            }
            if ([string]$roundObject.verdict -eq "REJECTED" -and [string]$roundObject.report_path -and -not [string]$roundObject.produced_findings_ref) {
                $producedSource = if ([string]$roundObject.fable_result -eq "FINAL_REJECT") { "FABLE" } else { "OPUS" }
                Ensure-Property $roundObject "produced_findings_source" $producedSource
                Ensure-Property $roundObject "produced_findings_ref" ([string]$roundObject.report_path)
                $changed = $true
            }
        }

        if (-not [string]$cycleObject.current_candidate_sha) {
            $cycleCandidate = ""
            $cycleRounds = @($cycleObject.rounds | Sort-Object round)
            if ($cycleRounds.Count -gt 0 -and [string]$cycleRounds[-1].candidate_sha) { $cycleCandidate = ([string]$cycleRounds[-1].candidate_sha).ToLowerInvariant() }
            if (-not $cycleCandidate) { $cycleCandidate = $latestCandidate }
            if (-not $cycleCandidate) { $cycleCandidate = Get-WorktreeHead }
            Ensure-Property $cycleObject "current_candidate_sha" $cycleCandidate
            $changed = $true
        }
        if (-not [string]$cycleObject.cycle_start_sha) {
            $cycleStart = ""
            $cycleRounds = @($cycleObject.rounds | Sort-Object round)
            if ($cycleRounds.Count -gt 0 -and [string]$cycleRounds[0].producer_base_sha) { $cycleStart = ([string]$cycleRounds[0].producer_base_sha).ToLowerInvariant() }
            if (-not $cycleStart -and [string]$cycleObject.current_candidate_sha) { $cycleStart = ([string]$cycleObject.current_candidate_sha).ToLowerInvariant() }
            Ensure-Property $cycleObject "cycle_start_sha" $cycleStart
            $changed = $true
        }
        if (-not ($cycleObject.PSObject.Properties.Name -contains "findings_source")) { Ensure-Property $cycleObject "findings_source" $null; $changed = $true }
        if (-not ($cycleObject.PSObject.Properties.Name -contains "findings_ref")) { Ensure-Property $cycleObject "findings_ref" $null; $changed = $true }
    }

    if (-not $latestCandidate) { $latestCandidate = Get-WorktreeHead }
    if (-not [string]$State.current_candidate_sha) { Ensure-Property $State "current_candidate_sha" $latestCandidate; $changed = $true }

    $currentCycleObject = Get-Cycle $State ([int]$State.current_cycle)
    $currentRoundObject = Get-Round $currentCycleObject ([int]$State.current_round)
    $latestCompletedRoundObject = $null
    $latestFableTerminalRoundObject = $null
    $completedRounds = @()
    if ($currentCycleObject) {
        $completedRounds = @($currentCycleObject.rounds | Where-Object { [string]$_.phase -eq "COMPLETE" } | Sort-Object round)
        if ($completedRounds.Count -gt 0) { $latestCompletedRoundObject = $completedRounds[-1] }
        $fableTerminalRounds = @($completedRounds | Where-Object { [string]$_.fable_result -in @("FINAL_PASS", "FINAL_REJECT") })
        if ($fableTerminalRounds.Count -gt 0) { $latestFableTerminalRoundObject = $fableTerminalRounds[-1] }
    }

    # Fable is the terminal reviewer for a Cycle.  Legacy v20/R1 could
    # incorrectly continue Codex/Opus after FINAL_REJECT, so later Opus rounds
    # never supersede a Fable decision.  A *later Fable FINAL_PASS*, however,
    # is an explicit terminal decision that supersedes an earlier FINAL_REJECT.
    # Migration therefore uses the latest completed Fable terminal result in
    # the current Cycle, rather than either the latest completed Round or an
    # unconditional "ever rejected" barrier.
    $governanceRoundObject = $currentRoundObject
    if (-not $governanceRoundObject) { $governanceRoundObject = $latestCompletedRoundObject }

    $legacyStatus = [string]$State.status
    $pauseReason = [string]$State.pause_reason
    $terminalGovernanceNeedsRewrite = $false

    if ($latestFableTerminalRoundObject -and [string]$latestFableTerminalRoundObject.fable_result -eq "FINAL_PASS") {
        $governanceRoundObject = $latestFableTerminalRoundObject
        $terminalRound = [int]$latestFableTerminalRoundObject.round
        $terminalGovernanceNeedsRewrite = (
            ([string]$State.status -ne "COMPLETED") -or
            ([string]$State.stage -ne "COMPLETED") -or
            ([string]$State.pause_reason -ne "") -or
            ([int]$State.current_round -ne $terminalRound) -or
            ([string]$State.opus_result -ne [string]$latestFableTerminalRoundObject.opus_result) -or
            ([string]$State.fable_result -ne "FINAL_PASS") -or
            ([string]$State.findings_source -ne "") -or
            ([string]$State.findings_ref -ne "") -or
            ($currentCycleObject -and (
                ([string]$currentCycleObject.status -ne "COMPLETED") -or
                ([string]$currentCycleObject.findings_source -ne "") -or
                ([string]$currentCycleObject.findings_ref -ne "")
            ))
        )
        if ($terminalGovernanceNeedsRewrite) {
            Ensure-Property $State "status" "COMPLETED"
            Ensure-Property $State "stage" "COMPLETED"
            Ensure-Property $State "pause_reason" $null
            Ensure-Property $State "current_round" $terminalRound
            Ensure-Property $State "opus_result" ([string]$latestFableTerminalRoundObject.opus_result)
            Ensure-Property $State "fable_result" "FINAL_PASS"
            Ensure-Property $State "findings_source" $null
            Ensure-Property $State "findings_ref" $null
            if ($currentCycleObject) {
                Ensure-Property $currentCycleObject "status" "COMPLETED"
                Ensure-Property $currentCycleObject "findings_source" $null
                Ensure-Property $currentCycleObject "findings_ref" $null
            }
            $changed = $true
        }
    }
    elseif ($latestFableTerminalRoundObject -and [string]$latestFableTerminalRoundObject.fable_result -eq "FINAL_REJECT") {
        $governanceRoundObject = $latestFableTerminalRoundObject
        $terminalRound = [int]$latestFableTerminalRoundObject.round
        $terminalFindingsRef = [string]$latestFableTerminalRoundObject.report_path
        $terminalGovernanceNeedsRewrite = (
            ([string]$State.status -ne "PAUSED_AWAITING_USER") -or
            ([string]$State.stage -ne "PAUSED_AWAITING_USER") -or
            ([string]$State.pause_reason -ne "FABLE_FINAL_REJECT") -or
            ([int]$State.current_round -ne $terminalRound) -or
            ([string]$State.opus_result -ne [string]$latestFableTerminalRoundObject.opus_result) -or
            ([string]$State.fable_result -ne "FINAL_REJECT") -or
            ([string]$State.findings_source -ne "FABLE") -or
            ([string]$State.findings_ref -ne $terminalFindingsRef) -or
            ($currentCycleObject -and (
                ([string]$currentCycleObject.status -ne "PAUSED_AWAITING_USER") -or
                ([string]$currentCycleObject.findings_source -ne "FABLE") -or
                ([string]$currentCycleObject.findings_ref -ne $terminalFindingsRef)
            ))
        )
        if ($terminalGovernanceNeedsRewrite) {
            Ensure-Property $State "status" "PAUSED_AWAITING_USER"
            Ensure-Property $State "stage" "PAUSED_AWAITING_USER"
            Ensure-Property $State "pause_reason" "FABLE_FINAL_REJECT"
            Ensure-Property $State "current_round" $terminalRound
            Ensure-Property $State "opus_result" ([string]$latestFableTerminalRoundObject.opus_result)
            Ensure-Property $State "fable_result" "FINAL_REJECT"
            Ensure-Property $State "findings_source" "FABLE"
            Ensure-Property $State "findings_ref" $(if ($terminalFindingsRef) { $terminalFindingsRef } else { $null })
            if ($currentCycleObject) {
                Ensure-Property $currentCycleObject "status" "PAUSED_AWAITING_USER"
                Ensure-Property $currentCycleObject "findings_source" "FABLE"
                Ensure-Property $currentCycleObject "findings_ref" $(if ($terminalFindingsRef) { $terminalFindingsRef } else { $null })
            }
            $changed = $true
        }
    }
    elseif ($legacyStatus -eq "PASS") {
        Ensure-Property $State "status" "COMPLETED"
        Ensure-Property $State "stage" "COMPLETED"
        if ($currentCycleObject) { Ensure-Property $currentCycleObject "status" "COMPLETED" }
        $changed = $true
    }
    elseif ($legacyStatus -eq "LOOP_EXHAUSTED") {
        Ensure-Property $State "status" "PAUSED_AWAITING_USER"
        Ensure-Property $State "stage" "PAUSED_AWAITING_USER"
        Ensure-Property $State "pause_reason" "OPUS_ROUND_LIMIT"
        if ($latestCompletedRoundObject) { Ensure-Property $State "current_round" ([int]$latestCompletedRoundObject.round) }
        if ($currentCycleObject) { Ensure-Property $currentCycleObject "status" "PAUSED_AWAITING_USER" }
        $governanceRoundObject = $latestCompletedRoundObject
        $changed = $true
    }
    elseif ($legacyStatus -eq "IN_PROGRESS") {
        $newStatus = "RUNNING"
        $newStage = "CODEX_PRODUCE"

        if ($currentRoundObject) {
            if ([string]$currentRoundObject.phase -eq "PRODUCING") {
                $newStage = if ([string]$currentRoundObject.action -eq "construct") { "CODEX_PRODUCE" } else { "CODEX_REWORK" }
            }
            elseif ([string]$currentRoundObject.phase -eq "VERIFYING") { $newStage = "OPUS_REVIEW" }
            elseif ([string]$currentRoundObject.phase -eq "COMPLETE" -and [string]$currentRoundObject.verdict -eq "REJECTED") {
                if ([int]$currentRoundObject.round -ge [int]$State.max_rounds_per_cycle) {
                    $newStatus = "PAUSED_AWAITING_USER"
                    $newStage = "PAUSED_AWAITING_USER"
                    $pauseReason = "OPUS_ROUND_LIMIT"
                    $governanceRoundObject = $currentRoundObject
                }
                else { $newStage = "CODEX_REWORK" }
            }
        }
        elseif ($latestCompletedRoundObject) {
            $governanceRoundObject = $latestCompletedRoundObject
            if ([string]$latestCompletedRoundObject.opus_result -eq "BUG_FOUND") {
                if ([int]$latestCompletedRoundObject.round -ge [int]$State.max_rounds_per_cycle) {
                    $newStatus = "PAUSED_AWAITING_USER"
                    $newStage = "PAUSED_AWAITING_USER"
                    $pauseReason = "OPUS_ROUND_LIMIT"
                    Ensure-Property $State "current_round" ([int]$latestCompletedRoundObject.round)
                }
                else {
                    $newStage = "CODEX_REWORK"
                    Ensure-Property $State "current_round" ([int]$latestCompletedRoundObject.round + 1)
                }
            }
        }
        Ensure-Property $State "status" $newStatus
        Ensure-Property $State "stage" $newStage
        Ensure-Property $State "pause_reason" $(if ($newStatus -eq "PAUSED_AWAITING_USER") { $pauseReason } else { $null })
        if ($currentCycleObject) { Ensure-Property $currentCycleObject "status" $newStatus }
        $changed = $true
    }

    if (-not ($State.PSObject.Properties.Name -contains "pause_reason")) { Ensure-Property $State "pause_reason" $null; $changed = $true }
    if (-not ($State.PSObject.Properties.Name -contains "stage")) { Ensure-Property $State "stage" "CODEX_PRODUCE"; $changed = $true }
    if (-not ($State.PSObject.Properties.Name -contains "opus_result")) { Ensure-Property $State "opus_result" $null; $changed = $true }
    if (-not ($State.PSObject.Properties.Name -contains "fable_result")) { Ensure-Property $State "fable_result" $null; $changed = $true }
    if (-not ($State.PSObject.Properties.Name -contains "findings_source")) { Ensure-Property $State "findings_source" $null; $changed = $true }
    if (-not ($State.PSObject.Properties.Name -contains "findings_ref")) { Ensure-Property $State "findings_ref" $null; $changed = $true }

    if ($governanceRoundObject -and [string]$governanceRoundObject.opus_result) { Ensure-Property $State "opus_result" ([string]$governanceRoundObject.opus_result) }
    if ($governanceRoundObject -and [string]$governanceRoundObject.fable_result) { Ensure-Property $State "fable_result" ([string]$governanceRoundObject.fable_result) }
    if ($governanceRoundObject -and [string]$governanceRoundObject.verdict -eq "REJECTED" -and [string]$governanceRoundObject.report_path) {
        $source = if ([string]$governanceRoundObject.fable_result -eq "FINAL_REJECT") { "FABLE" } else { "OPUS" }
        Ensure-Property $State "findings_source" $source
        Ensure-Property $State "findings_ref" ([string]$governanceRoundObject.report_path)
        if ($currentCycleObject) {
            Ensure-Property $currentCycleObject "findings_source" $source
            Ensure-Property $currentCycleObject "findings_ref" ([string]$governanceRoundObject.report_path)
        }
    }

    if ($schema -ne 4) { Ensure-Property $State "schema_version" 4; $changed = $true }
    if ($changed) {
        Save-State $State
        Write-Host "[CORE-MIGRATION] durable loop state upgraded to schema 4 Loop Core governance fields"
    }
    return $State
}

function Validate-Candidate([string]$Sha) {
    if ($Sha -notmatch '^[0-9a-fA-F]{40}$') { throw "invalid candidate SHA: '$Sha'" }
    return $Sha.ToLowerInvariant()
}

function Get-CanonicalVerdict() {
    $resultPath = Join-Path $env:OUTDIR "uat-result.txt"
    if (-not (Test-Path $resultPath)) { return "" }
    $value = ([IO.File]::ReadAllText($resultPath, [System.Text.Encoding]::UTF8)).Trim()
    if ($value -notin @("PASS", "REJECTED", "BLOCKED")) { return "" }
    return $value
}

function Test-ProgressMatchesAllocation($Progress, $RoundObject, [string]$Stage) {
    if ([string]$Progress.candidate_sha -ne [string]$RoundObject.candidate_sha) { return $false }
    if ($Stage -eq "FABLE") {
        if (-not [string]$RoundObject.final_audit_uat_period_slot) { return $false }
        if ([int]$Progress.uat_period_slot -ne [int]$RoundObject.final_audit_uat_period_slot) { return $false }
        if ([int]$Progress.uat_period_primary -ne [int]$RoundObject.final_audit_uat_period_primary) { return $false }
        if ([int]$Progress.uat_period_secondary -ne [int]$RoundObject.final_audit_uat_period_secondary) { return $false }
        if ([string]$Progress.uat_period_pool_sha256 -ne [string]$RoundObject.final_audit_uat_period_pool_sha256) { return $false }
    }
    else {
        if ([int]$Progress.uat_period_slot -ne [int]$RoundObject.uat_period_slot) { return $false }
        if ([int]$Progress.uat_period_primary -ne [int]$RoundObject.uat_period_primary) { return $false }
        if ([int]$Progress.uat_period_secondary -ne [int]$RoundObject.uat_period_secondary) { return $false }
        if ([string]$Progress.uat_period_pool_sha256 -ne [string]$RoundObject.uat_period_pool_sha256) { return $false }
    }
    return $true
}

function Test-ProgressVerdictComplete($Progress, [string]$ExpectedVerdict) {
    if ([string]$Progress.final_verdict -ne $ExpectedVerdict) { return $false }
    if ($ExpectedVerdict -eq "BLOCKED") { return ([string]$Progress.status -eq "BLOCKED") }
    return ([string]$Progress.status -eq "COMPLETE")
}

function Test-CanonicalVerifierComplete($CycleObject, $RoundObject) {
    if (-not $RoundObject) { return $false }
    if (-not $RoundObject.candidate_sha) { return $false }

    $reportPath = Join-Path $env:OUTDIR "UAT_REPORT.md"
    $resultPath = Join-Path $env:OUTDIR "uat-result.txt"
    if (-not (Test-Path $reportPath)) { return $false }
    if (-not (Test-Path $resultPath)) { return $false }

    $verdict = Get-CanonicalVerdict
    if (-not $verdict) { return $false }

    $opusResultPath = Join-Path $env:OUTDIR "opus-result.txt"
    if (Test-Path $opusResultPath) {
        $opusAuthSha = ([string]$RoundObject.uat_write_authorization_opus_sha256).Trim().ToLowerInvariant()
        if ($opusAuthSha -notmatch '^[0-9a-f]{64}$') { return $false }
        $opusVerdict = ([IO.File]::ReadAllText($opusResultPath, [System.Text.Encoding]::UTF8)).Trim()
        if ($opusVerdict -notin @("PRECHECK_PASS", "REJECTED", "BLOCKED")) { return $false }

        if ($opusVerdict -eq "PRECHECK_PASS") {
            $fableAuthSha = ([string]$RoundObject.uat_write_authorization_fable_sha256).Trim().ToLowerInvariant()
            if ($fableAuthSha -notmatch '^[0-9a-f]{64}$') { return $false }
            $progressPath = Join-Path $env:OUTDIR "verifier-state\fable\verifier-progress.json"
            if (-not (Test-Path $progressPath)) { return $false }
            try { $progress = [IO.File]::ReadAllText($progressPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json }
            catch { return $false }
            if ([string]$progress.verifier_stage -ne "FABLE") { return $false }
            if (-not (Test-ProgressMatchesAllocation $progress $RoundObject "FABLE")) { return $false }
            if (-not (Test-ProgressVerdictComplete $progress $verdict)) { return $false }

            # Recompute the protected Round contract on every canonical/reconcile
            # decision. MarkFinalAuditEvidenceVerified checked this once, but the
            # durable state may be tampered or corrupted after that marker was set.
            $durableContractSha = ([string]$RoundObject.protected_round_contract_sha256).Trim().ToLowerInvariant()
            if ($durableContractSha -notmatch '^[0-9a-f]{64}$') { return $false }
            if (-not $CycleObject) { return $false }
            $currentContractSha = Get-ProtectedRoundContractSha256 $CycleObject $RoundObject
            if ($currentContractSha -ne $durableContractSha) { return $false }

            # A Fable COMPLETE checkpoint is necessary but not sufficient. The
            # workflow must first prove that Fable preserved the protected
            # Opus/controller evidence surface and the byte-for-byte Opus
            # UAT_REPORT prefix. Only that trusted post-audit gate may set this
            # durable marker. Without it, Prepare/Reconcile must resume the
            # same Round so those gates can run instead of silently completing.
            if ([string]$RoundObject.final_audit_evidence_verified -ne "true") { return $false }
            if ([string]$RoundObject.final_audit_evidence_verified_verdict -ne $verdict) { return $false }
            $protected = ([string]$RoundObject.protected_evidence_sha256).Trim().ToLowerInvariant()
            $verifiedProtected = ([string]$RoundObject.final_audit_evidence_verified_protected_sha256).Trim().ToLowerInvariant()
            if ($protected -notmatch '^[0-9a-f]{64}$' -or $verifiedProtected -ne $protected) { return $false }
            return $true
        }

        if ($verdict -ne $opusVerdict) { return $false }
        $progressPath = Join-Path $env:OUTDIR "verifier-state\opus\verifier-progress.json"
        if (-not (Test-Path $progressPath)) { return $false }
        try { $progress = [IO.File]::ReadAllText($progressPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json }
        catch { return $false }
        if ([string]$progress.verifier_stage -ne "OPUS") { return $false }
        if (-not (Test-ProgressMatchesAllocation $progress $RoundObject "OPUS")) { return $false }
        return (Test-ProgressVerdictComplete $progress $opusVerdict)
    }

    # v6/v7 compatibility is accepted only for a Round that was explicitly
    # created by Initialize-LegacyState from pre-v8 artifacts. Native staged
    # Rounds may never fall back to a single-verifier PASS.
    if ([string]$RoundObject.legacy_imported_from_pre_v8 -ne "true" -and $RoundObject.legacy_imported_from_pre_v8 -ne $true) { return $false }
    $legacyProgressPath = Join-Path $env:OUTDIR "verifier-state\verifier-progress.json"
    if (-not (Test-Path $legacyProgressPath)) { return $false }
    try { $legacy = [IO.File]::ReadAllText($legacyProgressPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json }
    catch { return $false }
    if (-not (Test-ProgressMatchesAllocation $legacy $RoundObject "OPUS")) { return $false }
    return (Test-ProgressVerdictComplete $legacy $verdict)
}


function Get-CanonicalCoreResults($CycleObject, $RoundObject, [string]$CanonicalVerdict) {
    if ($CanonicalVerdict -notin @("PASS", "REJECTED", "BLOCKED")) {
        throw "invalid canonical verifier verdict: '$CanonicalVerdict'"
    }

    $opusResultPath = Join-Path $env:OUTDIR "opus-result.txt"
    if (-not (Test-Path $opusResultPath)) {
        # Only the explicitly admitted pre-v8 import path may lack the staged
        # Opus result file. Preserve that historical classifier here; native
        # staged Rounds must derive their source from opus-result.txt.
        if ([string]$RoundObject.legacy_imported_from_pre_v8 -ne "true" -and $RoundObject.legacy_imported_from_pre_v8 -ne $true) {
            throw "canonical staged verifier result is missing opus-result.txt"
        }
        return Get-LegacyCoreResults $RoundObject $CanonicalVerdict
    }

    $opusVerdict = ([IO.File]::ReadAllText($opusResultPath, [System.Text.Encoding]::UTF8)).Trim()
    switch ($opusVerdict) {
        "REJECTED" {
            if ($CanonicalVerdict -ne "REJECTED") { throw "canonical Opus REJECTED disagrees with canonical verdict '$CanonicalVerdict'" }
            return [pscustomobject]@{ opus_result = "BUG_FOUND"; fable_result = "" }
        }
        "BLOCKED" {
            if ($CanonicalVerdict -ne "BLOCKED") { throw "canonical Opus BLOCKED disagrees with canonical verdict '$CanonicalVerdict'" }
            return [pscustomobject]@{ opus_result = ""; fable_result = "" }
        }
        "PRECHECK_PASS" {
            switch ($CanonicalVerdict) {
                "PASS" { return [pscustomobject]@{ opus_result = "NO_BUG"; fable_result = "FINAL_PASS" } }
                "REJECTED" { return [pscustomobject]@{ opus_result = "NO_BUG"; fable_result = "FINAL_REJECT" } }
                "BLOCKED" { return [pscustomobject]@{ opus_result = "NO_BUG"; fable_result = "" } }
            }
        }
        default { throw "invalid canonical Opus verdict: '$opusVerdict'" }
    }
    throw "unable to derive canonical Loop Core reviewer results"
}

function Write-CycleSummary($State, $CycleObject) {
    $cycleDir = Join-Path $CyclesDir ("cycle-{0}" -f [int]$CycleObject.cycle)
    New-Item -ItemType Directory -Force $cycleDir | Out-Null
    $path = Join-Path $cycleDir "cycle-summary.md"
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# Loop Cycle $($CycleObject.cycle) Summary")
    $lines.Add("")
    $lines.Add("Status: $($CycleObject.status)")
    $lines.Add("Maximum rounds: $($State.max_rounds_per_cycle)")
    $lines.Add("")
    $lines.Add("| Round | Action | Opus slot | Opus pair | Fable slot | Fable pair | Candidate | Verdict | Report |")
    $lines.Add("|---:|---|---:|---|---:|---|---|---|---|")
    foreach ($r in @($CycleObject.rounds | Sort-Object round)) {
        $candidate = [string]$r.candidate_sha
        if (-not $candidate) { $candidate = "-" }
        $report = [string]$r.report_path
        if (-not $report) { $report = "-" }
        $roundVerdict = [string]$r.verdict
        if (-not $roundVerdict) { $roundVerdict = "-" }
        $periodPair = "$($r.uat_period_primary)/$($r.uat_period_secondary)"
        $finalSlot = [string]$r.final_audit_uat_period_slot
        if (-not $finalSlot) { $finalSlot = "-" }
        $finalPair = "-"
        if ([string]$r.final_audit_uat_period_primary) { $finalPair = "$($r.final_audit_uat_period_primary)/$($r.final_audit_uat_period_secondary)" }
        $lines.Add("| $($r.round) | $($r.action) | $($r.uat_period_slot) | $periodPair | $finalSlot | $finalPair | $candidate | $roundVerdict | $report |")
    }
    Write-Utf8NoBom $path (($lines -join "`n") + "`n")
    return $path
}

function Archive-Round($State, $CycleObject, $RoundObject, [string]$RoundVerdict) {
    $roundDir = Join-Path $CyclesDir ("cycle-{0}\round-{1}" -f [int]$CycleObject.cycle, [int]$RoundObject.round)
    New-Item -ItemType Directory -Force $roundDir | Out-Null

    $reportSource = Join-Path $env:OUTDIR "UAT_REPORT.md"
    $resultSource = Join-Path $env:OUTDIR "uat-result.txt"
    if (-not (Test-Path $reportSource)) { throw "UAT_REPORT.md missing; cannot complete round" }
    if (-not (Test-Path $resultSource)) { throw "uat-result.txt missing; cannot complete round" }

    $actual = Get-CanonicalVerdict
    if ($actual -ne $RoundVerdict) { throw "canonical verdict '$actual' does not match requested verdict '$RoundVerdict'" }

    Copy-Item -Force $reportSource (Join-Path $roundDir "UAT_REPORT.md")
    Copy-Item -Force $resultSource (Join-Path $roundDir "uat-result.txt")
    Write-Utf8NoBom (Join-Path $roundDir "candidate-sha.txt") ([string]$RoundObject.candidate_sha + "`n")

    foreach ($name in @("opus-result.txt", "opus-core-result.txt", "fable-core-result.txt", "codex-final.txt", "IMPLEMENTATION_HANDOFF.md")) {
        $src = Join-Path $env:OUTDIR $name
        if (Test-Path $src) { Copy-Item -Force $src (Join-Path $roundDir $name) }
    }

    $verifierState = Join-Path $env:OUTDIR "verifier-state"
    if (Test-Path $verifierState) {
        $dst = Join-Path $roundDir "verifier-state"
        if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
        Copy-Item -Recurse -Force $verifierState $dst
    }

    $summary = [pscustomobject][ordered]@{
        schema_version = 1
        cycle = [int]$CycleObject.cycle
        round = [int]$RoundObject.round
        action = [string]$RoundObject.action
        candidate_sha = [string]$RoundObject.candidate_sha
        uat_period_slot = [int]$RoundObject.uat_period_slot
        uat_period_primary = [int]$RoundObject.uat_period_primary
        uat_period_secondary = [int]$RoundObject.uat_period_secondary
        uat_period_pool_sha256 = [string]$RoundObject.uat_period_pool_sha256
        retired_uat_period_allocations = @($RoundObject.retired_uat_period_allocations)
        final_audit_uat_period_slot = [string]$RoundObject.final_audit_uat_period_slot
        final_audit_uat_period_primary = [string]$RoundObject.final_audit_uat_period_primary
        final_audit_uat_period_secondary = [string]$RoundObject.final_audit_uat_period_secondary
        final_audit_uat_period_pool_sha256 = [string]$RoundObject.final_audit_uat_period_pool_sha256
        master_agents_sha256 = [string]$RoundObject.master_agents_sha256
        opus_report_sha256 = [string]$RoundObject.opus_report_sha256
        opus_report_length = [string]$RoundObject.opus_report_length
        uat_write_authorization_opus = $RoundObject.uat_write_authorization_opus
        uat_write_authorization_fable = $RoundObject.uat_write_authorization_fable
        uat_write_authorization_history = @($RoundObject.uat_write_authorization_history)
        verdict = $RoundVerdict
        opus_result = [string]$RoundObject.opus_result
        fable_result = [string]$RoundObject.fable_result
        findings_source = [string]$RoundObject.findings_source
        findings_ref = [string]$RoundObject.findings_ref
        produced_findings_source = [string]$RoundObject.produced_findings_source
        produced_findings_ref = [string]$RoundObject.produced_findings_ref
        report_path = (Join-Path $roundDir "UAT_REPORT.md")
        completed_at = Utc-Now
        github_run_id = $env:GITHUB_RUN_ID
        github_run_attempt = $env:GITHUB_RUN_ATTEMPT
    }
    Write-Utf8NoBom (Join-Path $roundDir "round-summary.json") (($summary | ConvertTo-Json -Depth 20) + "`n")
    return (Join-Path $roundDir "UAT_REPORT.md")
}

function Complete-RoundInternal($State, $CycleObject, $RoundObject, [string]$RoundVerdict, [string]$OpusCoreResult, [string]$FableCoreResult) {
    if (-not $RoundObject.candidate_sha) { throw "round has no candidate SHA" }

    # This function is a transition sink, not a reviewer-source classifier.
    # Callers must derive typed results before entering the state machine.
    # A canonical BLOCKED result may intentionally leave Opus/Fable results empty;
    # empty therefore must never mean "fall back to legacy classification" here.

    if ($RoundVerdict -ne "BLOCKED" -and $OpusCoreResult -notin @("NO_BUG", "BUG_FOUND")) { throw "invalid normalized Opus result: '$OpusCoreResult'" }
    if ($RoundVerdict -eq "BLOCKED" -and $OpusCoreResult -and $OpusCoreResult -ne "NO_BUG") { throw "BLOCKED may carry only prior Opus NO_BUG, never a third reviewer result" }
    if ($FableCoreResult -and $FableCoreResult -notin @("FINAL_PASS", "FINAL_REJECT")) { throw "invalid normalized Fable result: '$FableCoreResult'" }

    if ($RoundVerdict -eq "PASS" -and ($OpusCoreResult -ne "NO_BUG" -or $FableCoreResult -ne "FINAL_PASS")) {
        throw "legacy PASS must map to NO_BUG + FINAL_PASS"
    }
    if ($RoundVerdict -eq "REJECTED") {
        $validReject = ($OpusCoreResult -eq "BUG_FOUND" -and -not $FableCoreResult) -or ($OpusCoreResult -eq "NO_BUG" -and $FableCoreResult -eq "FINAL_REJECT")
        if (-not $validReject) { throw "legacy REJECTED must map to BUG_FOUND or NO_BUG + FINAL_REJECT" }
    }

    Ensure-Property $RoundObject "opus_result" $(if ($OpusCoreResult) { $OpusCoreResult } else { $null })
    Ensure-Property $RoundObject "fable_result" $(if ($FableCoreResult) { $FableCoreResult } else { $null })

    # Round.findings_source/findings_ref describe the report consumed by Codex
    # when this Round began.  Keep that provenance immutable.  Reviewer findings
    # produced by this Round are recorded separately and then promoted to the
    # state/cycle cursor for the next automatic Round or manual next Cycle.
    $producedFindingsSource = ""
    if ($OpusCoreResult -eq "BUG_FOUND") { $producedFindingsSource = "OPUS" }
    elseif ($OpusCoreResult -eq "NO_BUG" -and $FableCoreResult -eq "FINAL_REJECT") { $producedFindingsSource = "FABLE" }
    Ensure-Property $RoundObject "produced_findings_source" $(if ($producedFindingsSource) { $producedFindingsSource } else { $null })
    $expectedProducedFindingsRef = ""
    if ($producedFindingsSource) {
        $expectedProducedFindingsRef = Join-Path $CyclesDir ("cycle-{0}\round-{1}\UAT_REPORT.md" -f [int]$CycleObject.cycle, [int]$RoundObject.round)
    }
    Ensure-Property $RoundObject "produced_findings_ref" $(if ($expectedProducedFindingsRef) { $expectedProducedFindingsRef } else { $null })

    $reportPath = Archive-Round $State $CycleObject $RoundObject $RoundVerdict
    if ($producedFindingsSource) { Ensure-Property $RoundObject "produced_findings_ref" $reportPath }

    Ensure-Property $RoundObject "phase" "COMPLETE"
    Ensure-Property $RoundObject "verdict" $RoundVerdict
    Ensure-Property $RoundObject "report_path" $reportPath
    Ensure-Property $RoundObject "completed_at" (Utc-Now)
    Ensure-Property $State "current_candidate_sha" ([string]$RoundObject.candidate_sha)
    Ensure-Property $CycleObject "current_candidate_sha" ([string]$RoundObject.candidate_sha)
    Ensure-Property $State "opus_result" $(if ($OpusCoreResult) { $OpusCoreResult } else { $null })
    Ensure-Property $State "fable_result" $(if ($FableCoreResult) { $FableCoreResult } else { $null })

    if ($RoundVerdict -eq "BLOCKED") {
        Ensure-Property $CycleObject "status" "BLOCKED"
        Ensure-Property $State "status" "BLOCKED"
        Ensure-Property $State "stage" $(if ($OpusCoreResult -eq "NO_BUG") { "FABLE_FINAL_REVIEW" } else { "OPUS_REVIEW" })
        Ensure-Property $State "pause_reason" $null
        Ensure-Property $State "current_round" ([int]$RoundObject.round)
    }
    elseif ($OpusCoreResult -eq "BUG_FOUND") {
        Ensure-Property $RoundObject "produced_findings_source" "OPUS"
        Ensure-Property $RoundObject "produced_findings_ref" $reportPath
        Ensure-Property $State "findings_source" "OPUS"
        Ensure-Property $State "findings_ref" $reportPath
        Ensure-Property $CycleObject "findings_source" "OPUS"
        Ensure-Property $CycleObject "findings_ref" $reportPath
        if ([int]$RoundObject.round -ge [int]$State.max_rounds_per_cycle) {
            Ensure-Property $CycleObject "status" "PAUSED_AWAITING_USER"
            Ensure-Property $State "status" "PAUSED_AWAITING_USER"
            Ensure-Property $State "stage" "PAUSED_AWAITING_USER"
            Ensure-Property $State "pause_reason" "OPUS_ROUND_LIMIT"
            Ensure-Property $State "current_round" ([int]$RoundObject.round)
            Write-CycleSummary $State $CycleObject | Out-Null
        }
        else {
            Ensure-Property $CycleObject "status" "RUNNING"
            Ensure-Property $State "status" "RUNNING"
            Ensure-Property $State "stage" "CODEX_REWORK"
            Ensure-Property $State "pause_reason" $null
            Ensure-Property $State "current_round" ([int]$RoundObject.round + 1)
        }
    }
    elseif ($OpusCoreResult -eq "NO_BUG" -and $FableCoreResult -eq "FINAL_PASS") {
        Ensure-Property $CycleObject "status" "COMPLETED"
        Ensure-Property $CycleObject "completed_at" (Utc-Now)
        Ensure-Property $State "status" "COMPLETED"
        Ensure-Property $State "stage" "COMPLETED"
        Ensure-Property $State "pause_reason" $null
        Ensure-Property $State "findings_source" $null
        Ensure-Property $State "findings_ref" $null
        # State/Cycle findings_* are forward cursors, not the durable audit log.
        # FINAL_PASS has no next Round/Cycle consumer, so clear both levels at
        # the write boundary. Round consumed/produced findings retain audit history.
        Ensure-Property $CycleObject "findings_source" $null
        Ensure-Property $CycleObject "findings_ref" $null
        Ensure-Property $State "current_round" ([int]$RoundObject.round)
        Write-CycleSummary $State $CycleObject | Out-Null
    }
    elseif ($OpusCoreResult -eq "NO_BUG" -and $FableCoreResult -eq "FINAL_REJECT") {
        Ensure-Property $RoundObject "produced_findings_source" "FABLE"
        Ensure-Property $RoundObject "produced_findings_ref" $reportPath
        Ensure-Property $State "findings_source" "FABLE"
        Ensure-Property $State "findings_ref" $reportPath
        Ensure-Property $CycleObject "findings_source" "FABLE"
        Ensure-Property $CycleObject "findings_ref" $reportPath
        Ensure-Property $CycleObject "status" "PAUSED_AWAITING_USER"
        Ensure-Property $State "status" "PAUSED_AWAITING_USER"
        Ensure-Property $State "stage" "PAUSED_AWAITING_USER"
        Ensure-Property $State "pause_reason" "FABLE_FINAL_REJECT"
        Ensure-Property $State "current_round" ([int]$RoundObject.round)
        Write-CycleSummary $State $CycleObject | Out-Null
    }
    else {
        throw "unsupported Loop Core transition: opus=$OpusCoreResult fable=$FableCoreResult legacy=$RoundVerdict"
    }

    Save-State $State
    return $reportPath
}

function Reconcile-State($State) {
    if (-not $State) { return $null }
    $cycleObject = Get-Cycle $State ([int]$State.current_cycle)
    if (-not $cycleObject) { throw "current cycle is missing from loop state" }
    $roundObject = Get-Round $cycleObject ([int]$State.current_round)
    if (-not $roundObject) { return $State }

    if ([string]$roundObject.phase -eq "PRODUCING" -and -not $roundObject.candidate_sha) {
        $pushedPath = Join-Path $env:OUTDIR "pushed-sha.txt"
        $local = (git -C $env:WORKTREE rev-parse HEAD).Trim().ToLowerInvariant()
        if ($LASTEXITCODE -ne 0) { throw "git rev-parse failed while reconciling producer state" }

        if (Test-Path $pushedPath) {
            $candidate = ([IO.File]::ReadAllText($pushedPath, [System.Text.Encoding]::UTF8)).Trim()
            if ($candidate -notmatch '^[0-9a-fA-F]{40}$') {
                throw "pushed-sha.txt exists but contains an invalid SHA; refusing to delete or reuse the recovery pointer"
            }
            $candidate = $candidate.ToLowerInvariant()

            $remoteLine = git -C $env:WORKTREE ls-remote $env:SSH_URL "refs/heads/$env:BRANCH"
            if ($LASTEXITCODE -ne 0) {
                throw "pushed-sha.txt exists but remote verification failed; refusing to delete or reuse the recovery pointer. Restore GitHub/SSH connectivity and dispatch loop-engine.yml with run_mode=auto again."
            }
            $remoteParts = @($remoteLine -split '\s+' | Where-Object { $_ })
            if ($remoteParts.Count -lt 1) {
                throw "pushed-sha.txt exists but the candidate branch is missing on remote; refusing to delete or reuse the recovery pointer"
            }
            $remote = $remoteParts[0].Trim().ToLowerInvariant()
            if ($candidate -ne $local -or $candidate -ne $remote) {
                throw "pushed-sha.txt does not match local/remote candidate: pointer=$candidate local=$local remote=$remote. Refusing automatic recovery."
            }

            Ensure-Property $roundObject "candidate_sha" $candidate
            Ensure-Property $roundObject "phase" "VERIFYING"
            Ensure-Property $cycleObject "current_candidate_sha" $candidate
            Ensure-Property $State "current_candidate_sha" $candidate
            Ensure-Property $State "stage" "OPUS_REVIEW"
            Ensure-Property $State "status" "RUNNING"
            Write-Host "[RECONCILE] recovered published candidate $candidate for cycle $($cycleObject.cycle) round $($roundObject.round)"
            Save-State $State
        }
        else {
            $producerBase = ([string]$roundObject.producer_base_sha).Trim().ToLowerInvariant()
            if ($producerBase -and $local -ne $producerBase) {
                $remoteLine = git -C $env:WORKTREE ls-remote $env:SSH_URL "refs/heads/$env:BRANCH"
                if ($LASTEXITCODE -ne 0) {
                    throw "[RECOVERY-BLOCKED] local HEAD advanced beyond producer_base_sha ($producerBase -> $local), but remote verification failed. Do not rerun Codex. Restore connectivity, then dispatch loop-engine.yml with run_mode=auto."
                }
                $remoteParts = @($remoteLine -split '\s+' | Where-Object { $_ })
                $remote = ""
                if ($remoteParts.Count -gt 0) { $remote = $remoteParts[0].Trim().ToLowerInvariant() }

                if ($remote -eq $local) {
                    Write-Utf8NoBom $pushedPath ($local + "`n")
                    Ensure-Property $roundObject "candidate_sha" $local
                    Ensure-Property $roundObject "phase" "VERIFYING"
                    Ensure-Property $cycleObject "current_candidate_sha" $local
                    Ensure-Property $State "current_candidate_sha" $local
                    Ensure-Property $State "stage" "OPUS_REVIEW"
                    Ensure-Property $State "status" "RUNNING"
                    Write-Host "[RECONCILE] recovered candidate after commit/push completed before durable pointer/state update: $local"
                    Save-State $State
                }
                else {
                    throw "[RECOVERY-BLOCKED] local HEAD advanced beyond producer_base_sha ($producerBase -> $local) but there is no durable pushed-sha.txt and remote candidate is '$remote'. This usually means commit succeeded but push failed. Do not rerun Codex. Manually push HEAD to the candidate branch, verify remote SHA equals local HEAD, recreate .loop-output\pushed-sha.txt with that SHA, then dispatch loop-engine.yml with run_mode=auto."
                }
            }
        }
    }

    if ([string]$roundObject.phase -eq "VERIFYING" -and (Test-CanonicalVerifierComplete $cycleObject $roundObject)) {
        $recoveredVerdict = Get-CanonicalVerdict
        Write-Host "[RECONCILE] verifier final evidence found for cycle $($cycleObject.cycle) round $($roundObject.round): $recoveredVerdict"
        $core = Get-CanonicalCoreResults $cycleObject $roundObject $recoveredVerdict
        Complete-RoundInternal $State $cycleObject $roundObject $recoveredVerdict ([string]$core.opus_result) ([string]$core.fable_result) | Out-Null
    }

    return $State
}

function Initialize-LegacyState() {
    $state = New-State
    $cycleObject = Get-Cycle $state 1
    $pushedPath = Join-Path $env:OUTDIR "pushed-sha.txt"
    $reportPath = Join-Path $env:OUTDIR "UAT_REPORT.md"
    $resultPath = Join-Path $env:OUTDIR "uat-result.txt"
    $progressPath = Join-Path $env:OUTDIR "verifier-state\verifier-progress.json"

    if (-not (Test-Path $pushedPath)) {
        if ((Test-Path $reportPath) -or (Test-Path $resultPath) -or (Test-Path $progressPath)) {
            throw "legacy verifier artifacts exist but pushed-sha.txt is missing; refusing to guess the candidate"
        }
        Save-State $state
        Write-Host "[LOOP] initialized a fresh cycle 1"
        return $state
    }

    $candidate = ([IO.File]::ReadAllText($pushedPath, [System.Text.Encoding]::UTF8)).Trim()
    $candidate = Validate-Candidate $candidate
    $local = (git -C $env:WORKTREE rev-parse HEAD).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0) { throw "git rev-parse failed while importing legacy candidate" }
    $remoteLine = git -C $env:WORKTREE ls-remote $env:SSH_URL "refs/heads/$env:BRANCH"
    if ($LASTEXITCODE -ne 0) { throw "git ls-remote failed while importing legacy candidate" }
    $remoteParts = @($remoteLine -split '\s+' | Where-Object { $_ })
    if ($remoteParts.Count -lt 1) { throw "candidate branch missing while importing legacy state" }
    $remote = $remoteParts[0].Trim().ToLowerInvariant()
    if ($candidate -ne $local -or $candidate -ne $remote) {
        throw "legacy pushed-sha does not match local/remote candidate; refusing automatic import"
    }

    $roundObject = [pscustomobject][ordered]@{
        round = 1
        action = "construct"
        phase = "VERIFYING"
        producer_base_sha = $null
        previous_report = ""
        candidate_sha = $candidate
        verdict = $null
        report_path = $null
        started_at = Utc-Now
        completed_at = $null
        last_run_id = $env:GITHUB_RUN_ID
        last_run_attempt = $env:GITHUB_RUN_ATTEMPT
        legacy_imported_from_pre_v8 = $true
    }
    $cycleObject.rounds = @($roundObject)
    Ensure-RoundPeriodAllocation $state $roundObject | Out-Null
    Bind-LegacyVerifierPeriodMetadata $roundObject
    Ensure-Property $state "current_round" 1
    Ensure-Property $state "status" "RUNNING"
    Ensure-Property $state "stage" "OPUS_REVIEW"
    Ensure-Property $state "current_candidate_sha" $candidate
    Ensure-Property $cycleObject "current_candidate_sha" $candidate
    Save-State $state
    Write-Host "[LEGACY-IMPORT] imported existing candidate as cycle 1 round 1: $candidate"

    if (Test-CanonicalVerifierComplete $cycleObject $roundObject) {
        $legacyVerdict = Get-CanonicalVerdict
        Write-Host "[LEGACY-IMPORT] existing verifier final result found: $legacyVerdict"
        $core = Get-LegacyCoreResults $roundObject $legacyVerdict
        Complete-RoundInternal $state $cycleObject $roundObject $legacyVerdict ([string]$core.opus_result) ([string]$core.fable_result) | Out-Null
    }
    else {
        Write-Host "[LEGACY-IMPORT] verifier is incomplete; auto mode will resume cycle 1 round 1"
    }
    return $state
}

function Prepare-Loop([string]$Mode) {
    New-Item -ItemType Directory -Force $env:OUTDIR | Out-Null
    New-Item -ItemType Directory -Force $CyclesDir | Out-Null

    # `new-cycle` is retained only as a compatibility alias for pre-v21 callers.
    # The public/manual governance action is workflow_dispatch run_mode=next-cycle.
    if ($Mode -eq "new-cycle") {
        Write-Warning "run_mode=new-cycle is deprecated; treating it as run_mode=next-cycle"
        $Mode = "next-cycle"
    }

    $state = Load-State
    if (-not $state) {
        if ($Mode -eq "next-cycle") { throw "next-cycle requires an existing PAUSED_AWAITING_USER Loop; use auto for a new WORK" }
        $state = Initialize-LegacyState
    }
    $state = Upgrade-StatePeriodSchema $state
    $state = Upgrade-CoreStateSchema $state
    $state = Reconcile-State $state
    $state = Upgrade-CoreStateSchema $state

    $cycleObject = Get-Cycle $state ([int]$state.current_cycle)
    if (-not $cycleObject) { throw "current cycle $($state.current_cycle) is missing" }

    $workflowBranch = [string]$env:BRANCH
    $ledgerBranch = [string]$state.candidate_branch
    $actualBranch = Get-WorktreeBranch
    if ($ledgerBranch -ne $workflowBranch -or $actualBranch -ne $ledgerBranch) {
        throw "Candidate Branch drift detected: ledger=$ledgerBranch workflow=$workflowBranch worktree=$actualBranch"
    }

    if ($Mode -eq "next-cycle") {
        if ([string]$state.status -ne "PAUSED_AWAITING_USER") {
            throw "next-cycle is allowed only after PAUSED_AWAITING_USER; current status is $($state.status)"
        }
        $pauseReason = [string]$state.pause_reason
        if ($pauseReason -notin @("OPUS_ROUND_LIMIT", "FABLE_FINAL_REJECT")) {
            throw "next-cycle is not allowed for pause_reason '$pauseReason'"
        }

        $findingsSource = [string]$state.findings_source
        $findingsRef = [string]$state.findings_ref
        if ($pauseReason -eq "OPUS_ROUND_LIMIT" -and $findingsSource -ne "OPUS") {
            throw "OPUS_ROUND_LIMIT next cycle requires OPUS findings"
        }
        if ($pauseReason -eq "FABLE_FINAL_REJECT" -and $findingsSource -ne "FABLE") {
            throw "FABLE_FINAL_REJECT next cycle requires FABLE findings"
        }
        if (-not $findingsRef -or -not (Test-Path $findingsRef)) {
            throw "next-cycle findings are missing: $findingsRef"
        }

        $previousCandidate = Validate-Candidate ([string]$state.current_candidate_sha)
        $worktreeHead = Get-WorktreeHead
        if ($worktreeHead -ne $previousCandidate) {
            throw "next-cycle must continue current Candidate HEAD: ledger=$previousCandidate worktree=$worktreeHead"
        }

        $newCycleNumber = [int]$state.current_cycle + 1
        $newCycle = New-CycleObject $newCycleNumber $findingsRef $previousCandidate $ledgerBranch $findingsSource $findingsRef
        $state.cycles = @($state.cycles) + @($newCycle)
        Ensure-Property $state "current_cycle" $newCycleNumber
        Ensure-Property $state "current_round" 1
        Ensure-Property $state "current_candidate_sha" $previousCandidate
        Ensure-Property $state "status" "RUNNING"
        Ensure-Property $state "stage" "CODEX_REWORK"
        Ensure-Property $state "pause_reason" $null
        Ensure-Property $state "opus_result" $null
        Ensure-Property $state "fable_result" $null
        # Preserve the paused reviewer findings as the explicit input to Cycle N+1 Codex.
        Ensure-Property $state "findings_source" $findingsSource
        Ensure-Property $state "findings_ref" $findingsRef
        Save-State $state
        $cycleObject = $newCycle
        Write-Host "[LOOP] manually opened cycle $newCycleNumber on Candidate Branch $ledgerBranch from SHA $previousCandidate using $findingsSource findings"
    }

    $startAction = "none"
    $startRound = [int]$state.current_round
    $previousReport = ""
    $findingsSourceOut = [string]$state.findings_source
    $findingsRefOut = [string]$state.findings_ref

    if ([string]$state.status -in @("COMPLETED", "PAUSED_AWAITING_USER")) {
        $startAction = "none"
    }
    elseif ([string]$state.status -eq "BLOCKED") {
        $currentRoundObject = Get-Round $cycleObject ([int]$state.current_round)
        if (-not $currentRoundObject -or -not $currentRoundObject.candidate_sha) { throw "BLOCKED state has no resumable candidate" }
        $startAction = "resume-verifier"
        $previousReport = [string]$currentRoundObject.previous_report
    }
    else {
        $currentRoundObject = Get-Round $cycleObject ([int]$state.current_round)
        if ($currentRoundObject) {
            if ([string]$currentRoundObject.phase -eq "VERIFYING") {
                $startAction = "resume-verifier"
                $previousReport = [string]$currentRoundObject.previous_report
            }
            elseif ([string]$currentRoundObject.phase -eq "PRODUCING") {
                $startAction = [string]$currentRoundObject.action
                $previousReport = [string]$currentRoundObject.previous_report
            }
            elseif ([string]$currentRoundObject.phase -eq "COMPLETE") {
                $opus = [string]$currentRoundObject.opus_result
                $fable = [string]$currentRoundObject.fable_result
                if ($fable -eq "FINAL_REJECT") {
                    Ensure-Property $cycleObject "status" "PAUSED_AWAITING_USER"
                    Ensure-Property $state "status" "PAUSED_AWAITING_USER"
                    Ensure-Property $state "stage" "PAUSED_AWAITING_USER"
                    Ensure-Property $state "pause_reason" "FABLE_FINAL_REJECT"
                    $startAction = "none"
                    Save-State $state
                }
                elseif ($opus -eq "BUG_FOUND") {
                    if ([int]$currentRoundObject.round -ge [int]$state.max_rounds_per_cycle) {
                        Ensure-Property $cycleObject "status" "PAUSED_AWAITING_USER"
                        Ensure-Property $state "status" "PAUSED_AWAITING_USER"
                        Ensure-Property $state "stage" "PAUSED_AWAITING_USER"
                        Ensure-Property $state "pause_reason" "OPUS_ROUND_LIMIT"
                        $startAction = "none"
                        Save-State $state
                    }
                    else {
                        $startRound = [int]$currentRoundObject.round + 1
                        Ensure-Property $state "current_round" $startRound
                        Ensure-Property $state "stage" "CODEX_REWORK"
                        $startAction = "rework"
                        $previousReport = [string]$currentRoundObject.report_path
                        $findingsSourceOut = "OPUS"
                        $findingsRefOut = $previousReport
                        Ensure-Property $state "findings_source" $findingsSourceOut
                        Ensure-Property $state "findings_ref" $findingsRefOut
                        Save-State $state
                    }
                }
                elseif ($opus -eq "NO_BUG" -and $fable -eq "FINAL_PASS") {
                    Ensure-Property $state "status" "COMPLETED"
                    Ensure-Property $state "stage" "COMPLETED"
                    $startAction = "none"
                    Save-State $state
                }
                elseif ([string]$currentRoundObject.verdict -eq "BLOCKED") {
                    $startAction = "resume-verifier"
                    $previousReport = [string]$currentRoundObject.previous_report
                }
                else {
                    throw "cannot prepare from completed round: opus=$opus fable=$fable legacy=$($currentRoundObject.verdict)"
                }
            }
            else {
                throw "cannot prepare from round phase '$($currentRoundObject.phase)' verdict '$($currentRoundObject.verdict)'"
            }
        }
        else {
            if ($startRound -eq 1 -and [int]$state.current_cycle -eq 1) {
                $startAction = "construct"
            }
            elseif ($startRound -eq 1 -and [int]$state.current_cycle -gt 1) {
                $startAction = "rework"
                $previousReport = [string]$cycleObject.findings_ref
                if (-not $previousReport) { $previousReport = [string]$cycleObject.previous_cycle_report }
                $findingsSourceOut = [string]$cycleObject.findings_source
                $findingsRefOut = $previousReport
            }
            else {
                $priorRound = Get-Round $cycleObject ($startRound - 1)
                if (-not $priorRound -or [string]$priorRound.opus_result -ne "BUG_FOUND") { throw "round $startRound has no prior Opus BUG_FOUND report" }
                $startAction = "rework"
                $previousReport = [string]$priorRound.report_path
                $findingsSourceOut = "OPUS"
                $findingsRefOut = $previousReport
            }
        }
    }

    if ($startAction -eq "construct") {
        Ensure-Property $state "stage" "CODEX_PRODUCE"
        Ensure-Property $state "findings_source" $null
        Ensure-Property $state "findings_ref" $null
        Save-State $state
    }
    elseif ($startAction -eq "rework") {
        Ensure-Property $state "stage" "CODEX_REWORK"
        Ensure-Property $state "findings_source" $findingsSourceOut
        Ensure-Property $state "findings_ref" $findingsRefOut
        Save-State $state
    }

    Write-Host "=== LOOP PREPARE ==="
    Write-Host "mode=$Mode"
    Write-Host "cycle=$($state.current_cycle)"
    Write-Host "start_round=$startRound"
    Write-Host "start_action=$startAction"
    Write-Host "status=$($state.status)"
    Write-Host "candidate_branch=$($state.candidate_branch)"
    Write-Host "cycle_start_sha=$($cycleObject.cycle_start_sha)"
    Write-Host "current_candidate_sha=$($state.current_candidate_sha)"
    if ($previousReport) { Write-Host "previous_report=$previousReport" }
    if ($findingsSourceOut) { Write-Host "findings_source=$findingsSourceOut" }

    Write-StepOutput "cycle" ([string]$state.current_cycle)
    Write-StepOutput "start_round" ([string]$startRound)
    Write-StepOutput "start_action" $startAction
    Write-StepOutput "previous_report" $previousReport
    Write-StepOutput "findings_source" $findingsSourceOut
    Write-StepOutput "findings_ref" $findingsRefOut
    Write-StepOutput "candidate_branch" ([string]$state.candidate_branch)
    Write-StepOutput "cycle_start_sha" ([string]$cycleObject.cycle_start_sha)
    Write-StepOutput "current_candidate_sha" ([string]$state.current_candidate_sha)
    Write-StepOutput "state_status" ([string]$state.status)
}

function Begin-Round([int]$CycleNumber, [int]$RoundNumber, [string]$ActionName, [string]$PriorReport) {
    $masterAgentsHash = ([string]$env:LOOP_MASTER_AGENTS_SHA256).ToLowerInvariant()
    if ($masterAgentsHash -notmatch '^[0-9a-f]{64}$') { throw "valid LOOP_MASTER_AGENTS_SHA256 is required before BeginRound" }

    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $state = Upgrade-CoreStateSchema $state
    if ([int]$state.current_cycle -ne $CycleNumber) { throw "cycle mismatch: state=$($state.current_cycle), requested=$CycleNumber" }
    if ($RoundNumber -lt 1 -or $RoundNumber -gt [int]$state.max_rounds_per_cycle) { throw "invalid round $RoundNumber" }
    if ([string]$state.candidate_branch -ne [string]$env:BRANCH) { throw "Candidate Branch changed within WORK" }

    $cycleObject = Get-Cycle $state $CycleNumber
    if (-not $cycleObject) { throw "cycle $CycleNumber missing" }
    $roundObject = Get-Round $cycleObject $RoundNumber

    if (-not $roundObject) {
        $baseSha = Get-WorktreeHead
        if ([string]$cycleObject.current_candidate_sha -and $baseSha -ne ([string]$cycleObject.current_candidate_sha).ToLowerInvariant()) {
            throw "round must start from current Candidate SHA: cycle=$($cycleObject.current_candidate_sha) worktree=$baseSha"
        }
        $phase = "PRODUCING"
        if ($ActionName -eq "resume-verifier") { $phase = "VERIFYING" }
        $roundObject = [pscustomobject][ordered]@{
            round = $RoundNumber
            action = $ActionName
            phase = $phase
            producer_base_sha = $baseSha
            previous_report = $PriorReport
            findings_source = [string]$state.findings_source
            findings_ref = $(if ($PriorReport) { $PriorReport } else { [string]$state.findings_ref })
            produced_findings_source = $null
            produced_findings_ref = $null
            master_agents_sha256 = $masterAgentsHash
            candidate_sha = $null
            opus_result = $null
            fable_result = $null
            verdict = $null
            report_path = $null
            started_at = Utc-Now
            completed_at = $null
            last_run_id = $env:GITHUB_RUN_ID
            last_run_attempt = $env:GITHUB_RUN_ATTEMPT
        }
        $cycleObject.rounds = @($cycleObject.rounds) + @($roundObject)
    }
    else {
        $existingMasterAgentsHash = [string]$roundObject.master_agents_sha256
        if ($existingMasterAgentsHash) {
            if ($existingMasterAgentsHash.ToLowerInvariant() -ne $masterAgentsHash) {
                throw "pinned master AGENTS snapshot hash differs from durable round ledger: ledger=$existingMasterAgentsHash runtime=$masterAgentsHash"
            }
        }
        else { Ensure-Property $roundObject "master_agents_sha256" $masterAgentsHash }

        if ($ActionName -eq "resume-verifier") {
            if (-not $roundObject.candidate_sha) { throw "cannot resume verifier without candidate SHA" }
            $phaseNow = [string]$roundObject.phase
            $verdictNow = [string]$roundObject.verdict
            $allowedResume = ($phaseNow -eq "VERIFYING") -or ($phaseNow -eq "COMPLETE" -and $verdictNow -eq "BLOCKED")
            if (-not $allowedResume) {
                throw "resume-verifier is allowed only for phase VERIFYING or COMPLETE+BLOCKED; current phase=$phaseNow verdict=$verdictNow. Do not use GitHub Re-run failed jobs for a durable Loop Engine round; dispatch loop-engine.yml again with run_mode=auto so GitHub Actions Controller can reconcile the durable state."
            }
            Ensure-Property $roundObject "phase" "VERIFYING"
            if ($phaseNow -eq "COMPLETE" -and $verdictNow -eq "BLOCKED") {
                Ensure-Property $roundObject "verdict" $null
                Ensure-Property $roundObject "report_path" $null
                Ensure-Property $roundObject "completed_at" $null
                Ensure-Property $roundObject "final_audit_evidence_verified" $null
                Ensure-Property $roundObject "final_audit_evidence_verified_verdict" $null
                Ensure-Property $roundObject "final_audit_evidence_verified_protected_sha256" $null
                Ensure-Property $roundObject "final_audit_evidence_verified_at" $null
            }
        }
        elseif ([string]$roundObject.phase -ne "PRODUCING") {
            throw "cannot run producer for an existing round in phase $($roundObject.phase). Do not use GitHub Re-run failed jobs for a durable Loop Engine round; dispatch loop-engine.yml again with run_mode=auto so the Controller selects the safe continuation action."
        }
        Ensure-Property $roundObject "last_run_id" $env:GITHUB_RUN_ID
        Ensure-Property $roundObject "last_run_attempt" $env:GITHUB_RUN_ATTEMPT
    }

    Ensure-RoundPeriodAllocation $state $roundObject | Out-Null
    Assert-NoDuplicateRoundPeriodAllocations $state

    Ensure-Property $cycleObject "status" "RUNNING"
    Ensure-Property $state "status" "RUNNING"
    Ensure-Property $state "current_round" $RoundNumber
    Ensure-Property $state "pause_reason" $null
    if ($ActionName -eq "construct") { Ensure-Property $state "stage" "CODEX_PRODUCE" }
    elseif ($ActionName -eq "rework") { Ensure-Property $state "stage" "CODEX_REWORK" }
    elseif ([string]$state.stage -notin @("OPUS_REVIEW", "FABLE_FINAL_REVIEW")) { Ensure-Property $state "stage" "OPUS_REVIEW" }

    if ($ActionName -ne "resume-verifier") {
        $legacyPublish = Join-Path $env:OUTDIR "pvam-work02-publish"
        Remove-PathFailClosed $legacyPublish
        foreach ($stageState in @(
            (Join-Path $env:OUTDIR "verifier-state\opus"),
            (Join-Path $env:OUTDIR "verifier-state\fable"),
            (Join-Path $env:OUTDIR "verifier-runtime\opus"),
            (Join-Path $env:OUTDIR "verifier-runtime\fable")
        )) { Remove-PathFailClosed $stageState }

        Remove-PathFailClosed (Join-Path $env:OUTDIR "pushed-sha.txt")
        Remove-PathFailClosed (Join-Path $env:OUTDIR "codex-final.txt")
        Remove-PathFailClosed (Join-Path $env:OUTDIR "IMPLEMENTATION_HANDOFF.md")
        Remove-PathFailClosed (Join-Path $env:OUTDIR "opus-result.txt")
        Remove-PathFailClosed (Join-Path $env:OUTDIR "opus-core-result.txt")
        Remove-PathFailClosed (Join-Path $env:OUTDIR "fable-core-result.txt")
        Remove-PathFailClosed (Join-Path $env:OUTDIR "uat-result.txt")
        Remove-PathFailClosed (Join-Path $env:OUTDIR "UAT_REPORT.md")
    }

    Save-State $state
    Export-RoundPeriodEnvironment $roundObject
    Write-Host "[ROUND-BEGIN] cycle=$CycleNumber round=$RoundNumber action=$ActionName phase=$($roundObject.phase) stage=$($state.stage) uat_period_slot=$($roundObject.uat_period_slot) periods=$($roundObject.uat_period_primary)/$($roundObject.uat_period_secondary)"
}

function Set-Candidate([int]$CycleNumber, [int]$RoundNumber, [string]$Sha) {
    $shaValue = Validate-Candidate $Sha
    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $cycleObject = Get-Cycle $state $CycleNumber
    $roundObject = Get-Round $cycleObject $RoundNumber
    if (-not $roundObject) { throw "round $CycleNumber/$RoundNumber is missing" }
    Ensure-Property $roundObject "candidate_sha" $shaValue
    Ensure-Property $roundObject "phase" "VERIFYING"
    Ensure-Property $cycleObject "current_candidate_sha" $shaValue
    Ensure-Property $state "current_candidate_sha" $shaValue
    Ensure-Property $state "stage" "OPUS_REVIEW"
    Ensure-Property $state "status" "RUNNING"
    Ensure-Property $state "pause_reason" $null
    Save-State $state
    Write-Host "[CANDIDATE] cycle=$CycleNumber round=$RoundNumber sha=$shaValue stage=OPUS_REVIEW"
}

function Rotate-LegacyVerifierPeriod([int]$CycleNumber, [int]$RoundNumber) {
    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $cycleObject = Get-Cycle $state $CycleNumber
    $roundObject = Get-Round $cycleObject $RoundNumber
    if (-not $roundObject) { throw "round $CycleNumber/$RoundNumber is missing" }
    if ([string]$roundObject.phase -ne "VERIFYING") {
        Export-RoundPeriodEnvironment $roundObject
        return
    }
    if (-not $roundObject.candidate_sha) { throw "cannot rotate legacy verifier UAT period without candidate SHA" }

    $legacyProgressPath = Join-Path $env:OUTDIR "verifier-state\verifier-progress.json"
    $opusProgressPath = Join-Path $env:OUTDIR "verifier-state\opus\verifier-progress.json"
    $opusResultPath = Join-Path $env:OUTDIR "opus-result.txt"

    # Once v8 Opus has started, this operation is a no-op. Same-stage resumes must
    # reuse the already-bound Opus pair rather than consuming a new pair.
    if ((Test-Path $opusProgressPath) -or (Test-Path $opusResultPath)) {
        Ensure-RoundPeriodAllocation $state $roundObject | Out-Null
        Export-RoundPeriodEnvironment $roundObject
        return
    }

    # No legacy direct verifier checkpoint means this is a native v8 round.
    if (-not (Test-Path $legacyProgressPath)) {
        Ensure-RoundPeriodAllocation $state $roundObject | Out-Null
        Export-RoundPeriodEnvironment $roundObject
        return
    }

    # A prior attempt may have atomically rotated the pair and then died before the
    # legacy checkpoint archive step. Do not rotate again.
    if ([string]$roundObject.v8_legacy_period_rotated -eq "true") {
        Ensure-RoundPeriodAllocation $state $roundObject | Out-Null
        Export-RoundPeriodEnvironment $roundObject
        Write-Host "[V8-PERIOD-MIGRATION] legacy verifier pair was already retired; reusing fresh Opus slot=$($roundObject.uat_period_slot)"
        return
    }

    Ensure-RoundPeriodAllocation $state $roundObject | Out-Null
    $retired = @($roundObject.retired_uat_period_allocations)
    $old = [pscustomobject][ordered]@{
        slot = [int]$roundObject.uat_period_slot
        primary = [int]$roundObject.uat_period_primary
        secondary = [int]$roundObject.uat_period_secondary
        pool_sha256 = [string]$roundObject.uat_period_pool_sha256
        reason = "legacy-v6-v7-incomplete-verifier-restarted-as-v8-opus"
        retired_at = Utc-Now
    }
    $retired = @($retired) + @($old)
    Ensure-Property $roundObject "retired_uat_period_allocations" @($retired)

    # Clear only the active Opus allocation. The retired allocation remains in the
    # global used-slot set, so it can never be silently reassigned.
    Ensure-Property $roundObject "uat_period_slot" $null
    Ensure-Property $roundObject "uat_period_primary" $null
    Ensure-Property $roundObject "uat_period_secondary" $null
    Ensure-Property $roundObject "uat_period_pool_sha256" $null
    Ensure-RoundPeriodAllocation $state $roundObject | Out-Null
    Ensure-Property $roundObject "v8_legacy_period_rotated" "true"
    Ensure-Property $roundObject "v8_legacy_period_rotated_at" (Utc-Now)
    Assert-NoDuplicateRoundPeriodAllocations $state
    Save-State $state
    Export-RoundPeriodEnvironment $roundObject
    Write-Host "[V8-PERIOD-MIGRATION] retired legacy slot=$($old.slot) periods=$($old.primary)/$($old.secondary); fresh Opus slot=$($roundObject.uat_period_slot) periods=$($roundObject.uat_period_primary)/$($roundObject.uat_period_secondary)"
}

function Allocate-FinalAuditPeriod([int]$CycleNumber, [int]$RoundNumber) {
    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $cycleObject = Get-Cycle $state $CycleNumber
    $roundObject = Get-Round $cycleObject $RoundNumber
    if (-not $roundObject) { throw "round $CycleNumber/$RoundNumber is missing" }
    if ([string]$roundObject.phase -ne "VERIFYING") { throw "Fable final-audit period can only be allocated while round is VERIFYING" }
    if (-not $roundObject.candidate_sha) { throw "cannot allocate Fable final-audit period without candidate SHA" }

    $opusResultPath = Join-Path $env:OUTDIR "opus-result.txt"
    $opusProgressPath = Join-Path $env:OUTDIR "verifier-state\opus\verifier-progress.json"
    if (-not (Test-Path $opusResultPath)) { throw "cannot allocate Fable final-audit period before opus-result.txt exists" }
    if (-not (Test-Path $opusProgressPath)) { throw "cannot allocate Fable final-audit period before durable Opus verifier progress exists" }
    $opusVerdict = ([IO.File]::ReadAllText($opusResultPath, [System.Text.Encoding]::UTF8)).Trim()
    if ($opusVerdict -ne "PRECHECK_PASS") { throw "Fable final audit requires Opus PRECHECK_PASS; actual=$opusVerdict" }
    try { $opusProgress = [IO.File]::ReadAllText($opusProgressPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json }
    catch { throw "Opus verifier-progress.json is invalid before Fable final audit: $($_.Exception.Message)" }
    if ([string]$opusProgress.verifier_stage -ne "OPUS" -or [string]$opusProgress.final_verdict -ne "PRECHECK_PASS" -or [string]$opusProgress.status -ne "COMPLETE") {
        throw "Fable final audit requires durable Opus COMPLETE/PRECHECK_PASS checkpoint"
    }
    if (-not (Test-ProgressMatchesAllocation $opusProgress $roundObject "OPUS")) {
        throw "Fable final audit requires Opus checkpoint to match the current candidate and Opus UAT allocation"
    }

    Ensure-FinalAuditPeriodAllocation $state $roundObject | Out-Null
    Assert-NoDuplicateRoundPeriodAllocations $state
    Ensure-Property $state "stage" "FABLE_FINAL_REVIEW"
    Ensure-Property $state "status" "RUNNING"
    Ensure-Property $state "pause_reason" $null
    Save-State $state
    Export-FinalAuditPeriodEnvironment $roundObject
    Write-Host "[FINAL-AUDIT-PERIOD] cycle=$CycleNumber round=$RoundNumber slot=$($roundObject.final_audit_uat_period_slot) periods=$($roundObject.final_audit_uat_period_primary)/$($roundObject.final_audit_uat_period_secondary)"
}

function Bind-OpusReportBaseline([int]$CycleNumber, [int]$RoundNumber, [string]$Sha256, [long]$ByteLength) {
    if ($Sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw "invalid Opus report SHA-256: '$Sha256'" }
    if ($ByteLength -le 0) { throw "invalid Opus report byte length: $ByteLength" }
    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $cycleObject = Get-Cycle $state $CycleNumber
    $roundObject = Get-Round $cycleObject $RoundNumber
    if (-not $roundObject) { throw "round $CycleNumber/$RoundNumber is missing" }
    if ([string]$roundObject.phase -ne "VERIFYING") { throw "Opus report baseline can only be bound while round is VERIFYING" }
    if (-not $roundObject.candidate_sha) { throw "cannot bind Opus report baseline without candidate SHA" }

    $normalized = $Sha256.ToLowerInvariant()
    $existingHash = [string]$roundObject.opus_report_sha256
    $existingLength = [string]$roundObject.opus_report_length
    if ($existingHash -and $existingHash.ToLowerInvariant() -ne $normalized) {
        throw "durable Opus report SHA-256 already differs: ledger=$existingHash requested=$normalized"
    }
    if ($existingLength -and [long]$roundObject.opus_report_length -ne $ByteLength) {
        throw "durable Opus report byte length already differs: ledger=$existingLength requested=$ByteLength"
    }
    Ensure-Property $roundObject "opus_report_sha256" $normalized
    Ensure-Property $roundObject "opus_report_length" $ByteLength
    Save-State $state
    Write-Host "[OPUS-REPORT-BASELINE] cycle=$CycleNumber round=$RoundNumber sha256=$normalized bytes=$ByteLength"
}

function Bind-ProtectedEvidenceBaseline([int]$CycleNumber, [int]$RoundNumber, [string]$Sha256) {
    if ($Sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw "invalid protected evidence SHA-256: '$Sha256'" }
    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $cycleObject = Get-Cycle $state $CycleNumber
    $roundObject = Get-Round $cycleObject $RoundNumber
    if (-not $roundObject) { throw "round $CycleNumber/$RoundNumber is missing" }
    if ([string]$roundObject.phase -ne "VERIFYING") { throw "protected evidence baseline can only be bound while round is VERIFYING" }
    if (-not $roundObject.candidate_sha) { throw "cannot bind protected evidence baseline without candidate SHA" }
    if (-not $roundObject.final_audit_uat_period_slot) { throw "cannot bind protected evidence baseline before Fable final-audit period allocation" }

    $normalized = $Sha256.ToLowerInvariant()
    $contractSha = Get-ProtectedRoundContractSha256 $cycleObject $roundObject
    $existingContractSha = [string]$roundObject.protected_round_contract_sha256
    if ($existingContractSha -and $existingContractSha.ToLowerInvariant() -ne $contractSha) {
        throw "durable protected Round contract SHA-256 differs: ledger=$existingContractSha current=$contractSha"
    }
    $existing = [string]$roundObject.protected_evidence_sha256
    if ($existing -and $existing.ToLowerInvariant() -ne $normalized) {
        throw "durable protected evidence SHA-256 already differs: ledger=$existing requested=$normalized"
    }
    Ensure-Property $roundObject "protected_evidence_sha256" $normalized
    Ensure-Property $roundObject "protected_round_contract_sha256" $contractSha
    if (-not ($roundObject.PSObject.Properties.Name -contains "protected_evidence_bound_at") -or -not $roundObject.protected_evidence_bound_at) {
        Ensure-Property $roundObject "protected_evidence_bound_at" (Utc-Now)
    }
    Save-State $state
    Write-Host "[PROTECTED-EVIDENCE-BASELINE] cycle=$CycleNumber round=$RoundNumber sha256=$normalized"
}

function Mark-FinalAuditEvidenceVerified([int]$CycleNumber, [int]$RoundNumber, [string]$RoundVerdict, [string]$ProtectedSha256) {
    if ($RoundVerdict -notin @("PASS", "REJECTED", "BLOCKED")) { throw "invalid final-audit verified verdict: '$RoundVerdict'" }
    if ($ProtectedSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw "invalid final-audit protected evidence SHA-256: '$ProtectedSha256'" }

    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $cycleObject = Get-Cycle $state $CycleNumber
    $roundObject = Get-Round $cycleObject $RoundNumber
    if (-not $roundObject) { throw "round $CycleNumber/$RoundNumber is missing" }
    if ([string]$roundObject.phase -ne "VERIFYING") { throw "final-audit evidence can only be marked while round is VERIFYING" }
    if (-not $roundObject.candidate_sha) { throw "cannot mark final-audit evidence without candidate SHA" }
    if (-not $roundObject.final_audit_uat_period_slot) { throw "cannot mark final-audit evidence without Fable final-audit period allocation" }

    $normalized = $ProtectedSha256.ToLowerInvariant()
    $durableProtected = ([string]$roundObject.protected_evidence_sha256).Trim().ToLowerInvariant()
    if ($durableProtected -notmatch '^[0-9a-f]{64}$' -or $durableProtected -ne $normalized) {
        throw "final-audit evidence marker disagrees with durable protected evidence baseline: ledger=$durableProtected requested=$normalized"
    }
    $contractSha = Get-ProtectedRoundContractSha256 $cycleObject $roundObject
    $durableContractSha = ([string]$roundObject.protected_round_contract_sha256).Trim().ToLowerInvariant()
    if ($durableContractSha -notmatch '^[0-9a-f]{64}$' -or $durableContractSha -ne $contractSha) {
        throw "final-audit evidence marker found a changed protected Round contract: ledger=$durableContractSha current=$contractSha"
    }

    $canonicalVerdict = Get-CanonicalVerdict
    if ($canonicalVerdict -ne $RoundVerdict) {
        throw "final-audit evidence marker verdict disagrees with canonical uat-result.txt: requested=$RoundVerdict canonical=$canonicalVerdict"
    }

    $progressPath = Join-Path $env:OUTDIR "verifier-state\fable\verifier-progress.json"
    if (-not (Test-Path $progressPath)) { throw "Fable verifier-progress.json missing while marking final-audit evidence" }
    try { $progress = [IO.File]::ReadAllText($progressPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json }
    catch { throw "Fable verifier-progress.json is invalid while marking final-audit evidence: $($_.Exception.Message)" }
    if ([string]$progress.verifier_stage -ne "FABLE") { throw "final-audit evidence marker requires a FABLE progress ledger" }
    if (-not (Test-ProgressMatchesAllocation $progress $roundObject "FABLE")) {
        throw "final-audit evidence marker requires Fable checkpoint to match the current candidate and final-audit allocation"
    }
    if (-not (Test-ProgressVerdictComplete $progress $RoundVerdict)) {
        throw "final-audit evidence marker requires Fable COMPLETE/BLOCKED checkpoint with verdict $RoundVerdict"
    }

    $existingVerified = [string]$roundObject.final_audit_evidence_verified
    $existingVerdict = [string]$roundObject.final_audit_evidence_verified_verdict
    $existingProtected = ([string]$roundObject.final_audit_evidence_verified_protected_sha256).Trim().ToLowerInvariant()
    if ($existingVerified -eq "true") {
        if ($existingVerdict -ne $RoundVerdict -or $existingProtected -ne $normalized) {
            throw "final-audit evidence marker is already bound to different evidence/verdict"
        }
        Write-Host "[FINAL-AUDIT-EVIDENCE] already verified cycle=$CycleNumber round=$RoundNumber verdict=$RoundVerdict sha256=$normalized"
        return
    }

    Ensure-Property $roundObject "final_audit_evidence_verified" "true"
    Ensure-Property $roundObject "final_audit_evidence_verified_verdict" $RoundVerdict
    Ensure-Property $roundObject "final_audit_evidence_verified_protected_sha256" $normalized
    Ensure-Property $roundObject "final_audit_evidence_verified_at" (Utc-Now)
    Save-State $state
    Write-Host "[FINAL-AUDIT-EVIDENCE] verified cycle=$CycleNumber round=$RoundNumber verdict=$RoundVerdict sha256=$normalized"
}

function Complete-Round([int]$CycleNumber, [int]$RoundNumber, [string]$RoundVerdict, [string]$OpusCoreResult = "", [string]$FableCoreResult = "") {
    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $cycleObject = Get-Cycle $state $CycleNumber
    $roundObject = Get-Round $cycleObject $RoundNumber
    if (-not $roundObject) { throw "round $CycleNumber/$RoundNumber is missing" }
    if (-not (Test-CanonicalVerifierComplete $cycleObject $roundObject)) {
        throw "verifier final evidence is incomplete or inconsistent; refusing to complete round"
    }

    # Canonical evidence is the single source of truth. Workflow/caller values
    # are retained only as optional consistency assertions so a wiring error,
    # replay, or manual invocation cannot reinterpret a Fable rejection as an
    # Opus bug (or vice versa) and cross a human governance boundary.
    $canonicalVerdict = Get-CanonicalVerdict
    if (-not $canonicalVerdict) { throw "canonical verifier verdict is missing after evidence validation" }
    if ($RoundVerdict -and $RoundVerdict -ne $canonicalVerdict) {
        throw "canonical verdict mismatch: caller='$RoundVerdict' canonical='$canonicalVerdict'"
    }
    $canonicalCore = Get-CanonicalCoreResults $cycleObject $roundObject $canonicalVerdict
    $canonicalOpusResult = [string]$canonicalCore.opus_result
    $canonicalFableResult = [string]$canonicalCore.fable_result

    if ($OpusCoreResult -and $OpusCoreResult -ne $canonicalOpusResult) {
        throw "canonical Opus result mismatch: caller='$OpusCoreResult' canonical='$canonicalOpusResult'"
    }
    if ($FableCoreResult -and $FableCoreResult -ne $canonicalFableResult) {
        throw "canonical Fable result mismatch: caller='$FableCoreResult' canonical='$canonicalFableResult'"
    }

    $reportPath = Complete-RoundInternal $state $cycleObject $roundObject $canonicalVerdict $canonicalOpusResult $canonicalFableResult
    $state = Load-State
    Write-StepOutput "verdict" $canonicalVerdict
    Write-StepOutput "report_path" $reportPath
    Write-StepOutput "candidate_sha" ([string]$roundObject.candidate_sha)
    Write-StepOutput "opus_result" ([string]$roundObject.opus_result)
    Write-StepOutput "fable_result" ([string]$roundObject.fable_result)
    Write-StepOutput "state_status" ([string]$state.status)
    Write-StepOutput "pause_reason" ([string]$state.pause_reason)
    Write-Host "[ROUND-COMPLETE] cycle=$CycleNumber round=$RoundNumber canonical_verdict=$canonicalVerdict opus=$($roundObject.opus_result) fable=$($roundObject.fable_result) status=$($state.status) pause_reason=$($state.pause_reason) report=$reportPath"
}

function Reopen-InvalidVerifierResult([int]$CycleNumber, [int]$RoundNumber, [string]$ExpectedCandidateSha, [string]$Reason) {
    if ($Reason -ne "CLAUDE_ARGUMENTS_DROPPED") { throw "a supported invalidation reason is required" }
    if ($ExpectedCandidateSha -notmatch '^[0-9a-fA-F]{40}$') { throw "a valid expected candidate SHA is required" }
    $ExpectedCandidateSha = $ExpectedCandidateSha.ToLowerInvariant()

    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    if ([int]$state.current_cycle -ne $CycleNumber -or [int]$state.current_round -ne $RoundNumber) {
        throw "only the current loop round can be reopened"
    }
    $cycleObject = Get-Cycle $state $CycleNumber
    $roundObject = Get-Round $cycleObject $RoundNumber
    if (-not $roundObject) { throw "round $CycleNumber/$RoundNumber is missing" }
    $durableCandidate = ([string]$roundObject.candidate_sha).Trim().ToLowerInvariant()
    if ($durableCandidate -ne $ExpectedCandidateSha) {
        throw "candidate SHA mismatch while reopening invalid verifier result: expected=$ExpectedCandidateSha durable=$durableCandidate"
    }
    if ([string]$state.status -ne "COMPLETED" -or [string]$state.stage -ne "COMPLETED" -or
        [string]$cycleObject.status -ne "COMPLETED" -or [string]$roundObject.phase -ne "COMPLETE" -or
        [string]$roundObject.verdict -ne "PASS" -or [string]$roundObject.opus_result -ne "NO_BUG" -or
        [string]$roundObject.fable_result -ne "FINAL_PASS") {
        throw "reopen is allowed only for the current completed NO_BUG + FINAL_PASS round"
    }

    # Preserve the invalid decision and all live verifier artifacts before making
    # them ineligible for reconciliation. Period allocations and authorization
    # grants remain attached to the same candidate and are reused by the rerun.
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
    $archiveRoot = Join-Path $env:OUTDIR ("invalidated-verifier-results\cycle-{0}\round-{1}\{2}-{3}" -f $CycleNumber, $RoundNumber, $stamp, $Reason.ToLowerInvariant())
    if (Test-Path -LiteralPath $archiveRoot) { throw "invalidation archive already exists: $archiveRoot" }
    New-Item -ItemType Directory -Force $archiveRoot | Out-Null
    Copy-Item -LiteralPath $StateFile -Destination (Join-Path $archiveRoot "loop-state.before-reopen.json") -Force

    $completedRoundArchive = Join-Path $CyclesDir ("cycle-{0}\round-{1}" -f $CycleNumber, $RoundNumber)
    if (Test-Path -LiteralPath $completedRoundArchive) {
        Copy-Item -LiteralPath $completedRoundArchive -Destination (Join-Path $archiveRoot "completed-round-archive") -Recurse -Force
    }
    foreach ($name in @("verifier-state", "verifier-runtime", "UAT_REPORT.md", "opus-result.txt", "uat-result.txt", "opus-core-result.txt", "fable-core-result.txt")) {
        $source = Join-Path $env:OUTDIR $name
        if (Test-Path -LiteralPath $source) {
            Move-Item -LiteralPath $source -Destination (Join-Path $archiveRoot $name)
        }
    }

    $invalidation = [pscustomobject][ordered]@{
        schema_version = 1
        cycle = $CycleNumber
        round = $RoundNumber
        candidate_sha = $durableCandidate
        reason = $Reason
        invalidated_at = Utc-Now
        previous_verdict = "PASS"
        previous_opus_result = "NO_BUG"
        previous_fable_result = "FINAL_PASS"
    }
    Write-Utf8NoBom (Join-Path $archiveRoot "invalidation.json") (($invalidation | ConvertTo-Json -Depth 10) + "`n")

    $history = @($roundObject.invalidated_verifier_results | Where-Object { $null -ne $_ })
    $history += [pscustomobject][ordered]@{
        reason = $Reason
        invalidated_at = [string]$invalidation.invalidated_at
        archive_path = $archiveRoot
        previous_verdict = "PASS"
        previous_opus_result = "NO_BUG"
        previous_fable_result = "FINAL_PASS"
    }
    Ensure-Property $roundObject "invalidated_verifier_results" $history

    foreach ($name in @(
        "verdict", "report_path", "completed_at", "opus_result", "fable_result",
        "produced_findings_source", "produced_findings_ref", "opus_report_sha256", "opus_report_length",
        "protected_evidence_sha256", "protected_round_contract_sha256", "protected_evidence_bound_at",
        "final_audit_evidence_verified", "final_audit_evidence_verified_verdict",
        "final_audit_evidence_verified_protected_sha256", "final_audit_evidence_verified_at"
    )) { Ensure-Property $roundObject $name $null }
    Ensure-Property $roundObject "phase" "VERIFYING"
    Ensure-Property $roundObject "last_run_id" $env:GITHUB_RUN_ID
    Ensure-Property $roundObject "last_run_attempt" $env:GITHUB_RUN_ATTEMPT

    Ensure-Property $cycleObject "status" "RUNNING"
    Ensure-Property $cycleObject "completed_at" $null
    Ensure-Property $cycleObject "findings_source" $null
    Ensure-Property $cycleObject "findings_ref" $null
    Ensure-Property $state "status" "RUNNING"
    Ensure-Property $state "stage" "OPUS_REVIEW"
    Ensure-Property $state "pause_reason" $null
    Ensure-Property $state "opus_result" $null
    Ensure-Property $state "fable_result" $null
    Ensure-Property $state "findings_source" $null
    Ensure-Property $state "findings_ref" $null
    Save-State $state
    Write-Host "[VERIFIER-RESULT-REOPENED] cycle=$CycleNumber round=$RoundNumber candidate=$durableCandidate reason=$Reason archive=$archiveRoot"
}

function Summarize-Loop() {
    $state = Load-State
    if (-not $state) { throw "loop state is missing" }
    $state = Upgrade-CoreStateSchema $state
    $state = Reconcile-State $state
    $state = Upgrade-CoreStateSchema $state
    Write-Host "=== LOOP ENGINE SUMMARY ==="
    Write-Host "current_cycle=$($state.current_cycle)"
    Write-Host "current_round=$($state.current_round)"
    Write-Host "status=$($state.status)"
    Write-Host "stage=$($state.stage)"
    Write-Host "pause_reason=$($state.pause_reason)"
    Write-Host "candidate_branch=$($state.candidate_branch)"
    Write-Host "current_candidate_sha=$($state.current_candidate_sha)"
    Write-Host "max_rounds_per_cycle=$($state.max_rounds_per_cycle)"
    foreach ($cycleObject in @($state.cycles | Sort-Object cycle)) {
        Write-Host "Cycle $($cycleObject.cycle): $($cycleObject.status) start_sha=$($cycleObject.cycle_start_sha) current_sha=$($cycleObject.current_candidate_sha)"
        foreach ($roundObject in @($cycleObject.rounds | Sort-Object round)) {
            $candidate = [string]$roundObject.candidate_sha
            if ($candidate -and $candidate.Length -gt 12) { $candidate = $candidate.Substring(0, 12) }
            Write-Host "  Round $($roundObject.round): phase=$($roundObject.phase) action=$($roundObject.action) opus=$($roundObject.opus_result) fable=$($roundObject.fable_result) legacy_verdict=$($roundObject.verdict) candidate=$candidate"
        }
    }

    switch ([string]$state.status) {
        "COMPLETED" {
            Write-Host "FINAL=COMPLETED"
            exit 0
        }
        "PAUSED_AWAITING_USER" {
            Write-Host "FINAL=PAUSED_AWAITING_USER pause_reason=$($state.pause_reason)"
            Write-Host "To continue this WORK after human review, manually dispatch Loop Engine with run_mode=next-cycle."
            exit 0
        }
        "BLOCKED" {
            Write-Error "FINAL=BLOCKED - fix the environment or human decision, then rerun loop-engine with run_mode=auto. Do not start a new cycle."
            exit 1
        }
        default {
            Write-Error "FINAL=INCOMPLETE - the current round stopped before a terminal/pause state. Rerun loop-engine with run_mode=auto; GitHub Actions Controller will resume from loop-state.json."
            exit 1
        }
    }
}

switch ($Operation) {
    "Prepare" { Prepare-Loop $RunMode; exit 0 }
    "BeginRound" { Begin-Round $Cycle $Round $RoundAction $PreviousReport; exit 0 }
    "SetCandidate" { Set-Candidate $Cycle $Round $CandidateSha; exit 0 }
    "RotateLegacyVerifierPeriod" { Rotate-LegacyVerifierPeriod $Cycle $Round; exit 0 }
    "AllocateFinalAuditPeriod" { Allocate-FinalAuditPeriod $Cycle $Round; exit 0 }
    "BindCycleUatAuthorization" { Bind-CycleUatAuthorization $Cycle $AuthorizationConfirmed $AuthorizationId $AuthorizedActions $AuthorizationActor $AuthorizationRunId $AuthorizationRunAttempt $TargetNamespace $ResourceScope $TargetBranch $ImpactScope; exit 0 }
    "BindUatWriteAuthorization" { Bind-UatWriteAuthorization $Cycle $Round $VerifierStage; exit 0 }
    "BindOpusReportBaseline" { Bind-OpusReportBaseline $Cycle $Round $OpusReportSha256 $OpusReportLength; exit 0 }
    "BindProtectedEvidenceBaseline" { Bind-ProtectedEvidenceBaseline $Cycle $Round $ProtectedEvidenceSha256; exit 0 }
    "MarkFinalAuditEvidenceVerified" { Mark-FinalAuditEvidenceVerified $Cycle $Round $Verdict $ProtectedEvidenceSha256; exit 0 }
    "CompleteRound" { Complete-Round $Cycle $Round $Verdict $OpusResult $FableResult; exit 0 }
    "ReopenInvalidVerifierResult" { Reopen-InvalidVerifierResult $Cycle $Round $CandidateSha $InvalidationReason; exit 0 }
    "Summarize" { Summarize-Loop }
}
