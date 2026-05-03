#!/data/data/com.termux/files/usr/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
AUDIO_DIR="$PROJECT_DIR/backend/static/audio"

if [ ! -d "$AUDIO_DIR" ]; then
  echo "audio cache does not exist"
  exit 0
fi

find "$AUDIO_DIR" -type f -mtime +3 -delete
echo "old audio cache cleaned"
