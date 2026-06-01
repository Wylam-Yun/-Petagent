# V1.8 Termux Runtime Supervisor Validation

This file records field evidence for the Nubia Termux runtime supervisor plan.
Do not store runtime logs, audio, secrets, screenshots, or generated frontend
build output here.

## 2026-06-01 Read-Only Preflight

Local repo state:

- Local `main` and `origin/main` after the first validation note: `1236697`
- V1.8 Task 1-6 implementation commit range:
  - `f04e5b6` through `f6dbba7`
- Additional V1.8 wrapper regression test commit:
  - `7310fd5`
- V1.8 Task 1-6 commits were pushed.
- Local shell syntax checks passed for:
  - `scripts/start.sh`
  - `scripts/stop.sh`
  - `scripts/status.sh`
  - `scripts/termux_start_services.sh`
  - `scripts/termux_service_manager.sh`
- `backend/tests/test_phase1_startup.py`:
  - initial Task 1-6 check: `11 passed`
  - after adding V1.8 wrapper regression assertions: `15 passed`

Nubia connection:

- ADB device online: `9debb82b`, model `NX531J`
- `adb forward tcp:18022 tcp:8022` active
- SSH identity: `uid=10137(u0_a137)`, groups include `3003(inet)`

Deployment action performed:

- Copied the V1.8 runtime wrapper scripts to `~/Petagent/scripts/` over
  Termux SSH:
  - `scripts/status.sh`
  - `scripts/termux_start_services.sh`
  - `scripts/termux_service_manager.sh`
  - `scripts/start.sh`
- Copied `docs/operations.md` to `~/Petagent/docs/operations.md`.
- Rechecked the copied phone files against local files with SHA-256. These
  matched on 2026-06-01:
  - `scripts/status.sh`:
    `20826398e7401eb7fa1c29bc1cd1d11659fa8fdc43f8c4efb96e6d97c139da7a`
  - `scripts/termux_start_services.sh`:
    `be682d7045917ec4745408360ff9985ef0848bfcf3cea300d23850584939491e`
  - `scripts/termux_service_manager.sh`:
    `3c59c33957ff22834f8ad8dcf39f3ba853aad5873ca5e434726c196ec3d1ef76`
  - `scripts/start.sh`:
    `792c05531dc99db55a1b3ebe1f60cb2cc268b1393c512e834b054ad07a6b4d61`
  - `docs/operations.md`:
    `b825bc05456d3ecaae04ebee4b777909f3666aac685f209283d18c20fb7deb9d`
- Did not run `scripts/termux_start_services.sh --ensure`.
- Did not kill or restart uvicorn.
- Did not reboot the phone.
- Did not start backend or manager through `adb shell su` or root.

Read-only phone results:

- Existing backend stayed healthy:
  - `/api/health` returned `ok=true`
  - backend `build_hash`: `ec528f8`
  - backend pid: `14471`
- New `scripts/status.sh` ran successfully and reported:
  - `context: ok`
  - `manager: not running`
  - `manager_context: not running`
  - `sshd: listening`
  - `process: running (14471)`
  - `/api/health` ok
  - `frontend_heartbeat_age_s` about `26450.8`; repeat read-only check later
    showed about `26722.8`
  - `watchdog_stuck: false`
  - `database: ok`
- `scripts/status.sh` reported `wake_lock`, `termux_boot`, and
  `termux_package` as `unknown` from SSH because Android `dumpsys`/`pm` were
  unavailable there. This is allowed by the plan.
- ADB-side package/power checks showed:
  - `pm list packages | grep -i termux`: only `package:com.termux`
  - `com.termux.boot`: missing
  - `com.termux`: `stopped=true`
  - `mWakeLockSummary=0x0`
  - `Wake Locks: size=0`
- `scripts/termux_start_services.sh --status-only` ran successfully and
  returned:
  - `context: ok`
  - `sshd: listening`
  - `manager: not running`
  - `manager_context: not running`
  - `wake_lock: unknown`
  - `backend: healthy`
  - exit status `0`
- `ps` showed `uvicorn` and `sshd`, and no `termux_service_manager.sh`.

Gate status:

- Task 7 `--status-only` read-only validation: complete.
- Task 7 `--ensure`: pending explicit operator confirmation because it starts
  or confirms the manager and should acquire a wake lock.
- Task 8 destructive backend kill/reboot recovery: pending separate explicit
  confirmation.
- Task 10 five real Nubia web microphone attempts: pending after supervisor
  runtime validation.

## Remaining Validation Gates

These gates are intentionally not satisfied by the read-only preflight above.

### Task 7 Manager Ensure Gate

Required explicit operator approval:

- "Run Task 7 --ensure" or equivalent.

Allowed actions after approval:

- Run `scripts/termux_start_services.sh --ensure` only through `ssh nubia-adb`
  in the real Termux SSH context.
- Confirm `id` still includes `3003(inet)`.
- Confirm backend pid before and after `--ensure`.
- Inspect `scripts/status.sh`, `~/.service_manager.log`, `logs/manager.log`,
  `ps`, and ADB `dumpsys power`.

Forbidden actions in this gate:

- Do not kill uvicorn.
- Do not reboot.
- Do not use `adb shell su` or root to start backend or manager.
- Do not install Termux:Boot.

Evidence required to mark Task 7 complete:

- `scripts/status.sh` shows backend healthy.
- `scripts/status.sh` shows `manager: running (<pid>)`.
- `scripts/status.sh` shows `manager_context: ok`.
- `ps` shows exactly one `termux_service_manager.sh`.
- Backend pid is unchanged unless pre-check health was already bad.
- Wake lock is held, or manager logs explicitly explain why wake lock
  visibility cannot be verified.

### Task 8 Destructive Recovery Gate

Required explicit operator approval:

- "Run Task 8 destructive recovery" or equivalent.

Preconditions:

- Task 7 passed.
- Phone is plugged in or has enough battery.

Actions:

- 8A may kill the current backend pid once and wait for manager recovery.
- 8B may allow manager/browser relaunch behavior to run.
- 8C reboot recovery is optional and only valid after Termux:Boot is installed
  and opened once.

Forbidden actions without separate approval:

- Do not reboot.
- Do not install APKs.
- Do not manually start backend after a failed kill-recovery attempt until logs
  are captured.

### Task 10 Real Nubia Web Voice Gate

Required explicit operator approval:

- "Run Task 10 voice validation" or equivalent.

Preconditions:

- Task 7 passed.
- Nubia browser page is open at `http://127.0.0.1:8000/`.
- Browser microphone permission is available.
- Audible Mac `say` playback is acceptable.

Evidence required:

- Five ADB long-press microphone attempts from the real Nubia web page.
- Five screenshots pulled from the phone.
- `voice_debug.jsonl` evidence for the latest attempts.
- `recent_dialogue_turns` evidence for successful voice turns.
- `agent_run.final_action_json.expression_key` evidence.
- Screenshot expression compared with latest successful expression key.
