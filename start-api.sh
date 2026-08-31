#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR/process-plan-agent-api"

if [ ! -d .venv ]; then
  echo "未检测到 .venv，请先执行 ./bootstrap.sh"
  exit 1
fi

source .venv/bin/activate
export PROCESSMIND_DATA_DIR="${PROCESSMIND_DATA_DIR:-$ROOT_DIR/data}"
API_PORT="${PROCESSMIND_API_PORT:-8000}"
uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
