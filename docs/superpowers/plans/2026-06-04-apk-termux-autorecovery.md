# APK Termux Autorecovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Android shell APK usable by non-technical users when the local Termux backend is down.

**Architecture:** The APK remains a WebView shell and never starts FastAPI itself. On health failure it attempts to launch the Termux app once, shows a native recovery screen, polls loopback health for a bounded period, and keeps manual retry/open-Termux controls available.

**Tech Stack:** Android Java Activity, Android package launch intents, existing WebView loopback policy, existing Gradle Android project.

---

### Task 1: Add Native Recovery Controls

**Files:**
- Modify: `android-shell/app/src/main/res/values/strings.xml`
- Modify: `android-shell/app/src/main/java/com/petagent/shell/MainActivity.java`

- [ ] Add strings for waiting, opening Termux, Termux missing, and recovery timeout.
- [ ] Add an unavailable body text view field so recovery status can update without rebuilding the screen.
- [ ] Add a manual `打开 Termux 启动服务` button that launches the Termux package and then continues polling.

### Task 2: Add Automatic Termux Launch and Bounded Polling

**Files:**
- Modify: `android-shell/app/src/main/java/com/petagent/shell/MainActivity.java`

- [ ] Add constants for Termux package name, poll interval, and max poll attempts.
- [ ] Track whether Termux has already been auto-launched for the current recovery cycle.
- [ ] On failed health check, launch Termux once if installed.
- [ ] Poll health every 2 seconds for up to 60 seconds while the unavailable screen is visible.
- [ ] Load the WebView as soon as health recovers.
- [ ] Cancel pending polling callbacks when the Activity is destroyed or when the WebView is shown.

### Task 3: Verify Build and Device Behavior

**Files:**
- Verify only; do not commit APK outputs.

- [ ] Run Java/Gradle build: `cd android-shell && ./gradlew assembleDebug`.
- [ ] Install debug APK on Nubia: `adb install -r android-shell/app/build/outputs/apk/debug/app-debug.apk`.
- [ ] Verify normal launch loads PetAgent UI when backend health is OK.
- [ ] Verify debug bad-health launch shows recovery screen and Termux button without claiming success.
- [ ] Confirm `/api/health` remains OK and existing browser entry is unaffected.
