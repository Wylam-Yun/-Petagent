# V1.9 Shell APK Entry Validation

This file records Nubia field evidence for the shell APK entry.
Do not store runtime logs, audio, screenshots, APK files, secrets, or generated
frontend build output here.

## Preflight

- Date: 2026-06-02 Asia/Shanghai
- Repo commits:
  - `83fbc8a` `docs: plan v19 shell apk entry`
  - `42136ab` `chore: scaffold android shell project`
  - `f7c2779` `feat: add android shell manifest resources`
  - `e2d5b07` `feat: add petagent webview shell activity`
- Android toolchain:
  - JDK: OpenJDK `17.0.19` from Homebrew `openjdk@17`
  - System Gradle used to generate wrapper: `9.5.1`
  - Gradle wrapper: `8.9`
  - Gradle wrapper distribution: `https://services.gradle.org/distributions/gradle-8.9-bin.zip`
  - Gradle wrapper JAR SHA-256: `497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7`
  - Android Gradle Plugin: `8.5.2`
  - Android SDK root: `/opt/homebrew/share/android-commandlinetools`
  - compile SDK: `35`
  - target SDK: `35`
  - min SDK: `23`
  - installed SDK packages:
    - `platform-tools` `37.0.0`
    - `platforms;android-35` version `2`
    - `build-tools;35.0.0`
    - `build-tools;34.0.0` auto-installed by AGP during first debug build
- APK package: `com.petagent.shell`
- APK version: `0.1.0` / `versionCode 1`

## Local Build Validation

- `cd android-shell && ./gradlew tasks`: passed; `:app` project discovered.
- `cd android-shell && ./gradlew assembleDebug`: passed; debug APK generated at `android-shell/app/build/outputs/apk/debug/app-debug.apk`.
- `cd android-shell && ./gradlew clean assembleDebug`: passed.
- Build note: AGP `8.5.2` warns that it was tested up to compile SDK `34`; this build intentionally uses installed compile SDK `35` as planned and completes successfully.
- Build output hygiene:
  - `android-shell/.gradle/`, `android-shell/build/`, `android-shell/app/build/`, and `android-shell/local.properties` are ignored.
  - `git ls-files android-shell/app/build android-shell/.gradle android-shell/build android-shell/local.properties` printed no tracked files.

## Local Regression Checks

- `cd frontend && npm test -- --run`: passed, `12` test files and `71` tests.
- `cd frontend && npm run build`: passed; generated `frontend/dist` remains ignored and untracked.
- `cd backend && ../.venv/bin/python -m pytest tests/test_voice_pipeline.py tests/test_voice_contract.py tests/test_text_chat.py tests/test_v17_context_memory_state.py -q`: passed, `34` tests.
- After the WebView 55 voice compatibility change:
  - `cd frontend && npm test -- --run src/pet/audio.test.ts`: passed,
    `9` tests.
  - `cd frontend && npm test -- --run`: passed, `12` test files and `73`
    tests.
  - `cd frontend && npm run build`: passed; generated `frontend/dist` remains
    ignored and untracked.
  - `cd android-shell && ./gradlew assembleDebug`: passed.
- Forbidden artifact check:
  - `git ls-files frontend/dist backend/data backend/static/audio backend/secrets logs android-shell/app/build` printed no tracked files.

## Phone Validation Status

- Initial ADB status after local build tooling installation:
  - `adb devices -l` temporarily printed no attached devices.
- Reconnected ADB status:
  - `9debb82b device usb:1-1 product:NX531J model:NX531J device:NX531J`
- ADB forwards restored:
  - `9debb82b tcp:18000 tcp:8000`
  - `9debb82b tcp:18022 tcp:8022`
- Termux runtime verification:
  - SSH `id` included `3003(inet)`.
  - `scripts/status.sh` showed `context: ok`, `manager: running`, `manager_context: ok`, `watchdog_stuck: false`, and `database: ok`.
  - `/api/health` returned `ok=true`, `build_hash=ec528f8`, backend pid `16691`.
  - `/build-info.json` returned `git_sha=ec528f8`.
- APK install:
  - `adb install -r android-shell/app/build/outputs/apk/debug/app-debug.apk`: `Success`.
- Runtime permission:
  - `android.permission.RECORD_AUDIO: granted=true`.
