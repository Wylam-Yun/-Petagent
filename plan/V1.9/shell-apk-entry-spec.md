# V1.9 Shell APK Entry Spec

## Goal

Add a second daily-use entry for PetAgent on the Nubia phone: a small native
Android APK that opens the existing local web app in a WebView.

The existing browser entry stays valid:

```text
http://127.0.0.1:8000/
```

The APK is only an entry shell. It must not move the backend out of Termux,
must not embed Python, and must not replace the V1.8 Termux manager.

## Current Project Facts

Repo:

- `/Users/wylam/Documents/workspace/Petagent`

Runtime architecture:

- Backend: FastAPI served from Termux on port `8000`.
- Frontend: React/Vite build served by the FastAPI backend from
  `frontend/dist`.
- Voice upload: `frontend/src/pet/api.ts` posts `FormData` to
  `/api/voice/chat`.
- Voice recording: `frontend/src/pet/audio.ts` tries `MediaRecorder`, then
  falls back to a WAV recorder built with Web Audio.
- Voice button: `frontend/src/components/VoiceButton.tsx` is click-to-record:
  tap once to start, tap once to send.
- Frontend heartbeat: `frontend/src/App.tsx` posts to
  `/api/frontend/heartbeat` every 30 seconds while online.
- Health endpoints:
  - `/api/health`
  - `/api/health/watchdog`
- Voice debug evidence is written by `backend/app/api/voice.py` to
  `backend/data/logs/voice_debug.jsonl`.
- Successful voice turns are stored as `voice_message` and are eligible for
  recent-dialogue context.
- Latest model expression evidence is in `agent_run.final_action_json`.

V1.8 runtime facts:

- V1.8 validation is recorded in
  `plan/V1.8/termux-runtime-supervisor-validation.md`.
- The backend death recovery validation passed: manager restored uvicorn after
  the backend pid was killed once.
- Five real Nubia web microphone turns passed through the real phone browser:
  `voice_chat`, `audio/webm`, `selected=unified`,
  `thinking_mode=false`, non-empty ASR text, and valid file sizes.
- Final V1.8 expression validation passed: latest backend
  `expression_key=happy` matched the phone display and did not revert to the
  question-mark fallback after TTS.
- Known V1.8 limitations remain:
  - Termux:Boot was still missing.
  - `termux-wake-lock` returned non-zero / `Aborted`; ADB `dumpsys power`
    did not show an active wake lock.
  - Termux-side browser relaunch via `termux-am`/`am` failed; ADB `am start`
    worked only as a field-validation assist.

Initial V1.9 draft preflight:

- `adb devices -l` showed no online device.
- `adb forward --list` was empty.
- `curl http://127.0.0.1:18000/api/health` could not connect because
  no ADB forward exists.
- Mac build tooling is not ready yet:
  - `java` reports no installed Java Runtime.
  - `gradle` is not installed.
  - `~/Library/Android/sdk` was not found.

2026-06-01 Nubia recheck:

- ADB is online:
  - serial `9debb82b`
  - model `NX531J`
  - Android `6.0.1`, SDK `23`
- ADB forwards were restored:
  - `9debb82b tcp:18000 tcp:8000`
  - `9debb82b tcp:18022 tcp:8022`
- `ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'` works from real
  Termux SSH context:
  - uid `10137(u0_a137)`
  - groups include `3003(inet)`
  - `context: ok`
  - `manager: running`
  - `manager_context: ok`
  - backend health `ok=true`, build hash `ec528f8`
  - `database: ok`
- `curl -fsS http://127.0.0.1:18000/api/health` works.
- `curl -fsS http://127.0.0.1:18000/build-info.json` works and reports
  `git_sha=ec528f8`.
- System WebView is still:
  - package `com.google.android.webview`
  - version `55.0.2883.91`
- Termux:Boot is still missing; `pm list packages | grep -i termux` shows
  only `package:com.termux`.
- Wake lock is still not held:
  - `mWakeLockSummary=0x0`
  - `Wake Locks: size=0`
- `dumpsys package com.termux` still reports `stopped=true` even though SSH,
  manager, and backend processes are currently running. Treat package stopped
  state as a boot/broadcast risk, not as proof that the current backend is
  down.
- Mac build tooling is still missing:
  - no Java Runtime
  - no `gradle`
  - no discovered `~/Library/Android/sdk`

## Problem Statement

The V1.8 runtime supervisor made the Termux backend more recoverable, but the
user-facing entry is still fragile:

1. A browser tab can be closed, backgrounded, or lose microphone permission.
2. The V1.8 manager cannot reliably relaunch the browser from Termux because
   Termux-side `am` tooling is broken on the phone.
