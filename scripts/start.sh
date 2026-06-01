#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
PID_FILE="$PROJECT_DIR/backend/data/runtime.pid"
LOG_FILE="$PROJECT_DIR/backend/data/logs/runtime.log"
HEALTH_URL="http://127.0.0.1:$PORT/api/health"

process_state() {
  pid="$1"
  [ -r "/proc/$pid/status" ] || return 0
  while IFS= read -r key value rest; do
    [ "$key" = "State:" ] && {
      echo "$value"
      return 0
    }
  done < "/proc/$pid/status"
}

android_identity_summary() {
  identity="$(id 2>/dev/null || true)"
  selinux="$(cat /proc/self/attr/current 2>/dev/null | tr -d '\000' || true)"
  echo "${identity:-id=unknown} selinux=${selinux:-unknown}"
}

has_android_inet_group() {
  identity="$(id 2>/dev/null || true)"
  case "$identity" in
    *"3003("*|*"3003,"*|*=",3003"*)
      return 0
      ;;
  esac
  return 1
}

require_android_runtime_context() {
  [ -d /data/data/com.termux/files/usr ] || return 0
  [ "${PETAGENT_SKIP_ANDROID_CONTEXT_CHECK:-0}" = "1" ] && return 0

  uid="$(id -u 2>/dev/null || echo "")"
  if [ "$uid" = "0" ]; then
    if [ "${PETAGENT_ALLOW_ROOT_RUNTIME:-0}" = "1" ]; then
      echo "WARNING: PetAgent runtime is starting as root; files may become root-owned."
      return 0
    fi
    echo "ERROR: refusing to start PetAgent runtime as root."
    echo "Start it from the Termux app session, or set PETAGENT_ALLOW_ROOT_RUNTIME=1 for an emergency one-off run."
    echo "Current identity: $(android_identity_summary)"
    exit 1
  fi

  if ! has_android_inet_group; then
    echo "ERROR: PetAgent runtime is not in the real Termux app network context."
    echo "Android socket permission requires the inet group (3003); adb/su u0_a137 does not grant it."
    echo "Open Termux on the phone or use Termux:Boot so the app starts the service."
    echo "Current identity: $(android_identity_summary)"
    exit 1
  fi
}

repair_android_context() {
  if [ "${PETAGENT_RESTORECON:-1}" = "0" ]; then
    return 0
  fi
  command -v su >/dev/null 2>&1 || return 0
  su -c "restorecon -R '$PROJECT_DIR/backend/data' '$PROJECT_DIR/backend/static' '$PROJECT_DIR/frontend/dist' 2>/dev/null" >/dev/null 2>&1 || true
}

process_cmdline() {
  pid="$1"
  [ -r "/proc/$pid/cmdline" ] || return 0
  tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true
}

remove_pid_file() {
  rm -f "$PID_FILE" 2>/dev/null && return 0
  repair_android_context
  rm -f "$PID_FILE" 2>/dev/null || true
}

process_exists() {
  pid="$1"
  [ -n "$pid" ] && [ -d "/proc/$pid" ] || return 1
  [ "$(process_state "$pid")" != "Z" ]
}

is_project_runtime() {
  pid="$1"
  cmdline="$(process_cmdline "$pid")"
  case "$cmdline" in
    *"$PROJECT_DIR/.venv/bin/python"*" -m uvicorn app.main:app "*)
      return 0
      ;;
  esac
  return 1
}

is_manager_process() {
  pid="$1"
  cmdline="$(process_cmdline "$pid")"
  case "$cmdline" in
    *"termux_service_manager.sh"*|*".service_manager.sh"*)
      return 0
      ;;
  esac
  return 1
}

manager_running() {
  for proc in /proc/[0-9]*; do
    pid="${proc#/proc/}"
    [ "$pid" = "$$" ] && continue
    is_manager_process "$pid" || continue
    process_exists "$pid" && return 0
  done
  return 1
}

warn_if_supervisor_missing() {
  [ -d /data/data/com.termux/files/usr ] || return 0
  manager_running && return 0
  echo "WARNING: PetAgent runtime is healthy but termux_service_manager.sh is not running."
  echo "Run scripts/termux_start_services.sh --ensure from the Termux app/SSH context to restore watchdog, wake lock, and browser recovery."
}

terminate_process() {
  pid="$1"
  kill "$pid" 2>/dev/null || true
  sleep 1
  process_exists "$pid" && kill -9 "$pid" 2>/dev/null || true
}

