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
        "scheduler-skip-failed"
    )]
    [string]$Case = "all",
    [string]$ProxyPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProxyPath) {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    $ProxyPath = Join-Path $repoRoot ".loop-engine\uat-action-proxy.ps1"
}
if (-not (Test-Path -LiteralPath $ProxyPath -PathType Leaf)) {
    throw "proxy script missing: $ProxyPath"
}

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

$cases = [ordered]@{
    "node-repo-partial-find" = { Test-NodeRepoPartialFind }
    "node-repo-no-candidate" = { Test-NodeRepoNoCandidate }
    "node-repo-ambiguous" = { Test-NodeRepoAmbiguous }
    "pod-repo-partial-find" = { Test-PodRepoPartialFind }
    "pod-repo-no-candidate" = { Test-PodRepoNoCandidate }
    "pod-repo-ambiguous" = { Test-PodRepoAmbiguous }
    "pod-repo-scope-denied" = { Test-PodRepoScopeDenied }
    "scheduler-skip-failed" = { Test-SchedulerSkipsFailedPods }
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