- Healthy backend WebView load:
  - Screenshot: `/private/tmp/petagent-v19-apk-home.png`.
  - Result: APK WebView displayed the existing PetAgent UI at the phone-local backend.
- Backend-unavailable screen:
  - Launched debug APK with `petagent_debug_health_url=http://127.0.0.1:65535/api/health`.
  - Screenshot: `/private/tmp/petagent-v19-apk-unavailable.png`.
  - Result: native unavailable screen showed `本地后端没有连上` with a retry button.
  - Real backend stayed healthy through `curl -fsS http://127.0.0.1:18000/api/health`.
- Normal relaunch after unavailable validation:
  - Screenshot: `/private/tmp/petagent-v19-apk-home-after-unavailable.png`.
  - Result: APK WebView displayed the existing PetAgent UI again.
- Disruptive backend stop validation: not run; debug health override covered the unavailable screen without disturbing Termux backend.
- Old WebView 55 voice compatibility:
  - Initial APK voice attempts reached `/api/voice/chat` but WebView
    `MediaRecorder` produced invalid WebM uploads that failed before
    `voice_debug.jsonl`.
  - The frontend now prefers the existing Web Audio WAV recorder only for old
    Chrome/Chromium WebView user agents (`Chrome <= 55` with `wv` or
    `Version/4.0`), preserving the existing `/api/voice/chat` endpoint.
  - `android.permission.MODIFY_AUDIO_SETTINGS` was added because logcat showed
    Chromium media requesting it alongside `RECORD_AUDIO`.
  - During field validation, Android AppOps had `RECORD_AUDIO: ignore` even
    while package runtime permission showed `granted=true`. `adb shell appops
    set com.petagent.shell RECORD_AUDIO allow` restored the validation device's
    permission state; the APK runtime still relies on normal Android permission
    grant behavior.
- Task 7 real APK voice validation:
  - Fresh baseline was written on the phone to
    `backend/data/logs/petagent_v19_voice_baseline.json`:
    `voice_debug_rows=79`, `raw_event_log_count=17`,
    `agent_run_count=95`, `audio_job_count=91`, database
    `backend/data/pet.db`.
  - Five APK voice turns after the baseline all created new
    `event=voice_chat` records in `voice_debug.jsonl`.
  - All five records were `ok=true`, `content_type=audio/wav`,
    `format=wav`, non-empty ASR `user_text`, `selected=unified`, and
    `thinking_mode=false`.
  - Audio evidence:
    - turn 1: `size_bytes=1335340`, `duration_s=41.728`, `rms=2981.6`,
      `max_amp=20006`.
    - turn 2: `size_bytes=1343532`, `duration_s=41.984`, `rms=3006.4`,
      `max_amp=19303`.
    - turn 3: `size_bytes=1368108`, `duration_s=42.752`, `rms=3024.6`,
      `max_amp=19244`.
    - turn 4: `size_bytes=1359916`, `duration_s=42.496`, `rms=2997.7`,
      `max_amp=19526`.
    - turn 5: `size_bytes=1351724`, `duration_s=42.24`, `rms=2890.5`,
      `max_amp=19277`.
  - SQLite deltas after the five turns:
    - `raw_event_log`: `+5`
    - `agent_run`: `+5`
    - `audio_job`: `+5`
  - The five new raw events were all `event_type=voice_message` and
    `source=voice_unified`, with non-empty `user_text` and `pet_reply`.
  - The five latest `agent_run` rows were `status=completed` with
    `audio_job_id` populated. `final_action_json.expression_key` values were
    `idle_wink` or `happy`; the final phone screenshot showed mood `happy` and
    face `(^▽^)`, not the question-mark fallback.
  - The five latest `audio_job` rows were `status=ready` with non-empty
    `/static/audio/...mp3` `voice_url` values.
  - Screenshots are local validation artifacts under `/private/tmp/`:
    `petagent-v19-voice-01.png` through `petagent-v19-voice-05.png`, plus
    `petagent-v19-voice-final-state.png`.
- Task 8 browser coexistence validation:
  - Installed APK did not break the old browser entry. Via Browser package
    `mark.via` opened `http://127.0.0.1:8000/` and displayed the existing
    PetAgent UI.
  - A browser text interaction sent `browser_v19_coexistence_test` and created
    a new `raw_event_log` row:
    `event_type=text_message`, `source=text_fast_reply`, with a non-empty
    `pet_reply`.
  - Screenshot artifact: `/private/tmp/petagent-v19-browser-text-sent.png`.

