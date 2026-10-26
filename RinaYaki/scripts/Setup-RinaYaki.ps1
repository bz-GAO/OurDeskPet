[CmdletBinding()]
param([switch]$WithoutLive, [switch]$WithoutWebView)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot '.venv'
$pythonPath = Join-Path $venvPath 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if (Test-Path -LiteralPath $venvPath) { throw 'Existing .venv is incomplete; recreate that environment before setup.' }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $launcher) { throw 'Install Python 3.11 or newer with Tk and the Python launcher first.' }
    & $launcher.Source -3 -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $pythonPath -c "import sys; assert sys.version_info >= (3, 11); import tkinter"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ with Tk is required; recreate .venv if Python has moved.' }
$extras = @()
if (-not $WithoutLive) { $extras += 'live' }
if (-not $WithoutWebView) { $extras += 'webview' }
$installTarget = if ($extras.Count) { $projectRoot + '[' + ($extras -join ',') + ']' } else { $projectRoot }
& $pythonPath -m pip install -e $installTarget
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Setup complete. Open Start-RinaYaki.vbs. API credentials, media tools and models are configured separately.'
