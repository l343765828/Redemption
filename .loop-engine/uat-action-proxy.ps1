$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$MainRepo = "D:\Redemption\Redemption"
$Kubectl = Join-Path $MainRepo "K8S\kubectl.exe"
$Kubeconfig = Join-Path $MainRepo "K8S\admin.conf"
$PolicyPath = Join-Path $MainRepo ".loop-engine\uat-action-policy.json"
$Stage = ([string]$env:VERIFIER_STAGE).Trim().ToUpperInvariant()
$StageLower = if ($Stage -in @("OPUS", "FABLE")) { $Stage.ToLowerInvariant() } else { "unknown" }
$StageStateDir = Join-Path $MainRepo (".loop-output\verifier-state\{0}" -f $StageLower)
$RequestPath = Join-Path $StageStateDir "proxy-request.json"
$LoopCycleText = ([string]$env:LOOP_CYCLE).Trim()
$LoopRoundText = ([string]$env:LOOP_ROUND).Trim()
$EvidenceCycle = if ($LoopCycleText -match '^[0-9]{1,6}$') { $LoopCycleText } else { "invalid-cycle" }
$EvidenceRound = if ($LoopRoundText -match '^[0-9]{1,6}$') { $LoopRoundText } else { "invalid-round" }
# Controller-owned audit evidence is deliberately outside verifier-state; Claude has no Edit rule for this tree.
# Schema-versioned storage prevents v16/v17 records from being interpreted under stronger v20 semantics.
$ControllerEvidenceSchema = "10"
$EvidenceDir = Join-Path $MainRepo (".loop-output\controller-evidence\schema-{0}\cycle-{1}\round-{2}\{3}" -f $ControllerEvidenceSchema, $EvidenceCycle, $EvidenceRound, $StageLower)
$ExecutionId = ([string]$env:LOOP_UAT_EXECUTION_ID).Trim().ToLowerInvariant()
$MaxAuditOutputBytes = 65536
$MaxAuditOutputLines = 400
$script:AuditRequestJson = '{"action":"UNKNOWN","reason":"request-not-loaded"}'

$AuthorizedActionsRaw = ([string]$env:LOOP_UAT_AUTHORIZED_ACTIONS).Trim().ToLowerInvariant()
$AuthorizedActions = @($AuthorizedActionsRaw -split ',' | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() } | Where-Object { $_ })
$TargetNamespace = ([string]$env:LOOP_UAT_TARGET_NAMESPACE).Trim().ToLowerInvariant()
$ResourceScopeRaw = ([string]$env:LOOP_UAT_RESOURCE_SCOPE).Trim().ToLowerInvariant()
$ResourceScope = @($ResourceScopeRaw -split ',' | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() } | Where-Object { $_ })
$TargetBranch = ([string]$env:LOOP_UAT_TARGET_BRANCH).Trim()
$ImpactScope = ([string]$env:LOOP_UAT_IMPACT_SCOPE).Trim().ToLowerInvariant()
$AllMutableTokens = @("test-data-write", "exec", "debug", "git-update", "deploy", "restart", "scale", "delete")
$script:StagePeriodContext = $null

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Get-TextSha256([string]$Text) {
    $bytes = $Utf8NoBom.GetBytes([string]$Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant() }
    finally { $sha.Dispose() }
}

# V19-STRICT-EVIDENCE-PARSER
function Read-ProxyEvidenceFields([string]$Path) {
    $fields = @{}
    foreach ($line in [IO.File]::ReadAllLines($Path, [Text.Encoding]::UTF8)) {
        if (-not $line) { continue }
        $idx = $line.IndexOf('=')
        if ($idx -le 0) { throw "PROXY_EVIDENCE_INVALID: malformed line in $Path" }
        $key = $line.Substring(0, $idx)
        $value = $line.Substring($idx + 1)
        if ($key -notmatch '^[a-z0-9_]+$') { throw "PROXY_EVIDENCE_INVALID: invalid field name '$key' in $Path" }
        if ($fields.ContainsKey($key)) { throw "PROXY_EVIDENCE_INVALID: duplicate field '$key' in $Path" }
        $fields[$key] = $value
    }
    return $fields
}

function Sanitize-AuditText([string]$Text) {
    if ($null -eq $Text) { return "" }
    $value = [string]$Text
    foreach ($name in @("password", "token", "secret", "authorization", "redis_password")) {
        $value = [regex]::Replace($value, "(?i)($name\s*[=:]\s*)[^\s,;]+", '$1<redacted>')
    }
    return $value.Replace("`r", " ").Replace("`n", " ")
}

function Write-ProxyAuditRecord(
    [string]$ActionName,
    [string]$RequestHash,
    [string[]]$RequiredTokens,
    [string]$Outcome,
    [string]$ErrorClass,
    [string]$ErrorMessage,
    $Result,
    [string]$Detail
) {
    try {
        New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
        $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
        $path = Join-Path $EvidenceDir ("action-$stamp-$([Guid]::NewGuid().ToString('N')).log")
        $lines = New-Object System.Collections.Generic.List[string]
        $lines.Add("stage=$Stage")
        $lines.Add("action=$ActionName")
        $lines.Add("request_sha256=$RequestHash")
        if ($script:AuditRequestJson) {
            $requestB64 = [Convert]::ToBase64String($Utf8NoBom.GetBytes($script:AuditRequestJson))
            $lines.Add("request_json_b64=$requestB64")
        }
        $lines.Add("authorization_id=$env:LOOP_UAT_AUTHORIZATION_ID")
        $lines.Add("cycle_scope_sha256=$env:LOOP_UAT_CYCLE_SCOPE_SHA256")
        $lines.Add("stage_scope_sha256=$env:LOOP_UAT_AUTHORIZATION_SCOPE_SHA256")
        $lines.Add("authorized_actions=$AuthorizedActionsRaw")
        $lines.Add("resource_scope=$ResourceScopeRaw")
        $lines.Add("uat_execution_id=$ExecutionId")
        $lines.Add("attempt_run_id=$env:GITHUB_RUN_ID")
        $lines.Add("attempt_run_attempt=$env:GITHUB_RUN_ATTEMPT")
        if ($script:StagePeriodContext) {
            $lines.Add("stage_period_slot=$($script:StagePeriodContext.Slot)")
            $lines.Add("stage_period_primary=$($script:StagePeriodContext.Primary)")
            $lines.Add("stage_period_secondary=$($script:StagePeriodContext.Secondary)")
            $lines.Add("stage_period_pool_sha256=$($script:StagePeriodContext.PoolSha256)")
        }
        $lines.Add("required_tokens=" + (@($RequiredTokens) -join ','))
        if ($Result -and ($Result.PSObject.Properties.Name -contains 'Semantic') -and $null -ne $Result.Semantic) {
            $semanticJson = $Result.Semantic | ConvertTo-Json -Depth 20 -Compress
            $semanticB64 = [Convert]::ToBase64String($Utf8NoBom.GetBytes($semanticJson))
            $lines.Add("semantic_json_b64=$semanticB64")
        }
        $lines.Add("target_namespace=$TargetNamespace")
        $lines.Add("target_branch=$TargetBranch")
        $lines.Add("impact_scope=$ImpactScope")
        $lines.Add("outcome=$Outcome")
        $lines.Add("error_class=$ErrorClass")
        if ($ErrorMessage) { $lines.Add("error_message=" + (Sanitize-AuditText $ErrorMessage)) }
        if ($Detail) { $lines.Add("detail=" + (Sanitize-AuditText $Detail)) }
        $auditExitCode = if ($Result) { [int]$Result.ExitCode } elseif ($Outcome -eq "SUCCESS") { 0 } else { 1 }
        $lines.Add("exit_code=$auditExitCode")
        if ($Result) {
            $outputLines = New-Object System.Collections.Generic.List[string]
            $lineCount = 0
            $byteCount = 0
            foreach ($rawLine in @($Result.Output)) {
                if ($lineCount -ge $MaxAuditOutputLines -or $byteCount -ge $MaxAuditOutputBytes) { break }
                $safeLine = Sanitize-AuditText ([string]$rawLine)
                $bytes = $Utf8NoBom.GetByteCount($safeLine + "`n")
                if (($byteCount + $bytes) -gt $MaxAuditOutputBytes) { break }
                $outputLines.Add($safeLine)
                $lineCount++
                $byteCount += $bytes
            }
            if (@($Result.Output).Count -gt $lineCount) { $outputLines.Add("<output-truncated>") }
            $outputJson = ConvertTo-Json -InputObject @($outputLines.ToArray()) -Compress
            $outputB64 = [Convert]::ToBase64String($Utf8NoBom.GetBytes($outputJson))
            $lines.Add("output_json_b64=$outputB64")
        }
        Write-Utf8NoBom $path (($lines.ToArray() -join "`n") + "`n")
        return $path
    }
    catch {
        Write-Error ("PROXY_AUDIT_WRITE_FAILED: " + $_.Exception.Message)
        return ""
    }
}

function Get-ProxyErrorClass([string]$Message) {
    foreach ($prefix in @(
        "UAT_WRITE_AUTHORIZATION_REQUIRED",
        "UAT_RESOURCE_SCOPE_DENIED",
        "UAT_ACTION_POLICY_DENIED",
        "UAT_ENV_BLOCKED",
        "DEBUG_",
        "GIT_"
    )) {
        if ($Message.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { return $prefix.TrimEnd('_') }
    }
    return "PROXY_FAILURE"
}

function Assert-AuthorizationEnvelope() {
    if ($Stage -notin @("OPUS", "FABLE")) { throw "VERIFIER_STAGE must be OPUS or FABLE" }
    if ($LoopCycleText -notmatch '^[0-9]{1,6}$' -or $LoopRoundText -notmatch '^[0-9]{1,6}$') { throw "UAT_ACTION_POLICY_DENIED: invalid Loop cycle/round identity" }
    if (-not $ExecutionId -or $ExecutionId -notmatch '^c[0-9]+-r[0-9]+-(opus|fable)-s[0-9]+-[0-9a-f]{12}$') { throw "UAT_WRITE_AUTHORIZATION_REQUIRED: durable uat_execution_id is missing or invalid" }
    foreach ($token in $AuthorizedActions) {
        if ($AllMutableTokens -notcontains $token) { throw "invalid authorized action token in durable grant: $token" }
    }
    if (-not $TargetNamespace) { throw "UAT authorization target namespace is missing" }
    if ($TargetNamespace -notmatch '^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$') { throw "invalid UAT authorization target namespace" }
    if ($ResourceScope.Count -lt 1) { throw "UAT authorization resource scope is missing" }
    if (-not $TargetBranch -or $TargetBranch -match '[\x00\r\n ]') { throw "invalid UAT authorization target branch" }
    if ($ImpactScope -ne "isolated-uat-only") { throw "UAT authorization impact scope must be isolated-uat-only" }
}

function Get-StageUatPeriodContext() {
    $authorizedStage = ([string]$env:LOOP_UAT_AUTHORIZATION_STAGE).Trim().ToUpperInvariant()
    if ($authorizedStage -ne $Stage) {
        throw "UAT_WRITE_AUTHORIZATION_REQUIRED: durable stage authorization is bound to $authorizedStage but proxy is running as $Stage"
    }

    $slotText = ""
    $primaryText = ""
    $secondaryText = ""
    $poolSha = ""
    if ($Stage -eq "FABLE") {
        $slotText = ([string]$env:LOOP_FINAL_UAT_PERIOD_SLOT).Trim()
        $primaryText = ([string]$env:LOOP_FINAL_UAT_PERIOD_PRIMARY).Trim()
        $secondaryText = ([string]$env:LOOP_FINAL_UAT_PERIOD_SECONDARY).Trim()
        $poolSha = ([string]$env:LOOP_FINAL_UAT_PERIOD_POOL_SHA256).Trim().ToLowerInvariant()
        $opusSlot = ([string]$env:LOOP_UAT_PERIOD_SLOT).Trim()
        if ($opusSlot -and $slotText -eq $opusSlot) { throw "UAT_ACTION_POLICY_DENIED: Fable final audit must not reuse the Opus period slot" }
    }
    else {
        $slotText = ([string]$env:LOOP_UAT_PERIOD_SLOT).Trim()
        $primaryText = ([string]$env:LOOP_UAT_PERIOD_PRIMARY).Trim()
        $secondaryText = ([string]$env:LOOP_UAT_PERIOD_SECONDARY).Trim()
        $poolSha = ([string]$env:LOOP_UAT_PERIOD_POOL_SHA256).Trim().ToLowerInvariant()
    }

    $slot = 0
    $primary = 0
    $secondary = 0
    if (-not [int]::TryParse($slotText, [ref]$slot) -or $slot -lt 1) { throw "UAT_ACTION_POLICY_DENIED: stage period slot is missing/invalid" }
    if (-not [int]::TryParse($primaryText, [ref]$primary) -or $primary -lt 1) { throw "UAT_ACTION_POLICY_DENIED: stage primary period is missing/invalid" }
    if (-not [int]::TryParse($secondaryText, [ref]$secondary) -or $secondary -lt 1) { throw "UAT_ACTION_POLICY_DENIED: stage secondary period is missing/invalid" }
    if ($primary -eq $secondary) { throw "UAT_ACTION_POLICY_DENIED: stage UAT periods must be distinct" }
    if ($poolSha -notmatch '^[0-9a-f]{64}$') { throw "UAT_ACTION_POLICY_DENIED: stage period pool SHA-256 is missing/invalid" }
    return [pscustomobject]@{ Slot=$slot; Primary=$primary; Secondary=$secondary; PoolSha256=$poolSha; Stage=$Stage }
}

function Assert-RequiredTokens([string[]]$RequiredTokens, [string]$ActionName) {
    foreach ($token in @($RequiredTokens)) {
        if ($AllMutableTokens -notcontains $token) { throw "UAT_ACTION_POLICY_DENIED: unknown required token '$token' for $ActionName" }
        if ($AuthorizedActions -notcontains $token) {
            throw "UAT_WRITE_AUTHORIZATION_REQUIRED: action $ActionName requires token '$token'; authorized=$($AuthorizedActions -join ',')"
        }
    }
}

function Test-ResourceAllowed([string]$Kind, [string]$Name) {
    $key = (([string]$Kind).Trim().ToLowerInvariant() + "/" + ([string]$Name).Trim().ToLowerInvariant())
    if ($key -notmatch '^[a-z0-9.-]+/[a-z0-9._-]+$') { return $false }
    foreach ($entry in $ResourceScope) {
        if ($entry.EndsWith('*')) {
            $prefix = $entry.Substring(0, $entry.Length - 1)
            if ($key.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { return $true }
        }
        elseif ($key -eq $entry) { return $true }
    }
    return $false
}

function Assert-ResourceAllowed([string]$Kind, [string]$Name) {
    if (-not (Test-ResourceAllowed $Kind $Name)) {
        $key = (([string]$Kind).Trim().ToLowerInvariant() + "/" + ([string]$Name).Trim().ToLowerInvariant())
        throw "UAT_RESOURCE_SCOPE_DENIED: $key is outside durable resource scope: $($ResourceScope -join ',')"
    }
}

function Assert-ListScopeAllowed([string]$Kind, [string]$NamePrefix, $Policy) {
    $kindLower = ([string]$Kind).Trim().ToLowerInvariant()
    if (@($Policy.listable_kinds | ForEach-Object { ([string]$_).ToLowerInvariant() }) -notcontains $kindLower) {
        throw "UAT_ACTION_POLICY_DENIED: kind '$kindLower' is not listable"
    }
    if (-not $NamePrefix -or $NamePrefix -notmatch '^[a-z0-9._-]+$') { throw "UAT_ACTION_POLICY_DENIED: list name_prefix is required" }
    $prefixKey = "$kindLower/$(([string]$NamePrefix).ToLowerInvariant())"
    $covered = $false
    foreach ($entry in $ResourceScope) {
        $scopePrefix = if ($entry.EndsWith('*')) { $entry.Substring(0, $entry.Length - 1) } else { $entry }
        if ($prefixKey.StartsWith($scopePrefix, [StringComparison]::OrdinalIgnoreCase) -or $scopePrefix.StartsWith($prefixKey, [StringComparison]::OrdinalIgnoreCase)) {
            $covered = $true
            break
        }
    }
    if (-not $covered) { throw "UAT_RESOURCE_SCOPE_DENIED: list prefix $prefixKey is outside durable resource scope" }
}

function Assert-NoShellWrapper([string[]]$Command) {
    if (-not $Command -or $Command.Count -lt 1) { throw "empty command profile" }
    $joined = (($Command | ForEach-Object { [string]$_ }) -join ' ').Trim().ToLowerInvariant()
    foreach ($needle in @("sh -c", "bash -c", "cmd /c", "powershell -command", "pwsh -command", "powershell.exe -command", "pwsh.exe -command")) {
        if ($joined.Contains($needle)) { throw "UAT_ACTION_POLICY_DENIED: shell wrapper is forbidden: $needle" }
    }
    $first = ([string]$Command[0]).Trim().ToLowerInvariant()
    if ($first -in @("sh", "bash", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe", "kubectl", "kubectl.exe", "helm", "helm.exe")) {
        throw "UAT_ACTION_POLICY_DENIED: shell/orchestrator executable is forbidden inside command profile: $first"
    }
}

function Invoke-Native([string]$FilePath, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $output = @()
    $exitCode = -1
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $FilePath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
    return [pscustomobject]@{ ExitCode = [int]$exitCode; Output = @($output | ForEach-Object { [string]$_ }) }
}

function Invoke-Kubectl([string[]]$Arguments) { return Invoke-Native $Kubectl $Arguments }

function Assert-Readyz() {
    $r = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "get", "--raw=/readyz", "--request-timeout=15s")
    if ($r.ExitCode -ne 0 -or (($r.Output -join "`n").Trim()).ToLowerInvariant() -notmatch '^ok') {
        throw "UAT_ENV_BLOCKED: Kubernetes readyz failed: $($r.Output -join ' ')"
    }
}

function Get-KubectlJson([string[]]$Arguments, [string]$FailurePrefix) {
    $r = Invoke-Kubectl ($Arguments + @("-o", "json", "--request-timeout=15s"))
    if ($r.ExitCode -ne 0) { throw "${FailurePrefix}: $($r.Output -join ' ')" }
    try { return (($r.Output -join "`n") | ConvertFrom-Json) }
    catch { throw "${FailurePrefix}: invalid JSON returned by kubectl" }
}

function Resolve-DebugImage($Policy) {
    if (([string]$Policy.debug_image_mode) -ne "discover-flannel-daemonset") { throw "UAT_ACTION_POLICY_DENIED: unsupported debug image mode" }
    if (([string]$Policy.debug_image_pull_policy) -ne "IfNotPresent") { throw "UAT_ACTION_POLICY_DENIED: debug image pull policy must be IfNotPresent" }
    foreach ($source in @($Policy.debug_image_sources)) {
        $ns = ([string]$source.namespace).Trim()
        $name = ([string]$source.name).Trim()
        $containerName = ([string]$source.container).Trim()
        if (-not $ns -or -not $name) { continue }
        $r = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "get", "daemonset", $name, "-n", $ns, "-o", "json", "--request-timeout=15s")
        if ($r.ExitCode -ne 0) { continue }
        try { $obj = (($r.Output -join "`n") | ConvertFrom-Json) } catch { continue }
        $containers = @($obj.spec.template.spec.containers)
        $selected = $null
        if ($containerName) { $selected = @($containers | Where-Object { ([string]$_.name) -eq $containerName } | Select-Object -First 1)[0] }
        if (-not $selected) { $selected = @($containers | Where-Object { (([string]$_.name) + " " + ([string]$_.image)).ToLowerInvariant().Contains("flannel") } | Select-Object -First 1)[0] }
        if ($selected) {
            $image = ([string]$selected.image).Trim()
            if ($image -and $image -notmatch '[\x00\r\n ]') { return $image }
        }
    }
    throw "UAT_ENV_BLOCKED: no cached flannel DaemonSet image could be discovered"
}

function Get-NodeDebuggerPodObjects([string]$Node) {
    $obj = Get-KubectlJson @("--kubeconfig", $Kubeconfig, "get", "pods", "-n", $TargetNamespace) "DEBUG_LIST_FAILED"
    $prefix = ("node-debugger-{0}-" -f $Node.ToLowerInvariant())
    $items = New-Object System.Collections.Generic.List[object]
    foreach ($item in @($obj.items)) {
        $name = ([string]$item.metadata.name).Trim().ToLowerInvariant()
        if ($name.StartsWith($prefix)) {
            $items.Add([pscustomobject]@{ Name = [string]$item.metadata.name; Uid = [string]$item.metadata.uid; Phase = [string]$item.status.phase })
        }
    }
    return $items.ToArray()
}

function Wait-NewDebugPod([string]$Node, [object[]]$Before, [int]$TimeoutSeconds = 60) {
    $beforeUids = @{}
    foreach ($item in @($Before)) { $beforeUids[[string]$item.Uid] = $true }
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $after = @(Get-NodeDebuggerPodObjects $Node)
        $created = @($after | Where-Object { -not $beforeUids.ContainsKey([string]$_.Uid) })
        if ($created.Count -eq 1) { return $created[0] }
        if ($created.Count -gt 1) { throw "DEBUG_POD_AMBIGUOUS: more than one new node-debugger Pod appeared" }
        Start-Sleep -Seconds 1
    }
    throw "DEBUG_POD_NOT_FOUND: kubectl debug did not produce a unique Pod within timeout"
}

