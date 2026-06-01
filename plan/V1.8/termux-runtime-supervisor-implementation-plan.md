# V1.8 Termux Runtime Supervisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` or an equivalent step-by-step implementation loop. Steps use checkbox (`- [ ]`) syntax for tracking. Do not skip the Nubia field validation section.

**Goal:** Restore and harden the Nubia Termux supervisor path so PetAgent can recover its SSH service, backend runtime, wake lock, and frontend page without relying on manual browser or adb/root startup.

**Architecture:** Keep the current product architecture unchanged: FastAPI/SQLite runs inside Termux, React/Vite static frontend is served by the backend, and future shell APK/WebView work will depend on `http://127.0.0.1:8000/`. V1.8 only hardens the runtime wrapper scripts, observability, boot setup, and validation workflow around the existing backend. It must not change V1.7 context, memory, prompt, ASR, reset, or expression behavior.

**Tech Stack:** Android 6.0.1 Nubia NX531J, Termux `u0_a137`, shell scripts, FastAPI health endpoints already present, ADB USB, `adb forward`, `ssh nubia-adb`, pytest only for local script/static checks where useful.

---

## Current Field Facts From 2026-06-01

Repo path:

- `/Users/wylam/Documents/workspace/Petagent`

Nubia identity and runtime:

- `adb devices -l` shows one online device:
  - serial `9debb82b`
  - model `NX531J`
- `adb forward tcp:18022 tcp:8022` works.
- `ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'` currently reports:
  - `uid=10137(u0_a137)`
  - groups include `3003(inet)`
  - `context: ok`
  - backend process running, pid `14471`
  - `/api/health` ok with build hash `ec528f8`
  - database `quick_check` ok
- `ps` currently shows:
  - `uvicorn` runtime
  - `sshd`
  - no `termux_service_manager.sh`
- `dumpsys power` currently shows:
  - `mWakefulness=Asleep`
  - `mWakeLockSummary=0x0`
  - `Wake Locks: size=0`
  - `mDeviceIdleWhitelist` includes Termux uid `10137`
- `pm list packages | grep -i termux` currently shows only:
  - `package:com.termux`
  - no `com.termux.boot`
- `dumpsys package com.termux` currently shows:
  - `versionName=0.119.0-beta.2`
  - `User 0: installed=true hidden=false stopped=true notLaunched=false enabled=0`
- WebView package state from the app-shell assessment:
  - `com.google.android.webview`
  - `versionName=55.0.2883.91`
  - this is old; V1.8 must not depend on Capacitor or modern WebView features.

Important interpretation:

- The backend is currently healthy.
- The runtime supervisor is currently absent.
- The system has no active Termux wake lock.
- Existing boot scripts exist under `~/.termux/boot`, but Termux:Boot is not installed or not visible to Package Manager.
- The current state is stable enough for user testing. Do not disturb it until the validation phase explicitly calls for it.

## User Constraints

1. Project is currently more stable than before; do not casually touch running services.
2. First produce an implementation plan that is grounded in the phone state and project scripts.
3. Do not start backend with `adb shell su` or root.
4. Runtime service must run from the real Termux app network context with Android `inet` group `3003`.
5. Failure must be explicit. Do not report success unless field checks prove it.
6. Do not change V1.7 product behavior while doing runtime hardening.
7. Do not commit or deploy `frontend/dist`, `backend/data`, `backend/static/audio`, `backend/secrets`, uploads, or logs.

## Existing Runtime Script Map

- `scripts/start.sh`
  - Starts only the FastAPI/uvicorn runtime.
  - Refuses root by default.
  - Refuses non-Termux network context if Android `inet` group is missing.
  - Writes `backend/data/runtime.pid`.
  - Cleans duplicate uvicorn runtimes.
  - Does not start or check `termux_service_manager.sh`.
- `scripts/stop.sh`
  - Stops only uvicorn runtimes.
  - Removes `backend/data/runtime.pid`.
  - Does not stop, start, or restart `termux_service_manager.sh`.
- `scripts/status.sh`
  - Checks Termux network context.
  - Checks backend pid file and `/api/health`.
  - Checks SQLite database.
  - Does not report manager presence, wake lock state, boot package state, or frontend heartbeat.
