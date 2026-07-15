@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "EXIT_CODE=0"
echo Stopping ProcessMind...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\manage-windows.ps1" -Action Stop
if errorlevel 1 (
  echo.
  echo ProcessMind could not be stopped cleanly.
  set "EXIT_CODE=1"
)

if not "%PROCESSMIND_NO_PAUSE%"=="1" (
  echo.
  pause
)
exit /b %EXIT_CODE%
