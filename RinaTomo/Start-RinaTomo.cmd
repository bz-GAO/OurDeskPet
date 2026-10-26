@echo off
setlocal

set "RINATOMO_ROOT=%~dp0"
set "RINATOMO_PYTHON=%RINATOMO_ROOT%.venv\Scripts\python.exe"

if not exist "%RINATOMO_PYTHON%" (
  echo RinaTomo runtime is not installed.
  echo Run this command from PowerShell first:
  echo   powershell -ExecutionPolicy Bypass -File "%RINATOMO_ROOT%scripts\Setup-RinaTomo.ps1"
  pause
  exit /b 2
)

rem Always import the source beside this launcher. This avoids stale absolute
rem paths left by an editable install after the project folder is moved.
set "PYTHONPATH=%RINATOMO_ROOT%src;%PYTHONPATH%"
set "PYTHONDONTWRITEBYTECODE=1"
pushd "%RINATOMO_ROOT%" >nul

if "%~1"=="" (
  "%RINATOMO_PYTHON%" -m rinatomo ui
) else (
  "%RINATOMO_PYTHON%" -m rinatomo %*
)

set "RINATOMO_EXIT=%ERRORLEVEL%"
popd >nul
exit /b %RINATOMO_EXIT%
