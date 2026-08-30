param(
    [Parameter(Mandatory=$true)][string]$EvidenceDir,
    [switch]$DryRun,
    [string]$ProxyScript='',
    [string]$RequestPath=''
)

$ErrorActionPreference='Stop'
$Utf8NoBom=New-Object System.Text.UTF8Encoding($false)

function Read-ProxyEvidenceFields([string]$Path) {
    $fields=@{}
    foreach($line in [IO.File]::ReadAllLines($Path,[Text.Encoding]::UTF8)){
        if(-not $line){continue}
        $index=$line.IndexOf('=')
        if($index -le 0){throw "PVAM_V2_FINALIZER invalid evidence line in $Path"}
        $key=$line.Substring(0,$index);$value=$line.Substring($index+1)
        if($key -notmatch '^[a-z0-9_]+$' -or $fields.ContainsKey($key)){throw "PVAM_V2_FINALIZER invalid evidence field in $Path"}
        $fields[$key]=$value
    }
    return $fields
}

function Get-LatestConfigOperation([string]$Path) {
    $latest=''
    if(-not (Test-Path -LiteralPath $Path -PathType Container)){return $latest}
    foreach($file in @(Get-ChildItem -LiteralPath $Path -File -Filter 'action-*.log' -Force|Sort-Object FullName)){
        $fields=Read-ProxyEvidenceFields $file.FullName
        if([string]$fields['action'] -ne 'PVAmountV2Config' -or [string]$fields['outcome'] -ne 'SUCCESS' -or -not $fields.ContainsKey('semantic_json_b64')){continue}
        try{$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$fields['semantic_json_b64']));$semantic=$raw|ConvertFrom-Json}catch{throw "PVAM_V2_FINALIZER invalid config semantic evidence in $($file.FullName)"}
        if([string]$semantic.kind -ne 'PVAmountV2ConfigResult'){continue}
        $operation=([string]$semantic.operation).Trim().ToLowerInvariant()
        if($operation -notin @('snapshot','activate','restore')){throw "PVAM_V2_FINALIZER invalid config operation in $($file.FullName)"}
        $latest=$operation
    }
    return $latest
}

function Invoke-ProxyRequest($Payload) {
    $json=$Payload|ConvertTo-Json -Depth 8 -Compress
    $parent=Split-Path -Parent $RequestPath
    if(-not (Test-Path -LiteralPath $parent -PathType Container)){New-Item -ItemType Directory -Force -Path $parent|Out-Null}
    [IO.File]::WriteAllText($RequestPath,$json,$Utf8NoBom)
    $output=@(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ProxyScript 2>&1)
    $exitCode=$LASTEXITCODE
    foreach($line in $output){Write-Output ([string]$line)}
    if($exitCode -ne 0){throw "proxy action $([string]$Payload.action) failed with exit code $exitCode"}
}

$latestOperation=Get-LatestConfigOperation $EvidenceDir
if($latestOperation -ne 'activate'){
    Write-Output 'PVAM_V2_FINALIZER no-op'
    exit 0
}

$sequence='RedisDeleteExactKeys -> ConsumerLifecycle restore -> PVAmountV2Config restore'
if($DryRun){
    Write-Output $sequence
    exit 0
}

if(-not $ProxyScript){$ProxyScript=Join-Path $PSScriptRoot 'uat-action-proxy.ps1'}
if(-not (Test-Path -LiteralPath $ProxyScript -PathType Leaf)){throw "PVAM_V2_FINALIZER proxy missing: $ProxyScript"}
if(-not $RequestPath){
    $stage=([string]$env:VERIFIER_STAGE).Trim().ToLowerInvariant()
    if($stage -notin @('opus','fable')){throw 'PVAM_V2_FINALIZER VERIFIER_STAGE must be OPUS or FABLE'}
    $mainRepo=Split-Path -Parent $PSScriptRoot
    $RequestPath=Join-Path $mainRepo ('.loop-output\verifier-state\{0}\proxy-request.json' -f $stage)
}

$failures=New-Object System.Collections.Generic.List[string]
foreach($step in @(
    [ordered]@{action='RedisDeleteExactKeys';controller_derived=$true},
    [ordered]@{action='ConsumerLifecycle';operation='restore'},
    [ordered]@{action='PVAmountV2Config';operation='restore'}
)){
    try{Invoke-ProxyRequest $step}
    catch{$failures.Add($_.Exception.Message);Write-Error $_.Exception.Message -ErrorAction Continue}
}
if($failures.Count -gt 0){throw ('PVAM_V2_FINALIZER incomplete: '+($failures.ToArray() -join '; '))}
Write-Output "PVAM_V2_FINALIZER complete: $sequence"