3. The phone's old browser/WebView stack makes modern wrapper frameworks risky.
4. If the backend is not available, the user needs a clear failure screen and a
   retry path rather than a blank page.

The APK should solve the entry problem while leaving the backend runtime in the
Termux context that already has the required Android `inet` group.

## Non-Goals

- Do not replace the browser entry.
- Do not start FastAPI from the APK.
- Do not embed Python or copy the backend into the APK.
- Do not access Termux private files directly from the APK.
- Do not use adb, root, or `su` from the APK.
- Do not create a new voice API path.
- Do not duplicate React business logic in native Android.
- Do not introduce Capacitor, Cordova, React Native, or another large wrapper.
- Do not claim boot recovery, wake-lock recovery, or manager recovery as fixed
  by this APK.
- Do not commit generated APKs, Android build outputs, runtime logs,
  `frontend/dist`, `backend/data`, `backend/static/audio`,
  `backend/secrets`, uploaded audio, or logs.

## Recommended Approach

Build a minimal native Android WebView shell in a new independent directory:

```text
android-shell/
  settings.gradle
  build.gradle
  gradlew
  gradle/wrapper/...
  app/
    build.gradle
    src/main/AndroidManifest.xml
    src/main/java/.../MainActivity.java
```

Use Java for the first version. This avoids Kotlin plugin setup risk and keeps
the APK understandable on an older Android device.

Target the old Nubia directly:

- minSdk: 23
- compileSdk: installed Android SDK version from the local machine
- app target URL: `http://127.0.0.1:8000/`
- backend health URL: `http://127.0.0.1:8000/api/health`
- no cleartext network host except loopback

## APK Responsibilities

The APK should:

1. Show a native loading screen while checking `/api/health`.
2. Load `http://127.0.0.1:8000/` in WebView when health is OK.
3. Show a native unavailable screen when the backend is not reachable.
4. Provide a retry button that reruns the health check and reloads WebView.
5. Request Android `RECORD_AUDIO` permission.
6. Grant WebView microphone permission only for loopback origin
   `http://127.0.0.1:8000`.
7. Keep the screen on while the activity is visible.
8. Enable JavaScript, DOM storage, media playback without user gesture, and
   WebView settings needed by the existing React frontend.
9. Keep file access disabled unless a later validated need appears.
10. Surface load failures explicitly instead of showing a blank page.
11. In debug builds only, accept a loopback health URL override through an ADB
    intent extra so the unavailable screen can be validated without stopping
    the Termux backend.

The APK may later add:

- A small foreground notification that reminds the user Termux backend must be
  running.
- A button that opens Termux through Android package launch intent.
- A debug screen showing `/api/health`, `/api/health/watchdog`, and WebView
  user agent.

Those are optional and not required for the first V1.9 pass.

## Permission And Security Rules

Manifest permissions:

- `android.permission.INTERNET`
- `android.permission.RECORD_AUDIO`
- `android.permission.WAKE_LOCK` only if the APK later needs its own wake lock.
  First pass should use `FLAG_KEEP_SCREEN_ON`, not a background wake lock.

WebView permission policy:

- Implement `WebChromeClient.onPermissionRequest`.
- Only grant `PermissionRequest.RESOURCE_AUDIO_CAPTURE`.
- Only grant it when `request.getOrigin()` parses as loopback:
  - `http://127.0.0.1:8000`
- Deny camera, MIDI, protected media, unknown resources, and non-loopback
  origins.

Network policy:

- Allow cleartext HTTP only for loopback.
- Do not open LAN hosts or arbitrary URLs by default.
- External navigation should either stay inside the local WebView URL or be
  blocked with an explicit message.
- On Android 6 era devices, `network_security_config` is not enough by itself.
  The runtime enforcement must also live in `WebViewClient` URL checks and
  `WebChromeClient` permission-origin checks.
- `WebViewClient.shouldInterceptRequest()` must block non-loopback subresource
  requests as well as main-frame navigation. A main-frame URL allowlist alone
  is not sufficient.

## Data Flow

Normal APK startup:

1. User opens PetAgent APK.
2. `MainActivity` checks `http://127.0.0.1:8000/api/health`.
3. If health succeeds, WebView loads `http://127.0.0.1:8000/`.
4. Existing React app runs unchanged.
5. Existing heartbeat posts to `/api/frontend/heartbeat`.
6. Existing voice button records through WebView microphone APIs.
7. Existing frontend uploads to `/api/voice/chat`.
8. Existing backend runs ASR -> unified LLM -> TTS.
9. Existing frontend displays latest `expression_key` and plays TTS.

Backend unavailable flow:

1. Health check fails or WebView main-frame load fails.
2. Native unavailable screen appears.
3. The screen says the local backend is not reachable and asks the user to open
   Termux/start services.
