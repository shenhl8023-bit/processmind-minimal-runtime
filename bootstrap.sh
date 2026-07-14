#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/2] 安装后端依赖..."
cd "$ROOT_DIR/process-plan-agent-api"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[2/2] 安装前端依赖..."
cd "$ROOT_DIR/process-plan-agent-ui"
npm install

echo "完成。现在可以分别执行 ./start-api.sh 和 ./start-ui.sh"
