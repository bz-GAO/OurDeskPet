[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GeneratedRoot,
    [Parameter(Mandatory = $true)][string]$BundlePath
)

$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $GeneratedRoot 'installer.nsi'
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Generated NSIS script is missing: $scriptPath"
}

$text = Get-Content -LiteralPath $scriptPath -Raw
$varMarker = 'Var OldMainBinaryName'
$pageMarker = '; 1. Welcome Page'
$languageMarker = '!insertmacro MUI_RESERVEFILE_LANGDLL'
$maintenanceMarker = '  ; Reinstalling the same version'
$renderMarker = '  ; Skip showing the page if passive'
$upgradeHeader = '    !insertmacro MUI_HEADER_TEXT "$(alreadyInstalled)" "$(choowHowToInstall)"'
$finishReadme = '!define MUI_FINISHPAGE_SHOWREADME_TEXT "$(createDesktop)"'
$finishRun = '!define MUI_FINISHPAGE_RUN_FUNCTION RunMainBinary'
$brandingMarker = 'BrandingText "${COPYRIGHT}"'
$licensePageMarker = '!insertmacro MUI_PAGE_LICENSE "${LICENSE}"'
$noAutoCloseMarker = '!define MUI_FINISHPAGE_NOAUTOCLOSE'
$mainBinaryMarker = '  File "${MAINBINARYSRCPATH}"'
$selectorPattern = '(?m)^  !if "\$\{DISPLAYLANGUAGESELECTOR\}" == "true"\r?\n    !insertmacro MUI_LANGDLL_DISPLAY\r?\n  !endif'
foreach ($marker in @($varMarker, $pageMarker, $languageMarker, $maintenanceMarker, $renderMarker, $upgradeHeader, $finishReadme, $finishRun, $brandingMarker, $licensePageMarker, $noAutoCloseMarker, $mainBinaryMarker)) {
    if (-not $text.Contains($marker)) {
        throw "The generated NSIS template changed; expected marker was not found: $marker"
    }
}
if (-not [regex]::IsMatch($text, $selectorPattern)) {
    throw 'The generated NSIS template changed; the language-dialog block was not found.'
}

