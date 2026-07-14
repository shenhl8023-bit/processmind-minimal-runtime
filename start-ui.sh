#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR/process-plan-agent-ui"

if [ ! -d node_modules ]; then
  echo "未检测到 node_modules，请先执行 ./bootstrap.sh"
  exit 1
fi

npm run dev -- --host 127.0.0.1 --port 5173
