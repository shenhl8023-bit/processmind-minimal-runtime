#!/bin/zsh
set -euo pipefail

ACTION="${1:-}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
LOG_DIR="$RUNTIME_DIR/logs"
STATE_FILE="$RUNTIME_DIR/service-pids.json"
PYTHON_EXE="$ROOT_DIR/process-plan-agent-api/.venv/bin/python"
VITE_SCRIPT="$ROOT_DIR/process-plan-agent-ui/node_modules/vite/bin/vite.js"

port_owner() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true
}

state_pid() {
  local service="$1"
  if [[ -f "$STATE_FILE" ]]; then
    sed -nE "s/.*\"${service}\"[[:space:]]*:[[:space:]]*([0-9]+).*/\1/p" "$STATE_FILE" | head -n 1
  fi
}

managed_process() {
  local service="$1"
  local process_id="$2"
  local command_line

  [[ "$process_id" =~ ^[0-9]+$ ]] || return 1
  command_line="$(ps -p "$process_id" -o command= 2>/dev/null || true)"
  [[ -n "$command_line" ]] || return 1

  if [[ "$service" == "api" ]]; then
    [[ "$command_line" == *"$PYTHON_EXE"* && "$command_line" == *"uvicorn app.main:app"* ]]
  else
    [[ "$command_line" == *"$VITE_SCRIPT"* ]]
  fi
}

write_state() {
  mkdir -p "$RUNTIME_DIR"
  printf '{\n  "api": %s,\n  "ui": %s\n}\n' "$1" "$2" > "$STATE_FILE"
}

wait_endpoint() {
  local name="$1"
  local url="$2"
  local process_id="$3"
  local attempt

  for attempt in {1..40}; do
    if ! kill -0 "$process_id" 2>/dev/null; then
      echo "$name exited before it became ready."
      return 1
    fi
    if curl --fail --silent --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done

  echo "$name did not become ready within 20 seconds."
  return 1
}

stop_process() {
  local service="$1"
  local process_id="$2"
  local attempt

  managed_process "$service" "$process_id" || return 1
  kill "$process_id" 2>/dev/null || true
  for attempt in {1..20}; do
    kill -0 "$process_id" 2>/dev/null || return 0
    sleep 0.25
  done
  kill -9 "$process_id" 2>/dev/null || true
}

show_log_tail() {
  local path="$1"
  if [[ -s "$path" ]]; then
    echo
    echo "Last lines from $path"
    tail -n 20 "$path"
  fi
}

start_application() {
  local node_exe api_pid ui_pid existing_pid
  local api_started=0
  local ui_started=0

  [[ -x "$PYTHON_EXE" ]] || { echo "Python environment is missing. Run ./bootstrap.sh first."; return 1; }
  [[ -f "$VITE_SCRIPT" ]] || { echo "Frontend dependencies are missing. Run ./bootstrap.sh first."; return 1; }
  node_exe="$(command -v node || true)"
  [[ -n "$node_exe" ]] || { echo "Node.js 20 or newer is required."; return 1; }
  command -v curl >/dev/null || { echo "curl is required."; return 1; }
  command -v lsof >/dev/null || { echo "lsof is required."; return 1; }

  mkdir -p "$LOG_DIR"

  existing_pid="$(port_owner 8000)"
  if [[ -n "$existing_pid" ]]; then
    managed_process api "$existing_pid" || { echo "Port 8000 is used by another program (PID $existing_pid)."; return 1; }
    api_pid="$existing_pid"
    echo "API is already running (PID $api_pid)."
  else
    cd "$ROOT_DIR/process-plan-agent-api"
    PROCESSMIND_DATA_DIR="$ROOT_DIR/data" nohup "$PYTHON_EXE" -m uvicorn app.main:app \
      --host 127.0.0.1 --port 8000 \
      > "$LOG_DIR/api.out.log" 2> "$LOG_DIR/api.err.log" < /dev/null &
    api_pid=$!
    api_started=1
    echo "Starting API (PID $api_pid)..."
  fi

  existing_pid="$(port_owner 5173)"
  if [[ -n "$existing_pid" ]]; then
    if ! managed_process ui "$existing_pid"; then
      echo "Port 5173 is used by another program (PID $existing_pid)."
      (( api_started )) && stop_process api "$api_pid" || true
      return 1
    fi
    ui_pid="$existing_pid"
    echo "Web UI is already running (PID $ui_pid)."
  else
    cd "$ROOT_DIR/process-plan-agent-ui"
    nohup "$node_exe" "$VITE_SCRIPT" --host 127.0.0.1 --port 5173 \
      > "$LOG_DIR/ui.out.log" 2> "$LOG_DIR/ui.err.log" < /dev/null &
    ui_pid=$!
    ui_started=1
    echo "Starting Web UI (PID $ui_pid)..."
  fi

  if ! wait_endpoint "API" "http://127.0.0.1:8000/" "$api_pid" || \
     ! wait_endpoint "Web UI" "http://127.0.0.1:5173/" "$ui_pid"; then
    (( ui_started )) && stop_process ui "$ui_pid" || true
    (( api_started )) && stop_process api "$api_pid" || true
    show_log_tail "$LOG_DIR/api.err.log"
    show_log_tail "$LOG_DIR/ui.err.log"
    return 1
  fi

  write_state "$api_pid" "$ui_pid"
  echo
  echo "ProcessMind is ready."
  echo "Web:      http://127.0.0.1:5173"
  echo "API docs: http://127.0.0.1:8000/docs"
  if [[ "${PROCESSMIND_NO_BROWSER:-0}" != "1" ]]; then
    open "http://127.0.0.1:5173" || echo "Open http://127.0.0.1:5173 in your browser."
  fi
}

stop_application() {
  local service port process_id candidate stopped_any
  stopped_any=0

  for service in ui api; do
    if [[ "$service" == "api" ]]; then
      port=8000
    else
      port=5173
    fi

    process_id="$(state_pid "$service")"
    if ! managed_process "$service" "$process_id"; then
      candidate="$(port_owner "$port")"
      if managed_process "$service" "$candidate"; then
        process_id="$candidate"
      else
        process_id=""
      fi
    fi

    if [[ -n "$process_id" ]] && stop_process "$service" "$process_id"; then
      echo "Stopped $service (PID $process_id)."
      stopped_any=1
    else
      echo "$service is not running."
    fi
  done

  rm -f "$STATE_FILE"
  if (( stopped_any )); then
    echo "ProcessMind has stopped."
  else
    echo "No ProcessMind services needed to be stopped."
  fi
}

case "$ACTION" in
  start) start_application ;;
  stop) stop_application ;;
  *) echo "Usage: $0 {start|stop}"; exit 2 ;;
esac