- `scripts/termux_start_services.sh`
  - Intended boot/manual entry point from real Termux context.
  - Starts `sshd` if needed.
  - Installs legacy `~/.service_manager.sh` shim.
  - Starts `scripts/termux_service_manager.sh` if needed.
  - Current risk: `manager_is_running()` accepts a lock pid only if the process has `inet` group. Field logs show repeated “foreign service manager process ... without valid Termux network context” after 2026-05-30; this path needs careful validation from real Termux, not adb/root.
- `scripts/termux_service_manager.sh`
  - Intended long-running supervisor.
  - Acquires Termux wake lock via `termux-wake-lock`.
  - Checks proxy, sshd, backend process, backend port, `/api/health`, `/api/health/watchdog`.
  - Relaunches browser when `frontend_heartbeat_age_s > FRONTEND_STARTUP_SECONDS`.
  - Current risk: not running at the time of this plan.

## Problem Statement

V1.7 deployed and verified the core product behavior successfully, but the field state now shows that the backend can remain healthy while the outer supervisor layer is missing. This creates an operational gap:

- A manual `scripts/stop.sh && scripts/start.sh` over SSH restores uvicorn but does not restore manager.
- Without manager, there is no loop that restarts uvicorn on death or HTTP half-alive.
- Without manager, there is no loop that relaunches the browser when frontend heartbeat is stale.
- Without manager startup, `termux-wake-lock` is not held.
- Without Termux:Boot, phone reboot will not automatically run `~/.termux/boot/start-sshd.sh`.
- Because `com.termux` is currently `stopped=true`, boot/broadcast behavior must be checked on the phone rather than assumed from files alone.

The implementation must repair this without destabilizing the currently healthy backend and without changing the product runtime semantics.

## Non-Goals

- Do not build the Android shell APK in V1.8.
- Do not embed Python in an APK.
- Do not change backend prompt, memory, state, reset, ASR, expression, TTS, or frontend UI behavior.
- Do not replace Termux with adb/root startup.
- Do not add package-manager automation that silently installs APKs without an explicit user approval step.
- Do not run destructive validation such as killing backend or rebooting phone until the user explicitly confirms the validation stage.

## Desired End State

Normal state after V1.8:

- `uvicorn` is healthy in the real Termux network context.
- `sshd` is listening on Termux port `8022`.
- `termux_service_manager.sh` is running as Termux user `u0_a137` and has Android group `3003`.
- `dumpsys power` shows an active wake lock attributable to Termux or `termux-wake-lock`.
- `scripts/status.sh` reports manager, wake lock, boot package, health, watchdog, and database status clearly.
- Manual `scripts/stop.sh && scripts/start.sh` does not leave the system in a state where backend is healthy but manager is absent without surfacing that warning.
- `~/.termux/boot/start-sshd.sh` delegates to `~/.start_services.sh`, which delegates to repo `scripts/termux_start_services.sh`.
- If Termux:Boot is installed and opened once, a real phone reboot restores sshd, manager, backend, and frontend page.

## Implementation Overview

Implement in five stages:

1. Add observability without changing runtime behavior.
2. Make the service entry scripts idempotent and diagnosable.
3. Add a controlled local/phone setup checklist for Termux:Boot and wake lock.
4. Add non-disruptive live checks.
5. Run opt-in disruptive validation: backend kill recovery, frontend relaunch, and reboot recovery.

Each stage must preserve the current stable backend until the final validation stage.

---

## Task 1: Add A Runtime Supervisor Status View

**Purpose:** Make the current gap visible before changing behavior. `scripts/status.sh` should not say only “process running” when manager, wake lock, or boot path is absent.

**Files:**

- Modify: `scripts/status.sh`
- Test manually on Nubia through SSH.

**Required behavior:**

- Keep existing output fields:
  - `context`
  - backend `process`
  - `/api/health`
  - `database`
- Add fields:
  - `manager: running (<pid>)` or `manager: not running`
  - `manager_context: ok` only when manager process has group `3003`
  - `sshd: listening` or `sshd: not listening`
  - `wake_lock: held` or `wake_lock: not held`
  - `termux_boot: installed` or `termux_boot: missing`
  - `termux_package: stopped=<true|false|unknown>`
  - `frontend_heartbeat_age_s: <value>` from `/api/health/watchdog` if available
  - `watchdog_stuck: true|false|unknown`
- Status script must not start, stop, install, or restart anything.
- If Android commands such as `dumpsys` or `pm` are unavailable from SSH, print `unknown`, not failure.

