#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$PROJECT_DIR/plan/V2.0/runtime-monitor}"
LAN_HOST="${LAN_HOST:-nubia}"
ADB_HOST="${ADB_HOST:-nubia-adb}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:18000/api/health}"
BUILD_URL="${BUILD_URL:-http://127.0.0.1:18000/build-info.json}"
DURATION_MIN=0
INTERVAL_SEC=60

usage() {
  cat <<'EOF'
Usage: scripts/runtime_soak_monitor.sh [--duration-min N] [--interval-sec N]

Samples PetAgent runtime health without running voice tests.
Prefers LAN SSH host "nubia"; falls back to "nubia-adb".
Writes NDJSON to plan/V2.0/runtime-monitor/.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --duration-min)
      DURATION_MIN="${2:?missing value for --duration-min}"
      shift 2
      ;;
    --interval-sec)
      INTERVAL_SEC="${2:?missing value for --interval-sec}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

json_line() {
  local ts route adb_state forward_state mac_health mac_build ssh_status package_state wake_state note
  ts="$1"
  route="$2"
  adb_state="$3"
  forward_state="$4"
  mac_health="$5"
  mac_build="$6"
  ssh_status="$7"
  package_state="$8"
  wake_state="$9"
  note="${10}"
  printf '{"ts":%s,"route":%s,"adb":%s,"forwards":%s,"mac_health":%s,"mac_build":%s,"ssh_status":%s,"packages":%s,"wake":%s,"note":%s}\n' \
    "$(printf '%s' "$ts" | json_escape)" \
    "$(printf '%s' "$route" | json_escape)" \
    "$(printf '%s' "$adb_state" | json_escape)" \
    "$(printf '%s' "$forward_state" | json_escape)" \
    "$(printf '%s' "$mac_health" | json_escape)" \
    "$(printf '%s' "$mac_build" | json_escape)" \
    "$(printf '%s' "$ssh_status" | json_escape)" \
    "$(printf '%s' "$package_state" | json_escape)" \
    "$(printf '%s' "$wake_state" | json_escape)" \
    "$(printf '%s' "$note" | json_escape)"
}

ssh_route() {
  if ssh -o BatchMode=yes -o ConnectTimeout=5 "$LAN_HOST" 'true' >/dev/null 2>&1; then
    echo "$LAN_HOST"
    return 0
  fi
  if ssh -o BatchMode=yes -o ConnectTimeout=5 "$ADB_HOST" 'true' >/dev/null 2>&1; then
    echo "$ADB_HOST"
    return 0
  fi
  echo ""
  return 1
}

sample_once() {
  local ts adb_state forward_state route mac_health mac_build ssh_status package_state wake_state note
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  adb_state="$(adb devices -l 2>&1 | tr '\n' ';' || true)"
  adb forward tcp:18022 tcp:8022 >/dev/null 2>&1 || true
  adb forward tcp:18000 tcp:8000 >/dev/null 2>&1 || true
  forward_state="$(adb forward --list 2>&1 | tr '\n' ';' || true)"
  mac_health="$(curl -fsS --connect-timeout 2 --max-time 5 "$HEALTH_URL" 2>&1 || true)"
  mac_build="$(curl -fsS --connect-timeout 2 --max-time 5 "$BUILD_URL" 2>&1 || true)"
  route="$(ssh_route || true)"
  note=""

  if [ -n "$route" ]; then
    ssh_status="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$route" 'id; cd ~/Petagent && scripts/status.sh' 2>&1 || true)"
  else
    ssh_status=""
    note="ssh_unreachable"
  fi

  package_state="$(adb shell 'dumpsys package com.termux 2>/dev/null | grep "User 0:" | head -1; dumpsys package com.termux.boot 2>/dev/null | grep "User 0:" | head -1; dumpsys package com.petagent.shell 2>/dev/null | grep "User 0:" | head -1' 2>&1 | tr '\n' ';' || true)"
  wake_state="$(adb shell 'dumpsys power 2>/dev/null | grep -i -E "mWakeLockSummary|Wake Locks|termux|wake" | head -80' 2>&1 | tr '\n' ';' || true)"

  json_line "$ts" "$route" "$adb_state" "$forward_state" "$mac_health" "$mac_build" "$ssh_status" "$package_state" "$wake_state" "$note"
}

mkdir -p "$OUT_DIR"
out_file="$OUT_DIR/runtime-soak-$(date '+%Y%m%d-%H%M%S').jsonl"
echo "Writing monitor samples to $out_file" >&2

if [ "$DURATION_MIN" -le 0 ]; then
  sample_once | tee -a "$out_file"
  exit 0
fi

end_at=$(( $(date +%s) + DURATION_MIN * 60 ))
while [ "$(date +%s)" -lt "$end_at" ]; do
  sample_once | tee -a "$out_file"
  sleep "$INTERVAL_SEC"
done
