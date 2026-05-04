#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
AUDIO_DIR="$PROJECT_DIR/backend/static/audio"
UPLOAD_DIR="$PROJECT_DIR/backend/data/uploads"

if [ -d "$AUDIO_DIR" ]; then
  find "$AUDIO_DIR" -type f -mtime +3 -delete
fi

if [ -d "$UPLOAD_DIR" ]; then
  find "$UPLOAD_DIR" -type f -mtime +3 -delete
fi

echo "old voice cache cleaned"