**Implementation notes:**

- Reuse existing shell helpers:
  - `process_state`
  - `process_exists`
  - `has_android_inet_group`
- Add a `process_has_android_inet_group(pid)` helper using `/proc/$pid/status`, matching `termux_service_manager.sh`.
- Find manager with `/proc/[0-9]*/cmdline`, matching command lines containing:
  - `termux_service_manager.sh`
  - `.service_manager.sh`
- Check wake lock with:
  - `dumpsys power | grep -i 'Wake Locks'`
  - and a broader grep for `termux` if present
- Check Termux:Boot with:
  - `pm list packages | grep -qx 'package:com.termux.boot'`
- Check Termux stopped state with:
  - `dumpsys package com.termux | grep 'User 0:'`

**Verification:**

Run:

```bash
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'cd ~/Petagent && scripts/status.sh'
```

Expected before later tasks, based on current phone state:

```text
context: ok
process: running (...)
manager: not running
wake_lock: not held
termux_boot: missing
termux_package: stopped=true
```

The exact backend health JSON and database line should remain present.

**Commit boundary:**

```bash
git add scripts/status.sh plan/V1.8/termux-runtime-supervisor-implementation-plan.md
git commit -m "chore: expose termux supervisor status"
```

---

## Task 2: Add A Non-Disruptive Supervisor Entry Command

**Purpose:** Provide one safe command that starts or confirms the manager from the correct Termux context, without killing a healthy backend.

**Files:**

- Modify: `scripts/termux_start_services.sh`
- Optional modify: `docs/operations.md`

**Required behavior:**

- `scripts/termux_start_services.sh --status-only`
  - prints sshd, manager, wake lock, backend health summary
  - exits nonzero if called from a non-Termux `inet` context
  - does not start or stop anything
- `scripts/termux_start_services.sh --ensure`
  - current default behavior, but named explicitly
  - starts sshd if missing
  - starts manager if missing
  - never directly starts uvicorn from this script except through the manager loop
  - does not kill a healthy uvicorn just because manager was missing
- no-arg behavior remains compatible with boot script and should behave like `--ensure`.
- Add clear log lines to `~/.service_manager.log`:
  - command mode
  - current identity
  - manager candidate pid and group result
  - reason for refusing non-Termux context

**Engineering risk to address:**

Field logs show repeated manager launch attempts followed by:

```text
stopping foreign service manager process ... without valid Termux network context
WARNING service manager not confirmed after launch
```

The implementation must distinguish:

- current SSH session identity has `inet`
- manager process pid has `inet`
- adb/root launched process lacks `inet`
- stale lock points to dead/non-manager pid

If a newly launched manager is judged invalid, the status output must show why.

**Verification without disturbing backend:**

Run:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/termux_start_services.sh --status-only; echo status:$?'
```

Expected:

- If invoked from current `ssh nubia-adb`, identity should include `3003(inet)`.
- It should report manager missing.
- It should not start manager.

Then, only after user confirms:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/termux_start_services.sh --ensure; sleep 2; scripts/status.sh'
```

Expected:

- backend remains healthy
- manager becomes running
- no duplicate uvicorn runtime is created
- `~/.service_manager.log` records successful manager confirmation

**Commit boundary:**

```bash
git add scripts/termux_start_services.sh docs/operations.md plan/V1.8/termux-runtime-supervisor-implementation-plan.md
git commit -m "fix: make termux service entry diagnosable"
```

---

## Task 3: Harden Manager Wake Lock And Browser Relaunch Observability

**Purpose:** Keep manager behavior but make wake lock and browser relaunch failures visible, because this is the layer a shell APK will later depend on.

**Files:**

- Modify: `scripts/termux_service_manager.sh`
- Modify: `docs/operations.md`

**Required behavior:**

- `acquire_wake_lock()` must log:
  - whether `termux-wake-lock` exists
  - whether it returned success
  - a post-check summary if `dumpsys power` is available
- If wake lock is not visible after a successful command, log a warning.
- `ensure_browser()` must log:
  - heartbeat age
  - target URL
  - `am start` exit status
  - if `am` is missing/unavailable
- Do not change `FRONTEND_STARTUP_SECONDS` default in this task.
- Do not add an infinite browser relaunch loop faster than the existing manager cadence.
- Do not assume a particular browser package. Keep the generic `ACTION_VIEW` intent.

**Verification:**