function Wait-DebugPodTermination([string]$PodName, [string]$PodUid, [int]$TimeoutSeconds = 300) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $obj = Get-KubectlJson @("--kubeconfig", $Kubeconfig, "get", "pod", $PodName, "-n", $TargetNamespace) "DEBUG_STATUS_FAILED"
        if (([string]$obj.metadata.uid) -ne $PodUid) { throw "DEBUG_POD_UID_MISMATCH: $PodName UID changed before completion" }
        $statuses = @($obj.status.containerStatuses)
        foreach ($status in $statuses) {
            $waitingReason = [string]$status.state.waiting.reason
            if ($waitingReason -in @("ErrImagePull", "ImagePullBackOff")) {
                throw "UAT_ENV_BLOCKED: debug Pod image is unavailable with IfNotPresent: $waitingReason"
            }
        }
        $terminated = @($statuses | Where-Object { $null -ne $_.state.terminated })
        if ($statuses.Count -gt 0 -and $terminated.Count -eq $statuses.Count) {
            $codes = @($terminated | ForEach-Object { [int]$_.state.terminated.exitCode })
            $exitCode = if (@($codes | Where-Object { $_ -ne 0 }).Count -gt 0) { [int](@($codes | Where-Object { $_ -ne 0 })[0]) } else { 0 }
            return [pscustomobject]@{ ExitCode = $exitCode; Phase = [string]$obj.status.phase; Object = $obj }
        }
        Start-Sleep -Seconds 1
    }
    throw "DEBUG_COMMAND_TIMEOUT: $PodName did not terminate within $TimeoutSeconds seconds"
}

function Remove-DebugPodByUid([string]$PodName, [string]$PodUid) {
    $get = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "get", "pod", $PodName, "-n", $TargetNamespace, "-o", "json", "--request-timeout=15s")
    if ($get.ExitCode -ne 0) {
        if (($get.Output -join " ") -match '(?i)notfound|not found') { return }
        throw "DEBUG_CLEANUP_FAILED: cannot re-read $PodName before deletion: $($get.Output -join ' ')"
    }
    try { $obj = (($get.Output -join "`n") | ConvertFrom-Json) } catch { throw "DEBUG_CLEANUP_FAILED: invalid Pod JSON for $PodName" }
    if (([string]$obj.metadata.uid) -ne $PodUid) { throw "DEBUG_POD_UID_MISMATCH: refuse to delete replacement Pod $PodName" }
    $del = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "delete", "pod", $PodName, "-n", $TargetNamespace, "--wait=true", "--request-timeout=30s")
    if ($del.ExitCode -ne 0) { throw "DEBUG_CLEANUP_FAILED: $PodName => $($del.Output -join ' ')" }
}

function Invoke-NodeDebugWithCleanup([string]$Node, [string[]]$Command, [string]$DebugImage) {
    Assert-ResourceAllowed "node" $Node
    Assert-NoShellWrapper $Command
    $before = @(Get-NodeDebuggerPodObjects $Node)
    $created = $null
    $creation = $null
    $result = $null
    $cleanupError = $null
    try {
        $debugArgs = @(
            "--kubeconfig", $Kubeconfig, "debug", ("node/{0}" -f $Node), "-n", $TargetNamespace,
            "--profile=sysadmin", ("--image={0}" -f $DebugImage), "--image-pull-policy=IfNotPresent", "--attach=false", "--"
        ) + @($Command)
        $creation = Invoke-Kubectl $debugArgs
        if ($creation.ExitCode -ne 0) { throw "DEBUG_CREATE_FAILED: $($creation.Output -join ' ')" }
        $created = Wait-NewDebugPod $Node $before 60
        $termination = Wait-DebugPodTermination $created.Name $created.Uid 300
        # kubectl logs is intentionally executed before cleanup so command evidence survives Pod deletion.
        $logs = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "logs", $created.Name, "-n", $TargetNamespace, "--all-containers=true", "--request-timeout=15s")
        $combined = New-Object System.Collections.Generic.List[string]
        foreach ($line in @($creation.Output)) { $combined.Add([string]$line) }
        $combined.Add("debug_pod=$($created.Name)")
        $combined.Add("debug_uid=$($created.Uid)")
        $combined.Add("debug_phase=$($termination.Phase)")
        $combined.Add("debug_exit_code=$($termination.ExitCode)")
        foreach ($line in @($logs.Output)) { $combined.Add([string]$line) }
        if ($logs.ExitCode -ne 0) { throw "DEBUG_LOGS_FAILED: cannot read completed debug Pod logs: $($logs.Output -join ' ')" }
        $result = [pscustomobject]@{ ExitCode = [int]$termination.ExitCode; Output = $combined.ToArray() }
    }
    finally {
        if (-not $created -and $creation -and $creation.ExitCode -eq 0) {
            try {
                $beforeUids = @{}
                foreach ($oldPod in @($before)) { $beforeUids[[string]$oldPod.Uid] = $true }
                $newPods = @(Get-NodeDebuggerPodObjects $Node | Where-Object { -not $beforeUids.ContainsKey([string]$_.Uid) })
                if ($newPods.Count -eq 1) { $created = $newPods[0] }
                elseif ($newPods.Count -gt 1) { $cleanupError = "DEBUG_POD_AMBIGUOUS: cannot safely identify debug Pod for cleanup" }
            }
            catch { $cleanupError = $_.Exception.Message }
        }
        if ($created) {
            try { Remove-DebugPodByUid $created.Name $created.Uid }
            catch { $cleanupError = $_.Exception.Message }
        }
    }
    if ($cleanupError) { throw $cleanupError }
    return $result
}

function Get-PolicyProfile($Container, [string]$ProfileName, [string]$ProfileKind) {
    if (-not $Container) { throw "UAT_ACTION_POLICY_DENIED: $ProfileKind policy container is missing" }
    $prop = @($Container.PSObject.Properties | Where-Object { $_.Name -eq $ProfileName } | Select-Object -First 1)[0]
    if (-not $prop) { throw "UAT_ACTION_POLICY_DENIED: unknown $ProfileKind profile '$ProfileName'" }
    return $prop.Value
}

function Expand-ProfileCommand([object[]]$Command) {
    $candidatePath = Join-Path $MainRepo ".loop-output\pushed-sha.txt"
    $candidate = if (Test-Path $candidatePath) { ([IO.File]::ReadAllText($candidatePath, [Text.Encoding]::UTF8)).Trim() } else { "" }
    $stagePeriod = Get-StageUatPeriodContext
    $replacements = @{
        "{namespace}" = $TargetNamespace
        "{target_branch}" = $TargetBranch
        "{candidate_sha}" = $candidate
        "{period_primary}" = [string]$stagePeriod.Primary
        "{period_secondary}" = [string]$stagePeriod.Secondary
    }
    $result = New-Object System.Collections.Generic.List[string]
    foreach ($raw in @($Command)) {
        $value = [string]$raw
        foreach ($key in $replacements.Keys) { $value = $value.Replace($key, [string]$replacements[$key]) }
        if ($value -match '[\x00\r\n]') { throw "UAT_ACTION_POLICY_DENIED: command profile expansion produced a control character" }
        $result.Add($value)
    }
    return $result.ToArray()
}

function Find-GitRepoByRemote([string]$Node, [string]$DebugImage, [string]$ExpectedRemote) {
    $find = Invoke-NodeDebugWithCleanup $Node @("chroot", "/host", "find", "/", "-maxdepth", "8", "-type", "d", "-name", ".git", "-print") $DebugImage
    if ($find.ExitCode -ne 0) { throw "GIT_REPO_DISCOVERY_FAILED: find .git failed" }
    $matches = New-Object System.Collections.Generic.List[string]
    foreach ($gitDir in @($find.Output | Where-Object { ([string]$_).Trim().EndsWith("/.git") })) {
        $repo = ([string]$gitDir).Trim().Substring(0, ([string]$gitDir).Trim().Length - 5)
        if (-not $repo -or $repo -match '[\x00\r\n]') { continue }
        $remote = Invoke-NodeDebugWithCleanup $Node @("chroot", "/host", "git", "-C", $repo, "config", "--get", "remote.origin.url") $DebugImage
        $remoteMatch = @($remote.Output | Where-Object { ([string]$_).Trim() -eq $ExpectedRemote })
        if ($remote.ExitCode -eq 0 -and $remoteMatch.Count -gt 0) { $matches.Add($repo) }
    }
    $unique = @($matches.ToArray() | Select-Object -Unique)
    if ($unique.Count -ne 1) { throw "GIT_REPO_DISCOVERY_FAILED: expected exactly one host repo for $ExpectedRemote, found $($unique.Count)" }
    return [string]$unique[0]
}

function Verify-NodeHostGitView([string]$Node, [string]$Repo, [string]$DebugImage, [string]$Candidate) {
    $branch = Invoke-NodeDebugWithCleanup $Node @("chroot", "/host", "git", "-C", $Repo, "rev-parse", "--abbrev-ref", "HEAD") $DebugImage
    $branchMatch = @($branch.Output | Where-Object { ([string]$_).Trim() -eq $TargetBranch })
    if ($branch.ExitCode -ne 0 -or $branchMatch.Count -lt 1) { throw "GIT_BRANCH_MISMATCH: node host branch is not $TargetBranch" }
    $head = Invoke-NodeDebugWithCleanup $Node @("chroot", "/host", "git", "-C", $Repo, "rev-parse", "HEAD") $DebugImage
    $headText = (($head.Output | Where-Object { ([string]$_).Trim() -match '^[0-9a-fA-F]{40}$' } | Select-Object -Last 1) -as [string]).Trim().ToLowerInvariant()
    if ($head.ExitCode -ne 0 -or $headText -ne $Candidate) { throw "GIT_HEAD_MISMATCH: node host HEAD=$headText expected=$Candidate" }
}

function Find-PodGitRepoByRemote([string]$Pod, [string]$Container, [string]$ExpectedRemote) {
    Assert-ResourceAllowed "pod" $Pod
    $args = @("--kubeconfig", $Kubeconfig, "exec", $Pod, "-n", $TargetNamespace)
    if ($Container) { $args += @("-c", $Container) }
    $find = Invoke-Kubectl ($args + @("--", "find", "/", "-maxdepth", "8", "-type", "d", "-name", ".git", "-print"))
    if ($find.ExitCode -ne 0) { throw "GIT_POD_VIEW_FAILED: cannot discover repo in verification pod" }
    $matches = New-Object System.Collections.Generic.List[string]
    foreach ($gitDir in @($find.Output | Where-Object { ([string]$_).Trim().EndsWith("/.git") })) {
        $repo = ([string]$gitDir).Trim().Substring(0, ([string]$gitDir).Trim().Length - 5)
        if (-not $repo -or $repo -match '[\x00\r\n]') { continue }
        $remote = Invoke-Kubectl ($args + @("--", "git", "-c", ("safe.directory={0}" -f $repo), "-C", $repo, "config", "--get", "remote.origin.url"))
        if ($remote.ExitCode -eq 0 -and (($remote.Output -join "`n").Trim()) -eq $ExpectedRemote) { $matches.Add($repo) }
    }
    $unique = @($matches.ToArray() | Select-Object -Unique)
    if ($unique.Count -ne 1) { throw "GIT_POD_VIEW_FAILED: expected exactly one repo in verification pod, found $($unique.Count)" }
    return [string]$unique[0]
}

function Verify-PodGitView([string]$Pod, [string]$Container, [string]$ExpectedRemote, [string]$Candidate) {
    $repo = Find-PodGitRepoByRemote $Pod $Container $ExpectedRemote
    $args = @("--kubeconfig", $Kubeconfig, "exec", $Pod, "-n", $TargetNamespace)
    if ($Container) { $args += @("-c", $Container) }
    $head = Invoke-Kubectl ($args + @("--", "git", "-c", ("safe.directory={0}" -f $repo), "-C", $repo, "rev-parse", "HEAD"))
    $text = (($head.Output -join "`n").Trim()).ToLowerInvariant()
    if ($head.ExitCode -ne 0 -or $text -ne $Candidate) { throw "GIT_POD_VIEW_FAILED: pod NFS HEAD=$text expected=$Candidate" }
    return $repo
}

function Get-PodExecArguments([string]$Pod, [string]$Container) {
    Assert-ResourceAllowed "pod" $Pod
    $args = @("--kubeconfig", $Kubeconfig, "exec", $Pod, "-n", $TargetNamespace)
    if ($Container) { $args += @("-c", $Container) }
    return $args
}

function Invoke-PodCommand([string]$Pod, [string]$Container, [string[]]$Command) {
    $args = @(Get-PodExecArguments $Pod $Container)
    return Invoke-Kubectl ($args + @("--") + @($Command))
}

function Invoke-RuntimePythonCommand([string]$Pod,[string]$Container,[string]$Repo,$Policy,[string]$Code,[string[]]$Arguments) {
    $expectedRepo=([string]$Policy.consumer_runtime_target.repo_path).Trim()
    if(-not $expectedRepo -or $Repo -ne $expectedRepo){throw 'UAT_ACTION_POLICY_DENIED: runtime Python repository path is not the version-controlled target'}
    $kafka=([string]$Policy.consumer_runtime_target.kafka_bootstrap).Trim()
    if(-not $kafka -or $kafka -match '[\x00\r\n ]'){throw 'UAT_ACTION_POLICY_DENIED: runtime Kafka bootstrap is missing or invalid'}
    if(-not $Code){throw 'UAT_ACTION_POLICY_DENIED: runtime Python code is missing'}
    $codeB64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Code))
    $launcher=@'
import base64, os, sys
repo, kafka, code_b64 = sys.argv[1:4]
if repo not in sys.path:
    sys.path.insert(0, repo)
from Model import Config as runtime_config
values = {
    "PVAM_DASK_SCHEDULER": runtime_config.SCHEDULE_ADDRESS,
    "PVAM_REDIS_HOST": runtime_config.REDIS_HOST,
    "PVAM_REDIS_PORT": runtime_config.REDIS_PORT,
    "PVAM_REDIS_DB": runtime_config.REDIS_DB,
    "PVAM_REDIS_PASSWORD": runtime_config.REDIS_PASSWORD,
}
if any(value is None or str(value) == "" for value in values.values()):
    raise RuntimeError("runtime Model.Config is incomplete")
os.environ.update({name: str(value) for name, value in values.items()})
os.environ["PVAM_KAFKA_BOOTSTRAP"] = kafka
sys.argv = ["<uat-runtime>"] + sys.argv[4:]
exec(compile(base64.b64decode(code_b64), "<uat-runtime>", "exec"), {"__name__": "__main__"})
'@
    return Invoke-PodCommand $Pod $Container (@('python3','-c',$launcher,$Repo,$kafka,$codeB64)+@($Arguments))
}

function Get-CurrentCandidateSha() {
    $candidatePath = Join-Path $MainRepo ".loop-output\pushed-sha.txt"
    if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) { throw "GIT_POD_VIEW_FAILED: pushed-sha.txt missing before runtime repo use" }
    $candidate = ([IO.File]::ReadAllText($candidatePath,[Text.Encoding]::UTF8)).Trim().ToLowerInvariant()
    if ($candidate -notmatch '^[0-9a-f]{40}$') { throw "GIT_POD_VIEW_FAILED: invalid candidate SHA before runtime repo use" }
    return $candidate
}

function Get-PodRepoRoot([string]$Pod, [string]$Container, $Policy) {
    $remote = ([string]$Policy.repo_remote_url).Trim()
    if (-not $remote) { throw "UAT_ACTION_POLICY_DENIED: repo_remote_url is missing" }
    $repo=Verify-PodGitView $Pod $Container $remote (Get-CurrentCandidateSha)
    $expectedRepo=([string]$Policy.consumer_runtime_target.repo_path).Trim()
    if(-not $expectedRepo -or $repo -ne $expectedRepo){throw 'UAT_ACTION_POLICY_DENIED: runtime repository path does not match consumer_runtime_target'}
    return $repo
}

function Invoke-PolicyExecProfile($Request, $Policy, [string]$ProfileName = "") {
    $name = if ($ProfileName) { $ProfileName } else { ([string]$Request.profile).Trim() }
    $profile = Get-PolicyProfile $Policy.exec_profiles $name "exec"
    $requiredTokens = @("exec") + @($profile.required_tokens | ForEach-Object { [string]$_ }) | Select-Object -Unique
    Assert-RequiredTokens @($requiredTokens) "ExecProfile:$name"
    $pod = ([string]$Request.pod).Trim(); $container = ([string]$Request.container).Trim()
    $command = @(Expand-ProfileCommand @($profile.command)); Assert-NoShellWrapper $command
    if ($profile.PSObject.Properties.Name -contains 'repo_cwd' -and [bool]$profile.repo_cwd) {
        $repo = Get-PodRepoRoot $pod $container $Policy
        $wrapper = "import os,subprocess,sys;os.chdir(sys.argv[1]);raise SystemExit(subprocess.call(sys.argv[2:]))"
        $command = @("python3", "-c", $wrapper, $repo) + $command
    }
    return Invoke-PodCommand $pod $container $command
}

