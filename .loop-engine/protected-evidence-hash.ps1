$ErrorActionPreference = "Stop"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if (-not $env:MAINREPO) { throw "MAINREPO is required" }
if (-not $env:OUTDIR) { throw "OUTDIR is required" }
if (-not $env:WORKTREE) { throw "WORKTREE is required" }

$MainRepo = $env:MAINREPO
$OutDir = $env:OUTDIR
$Worktree = $env:WORKTREE
$records = New-Object System.Collections.Generic.List[string]

function Add-FileRecord([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        $records.Add("MISSING|$Label")
        return
    }
    $item = Get-Item -LiteralPath $Path -Force
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    $records.Add("FILE|$Label|$($item.Length)|$hash")
}

function Add-TreeRecords([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        $records.Add("MISSING_DIR|$Label")
        return
    }
    $records.Add("DIR|$Label")
    $root = (Get-Item -LiteralPath $Path -Force).FullName.TrimEnd([char]92)
    $files = @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force | Sort-Object FullName)
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($root.Length).TrimStart([char]92).Replace([char]92, [char]47)
        Add-FileRecord $file.FullName ($Label.TrimEnd([char]47) + '/' + $relative)
    }
}


function Add-StableCycleContractRecords() {
    $cycleNumber = 0
    $roundNumber = 0
    if (-not [int]::TryParse(([string]$env:LOOP_CYCLE).Trim(), [ref]$cycleNumber) -or $cycleNumber -lt 1) {
        throw "LOOP_CYCLE is required for protected evidence digest"
    }
    if (-not [int]::TryParse(([string]$env:LOOP_ROUND).Trim(), [ref]$roundNumber) -or $roundNumber -lt 1) {
        throw "LOOP_ROUND is required for protected evidence digest"
    }

    $cycleRoot = Join-Path $OutDir ("cycles\cycle-{0}" -f $cycleNumber)
    Add-FileRecord (Join-Path $cycleRoot "cycle-uat-authorization.json") ("out/cycles/cycle-{0}/cycle-uat-authorization.json" -f $cycleNumber)
    $roundContext = Join-Path $cycleRoot ("round-{0}\context" -f $roundNumber)
    Add-TreeRecords $roundContext ("out/cycles/cycle-{0}/round-{1}/context" -f $cycleNumber, $roundNumber)

    # Archive-Round legitimately rewrites round-summary/report/verifier-state for a
    # BLOCKED attempt before the same logical Round is resumed. Those archival files
    # therefore cannot participate in a same-Round immutable before/after digest.
    # The stable context above plus protected_round_contract_sha256 and the live
    # controller invariants bind the authorization/AGENTS/candidate semantics.
    $records.Add(("MUTABLE_ARCHIVE_EXCLUDED|out/cycles/cycle-{0}/round-{1}/archive" -f $cycleNumber, $roundNumber))
}

function Add-OpusStableEvidenceRecords() {
    $opusRoot = Join-Path $OutDir "verifier-state\opus"
    # These checkpoint/session files are controller-owned volatile resume metadata.
    # prepare-verifier-state.ps1 legitimately rewrites them on every GitHub run,
    # including a Fable resume. They are intentionally excluded from the immutable
    # final-audit digest; the durable Round contract separately binds candidate,
    # periods, authorization and governance state.
    $volatileCheckpointFiles = @("verifier-progress.json", "resume-context.md", "claude-session.txt")
    foreach ($name in $volatileCheckpointFiles) { $records.Add("VOLATILE_EXCLUDED|out/verifier-state/opus/$name") }

    # Immutable Opus evidence that Fable receives as its audit basis.
    Add-FileRecord (Join-Path $opusRoot "UAT_REPORT.pre-fable.md") "out/verifier-state/opus/UAT_REPORT.pre-fable.md"
    Add-FileRecord (Join-Path $opusRoot "loop-state.pre-fable.json") "out/verifier-state/opus/loop-state.pre-fable.json"
    Add-TreeRecords (Join-Path $opusRoot "evidence") "out/verifier-state/opus/evidence"
    Add-TreeRecords (Join-Path $opusRoot "logs") "out/verifier-state/opus/logs"
    $controllerOpus = Join-Path $OutDir ("controller-evidence\schema-10\cycle-{0}\round-{1}\opus" -f [int]$env:LOOP_CYCLE, [int]$env:LOOP_ROUND)
    Add-TreeRecords $controllerOpus ("out/controller-evidence/schema-10/cycle-{0}/round-{1}/opus" -f [int]$env:LOOP_CYCLE, [int]$env:LOOP_ROUND)
}