After manager is running:

```bash
ssh nubia-adb 'cd ~/Petagent && tail -n 80 logs/manager.log'
adb shell 'dumpsys power | grep -i -E "Wake Locks|termux|mWakeLockSummary" | head -n 80'
ssh nubia-adb 'cd ~/Petagent && curl -fsS http://127.0.0.1:8000/api/health/watchdog'
```

Expected:

- manager log contains wake lock acquisition result
- `dumpsys power` shows wake lock held, or manager log explicitly says it could not verify it
- watchdog is reachable

**Commit boundary:**

```bash
git add scripts/termux_service_manager.sh docs/operations.md plan/V1.8/termux-runtime-supervisor-implementation-plan.md
git commit -m "chore: improve termux manager recovery logs"
```

---

## Task 4: Add A Deployment-Safe Supervisor Reminder

**Purpose:** Prevent the V1.7 pattern from recurring: `scripts/stop.sh && scripts/start.sh` leaves backend healthy but manager absent.

**Files:**

- Modify: `scripts/start.sh`
- Modify: `scripts/stop.sh` only if needed
- Modify: `docs/operations.md`

**Required behavior:**

- `scripts/start.sh` still starts only uvicorn.
- At the end of successful startup, if running on Android Termux and manager is absent, print:

```text
WARNING: PetAgent runtime is healthy but termux_service_manager.sh is not running.
Run scripts/termux_start_services.sh --ensure from the Termux app/SSH context to restore watchdog, wake lock, and browser recovery.
```

- Do not auto-start manager from `scripts/start.sh`; this avoids recursion and keeps the script focused.
- `scripts/stop.sh` should continue to stop only uvicorn. It should not stop manager unless a future explicit `--all` option is designed.
- Update operations docs to make the preferred manual recovery command:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/termux_start_services.sh --ensure'
```

and explain that:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/stop.sh && scripts/start.sh'
```

is backend-only and must be followed by supervisor status.

**Verification:**

