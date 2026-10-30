@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.runtime\python\python.exe"
if not exist "%PYTHON%" (
  echo Missing bundled Python 3.8.10 runtime.
  echo Expected: "%PYTHON%"
  if not "%PROCESSMIND_NO_PAUSE%"=="1" pause
  exit /b 1
)
"%PYTHON%" "%ROOT%scripts\win7_launcher.py" stop %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo Stop failed. See the error above. State is retained for retry.
if not "%PROCESSMIND_NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
