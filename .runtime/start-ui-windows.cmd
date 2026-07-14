@echo off
set "ROOT=D:\Project\processmind-minimal-runtime-20260709"
cd /d "%ROOT%\process-plan-agent-ui"
"C:\Program Files\nodejs\node.exe" "%ROOT%\process-plan-agent-ui\node_modules\vite\bin\vite.js" --host 127.0.0.1 --port 5173 >> "%ROOT%\.runtime\logs\ui.stdout.log" 2>> "%ROOT%\.runtime\logs\ui.stderr.log"
