@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "KB_ID=KB2533623"
set "MSU_PATH=%~dp0Windows6.1-KB2533623-x64.msu"

rem Avoid reinstalling the prerequisite when the hotfix is already present.
wmic qfe get HotFixID 2>nul | findstr /I /C:"%KB_ID%" >nul
if not errorlevel 1 (
  echo [已安装] %KB_ID% 已经存在，无需重复执行。
  exit /b 0
)

if not exist "%MSU_PATH%" (
  echo [错误] 找不到离线更新文件：%MSU_PATH%
  exit /b 2
)

rem Installing a system update requires an elevated administrator console.
net session >nul 2>&1
if errorlevel 1 (
  echo [错误] 请右键本脚本并选择“以管理员身份运行”。
  exit /b 3
)

echo [开始] 正在安装 %KB_ID%，完成后请手动重启 Windows 7。
wusa.exe "%MSU_PATH%" /norestart
set "WUSA_EXIT=%ERRORLEVEL%"
if "%WUSA_EXIT%"=="0" (
  echo [完成] %KB_ID% 已提交安装，请手动重启后再启动 ProcessMind。
  exit /b 0
)
if "%WUSA_EXIT%"=="3010" (
  echo [完成] %KB_ID% 已安装，必须重启 Windows 7 才会生效。
  exit /b 0
)

echo [失败] WUSA 返回代码 %WUSA_EXIT%，请查看 Windows 更新日志。
exit /b %WUSA_EXIT%
