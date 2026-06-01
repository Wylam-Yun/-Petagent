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
- Forbidden artifact check:
  - `git ls-files frontend/dist backend/data backend/static/audio backend/secrets logs android-shell/app/build` printed no tracked files.

## Phone Validation Status

- Current ADB status on 2026-06-02 after local build tooling installation:
  - `adb devices -l` printed no attached devices.
- Task 6 install/open/unavailable-screen checks: pending until Nubia is online again.
- Task 7 real APK voice validation: pending until APK is installed and opened on Nubia.
- Task 8 browser coexistence validation: pending until APK install validation is complete.

## Known Limitations Still In Scope

- Termux:Boot status is not changed by this APK work and remains a V1.8/V1.9 operational limitation until rechecked on the phone.
- Termux wake lock status is not changed by this APK work; the APK only uses `FLAG_KEEP_SCREEN_ON` while its activity is visible.
- The APK does not start, embed, or supervise the FastAPI backend.
- The APK must load `http://127.0.0.1:8000/` on the phone itself; Mac `18000` forwarding is only for validation.
