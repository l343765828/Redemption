param(
    [ValidateSet(
        "all",
        "node-repo-partial-find",
        "node-repo-no-candidate",
        "node-repo-ambiguous",
        "pod-repo-partial-find",
        "pod-repo-no-candidate",
        "pod-repo-ambiguous",
        "pod-repo-scope-denied",
        "scheduler-skip-failed",
        "runtime-python-argv-safe",
        "runtime-json-base64-safe",
        "pending-recovery-json-safe",
        "redis-proof-cross-period-distinct-keys",
        "redis-cleanup-stage-prefixes",
        "redis-cleanup-caller-key-sizes",
        "runtime-config-policy-redirect-blocked",
        "consumer-controller-payload-safe",
        "pytest-full-exclusions",
        "pytest-full-unsafe-exclusion"
    )]
    [string]$Case = "all",
    [string]$ProxyPath = "",
    [string]$PythonPath = "",
    [string]$PytestPythonPath = "",
    [string]$PolicyPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProxyPath) {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $ProxyPath = Join-Path $repoRoot ".loop-engine\uat-action-proxy.ps1"
}
if (-not $PolicyPath) {
    if (-not $repoRoot) { $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
    $PolicyPath = Join-Path $repoRoot ".loop-engine\uat-action-policy.json"
}
if (-not (Test-Path -LiteralPath $ProxyPath -PathType Leaf)) {
    throw "proxy script missing: $ProxyPath"
}
$script:ProxyRootForTests = Split-Path -Parent (Resolve-Path -LiteralPath $ProxyPath).Path

function Get-TestPythonCandidates([string]$ExplicitPath) {
    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in @($ExplicitPath, $env:LOOP_TEST_PYTHON)) {
        if ($candidate) { $candidates.Add([string]$candidate) }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($line in @(& $launcher.Source -0p 2>$null)) {
            if ([string]$line -match '([A-Za-z]:\\.*python\.exe)\s*$') { $candidates.Add($matches[1]) }
        }
    }
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) { $candidates.Add($pythonCommand.Source) }
    return @($candidates.ToArray() | Select-Object -Unique)
}

function Resolve-TestPython([string]$ExplicitPath, [bool]$RequirePytest) {
    foreach ($candidate in @(Get-TestPythonCandidates $ExplicitPath)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $previousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $probe = if ($RequirePytest) { "import pytest" } else { "import sys" }
            $null = @(& $candidate -c $probe 2>&1)
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
        catch {}
        finally { $ErrorActionPreference = $previousPreference }
    }
    $requirement = if ($RequirePytest) { " with pytest" } else { "" }
    throw "a runnable python.exe$requirement is required for PowerShell 5.1 proxy regressions"
}

$script:TestPythonPath = Resolve-TestPython $PythonPath $false
$script:TestPytestPythonPath = Resolve-TestPython $PytestPythonPath $true

function Import-ProxyFunctions([string[]]$Names) {
    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $ProxyPath,
        [ref]$tokens,
        [ref]$parseErrors
    )
    if (@($parseErrors).Count -ne 0) {
        throw "proxy script has PowerShell parse errors"
    }

    foreach ($name in $Names) {
        $matches = @($ast.FindAll({
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                $node.Name -eq $name
        }, $true))
        if ($matches.Count -ne 1) {
            throw "expected exactly one production function '$name', found $($matches.Count)"
        }
        $bodyText = $matches[0].Body.Extent.Text
        $bodyText = $bodyText.Substring(1, $bodyText.Length - 2)
        $bodyText = $bodyText.Replace('$PSScriptRoot', '$script:ProxyRootForTests')
        $parameterText = (@($matches[0].Parameters | ForEach-Object { $_.Extent.Text }) -join ", ")
        $functionText = if ($parameterText) { "param($parameterText)`n$bodyText" } else { $bodyText }
        Set-Item -Path ("Function:\script:{0}" -f $name) -Value ([scriptblock]::Create($functionText))
    }
}

function Assert-Equal($Expected, $Actual, [string]$Message) {
    if ($Expected -ne $Actual) {
        throw "$Message expected='$Expected' actual='$Actual'"
    }
}

function Assert-ThrowsLike([scriptblock]$Action, [string]$Pattern, [string]$Message) {
    $caught = $null
    try {
        & $Action
    }
    catch {
        $caught = $_.Exception.Message
    }
    if (-not $caught -or $caught -notlike $Pattern) {
        throw "$Message expected-like='$Pattern' actual='$caught'"
    }
}

function Invoke-LocalPythonFromPodCommand([object[]]$Command, [string]$PythonExecutable = $script:TestPythonPath, $StandardInput = $null) {
    if (@($Command).Count -lt 3 -or [string]$Command[0] -ne "python3") {
        throw "expected a python3 pod command"
    }
    $arguments = @($Command | Select-Object -Skip 1)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = if ($null -ne $StandardInput) {
            @($StandardInput | & $PythonExecutable @arguments 2>&1)
        }
        else {
            @(& $PythonExecutable @arguments 2>&1)
        }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    return [pscustomobject]@{
        ExitCode = [int]$exitCode
        Output = @($output | ForEach-Object { [string]$_ })
    }
}

