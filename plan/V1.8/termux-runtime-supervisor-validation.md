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

## 2026-06-01 Task 7 Non-Disruptive Ensure Validation

Pre-check evidence:

- ADB device online: `9debb82b`, model `NX531J`
- SSH identity: `uid=10137(u0_a137)`, groups include `3003(inet)`
- Pre-check backend pid: `14471`
- Pre-check backend health: `ok=true`, `build_hash=ec528f8`
- Pre-check manager: not running
- `scripts/termux_start_services.sh --status-only`: exit `0`, backend healthy

First `--ensure` attempt:

- Result: failed with exit status `1`
- Backend pid stayed `14471`
- `scripts/status.sh` still showed backend healthy and manager not running
- Failure evidence from `~/.service_manager.log`:
  - manager candidate pid `29421`
  - uid `10137`
  - `manager=yes`
  - `inet=missing_3003`
  - process was stopped as invalid
- Follow-up probe showed a normal SSH child process had:
  - `Groups: 3003 9997 10137 50137`
- Root cause: `/proc/$pid/status` on Android used a tab after `Groups:`, and
  the V1.8 parser only matched space-delimited groups. This made a valid
  manager process look like it lacked group `3003`.

Fix applied:

- Commit `57e53ca`: `fix: parse tabbed android process groups`
- Updated and redeployed:
  - `scripts/status.sh`
  - `scripts/termux_start_services.sh`
  - `scripts/termux_service_manager.sh`
- Phone SHA-256 after redeploy:
  - `scripts/status.sh`:
    `5c846e1d3bb59a1536c54530468ec5cd073095c6b335f9a3a4348b2db1e2caea`
  - `scripts/termux_start_services.sh`:
    `8385f65013f6cb36d0ad3d4ad922cbda2554a796ac52f1248987ca4a0f827e5c`
  - `scripts/termux_service_manager.sh`:
    `647af593f470b23f5e1a18b2fde4313579b14e97b9acf4bc879943eeb57df6bc`
- Local verification after fix:
  - `backend/tests/test_phase1_startup.py`: `15 passed`
  - `sh -n` passed for the five runtime shell scripts

Second `--ensure` attempt:

- Command: `scripts/termux_start_services.sh --ensure`
- Result: exit status `0`
- Backend pid stayed `14471`
- `scripts/status.sh` after ensure:
  - `context: ok`
  - `manager: running (5091)`
  - `manager_context: ok`
  - `sshd: listening`
  - `process: running (14471)`
  - `/api/health`: `ok=true`, `build_hash=ec528f8`
  - `frontend_heartbeat_age_s`: about `29107.1`
  - `watchdog_stuck: false`
  - `database: ok`
- Process check:
  - exactly one `termux_service_manager.sh`
  - manager pid `5091`
  - backend pid `14471`
  - sshd listening on `8022`
- `~/.service_manager.log` showed:
  - command mode `ensure`
  - current identity included `3003(inet)`
  - manager candidate pid `5091`, uid `10137`, `manager=yes`, `inet=ok`
  - `service manager confirmed running`

Manager findings after Task 7:

- `logs/manager.log` showed:
  - `Service manager started with PID 5091`
  - `termux-wake-lock command found`
  - `WARNING: termux-wake-lock returned non-zero`
  - `WARNING: dumpsys power returned no wake lock summary`
  - frontend heartbeat stale, browser relaunch attempted
  - `Browser relaunch am start exit=134 output=`
- ADB power check still showed:
  - `mWakeLockSummary=0x0`
  - `Wake Locks: size=0`
- ADB package check still showed:
  - only `package:com.termux`
  - `com.termux.boot` missing
  - `com.termux` `stopped=true`

Task 7 status:

- Supervisor startup validation: passed.
- Backend stability during Task 7: passed, pid stayed `14471`.
- Wake lock: not held; manager log explicitly records `termux-wake-lock`
  failure.