$text = $text.Replace($varMarker, @'
Var OldMainBinaryName
Var RinaLanguageCombo
'@)
$text = $text.Replace($pageMarker, @'
; 0. Language selection. This in-window page is deterministic under UI automation;
; the separate MUI language dialog is disabled below.
Page custom PageRinaLanguage PageLeaveRinaLanguage

; 1. Welcome Page
'@)
$text = $text.Replace($maintenanceMarker, @'
  ; A registration without the main executable or uninstaller is repairable,
  ; but it must not be presented as a complete current installation.
  ${IfNot} ${FileExists} "$INSTDIR\${MAINBINARYNAME}.exe"
  ${OrIfNot} ${FileExists} "$INSTDIR\uninstall.exe"
    StrCpy $R1 "$(incompleteInstallLong)"
    StrCpy $R2 "$(addOrReinstall)"
    StrCpy $R3 "$(uninstallApp)"
    !insertmacro MUI_HEADER_TEXT "$(incompleteInstall)" "$(chooseMaintenanceOption)"
    Goto render_reinstall_page
  ${EndIf}

  ; Reinstalling the same version
'@)
$text = $text.Replace($renderMarker, @'
  render_reinstall_page:
  ; Skip showing the page if passive
'@)
$upgradeHeaders = [regex]::Matches($text, [regex]::Escape($upgradeHeader))
if ($upgradeHeaders.Count -ne 2) {
    throw "Expected two upgrade/downgrade headers, found $($upgradeHeaders.Count)."
}
$firstHeader = $text.IndexOf($upgradeHeader)
$text = $text.Remove($firstHeader, $upgradeHeader.Length).Insert($firstHeader, '    !insertmacro MUI_HEADER_TEXT "$(updateAvailable)" "$(choowHowToInstall)"')
$lastHeader = $text.LastIndexOf('    !insertmacro MUI_HEADER_TEXT "$(alreadyInstalled)" "$(choowHowToInstall)"')
if ($lastHeader -lt 0) { throw 'Downgrade header marker was not found after updating the upgrade header.' }
$text = $text.Remove($lastHeader, $upgradeHeader.Length).Insert($lastHeader, '    !insertmacro MUI_HEADER_TEXT "$(newerInstalled)" "$(choowHowToInstall)"')
$text = $text.Replace($finishReadme, "!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED`r`n$finishReadme")
$text = $text.Replace($finishRun, "!define MUI_FINISHPAGE_RUN_NOTCHECKED`r`n$finishRun")
$text = $text.Replace($brandingMarker, "BrandingText `"@bz-GAO`"`r`nShowInstDetails nevershow")
# Welcome and finish are nsDialogs pages and support native clickable links.
$text = $text.Replace('!insertmacro MUI_PAGE_WELCOME', "!define MUI_PAGE_CUSTOMFUNCTION_SHOW RinaWelcomeAuthor`r`n!insertmacro MUI_PAGE_WELCOME")
$text = $text.Replace('!insertmacro MUI_PAGE_FINISH', "!define MUI_FINISHPAGE_LINK `"@bz-GAO`"`r`n!define MUI_FINISHPAGE_LINK_LOCATION `"https://github.com/bz-GAO/OurDeskPet`"`r`n!insertmacro MUI_PAGE_FINISH")
$text = $text.Replace($licensePageMarker, @'
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_LICENSEPAGE_CHECKBOX_TEXT "$(licenseCheckbox)"
!define MUI_LICENSEPAGE_TEXT_BOTTOM " "
!insertmacro MUI_PAGE_LICENSE "${LICENSE}"
'@)
$text = $text.Replace($noAutoCloseMarker, '; Continue directly to the finish page when installation succeeds.')
$text = $text.Replace($mainBinaryMarker, @'
  SetDetailsPrint textonly
  DetailPrint "$(installingRinaDesk)"
  SetDetailsPrint none
  File "${MAINBINARYSRCPATH}"
'@)
$languageFunctions = @'

Function PageRinaLanguage
  nsDialogs::Create 1018
  Pop $0
  ${IfThen} $0 == error ${|} Abort ${|}
  GetDlgItem $1 $HWNDPARENT 1037
  ShowWindow $1 ${SW_HIDE}
  GetDlgItem $1 $HWNDPARENT 1038
  ShowWindow $1 ${SW_HIDE}
  GetDlgItem $1 $HWNDPARENT 1034
  ShowWindow $1 ${SW_HIDE}
  GetDlgItem $1 $HWNDPARENT 1039
  ShowWindow $1 ${SW_HIDE}
  GetDlgItem $1 $HWNDPARENT 1035
  ShowWindow $1 ${SW_HIDE}
  GetDlgItem $1 $HWNDPARENT 1045
  ShowWindow $1 ${SW_HIDE}
  ${NSD_CreateLabel} 30u 50u 240u 18u "选择语言"
  Pop $1
  ${NSD_AddStyle} $1 ${SS_CENTER}
  ${NSD_CreateDropList} 70u 76u 160u 120u ""
  Pop $RinaLanguageCombo
  ${NSD_CB_AddString} $RinaLanguageCombo "简体中文"
  ${NSD_CB_AddString} $RinaLanguageCombo "English"
  SendMessage $RinaLanguageCombo ${CB_SETCURSEL} 0 0
  ${NSD_CreateLink} 215u 125u 80u 12u "@bz-GAO"
  Pop $1
  ${NSD_OnClick} $1 RinaOpenProject
  nsDialogs::Show
FunctionEnd

Function RinaWelcomeAuthor
  ${NSD_CreateLink} 120u 166u 90u 16u "@bz-GAO"
  Pop $0
  SetCtlColors $0 0067C0 FFFFFF
  System::Call 'user32::BringWindowToTop(p r0)'
  ${NSD_OnClick} $0 RinaOpenProject
FunctionEnd

Function RinaOpenProject
  Pop $0
  ExecShell "open" "https://github.com/bz-GAO/OurDeskPet"
FunctionEnd

Function PageLeaveRinaLanguage
  ${NSD_GetText} $RinaLanguageCombo $0
  ${If} $0 == "English"
    StrCpy $LANGUAGE 1033
  ${Else}
    StrCpy $LANGUAGE 2052
  ${EndIf}
  GetDlgItem $1 $HWNDPARENT 1037
  ShowWindow $1 ${SW_SHOW}
  GetDlgItem $1 $HWNDPARENT 1038
  ShowWindow $1 ${SW_SHOW}
  GetDlgItem $1 $HWNDPARENT 1034
  ShowWindow $1 ${SW_SHOW}
  GetDlgItem $1 $HWNDPARENT 1039
  ShowWindow $1 ${SW_SHOW}
  GetDlgItem $1 $HWNDPARENT 1035
  ShowWindow $1 ${SW_SHOW}
  GetDlgItem $1 $HWNDPARENT 1045
  ShowWindow $1 ${SW_SHOW}
FunctionEnd
'@
$text = $text.Replace($languageMarker, $languageMarker + $languageFunctions)
$text = [regex]::Replace($text, $selectorPattern, @'
  ; RinaDesk uses the first in-window page for deterministic language selection.
'@)

[IO.File]::WriteAllText($scriptPath, $text, [Text.UTF8Encoding]::new($true))
$makeNsis = Join-Path $env:LOCALAPPDATA 'tauri\NSIS\makensis.exe'
if (-not (Test-Path -LiteralPath $makeNsis -PathType Leaf)) {
    throw "NSIS compiler is missing: $makeNsis"
}
$rebuilt = Join-Path $GeneratedRoot 'nsis-output.exe'
Remove-Item -LiteralPath $rebuilt -Force -ErrorAction SilentlyContinue
Push-Location $GeneratedRoot
try {
    & $makeNsis /V2 (Split-Path -Leaf $scriptPath)
    if ($LASTEXITCODE -ne 0) { throw 'Customized NSIS compilation failed.' }
} finally {
    Pop-Location
}
if (-not (Test-Path -LiteralPath $rebuilt -PathType Leaf)) {
    throw "Customized NSIS output is missing: $rebuilt"
}
Move-Item -LiteralPath $rebuilt -Destination $BundlePath -Force
Write-Output 'Applied RinaDesk language page to generated NSIS installer.'
