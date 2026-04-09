#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -f "$ROOT_DIR/tsbot.env" ]]; then
  # shellcheck disable=SC1090
  source "$ROOT_DIR/tsbot.env"
fi

port_pid() {
  local port="$1"
  ss -ltnp "sport = :${port}" 2>/dev/null | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | head -n1
}

stop_one() {
  local name="$1"
  local port="$2"
  local pid_file="$ROOT_DIR/logs/${name}.pid"

  local pid=""
  if [[ -f "$pid_file" ]]; then
    pid=$(cat "$pid_file" 2>/dev/null || true)
    rm -f "$pid_file"
  fi

  if [[ -z "$pid" ]]; then
    pid=$(port_pid "$port" || true)
  fi

  if [[ -n "$pid" ]]; then
    echo "[stop] ${name} (pid=${pid})"
    kill -TERM "$pid" 2>/dev/null || true

    local count=0
    while kill -0 "$pid" 2>/dev/null && [[ $count -lt 10 ]]; do
      sleep 1
      count=$((count + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
      echo "[force-stop] ${name} (pid=${pid}) - graceful shutdown timeout"
      kill -9 "$pid" 2>/dev/null || true
      sleep 1
    else
      echo "[graceful-stop] ${name} shutdown complete"
    fi
  else
    echo "[skip] ${name} not running"
  fi
}

echo "Stopping TSBot services..."

WEB_PORT="${TSBOT_WEB_PORT:-8080}"
stop_one "web" "$WEB_PORT"
if [[ "${VITE_DEV_PORT:-5173}" != "$WEB_PORT" ]]; then
  stop_one "web-dev" "${VITE_DEV_PORT:-5173}"
fi
stop_one "backend" "${TSBOT_PORT:-8009}"
stop_one "voice" 50051

echo "All services stopped."
