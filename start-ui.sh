#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR/process-plan-agent-ui"

if [ ! -d node_modules ]; then
  echo "未检测到 node_modules，请先执行 ./bootstrap.sh"
  exit 1
fi

API_PORT="${PROCESSMIND_API_PORT:-8000}"
UI_PORT="${PROCESSMIND_UI_PORT:-5173}"
export VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-http://127.0.0.1:${API_PORT}}"

npm run dev -- --host 127.0.0.1 --port "$UI_PORT"