cleanup_duplicate_runtimes() {
  keep_pid="${1:-}"
  for proc in /proc/[0-9]*; do
    pid="${proc#/proc/}"
    [ "$pid" = "$keep_pid" ] && continue
    is_project_runtime "$pid" || continue
    echo "Stopping duplicate PetAgent runtime: $pid"
    terminate_process "$pid"
  done
  command -v su >/dev/null 2>&1 || return 0
  su -c "for proc in /proc/[0-9]*; do
    pid=\"\${proc#/proc/}\"
    [ \"\$pid\" = \"$keep_pid\" ] && continue
    cmdline=\$(tr '\000' ' ' < \"/proc/\$pid/cmdline\" 2>/dev/null || true)
    case \"\$cmdline\" in
      *\"$PROJECT_DIR/.venv/bin/python\"*\" -m uvicorn app.main:app \"*)
        echo \"Stopping duplicate PetAgent runtime as root: \$pid\"
        kill \"\$pid\" 2>/dev/null || true
        sleep 1
        [ -d \"/proc/\$pid\" ] && kill -9 \"\$pid\" 2>/dev/null || true
        ;;
    esac
  done" || true
}

START_LOCK="$PROJECT_DIR/backend/data/start.lock"
require_android_runtime_context
if [ -d "$START_LOCK" ]; then
  lock_pid="$(cat "$START_LOCK/pid" 2>/dev/null || true)"
  if process_exists "$lock_pid"; then
    echo "PetAgent start already in progress (pid $lock_pid)"
    exit 0
  fi
  rm -rf "$START_LOCK" 2>/dev/null || true
fi
# Atomic lock: mkdir without -p fails if dir already exists
if ! mkdir "$START_LOCK" 2>/dev/null; then
  # Another process抢到了锁，再检查一次
  lock_pid="$(cat "$START_LOCK/pid" 2>/dev/null || true)"
  if process_exists "$lock_pid"; then
    echo "PetAgent start already in progress (pid $lock_pid)"
    exit 0
  fi
  # Stale lock，清理后重试
  rm -rf "$START_LOCK" 2>/dev/null || true
  if ! mkdir "$START_LOCK" 2>/dev/null; then
    echo "Could not acquire start lock"
    exit 1
  fi
fi
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

pid_file_age_seconds() {
  f="$1"
  [ -f "$f" ] || { echo 999999; return 0; }
  now="$(date +%s 2>/dev/null || echo 0)"
  modified="$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null || echo 0)"
  echo $((now - modified))
}

port_listening() {
  command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -E "[:.]$PORT[[:space:]]" | grep -q LISTEN && return 0
  command -v netstat >/dev/null 2>&1 && netstat -ltn 2>/dev/null | grep -E "[:.]$PORT[[:space:]]" | grep -q LISTEN && return 0
  return 1
}

STARTUP_GRACE=120

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if process_exists "$OLD_PID"; then
    cleanup_duplicate_runtimes "$OLD_PID"
    if health_ok; then
      echo "PetAgent runtime already healthy: $OLD_PID"
      warn_if_supervisor_missing
      exit 0
    fi
    age="$(pid_file_age_seconds "$PID_FILE")"
    if [ "$age" -lt "$STARTUP_GRACE" ]; then
      if port_listening; then
        echo "PetAgent runtime pid $OLD_PID starting (${age}s, port up); waiting"
        exit 0
      fi
      echo "PetAgent runtime pid $OLD_PID starting (${age}s); waiting for grace"
      exit 0
    fi
    echo "PetAgent runtime pid $OLD_PID alive but unhealthy after ${age}s; restarting"
    kill "$OLD_PID" 2>/dev/null || true
    sleep 2
    process_exists "$OLD_PID" && kill -9 "$OLD_PID" 2>/dev/null || true
  fi
  remove_pid_file
fi

cleanup_duplicate_runtimes ""

PYTHON_BIN="${PYTHON:-python}"
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi

cd "$PROJECT_DIR/backend"
if [ "${PETAGENT_FOREGROUND:-0}" = "1" ]; then
  echo "$$" > "$PID_FILE" 2>/dev/null || {
    repair_android_context
    echo "$$" > "$PID_FILE"
  }
  echo "PetAgent runtime foreground on $HOST:$PORT ..."
  exec env PYTHONPATH="$PROJECT_DIR/backend" "$PYTHON_BIN" -m uvicorn app.main:app \
    --host "$HOST" --port "$PORT" \
    --timeout-keep-alive 15 \
    --timeout-graceful-shutdown 10 \
    --backlog 32 \
    --limit-max-requests 2000
fi

PYTHONPATH="$PROJECT_DIR/backend" nohup "$PYTHON_BIN" -m uvicorn app.main:app \
  --host "$HOST" --port "$PORT" \
  --timeout-keep-alive 15 \
  --timeout-graceful-shutdown 10 \
  --backlog 32 \
  --limit-max-requests 2000 \
  > "$LOG_FILE" 2>&1 &
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
    warn_if_supervisor_missing
    exit 0
  fi
  ATTEMPTS=$((ATTEMPTS + 1))
  sleep 2
done
echo "PetAgent runtime started but health check timed out after $((MAX_ATTEMPTS * 2))s"
exit 1
