@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.runtime\python\python.exe"
if not exist "%PYTHON%" (
  echo 缺少包内 Python 3.8.10 运行时: %PYTHON%
  exit /b 1
)
"%PYTHON%" "%ROOT%scripts\win7_launcher.py" start --package-root "%ROOT%" %*
exit /b %ERRORLEVEL%
