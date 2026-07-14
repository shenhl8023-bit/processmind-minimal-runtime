@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\.runtime\python\python.exe" (
  set "PROCESSMIND_NO_PAUSE=1"
  call "%ROOT%\bootstrap-windows.cmd"
  if errorlevel 1 exit /b 1
)

if not exist "%ROOT%\process-plan-agent-ui\node_modules\vite\bin\vite.js" (
  set "PROCESSMIND_NO_PAUSE=1"
  call "%ROOT%\bootstrap-windows.cmd"
  if errorlevel 1 exit /b 1
)

echo Starting ProcessMind...
echo.
start "ProcessMind API" cmd.exe /k ""%ROOT%\start-api.cmd""
timeout /t 3 /nobreak >nul
start "ProcessMind UI" cmd.exe /k ""%ROOT%\start-ui.cmd""

echo.
echo Keep the API and UI windows open while using the app.
echo Web:     http://127.0.0.1:5173
echo API docs: http://127.0.0.1:8000/docs
echo.
pause
