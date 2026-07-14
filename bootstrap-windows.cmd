@echo off
setlocal
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\bootstrap-windows.ps1"
if errorlevel 1 (
  echo.
  echo Bootstrap failed. See the error above.
  if not "%PROCESSMIND_NO_PAUSE%"=="1" pause
  exit /b 1
)
echo.
echo Bootstrap complete.
if not "%PROCESSMIND_NO_PAUSE%"=="1" pause
