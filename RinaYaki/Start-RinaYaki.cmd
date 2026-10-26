@echo off
setlocal
set "RINAYAKI_ROOT=%~dp0"
set "RINAYAKI_PYTHON=%RINAYAKI_ROOT%.venv\Scripts\python.exe"
if not exist "%RINAYAKI_PYTHON%" (
  echo Run scripts\Setup-RinaYaki.ps1 first.
  exit /b 2
)
set "PYTHONPATH=%RINAYAKI_ROOT%src;%PYTHONPATH%"
set "PYTHONDONTWRITEBYTECODE=1"
pushd "%RINAYAKI_ROOT%" >nul
if "%~1"=="" (
  "%RINAYAKI_PYTHON%" "%RINAYAKI_ROOT%scripts\yaki_ui.py"
) else (
  "%RINAYAKI_PYTHON%" -m rinayaki %*
)
set "RINAYAKI_EXIT=%ERRORLEVEL%"
popd >nul
exit /b %RINAYAKI_EXIT%
