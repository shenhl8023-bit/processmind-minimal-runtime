@echo off
set "ROOT=D:\Project\processmind-minimal-runtime-20260709"
set "PROCESSMIND_DATA_DIR=%ROOT%\data"
cd /d "%ROOT%\process-plan-agent-api"
"%ROOT%\.runtime\python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "%ROOT%\.runtime\logs\api.stdout.log" 2>> "%ROOT%\.runtime\logs\api.stderr.log"
