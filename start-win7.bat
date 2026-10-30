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
"%PYTHON%" "%ROOT%scripts\win7_launcher.py" start %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
  echo ProcessMind runs in the background. Closing this window does not stop it.
  echo Run stop-win7.cmd from this folder to stop ProcessMind.
) else (
  echo ProcessMind could not start. See the error above.
)
if not "%PROCESSMIND_NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