4. Retry button reruns health check.
5. No fake reply, no fake pet state, no generated audio.

Preferred validation flow for the unavailable screen:

1. Keep the real Termux backend running.
2. Launch the debug APK with `petagent_debug_health_url` set to an unused
   loopback port.
3. Confirm the unavailable screen appears.
4. Relaunch normally and confirm the web app loads.

Stopping the backend is a disruptive fallback validation only. Because the
V1.8 manager may restart uvicorn quickly, a stop/start validation is also more
race-prone than the debug health override.

## Compatibility Constraints

Nubia field facts force a conservative APK:

- Device model from V1.8: Nubia NX531J.
- Android generation: Android 6 era.
- System WebView from V1.8 assessment:
  `com.google.android.webview` version `55.0.2883.91`.
- Existing frontend already uses Vite legacy output targeting Android 6 and
  Chrome 49.
- Capacitor v7 is not appropriate for the first pass because its WebView
  expectations are newer than this device state.

The first APK should use only basic AndroidX-free or low-dependency Android
APIs when possible. If Gradle or Android plugin versions require newer Java or
SDK tooling, the plan must make that explicit before implementation.

## Testing Requirements

Local checks:

- `git status --short` before and after.
- Confirm no runtime artifacts are tracked.
- Confirm Android toolchain availability:
  - Java Runtime
  - Gradle or Gradle wrapper
  - Android SDK platform/build-tools
  - `adb`
- Build debug APK locally.
- Run any unit tests added for native helper classes if the project uses them.

Phone setup checks:

```bash
adb devices -l
adb forward tcp:18000 tcp:8000
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
curl -fsS http://127.0.0.1:18000/api/health
curl -fsS http://127.0.0.1:18000/build-info.json
```

APK install/open checks:

```bash
adb install -r android-shell/app/build/outputs/apk/debug/app-debug.apk
adb shell monkey -p <apk.package.name> 1
```

Real APK voice validation:

- Open the APK on the Nubia screen.
- Grant microphone permission in the Android permission prompt.
- Run at least five click-to-record voice attempts from inside the APK.
- Each attempt must be:
  - tap mic to start,
  - play or speak audible text near the phone,
  - tap mic again to send,
  - screenshot the result.

For each attempt, verify:

- Uploaded audio size is non-trivial.
- `voice_debug.jsonl` has a new row.
- top-level `event` is `voice_chat`.
- `audio_probe.content_type` is an allowed type such as `audio/webm` or
  `audio/wav`.
- `audio_probe.size_bytes` is non-trivial.
- `voice_route.selected` is `unified`.
- `voice_route.thinking_mode` is `false`.
- On ASR success, `user_text` is non-empty.
- On ASR final failure, backend returns explicit failure and does not call LLM.
- Successful `voice_message` turns enter recent 5-turn context.

Expression validation:

- Screenshot thinking state if it is visible.
- After each successful model reply, compare phone screenshot with latest
  `agent_run.final_action_json.expression_key`.
- After TTS playback completes, verify the face does not fall back to question
  mark or another stale expression.

Browser coexistence validation:

- After APK validation, open the old browser URL:
  `http://127.0.0.1:8000/`
- Confirm the same frontend still loads.
- Run one short text or voice interaction from the browser.
- Confirm APK changes did not require any browser-only code path to change.

## Acceptance Criteria

V1.9 is complete only when:

1. The APK builds from source on the Mac.
2. The APK installs on Nubia.
3. The APK displays a clear unavailable screen when backend health fails.
4. The APK loads the existing PetAgent web app when backend health succeeds.
5. The APK requests and grants microphone access only for loopback WebView
   origin.
6. Five real APK voice attempts pass through the existing `/api/voice/chat`
   unified chain.
7. Expression behavior matches backend `expression_key` and does not regress
   after TTS.
8. The original browser entry still works.
9. All known limitations are documented, especially Termux:Boot and wake-lock
   status if they remain unresolved.

## Open Operational Risks

- ADB is not online at the time this spec is written, so no current phone
  status could be freshly verified then. The 2026-06-01 recheck restored ADB
  and confirmed health, but future execution must re-run those checks.
- Java, Gradle, and Android SDK are not currently installed or discoverable on
  the Mac.
- If Nubia WebView 55 lacks a needed WebRTC or permission API behavior, the
  APK may load the page but fail microphone capture. The fallback WAV recorder
  reduces this risk but does not eliminate it.
- Android 6 WebView permission behavior must be checked on the real device; do
  not assume emulator results are enough.
- APK `FLAG_KEEP_SCREEN_ON` only helps while the activity is visible. It does
  not replace Termux wake lock or boot recovery.