- Browser relaunch observability: passed; relaunch attempt is logged, but
  `am start` currently exits `134`.

## 2026-06-01 Termux App And Browser Relaunch Diagnostics

Follow-up app state check:

- Opened Termux once with `adb shell monkey -p com.termux 1`.
- `dumpsys package com.termux` then showed:
  - `versionName=0.119.0-beta.2`
  - `User 0: installed=true hidden=false stopped=false notLaunched=false enabled=0`
- This cleared the Android stopped state for Termux, but did not fix wake lock
  or Termux-side browser launch.

Wake lock evidence:

- `termux-wake-lock` from Termux SSH still returned `Aborted`, exit status
  `134`.
- ADB `dumpsys power` still showed:
  - `mWakeLockSummary=0x0`
  - `Wake Locks: size=0`
- `logs/manager.log` continued to make this explicit:
  - `termux-wake-lock command found`
  - `WARNING: termux-wake-lock returned non-zero`

Browser relaunch root cause evidence:

- `termux-am start -a android.intent.action.VIEW -d http://127.0.0.1:8000/`
  returned:
  - `Could not connect to socket: No such file or directory`
  - exit status `1`
- `am start ...` from Termux returned exit status `134`.
- `adb logcat` for the Termux `am` wrapper showed:
  - `ClassLoader referenced unknown path: /data/data/com.termux/files/usr/libexec/termux-am/am.apk`
  - `ERROR: could not find class 'com.example.termuxam.Am'`
  - fatal `SIGABRT`
- `/system/bin/am start ...` from Termux returned `Can't connect to activity
  manager; is the system running?`
- ADB-side `adb shell am start -a android.intent.action.VIEW -d
  http://127.0.0.1:8000/` remains usable for field validation, but is not a
  manager runtime path.

Follow-up script hardening:

- Added browser relaunch command diagnostics in `scripts/termux_service_manager.sh`:
  - try `termux-am` first and log socket failure explicitly
  - fall back to `am`
  - log the `am` command path
  - warn if `$PREFIX/libexec/termux-am/am.apk` is missing
  - log empty-stderr `am` aborts as a logcat investigation hint
- Added a `/proc/$pid/cmdline` readability guard in:
  - `scripts/status.sh`
  - `scripts/termux_start_services.sh`
  - `scripts/termux_service_manager.sh`
  This avoids noisy redirection errors when a manager pid exits between process
  discovery and cmdline inspection.
- Local verification:
  - `sh -n` passed for the five runtime shell scripts
  - `backend/tests/test_phase1_startup.py`: `15 passed`
- Phone SHA-256 after redeploy:
  - `scripts/status.sh`:
    `b83542b9297d1e26ce30376296bd3945c57db4bb7c7787a42833af670e4c26bf`
  - `scripts/termux_start_services.sh`:
    `3b35ed2e963d8e690cf499b1cb083616aa157916726ca33ec88606171cbac176`
  - `scripts/termux_service_manager.sh`:
    `0175df0dbec731fae1542382bdd36b2e4ddec3934b9571a4cb025d82e62f71d4`
  - `docs/operations.md`:
    `590c7270c7898f98364239b36d6039bd2582a801bd88febca56d5d7ffeabdcaf`

Post-deploy manager evidence:

- Backend pid stayed `14471`.
- Manager remained running in the real Termux SSH context with `3003(inet)`.
- New `logs/manager.log` entries showed:
  - `Browser relaunch termux-am start exit=1 output=Could not connect to socket: No such file or directory`
  - `WARNING: termux-am socket unavailable; open Termux and enable its am socket server, or use adb am only for field validation`
  - `Browser relaunch am command path=/data/data/com.termux/files/usr/bin/am`
  - `Browser relaunch am start exit=134 output=`
  - `WARNING: am start failed with empty stderr; check adb logcat for Termux am wrapper or ActivityManager access errors`
