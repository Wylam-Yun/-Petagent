# PetAgent / Momo Operations

This file records the operator commands for the Nubia Android 6 + Termux
runtime. Keep raw secrets out of logs, issues, and commits.

## Internal Token

Debug, internal, reset, and skill execution endpoints require the internal
token. By default it is stored at:

```text
backend/secrets/internal_token
```

The file is generated with mode `0600` and ignored by Git.

Use it locally:

```bash
TOKEN="$(cat backend/secrets/internal_token)"
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/health/deep
```

On Nubia:

```bash
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'TOKEN="$(cat ~/Petagent/backend/secrets/internal_token)" && curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/health/deep'
```

Rotate/re-pair:

```bash
TOKEN="$(cat backend/secrets/internal_token)"
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/debug/token/rotate
```

The rotate endpoint returns only a token fingerprint and the token file path.
After rotation, read the new token from `backend/secrets/internal_token`. If
`DEBUG_INTERNAL_TOKEN` is set, token rotation is disabled because the environment
variable is the source of truth.

Rejected protected requests are recorded as `auth_rejected` incidents with only
path, method, client host, and reason. Token values are not stored.

## Runtime Checks

Basic checks:

```bash
adb forward tcp:18022 tcp:8022
adb forward tcp:18000 tcp:8000
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
curl -fsS http://127.0.0.1:18000/api/health
ssh nubia-adb 'curl -sS --connect-timeout 2 --max-time 5 http://127.0.0.1:8000/api/health'
ssh nubia-adb 'curl -sS --connect-timeout 2 --max-time 5 http://127.0.0.1:8000/api/health/watchdog'
ssh nubia-adb 'ps -A -o pid,ppid,stat,args | grep -E "[t]ermux_service_manager|[u]vicorn|[s]shd"'
```

Watchdog fields to inspect during V1.1 validation:

- `provider_inflight_age_s`
- `agent_inflight_age_s`
- `audio_queue_depth`
- `frontend_heartbeat_age_s`
- `stuck`

`scripts/status.sh` is read-only. It reports backend health, manager state,
manager Android `inet` group state, sshd, wake lock visibility, Termux:Boot
package presence, Termux stopped state, vendor force-stop risk, frontend
heartbeat age, watchdog stuck state, and SQLite quick check.

`termux_package: stopped=true` is not proof that the current backend is down.
If SSH, the manager, and `http://127.0.0.1:8000/api/health` are live, treat it
as a boot/broadcast/vendor-policy risk. `termux_vendor_force_stop_risk` exists
to keep that risk visible without mixing it into the live backend health
decision.

Preferred manual recovery from a real Termux app or Termux SSH context:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/termux_start_services.sh --ensure'
ssh nubia-adb 'cd ~/Petagent && scripts/status.sh'
```

Use the status-only entry when you need a non-disruptive check:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/termux_start_services.sh --status-only'
```

Do not start the backend through `adb shell su` or root. Android socket
permission requires the real Termux app identity with group `3003(inet)`.

`scripts/stop.sh && scripts/start.sh` is backend-only. It does not start or stop
`termux_service_manager.sh`, and it must be followed by supervisor status:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/stop.sh && scripts/start.sh && scripts/status.sh'
```

Start services manually in Termux after a phone reboot if SSH is not up:

```bash
sshd
~/.start_services.sh --ensure
```

The current V1.8 field state on the Nubia showed backend healthy while
`termux_service_manager.sh` was absent, no active Termux wake lock was visible,
`com.termux.boot` was missing, and `com.termux` had `stopped=true`. Treat those
as runtime facts to verify on the phone rather than assumptions.

## APK Shell Recovery

The Android WebView shell checks `http://127.0.0.1:8000/api/health` before
loading the frontend. If health is unavailable, the APK shows a native recovery
screen, launches Termux, returns to the APK after a short delay, and keeps
polling health for about a minute. The screen also keeps manual "open Termux"
and retry controls for the worst case.