## Follow-up Operational Hardening

- Follow-up date: 2026-06-02 Asia/Shanghai.
- Follow-up commit: `fix: harden apk mic diagnostics`.
- Phone-served `build-info.json` was rebuilt and redeployed after the follow-up
  commit; the final served SHA was rechecked after committing this validation
  note.
- Follow-up APK install:
  - `adb install -r android-shell/app/build/outputs/apk/debug/app-debug.apk`:
    `Success`.
  - `adb shell am start -W -n com.petagent.shell/.MainActivity`: `Status: ok`.
  - `dumpsys activity` showed `com.petagent.shell/.MainActivity` as the resumed
    activity.
  - Screenshot artifact:
    `/private/tmp/petagent-v19-followup-home-final.png`.
- ADB permission checks after reinstall:
  - `android.permission.RECORD_AUDIO: granted=true`.
  - `RECORD_AUDIO: allow`.
- `scripts/status.sh` now reports both APK runtime permission and AppOps state
  when Android allows Termux to inspect them. On this Nubia, ADB can see
  `RECORD_AUDIO: allow`, while Termux may only report `unknown` because
  `dumpsys package` and `appops` are not fully available from the Termux UID.
  This avoids misreporting a permission-denial result as an uninstalled APK.
- The shell APK now checks `AppOpsManager.OPSTR_RECORD_AUDIO` before granting
  WebView `RESOURCE_AUDIO_CAPTURE`. If Android's permission manager has blocked
  recording at AppOps level, the APK denies the WebView permission request and
  shows a native toast instead of allowing a misleading recording attempt.
- Added `scripts/install_termux_boot_entry.sh` to install only the Termux-side
  boot delegation files:
  `~/.start_services.sh` and `~/.termux/boot/start-sshd.sh`. It does not install
  `com.termux.boot` and does not use adb/root as runtime support.
- Follow-up phone deployment:
  - `scripts/install_termux_boot_entry.sh` ran through Termux SSH with
    `context: ok`.
  - `~/.start_services.sh` now delegates to
    `~/Petagent/scripts/termux_start_services.sh`.
  - `~/.termux/boot/start-sshd.sh` now delegates to
    `~/.start_services.sh --termux-boot`.
  - `adb shell pm list packages | grep -i termux` still printed only
    `package:com.termux`, so the boot scripts are prepared but cannot run on
    reboot until `com.termux.boot` is installed and opened once.
- Wake-lock follow-up:
  - `termux-wake-lock` exists but direct execution through real Termux SSH
    returned `Aborted`, exit status `134`.
  - `adb shell pm list packages | grep -i termux` printed only
    `package:com.termux`; `com.termux.api` is not installed.
  - `adb shell dumpsys power` did not show `termux:service-wakelock` in the final
    follow-up check. This remains a Termux/Termux:API operational limitation,
    not an APK-shell fix.
- Context cleanup for the repeated "打节拍" replies:
  - A text correction was sent through the existing `/api/text/chat` endpoint,
    not a new backend route.
  - The new `raw_event_log` row was `id=104`, `event_type=text_message`,
    `source=text_fast_reply`, and told 豆豆 that the repeated V1.9 recording
    phrases were engineering tests, not the user's current state.
- Local checks:
  - `sh -n scripts/status.sh`
  - `sh -n scripts/install_termux_boot_entry.sh`
  - `cd backend && ../.venv/bin/python -m pytest tests/test_phase1_startup.py -q`
  - `cd android-shell && JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew assembleDebug`

## Known Limitations Still In Scope

- Termux:Boot status is not changed by this APK work. The boot delegation files
  can be prepared, but automatic reboot recovery still requires
  `com.termux.boot` to be installed and opened once from the Android launcher.
- Termux wake lock is Termux service-manager state; the APK only uses
  `FLAG_KEEP_SCREEN_ON` while its activity is visible and does not keep the
  backend alive by itself.
- The APK does not start, embed, or supervise the FastAPI backend.
- The APK must load `http://127.0.0.1:8000/` on the phone itself; Mac `18000` forwarding is only for validation.
