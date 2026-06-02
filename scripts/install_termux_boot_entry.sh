#!/data/data/com.termux/files/usr/bin/sh
set -eu

HOME_DIR="${HOME_DIR:-${HOME:-/data/data/com.termux/files/home}}"
PREFIX_DIR="${PREFIX_DIR:-/data/data/com.termux/files/usr}"
PROJECT_DIR="${PROJECT_DIR:-$HOME_DIR/Petagent}"
BOOT_DIR="$HOME_DIR/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/start-sshd.sh"
START_SERVICES_SH="$HOME_DIR/.start_services.sh"

export HOME="$HOME_DIR"
export PREFIX="$PREFIX_DIR"
export PATH="$PREFIX_DIR/bin:$PREFIX_DIR/bin/applets:/system/bin:/system/xbin:/su/bin"

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

if [ -d "$PREFIX_DIR" ] && ! has_android_inet_group; then
  echo "context: not Termux app network context" >&2
  echo "context_detail: $(android_identity_summary)" >&2
  echo "hint: install boot entries from Termux or Termux SSH, not adb/su" >&2
  exit 1
fi

if [ ! -x "$PROJECT_DIR/scripts/termux_start_services.sh" ]; then
  echo "ERROR: missing executable $PROJECT_DIR/scripts/termux_start_services.sh" >&2
  exit 1
fi

mkdir -p "$BOOT_DIR"

cat > "$START_SERVICES_SH" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
exec "$HOME/Petagent/scripts/termux_start_services.sh" "$@"
EOF

cat > "$BOOT_SCRIPT" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
exec "$HOME/.start_services.sh" --termux-boot
EOF

chmod 700 "$START_SERVICES_SH" "$BOOT_SCRIPT"

echo "context: ok"
echo "termux_boot: $(termux_boot_status)"
echo "start_services_entry: $START_SERVICES_SH"
echo "boot_entry: $BOOT_SCRIPT"
