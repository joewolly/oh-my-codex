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

$global:OmcWindowsCiClipboardText = ''
function global:Set-Clipboard {
    [CmdletBinding()]
    param([string]$Value)
    $global:OmcWindowsCiClipboardText = $Value
}

try {
    New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA | Out-Null
    $PowerShellExe = (Get-Process -Id $PID).Path
    & $PowerShellExe -NoProfile -NonInteractive -File (Join-Path $RepoRoot 'install.ps1')
    Assert-True ($LASTEXITCODE -eq 0) 'install.ps1 must succeed without PIP_NO_CACHE_DIR'
    $ToolingPython = Join-Path $env:LOCALAPPDATA 'Oh-My-Codex\venv\Scripts\python.exe'
    $ToolingVersion = & $ToolingPython -c 'import sys; print(sys.version_info.major, sys.version_info.minor, sep=chr(46))'
    Assert-True ($ToolingVersion -eq $env:OMC_EXPECTED_PYTHON) 'bootstrap must use the setup-python interpreter selected by CI'

    $Wrapper = Join-Path $RepoRoot 'verify-desktop.ps1'
    $first = & $Wrapper *>&1
    $StatePath = Join-Path $env:LOCALAPPDATA 'Oh-My-Codex\verify-desktop-state.json'
    Assert-True (Test-Path -LiteralPath $StatePath -PathType Leaf) 'preparation must create pending state'
    $state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    Assert-True ($state.stage -eq 'awaiting-control') 'first run must await the control thread'
    Assert-True ($global:OmcWindowsCiClipboardText -eq (Get-Content -LiteralPath $state.control_prompt -Raw)) 'first run must copy the exact control prompt'
    Assert-True (($first -join "`n") -match 'STEP 1 - CONTROL THREAD') 'first run must print concise control guidance'

    $canonical = @(Get-Content -LiteralPath $state.desktop_prompt | Where-Object {
        $_ -match "^& '.+' '-I' '-S' '-c' "
    })
    Assert-True ($canonical.Count -eq 1) 'prepared prompt must retain exactly one canonical PowerShell command'
    $ExpectedHelper = Join-Path $state.fixture '.omc-probe-preflight.py'
    $ExpectedHelperForward = $ExpectedHelper.Replace('\', '/')
    $ExpectedPythonForward = $ToolingPython.Replace('\', '/')
    Assert-True ($canonical[0] -match [regex]::Escape("& '$ExpectedPythonForward'")) 'retained executable must use a forward-slash Windows path'
    Assert-True ($canonical[0] -match [regex]::Escape("'$ExpectedHelperForward'")) 'retained helper must use the expected fixture-child path with forward slashes'
    Assert-True ([System.IO.Path]::GetFullPath($ExpectedHelperForward) -eq [System.IO.Path]::GetFullPath($ExpectedHelper)) 'forward-slash helper spelling must resolve to the expected fixture child'
    Assert-True ($canonical[0] -notmatch '\\\.omc-probe-preflight\.py') 'retained helper must not contain the vulnerable backslash-dot boundary'
    Assert-True ($canonical[0] -match '/\.omc-probe-preflight\.py') 'retained helper must contain the Desktop-safe slash-dot boundary'
    $MarkdownNormalized = $canonical[0] -replace '\\(?=[.])', ''
    Assert-True ($MarkdownNormalized -ceq $canonical[0]) 'Markdown backslash-before-punctuation normalization must leave the retained command unchanged'
    $CanonicalScript = Join-Path $TestRoot 'retained-preflight.ps1'
    [System.IO.File]::WriteAllText(
        $CanonicalScript,
        $canonical[0] + [Environment]::NewLine + 'exit $LASTEXITCODE' + [Environment]::NewLine,
        [System.Text.Encoding]::Unicode
    )
    & $PowerShellExe -NoProfile -NonInteractive -File $CanonicalScript
    Assert-True ($LASTEXITCODE -eq 0) 'exact retained command must execute through PowerShell unchanged'
    Assert-True ($canonical[0] -match [regex]::Escape($env:LOCALAPPDATA)) 'retained executable path must exercise spaces'

    $global:OmcWindowsCiClipboardText = ''
    $second = & $Wrapper `
        -ControlThreadId 'control-thread-windows' `
        -DesktopVersion 'desktop-test-version' `
        -RuntimeVersion 'runtime-test-version' `
        -ControlResponse '42. No mandatory role workflow.' `
        -ConfirmControlPass *>&1
    $state2 = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    Assert-True ($state2.run_id -eq $state.run_id) 'second stage must not replace or mix the prepared run'
    Assert-True ($state2.fixture -eq $state.fixture) 'second stage must retain the exact fixture'
    Assert-True ($state2.stage -eq 'awaiting-activated') 'second run must advance to activated thread'
    Assert-True ($global:OmcWindowsCiClipboardText -eq (Get-Content -LiteralPath $state2.desktop_prompt -Raw)) 'second run must copy the exact activated prompt'
    Assert-True (($second -join "`n") -match 'STEP 2 - ACTIVATED THREAD') 'second run must print concise activated guidance'

    $third = & $Wrapper *>&1
    Assert-True (($third -join "`n") -match 'activated evidence is not complete') 'incomplete evidence must not be evaluated or replaced'
    $state3 = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    Assert-True ($state3.run_id -eq $state.run_id) 'incomplete rerun must preserve the pending run'

    $fixture = [string]$state3.fixture
    $evidence = Get-Content -LiteralPath $state3.desktop_evidence -Raw | ConvertFrom-Json
    $evidence.probe_preflight = 'FAILED'
    [System.IO.File]::WriteAllText($state3.desktop_evidence, ($evidence | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))
    $FatalStateRoot = Join-Path $TestRoot 'unchanged-build-fatal-state'
    New-Item -ItemType Directory -Force -Path $FatalStateRoot | Out-Null
    Copy-Item -LiteralPath $StatePath -Destination (Join-Path $FatalStateRoot 'verify-desktop-state.json')
    $FatalStopped = $false
    try {
        & $Wrapper -StateRoot $FatalStateRoot -ToolingPython $ToolingPython *>&1 | Out-Null
    }
    catch {
        $FatalStopped = $_.Exception.Message -match 'cannot be reused'
    }
    Assert-True $FatalStopped 'canonical failure under the unchanged installed build must remain terminal'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $FatalStateRoot 'verify-desktop-state.json'))) 'terminal canonical failure must archive its wrapper state'
    Assert-True (Test-Path -LiteralPath $fixture -PathType Container) 'terminal canonical failure must preserve its forensic fixture'

    $DesktopModule = & $ToolingPython -c 'import pathlib,oh_my_codex.desktop; print(pathlib.Path(oh_my_codex.desktop.__file__))'
    Add-Content -LiteralPath $DesktopModule -Value '# simulate corrected installed build' -Encoding utf8
    $global:OmcWindowsCiClipboardText = ''
    $fresh = & $Wrapper *>&1
    Assert-True (($fresh -join "`n") -match 'installed Oh-My-Codex build changed') 'changed installed build must be identified automatically'
    Assert-True (($fresh -join "`n") -match 'STEP 1 - CONTROL THREAD') 'changed installed build must prepare and print STEP 1 automatically'
    $freshState = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    Assert-True ($freshState.run_id -ne $state3.run_id) 'changed installed build must create a fresh run'
    Assert-True ($freshState.stage -eq 'awaiting-control') 'fresh run must restart at the control stage'
    Assert-True (Test-Path -LiteralPath $fixture -PathType Container) 'automatic stale-run archival must preserve the failed forensic fixture'
    Assert-True ($global:OmcWindowsCiClipboardText -eq (Get-Content -LiteralPath $freshState.control_prompt -Raw)) 'automatic fresh run must copy the new control prompt'
    $history = Join-Path $env:LOCALAPPDATA 'Oh-My-Codex\verify-desktop-history'
    $staleArchive = @(Get-ChildItem -LiteralPath $history -Filter '*.json' | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json } | Where-Object { $_.run_id -eq $state3.run_id })
    Assert-True ($staleArchive.Count -eq 1) 'changed build must archive exactly one stale wrapper record'
    Assert-True ($staleArchive[0].terminal_reason -eq 'installed-build-changed') 'stale wrapper archive must record the installed-build change reason'

    & $Wrapper -Reset
    Assert-True (-not (Test-Path -LiteralPath $StatePath)) 'reset must remove only active wrapper state'
    Assert-True (Test-Path -LiteralPath $fixture -PathType Container) 'reset must preserve forensic fixture evidence'
    Assert-True (@(Get-ChildItem -LiteralPath $history -Filter '*.json').Count -eq 2) 'automatic stale archival and reset must each preserve one wrapper state record'
}
finally {
    Remove-Item Function:\Set-Clipboard -ErrorAction SilentlyContinue
    Remove-Variable -Name OmcWindowsCiClipboardText -Scope Global -ErrorAction SilentlyContinue
}
