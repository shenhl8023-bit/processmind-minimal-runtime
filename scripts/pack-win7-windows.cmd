@echo off
setlocal
set "HERE=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%pack-win7-windows.ps1" %*
if errorlevel 1 (
  echo.
  echo Win7 package build failed.
  exit /b 1
)
echo.
echo Win7 package build completed.
