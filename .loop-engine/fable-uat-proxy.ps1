$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$MainRepo = "D:\Redemption\Redemption"
$Kubectl = Join-Path $MainRepo "K8S\kubectl.exe"
$Kubeconfig = Join-Path $MainRepo "K8S\admin.conf"
$FableStateDir = Join-Path $MainRepo ".loop-output\verifier-state\fable"
$RequestPath = Join-Path $FableStateDir "proxy-request.json"
$EvidenceDir = Join-Path $MainRepo ".loop-output\verifier-state\fable\evidence\proxy"

$AuthorizedActionsRaw = ([string]$env:LOOP_UAT_AUTHORIZED_ACTIONS).Trim().ToLowerInvariant()
if (-not $AuthorizedActionsRaw -or $AuthorizedActionsRaw -eq "none") { throw "UAT_WRITE_AUTHORIZATION_REQUIRED: Fable proxy has no bound mutable action scope" }
$AuthorizedActions = @($AuthorizedActionsRaw -split ',' | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() } | Where-Object { $_ })

function Assert-AuthorizedMutableAction([string]$RequiredToken, [string]$ActionName) {
    if ($AuthorizedActions -notcontains $RequiredToken) {
        throw "UAT_WRITE_AUTHORIZATION_REQUIRED: Fable proxy action $ActionName requires authorized action token '$RequiredToken'"
    }
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    [IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Assert-Action(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Readyz", "Get", "Describe", "Logs", "Exec", "Debug", "Wait", "ApiResources", "Version")]
    [string]$Action
) {
    return $Action
}

function Assert-SafeArgs([object[]]$ArgumentList) {
    $forbiddenPrefixes = @(
        "--kubeconfig",
        "--server",
        "--token",
        "--client-key",
        "--client-certificate",
        "--certificate-authority",
        "--cache-dir",
        "--log-file"
    )
    foreach ($item in @($ArgumentList)) {
        $arg = [string]$item
        if ($arg -eq "cp") { throw "Unsupported kubectl subcommand: cp" }
        foreach ($prefix in $forbiddenPrefixes) {
            if ($arg -eq $prefix -or $arg.StartsWith($prefix + "=", [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Unsupported kubectl argument in Fable proxy: $arg"
            }
        }
        if ($arg.Contains("`0") -or $arg.Contains("`r") -or $arg.Contains("`n")) {
            throw "Unsupported control character in Fable proxy argument"
        }
    }
}

function Invoke-Kubectl([string[]]$Arguments) {
    # Windows PowerShell 5.1 promotes native stderr to NativeCommandError when
    # ErrorActionPreference is Stop. Negative UATs and kubectl warnings are valid
    # evidence, so temporarily downgrade only the native invocation and always
    # restore the script-wide fail-fast preference afterwards.
    $previousErrorActionPreference = $ErrorActionPreference
    $output = @()
    $exitCode = -1
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $Kubectl @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [pscustomobject]@{
        ExitCode = [int]$exitCode
        Output = @($output | ForEach-Object { [string]$_ })
    }
}

function Write-ProxyEvidence([string]$Phase, [string]$ActionName, [string[]]$Arguments, $Result, [string]$RequestHash) {
    New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
    $evidencePath = Join-Path $EvidenceDir ("proxy-$stamp-$([Guid]::NewGuid().ToString('N')).log")
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("phase=$Phase")
    $lines.Add("action=$ActionName")
    $lines.Add("request_sha256=$RequestHash")
    $lines.Add("kubectl=$Kubectl")
    $lines.Add("kubeconfig_path=$Kubeconfig")
    $lines.Add("arguments=" + (($Arguments | ForEach-Object { [string]$_ }) -join " "))
    $lines.Add("exit_code=$($Result.ExitCode)")
    $lines.Add("output_begin")
    foreach ($line in @($Result.Output)) { $lines.Add([string]$line) }
    $lines.Add("output_end")
    Write-Utf8NoBom $evidencePath (($lines.ToArray() -join "`n") + "`n")
    return $evidencePath
}

if (-not (Test-Path -LiteralPath $Kubectl)) { throw "kubectl missing at governed path: $Kubectl" }
if (-not (Test-Path -LiteralPath $Kubeconfig)) { throw "kubeconfig missing at governed path: $Kubeconfig" }
if (-not (Test-Path -LiteralPath $RequestPath)) { throw "Fable UAT proxy request missing: $RequestPath" }

$request = [IO.File]::ReadAllText($RequestPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$action = Assert-Action ([string]$request.action)
$requestArgs = @($request.args | ForEach-Object { [string]$_ })
Assert-SafeArgs $requestArgs
$requestHash = (Get-FileHash -Algorithm SHA256 $RequestPath).Hash.ToLowerInvariant()

# Every proxy invocation starts with the governed read-only readyz probe. This
# also makes the proxy safe if a future workflow refactor accidentally omits the
# outer preflight. The 15s timeout is a governed project contract.
$readyArgs = @("--kubeconfig", $Kubeconfig, "get", "--raw=/readyz", "--request-timeout=15s")
$ready = Invoke-Kubectl $readyArgs
$readyEvidence = Write-ProxyEvidence "readyz" "Readyz" $readyArgs $ready $requestHash
if ($ready.ExitCode -ne 0 -or (($ready.Output -join "`n").Trim()).ToLowerInvariant() -notmatch '^ok') {
    throw "UAT_ENV_BLOCKED: Kubernetes readyz failed in Fable proxy; evidence=$readyEvidence output=$($ready.Output -join ' ')"
}

switch ($action) {
    "Readyz" { $commandArgs = @("--kubeconfig", $Kubeconfig, "get", "--raw=/readyz", "--request-timeout=15s") }
    "Get" { $commandArgs = @("--kubeconfig", $Kubeconfig, "get") + $requestArgs }
    "Describe" { $commandArgs = @("--kubeconfig", $Kubeconfig, "describe") + $requestArgs }
    "Logs" { $commandArgs = @("--kubeconfig", $Kubeconfig, "logs") + $requestArgs }
    "Exec" { Assert-AuthorizedMutableAction "exec" "Exec"; $commandArgs = @("--kubeconfig", $Kubeconfig, "exec") + $requestArgs }
    "Debug" { Assert-AuthorizedMutableAction "debug" "Debug"; $commandArgs = @("--kubeconfig", $Kubeconfig, "debug") + $requestArgs }
    "Wait" { $commandArgs = @("--kubeconfig", $Kubeconfig, "wait") + $requestArgs }
    "ApiResources" { $commandArgs = @("--kubeconfig", $Kubeconfig, "api-resources") + $requestArgs }
    "Version" { $commandArgs = @("--kubeconfig", $Kubeconfig, "version") + $requestArgs }
    default { throw "Unsupported Fable proxy action: $action" }
}

$result = Invoke-Kubectl $commandArgs
$evidencePath = Write-ProxyEvidence "action" $action $commandArgs $result $requestHash

foreach ($line in @($result.Output)) { Write-Output $line }
Write-Output "[FABLE-UAT-PROXY] readyz_evidence=$readyEvidence"
Write-Output "[FABLE-UAT-PROXY] evidence=$evidencePath"
exit $result.ExitCode
