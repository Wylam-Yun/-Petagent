#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PORT="${PORT:-8000}"
PID_FILE="$PROJECT_DIR/backend/data/runtime.pid"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "process: running ($PID)"
  else
    echo "process: stale pid file"
  fi
else
  echo "process: not running"
fi

if command -v curl >/dev/null 2>&1; then
  curl -fsS "http://127.0.0.1:$PORT/api/health" || true
  echo
fi
