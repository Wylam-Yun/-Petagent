# V1.8 Termux:Boot Field Checklist

Use this checklist only for the Nubia Termux runtime path. Do not install APKs
or change phone boot behavior without explicit operator approval.

## Current Field State

- Termux package visible: `com.termux`
- Termux:Boot package visible: missing
- Termux package stopped state observed on 2026-06-01: `stopped=true`
- Existing boot script path: `~/.termux/boot/start-sshd.sh`
- Required service entry: `~/Petagent/scripts/termux_start_services.sh`

## Required Manual Setup

1. Install Termux:Boot from a signing source compatible with the installed
   Termux package.
2. Open Termux:Boot once from the Android launcher.
3. Open Termux once if Android still reports `com.termux` as stopped.
4. Confirm `~/.termux/boot/start-sshd.sh` delegates to:

   ```sh
   ~/.start_services.sh --termux-boot
   ```

5. Confirm `~/.start_services.sh` delegates to:

   ```sh
   ~/Petagent/scripts/termux_start_services.sh
   ```

## Checks

```bash
adb shell 'pm list packages | grep -i termux'
adb shell 'dumpsys package com.termux.boot 2>/dev/null | grep -E "Package \\[|versionName|stopped=|enabled=|userId=" | head -n 40'
adb shell 'dumpsys package com.termux | grep -E "versionName|stopped=|enabled=|userId=" | head -n 40'
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'id; cd ~/Petagent && scripts/termux_start_services.sh --status-only'
ssh nubia-adb 'cd ~/Petagent && scripts/status.sh'
```

Expected after setup:

- `pm list packages` includes `package:com.termux.boot`
- `dumpsys package com.termux.boot` shows installed and enabled
- `dumpsys package com.termux` does not show `stopped=true`
- SSH identity includes `3003(inet)`
- `scripts/status.sh` reports manager, wake lock, Termux:Boot, frontend
  heartbeat, watchdog, backend health, and database state clearly

## Reboot Validation Gate

Run reboot validation only after Termux:Boot is installed and opened once:

```bash
adb reboot
adb wait-for-device
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
```

If SSH does not return after reboot, manually open Termux on the phone and
capture:

```bash
cat ~/.boot_services.log
cat ~/.service_manager.log
cd ~/Petagent && scripts/status.sh
```
