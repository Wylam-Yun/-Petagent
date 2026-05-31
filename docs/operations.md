# PetAgent / Momo Operations

This file records the V1.1 operator commands for the Nubia Android 6 + Termux
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

Start services manually after a phone reboot if SSH is not up:

```bash
sshd
~/.start_services.sh
```

## Frontend Recovery

The Termux manager relaunches the default browser when frontend heartbeat is
stale:

```bash
am start -a android.intent.action.VIEW -d http://127.0.0.1:8000/
```

V1.1 uses `FRONTEND_STARTUP_SECONDS=120` by default. Fully Kiosk or a WebView
shell is a later option, not required for V1.1.

## Proxy Supervision

The manager checks proxy port `7897` on every loop. If it is down and
`/data/local/tmp/start-proxy.sh` is executable, the manager tries to restart it.
Repeated proxy restart failures use `PROXY_BACKOFF_SECONDS` and do not change
the PetAgent runtime backoff counters.

Disable proxy autostart on the phone by creating:

```text
/data/local/tmp/.petagent_no_proxy_autostart
```

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
