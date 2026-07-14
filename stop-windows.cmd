@echo off
setlocal
echo Stopping ProcessMind services on ports 5173 and 8000...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":5173 .*LISTENING" /C:":8000 .*LISTENING"') do (
  taskkill /PID %%P /F >nul 2>nul
)
echo Done.
pause
