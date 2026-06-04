# V2.0 Runtime Stability And Autostart Plan

## Goal

Make PetAgent runtime failures diagnosable before running the 100-round APK voice test. The voice test should not start until the Termux runtime, service manager, backend, wake lock, and SSH access are stable enough that voice failures are not confused with phone lifecycle failures.

## Current Facts

- PetAgent backend must run from the real Termux app context. Valid `id` output includes `3003(inet)`.
- `nubia-adb` uses ADB forward `127.0.0.1:18022 -> phone:8022`.
- LAN SSH is also available as `nubia` at `192.168.10.239:8022`; use it when ADB is unstable.
- `com.termux` and `com.termux.boot` can be moved into Android `stopped=true` state. When that happens, manager, sshd, uvicorn, and the Termux wake lock can all disappear together.
- Opening Termux from the launcher clears `com.termux stopped=true` and has restored sshd, manager, backend, and wake lock in field checks.
- Termux:Boot is installed, but if `com.termux.boot stopped=true`, reboot autostart remains risky.
- ADB attachment is only a debug transport. Reconnecting ADB and restoring forwards does not wake Termux, restart sshd, restart the manager, or restart FastAPI.
- 2026-06-04 field check: ADB was online but forwards were empty; `com.termux stopped=true`; no Termux wake lock was visible from ADB; `nubia-adb` SSH closed immediately; Mac `18000` returned empty replies. Opening Termux triggered `.bashrc -> ~/.start_services.sh`, which restored sshd, manager, backend, and wake lock.
- Termux on this Android 6 build cannot always inspect `dumpsys power`, `dumpsys package`, or `appops` from its own UID. Local scripts should report permission-denied visibility separately from real `not held`, `stopped=true`, or `ignore` states.

## Stop Conditions

Do not run the 100-round voice test if any of these are true:

- ADB is offline and LAN SSH is also unreachable.
- SSH `id` lacks `3003(inet)`.
- `scripts/status.sh` does not report manager running and backend health ok.
- `dumpsys power` does not show the Termux wake lock after manager startup.
- `com.termux.boot stopped=true` immediately before a reboot/autostart validation.
- The runtime stability monitor shows manager/backend restarts during the soak window.

## Implementation Tasks

1. Add manager heartbeat logging.
   - Log at a configurable interval, default 300 seconds.
   - Include manager pid, backend pid, backend check result, port states, wake lock status, frontend heartbeat age, and memory RSS.
   - Keep logs compact and rotate with existing `logs/manager.log` behavior.

2. Add runtime exit attribution.
   - When backend is missing, log the previous pid, whether `/proc/<pid>` still exists, runtime pid-file age, port state, and recent runtime log tail.
   - When HTTP is half-alive, log the same state before restart.
   - Do not use adb/root/su to run backend.

3. Add a Mac-side stability monitor.
   - Prefer LAN SSH host `nubia`; fall back to `nubia-adb`.
   - Preserve existing ADB forward behavior but do not treat missing forward as backend failure.
   - Write text-only NDJSON or log output under `plan/V2.0/runtime-monitor/`.
   - Record ADB state, SSH route used, package stopped states, wake lock, status output, health, build-info, and pid changes.

4. Add field test procedures.
   - 2-hour soak: no voice, one sample per minute.
   - Failure injection: kill backend pid and verify manager restart.
   - ADB interruption: unplug/replug or restart adb server; confirm LAN SSH and phone-local health continue.
   - Reboot validation: only with owner consent; confirm Termux:Boot log and backend health after boot.

## Success Criteria

- 2-hour soak produces no unexplained manager/backend disappearance.
- If backend pid is killed, manager restarts it and health returns within two manager cycles.
- ADB interruption does not get reported as backend downtime if LAN SSH or phone-local health remains ok.
- Before 100-round voice test, both `com.termux stopped=false` and `com.termux.boot stopped=false` are confirmed, manager is running, backend is healthy, and wake lock is held.

## Notes

- This plan does not move backend into the APK.
- This plan does not use adb/root/su as runtime support.
- The APK remains only a WebView shell and should continue using the existing `/api/voice/chat` path.
