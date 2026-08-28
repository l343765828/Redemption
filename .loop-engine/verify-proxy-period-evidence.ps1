param(
    [Parameter(Mandatory=$true)][ValidateSet('OPUS','FABLE')][string]$Stage,
    [Parameter(Mandatory=$true)][string]$EvidenceDir,
    [Parameter(Mandatory=$true)][int]$ExpectedSlot,
    [Parameter(Mandatory=$true)][int]$ExpectedPrimary,
    [Parameter(Mandatory=$true)][int]$ExpectedSecondary,
    [Parameter(Mandatory=$true)][string]$ExpectedPoolSha256,
    [Parameter(Mandatory=$true)][string]$ExpectedAuthorizationScopeSha256,
    [Parameter(Mandatory=$true)][string]$ExpectedExecutionId,
    [Parameter(Mandatory=$true)][string]$PolicyPath,
    [ValidateSet('RequireComplete','ValidateExistingOnly')][string]$VerificationMode='RequireComplete',
    [string]$ExpectedCandidateSha='',
    [string]$ExpectedBaselineSha=''
)
$ErrorActionPreference='Stop'
$Utf8NoBom=New-Object System.Text.UTF8Encoding($false)
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

function Get-TextSha256([string]$Text) { $sha=[Security.Cryptography.SHA256]::Create(); try { return ([BitConverter]::ToString($sha.ComputeHash($Utf8NoBom.GetBytes($Text)))).Replace('-','').ToLowerInvariant() } finally {$sha.Dispose()} }
function Decode-JsonB64([string]$Value,[string]$What,[string]$FileName){ try{$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Value)); return $raw|ConvertFrom-Json}catch{throw "proxy evidence $What invalid in $FileName"} }
function Test-KeyCoversIdentity([string]$Key,[string]$Identity){ return $Key.EndsWith($Identity,[StringComparison]::Ordinal) -or $Key.Contains(":"+$Identity+":") -or $Key.Contains(":"+$Identity+"_") }
function Get-IdempotencyDoneKey([string]$Namespace,[int]$Period,[string]$Identity){
    if($Namespace -eq 'userstats'){return "system:idempotency:${Period}:${Identity}:done"}
    if($Namespace -eq 'placement'){return "system:idempotency:placement:${Period}:${Identity}:done"}
    if($Namespace -eq 'elite'){return "system:idempotency:elite:${Period}:${Identity}:done"}
    throw "unknown idempotency namespace: $Namespace"
}
function Get-LedgerCleanupKeys($Record,[string]$ExecutionId){
    $base="pvam:uat:work02:${ExecutionId}:"
    $keys=New-Object System.Collections.Generic.List[string]
    $identity=([string]$Record.identity).Trim();if(-not $identity){return @()}
    $keys.Add($base+'event_delivery:'+$identity)
    $topic=([string]$Record.topic).Trim()
    if($topic -eq 'pvam-pv-orders'){$keys.Add($base+'order_ledger:'+$identity);$keys.Add($base+'order_ledger:__period_index__')}
    if($topic -eq 'pvam-pv-refunds'){
        $original=([string]$Record.original_order_id).Trim()
        if($original){$keys.Add($base+'refund_reversal:'+$original)}
    }
    return @($keys.ToArray())
}
function Test-GitHunkContract($Semantic,$Policy){
    if(-not [bool]$Semantic.line_scope_ok){return $false}
    foreach($guard in @($Policy.git_hunk_allowlist.PSObject.Properties)){
        $path=[string]$guard.Name;$expected=@($guard.Value);$actual=@($Semantic.changed_hunks|Where-Object{[string]$_.path -eq $path})
        if($actual.Count -ne $expected.Count){return $false}
        for($i=0;$i -lt $expected.Count;$i++){
            $a=$actual[$i];$e=$expected[$i]
            if([int]$a.old_start -ne [int]$e.old_start -or [int]$a.old_count -ne [int]$e.old_count -or [int]$a.new_start -ne [int]$e.new_start -or [int]$a.new_count -ne [int]$e.new_count){return $false}
        }
    }
    return $true
}
function Test-ChangedPathAllowed([string]$Path,$Policy){
    $value=([string]$Path).Replace('\','/').Trim()
    foreach($raw in @($Policy.git_change_allowlist)){
        $pattern=([string]$raw).Replace('\','/').Trim()
        if(-not $pattern){continue}
        if($pattern.EndsWith('*')){if($value.StartsWith($pattern.Substring(0,$pattern.Length-1),[StringComparison]::Ordinal)){return $true}}
        elseif($value -eq $pattern){return $true}
    }
    return $false
}
if ($ExpectedSlot -lt 1 -or $ExpectedPrimary -lt 1 -or $ExpectedSecondary -lt 1 -or $ExpectedPrimary -eq $ExpectedSecondary) { throw 'invalid expected stage period allocation' }
if ($ExpectedPoolSha256 -notmatch '^[0-9a-f]{64}$' -or $ExpectedAuthorizationScopeSha256 -notmatch '^[0-9a-f]{64}$') { throw 'invalid expected proxy evidence hashes' }
if (-not $ExpectedExecutionId) { throw 'ExpectedExecutionId is required' }
$ExpectedCandidateSha = ([string]$ExpectedCandidateSha).Trim().ToLowerInvariant()
if ($ExpectedCandidateSha -notmatch '^[0-9a-f]{40}$') { throw 'ExpectedCandidateSha missing/invalid' }
if ($ExpectedBaselineSha -and $ExpectedBaselineSha -notmatch '^[0-9a-fA-F]{40}$'){throw 'ExpectedBaselineSha invalid'}
$ExpectedCandidateSha=$ExpectedCandidateSha.ToLowerInvariant();$ExpectedBaselineSha=$ExpectedBaselineSha.ToLowerInvariant()
if (-not (Test-Path -LiteralPath $PolicyPath -PathType Leaf)) { throw 'proxy policy missing' }
$policy=[IO.File]::ReadAllText($PolicyPath,[Text.Encoding]::UTF8)|ConvertFrom-Json
if ([int]$policy.schema_version -ne 8) { throw 'unsupported proxy policy schema' }
if([int]$policy.controller_evidence_schema -ne 10){throw 'unsupported controller evidence schema'}
$required_success_actions=@()
$prop=@($policy.required_success_actions_by_stage.PSObject.Properties|Where-Object {$_.Name -eq $Stage}|Select-Object -First 1)[0]
if($prop){$required_success_actions=@($prop.Value|ForEach-Object {[string]$_})}
if (-not (Test-Path -LiteralPath $EvidenceDir -PathType Container)) {
    if($VerificationMode -eq 'ValidateExistingOnly'){Write-Output "[PROXY-EVIDENCE] PASS stage=$Stage mode=$VerificationMode files=0";exit 0}
    throw "proxy evidence directory missing for required $Stage actions: $EvidenceDir"
}
$files=@(Get-ChildItem -LiteralPath $EvidenceDir -File -Filter 'action-*.log' -Force|Sort-Object FullName)
if ($files.Count -eq 0) {
    if($VerificationMode -eq 'ValidateExistingOnly'){Write-Output "[PROXY-EVIDENCE] PASS stage=$Stage mode=$VerificationMode files=0";exit 0}
    throw "proxy action evidence missing for required $Stage actions"
}
$success=@{};$successfulScenarios=@{};$dbsize=@{};$delivered=New-Object System.Collections.Generic.List[string];$deliveredRecords=New-Object System.Collections.Generic.List[object];$cleanupKeys=New-Object System.Collections.Generic.List[string];$successfulSelectedTargets=New-Object System.Collections.Generic.List[string];$lifecycleOps=@{};$observedScenarios=@{};$lifecycleOrder=@{};$observeOrder=@{};$dispatchedIdentities=@{};$redisProofs=@{};$uatProofs=@{};$uatProofOrder=@{};$runtimeGitUpdateOk=$false;[long]$totalDeleted=0;[int]$successOrdinal=0
foreach($file in $files) {
    $fields=Read-ProxyEvidenceFields $file.FullName
    foreach($name in @('stage','action','request_sha256','request_json_b64','stage_scope_sha256','uat_execution_id','stage_period_slot','stage_period_primary','stage_period_secondary','stage_period_pool_sha256','authorized_actions','required_tokens','outcome','exit_code')){if(-not $fields.ContainsKey($name)){throw "proxy evidence missing $name in $($file.Name)"}}
    if([string]$fields['stage'] -ne $Stage){throw "proxy evidence stage mismatch in $($file.Name)"}
    if([string]$fields['stage_scope_sha256'] -ne $ExpectedAuthorizationScopeSha256){throw "proxy evidence authorization scope mismatch in $($file.Name)"}
    if([string]$fields['uat_execution_id'] -ne $ExpectedExecutionId){throw "proxy evidence execution identity mismatch in $($file.Name)"}
    if([int]$fields['stage_period_slot'] -ne $ExpectedSlot -or [int]$fields['stage_period_primary'] -ne $ExpectedPrimary -or [int]$fields['stage_period_secondary'] -ne $ExpectedSecondary){throw "proxy evidence period mismatch in $($file.Name)"}
    if(([string]$fields['stage_period_pool_sha256']).ToLowerInvariant() -ne $ExpectedPoolSha256.ToLowerInvariant()){throw "proxy evidence period pool SHA mismatch in $($file.Name)"}
    try{$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$fields['request_json_b64']))}catch{throw "proxy evidence request_json_b64 invalid in $($file.Name)"}
    if((Get-TextSha256 $raw) -ne ([string]$fields['request_sha256']).ToLowerInvariant()){throw "proxy evidence request hash mismatch in $($file.Name)"}
    try{$request=$raw|ConvertFrom-Json}catch{throw "proxy evidence request JSON invalid in $($file.Name)"}
    $action=[string]$fields['action'];if(([string]$request.action).Trim() -ne $action){throw "proxy evidence action/request mismatch in $($file.Name)"}
    $authorized=@(([string]$fields['authorized_actions']).Split(',')|ForEach-Object {$_.Trim().ToLowerInvariant()}|Where-Object {$_})
    foreach($token in @(([string]$fields['required_tokens']).Split(',')|ForEach-Object {$_.Trim().ToLowerInvariant()}|Where-Object {$_})){if($authorized -notcontains $token){throw "proxy evidence required token '$token' outside authorized scope in $($file.Name)"}}
    $outcome=[string]$fields['outcome'];if($outcome -notin @('SUCCESS','DENIED','BLOCKED','FAILED')){throw "invalid proxy evidence outcome in $($file.Name)"}
    if($outcome -ne 'SUCCESS'){continue}
    if([int]$fields['exit_code'] -ne 0){throw "successful proxy evidence has nonzero exit code in $($file.Name)"}
    $successOrdinal++
    $success[$action]=$true
    $semantic=$null
    if($fields.ContainsKey('semantic_json_b64')){$semantic=Decode-JsonB64 ([string]$fields['semantic_json_b64']) 'semantic_json_b64' $file.Name}
    if($action -eq 'GitAudit'){
        if(-not $semantic -or [string]$semantic.kind -ne 'GitAuditResult'){throw "GitAuditResult semantic evidence missing in $($file.Name)"}
        if(-not [bool]$semantic.worktree_clean){throw "GitAudit semantic failure: worktree is dirty"}
        if((([string]$semantic.local_head).ToLowerInvariant() -ne $ExpectedCandidateSha -or ([string]$semantic.remote_head).ToLowerInvariant() -ne $ExpectedCandidateSha)){throw "GitAudit semantic failure: candidate SHA mismatch"}
        if($ExpectedBaselineSha -and ([string]$semantic.merge_base).ToLowerInvariant() -ne $ExpectedBaselineSha){throw "GitAudit semantic failure: merge-base mismatch"}
        if(([string]$semantic.handoff_candidate_sha).ToLowerInvariant() -ne $ExpectedCandidateSha){throw "GitAudit semantic failure: handoff candidate SHA mismatch"}
        if(-not [bool]$semantic.change_allowlist_ok){throw "GitAudit semantic failure: changed file allowlist was not satisfied"}
        if(-not (Test-GitHunkContract $semantic $policy)){throw "GitAudit semantic failure: changed hunk line-level contract was not satisfied"}
        foreach($changed in @($semantic.changed_files)){
            if(-not ([string]$changed).Trim()){throw "GitAudit semantic failure: blank changed file"}
            if(-not (Test-ChangedPathAllowed ([string]$changed) $policy)){throw "GitAudit semantic failure: changed file outside controller allowlist: $changed"}
        }
    }
    elseif($action -eq 'GitUpdate'){
        if(-not $semantic -or [string]$semantic.kind -ne 'GitUpdateResult'){throw "GitUpdateResult semantic evidence missing in $($file.Name)"}
        foreach($field in @('candidate_sha','remote_head','host_head','pod_head')){if(([string]$semantic.$field).ToLowerInvariant() -ne $ExpectedCandidateSha){throw "runtime candidate SHA mismatch in GitUpdate field ${field}"}}
        $runtimeGitUpdateOk=$true
    }
    elseif($action -eq 'ConsumerLifecycle'){
        if(-not $semantic -or [string]$semantic.kind -ne 'ConsumerLifecycleResult'){throw "ConsumerLifecycleResult semantic evidence missing in $($file.Name)"}
        if([string]$semantic.runtime_mode -ne 'scheduler-pod-temporary-process'){throw "ConsumerLifecycle runtime mode mismatch in $($file.Name)"}
        $op=([string]$semantic.operation).ToLowerInvariant();if($op){$lifecycleOps[$op]=$semantic;$lifecycleOrder[$op]=$successOrdinal}
        if($op -eq 'bind-primary'){if([int]$semantic.bound_period -ne $ExpectedPrimary){throw 'ConsumerLifecycle primary bound period mismatch'}}
        if($op -eq 'bind-secondary'){if([int]$semantic.bound_period -ne $ExpectedSecondary){throw 'ConsumerLifecycle secondary bound period mismatch'}}

        if($op -eq 'restore'){
            if(-not [bool]$semantic.restored){throw 'ConsumerLifecycle restore semantic evidence missing'}
            if([int]$semantic.matching_process_count -ne 0){throw 'ConsumerLifecycle restore did not prove governed process absence'}
            $baselineSha=([string]$semantic.baseline_sha256).Trim().ToLowerInvariant()
            if($baselineSha -notmatch '^[0-9a-f]{64}$'){throw 'ConsumerLifecycle restore baseline SHA-256 missing/invalid'}
        }
        if($op -like 'bind-*'){
            if([string]$semantic.ledger_prefix -ne "pvam:uat:work02:${ExpectedExecutionId}:"){throw 'ConsumerLifecycle ledger prefix mismatch'}
            if([int]$semantic.matching_process_count -lt 1){throw 'ConsumerLifecycle did not prove a running consumer PID'}
            if(-not ([string]$semantic.pod).Trim() -or -not ([string]$semantic.pod_uid).Trim() -or -not ([string]$semantic.container).Trim()){throw 'ConsumerLifecycle scheduler Pod identity evidence missing'}
            if(([string]$semantic.candidate_sha).ToLowerInvariant() -ne $ExpectedCandidateSha){throw 'ConsumerLifecycle runtime candidate SHA mismatch'}
            foreach($podHead in @($semantic.pod_repo_heads)){if(([string]$podHead.head).ToLowerInvariant() -ne $ExpectedCandidateSha){throw 'ConsumerLifecycle Pod/NFS candidate SHA mismatch'}}
        }
    }
    elseif($action -eq 'ConsumerObserve'){
        if(-not $semantic -or [string]$semantic.kind -ne 'ConsumerObserveResult'){throw "ConsumerObserveResult semantic evidence missing in $($file.Name)"}
        if([string]$semantic.runtime_mode -ne 'scheduler-pod-temporary-process'){throw "ConsumerObserve runtime mode mismatch in $($file.Name)"}
        $scenario=([string]$semantic.scenario).Trim();if(-not $scenario){throw 'ConsumerObserve scenario missing'};$observedScenarios[$scenario]=$semantic;$observeOrder[$scenario]=$successOrdinal
        if([int]$semantic.log_line_count -lt 1){throw 'required consumer observation missing consumer logs'}
        if(([string]$semantic.candidate_sha).ToLowerInvariant() -ne $ExpectedCandidateSha){throw 'ConsumerObserve runtime candidate SHA mismatch'}
        if(-not [bool]$semantic.offset_semantics_ok){throw "ConsumerObserve consumer-group offset semantics failed for $scenario"}
        if(-not [bool]$semantic.business_value_proof_ok){throw "ConsumerObserve controller business value proof failed for $scenario"}
        if(-not $semantic.business_snapshot_before -or -not $semantic.business_snapshot_after){throw "ConsumerObserve business snapshots missing for $scenario"}
        $reasonProp=@($policy.scenario_expected_exception_reason.PSObject.Properties|Where-Object{$_.Name -eq $scenario}|Select-Object -First 1)[0]
        if($reasonProp){$expectedReason=[string]$reasonProp.Value;if([string]$semantic.expected_exception_reason -ne $expectedReason -or @($semantic.exceptions|Where-Object{[string]$_.reason -eq $expectedReason}).Count -lt 1){throw "ConsumerObserve expected exception reason missing for ${scenario}: $expectedReason"}}
        $positive=(@($policy.scenarios_require_dispatched_three_chain|ForEach-Object{[string]$_}) -contains $scenario) -or $scenario -eq 'future-period-replay'
        if($positive){foreach($row in @($semantic.observations)){if([string]$row.delivery_status -ne 'DISPATCHED'){throw "delivery ledger is not DISPATCHED for $($row.identity)"};foreach($ns in @($policy.required_idempotency_namespaces|ForEach-Object{[string]$_})){if(-not [bool]$row.idempotency_namespaces.$ns){throw "required consumer observation missing $ns idempotency evidence for $($row.identity)"}};$dispatchedIdentities[[string]$row.identity]=[int]$row.period}}
        if(@($policy.scenarios_require_no_redis_side_effects|ForEach-Object{[string]$_}) -contains $scenario){if(-not [bool]$semantic.no_redis_side_effects_ok){throw "negative scenario Redis side-effect proof failed: $scenario"}}
        if($scenario -eq 'future-period' -and -not [bool]$semantic.pause_barrier_ok){throw 'future-period same-partition pause barrier proof failed'}
        if($scenario -eq 'future-period-replay' -and -not [bool]$semantic.future_replay_ok){throw 'future-period post-rebind replay proof failed'}
        if($scenario -eq 'cross-period-refund'){if(-not [bool]$semantic.cross_period_refund_ok -or -not [bool]$semantic.primary_refund_idempotency_absent -or [long]$semantic.refund_original_amount_units -ne [long]$semantic.primary_order_amount_units -or [long]$semantic.primary_business_delta_units -ne [long]$semantic.primary_order_amount_units -or [long]$semantic.secondary_business_delta_units -ne -[long]$semantic.refund_original_amount_units){throw 'cross-period refund amount/routing/business-delta proof failed'}}
        if($scenario -eq 'duplicate'){$dupRows=@($semantic.observations);if($dupRows.Count -lt 1){throw 'duplicate observation rows missing'};$dupExpected=[long]$dupRows[0].expected_amount_units;if(-not [bool]$semantic.duplicate_no_double_ok -or [int]$semantic.duplicate_delivery_count -ne 2 -or [long]$semantic.duplicate_business_delta_units -ne $dupExpected){throw 'duplicate no-double business-delta proof failed'}}
        if($scenario -eq 'drain-sentinel' -and -not [bool]$semantic.drain_detected){throw 'required consumer observation missing PERIOD DRAIN COMPLETE evidence'}
    }
    elseif($action -eq 'RedisDbSize'){
        if(-not $semantic -or [string]$semantic.kind -ne 'RedisDbSizeResult'){throw "RedisDbSizeResult semantic evidence missing in $($file.Name)"}
        $phase=([string]$semantic.phase).ToLowerInvariant();if($phase -notin @('before','after')){throw 'RedisDbSize semantic phase invalid'};$size=[long]$semantic.dbsize;if($size -lt 0){throw 'RedisDbSize semantic size invalid'};$dbsize[$phase]=$size
    }
    elseif($action -eq 'KafkaScenarioProduce'){
        if(-not $semantic -or [string]$semantic.kind -ne 'KafkaScenarioResult'){throw "KafkaScenarioResult semantic evidence missing in $($file.Name)"}
        $scenario=([string]$semantic.scenario).Trim();if($scenario){$successfulScenarios[$scenario]=$true};if([int]$semantic.delivery_count -lt 1){throw 'KafkaScenario semantic delivery_count invalid'}
        foreach($d in @($semantic.deliveries)){
            if([string]$d.topic -notin @($policy.kafka_topics)){throw 'KafkaScenario semantic topic invalid'};if([int]$d.partition -lt 0 -or [long]$d.offset -lt 0){throw 'KafkaScenario semantic partition/offset invalid'}
            $identity=([string]$d.key).Trim();$original='';if($d.payload){$original=([string]$d.payload.original_order_id).Trim()}
            $deliveredRecords.Add([pscustomobject]@{identity=$identity;topic=[string]$d.topic;period=[int]$d.period;original_order_id=$original})
        }
        foreach($k in @($semantic.delivered_keys)){$v=([string]$k).Trim();if($v -and -not $delivered.Contains($v)){$delivered.Add($v)}}
    }
    elseif($action -eq 'RedisDeleteExactKeys'){
        if(-not $semantic -or [string]$semantic.kind -ne 'RedisDeleteResult'){throw "RedisDeleteResult semantic evidence missing in $($file.Name)"}
        $requested=[int]$semantic.requested_count;$deleted=[int]$semantic.deleted_count;$remaining=[int]$semantic.remaining_count;if($requested -lt 1 -or $deleted -lt 0 -or $deleted -gt $requested -or $remaining -ne 0){throw 'RedisDelete semantic counts/remaining invalid'}
        $totalDeleted += $deleted
        foreach($k in @($semantic.requested_keys)){$v=([string]$k).Trim();if($v -and -not $cleanupKeys.Contains($v)){$cleanupKeys.Add($v)}}
    }
    elseif($action -eq 'RedisReadExactKeys'){
        if(-not $semantic -or [string]$semantic.kind -ne 'RedisReadResult'){throw "RedisReadResult semantic evidence missing in $($file.Name)"}
        if(-not $semantic.keys){throw 'RedisRead semantic keys missing'}
        $proofId=([string]$semantic.proof_id).Trim()
        if($proofId){
            if(-not [bool]$semantic.expectations_satisfied){throw "RedisRead exact key/value expectations failed for proof_id=$proofId"}
            if([string]$semantic.requested_keys_sha256 -notmatch '^[0-9a-f]{64}$' -or [string]$semantic.values_sha256 -notmatch '^[0-9a-f]{64}$'){throw "RedisRead proof hashes invalid for proof_id=$proofId"}
            $contract=@($policy.redis_proof_contracts.PSObject.Properties|Where-Object{$_.Name -eq $proofId}|Select-Object -First 1)[0];if(-not $contract){throw "RedisRead proof_id outside policy: $proofId"}
            if([string]$semantic.scenario -ne [string]$contract.Value.scenario){throw "RedisRead proof scenario mismatch for proof_id=$proofId"}
            $redisProofs[$proofId]=$semantic
        }
    }
    elseif($action -eq 'UatProof'){
        if(-not $semantic -or [string]$semantic.kind -ne 'UatProofResult'){throw "UatProofResult semantic evidence missing in $($file.Name)"}
        $proofId=([string]$semantic.proof_id).Trim();if(-not $proofId -or -not [bool]$semantic.passed){throw 'UatProof semantic proof_id/passed invalid'}
        $allowed=@($policy.mandatory_uat_proofs_by_stage.$Stage|ForEach-Object{[string]$_});if($allowed -notcontains $proofId){throw "UatProof proof_id outside required policy for ${Stage}: $proofId"}
        if($proofId -eq 'dispatch-p99'){if([int]$semantic.sample_count -lt [int]$policy.dispatch_p99_sample_count -or [double]$semantic.p99_ms -gt [double]$policy.dispatch_p99_max_ms -or -not [string]$semantic.p99_nonce -or @($semantic.sample_completed_at).Count -lt [int]$policy.dispatch_p99_sample_count){throw 'dispatch p99 proof threshold/sample/freshness failed'};if(([string]$semantic.candidate_sha).ToLowerInvariant() -ne $ExpectedCandidateSha){throw 'dispatch p99 runtime Candidate SHA mismatch'}}
        if($proofId -eq 'pending-dispatched-recovery'){if([string]$semantic.runtime_mode -ne 'scheduler-pod-temporary-process'){throw 'pending recovery Consumer runtime mode mismatch'};if(-not [bool]$semantic.pending_before_restart -or -not [bool]$semantic.crash_window_injected -or -not [bool]$semantic.idempotency_present_before_restart -or -not [bool]$semantic.restart_completed -or -not [bool]$semantic.dispatched_after_restart -or -not [bool]$semantic.three_chain_after_restart -or -not [bool]$semantic.business_unchanged_after_replay){throw 'PENDING -> DISPATCHED crash-window process-restart/no-double recovery proof invalid'};if(([string]$semantic.candidate_sha).ToLowerInvariant() -ne $ExpectedCandidateSha){throw 'pending recovery runtime Candidate SHA mismatch'}}
        if($proofId -eq 'cross-period-refund-routing'){if(-not [bool]$semantic.business_value_proof_ok -or [long]$semantic.secondary_business_delta_units -ne [long]$semantic.refund_delta_units -or [long]$semantic.primary_business_delta_units -ne [long]$semantic.primary_order_amount_units){throw 'cross-period UatProof business delta invalid'}}
        if($proofId -eq 'duplicate-no-double'){if(-not [bool]$semantic.business_value_proof_ok -or [long]$semantic.duplicate_business_delta_units -ne [long]$semantic.expected_amount_units){throw 'duplicate UatProof business delta invalid'}}
        if($proofId -eq 'int64-end-to-end'){if(-not [bool]$semantic.runtime_integer_amount_proved -or -not [bool]$semantic.runtime_business_amount_version_proved){throw 'int64 end-to-end runtime proof invalid'}}
        $uatProofs[$proofId]=$semantic;$uatProofOrder[$proofId]=$successOrdinal
        foreach($record in @($semantic.delivered_records)){$id=([string]$record.identity).Trim();if($id){if(-not $delivered.Contains($id)){$delivered.Add($id)};$deliveredRecords.Add($record)}}
    }
    elseif($action -eq 'PytestSelected'){
        if(-not $semantic -or [string]$semantic.kind -ne 'PytestSelectedResult'){throw 'PytestSelected semantic kind invalid'}
        foreach($target in @($semantic.targets)){ $v=([string]$target).Trim(); if($v -and -not $successfulSelectedTargets.Contains($v)){ $successfulSelectedTargets.Add($v) } }
    }
}
if($VerificationMode -eq 'RequireComplete'){
    foreach($action in $required_success_actions){if(-not $success.ContainsKey($action)){throw "required proxy action has no SUCCESS evidence for ${Stage}: $action"}}
    if($success.ContainsKey('RedisDeleteExactKeys') -and $totalDeleted -le 0){throw 'Redis cleanup produced no actual deletion'}
    foreach($target in @($policy.pytest_selected_required_targets | ForEach-Object {[string]$_})){if(-not $successfulSelectedTargets.Contains($target)){throw "required selected pytest target has no SUCCESS evidence for ${Stage}: $target"}}
    $redisProofProp=@($policy.required_redis_proofs_by_stage.PSObject.Properties|Where-Object{$_.Name -eq $Stage}|Select-Object -First 1)[0]
    if($redisProofProp){foreach($proofId in @($redisProofProp.Value|ForEach-Object{[string]$_})){if(-not $redisProofs.ContainsKey($proofId)){throw "required exact Redis proof missing for ${Stage}: $proofId"}}}
    $uatProofProp=@($policy.mandatory_uat_proofs_by_stage.PSObject.Properties|Where-Object{$_.Name -eq $Stage}|Select-Object -First 1)[0]
    if($uatProofProp){foreach($proofId in @($uatProofProp.Value|ForEach-Object{[string]$_})){if(-not $uatProofs.ContainsKey($proofId)){throw "mandatory UAT proof missing for ${Stage}: $proofId"}}}
    foreach($phase in @($policy.redis_dbsize_required_phases)){if(-not $dbsize.ContainsKey([string]$phase)){throw "required RedisDbSize phase missing: $phase"}}
    if($dbsize.ContainsKey('before') -and $dbsize.ContainsKey('after') -and [long]$dbsize['after'] -gt [long]$dbsize['before']){throw "RedisDbSize cleanup leak: before=$($dbsize['before']) after=$($dbsize['after'])"}
    if(-not $runtimeGitUpdateOk){throw "runtime candidate SHA mismatch: required GitUpdate semantic evidence missing"}
    $lifeProp=@($policy.required_consumer_lifecycle_ops_by_stage.PSObject.Properties|Where-Object {$_.Name -eq $Stage}|Select-Object -First 1)[0]
    if($lifeProp){
        $requiredLife=@($lifeProp.Value|ForEach-Object{[string]$_})
        [int]$previousLifeOrdinal=0
        foreach($op in $requiredLife){
            if(-not $lifecycleOps.ContainsKey($op)){throw "required ConsumerLifecycle operation missing for ${Stage}: $op"}
            [int]$currentLifeOrdinal=$lifecycleOrder[$op]
            if($previousLifeOrdinal -gt 0 -and $currentLifeOrdinal -le $previousLifeOrdinal){throw "ConsumerLifecycle operation order invalid for ${Stage}: $($requiredLife -join ' -> ')"}
            $previousLifeOrdinal=$currentLifeOrdinal
        }
        if($Stage -eq 'OPUS' -and $lifecycleOrder.ContainsKey('bind-primary') -and $lifecycleOrder.ContainsKey('bind-secondary')){
            foreach($needed in @('future-period','drain-sentinel','future-period-replay')){if(-not $observeOrder.ContainsKey($needed)){throw "period-switch lifecycle sequence invalid: $needed observation missing"}}
            [int]$primaryOrdinal=$lifecycleOrder['bind-primary'];[int]$futureOrdinal=$observeOrder['future-period'];[int]$drainOrdinal=$observeOrder['drain-sentinel'];[int]$secondaryOrdinal=$lifecycleOrder['bind-secondary'];[int]$replayOrdinal=$observeOrder['future-period-replay']
            if(-not ($primaryOrdinal -lt $futureOrdinal -and $futureOrdinal -lt $secondaryOrdinal -and $primaryOrdinal -lt $drainOrdinal -and $drainOrdinal -lt $secondaryOrdinal -and $secondaryOrdinal -lt $replayOrdinal)){throw 'period-switch lifecycle sequence invalid: expected bind-primary -> future-period + drain-sentinel -> bind-secondary -> future-period-replay'}
        }
    }
    $observeProp=@($policy.consumer_observation_required_scenarios_by_stage.PSObject.Properties|Where-Object {$_.Name -eq $Stage}|Select-Object -First 1)[0]
    if($observeProp){foreach($scenario in @($observeProp.Value|ForEach-Object{[string]$_})){if(-not $observedScenarios.ContainsKey($scenario)){throw "required consumer observation missing for ${Stage}: $scenario"}}}
    
    # V20-RESTORE-AFTER-OBSERVATIONS-AND-PROOFS
    if($lifecycleOrder.ContainsKey('restore')){
        [int]$restoreOrdinal=$lifecycleOrder['restore']
        if($observeProp){foreach($requiredObservedScenario in @($observeProp.Value|ForEach-Object{[string]$_})){if($observeOrder.ContainsKey($requiredObservedScenario) -and $restoreOrdinal -le [int]$observeOrder[$requiredObservedScenario]){throw "ConsumerLifecycle restore must occur after required ConsumerObserve scenario: $requiredObservedScenario"}}}
        if($uatProofProp){foreach($proofId in @($uatProofProp.Value|ForEach-Object{[string]$_})){if($uatProofOrder.ContainsKey($proofId) -and $restoreOrdinal -le [int]$uatProofOrder[$proofId]){throw "ConsumerLifecycle restore must occur after mandatory UAT proof: $proofId"}}}
    }
$scenarioProp=@($policy.required_kafka_scenarios_by_stage.PSObject.Properties|Where-Object {$_.Name -eq $Stage}|Select-Object -First 1)[0]
    if($scenarioProp){foreach($scenario in @($scenarioProp.Value|ForEach-Object {[string]$_})){if(-not $successfulScenarios.ContainsKey($scenario)){throw "required Kafka scenario has no SUCCESS evidence for ${Stage}: $scenario"}}}
    foreach($identity in @($delivered.ToArray())){if(-not @($cleanupKeys.ToArray()|Where-Object {Test-KeyCoversIdentity ([string]$_) $identity}).Count){throw "Redis cleanup evidence does not cover exact delivered Kafka identity: $identity"}}
    $seenCleanupRecords=@{}
    foreach($record in @($deliveredRecords.ToArray())){
        $identity=([string]$record.identity).Trim();if(-not $identity){continue};$recordKey=$identity+'|'+[string]$record.topic+'|'+[string]$record.period+'|'+[string]$record.original_order_id;if($seenCleanupRecords.ContainsKey($recordKey)){continue};$seenCleanupRecords[$recordKey]=$true
        foreach($ledgerKey in @(Get-LedgerCleanupKeys $record $ExpectedExecutionId)){if($cleanupKeys -notcontains $ledgerKey){throw "missing ledger cleanup key for identity=$identity expected=$ledgerKey"}}
        $period=[int]$record.period
        foreach($ns in @($policy.required_idempotency_namespaces|ForEach-Object{[string]$_})){
            $expectedKey=Get-IdempotencyDoneKey $ns $period $identity
            if($cleanupKeys -notcontains $expectedKey){throw "missing idempotency cleanup namespace $ns for identity=$identity period=$period expected=$expectedKey"}
        }
    }
}
Write-Output "[PROXY-EVIDENCE] PASS stage=$Stage mode=$VerificationMode files=$($files.Count) successful_actions=$($success.Count) slot=$ExpectedSlot periods=$ExpectedPrimary/$ExpectedSecondary execution=$ExpectedExecutionId"
