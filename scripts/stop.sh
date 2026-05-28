#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PID_FILE="$PROJECT_DIR/backend/data/runtime.pid"

process_cmdline() {
  pid="$1"
  tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true
}

process_exists() {
  pid="$1"
  [ -n "$pid" ] && [ -d "/proc/$pid" ]
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

terminate_process() {
  pid="$1"
  kill "$pid" 2>/dev/null || true
  sleep 1
  process_exists "$pid" && kill -9 "$pid" 2>/dev/null || true
}

stop_all_project_runtimes() {
  for proc in /proc/[0-9]*; do
    pid="${proc#/proc/}"
    is_project_runtime "$pid" || continue
    echo "Stopping PetAgent runtime: $pid"
    terminate_process "$pid"
  done
  command -v su >/dev/null 2>&1 || return 0
  su -c "for proc in /proc/[0-9]*; do
    pid=\"\${proc#/proc/}\"
    cmdline=\$(tr '\000' ' ' < \"/proc/\$pid/cmdline\" 2>/dev/null || true)
    case \"\$cmdline\" in
      *\"$PROJECT_DIR/.venv/bin/python\"*\" -m uvicorn app.main:app \"*)
        echo \"Stopping PetAgent runtime as root: \$pid\"
        kill \"\$pid\" 2>/dev/null || true
        sleep 1
        [ -d \"/proc/\$pid\" ] && kill -9 \"\$pid\" 2>/dev/null || true
        ;;
    esac
  done" || true
}

PID=""
if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
fi

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  terminate_process "$PID"
fi
stop_all_project_runtimes

rm -f "$PID_FILE"
echo "PetAgent runtime stopped"