# V19-CONSUMER-LIFECYCLE-GOVERNANCE
function Get-ConsumerLifecycleTarget($Policy,[string]$Deployment,[string]$Container) {
    $target=$Policy.consumer_runtime_target
    if(-not $target){throw "UAT_ACTION_POLICY_DENIED: consumer_runtime_target is missing; lifecycle mutation is fail-closed"}
    if(([string]$target.mode).ToLowerInvariant() -ne 'scheduler-pod-temporary-process'){throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle runtime mode is not allowlisted"}
    if(([string]$target.namespace).ToLowerInvariant() -ne $TargetNamespace){throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle runtime namespace mismatch"}
    $hostDeployment=([string]$target.host_deployment).Trim().ToLowerInvariant()
    $targetContainer=([string]$target.container).Trim()
    if(-not $hostDeployment -or -not $targetContainer){throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle runtime target is incomplete"}
    if($Deployment -and $Deployment.ToLowerInvariant() -ne $hostDeployment){throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle host deployment is not allowlisted"}
    if($Container -and $Container -ne $targetContainer){throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle host container is not allowlisted"}
    $prefix=([string]$target.pod_name_prefix).Trim().ToLowerInvariant()
    if($prefix -notmatch '^[a-z0-9]([-a-z0-9.]*[a-z0-9])?-$'){
        throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle pod_name_prefix is invalid"
    }
    return $target
}

function Assert-ConsumerLifecyclePodPrefixCoveredByScope([string]$Prefix) {
    $covered=$false
    foreach($entry in @($ResourceScope)){
        if($entry.StartsWith('pod/',[StringComparison]::Ordinal)){
            $pattern=$entry.Substring(4)
            if($pattern.EndsWith('*',[StringComparison]::Ordinal)){
                $scopePrefix=$pattern.Substring(0,$pattern.Length-1)
                if($Prefix.StartsWith($scopePrefix,[StringComparison]::Ordinal)){ $covered=$true; break }
            }
        }
    }
    if(-not $covered){throw "UAT_RESOURCE_SCOPE_DENIED: ConsumerLifecycle pod_name_prefix is not covered by Cycle pod scope"}
}

function Get-ConsumerLifecycleSelectedPods([string]$Deployment,[string]$Container,[string]$PodPrefix) {
    $dep = Get-KubectlJson @('--kubeconfig',$Kubeconfig,'get','deployment',$Deployment,'-n',$TargetNamespace) "UAT_ENV_BLOCKED: cannot read deployment selector"
    $labels=@()
    foreach($p in @($dep.spec.selector.matchLabels.PSObject.Properties)){$labels += ("{0}={1}" -f $p.Name,[string]$p.Value)}
    if($labels.Count -lt 1){throw "UAT_ENV_BLOCKED: ConsumerLifecycle deployment selector.matchLabels is empty"}
    $selector=$labels -join ','
    $pods=Get-KubectlJson @('--kubeconfig',$Kubeconfig,'get','pods','-n',$TargetNamespace,'-l',$selector) "UAT_ENV_BLOCKED: cannot list ConsumerLifecycle pods"
    $names=New-Object System.Collections.Generic.List[string]
    foreach($item in @($pods.items)){
        $name=([string]$item.metadata.name).Trim().ToLowerInvariant()
        if(-not $name){continue}
        if(-not $name.StartsWith($PodPrefix,[StringComparison]::Ordinal)){throw "UAT_RESOURCE_SCOPE_DENIED: selected ConsumerLifecycle pod outside versioned pod prefix: $name"}
        $matchingContainers=@($item.status.containerStatuses|Where-Object{([string]$_.name) -eq $Container})
        if($matchingContainers.Count -ne 1){throw "UAT_ENV_BLOCKED: Consumer runtime host container not found/ambiguous in pod $name"}
        if(([string]$item.status.phase) -ne 'Running' -or -not [bool]$matchingContainers[0].ready){continue}
        Assert-ResourceAllowed "pod" $name
        $names.Add($name)
    }
    if($names.Count -ne 1){throw "UAT_ENV_BLOCKED: expected exactly one Running/Ready Consumer runtime host pod; found $($names.Count)"}
    return $names.ToArray()
}

function Resolve-ConsumerRuntimeTarget($Request,$Policy,[string]$Action) {
    $requestedContainer=([string]$Request.container).Trim()
    $target=Get-ConsumerLifecycleTarget $Policy '' $requestedContainer
    $deployment=([string]$target.host_deployment).Trim().ToLowerInvariant()
    $container=([string]$target.container).Trim()
    Assert-ResourceAllowed 'deployment' $deployment
    Assert-ConsumerLifecyclePodPrefixCoveredByScope ([string]$target.pod_name_prefix)
    $pods=@(Get-ConsumerLifecycleSelectedPods $deployment $container ([string]$target.pod_name_prefix))
    $pod=[string]$pods[0]
    $requestedPod=([string]$Request.pod).Trim().ToLowerInvariant()
    if($requestedPod -and $requestedPod -ne $pod){throw "UAT_ACTION_POLICY_DENIED: $Action runtime pod is controller governed"}
    if($requestedContainer -and $requestedContainer -ne $container){throw "UAT_ACTION_POLICY_DENIED: $Action runtime container is controller governed"}
    $candidate=Get-CurrentCandidateSha
    $repo=Verify-PodGitView $pod $container ([string]$Policy.repo_remote_url) $candidate
    $expectedRepo=([string]$target.repo_path).Trim()
    if(-not $expectedRepo -or $repo -ne $expectedRepo){throw "UAT_ACTION_POLICY_DENIED: $Action runtime repository path mismatch"}
    return [pscustomobject]@{Target=$target;Deployment=$deployment;Pod=$pod;Container=$container;Candidate=$candidate;Repo=$repo}
}

function Invoke-ConsumerRuntimeController([string]$Pod,[string]$Container,[string]$Operation,$Payload) {
    $controllerPath=Join-Path $PSScriptRoot 'consumer-runtime-controller.py'
    if(-not (Test-Path -LiteralPath $controllerPath -PathType Leaf)){throw 'UAT_ENV_BLOCKED: consumer-runtime-controller.py is missing'}
    $controllerText=[IO.File]::ReadAllText($controllerPath,[Text.Encoding]::UTF8)
    $controllerB64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($controllerText))
    $payloadJson=$Payload|ConvertTo-Json -Depth 12 -Compress
    $launcher="import base64,sys;code=base64.b64decode(sys.argv[1]);sys.argv=['consumer-runtime-controller.py']+sys.argv[2:];exec(compile(code,'<consumer-runtime-controller>','exec'),{'__name__':'__main__','__file__':'consumer-runtime-controller.py'})"
    $runtime=Invoke-PodCommand $Pod $Container @('python3','-c',$launcher,$controllerB64,$Operation,$payloadJson)
    if($runtime.ExitCode -ne 0){return $runtime}
    $json=(@($runtime.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1)
    if(-not $json){throw 'UAT_ENV_BLOCKED: Consumer runtime controller returned no JSON'}
    try{$semantic=([string]$json)|ConvertFrom-Json}catch{throw 'UAT_ENV_BLOCKED: Consumer runtime controller returned invalid JSON'}
    if([string]$semantic.kind -ne 'ConsumerRuntimeControllerResult'){throw 'UAT_ENV_BLOCKED: Consumer runtime controller semantic kind mismatch'}
    $runtime|Add-Member -NotePropertyName Semantic -NotePropertyValue $semantic -Force
    return $runtime
}

function New-ConsumerRuntimePayload($Target,[string]$Role,[int]$Period,[int]$CalcMonth,[string]$Candidate,[string]$Repo) {
    return [ordered]@{
        execution_id=$ExecutionId
        repo_path=$Repo
        module=[string]$Target.module
        candidate_sha=$Candidate
        role=$Role
        bound_period=$Period
        calc_month=$CalcMonth
        ledger_prefix="pvam:uat:work02:${ExecutionId}:"
        kafka_bootstrap=[string]$Target.kafka_bootstrap
        elite_rate_percent=[string]$Target.elite_rate_percent
    }
}

function Get-ConsumerRuntimeLogs([string]$Pod,[string]$Container) {
    $runtime=Invoke-ConsumerRuntimeController $Pod $Container 'logs' ([ordered]@{execution_id=$ExecutionId})
    if($runtime.ExitCode -ne 0){throw 'UAT_ENV_BLOCKED: Consumer runtime logs unavailable'}
    return $runtime.Semantic
}

# V19-INVOKE-CONSUMERLIFECYCLE
function Invoke-ConsumerLifecycle($Request,$Policy) {
    $op=([string]$Request.operation).Trim().ToLowerInvariant()
    $requestedDeployment=([string]$Request.deployment).Trim().ToLowerInvariant()
    $requestedContainer=([string]$Request.container).Trim()
    $target=Get-ConsumerLifecycleTarget $Policy $requestedDeployment $requestedContainer
    $deployment=([string]$target.host_deployment).Trim().ToLowerInvariant()
    $container=([string]$target.container).Trim()
    Assert-ResourceAllowed "deployment" $deployment
    Assert-ConsumerLifecyclePodPrefixCoveredByScope ([string]$target.pod_name_prefix)
    $selectedPods=@(Get-ConsumerLifecycleSelectedPods $deployment $container ([string]$target.pod_name_prefix))
    $pod=$selectedPods[0]
    $podObject=Get-KubectlJson @('--kubeconfig',$Kubeconfig,'get','pod',$pod,'-n',$TargetNamespace) "UAT_ENV_BLOCKED: cannot read Consumer runtime host pod"
    $podUid=([string]$podObject.metadata.uid).Trim()
    if(-not $podUid){throw "UAT_ENV_BLOCKED: Consumer runtime host pod UID is missing"}
    $candidate=Get-CurrentCandidateSha
    $remote=([string]$Policy.repo_remote_url).Trim()
    if(-not $remote){throw "UAT_ACTION_POLICY_DENIED: repo_remote_url is missing"}
    $repo=Verify-PodGitView $pod $container $remote $candidate
    $expectedRepo=([string]$target.repo_path).Trim()
    if(-not $expectedRepo -or $repo -ne $expectedRepo){throw "UAT_ACTION_POLICY_DENIED: Consumer runtime repository path mismatch"}
    $runtimeMode='scheduler-pod-temporary-process'

    if($op -in @('bind-primary','bind-secondary')){
        Assert-RequiredTokens @('exec') 'ConsumerLifecycle'
        if($Request.PSObject.Properties.Name -contains 'calc_month'){throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle calc_month is controller governed"}
        $ctx=Get-StageUatPeriodContext
        $role=if($op -eq 'bind-primary'){'primary'}else{'secondary'}
        $period=if($role -eq 'primary'){[int]$ctx.Primary}else{[int]$ctx.Secondary}
        $calcProperty=@($target.calc_month_by_role.PSObject.Properties|Where-Object{$_.Name -eq $role}|Select-Object -First 1)[0]
        if(-not $calcProperty){throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle calc month policy missing for role $role"}
        $calcMonth=([string]$calcProperty.Value).Trim()
        if($calcMonth -notmatch '^[0-9]{6}$'){throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle governed calc month must be YYYYMM"}
        [int]$month=[int]$calcMonth.Substring(4,2)
        if($month -lt 1 -or $month -gt 12){throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle governed calc month is invalid"}
        $ledgerPrefix="pvam:uat:work02:${ExecutionId}:"
        $payload=New-ConsumerRuntimePayload $target $role $period ([int]$calcMonth) $candidate $repo
        $runtime=Invoke-ConsumerRuntimeController $pod $container 'replace' $payload
        if($runtime.ExitCode -ne 0){throw "UAT_ENV_BLOCKED: ConsumerLifecycle runtime replace failed"}
        $state=$runtime.Semantic
        if(-not [bool]$state.running -or [string]$state.role -ne $role -or [string]$state.bound_period -ne [string]$period -or [string]$state.calc_month -ne $calcMonth -or [string]$state.candidate_sha -ne $candidate -or [string]$state.ledger_prefix -ne $ledgerPrefix){
            throw "UAT_ENV_BLOCKED: ConsumerLifecycle runtime binding verification failed"
        }
        $podHeads=@([pscustomobject]@{pod=$pod;repo=$repo;head=$candidate})
        $semantic=[pscustomobject]@{kind='ConsumerLifecycleResult';runtime_mode='scheduler-pod-temporary-process';operation=$op;deployment=$deployment;container=$container;pod=$pod;pod_uid=$podUid;pod_name_prefix=[string]$target.pod_name_prefix;bound_period=$period;calc_month=$calcMonth;ledger_prefix=$ledgerPrefix;matching_process_count=1;candidate_sha=$candidate;pod_repo_heads=$podHeads;runtime_controller_operation=[string]$state.operation;process_pid=[int]$state.pid}
        return [pscustomobject]@{ExitCode=0;Output=@("runtime_mode=$runtimeMode","operation=$op","host_deployment=$deployment","pod=$pod","container=$container","bound_period=$period","matching_process_count=1","candidate_sha=$candidate");Semantic=$semantic}
    }
    elseif($op -eq 'status'){
        Assert-RequiredTokens @('exec') 'ConsumerLifecycle'
        $runtime=Invoke-ConsumerRuntimeController $pod $container 'status' ([ordered]@{execution_id=$ExecutionId})
        if($runtime.ExitCode -ne 0 -or -not [bool]$runtime.Semantic.running){throw "UAT_ENV_BLOCKED: governed PvEventConsumer is not running"}
        $state=$runtime.Semantic
        $semantic=[pscustomobject]@{kind='ConsumerLifecycleResult';runtime_mode='scheduler-pod-temporary-process';operation='status';deployment=$deployment;container=$container;pod=$pod;pod_uid=$podUid;pod_name_prefix=[string]$target.pod_name_prefix;bound_period=[int]$state.bound_period;calc_month=[int]$state.calc_month;ledger_prefix=[string]$state.ledger_prefix;matching_process_count=1;candidate_sha=[string]$state.candidate_sha;pod_repo_heads=@([pscustomobject]@{pod=$pod;repo=$repo;head=$candidate});process_pid=[int]$state.pid}
        return [pscustomobject]@{ExitCode=0;Output=@("runtime_mode=$runtimeMode","operation=status","pod=$pod","container=$container","matching_process_count=1");Semantic=$semantic}
    }
    elseif($op -eq 'restore'){
        Assert-RequiredTokens @('exec') 'ConsumerLifecycle'
        $runtime=Invoke-ConsumerRuntimeController $pod $container 'stop' ([ordered]@{execution_id=$ExecutionId})
        if($runtime.ExitCode -ne 0 -or -not [bool]$runtime.Semantic.stopped){throw "UAT_ENV_BLOCKED: ConsumerLifecycle runtime stop failed"}
        $baselineSha=Get-TextSha256 "runtime_mode=$runtimeMode;execution_id=$ExecutionId;baseline=consumer-absent"
        $semantic=[pscustomobject]@{kind='ConsumerLifecycleResult';runtime_mode='scheduler-pod-temporary-process';operation='restore';deployment=$deployment;container=$container;pod=$pod;pod_uid=$podUid;pod_name_prefix=[string]$target.pod_name_prefix;restored=$true;matching_process_count=0;baseline_sha256=$baselineSha}
        return [pscustomobject]@{ExitCode=0;Output=@("runtime_mode=$runtimeMode","operation=restore","pod=$pod","container=$container","matching_process_count=0","baseline_sha256=$baselineSha");Semantic=$semantic}
    }
    throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle operation must be bind-primary, bind-secondary, status, or restore"
}

function Get-KafkaScenarioSemantic([string]$Scenario) {
    $matches=New-Object System.Collections.Generic.List[object]
    if(-not (Test-Path -LiteralPath $EvidenceDir -PathType Container)){return $null}
    foreach($file in @(Get-ChildItem -LiteralPath $EvidenceDir -File -Filter 'action-*.log' -Force|Sort-Object FullName)){
        $fields=Read-ProxyEvidenceFields $file.FullName
        if([string]$fields['action'] -ne 'KafkaScenarioProduce' -or [string]$fields['outcome'] -ne 'SUCCESS' -or -not $fields.ContainsKey('semantic_json_b64')){continue}
        try{$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$fields['semantic_json_b64']));$sem=$raw|ConvertFrom-Json}catch{continue}
        if([string]$sem.scenario -eq $Scenario){$matches.Add($sem)}
    }
    if($matches.Count -lt 1){return $null}
    return $matches[$matches.Count-1]
}

function Get-LatestConsumerLifecycleSemantic() {
    $latest=$null
    if(-not (Test-Path -LiteralPath $EvidenceDir -PathType Container)){return $null}
    foreach($file in @(Get-ChildItem -LiteralPath $EvidenceDir -File -Filter 'action-*.log' -Force|Sort-Object FullName)){
        $fields=Read-ProxyEvidenceFields $file.FullName
        if([string]$fields['action'] -ne 'ConsumerLifecycle' -or [string]$fields['outcome'] -ne 'SUCCESS' -or -not $fields.ContainsKey('semantic_json_b64')){continue}
        try{$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$fields['semantic_json_b64']));$sem=$raw|ConvertFrom-Json}catch{continue}
        if([string]$sem.kind -eq 'ConsumerLifecycleResult' -and [string]$sem.runtime_mode -eq 'scheduler-pod-temporary-process' -and ([string]$sem.operation).StartsWith('bind-',[StringComparison]::OrdinalIgnoreCase)){$latest=$sem}
    }
    return $latest
}

function Get-ScenarioPolicyValue($Map,[string]$Scenario,[string]$Label) {
    $prop=@($Map.PSObject.Properties|Where-Object{$_.Name -eq $Scenario}|Select-Object -First 1)[0]
    if(-not $prop){throw "UAT_ACTION_POLICY_DENIED: missing $Label policy for scenario $Scenario"}
    $value=([string]$prop.Value).Trim().ToLowerInvariant()
    if($value -notin @('primary','secondary')){throw "UAT_ACTION_POLICY_DENIED: invalid $Label policy for scenario $Scenario"}
    return $value
}

function Invoke-ConsumerObserve($Request,$Policy) {
    Assert-RequiredTokens @('exec') 'ConsumerObserve'
    $scenario=([string]$Request.scenario).Trim()
    $isReplay=$scenario -eq 'future-period-replay'
    if(-not $isReplay -and @($Policy.kafka_scenarios|ForEach-Object{[string]$_}) -notcontains $scenario){throw "UAT_ACTION_POLICY_DENIED: ConsumerObserve scenario invalid"}
    $observeBoundRole=Get-ScenarioPolicyValue $Policy.scenario_observe_bound_role $scenario 'scenario_observe_bound_role'
    $latestLife=Get-LatestConsumerLifecycleSemantic
    if(-not $latestLife -or ([string]$latestLife.operation).ToLowerInvariant() -ne ("bind-{0}" -f $observeBoundRole)){throw "UAT_ENV_BLOCKED: ConsumerObserve required Consumer binding mismatch for scenario $scenario expected=bind-$observeBoundRole"}
    $runtimeTarget=Resolve-ConsumerRuntimeTarget $Request $Policy 'ConsumerObserve'
    $pod=[string]$runtimeTarget.Pod;$container=[string]$runtimeTarget.Container;$candidate=[string]$runtimeTarget.Candidate;$repo=[string]$runtimeTarget.Repo
    if(([string]$latestLife.pod).ToLowerInvariant() -ne $pod -or [string]$latestLife.container -ne $container){throw 'UAT_ENV_BLOCKED: ConsumerObserve binding refers to a replaced scheduler Pod'}
    $sourceScenario=if($isReplay){'future-period'}else{$scenario}
    $kafka=Get-KafkaScenarioSemantic $sourceScenario;if(-not $kafka){throw "UAT_ACTION_POLICY_DENIED: ConsumerObserve requires prior controller-owned KafkaScenarioProduce evidence for scenario $sourceScenario"}
    $records=@($kafka.deliveries)
    if($isReplay){$records=@($records|Where-Object{[string]$_.role -eq 'future'})}
    if($records.Count -lt 1){throw "UAT_ACTION_POLICY_DENIED: ConsumerObserve found no delivered identities"}
    $ctx=Get-StageUatPeriodContext
    $ledgerPrefix="pvam:uat:work02:${ExecutionId}:"
    $input=ConvertTo-Json -Depth 20 -InputObject @($records|ForEach-Object{[ordered]@{
        identity=[string]$_.key;topic=[string]$_.topic;partition=[int]$_.partition;offset=[long]$_.offset;period=[int]$_.period;role=[string]$_.role;
        payload=$_.payload;payload_sha256=[string]$_.payload_sha256;sent_at=[string]$_.sent_at
    }}) -Compress
    $inputB64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($input))
    $tail=[int]$Policy.consumer_exception_tail_per_partition;if($tail -lt 1 -or $tail -gt 5000){throw "UAT_ACTION_POLICY_DENIED: consumer exception tail policy invalid"}
    $timeout=[int]$Policy.consumer_exception_observe_timeout_seconds;if($timeout -lt 1 -or $timeout -gt 60){throw "UAT_ACTION_POLICY_DENIED: consumer exception timeout policy invalid"}
    $exceptionTopic=([string]$Policy.consumer_exception_topic).Trim();if(-not $exceptionTopic){throw "UAT_ACTION_POLICY_DENIED: consumer exception topic policy missing"}
    $code=@'
import base64,json,os,redis,sys,time
from decimal import Decimal, InvalidOperation
from confluent_kafka import Consumer,TopicPartition
rows=json.loads(base64.b64decode(sys.argv[1])); base=sys.argv[2]; scenario=sys.argv[3]; execution=sys.argv[4]; exception_topic=sys.argv[5]; tail=int(sys.argv[6]); timeout=float(sys.argv[7]); primary=int(sys.argv[8]); secondary=int(sys.argv[9])
r=redis.Redis(host=os.environ['PVAM_REDIS_HOST'],port=int(os.environ['PVAM_REDIS_PORT']),db=int(os.environ['PVAM_REDIS_DB']),password=os.environ.get('PVAM_REDIS_PASSWORD') or None,decode_responses=True)
def idem(period,ident):
    keys={'userstats':f'system:idempotency:{period}:{ident}:done','placement':f'system:idempotency:placement:{period}:{ident}:done','elite':f'system:idempotency:elite:{period}:{ident}:done'}
    return keys,{k:bool(r.exists(v)) for k,v in keys.items()}
def as_units(payload):
    raw=payload.get('amount') if payload.get('type')=='refund' else payload.get('bv')
    if raw is None:return None
    try:
        value=Decimal(str(raw))*Decimal(1000000)
        if value != value.to_integral_value(): return None
        return int(value)
    except (InvalidOperation,ValueError,TypeError): return None
out=[]
for row in rows:
    ident=str(row['identity']); period=int(row['period']); payload=row.get('payload') or {}; original=str(payload.get('original_order_id') or '')
    delivery_key=base+'event_delivery:'+ident; delivery_type=r.type(delivery_key); status=r.hget(delivery_key,'status') if delivery_type=='hash' else None
    order_key=base+'order_ledger:'+ident; order_type=r.type(order_key); order_fields=r.hgetall(order_key) if order_type=='hash' else {}
    refund_target=original or ident; refund_key=base+'refund_reversal:'+refund_target; refund_type=r.type(refund_key); refund_fields=r.hgetall(refund_key) if refund_type=='hash' else {}
    current_keys,current_exists=idem(period,ident); primary_keys,primary_exists=idem(primary,ident); secondary_keys,secondary_exists=idem(secondary,ident)
    out.append({'identity':ident,'topic':str(row['topic']),'partition':int(row['partition']),'offset':int(row['offset']),'period':period,'role':str(row.get('role') or ''),'payload':payload,'payload_sha256':str(row.get('payload_sha256') or ''),'expected_amount_units':as_units(payload),'delivery_key':delivery_key,'delivery_status':status,'delivery_exists':bool(r.exists(delivery_key)),'order_ledger_key':order_key,'order_ledger_exists':bool(r.exists(order_key)),'order_ledger_fields':order_fields,'refund_reversal_key':refund_key,'refund_reversal_exists':bool(r.exists(refund_key)),'refund_reversal_fields':refund_fields,'idempotency_keys':current_keys,'idempotency_namespaces':current_exists,'idempotency_primary_keys':primary_keys,'idempotency_primary':primary_exists,'idempotency_secondary_keys':secondary_keys,'idempotency_secondary':secondary_exists})
bootstrap=os.environ['PVAM_KAFKA_BOOTSTRAP']; group='pvam-pv-consumer'; c=Consumer({'bootstrap.servers':bootstrap,'group.id':group,'enable.auto.commit':False})
try:
    unique={}
    for x in out: unique[(x['topic'],x['partition'])]=TopicPartition(x['topic'],x['partition'])
    committed=c.committed(list(unique.values()),timeout=10); cmap={(tp.topic,tp.partition):int(tp.offset) for tp in committed}
finally:c.close()
for x in out:x['committed_offset']=cmap.get((x['topic'],x['partition']),-1001)
ids={x['identity'] for x in out}; exceptions=[]
e=Consumer({'bootstrap.servers':bootstrap,'group.id':'pvam-uat-observe-'+execution+'-'+scenario,'enable.auto.commit':False,'auto.offset.reset':'earliest'})
try:
    md=e.list_topics(exception_topic,timeout=10); topic_md=md.topics.get(exception_topic)
    if topic_md is not None and topic_md.error is None:
        assigned=[]
        for pid in sorted(topic_md.partitions):
            low,high=e.get_watermark_offsets(TopicPartition(exception_topic,pid),timeout=10); assigned.append(TopicPartition(exception_topic,pid,max(low,high-tail)))
        if assigned:
            e.assign(assigned); deadline=time.time()+timeout
            while time.time()<deadline:
                msg=e.poll(0.5)
                if msg is None or msg.error():continue
                try:rec=json.loads(msg.value())
                except Exception:continue
                if str(rec.get('event_identity') or '') in ids:
                    exceptions.append({'identity':str(rec.get('event_identity')),'reason':str(rec.get('reason')),'failed_stage':str(rec.get('failed_stage')),'source_topic':str(rec.get('source_topic')),'source_partition':rec.get('source_partition'),'source_offset':rec.get('source_offset'),'payload_hash':rec.get('payload_hash')})
finally:e.close()
print(json.dumps({'kind':'ConsumerRuntimeObservation','observations':out,'exceptions':exceptions},sort_keys=True))
'@
    $runtime=Invoke-RuntimePythonCommand $pod $container $repo $Policy $code @($inputB64,$ledgerPrefix,$scenario,$ExecutionId,$exceptionTopic,[string]$tail,[string]$timeout,[string]$ctx.Primary,[string]$ctx.Secondary)
    if($runtime.ExitCode -ne 0){return $runtime}
    $json=(@($runtime.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1);if(-not $json){throw "UAT_ENV_BLOCKED: ConsumerObserve runtime observation missing"};$obs=([string]$json)|ConvertFrom-Json
    if(-not $kafka.business_snapshot_before -or -not [string]$kafka.uat_user_id){throw 'UAT_ENV_BLOCKED: controller business snapshot before delivery is missing'}
    $businessSnapshotBefore=$kafka.business_snapshot_before
    $businessSnapshotAfter=Invoke-UserStatsSnapshot $pod $container $repo $Policy ([string]$kafka.uat_user_id) @([int]$ctx.Primary,[int]$ctx.Secondary)
    $primaryBefore=Get-UserStatsPeriodSnapshot $businessSnapshotBefore ([int]$ctx.Primary);$primaryAfter=Get-UserStatsPeriodSnapshot $businessSnapshotAfter ([int]$ctx.Primary)
    $secondaryBefore=Get-UserStatsPeriodSnapshot $businessSnapshotBefore ([int]$ctx.Secondary);$secondaryAfter=Get-UserStatsPeriodSnapshot $businessSnapshotAfter ([int]$ctx.Secondary)
    $primaryBusinessDeltaUnits=[long]$primaryAfter.pv-[long]$primaryBefore.pv;$secondaryBusinessDeltaUnits=[long]$secondaryAfter.pv-[long]$secondaryBefore.pv

    $runtimeLogs=Get-ConsumerRuntimeLogs $pod $container
    $combinedLogText=(@($runtimeLogs.lines) -join "`n")
    $drainDetected=$combinedLogText.Contains('PERIOD DRAIN COMPLETE')

    $positive=(@($Policy.scenarios_require_dispatched_three_chain|ForEach-Object{[string]$_}) -contains $scenario) -or $isReplay
    if($positive){foreach($row in @($obs.observations)){if([string]$row.delivery_status -ne 'DISPATCHED'){throw "UAT_ENV_BLOCKED: delivery ledger is not DISPATCHED for $($row.identity)"};foreach($ns in @('userstats','placement','elite')){if(-not [bool]$row.idempotency_namespaces.$ns){throw "UAT_ENV_BLOCKED: missing $ns idempotency done key for $($row.identity)"}}}}
    $offsetProp=@($Policy.scenario_expected_offset_semantics.PSObject.Properties|Where-Object{$_.Name -eq $scenario}|Select-Object -First 1)[0];$offsetExpectation=if($offsetProp){[string]$offsetProp.Value}else{''};$offsetOk=$true
    foreach($row in @($obs.observations)){$committed=[long]$row.committed_offset;$source=[long]$row.offset;if($offsetExpectation -eq 'committed' -and $committed -le $source){$offsetOk=$false};if($offsetExpectation -eq 'not-committed' -and $committed -gt $source){$offsetOk=$false}}
    if(-not $offsetOk){throw "UAT_ENV_BLOCKED: ConsumerObserve consumer-group offset semantics mismatch for scenario $scenario expectation=$offsetExpectation"}
    $reasonProp=@($Policy.scenario_expected_exception_reason.PSObject.Properties|Where-Object{$_.Name -eq $scenario}|Select-Object -First 1)[0];$expectedReason=if($reasonProp){[string]$reasonProp.Value}else{''}
    if($expectedReason){$matched=@($obs.exceptions|Where-Object{[string]$_.reason -eq $expectedReason});if($matched.Count -lt 1){throw "UAT_ENV_BLOCKED: expected exception reason $expectedReason was not observed for scenario $scenario"}}

    $noSideEffectRequired=@($Policy.scenarios_require_no_redis_side_effects|ForEach-Object{[string]$_}) -contains $scenario
    $noRedisSideEffectsOk=$true
    if($noSideEffectRequired){
        foreach($row in @($obs.observations)){
            if([bool]$row.delivery_exists -or [bool]$row.order_ledger_exists -or [bool]$row.refund_reversal_exists){$noRedisSideEffectsOk=$false}
            foreach($ns in @('userstats','placement','elite')){if([bool]$row.idempotency_primary.$ns -or [bool]$row.idempotency_secondary.$ns){$noRedisSideEffectsOk=$false}}
        }
        if(-not $noRedisSideEffectsOk){throw "UAT_ENV_BLOCKED: negative scenario produced forbidden Redis side effects: $scenario"}
    }

    $pauseBarrierOk=$false
    if($scenario -eq 'future-period'){
        $pauseBarrierOk=$true
        $futureRows=@($obs.observations|Where-Object{[string]$_.role -eq 'future'});$guardRows=@($obs.observations|Where-Object{[string]$_.role -eq 'guard'})
        if($futureRows.Count -ne 1 -or $guardRows.Count -ne 1){$pauseBarrierOk=$false}
        foreach($row in @($obs.observations)){
            if([long]$row.committed_offset -gt [long]$row.offset -or [bool]$row.delivery_exists -or [bool]$row.order_ledger_exists -or [bool]$row.refund_reversal_exists){$pauseBarrierOk=$false}
            foreach($ns in @('userstats','placement','elite')){if([bool]$row.idempotency_primary.$ns -or [bool]$row.idempotency_secondary.$ns){$pauseBarrierOk=$false}}
        }
        if(-not $pauseBarrierOk){throw 'UAT_ENV_BLOCKED: future-period same-partition pause barrier proof failed'}
    }

    $futureReplayOk=$false
    if($isReplay){
        $futureReplayOk=$true
        foreach($row in @($obs.observations)){if([string]$row.role -ne 'future' -or [string]$row.delivery_status -ne 'DISPATCHED' -or [long]$row.committed_offset -le [long]$row.offset){$futureReplayOk=$false};foreach($ns in @('userstats','placement','elite')){if(-not [bool]$row.idempotency_secondary.$ns){$futureReplayOk=$false}}}
        if(-not $futureReplayOk){throw 'UAT_ENV_BLOCKED: future-period message was not reprocessed after secondary bind'}
    }

    $crossPeriodRefundOk=$false;$primaryOrderAmountUnits=$null;$refundOriginalAmountUnits=$null;$primaryRefundIdempotencyAbsent=$false
    if($scenario -eq 'cross-period-refund'){
        $orderRows=@($obs.observations|Where-Object{[string]$_.role -eq 'original-order'});$refundRows=@($obs.observations|Where-Object{[string]$_.role -eq 'refund'})
        if($orderRows.Count -eq 1 -and $refundRows.Count -eq 1){
            $o=$orderRows[0];$rrow=$refundRows[0];$primaryOrderAmountUnits=[long]$o.expected_amount_units;$refundOriginalAmountUnits=if($rrow.refund_reversal_fields.original_amount_units){[long]$rrow.refund_reversal_fields.original_amount_units}else{-1}
            $primaryRefundIdempotencyAbsent=$true;foreach($ns in @('userstats','placement','elite')){if([bool]$rrow.idempotency_primary.$ns){$primaryRefundIdempotencyAbsent=$false}}
            $secondaryRefundApplied=$true;foreach($ns in @('userstats','placement','elite')){if(-not [bool]$rrow.idempotency_secondary.$ns){$secondaryRefundApplied=$false}}
            $crossPeriodRefundOk=([int]$o.period -eq [int]$ctx.Primary -and [int]$rrow.period -eq [int]$ctx.Secondary -and [string]$o.delivery_status -eq 'DISPATCHED' -and [string]$rrow.delivery_status -eq 'DISPATCHED' -and [string]$o.order_ledger_fields.amount_units -eq [string]$o.expected_amount_units -and [int]$o.order_ledger_fields.period -eq [int]$ctx.Primary -and [string]$rrow.refund_reversal_fields.event_identity -eq [string]$rrow.identity -and $refundOriginalAmountUnits -eq $primaryOrderAmountUnits -and $primaryRefundIdempotencyAbsent -and $secondaryRefundApplied)
        }
        if(-not $crossPeriodRefundOk){throw 'UAT_ENV_BLOCKED: cross-period refund routing/amount proof failed'}
    }

    $duplicateNoDoubleOk=$false;$duplicateDeliveryCount=0
    if($scenario -eq 'duplicate'){
        $duplicateDeliveryCount=@($obs.observations).Count;$ids=@($obs.observations|ForEach-Object{[string]$_.identity}|Select-Object -Unique);$hashes=@($obs.observations|ForEach-Object{[string]$_.payload_sha256}|Select-Object -Unique)
        if($duplicateDeliveryCount -eq 2 -and $ids.Count -eq 1 -and $hashes.Count -eq 1){$row=@($obs.observations)[0];$duplicateNoDoubleOk=([string]$row.delivery_status -eq 'DISPATCHED' -and [string]$row.order_ledger_fields.amount_units -eq [string]$row.expected_amount_units);foreach($ns in @('userstats','placement','elite')){if(-not [bool]$row.idempotency_namespaces.$ns){$duplicateNoDoubleOk=$false}}}
        if(-not $duplicateNoDoubleOk){throw 'UAT_ENV_BLOCKED: duplicate no-double controller proof failed'}
    }

    $businessValueProofOk=$false;$duplicateBusinessDeltaUnits=$null
    $firstExpected=$null
    foreach($row in @($obs.observations)){if($null -ne $row.expected_amount_units){$firstExpected=[long]$row.expected_amount_units;break}}
    if($scenario -in @('forbidden-field','schema-invalid','expired-period','future-period','drain-sentinel')){
        $businessValueProofOk=(Test-UserStatsPeriodStateEqual $primaryBefore $primaryAfter) -and (Test-UserStatsPeriodStateEqual $secondaryBefore $secondaryAfter)
    }
    elseif($scenario -eq 'future-period-replay'){
        $businessValueProofOk=($null -ne $firstExpected -and $primaryBusinessDeltaUnits -eq 0 -and $secondaryBusinessDeltaUnits -eq $firstExpected -and [string]$secondaryAfter.pv_type -eq 'int' -and [int]$secondaryAfter.amount_encoding_version -eq 2)
    }
    elseif($scenario -eq 'cross-period-refund'){
        $businessValueProofOk=($null -ne $firstExpected -and $primaryBusinessDeltaUnits -eq $firstExpected -and $secondaryBusinessDeltaUnits -eq -$firstExpected -and [string]$primaryAfter.pv_type -eq 'int' -and [string]$secondaryAfter.pv_type -eq 'int' -and [int]$primaryAfter.amount_encoding_version -eq 2 -and [int]$secondaryAfter.amount_encoding_version -eq 2)
    }
    elseif($scenario -eq 'duplicate'){
        $duplicateBusinessDeltaUnits=$primaryBusinessDeltaUnits
        $businessValueProofOk=($null -ne $firstExpected -and $primaryBusinessDeltaUnits -eq $firstExpected -and $secondaryBusinessDeltaUnits -eq 0 -and [string]$primaryAfter.pv_type -eq 'int' -and [int]$primaryAfter.amount_encoding_version -eq 2)
    }
    elseif($scenario -eq 'order'){
        $businessValueProofOk=($null -ne $firstExpected -and $primaryBusinessDeltaUnits -eq $firstExpected -and [string]$primaryAfter.pv_type -eq 'int' -and [int]$primaryAfter.amount_encoding_version -eq 2)
    }
    elseif($scenario -eq 'refund'){
        $businessValueProofOk=($null -ne $firstExpected -and $primaryBusinessDeltaUnits -eq -$firstExpected -and [string]$primaryAfter.pv_type -eq 'int' -and [int]$primaryAfter.amount_encoding_version -eq 2)
    }
    elseif($scenario -eq 'payload-drift'){
        $businessValueProofOk=($null -ne $firstExpected -and $primaryBusinessDeltaUnits -eq $firstExpected -and [string]$primaryAfter.pv_type -eq 'int' -and [int]$primaryAfter.amount_encoding_version -eq 2)
    }
    if(-not $businessValueProofOk){throw "UAT_ENV_BLOCKED: controller business value delta proof failed for scenario $scenario primary_delta=$primaryBusinessDeltaUnits secondary_delta=$secondaryBusinessDeltaUnits"}

    if($scenario -eq 'drain-sentinel' -and -not $drainDetected){throw 'UAT_ENV_BLOCKED: PERIOD DRAIN COMPLETE log evidence missing'}
    $totalLogLines=[int]$runtimeLogs.line_count
    $semantic=[pscustomobject]@{kind='ConsumerObserveResult';runtime_mode='scheduler-pod-temporary-process';scenario=$scenario;source_scenario=$sourceScenario;delivery_status=($(if($positive){'DISPATCHED'}else{'scenario-specific'}));observations=@($obs.observations);exceptions=@($obs.exceptions);expected_exception_reason=$expectedReason;offset_expectation=$offsetExpectation;offset_semantics_ok=$offsetOk;no_redis_side_effects_ok=$noRedisSideEffectsOk;pause_barrier_ok=$pauseBarrierOk;future_replay_ok=$futureReplayOk;cross_period_refund_ok=$crossPeriodRefundOk;primary_order_amount_units=$primaryOrderAmountUnits;refund_original_amount_units=$refundOriginalAmountUnits;primary_refund_idempotency_absent=$primaryRefundIdempotencyAbsent;duplicate_no_double_ok=$duplicateNoDoubleOk;duplicate_delivery_count=$duplicateDeliveryCount;business_value_proof_ok=$businessValueProofOk;business_snapshot_before=$businessSnapshotBefore;business_snapshot_after=$businessSnapshotAfter;primary_business_delta_units=$primaryBusinessDeltaUnits;secondary_business_delta_units=$secondaryBusinessDeltaUnits;duplicate_business_delta_units=$duplicateBusinessDeltaUnits;idempotency_namespaces=@('userstats','placement','elite');log_line_count=$totalLogLines;previous_log_line_count=0;drain_detected=$drainDetected;consumer_log_sha256=(Get-TextSha256 $combinedLogText);candidate_sha=$candidate;pod=$pod;container=$container;pod_repo=$repo}
    return [pscustomobject]@{ExitCode=0;Output=@("scenario=$scenario","observations=$(@($obs.observations).Count)","exceptions=$(@($obs.exceptions).Count)","offset_expectation=$offsetExpectation","no_redis_side_effects_ok=$noRedisSideEffectsOk","pause_barrier_ok=$pauseBarrierOk","future_replay_ok=$futureReplayOk","cross_period_refund_ok=$crossPeriodRefundOk","duplicate_no_double_ok=$duplicateNoDoubleOk","business_value_proof_ok=$businessValueProofOk","primary_business_delta_units=$primaryBusinessDeltaUnits","secondary_business_delta_units=$secondaryBusinessDeltaUnits","candidate_sha=$candidate");Semantic=$semantic}
}
function Test-GitChangedPathAllowed([string]$Path, $Policy) {
    $value = ([string]$Path).Replace('\\','/').Trim()
    foreach($raw in @($Policy.git_change_allowlist)) {
        $pattern = ([string]$raw).Replace('\\','/').Trim()
        if (-not $pattern) { continue }
        if ($pattern.EndsWith('*')) {
            if ($value.StartsWith($pattern.Substring(0,$pattern.Length-1),[StringComparison]::Ordinal)) { return $true }
        }
        elseif ($value -eq $pattern) { return $true }
    }
    return $false
}

function Get-GitChangedHunks([string]$Worktree,[string]$Baseline,[string]$Head,[string]$Path) {
    $diff = Invoke-Native "git" @("-C",$Worktree,"diff","--unified=0","--no-color",("{0}..{1}" -f $Baseline,$Head),"--",$Path)
    if ($diff.ExitCode -ne 0) { throw "GIT_AUDIT_FAILED: git diff --unified=0 failed for $Path" }
    $hunks = New-Object System.Collections.Generic.List[object]
    foreach($line in @($diff.Output)) {
        $m=[regex]::Match([string]$line,'^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@')
        if(-not $m.Success){continue}
        $oldCount=if($m.Groups[2].Success){[int]$m.Groups[2].Value}else{1}
        $newCount=if($m.Groups[4].Success){[int]$m.Groups[4].Value}else{1}
        $hunks.Add([pscustomobject]@{old_start=[int]$m.Groups[1].Value;old_count=$oldCount;new_start=[int]$m.Groups[3].Value;new_count=$newCount})
    }
    return @($hunks.ToArray())
}

function Test-GitChangedHunksAllowed([string]$Worktree,[string]$Baseline,[string]$Head,[string]$Path,$Policy) {
    $guardProp=@($Policy.git_hunk_allowlist.PSObject.Properties|Where-Object{$_.Name -eq $Path}|Select-Object -First 1)[0]
    $actual=@(Get-GitChangedHunks $Worktree $Baseline $Head $Path)
    if(-not $guardProp){return [pscustomobject]@{Allowed=$true;Hunks=$actual}}
    $expected=@($guardProp.Value)
    if($actual.Count -ne $expected.Count){return [pscustomobject]@{Allowed=$false;Hunks=$actual}}
    for($i=0;$i -lt $expected.Count;$i++){
        $a=$actual[$i];$e=$expected[$i]
        if([int]$a.old_start -ne [int]$e.old_start -or [int]$a.old_count -ne [int]$e.old_count -or [int]$a.new_start -ne [int]$e.new_start -or [int]$a.new_count -ne [int]$e.new_count){return [pscustomobject]@{Allowed=$false;Hunks=$actual}}
    }
    return [pscustomobject]@{Allowed=$true;Hunks=$actual}
}

function Invoke-GitAudit($Request, $Policy) {
    # Governed read-only sequence with controller-verifiable semantics.
    # Contract commands: git status --porcelain; git log; git diff; git ls-remote; git merge-base.
    $worktree = ([string]$env:WORKTREE).Trim()
    $baseline = ([string]$env:BASELINE).Trim().ToLowerInvariant()
    $sshUrl = ([string]$env:SSH_URL).Trim()
    if (-not $worktree -or -not (Test-Path -LiteralPath $worktree -PathType Container)) { throw "GIT_AUDIT_FAILED: WORKTREE missing" }
    if ($baseline -notmatch '^[0-9a-f]{40}$') { throw "GIT_AUDIT_FAILED: BASELINE invalid" }
    if (-not $sshUrl) { throw "GIT_AUDIT_FAILED: SSH_URL missing" }

    $status = Invoke-Native "git" @("-C",$worktree,"status","--porcelain=v1","--untracked-files=all")
    if ($status.ExitCode -ne 0) { throw "GIT_AUDIT_FAILED: git status failed" }
    $dirty = @($status.Output | Where-Object { ([string]$_).Trim() })
    $local = Invoke-Native "git" @("-C",$worktree,"rev-parse","HEAD")
    if ($local.ExitCode -ne 0) { throw "GIT_AUDIT_FAILED: git rev-parse HEAD failed" }
    $localHead = ((@($local.Output | Where-Object { ([string]$_).Trim() -match '^[0-9a-fA-F]{40}$' }) | Select-Object -Last 1) -as [string]).Trim().ToLowerInvariant()
    $log = Invoke-Native "git" @("-C",$worktree,"log","--oneline",("{0}..HEAD" -f $baseline))
    if ($log.ExitCode -ne 0) { throw "GIT_AUDIT_FAILED: git log failed" }
    $diff = Invoke-Native "git" @("-C",$worktree,"diff","--stat",("{0}..HEAD" -f $baseline))
    if ($diff.ExitCode -ne 0) { throw "GIT_AUDIT_FAILED: git diff failed" }
    $diffNames = Invoke-Native "git" @("-C",$worktree,"diff","--name-only",("{0}..HEAD" -f $baseline))
    if ($diffNames.ExitCode -ne 0) { throw "GIT_AUDIT_FAILED: git diff --name-only failed" }
    $changedFiles = @($diffNames.Output | ForEach-Object { ([string]$_).Replace('\\','/').Trim() } | Where-Object { $_ } | Select-Object -Unique)
    foreach($file in $changedFiles) { if (-not (Test-GitChangedPathAllowed $file $Policy)) { throw "GIT_AUDIT_FAILED: unauthorized changed file outside WORK-PVAM-02 changed file allowlist: $file" } }
    $changedHunks = New-Object System.Collections.Generic.List[object]
    foreach($file in $changedFiles){
        $hunkResult=Test-GitChangedHunksAllowed $worktree $baseline $localHead $file $Policy
        foreach($h in @($hunkResult.Hunks)){$changedHunks.Add([pscustomobject]@{path=$file;old_start=[int]$h.old_start;old_count=[int]$h.old_count;new_start=[int]$h.new_start;new_count=[int]$h.new_count})}
        if(-not [bool]$hunkResult.Allowed){throw "GIT_AUDIT_FAILED: changed hunk outside WORK-PVAM-02 line-level contract: $file"}
    }
    $remote = Invoke-Native "git" @("ls-remote",$sshUrl,("refs/heads/{0}" -f $TargetBranch))
    if ($remote.ExitCode -ne 0) { throw "GIT_AUDIT_FAILED: git ls-remote failed" }
    $remoteHead = ""
    foreach ($line in @($remote.Output)) { if (([string]$line).Trim() -match '^([0-9a-fA-F]{40})\s+') { $remoteHead=$matches[1].ToLowerInvariant(); break } }
    $merge = Invoke-Native "git" @("-C",$worktree,"merge-base",$baseline,"HEAD")
    if ($merge.ExitCode -ne 0) { throw "GIT_AUDIT_FAILED: git merge-base failed" }
    $mergeBase = ((@($merge.Output | Where-Object { ([string]$_).Trim() -match '^[0-9a-fA-F]{40}$' }) | Select-Object -Last 1) -as [string]).Trim().ToLowerInvariant()
    $candidatePath = Join-Path $MainRepo ".loop-output\\pushed-sha.txt"
    $candidate = if(Test-Path -LiteralPath $candidatePath){([IO.File]::ReadAllText($candidatePath,[Text.Encoding]::UTF8)).Trim().ToLowerInvariant()}else{""}
    if($dirty.Count -gt 0){throw "GIT_AUDIT_FAILED: worktree is dirty"}
    if($candidate -notmatch '^[0-9a-f]{40}$'){throw "GIT_AUDIT_FAILED: pushed candidate SHA missing/invalid"}
    if($localHead -ne $candidate -or $remoteHead -ne $candidate){throw "GIT_AUDIT_FAILED: local/remote candidate SHA mismatch"}
    if($mergeBase -ne $baseline){throw "GIT_AUDIT_FAILED: merge-base does not equal baseline"}

    $handoffPath = Join-Path $MainRepo ".loop-output\\IMPLEMENTATION_HANDOFF.md"
    if (-not (Test-Path -LiteralPath $handoffPath -PathType Leaf)) { throw "GIT_AUDIT_FAILED: IMPLEMENTATION_HANDOFF.md missing" }
    $handoff = [IO.File]::ReadAllText($handoffPath,[Text.Encoding]::UTF8)
    $marker = '## CONTROLLER CANDIDATE CONTRACT'
    $markerIndex = $handoff.LastIndexOf($marker,[StringComparison]::Ordinal)
    if ($markerIndex -lt 0) { throw "GIT_AUDIT_FAILED: controller candidate contract missing from IMPLEMENTATION_HANDOFF.md" }
    $contract = $handoff.Substring($markerIndex)
    $m = [regex]::Match($contract,'(?im)^Candidate SHA:\s*([0-9a-f]{40})\s*$')
    if (-not $m.Success) { throw "GIT_AUDIT_FAILED: handoff candidate SHA missing" }
    $handoffCandidate = $m.Groups[1].Value.ToLowerInvariant()
    if ($handoffCandidate -ne $candidate) { throw "GIT_AUDIT_FAILED: handoff candidate SHA mismatch" }
    $handoffFiles = @([regex]::Matches($contract,'(?m)^- `([^`]+)`\s*$') | ForEach-Object { $_.Groups[1].Value.Replace('\\','/').Trim() } | Where-Object { $_ } | Select-Object -Unique)
    if (($handoffFiles -join "`n") -ne ($changedFiles -join "`n")) { throw "GIT_AUDIT_FAILED: handoff changed file set does not equal git diff changed file allowlist set" }

    $out = @("worktree_clean=True","local_head=$localHead","remote_head=$remoteHead","merge_base=$mergeBase","baseline=$baseline","handoff_candidate_sha=$handoffCandidate") + @($changedFiles | ForEach-Object { "changed_file=$_" }) + @($log.Output) + @($diff.Output)
    $semantic=[pscustomobject]@{kind='GitAuditResult';worktree_clean=$true;local_head=$localHead;remote_head=$remoteHead;merge_base=$mergeBase;baseline=$baseline;target_branch=$TargetBranch;handoff_candidate_sha=$handoffCandidate;changed_files=@($changedFiles);change_allowlist_ok=$true;line_scope_ok=$true;changed_hunks=@($changedHunks.ToArray())}
    return [pscustomobject]@{ExitCode=0;Output=@($out);Semantic=$semantic}
}

function Assert-PytestTargetAllowed([string]$Target, $Policy) {
    if (-not $Target -or $Target -match '[\x00\r\n]' -or $Target -match '^[A-Za-z]:' -or $Target.StartsWith('/')) { throw "UAT_ACTION_POLICY_DENIED: unsafe pytest target" }
    $normalized=$Target.Replace('\\','/')
    $parts=$normalized.Split('::')
    $path=$parts[0]
    foreach ($segment in @($path.Split('/'))) {
        if (-not $segment -or $segment -eq '.' -or $segment -eq '..') { throw "UAT_ACTION_POLICY_DENIED: pytest target directory traversal is forbidden" }
    }
    if ($normalized -notmatch '^[A-Za-z0-9_./:\-\[\]]+$') { throw "UAT_ACTION_POLICY_DENIED: unsafe pytest target" }
    $exact=@($Policy.pytest_selected_exact | ForEach-Object { [string]$_ })
    $prefixes=@($Policy.pytest_selected_prefixes | ForEach-Object { [string]$_ })
    $ok=$exact -contains $path
    if (-not $ok) { foreach($prefix in $prefixes){ if($path.StartsWith($prefix,[StringComparison]::Ordinal)){ $ok=$true; break } } }
    if (-not $ok) { throw "UAT_ACTION_POLICY_DENIED: pytest target outside exact/prefix allowlist: $Target" }
    return $normalized
}

function Invoke-PytestProfile($Request, $Policy, [bool]$Full) {
    Assert-RequiredTokens @("exec") $(if ($Full) { "PytestFull" } else { "PytestSelected" })
    $pod = ([string]$Request.pod).Trim(); $container = ([string]$Request.container).Trim()
    $repo = Get-PodRepoRoot $pod $container $Policy
    $targets = @()
    if (-not $Full) {
        $rawTargets=@($Request.targets | ForEach-Object { ([string]$_).Trim() })
        if ($rawTargets.Count -lt 1 -or $rawTargets.Count -gt 30) { throw "UAT_ACTION_POLICY_DENIED: PytestSelected requires 1..30 targets" }
        $targets=@($rawTargets | ForEach-Object { Assert-PytestTargetAllowed $_ $Policy })
    }
    $code = "import os,sys,pytest;root=os.path.realpath(sys.argv[1]);os.chdir(root);targets=sys.argv[2:];files=[t.split('::',1)[0] for t in targets];assert all(os.path.commonpath([root,os.path.realpath(os.path.join(root,f))])==root for f in files);raise SystemExit(pytest.main(['-q']+targets))"
    $r=Invoke-PodCommand $pod $container (@("python3","-c",$code,$repo) + $targets)
    $r | Add-Member -NotePropertyName Semantic -NotePropertyValue ([pscustomobject]@{kind=($(if($Full){'PytestFullResult'}else{'PytestSelectedResult'}));targets=@($targets);exit_code=[int]$r.ExitCode}) -Force
    return $r
}

function Assert-SafeProducerValue([string]$Value, [string]$Name, [bool]$AllowEmpty=$false) {
    if (-not $Value) { if ($AllowEmpty) { return }; throw "UAT_ACTION_POLICY_DENIED: $Name is required" }
    if ($Value.Length -gt 256 -or $Value -match '[\x00\r\n]') { throw "UAT_ACTION_POLICY_DENIED: invalid $Name" }
}

function Invoke-UserStatsSnapshot($Pod,$Container,[string]$Repo,$Policy,[string]$UserId,[int[]]$Periods) {
    Assert-SafeProducerValue $UserId 'user_id'
    if(-not $Repo){throw 'UAT_ENV_BLOCKED: UserStats snapshot requires verified repository root'}
    $spec=[ordered]@{repo=$Repo;user_id=$UserId;periods=@($Periods|ForEach-Object{[int]$_})}
    $specB64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($spec|ConvertTo-Json -Depth 5 -Compress)))
    $code=@'
import base64,json,sys
spec=json.loads(base64.b64decode(sys.argv[1])); repo=str(spec['repo']); user=str(spec['user_id']); periods=[int(x) for x in spec['periods']]
if repo not in sys.path: sys.path.insert(0,repo)
from redis_om import NotFoundError
from Model.User.UserStats import UserStats
out={}
for period in periods:
    pk=f'{period}:{user}'
    try:
        row=UserStats.get(pk); pv=row.pv if row.pv is not None else 0; ver=row.amount_encoding_version
        out[str(period)]={'exists':True,'pv':int(pv),'pv_type':type(pv).__name__,'amount_encoding_version':ver,'pk':pk}
    except NotFoundError:
        out[str(period)]={'exists':False,'pv':0,'pv_type':'int','amount_encoding_version':None,'pk':pk}
print(json.dumps({'kind':'UserStatsSnapshot','user_id':user,'periods':out},sort_keys=True))
'@
    $r=Invoke-RuntimePythonCommand $Pod $Container $Repo $Policy $code @($specB64)
    if($r.ExitCode -ne 0){throw 'UAT_ENV_BLOCKED: UserStats business snapshot command failed'}
    $json=(@($r.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1)
    if(-not $json){throw 'UAT_ENV_BLOCKED: UserStats business snapshot structured result missing'}
    $snapshot=([string]$json)|ConvertFrom-Json
    if([string]$snapshot.kind -ne 'UserStatsSnapshot' -or [string]$snapshot.user_id -ne $UserId){throw 'UAT_ENV_BLOCKED: UserStats business snapshot identity mismatch'}
    foreach($period in @($Periods)){
        $prop=@($snapshot.periods.PSObject.Properties|Where-Object{$_.Name -eq [string][int]$period}|Select-Object -First 1)[0]
        if(-not $prop){throw "UAT_ENV_BLOCKED: UserStats business snapshot missing period=$period"}
        if([string]$prop.Value.pv_type -ne 'int'){throw "UAT_ENV_BLOCKED: UserStats pv is not strict int for period=$period"}
    }
    return $snapshot
}

function Get-UserStatsPeriodSnapshot($Snapshot,[int]$Period) {
    if(-not $Snapshot -or -not $Snapshot.periods){throw 'UAT_ENV_BLOCKED: UserStats snapshot missing'}
    $prop=@($Snapshot.periods.PSObject.Properties|Where-Object{$_.Name -eq [string]$Period}|Select-Object -First 1)[0]
    if(-not $prop){throw "UAT_ENV_BLOCKED: UserStats snapshot missing period=$Period"}
    return $prop.Value
}

function Test-UserStatsPeriodStateEqual($Before,$After) {
    return ([bool]$Before.exists -eq [bool]$After.exists -and [long]$Before.pv -eq [long]$After.pv -and [string]$Before.amount_encoding_version -eq [string]$After.amount_encoding_version)
}

function Invoke-ControllerUatProducer($Pod,$Container,[string]$Repo,$Policy,$Spec) {
    $specJson=$Spec|ConvertTo-Json -Depth 20 -Compress
    $specB64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($specJson))
    $code=@'
import base64,hashlib,json,os,sys
from datetime import datetime, timezone
from confluent_kafka import Producer
spec=json.loads(base64.b64decode(sys.argv[1]))
scenario=str(spec['scenario']); period=int(spec['period']); seq=int(spec.get('seq',1)); user=str(spec.get('user_id') or 'U-UAT-001'); bv=str(spec.get('bv') or '1500.99'); amount=str(spec.get('amount') if spec.get('amount') is not None else bv); part=spec.get('partition')
def order_payload(order_id,p,bv_value): return {'type':'order','order_id':order_id,'period':p,'user_id':user,'bv':bv_value}
def refund_payload(order_id,p,original,amount_value):
    x={'type':'refund','order_id':order_id,'period':p,'user_id':user,'original_order_id':original,'amount':amount_value}
    if spec.get('approved_at') is not None:x['approved_at']=spec['approved_at']
    return x
def msg(topic,payload,partition=None): return {'topic':topic,'key':str(payload['order_id']),'payload':payload,'partition':partition}
order_id=str(spec.get('order_id') or f'{scenario}-{period}-{seq}'); plan=[]
if scenario in ('order','future-period','expired-period'):
    plan=[msg('pvam-pv-orders',order_payload(order_id,period,bv),part)]
elif scenario=='refund':
    original=str(spec.get('original_order_id') or '')
    if not original: raise RuntimeError('refund requires original_order_id')
    plan=[msg('pvam-pv-refunds',refund_payload(order_id,period,original,amount),part)]
elif scenario=='cross-period-refund':
    refund_id=str(spec.get('refund_order_id') or f'{scenario}-{period+1}-{seq+1}')
    plan=[msg('pvam-pv-orders',order_payload(order_id,period,bv),part),msg('pvam-pv-refunds',refund_payload(refund_id,period+1,order_id,amount),part)]
elif scenario=='duplicate':
    m=msg('pvam-pv-orders',order_payload(order_id,period,bv),part);plan=[m,m]
elif scenario=='payload-drift':
    plan=[msg('pvam-pv-orders',order_payload(order_id,period,bv),part),msg('pvam-pv-orders',order_payload(order_id,period,str(spec.get('drift_bv') or '1501.00')),part)]
elif scenario=='forbidden-field':
    payload=order_payload(order_id,period,bv);fields=spec.get('forbidden_fields') or ['business_revision','previous_business_revision','previous_amount']
    for field in fields:
        payload[field]=1 if field=='business_revision' else (None if field=='previous_business_revision' else bv)
    plan=[msg('pvam-pv-orders',payload,part)]
elif scenario=='schema-invalid':
    payload=order_payload(order_id,period,bv);case=str(spec.get('invalid_case') or 'bv-number')
    if case=='bv-number':payload['bv']=float(bv)
    elif case=='missing-required':payload.pop('user_id',None)
    elif case=='period-zero':payload['period']=0
    elif case=='period-negative':payload['period']=-1
    elif case=='period-bool':payload['period']=True
    elif case=='amount-scale':payload['bv']='1500.999'
    else:raise RuntimeError('unsupported invalid_case')
    plan=[msg('pvam-pv-orders',payload,part)]
elif scenario=='drain-sentinel':
    original=str(spec.get('original_order_id') or '');refund_id=str(spec.get('refund_order_id') or '')
    if not original or not refund_id or spec.get('amount') is None:raise RuntimeError('drain-sentinel requires original/refund ids and amount')
    for partition in range(3):plan.append(msg('pvam-pv-orders',order_payload(f'drain-sentinel-{period}-{seq+partition}',period,'0'),partition))
    for partition in range(3):plan.append(msg('pvam-pv-refunds',refund_payload(refund_id,period,original,amount),partition))
else:raise RuntimeError('unsupported controller UAT scenario')
producer=Producer({'bootstrap.servers':os.environ['PVAM_KAFKA_BOOTSTRAP'],'acks':'all'})
for item in plan:
    reports=[];encoded=json.dumps(item['payload'],ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
    kwargs={'key':item['key'].encode('utf-8'),'value':encoded,'callback':lambda err,m,rr=reports:rr.append((err,m))}
    if item['partition'] is not None:kwargs['partition']=int(item['partition'])
    producer.produce(item['topic'],**kwargs);remaining=producer.flush(30)
    if remaining or len(reports)!=1 or reports[0][0] is not None:raise RuntimeError('Kafka delivery callback incomplete/failed')
    m=reports[0][1]
    print(json.dumps({'topic':item['topic'],'partition':m.partition(),'offset':m.offset(),'key':item['key'],'payload':item['payload'],'payload_sha256':hashlib.sha256(encoded).hexdigest(),'sent_at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False,separators=(',',':')))
'@
    return Invoke-RuntimePythonCommand $Pod $Container $Repo $Policy $code @($specB64)
}

function Invoke-KafkaScenarioProduce($Request, $Policy) {
    Assert-RequiredTokens @("exec", "test-data-write") "KafkaScenarioProduce"
    $scenario=([string]$Request.scenario).Trim()
    if(@($Policy.kafka_scenarios|ForEach-Object{[string]$_}) -notcontains $scenario){throw 'UAT_ACTION_POLICY_DENIED: unsupported Kafka UAT scenario'}
    if($Request.PSObject.Properties.Name -contains 'period_role'){throw 'UAT_ACTION_POLICY_DENIED: KafkaScenarioProduce period_role is controller-owned'}
    $periodRole=Get-ScenarioPolicyValue $Policy.scenario_period_role $scenario 'scenario_period_role';$requiredBoundRole=Get-ScenarioPolicyValue $Policy.scenario_required_bound_role $scenario 'scenario_required_bound_role';$latestLife=Get-LatestConsumerLifecycleSemantic
    if(-not $latestLife -or ([string]$latestLife.operation).ToLowerInvariant() -ne ("bind-{0}" -f $requiredBoundRole)){throw "UAT_ENV_BLOCKED: scenario required Consumer binding mismatch for $scenario expected=bind-$requiredBoundRole"}
    $runtimeTarget=Resolve-ConsumerRuntimeTarget $Request $Policy 'KafkaScenarioProduce'
    $pod=[string]$runtimeTarget.Pod;$container=[string]$runtimeTarget.Container;$repo=[string]$runtimeTarget.Repo
    if(([string]$latestLife.pod).ToLowerInvariant() -ne $pod -or [string]$latestLife.container -ne $container){throw 'UAT_ENV_BLOCKED: KafkaScenarioProduce binding refers to a replaced scheduler Pod'}
    $ctx=Get-StageUatPeriodContext;$period=if($periodRole -eq 'secondary'){[int]$ctx.Secondary}else{[int]$ctx.Primary};if($scenario -eq 'cross-period-refund' -and [int]$ctx.Secondary -ne [int]$ctx.Primary+1){throw 'UAT_ACTION_POLICY_DENIED: cross-period-refund requires adjacent stage periods'}
    $hash=Get-TextSha256 $ExecutionId;$seq=[int](([Convert]::ToUInt32($hash.Substring(0,8),16)%900000)+1000);if($Request.PSObject.Properties.Name -contains 'seq'){$tmp=0;if(-not [int]::TryParse(([string]$Request.seq),[ref]$tmp)-or $tmp -lt 1 -or $tmp -gt 2000000000){throw 'UAT_ACTION_POLICY_DENIED: invalid Kafka seq'};$seq=$tmp}
    $marker="uat-$ExecutionId-";$orderId=([string]$Request.order_id).Trim();if(-not $orderId){$orderId="$marker$scenario-$seq"};if(-not $orderId.StartsWith($marker,[StringComparison]::Ordinal)){throw 'UAT_ACTION_POLICY_DENIED: order_id must use durable execution marker'}
    $selectedPartition=$null;if($Request.PSObject.Properties.Name -contains 'partition'){$part=0;if(-not [int]::TryParse(([string]$Request.partition),[ref]$part)-or $part -lt 0 -or $part -gt 2){throw 'UAT_ACTION_POLICY_DENIED: partition must be 0..2'};$selectedPartition=$part}elseif($scenario -eq 'future-period'){$selectedPartition=[int]([Convert]::ToUInt32($hash.Substring(8,8),16)%3)}
    $spec=[ordered]@{scenario=$scenario;period=$period;seq=$seq;order_id=$orderId;user_id=$(if($Request.PSObject.Properties.Name -contains 'user_id'){([string]$Request.user_id).Trim()}else{'U-UAT-001'});bv=$(if($Request.PSObject.Properties.Name -contains 'bv'){([string]$Request.bv).Trim()}else{'1500.99'});amount=$(if($Request.PSObject.Properties.Name -contains 'amount'){([string]$Request.amount).Trim()}else{$null});drift_bv=$(if($Request.PSObject.Properties.Name -contains 'drift_bv'){([string]$Request.drift_bv).Trim()}else{'1501.00'});approved_at=$(if($Request.PSObject.Properties.Name -contains 'approved_at'){([string]$Request.approved_at).Trim()}else{$null});invalid_case=$(if($Request.PSObject.Properties.Name -contains 'invalid_case'){([string]$Request.invalid_case).Trim()}else{'bv-number'});partition=$selectedPartition;original_order_id=$(if($Request.PSObject.Properties.Name -contains 'original_order_id'){([string]$Request.original_order_id).Trim()}else{$null});refund_order_id=$(if($Request.PSObject.Properties.Name -contains 'refund_order_id'){([string]$Request.refund_order_id).Trim()}else{$null});forbidden_fields=@($Request.forbidden_fields|ForEach-Object{([string]$_).Trim()}|Where-Object{$_})}
    foreach($name in @('user_id','bv','drift_bv')){Assert-SafeProducerValue ([string]$spec[$name]) $name};foreach($name in @('amount','approved_at','invalid_case')){if($null -ne $spec[$name]){Assert-SafeProducerValue ([string]$spec[$name]) $name}}
    foreach($name in @('original_order_id','refund_order_id')){if($spec[$name]){Assert-SafeProducerValue ([string]$spec[$name]) $name;if(-not ([string]$spec[$name]).StartsWith($marker,[StringComparison]::Ordinal)){throw "UAT_ACTION_POLICY_DENIED: $name must use durable execution marker"}}}
    if($scenario -eq 'cross-period-refund' -and -not $spec.refund_order_id){$spec.refund_order_id="$marker$scenario-refund-$($seq+1)"}
    $businessSnapshotBefore=Invoke-UserStatsSnapshot $pod $container $repo $Policy ([string]$spec.user_id) @([int]$ctx.Primary,[int]$ctx.Secondary)
    $r=Invoke-ControllerUatProducer $pod $container $repo $Policy $spec;if($r.ExitCode -ne 0){return $r};$allOutput=New-Object System.Collections.Generic.List[string];foreach($line in @($r.Output)){$allOutput.Add([string]$line)}
    $futureGuardId='';if($scenario -eq 'future-period'){$futureGuardId="$marker"+"future-period-guard-$seq";$guardSpec=[ordered]@{scenario='order';period=[int]$ctx.Primary;seq=$seq+900001;order_id=$futureGuardId;user_id=[string]$spec.user_id;bv='0';partition=$selectedPartition};$guard=Invoke-ControllerUatProducer $pod $container $repo $Policy $guardSpec;if($guard.ExitCode -ne 0){throw 'UAT_ENV_BLOCKED: future-period guard delivery failed'};foreach($line in @($guard.Output)){$allOutput.Add([string]$line)}}
    $records=New-Object System.Collections.Generic.List[object]
    foreach($line in @($allOutput.ToArray())){$t=([string]$line).Trim();if(-not $t.StartsWith('{')){continue};try{$o=$t|ConvertFrom-Json}catch{continue};if(@($Policy.kafka_topics|ForEach-Object{[string]$_}) -notcontains [string]$o.topic){throw 'KAFKA_DELIVERY_EVIDENCE_INVALID: unexpected topic'};if($null -eq $o.partition -or $null -eq $o.offset){throw 'KAFKA_DELIVERY_EVIDENCE_INVALID: partition/offset missing'};$key=([string]$o.key).Trim();if(-not $key.StartsWith($marker,[StringComparison]::Ordinal)-and -not($scenario -eq 'drain-sentinel'-and $key.StartsWith("drain-sentinel-$period-",[StringComparison]::Ordinal))){throw 'KAFKA_DELIVERY_EVIDENCE_INVALID: key is not bound to durable execution identity'};$role=$scenario;if($scenario -eq 'cross-period-refund'){$role=if([string]$o.topic -eq 'pvam-pv-orders'){'original-order'}else{'refund'}}elseif($scenario -eq 'future-period'){$role=if($key -eq $futureGuardId){'guard'}else{'future'}}elseif($scenario -eq 'duplicate'){$role='duplicate'};$records.Add([pscustomobject]@{topic=[string]$o.topic;key=$key;partition=[int]$o.partition;offset=[long]$o.offset;period=[int]$o.payload.period;role=$role;payload=$o.payload;payload_sha256=[string]$o.payload_sha256;sent_at=[string]$o.sent_at})}
    if($records.Count -lt 1){throw 'KAFKA_DELIVERY_EVIDENCE_INVALID: controller UAT producer returned no delivery evidence'}
    if($scenario -eq 'future-period'){$future=@($records.ToArray()|Where-Object{[string]$_.role -eq 'future'});$guard=@($records.ToArray()|Where-Object{[string]$_.role -eq 'guard'});if($future.Count -ne 1 -or $guard.Count -ne 1 -or [int]$future[0].partition -ne [int]$guard[0].partition -or [long]$guard[0].offset -le [long]$future[0].offset){throw 'KAFKA_DELIVERY_EVIDENCE_INVALID: future-period pause guard is not ordered on same partition'}}
    $deliveries=@($records.ToArray());$deliveredKeys=@($deliveries|ForEach-Object{[string]$_.key}|Select-Object -Unique);$r.Output=@($allOutput.ToArray());$r|Add-Member -NotePropertyName Semantic -NotePropertyValue ([pscustomobject]@{kind='KafkaScenarioResult';scenario=$scenario;period=$period;uat_execution_id=$ExecutionId;delivery_count=$deliveries.Count;delivered_keys=$deliveredKeys;deliveries=$deliveries;future_guard_identity=$futureGuardId;producer_authority='controller-owned-v20';uat_user_id=[string]$spec.user_id;business_snapshot_before=$businessSnapshotBefore}) -Force;return $r
}
function Get-ExpandedRedisPrefixes($Templates) {
    $ctx=Get-StageUatPeriodContext
    $items=New-Object System.Collections.Generic.List[string]
    foreach ($raw in @($Templates)) {
        $t=[string]$raw
        $t=$t.Replace('{uat_execution_id}',$ExecutionId)
        if ($t.Contains('{period}')) {
            $items.Add($t.Replace('{period}',[string]$ctx.Primary)); $items.Add($t.Replace('{period}',[string]$ctx.Secondary))
        } else { $items.Add($t) }
    }
    return $items.ToArray()
}

function Get-DeliveredKafkaKeysFromControllerEvidence() {
    $keys=New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path -LiteralPath $EvidenceDir -PathType Container)) { return $keys.ToArray() }
    foreach($file in @(Get-ChildItem -LiteralPath $EvidenceDir -File -Filter 'action-*.log' -Force)) {
        $fields=Read-ProxyEvidenceFields $file.FullName
        if(([string]$fields['action']) -ne 'KafkaScenarioProduce' -or ([string]$fields['outcome']) -ne 'SUCCESS' -or -not $fields.ContainsKey('semantic_json_b64')){continue}
        try { $raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$fields['semantic_json_b64'])); $s=$raw|ConvertFrom-Json } catch { continue }
        foreach($k in @($s.delivered_keys)){ $v=([string]$k).Trim(); if($v -and -not $keys.Contains($v)){ $keys.Add($v) } }
    }
    return $keys.ToArray()
}

function Test-KeyContainsExactDeliveredIdentity([string]$Key) {
    foreach($identity in @(Get-DeliveredKafkaKeysFromControllerEvidence)) {
        if($Key.EndsWith($identity,[StringComparison]::Ordinal) -or $Key.Contains(":"+$identity+":") -or $Key.Contains(":"+$identity+"_")){ return $true }
    }
    return $false
}

function Test-RedisKeyGoverned([string]$Key,$Templates) {
    if (-not $Key -or $Key -match '[\x00\r\n ]') { return $false }
    $marker="uat-$ExecutionId-"
    foreach ($prefix in @(Get-ExpandedRedisPrefixes $Templates)) {
        if ($Key.StartsWith($prefix,[StringComparison]::Ordinal)) {
            if ($prefix.StartsWith('pvam:uat:work02:',[StringComparison]::Ordinal)) { return $true }
            if ($Key.Contains($marker)) { return $true }
            if (Test-KeyContainsExactDeliveredIdentity $Key) { return $true }
        }
    }
    return $false
}

function Invoke-RedisExactCleanup($Request, $Policy) {
    Assert-RequiredTokens @("exec", "test-data-write") "RedisDeleteExactKeys"
    $runtimeTarget=Resolve-ConsumerRuntimeTarget $Request $Policy 'RedisDeleteExactKeys'
    $pod=[string]$runtimeTarget.Pod;$container=[string]$runtimeTarget.Container;$repo=[string]$runtimeTarget.Repo
    $keys=@($Request.keys | ForEach-Object { [string]$_ })
    if ($keys.Count -lt 1 -or $keys.Count -gt 100) { throw "UAT_ACTION_POLICY_DENIED: Redis cleanup requires 1..100 exact keys" }
    foreach ($key in $keys) { if (-not (Test-RedisKeyGoverned $key $Policy.redis_exact_cleanup_prefixes)) { throw "UAT_ACTION_POLICY_DENIED: Redis key outside durable execution/period scope or exact delivered Kafka identity: $key" } }
    $keysJson=ConvertTo-Json -InputObject $keys -Compress
    if (-not $keysJson.TrimStart().StartsWith('[',[StringComparison]::Ordinal)) { throw "REDIS_CLEANUP_SHAPE_INVALID: serialized exact-key list is not a JSON array" }
    $b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($keysJson))
    $code="import base64,json,os,sys,redis;r=redis.Redis(host=os.environ['PVAM_REDIS_HOST'],port=int(os.environ['PVAM_REDIS_PORT']),db=int(os.environ['PVAM_REDIS_DB']),password=os.environ.get('PVAM_REDIS_PASSWORD') or None,decode_responses=True);ks=json.loads(base64.b64decode(sys.argv[1]));assert isinstance(ks,list) and all(isinstance(k,str) for k in ks);deleted=int(r.delete(*ks));remaining=[k for k in ks if r.exists(k)];print(json.dumps({'kind':'RedisDeleteResult','requested_count':len(ks),'deleted_count':deleted,'remaining_count':len(remaining),'remaining':remaining,'requested_keys':ks},sort_keys=True))"
    $r=Invoke-RuntimePythonCommand $pod $container $repo $Policy $code @($b64)
    if($r.ExitCode -eq 0){ $json=(@($r.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1); if(-not $json){throw 'REDIS_CLEANUP_RESULT_INVALID: no structured result'}; $s=([string]$json)|ConvertFrom-Json; if([int]$s.remaining_count -ne 0){throw 'REDIS_CLEANUP_INCOMPLETE: exact keys remain after delete'}; $r|Add-Member -NotePropertyName Semantic -NotePropertyValue $s -Force }
    return $r
}

function Get-RedisProofKeys([string]$ProofId,$Policy) {
    $contractProp=@($Policy.redis_proof_contracts.PSObject.Properties|Where-Object{$_.Name -eq $ProofId}|Select-Object -First 1)[0]
    if(-not $contractProp){throw "UAT_ACTION_POLICY_DENIED: unknown Redis proof_id: $ProofId"}
    $scenario=[string]$contractProp.Value.scenario
    $kafka=Get-KafkaScenarioSemantic $scenario
    if(-not $kafka){throw "UAT_ACTION_POLICY_DENIED: Redis proof requires prior KafkaScenarioProduce evidence for $scenario"}
    $base="pvam:uat:work02:${ExecutionId}:"
    $keys=New-Object System.Collections.Generic.List[string]
    if($ProofId -eq 'cross-period-refund-ledgers'){
        $order=@($kafka.deliveries|Where-Object{[string]$_.role -eq 'original-order'});$refund=@($kafka.deliveries|Where-Object{[string]$_.role -eq 'refund'})
        if($order.Count -ne 1 -or $refund.Count -ne 1){throw 'UAT_ACTION_POLICY_DENIED: cross-period Redis proof delivery roles invalid'}
        $orderId=[string]$order[0].key;$refundId=[string]$refund[0].key
        foreach($k in @($base+'order_ledger:'+$orderId,$base+'refund_reversal:'+$orderId,$base+'event_delivery:'+$orderId,$base+'event_delivery:'+$refundId)){$keys.Add($k)}
    }
    elseif($ProofId -eq 'duplicate-ledgers'){
        $rows=@($kafka.deliveries);$ids=@($rows|ForEach-Object{[string]$_.key}|Select-Object -Unique)
        if($rows.Count -ne 2 -or $ids.Count -ne 1){throw 'UAT_ACTION_POLICY_DENIED: duplicate Redis proof delivery shape invalid'}
        $id=$ids[0];$keys.Add($base+'order_ledger:'+$id);$keys.Add($base+'event_delivery:'+$id)
    }
    else{throw "UAT_ACTION_POLICY_DENIED: unsupported Redis proof_id: $ProofId"}
    return [pscustomobject]@{ProofId=$ProofId;Scenario=$scenario;Keys=@($keys.ToArray());Kafka=$kafka}
}

function Convert-RedisHashPairsToMap($Pairs) {
    $map=@{}
    foreach($pair in @($Pairs)){if(@($pair).Count -eq 2){$map[[string]$pair[0]]=[string]$pair[1]}}
    return $map
}

function Get-RedisReadKeyItem($Semantic,[string]$Key) {
    $prop=@($Semantic.keys.PSObject.Properties|Where-Object{$_.Name -eq $Key}|Select-Object -First 1)[0]
    if(-not $prop){throw "REDIS_PROOF_INVALID: requested key missing from structured result: $Key"}
    return $prop.Value
}

function Convert-ContractAmountToUnits([string]$Text) {
    $value=0D
    if(-not [decimal]::TryParse($Text,[Globalization.NumberStyles]::Number,[Globalization.CultureInfo]::InvariantCulture,[ref]$value)){throw "REDIS_PROOF_INVALID: amount is not exact decimal"}
    $scaled=$value*1000000D
    if($scaled -ne [decimal]::Truncate($scaled)){throw "REDIS_PROOF_INVALID: amount has more than six decimal places"}
    if($scaled -gt [long]::MaxValue -or $scaled -lt [long]::MinValue){throw "REDIS_PROOF_INVALID: amount outside int64"}
    return [long]$scaled
}

function Test-RedisProofExpectations([string]$ProofId,$ProofCtx,$Semantic) {
    foreach($key in @($ProofCtx.Keys)){$item=Get-RedisReadKeyItem $Semantic $key;if([bool]$item.truncated){return $false}}
    if($ProofId -eq 'cross-period-refund-ledgers'){
        $order=@($ProofCtx.Kafka.deliveries|Where-Object{[string]$_.role -eq 'original-order'})[0];$refund=@($ProofCtx.Kafka.deliveries|Where-Object{[string]$_.role -eq 'refund'})[0]
        $base="pvam:uat:work02:${ExecutionId}:";$orderKey=$base+'order_ledger:'+([string]$order.key);$refundKey=$base+'refund_reversal:'+([string]$order.key);$orderDelivery=$base+'event_delivery:'+([string]$order.key);$refundDelivery=$base+'event_delivery:'+([string]$refund.key)
        $orderItem=Get-RedisReadKeyItem $Semantic $orderKey;$refundItem=Get-RedisReadKeyItem $Semantic $refundKey;$od=Get-RedisReadKeyItem $Semantic $orderDelivery;$rd=Get-RedisReadKeyItem $Semantic $refundDelivery
        if([string]$orderItem.type -ne 'hash' -or [string]$refundItem.type -ne 'hash' -or [string]$od.type -ne 'hash' -or [string]$rd.type -ne 'hash'){return $false}
        $om=Convert-RedisHashPairsToMap $orderItem.value;$rm=Convert-RedisHashPairsToMap $refundItem.value;$odm=Convert-RedisHashPairsToMap $od.value;$rdm=Convert-RedisHashPairsToMap $rd.value
        $expected=Convert-ContractAmountToUnits ([string]$order.payload.bv)
        if([string]$om['amount_units'] -ne [string]$expected -or [int]$om['period'] -ne [int]$order.period){return $false}
        if([string]$rm['original_amount_units'] -ne [string]$expected -or [string]$rm['event_identity'] -ne [string]$refund.key){return $false}
        if([string]$odm['status'] -ne 'DISPATCHED' -or [string]$rdm['status'] -ne 'DISPATCHED'){return $false}
        return $true
    }
    if($ProofId -eq 'duplicate-ledgers'){
        $row=@($ProofCtx.Kafka.deliveries)[0];$base="pvam:uat:work02:${ExecutionId}:";$orderKey=$base+'order_ledger:'+([string]$row.key);$deliveryKey=$base+'event_delivery:'+([string]$row.key)
        $orderItem=Get-RedisReadKeyItem $Semantic $orderKey;$deliveryItem=Get-RedisReadKeyItem $Semantic $deliveryKey
        if([string]$orderItem.type -ne 'hash' -or [string]$deliveryItem.type -ne 'hash'){return $false}
        $om=Convert-RedisHashPairsToMap $orderItem.value;$dm=Convert-RedisHashPairsToMap $deliveryItem.value;$expected=Convert-ContractAmountToUnits ([string]$row.payload.bv)
        return ([string]$om['amount_units'] -eq [string]$expected -and [string]$dm['status'] -eq 'DISPATCHED')
    }
    return $false
}

function Invoke-RedisExactRead($Request, $Policy) {
    Assert-RequiredTokens @("exec") "RedisReadExactKeys"
    $runtimeTarget=Resolve-ConsumerRuntimeTarget $Request $Policy 'RedisReadExactKeys'
    $pod=[string]$runtimeTarget.Pod;$container=[string]$runtimeTarget.Container;$repo=[string]$runtimeTarget.Repo
    $proofId=([string]$Request.proof_id).Trim();$proofCtx=$null
    if($proofId){
        $proofCtx=Get-RedisProofKeys $proofId $Policy;$keys=@($proofCtx.Keys)
        $requested=@($Request.keys|ForEach-Object{[string]$_}|Where-Object{$_})
        if($requested.Count -gt 0 -and (($requested -join "`n") -ne ($keys -join "`n"))){throw 'UAT_ACTION_POLICY_DENIED: Redis proof keys are controller-owned and request does not match'}
    } else {$keys=@($Request.keys | ForEach-Object { [string]$_ })}
    if ($keys.Count -lt 1 -or $keys.Count -gt 100) { throw "UAT_ACTION_POLICY_DENIED: Redis read requires 1..100 exact keys" }
    foreach ($key in $keys) { if (-not (Test-RedisKeyGoverned $key $Policy.redis_read_prefixes)) { throw "UAT_ACTION_POLICY_DENIED: Redis read key outside durable execution/period scope or exact delivered Kafka identity: $key" } }
    $keysJson=ConvertTo-Json -InputObject $keys -Compress; $b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($keysJson))
    $code=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("aW1wb3J0IGJhc2U2NAppbXBvcnQganNvbgppbXBvcnQgb3MKaW1wb3J0IHJlZGlzCmltcG9ydCBzeXMKCnIgPSByZWRpcy5SZWRpcygKICAgIGhvc3Q9b3MuZW52aXJvblsiUFZBTV9SRURJU19IT1NUIl0sCiAgICBwb3J0PWludChvcy5lbnZpcm9uWyJQVkFNX1JFRElTX1BPUlQiXSksCiAgICBkYj1pbnQob3MuZW52aXJvblsiUFZBTV9SRURJU19EQiJdKSwKICAgIHBhc3N3b3JkPW9zLmVudmlyb24uZ2V0KCJQVkFNX1JFRElTX1BBU1NXT1JEIikgb3IgTm9uZSwKICAgIGRlY29kZV9yZXNwb25zZXM9VHJ1ZSwKKQprcyA9IGpzb24ubG9hZHMoYmFzZTY0LmI2NGRlY29kZShzeXMuYXJndlsxXSkpCm1heF9pdGVtcyA9IDEwMAptYXhfdGV4dCA9IDQwOTYKb3V0ID0ge30KZm9yIGsgaW4ga3M6CiAgICB0ID0gci50eXBlKGspCiAgICBpdGVtID0geyJ0eXBlIjogdCwgInRydW5jYXRlZCI6IEZhbHNlfQogICAgaWYgdCA9PSAibm9uZSI6CiAgICAgICAgaXRlbVsidmFsdWUiXSA9IE5vbmUKICAgIGVsaWYgdCA9PSAic3RyaW5nIjoKICAgICAgICB2ID0gci5nZXQoaykKICAgICAgICBpdGVtWyJ2YWx1ZSJdID0gdls6bWF4X3RleHRdIGlmIHYgaXMgbm90IE5vbmUgZWxzZSBOb25lCiAgICAgICAgaXRlbVsidHJ1bmNhdGVkIl0gPSBib29sKHYgaXMgbm90IE5vbmUgYW5kIGxlbih2KSA+IG1heF90ZXh0KQogICAgZWxpZiB0ID09ICJoYXNoIjoKICAgICAgICB2YWxzID0gW10KICAgICAgICBmb3IgaSwgKGYsIHYpIGluIGVudW1lcmF0ZShyLmhzY2FuX2l0ZXIoaykpOgogICAgICAgICAgICBpZiBpID49IG1heF9pdGVtczoKICAgICAgICAgICAgICAgIGl0ZW1bInRydW5jYXRlZCJdID0gVHJ1ZQogICAgICAgICAgICAgICAgYnJlYWsKICAgICAgICAgICAgdmFscy5hcHBlbmQoW3N0cihmKVs6bWF4X3RleHRdLCBzdHIodilbOm1heF90ZXh0XV0pCiAgICAgICAgaXRlbVsidmFsdWUiXSA9IHZhbHMKICAgIGVsaWYgdCA9PSAibGlzdCI6CiAgICAgICAgdmFscyA9IHIubHJhbmdlKGssIDAsIG1heF9pdGVtcykKICAgICAgICBpdGVtWyJ0cnVuY2F0ZWQiXSA9IGxlbih2YWxzKSA+IG1heF9pdGVtcwogICAgICAgIGl0ZW1bInZhbHVlIl0gPSBbc3RyKHgpWzptYXhfdGV4dF0gZm9yIHggaW4gdmFsc1s6bWF4X2l0ZW1zXV0KICAgIGVsaWYgdCA9PSAic2V0IjoKICAgICAgICB2YWxzID0gW10KICAgICAgICBmb3IgaSwgdiBpbiBlbnVtZXJhdGUoci5zc2Nhbl9pdGVyKGspKToKICAgICAgICAgICAgaWYgaSA+PSBtYXhfaXRlbXM6CiAgICAgICAgICAgICAgICBpdGVtWyJ0cnVuY2F0ZWQiXSA9IFRydWUKICAgICAgICAgICAgICAgIGJyZWFrCiAgICAgICAgICAgIHZhbHMuYXBwZW5kKHN0cih2KVs6bWF4X3RleHRdKQogICAgICAgIGl0ZW1bInZhbHVlIl0gPSB2YWxzCiAgICBlbGlmIHQgPT0gInpzZXQiOgogICAgICAgIHZhbHMgPSByLnpyYW5nZShrLCAwLCBtYXhfaXRlbXMsIHdpdGhTY29yZXM9VHJ1ZSkKICAgICAgICBpdGVtWyJ0cnVuY2F0ZWQiXSA9IGxlbih2YWxzKSA+IG1heF9pdGVtcwogICAgICAgIGl0ZW1bInZhbHVlIl0gPSBbW3N0cih2KVs6bWF4X3RleHRdLCBmbG9hdChzKV0gZm9yIHYsIHMgaW4gdmFsc1s6bWF4X2l0ZW1zXV0KICAgIGVsaWYgdCA9PSAic3RyZWFtIjoKICAgICAgICB2YWxzID0gci54cmFuZ2UoaywgY291bnQ9bWF4X2l0ZW1zICsgMSkKICAgICAgICBpdGVtWyJ0cnVuY2F0ZWQiXSA9IGxlbih2YWxzKSA+IG1heF9pdGVtcwogICAgICAgIGl0ZW1bInZhbHVlIl0gPSBbCiAgICAgICAgICAgIFtzdHIoaSksIHtzdHIoZilbOm1heF90ZXh0XTogc3RyKHYpWzptYXhfdGV4dF0gZm9yIGYsIHYgaW4gZmllbGRzLml0ZW1zKCl9XQogICAgICAgICAgICBmb3IgaSwgZmllbGRzIGluIHZhbHNbOm1heF9pdGVtc10KICAgICAgICBdCiAgICBlbHNlOgogICAgICAgIGl0ZW1bInZhbHVlIl0gPSAiPHVuc3VwcG9ydGVkLXR5cGU+IgogICAgb3V0W2tdID0gaXRlbQpwcmludChqc29uLmR1bXBzKHsia2luZCI6ICJSZWRpc1JlYWRSZXN1bHQiLCAibWF4X2l0ZW1zIjogbWF4X2l0ZW1zLCAia2V5cyI6IG91dH0sIHNvcnRfa2V5cz1UcnVlKSkK"))
    $r=Invoke-RuntimePythonCommand $pod $container $repo $Policy $code @($b64)
    if($r.ExitCode -eq 0){
        $json=(@($r.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1);if(-not $json){throw 'REDIS_READ_RESULT_INVALID: no structured result'}
        $s=([string]$json)|ConvertFrom-Json;$expectationsSatisfied=$true;$scenario=''
        if($proofId){$scenario=[string]$proofCtx.Scenario;$expectationsSatisfied=Test-RedisProofExpectations $proofId $proofCtx $s;if(-not $expectationsSatisfied){throw "REDIS_PROOF_INVALID: exact Redis key/value expectations failed for $proofId"}}
        $requestedHash=Get-TextSha256 ($keys -join "`n");$valuesJson=$s.keys|ConvertTo-Json -Depth 20 -Compress;$valuesHash=Get-TextSha256 $valuesJson
        $s|Add-Member -NotePropertyName proof_id -NotePropertyValue $proofId -Force;$s|Add-Member -NotePropertyName scenario -NotePropertyValue $scenario -Force;$s|Add-Member -NotePropertyName expectations_satisfied -NotePropertyValue ([bool]$expectationsSatisfied) -Force;$s|Add-Member -NotePropertyName requested_keys -NotePropertyValue @($keys) -Force;$s|Add-Member -NotePropertyName requested_keys_sha256 -NotePropertyValue $requestedHash -Force;$s|Add-Member -NotePropertyName values_sha256 -NotePropertyValue $valuesHash -Force
        $r|Add-Member -NotePropertyName Semantic -NotePropertyValue $s -Force
    }
    return $r
}
function Invoke-RedisDbSize($Request,$Policy) {
    Assert-RequiredTokens @("exec") "RedisDbSize"
    $runtimeTarget=Resolve-ConsumerRuntimeTarget $Request $Policy 'RedisDbSize'
    $pod=[string]$runtimeTarget.Pod;$container=[string]$runtimeTarget.Container;$repo=[string]$runtimeTarget.Repo
    $phase=([string]$Request.phase).Trim().ToLowerInvariant(); if($phase -notin @('before','after')){throw 'UAT_ACTION_POLICY_DENIED: RedisDbSize phase must be before or after'}
    $code="import json,os,redis,sys;r=redis.Redis(host=os.environ['PVAM_REDIS_HOST'],port=int(os.environ['PVAM_REDIS_PORT']),db=int(os.environ['PVAM_REDIS_DB']),password=os.environ.get('PVAM_REDIS_PASSWORD') or None);print(json.dumps({'kind':'RedisDbSizeResult','phase':sys.argv[1],'dbsize':int(r.dbsize())},sort_keys=True))"
    $r=Invoke-RuntimePythonCommand $pod $container $repo $Policy $code @($phase)
    if($r.ExitCode -eq 0){$json=(@($r.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1);if(-not $json){throw 'REDIS_DBSIZE_RESULT_INVALID'};$r|Add-Member -NotePropertyName Semantic -NotePropertyValue (([string]$json)|ConvertFrom-Json) -Force}
    return $r
}

function Get-LatestActionSemantic([string]$Action,[string]$Scenario='',[string]$ProofId='') {
    $latest=$null
    if(-not (Test-Path -LiteralPath $EvidenceDir -PathType Container)){return $null}
    foreach($file in @(Get-ChildItem -LiteralPath $EvidenceDir -File -Filter 'action-*.log' -Force|Sort-Object FullName)){
        $fields=Read-ProxyEvidenceFields $file.FullName
        if([string]$fields['action'] -ne $Action -or [string]$fields['outcome'] -ne 'SUCCESS' -or -not $fields.ContainsKey('semantic_json_b64')){continue}
        try{$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$fields['semantic_json_b64']));$sem=$raw|ConvertFrom-Json}catch{continue}
        if($Scenario -and [string]$sem.scenario -ne $Scenario){continue}
        if($ProofId -and [string]$sem.proof_id -ne $ProofId){continue}
        $latest=$sem
    }
    return $latest
}

function Test-PytestSelectedTargetSucceeded([string]$Target) {
    if(-not (Test-Path -LiteralPath $EvidenceDir -PathType Container)){return $false}
    foreach($file in @(Get-ChildItem -LiteralPath $EvidenceDir -File -Filter 'action-*.log' -Force|Sort-Object FullName)){
        $fields=Read-ProxyEvidenceFields $file.FullName
        if([string]$fields['action'] -ne 'PytestSelected' -or [string]$fields['outcome'] -ne 'SUCCESS' -or -not $fields.ContainsKey('semantic_json_b64')){continue}
        try{$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$fields['semantic_json_b64']));$sem=$raw|ConvertFrom-Json}catch{continue}
        if(@($sem.targets|ForEach-Object{[string]$_}) -contains $Target){return $true}
    }
    return $false
}

