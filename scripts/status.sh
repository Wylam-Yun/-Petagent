#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PORT="${PORT:-8000}"
SSHD_PORT="${SSHD_PORT:-8022}"
APK_PACKAGE="${APK_PACKAGE:-com.petagent.shell}"
HOME_DIR="${HOME_DIR:-${HOME:-/data/data/com.termux/files/home}}"
PID_FILE="$PROJECT_DIR/backend/data/runtime.pid"
LOCK_DIR="$HOME_DIR/.termux_service_manager.lock"

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

process_has_android_inet_group() {
  pid="$1"
  [ -r "/proc/$pid/status" ] || return 1
  while IFS= read -r line; do
    case "$line" in
      Groups:*)
        groups="${line#Groups:}"
        groups="$(printf '%s' "$groups" | tr '\011' ' ')"
        case " $groups " in
          *" 3003 "*)
            return 0
            ;;
        esac
        return 1
        ;;
    esac
  done < "/proc/$pid/status"
  return 1
}

process_cmdline() {
  pid="$1"
  [ -r "/proc/$pid/cmdline" ] || return 0
  tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true
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

find_manager_pid() {
  lock_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if process_exists "$lock_pid" && is_manager_process "$lock_pid"; then
    echo "$lock_pid"
    return 0
  fi

  for cmdline in /proc/[0-9]*/cmdline; do
    [ -r "$cmdline" ] || continue
    pid="${cmdline%/cmdline}"
    pid="${pid##*/}"
    [ "$pid" = "$$" ] && continue
    if is_manager_process "$pid"; then
      echo "$pid"
      return 0
    fi
  done
  return 1
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

check_port_listen() {
  port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -E "[:.]$port[[:space:]]" | grep -q LISTEN && return 0
  fi

  if command -v netstat >/dev/null 2>&1; then
    netstat -ltn 2>/dev/null | grep -E "[:.]$port[[:space:]]" | grep -q LISTEN && return 0
  fi

  if [ "$port" = "8022" ]; then
    grep -qi ":1F56 .* 0A " /proc/net/tcp /proc/net/tcp6 2>/dev/null && return 0
  fi
  return 1
}

wake_lock_status() {
  if ! command -v dumpsys >/dev/null 2>&1; then
    echo "unknown"
    return 0
  fi

  summary="$(dumpsys power 2>/dev/null | grep -i -E 'Wake Locks|termux|wake-lock|mWakeLockSummary' | head -n 80 || true)"
  if [ -z "$summary" ]; then
    echo "unknown"
    return 0
  fi

  if printf '%s\n' "$summary" | grep -qi -E 'termux|wake-lock'; then
    echo "held"
    return 0
  fi

  if printf '%s\n' "$summary" | grep -qi 'Wake Locks: size=0'; then
    echo "not held"
    return 0
  fi

  if printf '%s\n' "$summary" | grep -qi 'mWakeLockSummary=0x0'; then
    echo "not held"
    return 0
  fi

  echo "unknown"
}

termux_boot_status() {
  if ! command -v pm >/dev/null 2>&1; then
    echo "unknown"
    return 0
  fi

  packages="$(pm list packages 2>/dev/null || true)"
  if [ -z "$packages" ]; then
    echo "unknown"
    return 0
  fi
  if printf '%s\n' "$packages" | grep -qx 'package:com.termux.boot'; then
    echo "installed"
  else
    echo "missing"
  fi
}

termux_stopped_state() {
  if ! command -v dumpsys >/dev/null 2>&1; then
    echo "unknown"
    return 0
  fi

  line="$(dumpsys package com.termux 2>/dev/null | grep 'User 0:' | head -n 1 || true)"
  case "$line" in
    *"stopped=true"*)
      echo "true"
      ;;
    *"stopped=false"*)
      echo "false"
      ;;
    *)
      echo "unknown"
      ;;
  esac
}

