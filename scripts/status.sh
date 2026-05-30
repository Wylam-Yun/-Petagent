#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PORT="${PORT:-8000}"
PID_FILE="$PROJECT_DIR/backend/data/runtime.pid"

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

process_exists() {
  pid="$1"
  [ -n "$pid" ] && [ -d "/proc/$pid" ] || return 1
  [ "$(process_state "$pid")" != "Z" ]
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

if [ -d /data/data/com.termux/files/usr ] && ! has_android_inet_group; then
  echo "context: not Termux app network context"
  echo "context_detail: $(android_identity_summary)"
  echo "hint: open Termux on the phone or use Termux:Boot; adb/su u0_a137 cannot start the web server socket"
else
  echo "context: ok"
fi

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if process_exists "$PID"; then
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

if command -v python >/dev/null 2>&1; then
  python - "$PROJECT_DIR/backend/data/pet.db" <<'PY' || true
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
if not db_path.exists():
    print("database: missing")
    raise SystemExit(0)

try:
    con = sqlite3.connect(str(db_path))
    result = con.execute("PRAGMA quick_check").fetchone()
    print(f"database: {result[0] if result else 'unknown'}")
except sqlite3.DatabaseError as exc:
    print(f"database: malformed ({exc})")
PY
fi
