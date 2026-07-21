@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\.runtime\logs" mkdir "%ROOT%\.runtime\logs"

set "NODE_EXE="
if exist "%ROOT%\.runtime\node\node.exe" (
  set "NODE_EXE=%ROOT%\.runtime\node\node.exe"
) else (
  where node.exe >nul 2>nul
  if not errorlevel 1 (
    set "NODE_EXE=node.exe"
  ) else if exist "%ProgramFiles%\nodejs\node.exe" (
    set "NODE_EXE=%ProgramFiles%\nodejs\node.exe"
  ) else (
    echo Node.js was not found.
    echo Run: powershell -File "%ROOT%\scripts\prepare-offline-node.ps1"
    echo Or install Node.js 20+ / place portable Node at .runtime\node\node.exe
    pause
    exit /b 1
  )
)

if not exist "%ROOT%\process-plan-agent-ui\node_modules\vite\bin\vite.js" (
  echo Frontend dependencies were not found. Running bootstrap first...
  set "PROCESSMIND_NO_PAUSE=1"
  call "%ROOT%\bootstrap-windows.cmd"
  if errorlevel 1 exit /b 1
)

cd /d "%ROOT%\process-plan-agent-ui"

echo Starting ProcessMind UI on http://127.0.0.1:5173
"%NODE_EXE%" "%ROOT%\process-plan-agent-ui\node_modules\vite\bin\vite.js" --host 127.0.0.1 --port 5173

echo.
echo UI stopped.
pause
