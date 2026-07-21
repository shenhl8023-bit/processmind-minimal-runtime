@echo off
setlocal
set "HERE=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%assemble-offline-windows.ps1" %*
if errorlevel 1 (
  echo.
  echo Assemble failed.
  pause
  exit /b 1
)
echo.
pause
