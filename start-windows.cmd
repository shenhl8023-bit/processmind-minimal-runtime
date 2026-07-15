@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "EXIT_CODE=0"
set "ORIGINAL_NO_PAUSE=%PROCESSMIND_NO_PAUSE%"

if not exist "%ROOT%\.runtime\python\python.exe" (
  set "PROCESSMIND_NO_PAUSE=1"
  call "%ROOT%\bootstrap-windows.cmd"
  if errorlevel 1 (
    set "PROCESSMIND_NO_PAUSE=%ORIGINAL_NO_PAUSE%"
    set "EXIT_CODE=1"
    goto :finish
  )
  set "PROCESSMIND_NO_PAUSE=%ORIGINAL_NO_PAUSE%"
)

if not exist "%ROOT%\process-plan-agent-ui\node_modules\vite\bin\vite.js" (
  set "PROCESSMIND_NO_PAUSE=1"
  call "%ROOT%\bootstrap-windows.cmd"
  if errorlevel 1 (
    set "PROCESSMIND_NO_PAUSE=%ORIGINAL_NO_PAUSE%"
    set "EXIT_CODE=1"
    goto :finish
  )
  set "PROCESSMIND_NO_PAUSE=%ORIGINAL_NO_PAUSE%"
)

echo Starting ProcessMind...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\manage-windows.ps1" -Action Start
if errorlevel 1 (
  echo.
  echo ProcessMind failed to start. Check the message and logs above.
  set "EXIT_CODE=1"
)

:finish
if not "%PROCESSMIND_NO_PAUSE%"=="1" (
  echo.
  pause
)
exit /b %EXIT_CODE%
