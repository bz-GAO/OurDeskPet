[CmdletBinding()]
param(
    [switch]$WithTests
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot '.venv'
$pythonPath = Join-Path $venvPath 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    if (Test-Path -LiteralPath $venvPath) {
        throw "The existing .venv is incomplete. Remove only '$venvPath', then run setup again."
    }
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -eq $pyLauncher) {
        throw 'Python launcher (py.exe) was not found. Install Python 3.11 or newer first.'
    }
    Write-Host 'Creating the local Python environment...'
    & $pyLauncher.Source -3 -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create '$venvPath'."
    }
}

$pyprojectPath = Join-Path $projectRoot 'pyproject.toml'
& $pythonPath -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'; import tkinter; print('Python', sys.version.split()[0])"
if ($LASTEXITCODE -ne 0) {
    throw 'RinaTomo requires a working Python 3.11+ environment with Tk. Recreate .venv after moving Python.'
}
$readDependencies = @'
import json
import pathlib
import sys
import tomllib

data = tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
dependencies = list(data["project"].get("dependencies", []))
if sys.argv[2] == "with-test":
    dependencies.extend(data["project"].get("optional-dependencies", {}).get("test", []))
print(json.dumps(dependencies))
'@
$dependencyMode = if ($WithTests) { 'with-test' } else { 'runtime-only' }
# Windows PowerShell 5.1 rewrites quotes inside native -c arguments. stdin keeps
# the Python program intact in both Windows PowerShell and PowerShell 7.
$dependencyJson = $readDependencies | & $pythonPath - $pyprojectPath $dependencyMode
if ($LASTEXITCODE -ne 0) {
    throw 'Could not read dependencies from pyproject.toml.'
}
$dependencies = @(
    foreach ($dependency in ($dependencyJson | ConvertFrom-Json)) { [string]$dependency }
)

Write-Host "Installing $($dependencies.Count) third-party dependencies into .venv..."
if ($dependencies.Count -gt 0) {
    & $pythonPath -m pip install @dependencies
    if ($LASTEXITCODE -ne 0) {
        throw 'RinaTomo dependency installation failed.'
    }
}

Write-Host 'Setup complete. Run Start-RinaTomo.cmd or Start-RinaTomo.cmd doctor.'
