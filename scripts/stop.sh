#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PID_FILE="$PROJECT_DIR/backend/data/runtime.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "PetAgent runtime is not running"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  kill "$PID" 2>/dev/null || true
  sleep 1
fi

rm -f "$PID_FILE"
echo "PetAgent runtime stopped"