function Test-NodeRepoPartialFind {
    Import-ProxyFunctions @("Find-GitRepoByRemote")
    $script:nodeDebugCall = 0
    function script:Invoke-NodeDebugWithCleanup {
        param([string]$Node, [string[]]$Command, [string]$DebugImage)
        $script:nodeDebugCall++
        if ($script:nodeDebugCall -eq 1) {
            return [pscustomobject]@{
                ExitCode = 1
                Output = @(
                    "/mnt/redemption/Redemption/.git",
                    "find: /proc/1234/fd: No such file or directory"
                )
            }
        }
        return [pscustomobject]@{
            ExitCode = 0
            Output = @("git@github.com:l343765828/Redemption.git")
        }
    }

    $repo = Find-GitRepoByRemote "node3" "registry.local/debug:latest" "git@github.com:l343765828/Redemption.git"
    Assert-Equal "/mnt/redemption/Redemption" $repo "node repo discovery must validate usable matches even when find reports traversal errors"
    Assert-Equal 2 $script:nodeDebugCall "node repo discovery must validate the matching remote"
}

function Test-NodeRepoNoCandidate {
    Import-ProxyFunctions @("Find-GitRepoByRemote")
    function script:Invoke-NodeDebugWithCleanup {
        param([string]$Node, [string[]]$Command, [string]$DebugImage)
        return [pscustomobject]@{
            ExitCode = 1
            Output = @("find: /proc/1234/fd: No such file or directory")
        }
    }

    Assert-ThrowsLike {
        Find-GitRepoByRemote "node3" "registry.local/debug:latest" "git@github.com:l343765828/Redemption.git"
    } "GIT_REPO_DISCOVERY_FAILED: find .git failed" "node repo discovery must remain fail-closed when traversal yields no candidates"
}

function Test-NodeRepoAmbiguous {
    Import-ProxyFunctions @("Find-GitRepoByRemote")
    $script:nodeDebugCall = 0
    function script:Invoke-NodeDebugWithCleanup {
        param([string]$Node, [string[]]$Command, [string]$DebugImage)
        $script:nodeDebugCall++
        if ($script:nodeDebugCall -eq 1) {
            return [pscustomobject]@{
                ExitCode = 0
                Output = @(
                    "/mnt/redemption/Redemption/.git",
                    "/mnt/duplicate/Redemption/.git"
                )
            }
        }
        return [pscustomobject]@{
            ExitCode = 0
            Output = @("git@github.com:l343765828/Redemption.git")
        }
    }

    Assert-ThrowsLike {
        Find-GitRepoByRemote "node3" "registry.local/debug:latest" "git@github.com:l343765828/Redemption.git"
    } "GIT_REPO_DISCOVERY_FAILED: expected exactly one host repo*found 2" "node repo discovery must reject multiple exact remote matches"
    Assert-Equal 3 $script:nodeDebugCall "node repo discovery must inspect every candidate before rejecting ambiguity"
}

function Test-PodRepoPartialFind {
    Import-ProxyFunctions @("Test-ResourceAllowed", "Assert-ResourceAllowed", "Find-PodGitRepoByRemote")
    $script:podKubectlCall = 0
    $script:Kubeconfig = "D:\fake\admin.conf"
    $script:TargetNamespace = "dask-operator"
    $script:ResourceScope = @("pod/dask-cluster-scheduler-*")
    function script:Invoke-Kubectl {
        param([object[]]$CommandArgs)
        $script:podKubectlCall++
        if ($script:podKubectlCall -eq 1) {
            return [pscustomobject]@{
                ExitCode = 1
                Output = @(
                    "/mnt/redemption/Redemption/.git",
                    "find: /proc/5678/fd: Permission denied"
                )
            }
        }
        return [pscustomobject]@{
            ExitCode = 0
            Output = @("git@github.com:l343765828/Redemption.git")
        }
    }

    $repo = Find-PodGitRepoByRemote "dask-cluster-scheduler-running" "scheduler" "git@github.com:l343765828/Redemption.git"
    Assert-Equal "/mnt/redemption/Redemption" $repo "pod repo discovery must validate usable matches even when find reports traversal errors"
    Assert-Equal 2 $script:podKubectlCall "pod repo discovery must validate the matching remote"
}

function Test-PodRepoNoCandidate {
    Import-ProxyFunctions @("Test-ResourceAllowed", "Assert-ResourceAllowed", "Find-PodGitRepoByRemote")
    $script:Kubeconfig = "D:\fake\admin.conf"
    $script:TargetNamespace = "dask-operator"
    $script:ResourceScope = @("pod/dask-cluster-scheduler-*")
    function script:Invoke-Kubectl {
        param([object[]]$CommandArgs)
        return [pscustomobject]@{
            ExitCode = 1
            Output = @("find: /proc/5678/fd: Permission denied")
        }
    }

    Assert-ThrowsLike {
        Find-PodGitRepoByRemote "dask-cluster-scheduler-running" "scheduler" "git@github.com:l343765828/Redemption.git"
    } "GIT_POD_VIEW_FAILED: cannot discover repo in verification pod" "pod repo discovery must remain fail-closed when traversal yields no candidates"
}