# Durable Loop Engine evidence that Fable is not permitted to change.
# The live loop-state.json carries the durable baseline field itself and is not hashed
# directly to avoid a self-referential digest. The Opus tree contains the immutable
# loop-state.pre-fable.json snapshot and is hashed below.
Add-StableCycleContractRecords
Add-OpusStableEvidenceRecords
Add-FileRecord (Join-Path $OutDir "pushed-sha.txt") "out/pushed-sha.txt"
Add-FileRecord (Join-Path $OutDir "codex-final.txt") "out/codex-final.txt"
Add-FileRecord (Join-Path $OutDir "IMPLEMENTATION_HANDOFF.md") "out/IMPLEMENTATION_HANDOFF.md"
Add-FileRecord (Join-Path $OutDir "opus-result.txt") "out/opus-result.txt"

# Governing controller and instruction surface. UAT_REPORT.md, uat-result.txt and
# verifier-state/fable are intentionally excluded because Fable must write them.
foreach ($relative in @(
    ".github\workflows\loop-engine.yml",
    ".github\workflows\loop-round.yml",
    ".loop-engine\loop-state.ps1",
    ".loop-engine\prepare-verifier-state.ps1",
    ".loop-engine\claude-verifier-runner.ps1",
    ".loop-engine\agent-skill-contract.ps1",
    ".loop-engine\finalize-pvam-v2-uat.ps1",
    ".loop-engine\automated-override.md",
    ".loop-engine\verifier-checkpoint-protocol.md",
    ".loop-engine\uat-period-pool.json",
    ".loop-engine\uat-action-proxy.ps1",
    ".loop-engine\uat-action-policy.json",
    ".loop-engine\consumer-runtime-controller-r9.py",
    ".loop-engine\protected-evidence-hash.ps1",
    ".loop-engine\verify-proxy-period-evidence.ps1",
    "K8S\kubectl.exe",
    "K8S\admin.conf"
)) {
    Add-FileRecord (Join-Path $MainRepo $relative) ("repo/" + $relative.Replace([char]92, [char]47))
}

# Candidate integrity: the final auditor receives a committed candidate. Any
# source mutation makes git status dirty and blocks the post-audit gate.
Push-Location $Worktree
try {
    $head = (git rev-parse HEAD).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') { throw "unable to resolve candidate HEAD for protected evidence digest" }
    # git status --porcelain is intentionally part of the protected-surface gate.
    $status = @(git status --porcelain=v1 --untracked-files=all)
    if ($LASTEXITCODE -ne 0) { throw "git status failed for protected evidence digest" }
    if ($status.Count -gt 0) { throw "candidate worktree is dirty during protected evidence digest: $($status -join '; ')" }
    $records.Add("CANDIDATE_HEAD|$head")
    $records.Add("CANDIDATE_STATUS|CLEAN")
}
finally {
    Pop-Location
}

$material = ($records.ToArray() -join "`n") + "`n"
$bytes = $Utf8NoBom.GetBytes($material)
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $digest = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
}
finally {
    $sha.Dispose()
}
if ($digest -notmatch '^[0-9a-f]{64}$') { throw "protected evidence digest generation failed" }
Write-Output $digest
