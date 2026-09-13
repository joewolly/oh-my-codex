[CmdletBinding()]
param(
    [switch]$Reset,
    [string]$ControlThreadId,
    [string]$ActivatedThreadId,
    [string]$DesktopVersion,
    [string]$RuntimeVersion,
    [string]$ControlResponse,
    [switch]$ConfirmControlPass,
    [string]$ToolingPython,
    [string]$StateRoot
)

$ErrorActionPreference = 'Stop'
$StateSchema = 1
$FreshnessHours = 24

if (-not $StateRoot) {
    if (-not $env:LOCALAPPDATA) {
        throw 'LOCALAPPDATA is unavailable; cannot locate Oh-My-Codex state.'
    }
    $StateRoot = Join-Path $env:LOCALAPPDATA 'Oh-My-Codex'
}
$StatePath = Join-Path $StateRoot 'verify-desktop-state.json'
$ArchiveRoot = Join-Path $StateRoot 'verify-desktop-history'

if (-not $ToolingPython) {
    $ToolingPython = Join-Path $StateRoot 'venv\Scripts\python.exe'
}

function Write-Utf8File([string]$Path, [string]$Content) {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8)
}

function Write-State([object]$State) {
    New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
    $temporary = Join-Path $StateRoot ('.verify-desktop-state.{0}.tmp' -f [guid]::NewGuid().ToString('N'))
    Write-Utf8File $temporary ($State | ConvertTo-Json -Depth 20)
    Move-Item -LiteralPath $temporary -Destination $StatePath -Force
}

function Archive-State([string]$Reason) {
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        return
    }
    New-Item -ItemType Directory -Force -Path $ArchiveRoot | Out-Null
    $stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    try {
        $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    }
    catch {
        Move-Item -LiteralPath $StatePath -Destination (Join-Path $ArchiveRoot ("$stamp-invalid-state.json"))
        return
    }
    $state | Add-Member -NotePropertyName terminal_reason -NotePropertyValue $Reason -Force
    $state | Add-Member -NotePropertyName archived_at -NotePropertyValue ([DateTimeOffset]::UtcNow.ToString('o')) -Force
    $run = if ($state.run_id) { [string]$state.run_id } else { 'unknown' }
    $archive = Join-Path $ArchiveRoot ("$stamp-$run.json")
    Write-Utf8File $archive ($state | ConvertTo-Json -Depth 20)
    Remove-Item -LiteralPath $StatePath
}

function Invoke-ToolJson([string[]]$Arguments, [switch]$AllowFailure) {
    $output = & $ToolingPython @Arguments 2>&1
    $code = $LASTEXITCODE
    $text = @($output) -join [Environment]::NewLine
    if ($code -ne 0 -and (-not $AllowFailure -or $code -ne 1)) {
        throw "Oh-My-Codex command failed (exit $code): $text"
    }
    try {
        return $text | ConvertFrom-Json
    }
    catch {
        throw "Oh-My-Codex returned invalid JSON: $text"
    }
}

function Copy-Prompt([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Prepared prompt is missing: $Path"
    }
    Get-Content -LiteralPath $Path -Raw | Set-Clipboard
}

function Require-Value([string]$Value, [string]$Prompt) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        $Value = Read-Host $Prompt
    }
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Prompt is required."
    }
    return $Value.Trim()
}

function Read-PendingState {
    try {
        $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    }
    catch {
        Archive-State 'invalid-wrapper-state'
        throw 'Pending verification state is invalid. It was archived; prepare a fresh run.'
    }
    if ($state.schema -ne $StateSchema -or -not $state.run_id -or -not $state.fixture -or -not $state.prepared_at) {
        Archive-State 'invalid-wrapper-state'
        throw 'Pending verification state is incomplete. It was archived; prepare a fresh run.'
    }
    if (-not (Test-Path -LiteralPath $state.fixture -PathType Container)) {
        Archive-State 'fixture-missing'
        throw 'The pending fixture disappeared. State was archived; prepare a fresh run.'
    }
    try {
        $prepared = [DateTimeOffset]::Parse([string]$state.prepared_at)
    }
    catch {
        Archive-State 'invalid-prepared-time'
        throw 'The pending preparation timestamp is invalid. State was archived; prepare a fresh run.'
    }
    if ([DateTimeOffset]::UtcNow -gt $prepared.AddHours($FreshnessHours)) {
        Archive-State 'preparation-expired'
        throw 'The pending acceptance run expired. State was archived; prepare a fresh run.'
    }
    $metadataPath = Join-Path $state.fixture '.omc-desktop.json'
    try {
        $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    }
    catch {
        Archive-State 'fixture-metadata-missing-or-invalid'
        throw 'The pending fixture metadata is missing or invalid. State was archived; prepare a fresh run.'
    }
    $metadataAssets = $metadata.asset_fingerprints | ConvertTo-Json -Compress
    $stateAssets = $state.asset_fingerprints | ConvertTo-Json -Compress
    if ($metadata.run_id -ne $state.run_id -or
        $metadata.fixture_path -ne $state.fixture -or
        $metadata.prepared_at -ne $state.prepared_at -or
        $metadata.package_version -ne $state.package_version -or
        $metadata.baseline_fingerprint -ne $state.baseline_fingerprint -or
        $metadataAssets -ne $stateAssets -or
        $state.control_prompt -ne (Join-Path $state.fixture 'control-prompt.txt') -or
        $state.control_evidence -ne (Join-Path $state.fixture 'control-evidence.json') -or
        $state.desktop_prompt -ne (Join-Path $state.fixture 'desktop-prompt.txt') -or
        $state.desktop_evidence -ne (Join-Path $state.fixture 'desktop-evidence.json')) {
        Archive-State 'fixture-identity-mismatch'
        throw 'The pending run no longer matches its prepared fixture/build. State was archived; prepare a fresh run.'
    }
    return $state
}

