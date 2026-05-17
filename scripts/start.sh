#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
PID_FILE="$PROJECT_DIR/backend/data/runtime.pid"
LOG_FILE="$PROJECT_DIR/backend/data/logs/runtime.log"
HEALTH_URL="http://127.0.0.1:$PORT/api/health"

repair_android_context() {
  if [ "${PETAGENT_RESTORECON:-1}" = "0" ]; then
    return 0
  fi
  command -v su >/dev/null 2>&1 || return 0
  su -c "restorecon -R '$PROJECT_DIR/backend/data' '$PROJECT_DIR/backend/static' '$PROJECT_DIR/frontend/dist' 2>/dev/null" >/dev/null 2>&1 || true
}

remove_pid_file() {
  rm -f "$PID_FILE" 2>/dev/null && return 0
  repair_android_context
  rm -f "$PID_FILE" 2>/dev/null || true
}

START_LOCK="$PROJECT_DIR/backend/data/start.lock"
if [ -d "$START_LOCK" ]; then
  lock_pid="$(cat "$START_LOCK/pid" 2>/dev/null || true)"
  if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
    echo "PetAgent start already in progress (pid $lock_pid)"
    exit 0
  fi
  rm -rf "$START_LOCK" 2>/dev/null || true
fi
mkdir -p "$START_LOCK" 2>/dev/null || true
echo "$$" > "$START_LOCK/pid" 2>/dev/null || true
trap 'rm -rf "$START_LOCK" 2>/dev/null || true' EXIT

repair_android_context
mkdir -p "$PROJECT_DIR/backend/data/logs" "$PROJECT_DIR/backend/static/audio"

if [ -x "$PROJECT_DIR/scripts/clean_cache.sh" ]; then
  "$PROJECT_DIR/scripts/clean_cache.sh" >/dev/null 2>&1 || true
fi

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  . "$PROJECT_DIR/.env"
  set +a
fi

health_ok() {
  command -v curl >/dev/null 2>&1 || return 1
  curl -s --connect-timeout 2 --max-time 5 "$HEALTH_URL" 2>/dev/null | grep -q '"ok":true'
}

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    if health_ok; then
      echo "PetAgent runtime already healthy: $OLD_PID"
      exit 0
    fi
    echo "PetAgent runtime pid $OLD_PID is alive but unhealthy; restarting"
    kill "$OLD_PID" 2>/dev/null || true
    sleep 2
    kill -0 "$OLD_PID" 2>/dev/null && kill -9 "$OLD_PID" 2>/dev/null || true
  fi
  remove_pid_file
fi

PYTHON_BIN="${PYTHON:-python}"
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi

cd "$PROJECT_DIR/backend"
PYTHONPATH="$PROJECT_DIR/backend" nohup "$PYTHON_BIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
echo "$!" > "$PID_FILE" 2>/dev/null || {
  repair_android_context
  echo "$!" > "$PID_FILE"
}
echo "PetAgent runtime starting on $HOST:$PORT ..."

ATTEMPTS=0
MAX_ATTEMPTS=60
while [ "$ATTEMPTS" -lt "$MAX_ATTEMPTS" ]; do
  if health_ok; then
    echo "PetAgent runtime ready on $HOST:$PORT"
    exit 0
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  sleep 2
done
echo "PetAgent runtime started but health check timed out after $((MAX_ATTEMPTS * 2))s"
exit 1