This is recovery, not system-level persistence. A normal APK cannot grant
Termux "highest priority" residency or prevent Nubia NeoSafe/vendor battery
management from force-stopping Termux. Termux:Boot, Termux wake lock, battery
whitelisting, auto-start permission, and background protection are still
device-policy requirements. A Termux wake lock helps sleep behavior but does
not override a vendor force-stop.

The frontend also exposes two local management controls:

- `重新认识`: clears runtime memory/state after confirmation.
- `重启后端`: calls loopback-only `POST /api/runtime/restart`, returns
  immediately, then restarts through the existing Termux `scripts/stop.sh` and
  `scripts/start.sh` path. It requires the backend to still be reachable; if
  the backend is already down, use the APK recovery screen or open Termux.

## Termux:Boot Setup

Termux:Boot is a separate package, not part of Termux. On the current Nubia
field state, `pm list packages | grep -i termux` showed `com.termux` only, so
boot recovery cannot be assumed until `com.termux.boot` is installed and opened
once from the launcher. Opening it once clears Android's stopped state so boot
broadcasts can run.

Expected boot script path:

```text
~/.termux/boot/start-sshd.sh
```

Expected delegation:

```sh
~/.start_services.sh --termux-boot
```

`~/.start_services.sh` should delegate to:

```sh
~/Petagent/scripts/termux_start_services.sh
```

Package and stopped-state checks:

```bash
adb shell 'pm list packages | grep -i termux'
adb shell 'dumpsys package com.termux.boot 2>/dev/null | grep -E "Package \\[|versionName|stopped=|enabled=|userId=" | head -n 40'
adb shell 'dumpsys package com.termux | grep -E "versionName|stopped=|enabled=|userId=" | head -n 40'
```

Installing Termux:Boot from a mismatched signing source may require reinstalling
Termux plugins. Do not automate Termux:Boot installation from this repo; confirm
the signing source and install/open-once step explicitly on the phone.

## Frontend Recovery

The Termux manager relaunches the default browser when frontend heartbeat is
stale:

```bash
termux-am start -a android.intent.action.VIEW -d http://127.0.0.1:8000/
```

If the Termux `am` socket is unavailable, the manager falls back to the legacy
`am` wrapper and records the exact exit code/output. On the current Nubia field
state, `termux-am` reported a missing socket and the legacy wrapper aborted
because `$PREFIX/libexec/termux-am/am.apk` was absent. For validation only, ADB
can still open the page:

```bash
adb shell am start -a android.intent.action.VIEW -d http://127.0.0.1:8000/
```

V1.1 uses `FRONTEND_STARTUP_SECONDS=120` by default. Fully Kiosk or a WebView
shell is a later option, not required for V1.1.

## API Network Path

External LLM, ASR, and TTS API calls are direct HTTPS requests from the real
Termux app context. The manager no longer starts or supervises a local API
proxy.

## Logs

Primary logs:

- manager: `~/Petagent/logs/manager.log`
- manager old rotation: `~/Petagent/logs/manager.log.old`
- runtime launcher: `~/.petagent_runtime_manager.log`
- backend runtime: `~/Petagent/backend/data/logs/runtime.log`
- backend runtime old rotation: `~/Petagent/backend/data/logs/runtime.log.old`

Manager logs rotate at `MAX_LOG_SIZE` bytes. Backend runtime logs rotate from
the maintenance worker at 512KB by default using a streaming copy suitable for
low-memory Android 6 devices.

## Live API Suite

Run from Nubia after deployment:

```bash
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'cd ~/Petagent/backend && PETAGENT_TEST_URL=http://127.0.0.1:8000 PETAGENT_INTERNAL_TOKEN_FILE=../backend/secrets/internal_token ../.venv/bin/python -m pytest tests/test_live_nubia.py -q'
```

The live suite covers ten V1.1 scenarios: light health, watchdog, public client
config, frontend heartbeat, pet state/interactions, text chat/audio job polling,
pet event dispatch, debug runs/incidents with token, deep health with token, and
protected endpoint rejection without token.