if ($Reset) {
    if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
        Archive-State 'operator-reset'
        Write-Host 'Pending wrapper state was archived. Prepared fixture evidence was preserved.'
    }
    else {
        Write-Host 'No pending Desktop acceptance run exists.'
    }
    return
}

if (-not (Test-Path -LiteralPath $ToolingPython -PathType Leaf)) {
    throw "Oh-My-Codex tooling Python is missing: $ToolingPython`nRun .\install.ps1 first."
}

if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
    $prepared = Invoke-ToolJson -Arguments @('-m', 'oh_my_codex', 'verify-desktop', '--prepare', '--json')
    if ($prepared.overall -ne 'PASS' -or $prepared.status -ne 'prepared') {
        throw 'Desktop fixture preparation did not return overall=PASS and status=prepared.'
    }
    $metadata = Get-Content -LiteralPath (Join-Path $prepared.fixture '.omc-desktop.json') -Raw | ConvertFrom-Json
    $state = [ordered]@{
        schema = $StateSchema
        stage = 'awaiting-control'
        run_id = [string]$prepared.run_id
        fixture = [string]$prepared.fixture
        prepared_at = [string]$prepared.prepared_at
        package_version = [string]$metadata.package_version
        baseline_fingerprint = [string]$prepared.baseline_fingerprint
        asset_fingerprints = $metadata.asset_fingerprints
        control_prompt = [string]$prepared.control_prompt
        control_evidence = [string]$prepared.control_evidence
        desktop_prompt = [string]$prepared.prompt
        desktop_evidence = [string]$prepared.evidence
    }
    Write-State $state
    Copy-Prompt $state.control_prompt
    Write-Host 'STEP 1 - CONTROL THREAD'
    Write-Host '- Fully quit/relaunch Codex Desktop if required.'
    Write-Host '- Start a NEW thread.'
    Write-Host '- Do NOT activate $oh-my-codex.'
    Write-Host '- Paste the control prompt now on your clipboard.'
    Write-Host "Run: $($state.run_id)"
    Write-Host 'When the control thread is complete, run .\verify-desktop.ps1 again.'
    return
}

