#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOME="${REMOTE_HOME:-/data/data/com.termux/files/home}"
REMOTE_DIR="${REMOTE_DIR:-$REMOTE_HOME/Petagent}"
TERMUX_UID="${TERMUX_UID:-}"
BUILD_FRONTEND="${BUILD_FRONTEND:-1}"
ARCHIVE="/tmp/petagent-deploy-$(date +%Y%m%d%H%M%S).tar.gz"
REMOTE_ARCHIVE="/data/local/tmp/$(basename "$ARCHIVE")"
INSTALL_SCRIPT="$(mktemp /tmp/petagent-install.XXXXXX.sh)"
REMOTE_INSTALL_SCRIPT="/data/local/tmp/$(basename "$INSTALL_SCRIPT")"

cleanup() {
  rm -f "$ARCHIVE" "$INSTALL_SCRIPT"
}
trap cleanup EXIT

if ! command -v adb >/dev/null 2>&1; then
  echo "adb not found" >&2
  exit 1
fi

cd "$PROJECT_DIR"

if [ "$BUILD_FRONTEND" = "1" ]; then
  (cd frontend && npm run build)
fi

if [ -z "$TERMUX_UID" ]; then
  TERMUX_UID="$(adb shell "dumpsys package com.termux | grep -m1 'userId=' | sed 's/.*userId=//; s/[^0-9].*//'" | tr -d '\r')"
fi

if [ -z "$TERMUX_UID" ]; then
  echo "Could not detect Termux uid" >&2
  exit 1
fi

echo "Packing deploy archive..."
COPYFILE_DISABLE=1 tar \
  --format=ustar \
  --exclude='.git' \
  --exclude='.pytest_cache' \
  --exclude='.venv' \
  --exclude='backend/.pytest_cache' \
  --exclude='backend/data' \
  --exclude='backend/secrets' \
  --exclude='backend/static/audio' \
  --exclude='backend/tests' \
  --exclude='frontend/.pytest_cache' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/src' \
  --exclude='plan' \
  -czf "$ARCHIVE" \
  .env.example README.md backend config frontend/dist frontend/index.html frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/vite.config.test.ts scripts

archive_size="$(du -h "$ARCHIVE" | awk '{print $1}')"
echo "Pushing $archive_size archive to Nubia..."
adb push "$ARCHIVE" "$REMOTE_ARCHIVE" >/dev/null

echo "Installing archive into $REMOTE_DIR..."
cat > "$INSTALL_SCRIPT" <<EOF
#!/system/bin/sh
set -eu
uid="$TERMUX_UID"
remote_dir="$REMOTE_DIR"
archive="$REMOTE_ARCHIVE"
export PATH="$REMOTE_HOME/../usr/bin:$REMOTE_HOME/../usr/bin/applets:/system/bin:/system/xbin:/su/bin"
export LD_LIBRARY_PATH="$REMOTE_HOME/../usr/lib"
export LD_PRELOAD="$REMOTE_HOME/../usr/lib/libtermux-exec-ld-preload.so"
mkdir -p "\$remote_dir"
cd "\$remote_dir"
mkdir -p backend/data backend/secrets backend/static/audio logs
tar -xzf "\$archive" -C "\$remote_dir"
find "\$remote_dir" -name '._*' -type f -delete 2>/dev/null || true
chown "\$uid:\$uid" "\$remote_dir" backend frontend logs 2>/dev/null || true
chown -R "\$uid:\$uid" .env.example README.md backend/app backend/requirements.txt backend/requirements-asr.txt backend/pytest.ini config frontend/dist frontend/index.html frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/vite.config.test.ts scripts
chmod 700 "\$remote_dir/scripts/start.sh" "\$remote_dir/scripts/stop.sh" 2>/dev/null || true
chmod 755 "\$remote_dir/scripts/termux_service_manager.sh" "\$remote_dir/scripts/termux_start_services.sh" 2>/dev/null || true
restorecon -R "\$remote_dir" 2>/dev/null || true
rm -f "\$archive" "$REMOTE_INSTALL_SCRIPT"
EOF
adb push "$INSTALL_SCRIPT" "$REMOTE_INSTALL_SCRIPT" >/dev/null
adb shell "su -c 'sh $REMOTE_INSTALL_SCRIPT'"

echo "Deploy complete."
echo "Note: adb-launched background processes do not stay alive reliably on this Nubia."
echo "Use the Termux boot/startup path, or run a foreground runtime for live tests."
