#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
PID_FILE="$PROJECT_DIR/backend/data/runtime.pid"
LOG_FILE="$PROJECT_DIR/backend/data/logs/runtime.log"

mkdir -p "$PROJECT_DIR/backend/data/logs" "$PROJECT_DIR/backend/static/audio"

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  . "$PROJECT_DIR/.env"
  set +a
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "PetAgent runtime already running: $OLD_PID"
    exit 0
  fi
fi

PYTHON_BIN="${PYTHON:-python}"
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi

cd "$PROJECT_DIR/backend"
PYTHONPATH="$PROJECT_DIR/backend" nohup "$PYTHON_BIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
echo "$!" > "$PID_FILE"
echo "PetAgent runtime started on $HOST:$PORT"
