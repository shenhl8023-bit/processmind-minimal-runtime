@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0pack-win7-windows.ps1" -Edition basic-trial %*
exit /b %errorlevel%