function Invoke-PendingRecoveryProof($Request,$Policy) {
    Assert-RequiredTokens @('exec','test-data-write','restart') 'UatProof:pending-dispatched-recovery'
    $latestLife=Get-LatestConsumerLifecycleSemantic
    if(-not $latestLife){throw 'UAT_ENV_BLOCKED: pending recovery proof requires active Consumer binding'}
    $op=([string]$latestLife.operation).ToLowerInvariant();if($op -notin @('bind-primary','bind-secondary')){throw 'UAT_ENV_BLOCKED: pending recovery proof requires bound Consumer'}
    $ctx=Get-StageUatPeriodContext;$period=if($op -eq 'bind-secondary'){[int]$ctx.Secondary}else{[int]$ctx.Primary}
    $deployment=[string]$latestLife.deployment;$container=[string]$latestLife.container;$target=Get-ConsumerLifecycleTarget $Policy $deployment $container
    $pods=@(Get-ConsumerLifecycleSelectedPods $deployment $container ([string]$target.pod_name_prefix));if($pods.Count -lt 1){throw 'UAT_ENV_BLOCKED: pending recovery proof has no Consumer pod'}
    $pod=[string]$pods[0];Assert-ResourceAllowed 'pod' $pod
    $candidate=Get-CurrentCandidateSha
    $repo=Verify-PodGitView $pod $container ([string]$Policy.repo_remote_url) $candidate
    $nonce=[Guid]::NewGuid().ToString('N').Substring(0,12);$identity="uat-$ExecutionId-pending-recovery-$nonce"
    $userId=if($Request.PSObject.Properties.Name -contains 'user_id'){([string]$Request.user_id).Trim()}else{'U-UAT-001'};Assert-SafeProducerValue $userId 'user_id'
    $ledgerPrefix="pvam:uat:work02:${ExecutionId}:";$deliveryKey=$ledgerPrefix+'event_delivery:'+$identity;$orderKey=$ledgerPrefix+'order_ledger:'+$identity
    $idemKeys=@("system:idempotency:${period}:${identity}:done","system:idempotency:placement:${period}:${identity}:done","system:idempotency:elite:${period}:${identity}:done")
    $snapshotBeforeFirst=Invoke-UserStatsSnapshot $pod $container $repo $Policy $userId @($period)
    $prodSpec=[ordered]@{scenario='order';period=$period;seq=1;order_id=$identity;user_id=$userId;bv='1.00';partition=0}
    $firstProd=Invoke-ControllerUatProducer $pod $container $repo $Policy $prodSpec;if($firstProd.ExitCode -ne 0){return $firstProd}
    $deliveryLine=(@($firstProd.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1);if(-not $deliveryLine){throw 'UAT_ENV_BLOCKED: pending recovery initial producer evidence missing'};$delivery=([string]$deliveryLine)|ConvertFrom-Json
    $waitCode=@'
import json,os,redis,sys,time
r=redis.Redis(host=os.environ['PVAM_REDIS_HOST'],port=int(os.environ['PVAM_REDIS_PORT']),db=int(os.environ['PVAM_REDIS_DB']),password=os.environ.get('PVAM_REDIS_PASSWORD') or None,decode_responses=True)
k=sys.argv[1]; keys=json.loads(sys.argv[2]); end=time.time()+60; status=None
while time.time()<end:
    status=r.hget(k,'status') if r.type(k)=='hash' else None
    if status=='DISPATCHED' and all(r.exists(x) for x in keys): break
    time.sleep(.25)
print(json.dumps({'status':status,'three_chain':all(bool(r.exists(x)) for x in keys),'keys':keys},sort_keys=True))
'@
    $idemJson=$idemKeys|ConvertTo-Json -Compress
    $firstWait=Invoke-RuntimePythonCommand $pod $container $repo $Policy $waitCode @($deliveryKey,$idemJson);if($firstWait.ExitCode -ne 0){return $firstWait}
    $firstJson=(@($firstWait.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1);if(-not $firstJson){throw 'UAT_ENV_BLOCKED: pending recovery initial completion evidence missing'};$firstSem=([string]$firstJson)|ConvertFrom-Json
    if([string]$firstSem.status -ne 'DISPATCHED' -or -not [bool]$firstSem.three_chain){throw 'UAT_ENV_BLOCKED: pending recovery could not establish a completed three-chain event'}
    $snapshotBeforeReplay=Invoke-UserStatsSnapshot $pod $container $repo $Policy $userId @($period);$pre0=Get-UserStatsPeriodSnapshot $snapshotBeforeFirst $period;$preReplay=Get-UserStatsPeriodSnapshot $snapshotBeforeReplay $period
    if(([long]$preReplay.pv-[long]$pre0.pv) -ne 1000000 -or [int]$preReplay.amount_encoding_version -ne 2){throw 'UAT_ENV_BLOCKED: pending recovery initial business dispatch did not apply exactly once'}

    $injectCode=@'
import json,os,redis,sys
r=redis.Redis(host=os.environ['PVAM_REDIS_HOST'],port=int(os.environ['PVAM_REDIS_PORT']),db=int(os.environ['PVAM_REDIS_DB']),password=os.environ.get('PVAM_REDIS_PASSWORD') or None,decode_responses=True)
k=sys.argv[1]; expected=sys.argv[2]; keys=json.loads(sys.argv[3]); current=r.hget(k,'payload_hash'); status=r.hget(k,'status')
if current!=expected or status!='DISPATCHED': raise RuntimeError('delivery ledger is not the expected completed event')
if not all(r.exists(x) for x in keys): raise RuntimeError('stage idempotency markers are not all present before crash-window injection')
r.hset(k,'status','PENDING')
print(json.dumps({'crash_window_injected':True,'status':r.hget(k,'status'),'idempotency_present_before_restart':all(bool(r.exists(x)) for x in keys)},sort_keys=True))
'@
    $inject=Invoke-RuntimePythonCommand $pod $container $repo $Policy $injectCode @($deliveryKey,[string]$delivery.payload_sha256,$idemJson);if($inject.ExitCode -ne 0){return $inject}
    $injectJson=(@($inject.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1);if(-not $injectJson){throw 'UAT_ENV_BLOCKED: pending crash-window injection evidence missing'};$injectSem=([string]$injectJson)|ConvertFrom-Json
    if([string]$injectSem.status -ne 'PENDING' -or -not [bool]$injectSem.crash_window_injected -or -not [bool]$injectSem.idempotency_present_before_restart){throw 'UAT_ENV_BLOCKED: failed to establish PENDING-after-stages crash window'}

    $role=if($op -eq 'bind-secondary'){'secondary'}else{'primary'}
    $runtimePayload=New-ConsumerRuntimePayload $target $role $period ([int]$latestLife.calc_month) $candidate $repo
    $restart=Invoke-ConsumerRuntimeController $pod $container 'replace' $runtimePayload
    if($restart.ExitCode -ne 0 -or -not [bool]$restart.Semantic.running){throw 'UAT_ENV_BLOCKED: pending recovery Consumer process restart failed'}
    $newPod=$pod
    $newRepo=$repo
    $replay=Invoke-ControllerUatProducer $newPod $container $newRepo $Policy $prodSpec;if($replay.ExitCode -ne 0){return $replay}
    $secondWait=Invoke-RuntimePythonCommand $newPod $container $newRepo $Policy $waitCode @($deliveryKey,$idemJson);if($secondWait.ExitCode -ne 0){return $secondWait}
    $secondJson=(@($secondWait.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1);if(-not $secondJson){throw 'UAT_ENV_BLOCKED: pending recovery replay completion evidence missing'};$secondSem=([string]$secondJson)|ConvertFrom-Json
    if([string]$secondSem.status -ne 'DISPATCHED' -or -not [bool]$secondSem.three_chain){throw 'UAT_ENV_BLOCKED: PENDING state did not recover to DISPATCHED after restart/replay'}
    $snapshotAfterReplay=Invoke-UserStatsSnapshot $newPod $container $newRepo $Policy $userId @($period);$postReplay=Get-UserStatsPeriodSnapshot $snapshotAfterReplay $period
    $businessUnchanged=Test-UserStatsPeriodStateEqual $preReplay $postReplay
    if(-not $businessUnchanged){throw 'UAT_ENV_BLOCKED: PENDING replay duplicated or lost business PV'}
    $orderIndexKey=$ledgerPrefix+'order_ledger:__period_index__';$cleanup=@($deliveryKey,$orderKey,$orderIndexKey)+@($idemKeys)
    return [pscustomobject]@{ExitCode=0;Output=@('proof=pending-dispatched-recovery','runtime_mode=scheduler-pod-temporary-process','crash_window_injected=True','idempotency_present_before_restart=True','restart_completed=True','dispatched_after_restart=True','business_unchanged_after_replay=True');Semantic=[pscustomobject]@{kind='UatProofResult';proof_id='pending-dispatched-recovery';runtime_mode='scheduler-pod-temporary-process';passed=$true;period=$period;identity=$identity;payload_hash=[string]$delivery.payload_sha256;pending_before_restart=$true;crash_window_injected=$true;idempotency_present_before_restart=$true;restart_completed=$true;dispatched_after_restart=$true;three_chain_after_restart=$true;business_unchanged_after_replay=$true;business_snapshot_before_replay=$snapshotBeforeReplay;business_snapshot_after_replay=$snapshotAfterReplay;delivered_keys=@($identity);delivered_records=@([pscustomobject]@{identity=$identity;topic='pvam-pv-orders';period=$period;original_order_id=''});cleanup_keys=$cleanup;proof_nonce=$nonce;candidate_sha=$candidate}}
}

function Invoke-DispatchP99Proof($Request,$Policy) {
    Assert-RequiredTokens @('exec','test-data-write') 'UatProof:dispatch-p99'
    $latestLife=Get-LatestConsumerLifecycleSemantic;if(-not $latestLife){throw 'UAT_ENV_BLOCKED: dispatch p99 proof requires active Consumer binding'}
    $op=([string]$latestLife.operation).ToLowerInvariant();if($op -notin @('bind-primary','bind-secondary')){throw 'UAT_ENV_BLOCKED: dispatch p99 proof requires bound Consumer'}
    $ctx=Get-StageUatPeriodContext;$period=if($op -eq 'bind-secondary'){[int]$ctx.Secondary}else{[int]$ctx.Primary}
    $deployment=[string]$latestLife.deployment;$container=[string]$latestLife.container;$target=Get-ConsumerLifecycleTarget $Policy $deployment $container
    $pods=@(Get-ConsumerLifecycleSelectedPods $deployment $container ([string]$target.pod_name_prefix));if($pods.Count -lt 1){throw 'UAT_ENV_BLOCKED: dispatch p99 proof has no current Consumer pod'}
    $pod=[string]$pods[0];Assert-ResourceAllowed 'pod' $pod
    $candidate=Get-CurrentCandidateSha
    $repo=Verify-PodGitView $pod $container ([string]$Policy.repo_remote_url) $candidate
    if($repo -ne ([string]$target.repo_path).Trim()){throw 'UAT_ACTION_POLICY_DENIED: dispatch p99 runtime repository path mismatch'}
    $userId=if($Request.PSObject.Properties.Name -contains 'user_id'){([string]$Request.user_id).Trim()}else{'U-UAT-001'};Assert-SafeProducerValue $userId 'user_id'
    $count=[int]$Policy.dispatch_p99_sample_count;$limit=[int]$Policy.dispatch_p99_max_ms;if($count -lt 5 -or $count -gt 100 -or $limit -lt 1){throw 'UAT_ACTION_POLICY_DENIED: dispatch p99 policy invalid'}
    $base="pvam:uat:work02:${ExecutionId}:";$nonce=[Guid]::NewGuid().ToString('N').Substring(0,12);$code=@'
import json,os,redis,sys,time
from confluent_kafka import Producer
bootstrap=os.environ['PVAM_KAFKA_BOOTSTRAP']; period=int(sys.argv[1]); count=int(sys.argv[2]); base=sys.argv[3]; prefix=sys.argv[4]; nonce=sys.argv[5]; user=sys.argv[6]
r=redis.Redis(host=os.environ['PVAM_REDIS_HOST'],port=int(os.environ['PVAM_REDIS_PORT']),db=int(os.environ['PVAM_REDIS_DB']),password=os.environ.get('PVAM_REDIS_PASSWORD') or None,decode_responses=True)
p=Producer({'bootstrap.servers':bootstrap,'acks':'all'});lat=[];samples=[]
for n in range(count):
    ident=f'{prefix}p99-{nonce}-{n}'; payload={'type':'order','order_id':ident,'period':period,'user_id':user,'bv':'1.00'}; reports=[]; started=time.monotonic()
    p.produce('pvam-pv-orders',key=ident.encode(),value=json.dumps(payload,separators=(',',':')).encode(),callback=lambda e,m,rr=reports:rr.append((e,m.partition(),m.offset())))
    rem=p.flush(10)
    if rem or len(reports)!=1 or reports[0][0] is not None: raise RuntimeError('p99 delivery failed')
    dk=base+'event_delivery:'+ident; ik=[f'system:idempotency:{period}:{ident}:done',f'system:idempotency:placement:{period}:{ident}:done',f'system:idempotency:elite:{period}:{ident}:done']; deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if r.hget(dk,'status')=='DISPATCHED' and all(r.exists(k) for k in ik): break
        time.sleep(.05)
    else: raise RuntimeError('p99 sample did not reach DISPATCHED three-chain')
    completed=time.monotonic(); elapsed=(completed-started)*1000.0; lat.append(elapsed)
    samples.append({'identity':ident,'partition':reports[0][1],'offset':reports[0][2],'latency_ms':elapsed,'sample_completed_at':time.time(),'cleanup_keys':[dk,base+'order_ledger:'+ident,base+'order_ledger:__period_index__']+ik})
ordered=sorted(lat); rank=max(0,min(len(ordered)-1,int((len(ordered)*99+99)//100)-1))
print(json.dumps({'latencies_ms':ordered,'p99_ms':ordered[rank],'samples':samples,'p99_nonce':nonce},sort_keys=True))
'@
    $prefix="uat-$ExecutionId-"
    $r=Invoke-RuntimePythonCommand $pod $container $repo $Policy $code @([string]$period,[string]$count,$base,$prefix,$nonce,$userId);if($r.ExitCode -ne 0){return $r}
    $json=(@($r.Output|Where-Object{([string]$_).Trim().StartsWith('{')})|Select-Object -Last 1);if(-not $json){throw 'UAT_ENV_BLOCKED: dispatch p99 structured result missing'};$x=([string]$json)|ConvertFrom-Json
    if([string]$x.p99_nonce -ne $nonce){throw 'UAT_ENV_BLOCKED: dispatch p99 nonce mismatch'}
    if([double]$x.p99_ms -gt [double]$limit){throw "UAT_ENV_BLOCKED: dispatch p99 exceeds policy limit p99_ms=$($x.p99_ms) limit_ms=$limit"}
    $ids=@($x.samples|ForEach-Object{[string]$_.identity});$records=@($x.samples|ForEach-Object{[pscustomobject]@{identity=[string]$_.identity;topic='pvam-pv-orders';period=$period;original_order_id=''}});$cleanup=@($x.samples|ForEach-Object{@($_.cleanup_keys)}|ForEach-Object{$_})
    $r|Add-Member -NotePropertyName Semantic -NotePropertyValue ([pscustomobject]@{kind='UatProofResult';proof_id='dispatch-p99';passed=$true;p99_ms=[double]$x.p99_ms;limit_ms=$limit;sample_count=$count;period=$period;p99_nonce=$nonce;sample_completed_at=@($x.samples|ForEach-Object{$_.sample_completed_at});delivered_keys=$ids;delivered_records=$records;cleanup_keys=$cleanup;candidate_sha=$candidate}) -Force;return $r
}

function Invoke-UatProof($Request,$Policy) {
    $proofId=([string]$Request.proof_id).Trim();$allowed=@($Policy.mandatory_uat_proofs_by_stage.$Stage|ForEach-Object{[string]$_});if($allowed -notcontains $proofId){throw "UAT_ACTION_POLICY_DENIED: proof_id not required/allowed for stage ${Stage}: $proofId"}
    if($proofId -eq 'pending-dispatched-recovery'){return Invoke-PendingRecoveryProof $Request $Policy}
    if($proofId -eq 'dispatch-p99'){return Invoke-DispatchP99Proof $Request $Policy}
    Assert-RequiredTokens @('exec') ("UatProof:"+$proofId)
    if($proofId -eq 'cross-period-refund-routing'){
        $o=Get-LatestActionSemantic 'ConsumerObserve' 'cross-period-refund';$r=Get-LatestActionSemantic 'RedisReadExactKeys' 'cross-period-refund' 'cross-period-refund-ledgers'
        $passed=($o -and [bool]$o.cross_period_refund_ok -and [bool]$o.business_value_proof_ok -and [bool]$o.primary_refund_idempotency_absent -and [long]$o.primary_business_delta_units -eq [long]$o.primary_order_amount_units -and [long]$o.secondary_business_delta_units -eq -[long]$o.refund_original_amount_units -and $r -and [bool]$r.expectations_satisfied)
        if(-not $passed){throw 'UAT_ENV_BLOCKED: cross-period-refund-routing proof prerequisites not satisfied'}
        return [pscustomobject]@{ExitCode=0;Output=@('proof=cross-period-refund-routing');Semantic=[pscustomobject]@{kind='UatProofResult';proof_id=$proofId;passed=$true;primary_order_amount_units=[long]$o.primary_order_amount_units;refund_delta_units=-[long]$o.refund_original_amount_units;primary_business_delta_units=[long]$o.primary_business_delta_units;secondary_business_delta_units=[long]$o.secondary_business_delta_units;business_value_proof_ok=$true;primary_refund_idempotency_absent=$true;redis_proof_id='cross-period-refund-ledgers'}}
    }
    if($proofId -eq 'duplicate-no-double'){
        $o=Get-LatestActionSemantic 'ConsumerObserve' 'duplicate';$r=Get-LatestActionSemantic 'RedisReadExactKeys' 'duplicate' 'duplicate-ledgers';$rows=if($o){@($o.observations)}else{@()};$expected=if($rows.Count -gt 0){[long]$rows[0].expected_amount_units}else{0};$passed=($o -and [bool]$o.duplicate_no_double_ok -and [bool]$o.business_value_proof_ok -and [int]$o.duplicate_delivery_count -eq 2 -and [long]$o.duplicate_business_delta_units -eq $expected -and $r -and [bool]$r.expectations_satisfied)
        if(-not $passed){throw 'UAT_ENV_BLOCKED: duplicate-no-double proof prerequisites not satisfied'}
        return [pscustomobject]@{ExitCode=0;Output=@('proof=duplicate-no-double');Semantic=[pscustomobject]@{kind='UatProofResult';proof_id=$proofId;passed=$true;duplicate_delivery_count=2;duplicate_business_delta_units=[long]$o.duplicate_business_delta_units;expected_amount_units=$expected;business_value_proof_ok=$true;redis_proof_id='duplicate-ledgers'}}
    }
    if($proofId -eq 'int64-end-to-end'){
        $testOk=Test-PytestSelectedTargetSucceeded 'User/Test/test_amount_dtype_migration.py';$o=Get-LatestActionSemantic 'ConsumerObserve' 'duplicate';$runtimeOk=$false;$businessVersionOk=$false
        if($o){foreach($row in @($o.observations)){if($null -ne $row.expected_amount_units -and ([string]$row.order_ledger_fields.amount_units) -match '^-?[0-9]+$' -and [string]$row.order_ledger_fields.amount_units -eq [string]$row.expected_amount_units){$runtimeOk=$true;break}};$ctx=Get-StageUatPeriodContext;$after=Get-UserStatsPeriodSnapshot $o.business_snapshot_after ([int]$ctx.Primary);$businessVersionOk=([string]$after.pv_type -eq 'int' -and [int]$after.amount_encoding_version -eq 2 -and [bool]$o.business_value_proof_ok)}
        if(-not $testOk -or -not $runtimeOk -or -not $businessVersionOk){throw 'UAT_ENV_BLOCKED: int64 end-to-end proof requires dtype tests, exact integer ledger amount, and v2 integer UserStats runtime state'}
        return [pscustomobject]@{ExitCode=0;Output=@('proof=int64-end-to-end');Semantic=[pscustomobject]@{kind='UatProofResult';proof_id=$proofId;passed=$true;dtype_test_target='User/Test/test_amount_dtype_migration.py';runtime_integer_amount_proved=$true;runtime_business_amount_version_proved=$true}}
    }
    if($proofId -eq 'pause-rebalance'){
        $before=Get-LatestActionSemantic 'ConsumerObserve' 'future-period';$after=Get-LatestActionSemantic 'ConsumerObserve' 'future-period-replay';$drain=Get-LatestActionSemantic 'ConsumerObserve' 'drain-sentinel'
        if(-not $before -or -not [bool]$before.pause_barrier_ok -or -not $after -or -not [bool]$after.future_replay_ok -or -not $drain -or -not [bool]$drain.drain_detected){throw 'UAT_ENV_BLOCKED: pause/rebalance proof requires pause barrier, drain, and post-rebind replay'}
        return [pscustomobject]@{ExitCode=0;Output=@('proof=pause-rebalance');Semantic=[pscustomobject]@{kind='UatProofResult';proof_id=$proofId;passed=$true;pause_barrier_ok=$true;drain_detected=$true;future_replay_ok=$true}}
    }
    throw "UAT_ACTION_POLICY_DENIED: unsupported UAT proof_id: $proofId"
}
function Invoke-GovernedList($Request, $Policy) {
    $kind = ([string]$Request.kind).Trim().ToLowerInvariant()
    $prefix = ([string]$Request.name_prefix).Trim().ToLowerInvariant()
    Assert-ListScopeAllowed $kind $prefix $Policy
    $obj = Get-KubectlJson @("--kubeconfig", $Kubeconfig, "get", $kind, "-n", $TargetNamespace) "UAT_ENV_BLOCKED"
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($item in @($obj.items)) {
        $name = ([string]$item.metadata.name).Trim().ToLowerInvariant()
        if ($name.StartsWith($prefix) -and (Test-ResourceAllowed $kind $name)) {
            $rows.Add([pscustomobject]@{ kind=$kind; name=[string]$item.metadata.name; uid=[string]$item.metadata.uid; phase=[string]$item.status.phase })
        }
    }
    return [pscustomobject]@{ ExitCode = 0; Output = @(($rows.ToArray() | ConvertTo-Json -Depth 6 -Compress)) }
}

$policy = $null
$request = $null
$requestHash = ""
$action = "UNKNOWN"
$requestHash = Get-TextSha256 $script:AuditRequestJson
$required = @()
$result = $null
$detail = ""
$outcome = "FAILED"
$errorClass = ""
$errorMessage = ""
$evidence = ""
$exitCode = 1

try {
    Assert-AuthorizationEnvelope
    $script:StagePeriodContext = Get-StageUatPeriodContext
    if (-not (Test-Path -LiteralPath $Kubectl)) { throw "UAT_ENV_BLOCKED: kubectl missing at governed path: $Kubectl" }
    if (-not (Test-Path -LiteralPath $Kubeconfig)) { throw "UAT_ENV_BLOCKED: kubeconfig missing at governed path: $Kubeconfig" }
    if (-not (Test-Path -LiteralPath $PolicyPath)) { throw "UAT_ACTION_POLICY_DENIED: UAT action policy missing: $PolicyPath" }
    if (-not (Test-Path -LiteralPath $RequestPath)) { throw "UAT_ACTION_POLICY_DENIED: UAT action proxy request missing: $RequestPath" }
    $policy = [IO.File]::ReadAllText($PolicyPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if ([int]$policy.schema_version -ne 8) { throw "UAT_ACTION_POLICY_DENIED: unsupported UAT action policy schema_version" }
    if ([int]$policy.controller_evidence_schema -ne 10 -or $ControllerEvidenceSchema -ne '10') { throw "UAT_ACTION_POLICY_DENIED: controller evidence schema mismatch" }
    $requestRaw = [IO.File]::ReadAllText($RequestPath, [Text.Encoding]::UTF8)
    $requestHash = Get-TextSha256 $requestRaw
    $script:AuditRequestJson = $requestRaw
    $request = $requestRaw | ConvertFrom-Json
    $action = ([string]$request.action).Trim()
    if (-not $action -or $action -match '[\x00\r\n ]') { throw "UAT_ACTION_POLICY_DENIED: invalid structured UAT action" }
    Assert-Readyz
    $debugImage = $null

    switch ($action) {
        "Readyz" { $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "get", "--raw=/readyz", "--request-timeout=15s") }
        "List" { $result = Invoke-GovernedList $request $policy }
        "Get" {
            Assert-ResourceAllowed ([string]$request.kind) ([string]$request.name)
            $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "get", ("{0}/{1}" -f $request.kind, $request.name), "-n", $TargetNamespace, "--request-timeout=15s")
        }
        "GetJsonPath" {
            Assert-ResourceAllowed ([string]$request.kind) ([string]$request.name)
            $jsonPath = ([string]$request.jsonpath).Trim()
            if (-not $jsonPath -or $jsonPath.Length -gt 512 -or $jsonPath -match '[\x00\r\n]') { throw "UAT_ACTION_POLICY_DENIED: invalid jsonpath" }
            $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "get", ("{0}/{1}" -f $request.kind, $request.name), "-n", $TargetNamespace, ("-o=jsonpath={0}" -f $jsonPath), "--request-timeout=15s")
        }
        "Describe" {
            Assert-ResourceAllowed ([string]$request.kind) ([string]$request.name)
            $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "describe", ([string]$request.kind), ([string]$request.name), "-n", $TargetNamespace, "--request-timeout=15s")
        }
        "Logs" {
            Assert-ResourceAllowed "pod" ([string]$request.name)
            $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "logs", ([string]$request.name), "-n", $TargetNamespace, "--request-timeout=15s")
        }
        "Wait" {
            Assert-ResourceAllowed ([string]$request.kind) ([string]$request.name)
            $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "wait", ("{0}/{1}" -f $request.kind, $request.name), "-n", $TargetNamespace, "--for=condition=Ready", "--timeout=60s")
        }
        "ApiResources" { $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "api-resources", "--request-timeout=15s") }
        "Version" { $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "version", "--request-timeout=15s") }
        "RolloutStatus" {
            Assert-ResourceAllowed ([string]$request.kind) ([string]$request.name)
            $timeoutSeconds = 180
            if ($request.PSObject.Properties.Name -contains 'timeout_seconds') {
                $timeoutText = ([string]$request.timeout_seconds).Trim()
                if (-not [int]::TryParse($timeoutText, [ref]$timeoutSeconds) -or $timeoutSeconds -lt 1 -or $timeoutSeconds -gt 900) { throw "UAT_ACTION_POLICY_DENIED: rollout timeout_seconds must be 1..900" }
            }
            $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "rollout", "status", ("{0}/{1}" -f $request.kind, $request.name), "-n", $TargetNamespace, ("--timeout={0}s" -f $timeoutSeconds), "--request-timeout=30s")
        }
        "Restart" {
            $required = @("restart"); Assert-RequiredTokens $required $action
            Assert-ResourceAllowed ([string]$request.kind) ([string]$request.name)
            $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "rollout", "restart", ("{0}/{1}" -f $request.kind, $request.name), "-n", $TargetNamespace, "--request-timeout=30s")
        }
        "Scale" {
            $required = @("scale"); Assert-RequiredTokens $required $action
            Assert-ResourceAllowed ([string]$request.kind) ([string]$request.name)
            if ($request.PSObject.Properties.Name -notcontains 'replicas') { throw "UAT_ACTION_POLICY_DENIED: replicas is required for Scale" }
            $replicas = 0
            $replicasText = ([string]$request.replicas).Trim()
            if (-not [int]::TryParse($replicasText, [ref]$replicas)) { throw "UAT_ACTION_POLICY_DENIED: replicas must be an integer" }
            if ($replicas -lt 0 -or $replicas -gt 100) { throw "UAT_ACTION_POLICY_DENIED: replicas outside governed range 0..100" }
            $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "scale", ("{0}/{1}" -f $request.kind, $request.name), ("--replicas={0}" -f $replicas), "-n", $TargetNamespace, "--request-timeout=30s")
        }
        "Delete" {
            $required = @("delete"); Assert-RequiredTokens $required $action
            Assert-ResourceAllowed ([string]$request.kind) ([string]$request.name)
            $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "delete", ([string]$request.kind), ([string]$request.name), "-n", $TargetNamespace, "--wait=true", "--request-timeout=30s")
        }
        "SetImage" {
            $required = @("deploy"); Assert-RequiredTokens $required $action
            $kind = ([string]$request.kind).Trim().ToLowerInvariant()
            $name = ([string]$request.name).Trim().ToLowerInvariant()
            Assert-ResourceAllowed $kind $name
            $container = ([string]$request.container).Trim(); $image = ([string]$request.image).Trim()
            if ($container -notmatch '^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$') { throw "UAT_ACTION_POLICY_DENIED: invalid container name" }
            if (-not $image -or $image -match '[\x00\r\n ]') { throw "UAT_ACTION_POLICY_DENIED: invalid image reference" }
            $allowed = $false
            foreach ($entry in @($policy.set_image_allowlist)) {
                if (([string]$entry.kind).Trim().ToLowerInvariant() -eq $kind -and
                    ([string]$entry.name).Trim().ToLowerInvariant() -eq $name -and
                    ([string]$entry.container).Trim() -eq $container -and
                    ([string]$entry.image).Trim() -eq $image) { $allowed = $true; break }
            }
            if (-not $allowed) { throw "UAT_ACTION_POLICY_DENIED: SET_IMAGE_NOT_ALLOWLISTED for $kind/$name container=$container image=$image" }
            $result = Invoke-Kubectl @("--kubeconfig", $Kubeconfig, "set", "image", ("{0}/{1}" -f $kind, $name), ("{0}={1}" -f $container, $image), "-n", $TargetNamespace, "--request-timeout=30s")
        }
        "ExecProfile" {
            $profile = Get-PolicyProfile $policy.exec_profiles ([string]$request.profile) "exec"
            $required = @("exec") + @($profile.required_tokens | ForEach-Object { [string]$_ }) | Select-Object -Unique
            $result = Invoke-PolicyExecProfile $request $policy
        }
        "ConsumerLifecycle" {
            $op=([string]$request.operation).Trim().ToLowerInvariant()
            if($op -notin @('bind-primary','bind-secondary','status','restore')){
                throw "UAT_ACTION_POLICY_DENIED: ConsumerLifecycle operation must be bind-primary, bind-secondary, status, or restore"
            }
            $required=@('exec')
            $result = Invoke-ConsumerLifecycle $request $policy
        }
        "ConsumerObserve" { $required=@('exec'); $result = Invoke-ConsumerObserve $request $policy }
        "UatProof" {
            $proofId=([string]$request.proof_id).Trim()
            if($proofId -eq 'pending-dispatched-recovery'){$required=@('exec','test-data-write','restart')}
            elseif($proofId -eq 'dispatch-p99'){$required=@('exec','test-data-write')}
            else{$required=@('exec')}
            $result = Invoke-UatProof $request $policy
        }
        "GitAudit" { $result = Invoke-GitAudit $request $policy }
        "PytestFull" { $required=@("exec"); $result = Invoke-PytestProfile $request $policy $true }
        "PytestSelected" { $required=@("exec"); $result = Invoke-PytestProfile $request $policy $false }
        "DaskListDatasets" {
            $required=@("exec")
            $result = Invoke-PolicyExecProfile $request $policy "dask-list-datasets"
        }
        "RedisDbSize" { $required=@("exec"); $result = Invoke-RedisDbSize $request $policy }
        "KafkaScenarioProduce" { $required=@("exec","test-data-write"); $result = Invoke-KafkaScenarioProduce $request $policy }
        "DebugProfile" {
            $profile = Get-PolicyProfile $policy.debug_profiles ([string]$request.profile) "debug"
            $required = @("debug") + @($profile.required_tokens | ForEach-Object { [string]$_ }) | Select-Object -Unique
            Assert-RequiredTokens @($required) $action
            $command = @(Expand-ProfileCommand @($profile.command)); Assert-NoShellWrapper $command
            $debugImage = Resolve-DebugImage $policy
            $result = Invoke-NodeDebugWithCleanup ([string]$request.node) $command $debugImage
        }
        "RedisDeleteExactKeys" {
            $required = @("exec", "test-data-write")
            $result = Invoke-RedisExactCleanup $request $policy
        }
        "RedisReadExactKeys" {
            $required = @("exec")
            $result = Invoke-RedisExactRead $request $policy
        }
        "GitUpdate" {
            $required = @("debug", "git-update"); Assert-RequiredTokens $required $action
            $node = ([string]$request.node).Trim().ToLowerInvariant(); Assert-ResourceAllowed "node" $node
            if ($TargetBranch -ne [string]$env:BRANCH) { throw "GIT_BRANCH_MISMATCH: authorized target branch does not match Loop Engine candidate branch" }
            $candidatePath = Join-Path $MainRepo ".loop-output\pushed-sha.txt"
            if (-not (Test-Path $candidatePath)) { throw "GIT_HEAD_MISMATCH: pushed-sha.txt missing for GitUpdate" }
            $candidate = ([IO.File]::ReadAllText($candidatePath, [Text.Encoding]::UTF8)).Trim().ToLowerInvariant()
            if ($candidate -notmatch '^[0-9a-f]{40}$') { throw "GIT_HEAD_MISMATCH: invalid candidate SHA for GitUpdate" }
            $expectedRemote = ([string]$policy.repo_remote_url).Trim()
            if (-not $expectedRemote) { throw "UAT_ACTION_POLICY_DENIED: repo_remote_url is missing" }
            $debugImage = Resolve-DebugImage $policy
            $repo = Find-GitRepoByRemote $node $debugImage $expectedRemote
            $detail = "host_repo=$repo"

            $status = Invoke-NodeDebugWithCleanup $node @("chroot", "/host", "git", "-C", $repo, "status", "--porcelain", "--untracked-files=all") $debugImage
            if ($status.ExitCode -ne 0) { throw "GIT_STATUS_FAILED: cannot inspect node host worktree" }
            $statusLines = @($status.Output | Where-Object { ([string]$_).Trim() -and -not ([string]$_).StartsWith("debug_") -and -not ([string]$_).StartsWith("pod/") })
            $dirty = @($statusLines | Where-Object { ([string]$_).Trim() -match '^[ MARCUD?!]{1,2}\s' })
            if ($dirty.Count -gt 0) { throw "GIT_WORKTREE_DIRTY: node host repo contains unknown changes; refuse mutation" }

            $fetch = Invoke-NodeDebugWithCleanup $node @("chroot", "/host", "git", "-C", $repo, "fetch", "origin", $TargetBranch) $debugImage
            if ($fetch.ExitCode -ne 0) { throw "GIT_FETCH_FAILED: fetch origin failed" }
            $remoteHead = Invoke-NodeDebugWithCleanup $node @("chroot", "/host", "git", "-C", $repo, "rev-parse", ("origin/{0}" -f $TargetBranch)) $debugImage
            $remoteText = (($remoteHead.Output | Where-Object { ([string]$_).Trim() -match '^[0-9a-fA-F]{40}$' } | Select-Object -Last 1) -as [string]).Trim().ToLowerInvariant()
            if ($remoteHead.ExitCode -ne 0 -or $remoteText -ne $candidate) { throw "GIT_HEAD_MISMATCH: remote candidate HEAD=$remoteText expected=$candidate" }

            $checkout = Invoke-NodeDebugWithCleanup $node @("chroot", "/host", "git", "-C", $repo, "checkout", "-B", $TargetBranch, $candidate) $debugImage
            if ($checkout.ExitCode -ne 0) { throw "GIT_CHECKOUT_FAILED: checkout candidate failed" }
            Verify-NodeHostGitView $node $repo $debugImage $candidate

            $verificationPod = ([string]$request.verification_pod).Trim()
            if (-not $verificationPod) { throw "GIT_POD_VIEW_FAILED: verification_pod is required for three-way HEAD verification" }
            $verificationContainer = ([string]$request.verification_container).Trim()
            $podRepo = Verify-PodGitView $verificationPod $verificationContainer $expectedRemote $candidate
            $detail = "host_repo=$repo;pod_repo=$podRepo"
            $semantic = [pscustomobject]@{ kind='GitUpdateResult'; candidate_sha=$candidate; remote_head=$candidate; host_head=$candidate; pod_head=$candidate; host_repo=$repo; pod_repo=$podRepo; verification_pod=$verificationPod }
            $result = [pscustomobject]@{ ExitCode = 0; Output = @("candidate=$candidate", "remote=$remoteText", "host_repo=$repo", "pod_repo=$podRepo"); Semantic=$semantic }
        }
        default { throw "UAT_ACTION_POLICY_DENIED: unsupported structured UAT action: $action" }
    }

    if ($null -eq $result) { throw "PROXY_FAILURE: action returned no result" }
    if ([int]$result.ExitCode -ne 0) { throw "PROXY_COMMAND_FAILED: action $action exited $($result.ExitCode): $($result.Output -join ' ')" }
    $outcome = "SUCCESS"
    $exitCode = 0
}
catch {
    $errorMessage = $_.Exception.Message
    $errorClass = Get-ProxyErrorClass $errorMessage
    $outcome = if ($errorClass -in @("UAT_WRITE_AUTHORIZATION_REQUIRED", "UAT_RESOURCE_SCOPE_DENIED", "UAT_ACTION_POLICY_DENIED")) { "DENIED" } elseif ($errorClass -eq "UAT_ENV_BLOCKED") { "BLOCKED" } else { "FAILED" }
    $exitCode = 1
}
finally {
    $evidence = Write-ProxyAuditRecord $action $requestHash @($required) $outcome $errorClass $errorMessage $result $detail
}

if ($result) { foreach ($line in @($result.Output)) { Write-Output $line } }
if ($evidence) { Write-Output "[UAT-ACTION-PROXY] evidence=$evidence" }
if ($exitCode -ne 0) { Write-Error $errorMessage }
exit $exitCode