$state = Read-PendingState
if ($state.stage -eq 'awaiting-control') {
    # No activated work is authorized yet, so the canonical preflight must still
    # validate the untouched fixture and current installed managed assets.
    try {
        $check = Invoke-ToolJson -Arguments @('-m', 'oh_my_codex', 'verify-desktop', '--check-probes', [string]$state.fixture, '--json')
    }
    catch {
        Archive-State 'pre-activation-preflight-failed'
        throw "This acceptance run cannot be reused. Fix/update Oh-My-Codex, reinstall, and prepare a new run.`n$($_.Exception.Message)"
    }
    if ($check.overall -ne 'PASS') {
        Archive-State 'pre-activation-preflight-failed'
        throw 'This acceptance run cannot be reused. Fix/update Oh-My-Codex, reinstall, and prepare a new run.'
    }

    $ControlThreadId = Require-Value $ControlThreadId 'Control thread ID'
    $DesktopVersion = Require-Value $DesktopVersion 'Codex Desktop version'
    $RuntimeVersion = Require-Value $RuntimeVersion 'Bundled Codex runtime version'
    $ControlResponse = Require-Value $ControlResponse 'Brief control response or transcript reference'
    if (-not $ConfirmControlPass) {
        $confirmation = Read-Host 'Confirm the control stayed ordinary, did not activate Oh-My-Codex, and made no source changes (type YES)'
        if ($confirmation -cne 'YES') {
            throw 'Control attestation was not confirmed. The pending run was preserved.'
        }
    }

    $control = Get-Content -LiteralPath $state.control_evidence -Raw | ConvertFrom-Json
    $hostPlatform = (& $ToolingPython -c 'import platform; print(platform.platform())') -join ''
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($hostPlatform)) {
        throw 'Could not determine the Windows platform identity with the tooling Python.'
    }
    $control.surface = 'CODEX_DESKTOP'
    $control.thread_id = $ControlThreadId
    $control.observed_at = [DateTimeOffset]::UtcNow.ToString('o')
    $control.os = $hostPlatform.Trim()
    $control.desktop_version = $DesktopVersion
    $control.runtime_version = $RuntimeVersion
    $control.new_thread_started = $true
    $control.skill_invoked = $false
    $control.activation_marker_observed = $false
    $control.policy_loaded = $false
    $control.instructed_omc_orchestrator = $false
    $control.omc_workflow_forced = $false
    $control.source_modifications_observed = $false
    $control.transcript_reviewed = $true
    $control.observation_basis = 'DESKTOP_OPERATOR_REVIEW'
    $control.evidence_reference = 'Windows operator attestation via verify-desktop.ps1'
    $control.response = $ControlResponse
    $control.activation_control_result = 'PASS'
    Write-Utf8File $state.control_evidence ($control | ConvertTo-Json -Depth 20)

    $state.stage = 'awaiting-activated'
    $state.control_thread_id = $ControlThreadId
    $state.desktop_version = $DesktopVersion
    $state.runtime_version = $RuntimeVersion
    Write-State $state
    Copy-Prompt $state.desktop_prompt
    Write-Host 'STEP 2 - ACTIVATED THREAD'
    Write-Host '- Preserve the control thread ID.'
    Write-Host '- Start a DIFFERENT NEW thread.'
    Write-Host '- Select Astra/high or Sol/high.'
    Write-Host '- Explicitly invoke $oh-my-codex.'
    Write-Host '- Paste the activated acceptance prompt now on your clipboard.'
    Write-Host "Run: $($state.run_id)"
    Write-Host 'When the activated thread is complete, run .\verify-desktop.ps1 again.'
    return
}

if ($state.stage -ne 'awaiting-activated') {
    Archive-State 'invalid-wrapper-stage'
    throw 'Pending verification state has an unknown stage. It was archived; prepare a fresh run.'
}

$evidence = Get-Content -LiteralPath $state.desktop_evidence -Raw | ConvertFrom-Json
if ($evidence.run_id -notin @('UNVERIFIED', $state.run_id)) {
    Archive-State 'desktop-evidence-run-mismatch'
    throw 'Desktop evidence belongs to a different run. State was archived; prepare a fresh run.'
}
if ($evidence.probe_preflight -eq 'FAILED') {
    Archive-State 'canonical-preflight-failed'
    throw 'This acceptance run cannot be reused. Fix/update Oh-My-Codex, reinstall, and prepare a new run.'
}
if ($evidence.run_id -ne $state.run_id -or $evidence.workflow_completed -notin @($true, 'VERIFIED')) {
    Write-Host 'The activated evidence is not complete yet. Finish the activated thread; do not repair, retry, or replace a failed canonical preflight.'
    Write-Host "Run: $($state.run_id)"
    return
}

$ActivatedThreadId = Require-Value $ActivatedThreadId 'Activated thread ID'
if ($ActivatedThreadId -eq $state.control_thread_id) {
    throw 'Control and activated thread IDs must be different. The pending run was preserved.'
}
$result = Invoke-ToolJson -AllowFailure -Arguments @(
    '-m', 'oh_my_codex', 'verify-desktop',
    '--evaluate', [string]$state.desktop_evidence,
    '--desktop-version', [string]$state.desktop_version,
    '--runtime-version', [string]$state.runtime_version,
    '--thread-id', $ActivatedThreadId,
    '--control-thread-id', [string]$state.control_thread_id,
    '--json'
)

Write-Host "CODEX DESKTOP VERIFICATION: $($result.overall)"
Write-Host "Core orchestration: $($result.core_orchestration)"
Write-Host "Explicit activation control: $($result.explicit_activation_control)"
Write-Host "Probe boundary compliance: $($result.probe_boundary_compliance)"
Write-Host "Strict sandbox isolation: $($result.strict_sandbox_isolation)"
foreach ($warning in @($result.warnings)) {
    Write-Warning $warning
}

if ([string]$result.overall -like 'PASS*') {
    Archive-State 'evaluation-passed'
    Write-Host 'Wrapper state was archived; the forensic fixture was preserved.'
}
else {
    Archive-State 'evaluation-failed'
    Write-Host 'Acceptance failed. Wrapper state was archived; the forensic fixture was preserved.'
}