function Test-PodRepoAmbiguous {
    Import-ProxyFunctions @("Test-ResourceAllowed", "Assert-ResourceAllowed", "Find-PodGitRepoByRemote")
    $script:podKubectlCall = 0
    $script:Kubeconfig = "D:\fake\admin.conf"
    $script:TargetNamespace = "dask-operator"
    $script:ResourceScope = @("pod/dask-cluster-scheduler-*")
    function script:Invoke-Kubectl {
        param([object[]]$CommandArgs)
        $script:podKubectlCall++
        if ($script:podKubectlCall -eq 1) {
            return [pscustomobject]@{
                ExitCode = 0
                Output = @(
                    "/mnt/redemption/Redemption/.git",
                    "/mnt/duplicate/Redemption/.git"
                )
            }
        }
        return [pscustomobject]@{
            ExitCode = 0
            Output = @("git@github.com:l343765828/Redemption.git")
        }
    }

    Assert-ThrowsLike {
        Find-PodGitRepoByRemote "dask-cluster-scheduler-running" "scheduler" "git@github.com:l343765828/Redemption.git"
    } "GIT_POD_VIEW_FAILED: expected exactly one repo in verification pod, found 2" "pod repo discovery must reject multiple exact remote matches"
    Assert-Equal 3 $script:podKubectlCall "pod repo discovery must inspect every candidate before rejecting ambiguity"
}

function Test-PodRepoScopeDenied {
    Import-ProxyFunctions @("Test-ResourceAllowed", "Assert-ResourceAllowed", "Find-PodGitRepoByRemote")
    $script:podKubectlCall = 0
    $script:Kubeconfig = "D:\fake\admin.conf"
    $script:TargetNamespace = "dask-operator"
    $script:ResourceScope = @("pod/unrelated-uat-*")
    function script:Invoke-Kubectl {
        param([object[]]$CommandArgs)
        $script:podKubectlCall++
        throw "kubectl must not run for an unauthorized pod"
    }

    Assert-ThrowsLike {
        Find-PodGitRepoByRemote "dask-cluster-scheduler-running" "scheduler" "git@github.com:l343765828/Redemption.git"
    } "UAT_RESOURCE_SCOPE_DENIED:*" "pod repo discovery must enforce the production resource-scope guard before kubectl"
    Assert-Equal 0 $script:podKubectlCall "pod repo discovery must reject unauthorized pods before invoking kubectl"
}

function Test-SchedulerSkipsFailedPods {
    Import-ProxyFunctions @("Test-ResourceAllowed", "Assert-ResourceAllowed", "Get-ConsumerLifecycleSelectedPods")
    $script:Kubeconfig = "D:\fake\admin.conf"
    $script:TargetNamespace = "dask-operator"
    $script:ResourceScope = @("pod/dask-cluster-scheduler-*")
    function script:Get-KubectlJson {
        param([object[]]$Arguments, [string]$FailureMessage)
        if ($Arguments -contains "deployment") {
            return @'
{
  "spec": {
    "selector": {
      "matchLabels": {
        "dask.org/cluster-name": "dask-cluster",
        "dask.org/component": "scheduler"
      }
    }
  }
}
'@ | ConvertFrom-Json
        }
        return @'
{
  "items": [
    {
      "metadata": {"name": "dask-cluster-scheduler-failed"},
      "status": {
        "phase": "Failed",
        "reason": "UnexpectedAdmissionError"
      }
    },
    {
      "metadata": {"name": "dask-cluster-scheduler-running"},
      "status": {
        "phase": "Running",
        "containerStatuses": [
          {"name": "scheduler", "ready": true}
        ]
      }
    }
  ]
}
'@ | ConvertFrom-Json
    }

    $selected = @(Get-ConsumerLifecycleSelectedPods "dask-cluster-scheduler" "scheduler" "dask-cluster-scheduler-")
    Assert-Equal 1 $selected.Count "scheduler selection must return exactly one Running/Ready pod"
    Assert-Equal "dask-cluster-scheduler-running" $selected[0] "scheduler selection must ignore terminal Failed pods"
}

