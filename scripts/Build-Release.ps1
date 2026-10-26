[CmdletBinding()]
param([string]$CacheRoot, [switch]$SkipTests)
$ErrorActionPreference='Stop'
$releaseRoot=Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $releaseRoot 'release-manifest.json'))) { throw 'Not an OurDeskPet release root.' }
if (-not $CacheRoot) { $CacheRoot=Join-Path $releaseRoot '.build-cache' }
$previousTarget=$env:CARGO_TARGET_DIR
$previousPath=$env:PATH
$previousTime=$env:RINADESK_BUILD_TIME
$previousRevision=$env:RINADESK_SOURCE_REVISION
try {
    $env:CARGO_TARGET_DIR=Join-Path $CacheRoot 'cargo-target'
    $env:RINADESK_BUILD_TIME=[DateTimeOffset]::Now.ToString('yyyy-MM-dd HH:mm:ss zzz')
    $env:RINADESK_SOURCE_REVISION='OurDeskPet-release'
    if (-not (Get-Command rc.exe -ErrorAction SilentlyContinue)) {
        $kits=Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10/bin'
        $compiler=Get-ChildItem -LiteralPath $kits -Directory | Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'x64/rc.exe' } | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $compiler) { throw 'Windows SDK resource compiler unavailable.' }
        $env:PATH=(Split-Path -Parent $compiler)+';'+$env:PATH
    }
    $portablePython=Join-Path $releaseRoot 'RinaYaki/.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $portablePython)) { throw 'Portable runtime missing; prepare it before building.' }
    & $portablePython (Join-Path $PSScriptRoot 'prepare-package.py') --root $releaseRoot
    if ($LASTEXITCODE -ne 0) { throw 'Package manifest preparation failed.' }
    Push-Location (Join-Path $releaseRoot 'RinaDesk/app')
    try {
        if (-not $SkipTests) {
            & node.exe 'scripts/release-check.cjs'
            if ($LASTEXITCODE -ne 0) { throw 'Release checks failed.' }
        }
        & npm.cmd run tauri build -- --bundles nsis --config src-tauri/tauri.package.json
        if ($LASTEXITCODE -ne 0) { throw 'OurDeskPet installer build failed.' }
    } finally { Pop-Location }
    $generated=Join-Path $env:CARGO_TARGET_DIR 'release/nsis/x64'
    $bundle=Join-Path $env:CARGO_TARGET_DIR 'release/bundle/nsis/OurDeskPet_0.1.0_x64-setup.exe'
    & (Join-Path $releaseRoot 'RinaDesk/scripts/Apply-InstallerPreviewTemplate.ps1') -GeneratedRoot $generated -BundlePath $bundle
    $artifacts=Join-Path $releaseRoot 'artifacts'
    New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
    $setup=Join-Path $artifacts 'OurDeskPet-0.1.0-x64-setup_test.exe'
    Copy-Item -LiteralPath $bundle -Destination $setup -Force
    $hash=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath (Join-Path $artifacts 'OurDeskPet-0.1.0-x64-setup_test.sha256') -Value "$hash  OurDeskPet-0.1.0-x64-setup_test.exe" -Encoding ascii
    Write-Output "Installer: $setup"
    Write-Output "SHA-256: $hash"
} finally {
    $env:CARGO_TARGET_DIR=$previousTarget
    $env:PATH=$previousPath
    $env:RINADESK_BUILD_TIME=$previousTime
    $env:RINADESK_SOURCE_REVISION=$previousRevision
}
