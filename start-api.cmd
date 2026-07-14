@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\.runtime\logs" mkdir "%ROOT%\.runtime\logs"

if not exist "%ROOT%\.runtime\python\python.exe" (
  echo Portable Python was not found. Running bootstrap first...
  set "PROCESSMIND_NO_PAUSE=1"
  call "%ROOT%\bootstrap-windows.cmd"
  if errorlevel 1 exit /b 1
)

set "PROCESSMIND_DATA_DIR=%ROOT%\data"
cd /d "%ROOT%\process-plan-agent-api"

echo Starting ProcessMind API on http://127.0.0.1:8000
"%ROOT%\.runtime\python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo API stopped.
pause