function Test-RuntimePythonArgvSafe {
    Import-ProxyFunctions @("Invoke-RuntimePythonCommand")
    function script:Invoke-PodCommand {
        param([string]$Pod, [string]$Container, [object[]]$Command)
        return Invoke-LocalPythonFromPodCommand $Command
    }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("proxy-runtime-argv-{0}" -f [Guid]::NewGuid().ToString("N"))
    $modelRoot = Join-Path $tempRoot "Model"
    try {
        [IO.Directory]::CreateDirectory($modelRoot) | Out-Null
        [IO.File]::WriteAllText((Join-Path $modelRoot "__init__.py"), "", (New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText((Join-Path $modelRoot "Config.py"), @'
SCHEDULE_ADDRESS = 'tcp://scheduler:8786'
REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_DB = 1
REDIS_PASSWORD = 'secret'
'@, (New-Object Text.UTF8Encoding($false)))

        $policy = [pscustomobject]@{
            consumer_runtime_target = [pscustomobject]@{
                repo_path = $tempRoot
                kafka_bootstrap = "kafka:9092"
                dask_scheduler = "tcp://scheduler:8786"
                redis_host = "redis"
                redis_port = 6379
                redis_db = 1
            }
        }
        $runtimeCode = @'
import json, os, sys
print(json.dumps({'kind': 'RuntimeArgvProbe', 'args': sys.argv[1:], 'kafka': os.environ['PVAM_KAFKA_BOOTSTRAP']}, sort_keys=True))
'@
        $result = Invoke-RuntimePythonCommand "scheduler-pod" "scheduler" $tempRoot $policy $runtimeCode @("alpha", "beta value")
        Assert-Equal 0 $result.ExitCode "runtime Python launcher must survive the real PowerShell 5.1 native argv boundary"
        $jsonLine = @($result.Output | Where-Object { ([string]$_).Trim().StartsWith("{") } | Select-Object -Last 1)
        if ($jsonLine.Count -ne 1) { throw "runtime Python argv probe returned no JSON" }
        $semantic = ([string]$jsonLine[0]) | ConvertFrom-Json
        Assert-Equal "RuntimeArgvProbe" $semantic.kind "runtime Python argv probe kind mismatch"
        Assert-Equal "alpha|beta value" (@($semantic.args) -join "|") "runtime Python arguments must remain intact"
        Assert-Equal "kafka:9092" $semantic.kafka "runtime Kafka bootstrap must remain intact"
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
    }
}

function Test-RuntimeJsonBase64Safe {
    Import-ProxyFunctions @("Invoke-RuntimePythonCommand", "ConvertTo-Utf8Base64Json")
    function script:Invoke-PodCommand {
        param([string]$Pod, [string]$Container, [object[]]$Command)
        return Invoke-LocalPythonFromPodCommand $Command
    }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("proxy-runtime-json-{0}" -f [Guid]::NewGuid().ToString("N"))
    $modelRoot = Join-Path $tempRoot "Model"
    try {
        [IO.Directory]::CreateDirectory($modelRoot) | Out-Null
        [IO.File]::WriteAllText((Join-Path $modelRoot "__init__.py"), "", (New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText((Join-Path $modelRoot "Config.py"), @'
SCHEDULE_ADDRESS = 'tcp://scheduler:8786'
REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_DB = 1
REDIS_PASSWORD = 'secret'
'@, (New-Object Text.UTF8Encoding($false)))

        $policy = [pscustomobject]@{
            consumer_runtime_target = [pscustomobject]@{
                repo_path = $tempRoot
                kafka_bootstrap = "kafka:9092"
                dask_scheduler = "tcp://scheduler:8786"
                redis_host = "redis"
                redis_port = 6379
                redis_db = 1
            }
        }
        $keys = @('system:idempotency:990014:uat-json:"quoted":done', 'system:idempotency:990014:space value:done')
        $encoded = ConvertTo-Utf8Base64Json $keys
        $runtimeCode = @'
import base64, json, sys
print(json.dumps({'kind': 'RuntimeJsonProbe', 'keys': json.loads(base64.b64decode(sys.argv[1]))}, sort_keys=True))
'@
        $result = Invoke-RuntimePythonCommand "scheduler-pod" "scheduler" $tempRoot $policy $runtimeCode @($encoded)
        Assert-Equal 0 $result.ExitCode "Base64 JSON must survive the real PowerShell 5.1 native argv boundary"
        $jsonLine = @($result.Output | Where-Object { ([string]$_).Trim().StartsWith("{") } | Select-Object -Last 1)
        if ($jsonLine.Count -ne 1) { throw "runtime Base64 JSON probe returned no JSON" }
        $semantic = ([string]$jsonLine[0]) | ConvertFrom-Json
        Assert-Equal ($keys -join "|") (@($semantic.keys) -join "|") "decoded JSON values must remain exact"

        $empty = if ($false) { @("unreachable") } else { @() }
        $emptyEncoded = ConvertTo-Utf8Base64Json $empty
        $emptyJson = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($emptyEncoded))
        Assert-Equal "[]" $emptyJson "a PowerShell pipeline-empty array must remain JSON []"
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
    }
}

function Test-PendingRecoveryJsonSafe {
    Import-ProxyFunctions @("ConvertTo-Utf8Base64Json", "Invoke-PendingRecoveryProof")
    function script:Assert-RequiredTokens { param($Tokens, [string]$Action) }
    function script:Get-LatestConsumerLifecycleSemantic {
        return [pscustomobject]@{operation="bind-secondary";deployment="dask-cluster-scheduler";container="scheduler";calc_month=1}
    }
    function script:Get-StageUatPeriodContext { return [pscustomobject]@{Primary=990013;Secondary=990014} }
    function script:Get-ConsumerLifecycleTarget { param($Policy,[string]$Deployment,[string]$Container); return [pscustomobject]@{pod_name_prefix="dask-cluster-scheduler-"} }
    function script:Get-ConsumerLifecycleSelectedPods { param([string]$Deployment,[string]$Container,[string]$Prefix); return @("scheduler-pod") }
    function script:Assert-ResourceAllowed { param([string]$Kind,[string]$Name) }
    function script:Get-CurrentCandidateSha { return "0123456789abcdef0123456789abcdef01234567" }
    function script:Verify-PodGitView { param([string]$Pod,[string]$Container,[string]$Remote,[string]$Candidate); return "/mnt/dask/Redemption/Redemption" }
    function script:Assert-SafeProducerValue { param([string]$Value,[string]$Name) }
    function script:Invoke-UserStatsSnapshot { param([string]$Pod,[string]$Container,[string]$Repo,$Policy,[string]$UserId,$Periods); return [pscustomobject]@{} }
    function script:Invoke-ControllerUatProducer {
        param([string]$Pod,[string]$Container,[string]$Repo,$Policy,$Spec)
        return [pscustomobject]@{
            ExitCode=0
            Output=@('{"payload_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')
        }
    }
    function script:Invoke-RuntimePythonCommand {
        param([string]$Pod,[string]$Container,[string]$Repo,$Policy,[string]$Code,[string[]]$Arguments)
        $decoded=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$Arguments[1]))|ConvertFrom-Json
        Assert-Equal 3 @($decoded).Count "pending recovery must send all three idempotency keys as Base64 JSON"
        Assert-Equal "system:idempotency:990014:" ([string]$decoded[0]).Substring(0,26) "pending recovery idempotency namespace mismatch"
        throw "C02_CAPTURED"
    }

    $policy=[pscustomobject]@{repo_remote_url="git@github.com:l343765828/Redemption.git"}
    Assert-ThrowsLike {
        Invoke-PendingRecoveryProof ([pscustomobject]@{user_id="U-UAT-001"}) $policy
    } "C02_CAPTURED" "pending recovery must Base64-encode JSON before the runtime boundary"
}

function Test-RedisProofCrossPeriodDistinctKeys {
    Import-ProxyFunctions @("Get-RedisProofKeys")
    $script:ExecutionId = "c2-r3-opus-s7-test"
    function script:Get-KafkaScenarioSemantic {
        param([string]$Scenario)
        return [pscustomobject]@{
            deliveries = @(
                [pscustomobject]@{role="original-order";key="uat-c2-r3-opus-s7-test-order"},
                [pscustomobject]@{role="refund";key="uat-c2-r3-opus-s7-test-refund"}
            )
        }
    }
    $policy = [pscustomobject]@{
        redis_proof_contracts = [pscustomobject]@{
            "cross-period-refund-ledgers" = [pscustomobject]@{scenario="cross-period-refund"}
        }
    }

    $result = Get-RedisProofKeys "cross-period-refund-ledgers" $policy
    $base = "pvam:uat:work02:$($script:ExecutionId):"
    $expected = New-Object System.Collections.Generic.List[string]
    $expected.Add($base + "order_ledger:uat-c2-r3-opus-s7-test-order")
    $expected.Add($base + "refund_reversal:uat-c2-r3-opus-s7-test-order")
    $expected.Add($base + "event_delivery:uat-c2-r3-opus-s7-test-order")
    $expected.Add($base + "event_delivery:uat-c2-r3-opus-s7-test-refund")
    Assert-Equal 4 @($result.Keys).Count "cross-period proof must retain four distinct exact Redis keys"
    Assert-Equal ($expected.ToArray() -join "|") (@($result.Keys) -join "|") "cross-period proof key identities mismatch"
}

function Test-RedisCleanupStagePrefixes([ValidateSet("controller", "caller")][string]$Mode = "controller") {
    Import-ProxyFunctions @(
        "Get-ExpandedRedisPrefixes",
        "ConvertTo-Utf8Base64Json",
        "Get-ControllerDerivedRedisScanPrefixes",
        "Invoke-Native",
        "Invoke-RuntimePythonCommand",
        "Invoke-RedisExactCleanup"
    )
    $script:ExecutionId = "c2-r3-opus-s7-test"
    function script:Get-StageUatPeriodContext {
        return [pscustomobject]@{Primary=990013;Secondary=990014}
    }
    $policy = [IO.File]::ReadAllText($PolicyPath, [Text.Encoding]::UTF8) | ConvertFrom-Json

    $actual = @(Get-ControllerDerivedRedisScanPrefixes $policy)
    $expected = @(
        "pvam:uat:work02:c2-r3-opus-s7-test:",
        "system:idempotency:990013:",
        "system:idempotency:990014:",
        "system:idempotency:placement:990013:",
        "system:idempotency:placement:990014:",
        "system:idempotency:elite:990013:",
        "system:idempotency:elite:990014:",
        "user_stats:Model.User.UserStats.UserStats:990013:",
        "user_stats:Model.User.UserStats.UserStats:990014:",
        "elite_bonus_stats:Model.User.EliteBonusStats.EliteBonusStats:990013:",
        "elite_bonus_stats:Model.User.EliteBonusStats.EliteBonusStats:990014:",
        "eb_source:990013:",
        "eb_source:990014:"
    )
    Assert-Equal ($expected -join "|") ($actual -join "|") "controller cleanup must scan only execution- or period-scoped prefixes"
    if ($actual -contains "pvam:event_delivery:") { throw "controller cleanup must not scan an unscoped global prefix" }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("proxy-redis-cleanup-{0}" -f [Guid]::NewGuid().ToString("N"))
    $modelRoot = Join-Path $tempRoot "Model"
    try {
        [IO.Directory]::CreateDirectory($modelRoot) | Out-Null
        [IO.File]::WriteAllText((Join-Path $modelRoot "__init__.py"), "", (New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText((Join-Path $modelRoot "Config.py"), @'
SCHEDULE_ADDRESS = 'tcp://scheduler:8786'
REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_DB = 1
REDIS_PASSWORD = 'secret'
'@, (New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText((Join-Path $tempRoot "redis.py"), @'
import fnmatch
STORE = {
    'pvam:uat:work02:c2-r3-opus-s7-test:event_delivery:failed-proof',
    'eb_source:990013:U-UAT-001',
    'elite_bonus_stats:Model.User.EliteBonusStats.EliteBonusStats:990014:1',
    'user_stats:Model.User.UserStats.UserStats:990013:3',
    'pvam:event_delivery:must-remain-unscoped',
}
class Redis:
    def __init__(self, **kwargs): pass
    def scan_iter(self, match, count=200):
        return iter(sorted(k for k in STORE if fnmatch.fnmatchcase(k, match)))
    def delete(self, *keys):
        found = sum(1 for key in keys if key in STORE)
        STORE.difference_update(keys)
        return found
    def exists(self, key): return key in STORE
'@, (New-Object Text.UTF8Encoding($false)))

        $script:ControllerCleanupKeys = @(0..313 | ForEach-Object {
            "pvam:uat:work02:c2-r3-opus-s7-test:event_delivery:large-$('{0:D3}' -f $_)-$(('x' * 64))"
        })
        $policy = [pscustomobject]@{
            redis_exact_cleanup_prefixes = @($policy.redis_exact_cleanup_prefixes)
            consumer_runtime_target = [pscustomobject]@{
                repo_path = $tempRoot
                kafka_bootstrap = "kafka:9092"
                dask_scheduler = "tcp://scheduler:8786"
                redis_host = "redis"
                redis_port = 6379
                redis_db = 1
            }
        }
        function script:Assert-RequiredTokens { param($Tokens, [string]$Action) }
        function script:Get-ControllerDerivedRedisCleanupKeys { param($Policy) return @($script:ControllerCleanupKeys) }
        function script:Test-RedisKeyGoverned { param([string]$Key, $Templates) return $true }
        function script:Resolve-ConsumerRuntimeTarget {
            param($Request, $Policy, [string]$Action)
            return [pscustomobject]@{Pod="scheduler-pod";Container="scheduler";Repo=$tempRoot}
        }
        function script:Invoke-PodCommand {
            param([string]$Pod, [string]$Container, [object[]]$Command)
            return Invoke-LocalPythonFromPodCommand $Command
        }
        function script:Invoke-PodCommandWithInput {
            param([string]$Pod, [string]$Container, [object[]]$Command, [string]$StandardInput)
            if (@($Command).Count -lt 3 -or [string]$Command[0] -ne "python3") { throw "expected a python3 pod command" }
            return Invoke-Native $script:TestPythonPath @($Command | Select-Object -Skip 1) $StandardInput
        }

        if ($Mode -eq "controller") {
            $result = Invoke-RedisExactCleanup ([pscustomobject]@{controller_derived=$true}) $policy
            if ($result.ExitCode -ne 0) { throw "controller-derived Redis cleanup runtime failed: $(@($result.Output) -join ' | ')" }
            Assert-Equal 0 $result.ExitCode "controller-derived Redis cleanup runtime must succeed with more than 313 exact keys"
            Assert-Equal 318 ([int]$result.Semantic.requested_count) "cleanup must union 314 exact evidence keys with four stage-scoped discoveries"
            Assert-Equal 4 ([int]$result.Semantic.discovered_count) "cleanup must report stage-scoped discoveries"
            Assert-Equal 0 ([int]$result.Semantic.remaining_count) "cleanup must delete every resolved exact key"
            if (@($result.Semantic.requested_keys) -contains "pvam:event_delivery:must-remain-unscoped") {
                throw "controller cleanup must leave globally scoped Redis keys untouched"
            }
        }
        else {
            foreach ($size in @(1, 2, 80)) {
                $callerKeys = @(0..($size - 1) | ForEach-Object {
                    "pvam:uat:work02:c2-r3-opus-s7-test:event_delivery:caller-$size-$('{0:D3}' -f $_)"
                })
                $result = Invoke-RedisExactCleanup ([pscustomobject]@{keys=$callerKeys}) $policy
                if ($result.ExitCode -ne 0) { throw "caller Redis cleanup size $size failed: $(@($result.Output) -join ' | ')" }
                Assert-Equal $size ([int]$result.Semantic.requested_count) "caller Redis cleanup key count mismatch for size $size"
                Assert-Equal 0 ([int]$result.Semantic.discovered_count) "caller Redis cleanup must not perform stage-prefix discovery"
                Assert-Equal 0 ([int]$result.Semantic.remaining_count) "caller Redis cleanup must leave no requested keys for size $size"
            }
        }
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
    }
}

function Test-RuntimeConfigPolicyRedirectBlocked {
    Import-ProxyFunctions @("Invoke-RuntimePythonCommand")
    function script:Invoke-PodCommand {
        param([string]$Pod, [string]$Container, [object[]]$Command)
        return Invoke-LocalPythonFromPodCommand $Command
    }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("proxy-runtime-policy-redirect-{0}" -f [Guid]::NewGuid().ToString("N"))
    $modelRoot = Join-Path $tempRoot "Model"
    try {
        [IO.Directory]::CreateDirectory($modelRoot) | Out-Null
        [IO.File]::WriteAllText((Join-Path $modelRoot "__init__.py"), "", (New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText((Join-Path $modelRoot "Config.py"), @'
SCHEDULE_ADDRESS = 'tcp://scheduler:8786'
REDIS_HOST = 'redis'
REDIS_PORT = 6379
REDIS_DB = 9
REDIS_PASSWORD = 'secret'
'@, (New-Object Text.UTF8Encoding($false)))

        $policy = [pscustomobject]@{
            consumer_runtime_target = [pscustomobject]@{
                repo_path = $tempRoot
                kafka_bootstrap = "kafka:9092"
                dask_scheduler = "tcp://scheduler:8786"
                redis_host = "redis"
                redis_port = 6379
                redis_db = 1
            }
        }
        $result = Invoke-RuntimePythonCommand "scheduler-pod" "scheduler" $tempRoot $policy "print('must-not-run')" @()
        if ($result.ExitCode -eq 0) { throw "Candidate Config redirected Redis DB despite the policy-pinned runtime target" }
        $text = @($result.Output) -join "`n"
        if ($text -notlike "*UAT_ACTION_POLICY_DENIED: runtime Model.Config does not match policy-pinned endpoints*") {
            throw "runtime redirect rejection did not expose the governed denial reason: $text"
        }
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
    }
}

function Test-ConsumerControllerPayloadSafe {
    Import-ProxyFunctions @("Invoke-ConsumerRuntimeController")
    function script:Invoke-PodCommand {
        param([string]$Pod, [string]$Container, [object[]]$Command)
        return Invoke-LocalPythonFromPodCommand $Command
    }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("proxy-consumer-payload-{0}" -f [Guid]::NewGuid().ToString("N"))
    $savedProxyRoot = $script:ProxyRootForTests
    try {
        [IO.Directory]::CreateDirectory($tempRoot) | Out-Null
        [IO.File]::WriteAllText((Join-Path $tempRoot "consumer-runtime-controller-r9.py"), @'
import json, sys
payload = json.loads(sys.argv[2])
print(json.dumps({'kind': 'ConsumerRuntimeControllerResult', 'operation': sys.argv[1], 'payload': payload}, sort_keys=True))
'@, (New-Object Text.UTF8Encoding($false)))
        $script:ProxyRootForTests = $tempRoot
        $payload = [pscustomobject]@{
            message = 'quoted "value" with spaces'
            nested = [pscustomobject]@{ count = 3 }
        }

        $result = Invoke-ConsumerRuntimeController "scheduler-pod" "scheduler" "replace" $payload
        Assert-Equal 0 $result.ExitCode "consumer controller payload must survive the real PowerShell 5.1 native argv boundary"
        Assert-Equal "replace" $result.Semantic.operation "consumer controller operation mismatch"
        Assert-Equal 'quoted "value" with spaces' $result.Semantic.payload.message "consumer controller JSON string must remain intact"
        Assert-Equal 3 ([int]$result.Semantic.payload.nested.count) "consumer controller nested JSON must remain intact"
    }
    finally {
        $script:ProxyRootForTests = $savedProxyRoot
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
    }
}

function Test-PytestFullExclusions {
    Import-ProxyFunctions @("Assert-RequiredTokens", "Invoke-PytestProfile")
    $script:AllMutableTokens = @("exec")
    $script:AuthorizedActions = @("exec")
    function script:Get-PodRepoRoot {
        param([string]$Pod, [string]$Container, $Policy)
        return $script:PytestRepoRoot
    }
    function script:Invoke-PodCommand {
        param([string]$Pod, [string]$Container, [object[]]$Command)
        return Invoke-LocalPythonFromPodCommand $Command $script:TestPytestPythonPath
    }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("proxy-pytest-full-{0}" -f [Guid]::NewGuid().ToString("N"))
    $script:PytestRepoRoot = $tempRoot
    $excluded = @(
        "User/Test/test_team_bonus_tb.py",
        "User/test_bonus_pipeline_auto_check.py",
        "User/test_userstatsservice_elite_report.py"
    )
    try {
        foreach ($relativePath in @($excluded + "tests/test_retained_full_suite.py")) {
            $absolutePath = Join-Path $tempRoot $relativePath
            [IO.Directory]::CreateDirectory((Split-Path -Parent $absolutePath)) | Out-Null
            $content = if ($relativePath -eq "tests/test_retained_full_suite.py") {
                "def test_retained_full_suite():`n    assert True`n"
            }
            else {
                "raise RuntimeError('baseline-broken module must be excluded')`n"
            }
            [IO.File]::WriteAllText($absolutePath, $content, (New-Object Text.UTF8Encoding($false)))
        }

        $policy = [IO.File]::ReadAllText($PolicyPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
        $result = Invoke-PytestProfile ([pscustomobject]@{pod="scheduler-pod";container="scheduler"}) $policy $true
        Assert-Equal 0 $result.ExitCode "PytestFull must retain the full suite while excluding only governed baseline-broken modules"
        Assert-Equal ($excluded -join "|") (@($result.Semantic.excluded_paths) -join "|") "PytestFull evidence must record the exact governed exclusions"
        Assert-Equal 0 @($result.Semantic.targets).Count "PytestFull must remain a full-suite action rather than selected-target execution"
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
    }
}

function Test-PytestFullUnsafeExclusion {
    Import-ProxyFunctions @("Assert-RequiredTokens", "Invoke-PytestProfile")
    $script:AllMutableTokens = @("exec")
    $script:AuthorizedActions = @("exec")
    $script:pytestPodCommandCalls = 0
    function script:Get-PodRepoRoot {
        param([string]$Pod, [string]$Container, $Policy)
        return "/mnt/dask/Redemption/Redemption"
    }
    function script:Invoke-PodCommand {
        param([string]$Pod, [string]$Container, [object[]]$Command)
        $script:pytestPodCommandCalls++
        return [pscustomobject]@{ExitCode=0;Output=@("unexpected invocation")}
    }
    $policy = [pscustomobject]@{
        pytest_full_excluded_paths = @("../outside.py")
        pytest_selected_exact = @()
        pytest_selected_prefixes = @()
    }

    Assert-ThrowsLike {
        Invoke-PytestProfile ([pscustomobject]@{pod="scheduler-pod";container="scheduler"}) $policy $true
    } "UAT_ACTION_POLICY_DENIED:*" "PytestFull must reject unsafe exclusion paths"
    Assert-Equal 0 $script:pytestPodCommandCalls "PytestFull must reject unsafe exclusions before invoking the pod"
}

$cases = [ordered]@{
    "node-repo-partial-find" = { Test-NodeRepoPartialFind }
    "node-repo-no-candidate" = { Test-NodeRepoNoCandidate }
    "node-repo-ambiguous" = { Test-NodeRepoAmbiguous }
    "pod-repo-partial-find" = { Test-PodRepoPartialFind }
    "pod-repo-no-candidate" = { Test-PodRepoNoCandidate }
    "pod-repo-ambiguous" = { Test-PodRepoAmbiguous }
    "pod-repo-scope-denied" = { Test-PodRepoScopeDenied }
    "scheduler-skip-failed" = { Test-SchedulerSkipsFailedPods }
    "runtime-python-argv-safe" = { Test-RuntimePythonArgvSafe }
    "runtime-json-base64-safe" = { Test-RuntimeJsonBase64Safe }
    "pending-recovery-json-safe" = { Test-PendingRecoveryJsonSafe }
    "redis-proof-cross-period-distinct-keys" = { Test-RedisProofCrossPeriodDistinctKeys }
    "redis-cleanup-stage-prefixes" = { Test-RedisCleanupStagePrefixes }
    "redis-cleanup-caller-key-sizes" = { Test-RedisCleanupStagePrefixes "caller" }
    "runtime-config-policy-redirect-blocked" = { Test-RuntimeConfigPolicyRedirectBlocked }
    "consumer-controller-payload-safe" = { Test-ConsumerControllerPayloadSafe }
    "pytest-full-exclusions" = { Test-PytestFullExclusions }
    "pytest-full-unsafe-exclusion" = { Test-PytestFullUnsafeExclusion }
}

$selectedCases = if ($Case -eq "all") { @($cases.Keys) } else { @($Case) }
$failures = New-Object System.Collections.Generic.List[string]
foreach ($name in $selectedCases) {
    try {
        & $cases[$name]
        Write-Host "[PROXY-RUNTIME-REGRESSION] PASS $name"
    }
    catch {
        $failures.Add("${name}: $($_.Exception.Message)")
        Write-Host "[PROXY-RUNTIME-REGRESSION] FAIL $name :: $($_.Exception.Message)"
    }
}

if ($failures.Count -gt 0) {
    throw "proxy runtime regression failures: $($failures -join ' | ')"
}
Write-Host "[PROXY-RUNTIME-REGRESSION] SUMMARY passed=$($selectedCases.Count) failed=0"
