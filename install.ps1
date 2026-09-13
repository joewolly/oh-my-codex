[CmdletBinding()]
param(
    [string]$VenvDir,
    [string]$CodexHome,
    [string]$SkillsHome,
    [switch]$SkipDoctor
)

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bootstrap = Join-Path $RootDir 'scripts/bootstrap.py'

if (-not (Test-Path -LiteralPath $Bootstrap -PathType Leaf)) {
    throw "Oh-My-Codex bootstrap is missing: $Bootstrap"
}

$candidates = @()
if ($env:PYTHON) {
    $candidates += [pscustomobject]@{ Exe = $env:PYTHON; Prefix = @() }
}
$candidates += [pscustomobject]@{ Exe = 'py'; Prefix = @('-3.13') }
$candidates += [pscustomobject]@{ Exe = 'py'; Prefix = @('-3.12') }
$candidates += [pscustomobject]@{ Exe = 'py'; Prefix = @('-3.11') }
$candidates += [pscustomobject]@{ Exe = 'python'; Prefix = @() }

$selected = $null
foreach ($candidate in $candidates) {
    try {
        & $candidate.Exe @($candidate.Prefix) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' *> $null
        if ($LASTEXITCODE -eq 0) {
            $selected = $candidate
            break
        }
    }
    catch {
        continue
    }
}

if ($null -eq $selected) {
    throw 'Oh-My-Codex requires Python 3.11 or newer. Install Python 3.11+ and rerun .\install.ps1.'
}

$bootstrapArgs = @($Bootstrap)
if ($VenvDir) {
    $bootstrapArgs += @('--venv-dir', $VenvDir)
}
if ($CodexHome) {
    $bootstrapArgs += @('--codex-home', $CodexHome)
}
if ($SkillsHome) {
    $bootstrapArgs += @('--skills-home', $SkillsHome)
}
if ($SkipDoctor) {
    $bootstrapArgs += '--skip-doctor'
}

$prefix = @($selected.Prefix)
& $selected.Exe @prefix @bootstrapArgs
exit $LASTEXITCODE
