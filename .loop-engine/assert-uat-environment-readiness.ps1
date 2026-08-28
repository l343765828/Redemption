param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Core", "FullUat")]
    [string]$Mode,

    [ValidateSet("OPUS", "FABLE")]
    [string]$Stage = "OPUS",

    [string]$ReadinessFile = $env:UAT_READINESS_FILE,
    [string]$PolicyFile = $env:UAT_ACTION_POLICY_FILE
)

$ErrorActionPreference = "Stop"

if (-not $ReadinessFile) { throw "UAT_READINESS_FILE is required" }
if (-not (Test-Path $ReadinessFile)) { throw "UAT readiness file missing: $ReadinessFile" }
$readiness = [IO.File]::ReadAllText($ReadinessFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
if ([int]$readiness.schema_version -ne 1) { throw "unsupported UAT environment readiness schema" }
if ([string]$readiness.historical_compatibility.v8_v9_r2_history -ne "NOT_PRESENT") {
    throw "unexpected historical compatibility status: $($readiness.historical_compatibility.v8_v9_r2_history)"
}
if ([string]$readiness.period_pool.reservation_status -ne "CONFIRMED") {
    throw "UAT period reservation is not confirmed"
}

if ($Mode -eq "Core") {
    Write-Output "UAT_ENVIRONMENT_READINESS=READY mode=Core"
    exit 0
}

if (-not $PolicyFile) { throw "UAT_ACTION_POLICY_FILE is required for FullUat readiness" }
if (-not (Test-Path $PolicyFile)) { throw "UAT action policy missing: $PolicyFile" }
$policy = [IO.File]::ReadAllText($PolicyFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json

$blockers = New-Object System.Collections.Generic.List[string]
if ([string]$readiness.period_pool.real_pvam_db_occupancy -ne "CONFIRMED") {
    $blockers.Add("UAT_PERIOD_DB_OCCUPANCY_NOT_CONFIRMED")
}

$requiredActions = @($policy.required_success_actions_by_stage.$Stage)
$requiresConsumerLifecycle = $requiredActions -contains "ConsumerLifecycle"
$targets = @($policy.consumer_lifecycle_targets)
if ($requiresConsumerLifecycle -and (([string]$readiness.consumer_lifecycle.status -ne "AVAILABLE") -or $targets.Count -eq 0)) {
    $blockers.Add("CONSUMER_LIFECYCLE_UNAVAILABLE")
}

if ($blockers.Count -gt 0) {
    Write-Output ("UAT_ENVIRONMENT_READINESS=BLOCKED mode=FullUat stage={0} blockers={1}" -f $Stage, ($blockers -join ","))
    exit 2
}

Write-Output ("UAT_ENVIRONMENT_READINESS=READY mode=FullUat stage={0}" -f $Stage)
exit 0
