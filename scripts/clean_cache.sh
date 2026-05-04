#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
AUDIO_DIR="$PROJECT_DIR/backend/static/audio"
UPLOAD_DIR="$PROJECT_DIR/backend/data/uploads"
MAX_CACHE_MB="${PETAGENT_MAX_AUDIO_CACHE_MB:-200}"
MAX_CACHE_KB=$((MAX_CACHE_MB * 1024))

if [ -d "$AUDIO_DIR" ]; then
  find "$AUDIO_DIR" -type f -mtime +3 -delete
fi

if [ -d "$UPLOAD_DIR" ]; then
  find "$UPLOAD_DIR" -type f -mtime +3 -delete
fi

prune_by_size() {
  dir="$1"
  [ -d "$dir" ] || return 0
  while :; do
    size_kb="$(du -sk "$dir" | awk '{print $1}')"
    [ "$size_kb" -le "$MAX_CACHE_KB" ] && break
    oldest="$(find "$dir" -type f -exec ls -t {} + 2>/dev/null | tail -n 1)"
    [ -n "$oldest" ] || break
    rm -f "$oldest"
  done
}

prune_by_size "$AUDIO_DIR"
prune_by_size "$UPLOAD_DIR"

echo "old voice cache cleaned"
