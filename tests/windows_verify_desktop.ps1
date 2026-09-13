$ErrorActionPreference = 'Stop'

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) {
        throw "ASSERTION FAILED: $Message"
    }
}

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$TestRoot = Join-Path $env:RUNNER_TEMP ("omc windows wrapper {0}" -f [guid]::NewGuid().ToString('N'))
$env:LOCALAPPDATA = Join-Path $TestRoot 'local app data'
Remove-Item Env:PIP_NO_CACHE_DIR -ErrorAction SilentlyContinue

$script:ClipboardText = ''
function global:Set-Clipboard {
    [CmdletBinding()]
    param([Parameter(ValueFromPipeline = $true)][string]$Value)
    process { $script:ClipboardText = $Value }
}

try {
    New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA | Out-Null
    $PowerShellExe = (Get-Process -Id $PID).Path
    & $PowerShellExe -NoProfile -NonInteractive -File (Join-Path $RepoRoot 'install.ps1')
    Assert-True ($LASTEXITCODE -eq 0) 'install.ps1 must succeed without PIP_NO_CACHE_DIR'

    $Wrapper = Join-Path $RepoRoot 'verify-desktop.ps1'
    $first = & $Wrapper
    $StatePath = Join-Path $env:LOCALAPPDATA 'Oh-My-Codex\verify-desktop-state.json'
    Assert-True (Test-Path -LiteralPath $StatePath -PathType Leaf) 'preparation must create pending state'
    $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    Assert-True ($state.stage -eq 'awaiting-control') 'first run must await the control thread'
    Assert-True ($script:ClipboardText -eq (Get-Content -LiteralPath $state.control_prompt -Raw)) 'first run must copy the exact control prompt'
    Assert-True (($first -join "`n") -match 'STEP 1 - CONTROL THREAD') 'first run must print concise control guidance'

    $canonical = @(Get-Content -LiteralPath $state.desktop_prompt | Where-Object {
        $_ -match "^& '.+' '-I' '-S' '-c' "
    })
    Assert-True ($canonical.Count -eq 1) 'prepared prompt must retain exactly one canonical PowerShell command'
    & $PowerShellExe -NoProfile -NonInteractive -Command $canonical[0]
    Assert-True ($LASTEXITCODE -eq 0) 'exact retained command must execute through PowerShell unchanged'
    Assert-True ($canonical[0] -match [regex]::Escape($env:LOCALAPPDATA)) 'retained executable path must exercise spaces'

    $script:ClipboardText = ''
    $second = & $Wrapper `
        -ControlThreadId 'control-thread-windows' `
        -DesktopVersion 'desktop-test-version' `
        -RuntimeVersion 'runtime-test-version' `
        -ControlResponse '42. No mandatory role workflow.' `
        -ConfirmControlPass
    $state2 = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    Assert-True ($state2.run_id -eq $state.run_id) 'second stage must not replace or mix the prepared run'
    Assert-True ($state2.fixture -eq $state.fixture) 'second stage must retain the exact fixture'
    Assert-True ($state2.stage -eq 'awaiting-activated') 'second run must advance to activated thread'
    Assert-True ($script:ClipboardText -eq (Get-Content -LiteralPath $state2.desktop_prompt -Raw)) 'second run must copy the exact activated prompt'
    Assert-True (($second -join "`n") -match 'STEP 2 - ACTIVATED THREAD') 'second run must print concise activated guidance'

    $third = & $Wrapper
    Assert-True (($third -join "`n") -match 'activated evidence is not complete') 'incomplete evidence must not be evaluated or replaced'
    $state3 = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    Assert-True ($state3.run_id -eq $state.run_id) 'incomplete rerun must preserve the pending run'

    $fixture = [string]$state3.fixture
    & $Wrapper -Reset
    Assert-True (-not (Test-Path -LiteralPath $StatePath)) 'reset must remove only active wrapper state'
    Assert-True (Test-Path -LiteralPath $fixture -PathType Container) 'reset must preserve forensic fixture evidence'
    $history = Join-Path $env:LOCALAPPDATA 'Oh-My-Codex\verify-desktop-history'
    Assert-True (@(Get-ChildItem -LiteralPath $history -Filter '*.json').Count -eq 1) 'reset must archive one wrapper state record'
}
finally {
    Remove-Item Function:\Set-Clipboard -ErrorAction SilentlyContinue
}