apk_record_audio_permission_status() {
  if ! command -v dumpsys >/dev/null 2>&1; then
    echo "unknown"
    return 0
  fi

  package_dump="$(dumpsys package "$APK_PACKAGE" 2>/dev/null || true)"
  if [ -z "$package_dump" ]; then
    echo "unknown"
    return 0
  fi
  if printf '%s\n' "$package_dump" | grep -qi 'Permission Denial'; then
    echo "unknown"
    return 0
  fi
  if ! printf '%s\n' "$package_dump" | grep -q "Package \\[$APK_PACKAGE\\]"; then
    echo "missing"
    return 0
  fi

  permission_line="$(printf '%s\n' "$package_dump" | grep 'android.permission.RECORD_AUDIO' | head -n 1 || true)"
  case "$permission_line" in
    *"granted=true"*)
      echo "granted"
      ;;
    *"granted=false"*)
      echo "denied"
      ;;
    *)
      echo "unknown"
      ;;
  esac
}

apk_record_audio_appops_status() {
  if command -v appops >/dev/null 2>&1; then
    appops_output="$(appops get "$APK_PACKAGE" RECORD_AUDIO 2>&1 || true)"
  elif command -v cmd >/dev/null 2>&1; then
    appops_output="$(cmd appops get "$APK_PACKAGE" RECORD_AUDIO 2>&1 || true)"
  else
    echo "unknown"
    return 0
  fi

  case "$appops_output" in
    *"NullPointerException"*|*"Permission Denial"*)
      echo "unknown"
      ;;
    *"Unknown package"*|*"not found"*|*"No such package"*)
      echo "missing"
      ;;
    *"RECORD_AUDIO: allow"*)
      echo "allow"
      ;;
    *"RECORD_AUDIO: ignore"*)
      echo "ignore"
      ;;
    *"RECORD_AUDIO: deny"*)
      echo "deny"
      ;;
    *"No operations."*|"")
      echo "default"
      ;;
    *)
      echo "unknown"
      ;;
  esac
}

json_field() {
  key="$1"
  json="$2"
  printf '%s' "$json" | sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\\([^,}]*\\).*/\\1/p" | head -n 1 | tr -d '" '
}

if [ -d /data/data/com.termux/files/usr ] && ! has_android_inet_group; then
  echo "context: not Termux app network context"
  echo "context_detail: $(android_identity_summary)"
  echo "hint: open Termux on the phone or use Termux:Boot; adb/su u0_a137 cannot start the web server socket"
else
  echo "context: ok"
fi

MANAGER_PID="$(find_manager_pid || true)"
if [ -n "$MANAGER_PID" ]; then
  echo "manager: running ($MANAGER_PID)"
  if process_has_android_inet_group "$MANAGER_PID"; then
    echo "manager_context: ok"
  else
    echo "manager_context: missing inet group 3003"
  fi
else
  echo "manager: not running"
  echo "manager_context: not running"
fi

if check_port_listen "$SSHD_PORT"; then
  echo "sshd: listening"
else
  echo "sshd: not listening"
fi

echo "wake_lock: $(wake_lock_status)"
echo "termux_boot: $(termux_boot_status)"
echo "termux_package: stopped=$(termux_stopped_state)"
echo "apk_record_audio_permission: $(apk_record_audio_permission_status)"
echo "apk_record_audio_appops: $(apk_record_audio_appops_status)"

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
  WATCHDOG_JSON="$(curl -fsS --connect-timeout 2 --max-time 5 "http://127.0.0.1:$PORT/api/health/watchdog" 2>/dev/null || true)"
  if [ -n "$WATCHDOG_JSON" ]; then
    heartbeat_age="$(json_field frontend_heartbeat_age_s "$WATCHDOG_JSON")"
    stuck="$(json_field stuck "$WATCHDOG_JSON")"
    echo "frontend_heartbeat_age_s: ${heartbeat_age:-unknown}"
    echo "watchdog_stuck: ${stuck:-unknown}"
  else
    echo "frontend_heartbeat_age_s: unknown"
    echo "watchdog_stuck: unknown"
  fi
else
  echo "frontend_heartbeat_age_s: unknown"
  echo "watchdog_stuck: unknown"
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