Non-disruptive check:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/start.sh'
```

Expected if backend already healthy:

- It exits without restarting backend.
- It prints existing “already healthy” message.
- If manager absent, it also prints the supervisor warning.

**Commit boundary:**

```bash
git add scripts/start.sh scripts/stop.sh docs/operations.md plan/V1.8/termux-runtime-supervisor-implementation-plan.md
git commit -m "chore: warn when backend starts without supervisor"
```

---

## Task 5: Document And Gate Termux:Boot Setup

**Purpose:** Make boot recovery explicit and reproducible without assuming the package is installed.

**Files:**

- Modify: `docs/operations.md`
- Optional create: `plan/V1.8/termux-boot-field-checklist.md`

**Required documentation:**

- Explain that Termux:Boot is a separate package, not part of Termux.
- Explain that on the current Nubia field state `com.termux.boot` is missing.
- Explain that after installing Termux:Boot, the user must open it once from launcher so Android clears the stopped state and allows boot execution.
- Confirm expected boot script path:

```text
~/.termux/boot/start-sshd.sh
```

- Confirm current boot script should delegate:

```sh
~/.start_services.sh --termux-boot
```

- Confirm `~/.start_services.sh` should delegate to:

```sh
~/Petagent/scripts/termux_start_services.sh
```

- Include exact package checks:

```bash
adb shell 'pm list packages | grep -i termux'
adb shell 'dumpsys package com.termux.boot | grep -E "Package \\[|versionName|stopped=|enabled=|userId="'
adb shell 'dumpsys package com.termux | grep -E "versionName|stopped=|enabled=|userId=" | head -n 40'
```

- Include a warning that installing Termux:Boot from a mismatched signing source may require reinstalling Termux plugins. Do not automate this.

**Verification:**

No code verification required. This task is documentation and runbook.

**Commit boundary:**

```bash
git add docs/operations.md plan/V1.8/termux-runtime-supervisor-implementation-plan.md plan/V1.8/termux-boot-field-checklist.md
git commit -m "docs: add termux boot recovery checklist"
```

---

## Task 6: Local Static Checks

**Purpose:** Catch shell syntax regressions before touching phone state.

**Files:**

- Existing shell scripts only.

**Commands:**

Run from repo root:

```bash
sh -n scripts/start.sh
sh -n scripts/stop.sh
sh -n scripts/status.sh
sh -n scripts/termux_start_services.sh
sh -n scripts/termux_service_manager.sh
```

Expected:

- all commands exit `0`

Optional if available:

```bash
shellcheck scripts/start.sh scripts/stop.sh scripts/status.sh scripts/termux_start_services.sh scripts/termux_service_manager.sh
```

Expected:

- no critical issues; Android/Termux-specific portability warnings may be documented instead of fixed.

**Commit boundary:**

- No commit if no files changed.
- If shellcheck-driven fixes are made:

```bash
git add scripts/*.sh plan/V1.8/termux-runtime-supervisor-implementation-plan.md
git commit -m "chore: fix termux shell script lint"
```

---

## Task 7: Non-Disruptive Nubia Field Validation

**Purpose:** Validate supervisor startup without killing the current healthy backend.

**Precondition:**

- User confirms it is acceptable to start the manager.
- Do not reboot the phone in this task.
- Do not kill uvicorn in this task.

**Commands:**

```bash
adb devices -l
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'id'
ssh nubia-adb 'cd ~/Petagent && scripts/status.sh'
ssh nubia-adb 'cd ~/Petagent && scripts/termux_start_services.sh --status-only'
ssh nubia-adb 'cd ~/Petagent && scripts/termux_start_services.sh --ensure'
sleep 5
ssh nubia-adb 'cd ~/Petagent && scripts/status.sh'
ssh nubia-adb 'cd ~/Petagent && tail -n 100 ~/.service_manager.log 2>/dev/null || true'
ssh nubia-adb 'cd ~/Petagent && tail -n 100 logs/manager.log 2>/dev/null || true'
adb shell 'dumpsys power | grep -i -E "Wake Locks|termux|mWakeLockSummary|mDeviceIdleWhitelist" | head -n 100'
```

Expected:

- `id` includes `3003(inet)`.
- `scripts/status.sh` after `--ensure` shows:
  - backend healthy
  - manager running
  - manager context ok
  - sshd listening
  - wake lock held or explicit warning explaining why it cannot be verified
- `ps` shows exactly one `termux_service_manager.sh`.
- backend pid does not change unless it was unhealthy before the test.

Failure handling:

- If manager starts but is immediately judged “foreign” or without `inet`, stop. Do not keep retrying.
- Capture:

```bash
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh; tail -n 160 ~/.service_manager.log 2>/dev/null; tail -n 160 logs/manager.log 2>/dev/null'
adb shell 'ps -A -o pid,ppid,stat,args | grep -E "[t]ermux_service_manager|[u]vicorn|[s]shd"'
```

Then inspect before changing code.

---

## Task 8: Disruptive Recovery Validation

**Purpose:** Prove the restored manager actually recovers backend and frontend. This task must not run unless the user explicitly approves disruptive validation.

**Precondition:**

- Task 7 passed.
- User confirms it is okay to kill backend once and relaunch the phone browser.
- Phone has enough battery or is plugged in.

### 8A: Backend Process Death Recovery

Commands:

```bash
ssh nubia-adb 'cd ~/Petagent && old="$(cat backend/data/runtime.pid)"; echo old_pid:$old; kill "$old"; sleep 45; scripts/status.sh; echo new_pid:$(cat backend/data/runtime.pid 2>/dev/null || true)'
```

Expected:

- Manager detects missing process.
- New uvicorn pid appears.
- `/api/health` returns ok.
- `logs/manager.log` records process-not-running and restart.

Failure rule:

- If backend does not recover, do not manually run `scripts/start.sh` until logs are captured.

### 8B: Frontend Relaunch

Commands:

```bash
ssh nubia-adb 'cd ~/Petagent && curl -fsS http://127.0.0.1:8000/api/health/watchdog'
```

If `frontend_heartbeat_age_s` is greater than `FRONTEND_STARTUP_SECONDS`, wait one manager interval and inspect:

```bash
ssh nubia-adb 'cd ~/Petagent && sleep 35; tail -n 80 logs/manager.log; curl -fsS http://127.0.0.1:8000/api/health/watchdog'
```

Expected:

- Manager logs browser relaunch attempt.
- Phone displays PetAgent page, or logs show explicit `am start` failure.

### 8C: Optional Reboot Recovery

Do this only after Termux:Boot is installed and opened once.

Commands:

```bash
adb reboot
```

After device returns:

```bash
adb wait-for-device
adb devices -l
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
```

Expected:

- SSH returns without manually opening Termux.
- Manager is running.
- Backend is healthy.
- Wake lock is held or warning is explicit.
- Frontend page is launched if heartbeat was stale.

Failure rule:

- If SSH does not return after reboot, manually open Termux on the phone and capture:

```bash
cat ~/.boot_services.log
cat ~/.service_manager.log
cd ~/Petagent && scripts/status.sh
```

Then decide whether the issue is Termux:Boot installation/state or script behavior.

---

## Task 9: Final Runtime Supervisor Verification

**Commands:**

```bash
git status --short
git ls-files backend/data frontend/dist backend/static/audio backend/secrets logs
```

Expected:

- No runtime data, secrets, audio, or built frontend files staged/tracked by mistake.

Phone final status:

```bash
adb devices -l
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
ssh nubia-adb 'cd ~/Petagent && tail -n 80 logs/manager.log 2>/dev/null || true'
adb shell 'dumpsys power | grep -i -E "Wake Locks|termux|mWakeLockSummary|mDeviceIdleWhitelist" | head -n 100'
```

Record these fields for the final handoff after Task 10:

- whether Termux:Boot is installed
- whether Termux:Boot was opened once
- whether manager is running
- manager pid
- backend pid
- whether wake lock is visible
- whether frontend heartbeat is fresh or browser relaunch was attempted
- whether reboot validation was run
- any remaining manual phone setting needed

---

## Task 10: Real Nubia Web Voice Chain Regression

**Purpose:** After the supervisor work is stable, run the same real phone web microphone path used in V1.7 so runtime hardening does not accidentally break the user-facing voice loop or expression behavior.

**Precondition:**

- Task 7 passed.
- Backend is healthy on the deployed build.
- Nubia page is open at `http://127.0.0.1:8000/`.
- The browser has microphone permission.
- The phone is physically close enough to the Mac speaker that the Nubia microphone can record the Mac playback.
- User confirms it is acceptable to play audible test speech through the Mac speaker.

**Important distinction:**

- This task must not use direct `curl /api/voice/chat` upload as the main proof.
- The proof must come from the Nubia browser recording through the phone microphone.
- ADB is allowed only to simulate touch/long press and capture screenshots.

### 10A: Prepare Screen And Audio

Commands:

```bash
adb devices -l
adb forward tcp:18022 tcp:8022
adb forward tcp:18000 tcp:8000
curl -fsS http://127.0.0.1:18000/api/health
ssh nubia-adb 'cd ~/Petagent && scripts/status.sh'
osascript -e 'set volume output muted false' -e 'set volume output volume 80'
adb shell screencap -p /sdcard/petagent-before-voice.png
adb pull /sdcard/petagent-before-voice.png /private/tmp/petagent-v18-before-voice.png
```

Open `/private/tmp/petagent-v18-before-voice.png` and record the microphone button center coordinate. On the 1080x1920 Nubia screenshots from V1.7, the practical center was around `540 1650`, but do not hardcode it if the UI shifted.

Expected:

- Health is ok.
- Status script shows backend healthy and, after V1.8 work, manager status clearly.
- Screenshot shows the PetAgent page and the current expression before testing.

### 10B: Run Five Real Web Microphone Attempts

Use the measured button coordinate in the commands below. If the coordinate remains `540 1650`, the command form is:

```bash
say 'V1.8 真实网页语音链路第一轮测试123456789。' &
adb shell input swipe 540 1650 540 1650 4200
sleep 10
adb shell screencap -p /sdcard/petagent-v18-voice-1.png
adb pull /sdcard/petagent-v18-voice-1.png /private/tmp/petagent-v18-voice-1.png

say 'V1.8 真实网页语音链路第二轮测试123456789。' &
adb shell input swipe 540 1650 540 1650 4200
sleep 10
adb shell screencap -p /sdcard/petagent-v18-voice-2.png
adb pull /sdcard/petagent-v18-voice-2.png /private/tmp/petagent-v18-voice-2.png

say 'V1.8 真实网页语音链路第三轮测试123456789。' &
adb shell input swipe 540 1650 540 1650 4200
sleep 10
adb shell screencap -p /sdcard/petagent-v18-voice-3.png
adb pull /sdcard/petagent-v18-voice-3.png /private/tmp/petagent-v18-voice-3.png

say 'V1.8 真实网页语音链路第四轮测试123456789。' &
adb shell input swipe 540 1650 540 1650 4200
sleep 10
adb shell screencap -p /sdcard/petagent-v18-voice-4.png
adb pull /sdcard/petagent-v18-voice-4.png /private/tmp/petagent-v18-voice-4.png

say 'V1.8 真实网页语音链路第五轮测试123456789。' &
adb shell input swipe 540 1650 540 1650 4200
sleep 10
adb shell screencap -p /sdcard/petagent-v18-voice-5.png
adb pull /sdcard/petagent-v18-voice-5.png /private/tmp/petagent-v18-voice-5.png
```

If the first attempt uploads a file that is too small or ASR is empty because playback started too late, repeat the attempt with:

- Mac volume still at 80 or higher.
- Phone closer to speaker.
- `input swipe` duration increased to `5000`.
- `say ... & sleep 0.2; adb shell input swipe ...` if timing needs adjustment.

### 10C: Verify Backend Voice Logs

Commands:

```bash
ssh nubia-adb 'cd ~/Petagent && tail -n 10 backend/data/logs/voice_debug.jsonl'
ssh nubia-adb 'cd ~/Petagent && .venv/bin/python - <<'"'"'PY'"'"'
import json
from pathlib import Path

path = Path("backend/data/logs/voice_debug.jsonl")
rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
for row in rows[-5:]:
    route = row.get("voice_route", {})
    probe = row.get("audio_probe", {})
    print({
        "ok": row.get("ok"),
        "filename": row.get("filename"),
        "size_bytes": probe.get("size_bytes"),
        "format": probe.get("format"),
        "content_type": probe.get("content_type"),
        "user_text": row.get("user_text"),
        "selected": route.get("selected"),
        "thinking_mode": route.get("thinking_mode"),
        "asr_provider": route.get("asr_provider"),
        "brain_provider": route.get("brain_provider"),
        "error_class": row.get("error_class"),
    })
PY'
```

Expected for the latest five attempts:

- Five entries exist.
- Each entry has `event: voice_chat`.
- Upload sizes are plausibly non-empty voice recordings, not tiny accidental taps.
- `audio_probe.content_type` is `audio/webm` or the current frontend recording format.
- Successful ASR attempts have non-empty `user_text`.
- Successful route is `selected: unified`.
- `thinking_mode` is `false`.
- If ASR fails, failure is explicit:
  - `ok: false`
  - `error_class` or `asr_error_code` explains why
  - no fake LLM reply is generated for that failed turn.

### 10D: Verify Recent Voice Context And Expression State

Commands:

```bash
ssh nubia-adb 'cd ~/Petagent && .venv/bin/python - <<'"'"'PY'"'"'
from app.runtime.context_store import EventLogStore

store = EventLogStore("backend/data/pet.db")
turns = store.recent_dialogue_turns(limit=5)
for idx, turn in enumerate(turns, 1):
    print(idx, turn.get("event_type"), turn.get("source"), turn.get("user_text"), turn.get("pet_reply"))
PY'
```

Also inspect:

```bash
ssh nubia-adb 'cd ~/Petagent && .venv/bin/python - <<'"'"'PY'"'"'
import json
import sqlite3

con = sqlite3.connect("backend/data/pet.db")
con.row_factory = sqlite3.Row
rows = con.execute(
    "select run_id, final_action_json from agent_run where final_action_json is not null order by created_at desc limit 5"
).fetchall()
for row in rows:
    action = json.loads(row["final_action_json"])
    print(row["run_id"], action.get("expression_key"), action.get("mood"), action.get("reply"))
PY'
```

Expected:

- Successful voice turns enter `recent_dialogue_turns(limit=5)` as `voice_message`.
- `user_text` and `pet_reply` are non-empty for successful turns.
- Recent `agent_run.final_action_json.expression_key` is present for successful LLM turns.

Screenshot review:

- Open each of:
  - `/private/tmp/petagent-v18-before-voice.png`
  - `/private/tmp/petagent-v18-voice-1.png`
  - `/private/tmp/petagent-v18-voice-2.png`
  - `/private/tmp/petagent-v18-voice-3.png`
  - `/private/tmp/petagent-v18-voice-4.png`
  - `/private/tmp/petagent-v18-voice-5.png`
- Check the visible expression during/after the voice chain:
  - thinking phase may show `thinking`.
  - after the LLM response, the page should keep the latest `expression_key`.
  - after TTS playback finishes, the face must not automatically fall back to question mark or an unrelated placeholder.
- Compare the final visible expression with the latest successful `agent_run.final_action_json.expression_key`.

Failure handling:

- If the screenshot face and latest `expression_key` disagree, capture:

```bash
adb shell screencap -p /sdcard/petagent-v18-expression-mismatch.png
adb pull /sdcard/petagent-v18-expression-mismatch.png /private/tmp/petagent-v18-expression-mismatch.png
ssh nubia-adb 'cd ~/Petagent && tail -n 20 backend/data/logs/voice_debug.jsonl'
ssh nubia-adb 'cd ~/Petagent && .venv/bin/python - <<'"'"'PY'"'"'
import json
import sqlite3
con = sqlite3.connect("backend/data/pet.db")
con.row_factory = sqlite3.Row
for row in con.execute("select run_id, final_action_json from agent_run where final_action_json is not null order by created_at desc limit 10"):
    action = json.loads(row["final_action_json"])
    print(row["run_id"], action.get("expression_key"), action.get("reply"))
PY'
```

Do not mark V1.8 field validation complete until the expression mismatch is explained or fixed.

---

## Task 11: Final Handoff

**Purpose:** Summarize the runtime and real voice-chain state after all selected validation tasks.

Final handoff must state:

- git commit hash deployed on Nubia
- whether Termux:Boot is installed
- whether Termux:Boot was opened once
- whether reboot validation was run or deferred
- whether manager is running
- manager pid
- backend pid
- whether wake lock is visible
- whether frontend heartbeat is fresh or browser relaunch was attempted
- whether five real Nubia web microphone attempts passed
- latest five voice upload sizes and transcripts
- final visible expression from screenshot
- latest successful `agent_run.final_action_json.expression_key`
- whether screenshot expression and backend `expression_key` matched
- any remaining manual phone setting needed

Commands:

```bash
git status --short
git rev-parse --short HEAD
adb devices -l
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
ssh nubia-adb 'cd ~/Petagent && tail -n 5 backend/data/logs/voice_debug.jsonl'
```

Expected:

- No uncommitted runtime artifacts are included in git.
- Handoff explicitly says which disruptive validations were run and which were intentionally deferred.

---

## Implementation Risks And Mitigations

- **Risk: manager launch from SSH is still not the same as Termux app context.**
  - Mitigation: require `id` and process group `3003` checks for both shell and manager process.
- **Risk: adb/root started processes can appear to work but lack socket permissions.**
  - Mitigation: preserve existing refusal logic; do not use `adb shell su` to start backend or manager.
- **Risk: wake lock command succeeds but no wake lock is held.**
  - Mitigation: verify through `dumpsys power`; log “unverified” as warning.
- **Risk: Termux:Boot cannot be used because package is missing or signature mismatched.**
  - Mitigation: document manual install/open-once requirement; do not automate APK install in this plan.
- **Risk: default browser does not launch or old WebView cannot support the page.**
  - Mitigation: log `am start` result; future shell APK will replace browser but still depends on backend supervisor.
- **Risk: repeated manager restarts create duplicate uvicorn processes.**
  - Mitigation: Task 7 checks backend pid stability and exact manager count before disruptive testing.
- **Risk: current phone is stable and validation disrupts user testing.**
  - Mitigation: Tasks 1-6 are non-disruptive; Tasks 7-8 require explicit user confirmation.
- **Risk: supervisor fixes pass but the real browser microphone path regresses.**
  - Mitigation: Task 10 repeats five real Nubia web microphone attempts and checks upload logs, recent voice context, screenshots, and final expression consistency.

## Definition Of Done

V1.8 is complete only when:

- Status script surfaces manager, wake lock, Termux:Boot, frontend heartbeat, and watchdog state.
- Service entry script has explicit `--status-only` and `--ensure` modes.
- Manager wake lock and browser relaunch attempts are observable in logs.
- Backend-only `start.sh` warns when supervisor is missing.
- Operations docs explain the correct recovery path and Termux:Boot setup.
- Local shell syntax checks pass.
- Nubia non-disruptive validation passes.
- Disruptive recovery validation is either passed or explicitly deferred by the user.
- Five real Nubia web microphone attempts are run after runtime hardening, with screenshots reviewed for thinking/latest-expression behavior and no automatic question-mark fallback after TTS.
