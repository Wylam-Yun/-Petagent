# V1.9 Shell APK Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` or an equivalent step-by-step implementation loop. Steps use checkbox (`- [ ]`) syntax for tracking. Do not skip the Nubia APK voice validation section.

**Goal:** Add a native Android WebView shell APK as a second PetAgent entry while preserving the existing browser entry and Termux backend runtime.

**Architecture:** Keep FastAPI, SQLite, ASR, LLM, TTS, memory, and frontend behavior unchanged. Add an independent `android-shell/` native Android project whose only runtime job is to health-check `http://127.0.0.1:8000`, load the existing local web app in WebView, grant microphone permission only to the loopback origin, and fail explicitly when the backend is unavailable.

**Tech Stack:** Android native Java, Gradle Android plugin, minSdk 23, Nubia NX531J / Android 6 era WebView 55, existing React/Vite legacy frontend served by FastAPI in Termux, ADB USB, `adb forward`, `ssh nubia-adb`.

---

## Current Field Facts

Repo:

- `/Users/wylam/Documents/workspace/Petagent`

Initial V1.9 draft preflight:

- `git status --short` is clean before this plan.
- There is no existing Android project in the repo:
  - no `settings.gradle`
  - no `build.gradle`
  - no `gradlew`
  - no `AndroidManifest.xml`
- `adb devices -l` showed no online device.
- `adb forward --list` was empty.
- `curl -fsS http://127.0.0.1:18000/api/health` could not connect.
- Local Android build tooling is not ready:
  - `/usr/bin/java` exists but reports no Java Runtime.
  - `gradle` is not installed.
  - `~/Library/Android/sdk` was not found.

2026-06-01 Nubia recheck:

- `adb devices -l` shows `9debb82b device ... model:NX531J`.
- The phone reports Android `6.0.1`, SDK `23`.
- `adb forward tcp:18000 tcp:8000` and
  `adb forward tcp:18022 tcp:8022` were restored.
- `ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'` works:
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
- System WebView is `com.google.android.webview` version `55.0.2883.91`.
- Termux:Boot is still missing; ADB package list shows only `com.termux`.
- Wake lock is still not held:
  - `mWakeLockSummary=0x0`
  - `Wake Locks: size=0`
- `dumpsys package com.termux` still reports `stopped=true`, but SSH, manager,
  and backend processes are currently running. Treat this as a boot/broadcast
  risk, not as current backend failure.
- Local Android build tooling is still missing:
  - no Java Runtime
  - no `gradle`
  - no discovered `~/Library/Android/sdk`

Relevant V1.8 validation facts:

- V1.8 validation file:
  `plan/V1.8/termux-runtime-supervisor-validation.md`
- Backend death recovery passed through the Termux manager.
- Five real Nubia browser voice attempts succeeded through the existing web
  page.
- Browser voice interaction is click-to-record, not press-and-hold.
- Final V1.8 expression screenshot matched backend `expression_key=happy`.
- Known limitations still matter for V1.9:
  - Termux:Boot missing.
  - Termux wake lock not held.
  - Termux-side browser relaunch unavailable because `termux-am` socket/tooling
    is broken and `am` exits `134`.

Relevant project details:

- Frontend API client:
  `frontend/src/pet/api.ts`
  - voice uploads go to `/api/voice/chat`
  - frontend heartbeat goes to `/api/frontend/heartbeat`
- Frontend audio recorder:
  `frontend/src/pet/audio.ts`
  - tries `MediaRecorder`
  - falls back to Web Audio WAV recorder
  - minimum recording duration is `300ms`
  - maximum recording duration is `15000ms`
- Voice button:
  `frontend/src/components/VoiceButton.tsx`
  - tap to start recording
  - tap to send
- Backend voice endpoint:
  `backend/app/api/voice.py`
  - accepts `audio/webm`, `audio/wav`, `audio/mpeg`, `audio/ogg`,
    `audio/mp4`
  - writes `backend/data/logs/voice_debug.jsonl`
  - explicit failures return `ok=false` and `error_class`
- Backend static frontend:
  `backend/app/main.py`
  - mounts `/static`
  - mounts `frontend/dist` at `/` when present
- Runtime status:
  `scripts/status.sh`
  - reports manager, Termux context, sshd, wake lock, Termux:Boot, backend
    health, frontend heartbeat, watchdog, and database status.

## Non-Negotiable Constraints

1. Do not start backend from the APK.
2. Do not embed Python in the APK.
3. Do not use root, `su`, or adb as runtime support for the APK.
4. Keep backend startup in real Termux app context with Android group
   `3003(inet)`.
5. Keep the existing browser entry working at `http://127.0.0.1:8000/`.
6. Do not create a new frontend voice path or backend voice endpoint.
7. Failure must be explicit. No fake successful pet response when the backend
   is unavailable or ASR fails.
8. Do not commit generated APKs, Android build outputs, `frontend/dist`,
   `backend/data`, `backend/static/audio`, `backend/secrets`, uploads, or logs.
9. Validate the backend-unavailable screen without stopping the Termux backend
   whenever possible. Use the debug-only health URL override described in Task
   4 and Task 6.

## Planned File Structure

Create a new independent Android project:

```text
android-shell/
  .gitignore
  settings.gradle
  build.gradle
  gradle.properties
  gradlew
  gradlew.bat
  gradle/wrapper/gradle-wrapper.jar
  gradle/wrapper/gradle-wrapper.properties
  app/
    build.gradle
    src/main/AndroidManifest.xml
    src/main/res/xml/network_security_config.xml
    src/main/res/values/colors.xml
    src/main/res/values/strings.xml
    src/main/res/values/styles.xml
    src/main/java/com/petagent/shell/MainActivity.java
```

No backend or frontend code should be modified unless field validation proves a
specific WebView compatibility problem that cannot be solved inside the shell.

---

## Task 0: Restore Preconditions And Tooling

**Files:**

- Read: `plan/V1.9/shell-apk-entry-spec.md`
- Read: `plan/V1.8/termux-runtime-supervisor-validation.md`
- No repo code changes.

- [ ] **Step 1: Check repo cleanliness**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git status --short
```

Expected:

- Either clean output, if the V1.9 plan files were already committed.
- Or only V1.9 planning files, if this plan is still under review:

```text
?? plan/V1.9/
```

If unrelated files appear, inspect them before continuing. Do not revert user
changes.

- [ ] **Step 2: Check Android build tooling**

Run:

```bash
java -version
gradle -v
ls -d "$HOME/Library/Android/sdk"
```

Expected current result may fail because the V1.9 preflight found no Java
Runtime, no Gradle, and no Android SDK.

Required before Task 2:

- JDK installed and `java -version` works.
- Android SDK installed.
- Either system `gradle` works or a Gradle wrapper can be generated from
  Android Studio / installed Gradle.
- `ANDROID_HOME` points at the SDK, or `android-shell/local.properties`
  contains `sdk.dir=<absolute SDK path>`. `local.properties` must stay ignored.

If using Android Gradle Plugin `8.x`, use JDK 17 or newer. Record the exact
JDK, Gradle, Android Gradle Plugin, compile SDK, and build-tools versions in
`plan/V1.9/shell-apk-entry-validation.md`.

Do not fake this step. If tooling is missing, stop implementation and report
the exact missing tools.

- [ ] **Step 3: Reconnect Nubia before any phone validation**

Run:

```bash
adb devices -l
adb forward --list
```

Expected before validation:

- Device `9debb82b` appears as `device`.
- If the device is missing, ask the operator to reconnect/unlock the Nubia and
  approve USB debugging.

No phone validation can be marked passed while ADB is offline.

- [ ] **Step 4: Restore ADB forwards once device is online**

Run:

```bash
adb forward tcp:18000 tcp:8000
adb forward tcp:18022 tcp:8022
adb forward --list
```

Expected:

```text
9debb82b tcp:18000 tcp:8000
9debb82b tcp:18022 tcp:8022
```

Interpretation:

- `18000` only lets the Mac verify the phone backend with `curl`.
- `18022` only lets the Mac reach Termux SSH.
- The APK itself must load the phone's own `http://127.0.0.1:8000/`; it does
  not use the Mac-side `18000` forward.

- [ ] **Step 5: Verify Termux runtime from real SSH context**

Run:

```bash
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
curl -fsS http://127.0.0.1:18000/api/health
curl -fsS http://127.0.0.1:18000/build-info.json
```

Expected:

- SSH `id` includes `3003(inet)`.
- `scripts/status.sh` prints `context: ok`.
- Backend `/api/health` returns JSON with `"ok": true`.
- `build-info.json` returns frontend build info.
- These checks prove the phone backend is reachable and healthy. They do not
  prove the APK WebView works; APK proof must come from phone screenshots,
  WebView permission behavior, `voice_debug.jsonl`, and SQLite evidence.

If backend is down, restore it only through real Termux SSH:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/termux_start_services.sh --ensure'
```

Do not start backend through `adb shell su` or root.

---

## Task 1: Document V1.9 Spec And Plan

**Files:**

- Create: `plan/V1.9/shell-apk-entry-spec.md`
- Create: `plan/V1.9/shell-apk-entry-implementation-plan.md`

- [ ] **Step 1: Confirm spec covers phone state**

Read:

```bash
sed -n '1,260p' plan/V1.9/shell-apk-entry-spec.md
```

Confirm the spec explicitly mentions:

- Nubia NX531J / old WebView 55.
- Initial V1.9 draft preflight had ADB offline.
- 2026-06-01 Nubia recheck restored ADB forwards and verified SSH, health, and
  build-info.
- Java/Gradle/Android SDK are still missing on the Mac.
- V1.8 five-browser-voice success.
- V1.8 remaining Termux:Boot, wake-lock, and browser relaunch limitations.
- APK does not replace Termux manager.

- [ ] **Step 2: Commit only plan files after review**

Run:

```bash
git status --short
git add plan/V1.9/shell-apk-entry-spec.md plan/V1.9/shell-apk-entry-implementation-plan.md
git commit -m "docs: plan v19 shell apk entry"
```

Do not include generated runtime artifacts.

---

## Task 2: Scaffold Native Android Shell Project

**Files:**

- Create: `android-shell/.gitignore`
- Create: `android-shell/settings.gradle`
- Create: `android-shell/build.gradle`
- Create: `android-shell/gradle.properties`
- Create: `android-shell/gradlew`
- Create: `android-shell/gradlew.bat`
- Create: `android-shell/gradle/wrapper/gradle-wrapper.jar`
- Create: `android-shell/gradle/wrapper/gradle-wrapper.properties`
- Create: `android-shell/app/build.gradle`

- [ ] **Step 1: Generate or copy a standard Gradle wrapper**

Use Android Studio or an installed Gradle to create a standard wrapper under
`android-shell/`.

Expected wrapper files:

```text
android-shell/gradlew
android-shell/gradlew.bat
android-shell/gradle/wrapper/gradle-wrapper.jar
android-shell/gradle/wrapper/gradle-wrapper.properties
```

Do not hand-write a fake wrapper jar.
Record the wrapper distribution URL and checksum in
`plan/V1.9/shell-apk-entry-validation.md`. For AGP `8.5.2`, use a Gradle 8.x
wrapper supported by the installed Android Studio/JDK.

- [ ] **Step 2: Create Android project settings**

Create `android-shell/settings.gradle`:

```gradle
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "PetAgentShell"
include ":app"
```

- [ ] **Step 3: Create root Gradle build file**

Create `android-shell/build.gradle`:

```gradle
plugins {
    id "com.android.application" version "8.5.2" apply false
}
```

Android Gradle Plugin `8.5.2` requires JDK 17. If the installed Android
Studio/SDK toolchain cannot support it, choose the newest locally supported
Android Gradle Plugin and record the exact reason in
`plan/V1.9/shell-apk-entry-validation.md`. Do not spend time debugging APK
behavior until the toolchain versions are explicitly recorded.

- [ ] **Step 4: Create Gradle properties**

Create `android-shell/gradle.properties`:

```properties
org.gradle.jvmargs=-Xmx1536m -Dfile.encoding=UTF-8
android.useAndroidX=false
android.nonTransitiveRClass=true
```

- [ ] **Step 5: Create app Gradle build file**

Create `android-shell/app/build.gradle`:

```gradle
plugins {
    id "com.android.application"
}

android {
    namespace "com.petagent.shell"
    compileSdk 35

    defaultConfig {
        applicationId "com.petagent.shell"
        minSdk 23
        targetSdk 35
        versionCode 1
        versionName "0.1.0"
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_1_8
        targetCompatibility JavaVersion.VERSION_1_8
    }
}
```

If SDK 35 is not installed, install it or change `compileSdk` to the installed
SDK and record the exact value in validation notes.

- [ ] **Step 6: Create Android shell gitignore**

Create `android-shell/.gitignore`:

```gitignore
.gradle/
build/
local.properties
captures/
*.apk
*.aab
app/build/
```

- [ ] **Step 7: Verify empty project config**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/android-shell
./gradlew tasks
```

Expected:

- Gradle starts successfully.
- The `:app` project is discovered.

- [ ] **Step 8: Commit scaffold**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git status --short
git add android-shell
git commit -m "chore: scaffold android shell project"
```

Confirm no `android-shell/app/build/` or APK output is tracked.

---

## Task 3: Add Manifest, Resources, And Network Policy

**Files:**

- Create: `android-shell/app/src/main/AndroidManifest.xml`
- Create: `android-shell/app/src/main/res/xml/network_security_config.xml`
- Create: `android-shell/app/src/main/res/values/strings.xml`
- Create: `android-shell/app/src/main/res/values/colors.xml`
- Create: `android-shell/app/src/main/res/values/styles.xml`

- [ ] **Step 1: Create manifest**

Create `android-shell/app/src/main/AndroidManifest.xml`:

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.RECORD_AUDIO" />

    <application
        android:allowBackup="false"
        android:label="@string/app_name"
        android:networkSecurityConfig="@xml/network_security_config"
        android:supportsRtl="true"
        android:theme="@style/AppTheme">
        <activity
            android:name=".MainActivity"
            android:configChanges="keyboard|keyboardHidden|orientation|screenSize"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

- [ ] **Step 2: Create loopback-only cleartext policy**

Create `android-shell/app/src/main/res/xml/network_security_config.xml`:

```xml
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="false">127.0.0.1</domain>
        <domain includeSubdomains="false">localhost</domain>
    </domain-config>
    <base-config cleartextTrafficPermitted="false" />
</network-security-config>
```

This file is still useful for newer Android behavior, but the Nubia is Android
6 era. Runtime URL enforcement must also be done in `MainActivity` through
`isAllowedLocalUrl()`, `shouldInterceptRequest()`, and
`onPermissionRequest()`.

- [ ] **Step 3: Create string resources**

Create `android-shell/app/src/main/res/values/strings.xml`:

```xml
<resources>
    <string name="app_name">豆豆桌宠</string>
    <string name="backend_unavailable_title">本地后端没有连上</string>
    <string name="backend_unavailable_body">请先打开 Termux 并启动 PetAgent 服务，然后点重试。</string>
    <string name="retry">重试</string>
</resources>
```

- [ ] **Step 4: Create color resources**

Create `android-shell/app/src/main/res/values/colors.xml`:

```xml
<resources>
    <color name="screen_bg">#F7FBFF</color>
    <color name="text_main">#1F2937</color>
    <color name="text_muted">#64748B</color>
    <color name="button_bg">#2563EB</color>
    <color name="button_text">#FFFFFF</color>
</resources>
```

- [ ] **Step 5: Create simple theme**

Create `android-shell/app/src/main/res/values/styles.xml`:

```xml
<resources>
    <style name="AppTheme" parent="@android:style/Theme.Material.Light.NoActionBar">
        <item name="android:windowNoTitle">true</item>
        <item name="android:fontFamily">sans</item>
        <item name="android:colorAccent">@color/button_bg</item>
        <item name="android:windowLightStatusBar">true</item>
        <item name="android:navigationBarColor">@color/screen_bg</item>
        <item name="android:statusBarColor">@color/screen_bg</item>
    </style>
</resources>
```

If `android:windowLightStatusBar` causes an API/resource compatibility error,
move it to a versioned `values-v23/styles.xml` file or remove it and document
the change.

- [ ] **Step 6: Commit manifest/resources**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add android-shell/app/src/main
git commit -m "feat: add android shell manifest resources"
```

This commit is allowed to reference `MainActivity` before the Java file exists,
but do not claim the APK builds until Task 4 passes.

---

## Task 4: Implement MainActivity WebView Shell

**Files:**

- Create: `android-shell/app/src/main/java/com/petagent/shell/MainActivity.java`

- [ ] **Step 1: Create MainActivity**

Create `android-shell/app/src/main/java/com/petagent/shell/MainActivity.java`:

```java
package com.petagent.shell;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.io.IOException;
import java.io.ByteArrayInputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {
    private static final String DEFAULT_APP_URL = "http://127.0.0.1:8000/";
    private static final String DEFAULT_HEALTH_URL = "http://127.0.0.1:8000/api/health";
    private static final String DEBUG_HEALTH_URL_EXTRA = "petagent_debug_health_url";
    private static final int REQUEST_RECORD_AUDIO = 1001;

    private FrameLayout root;
    private WebView webView;
    private View loadingView;
    private View unavailableView;
    private String appUrl = DEFAULT_APP_URL;
    private String healthUrl = DEFAULT_HEALTH_URL;
    private PermissionRequest pendingAudioPermissionRequest;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        root = new FrameLayout(this);
        setContentView(root);
        configureDebugOverrides();
        createWebView();
        createLoadingView();
        createUnavailableView();
        checkHealthAndLoad();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null && webView.getVisibility() == View.GONE) {
            checkHealthAndLoad();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }

    private void configureDebugOverrides() {
        if ((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) == 0) {
            return;
        }
        String debugHealthUrl = getIntent().getStringExtra(DEBUG_HEALTH_URL_EXTRA);
        if (isAllowedLoopbackHttpUrl(debugHealthUrl)) {
            healthUrl = debugHealthUrl;
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQUEST_RECORD_AUDIO || pendingAudioPermissionRequest == null) {
            return;
        }
        PermissionRequest request = pendingAudioPermissionRequest;
        pendingAudioPermissionRequest = null;
        if (grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED
                && isAllowedLoopbackOrigin(request.getOrigin())) {
            request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
        } else {
            request.deny();
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void createWebView() {
        webView = new WebView(this);
        webView.setVisibility(View.GONE);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        if (android.os.Build.VERSION.SDK_INT >= 21) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        }
        webView.setWebViewClient(new LocalOnlyWebViewClient());
        webView.setWebChromeClient(new LocalOnlyChromeClient());
        root.addView(webView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
    }

    private void createLoadingView() {
        LinearLayout layout = centeredColumn();
        ProgressBar progress = new ProgressBar(this);
        TextView text = textView("正在连接本地后端...", 16, Color.rgb(31, 41, 55));
        layout.addView(progress);
        layout.addView(text);
        loadingView = layout;
        root.addView(loadingView);
    }

    private void createUnavailableView() {
        LinearLayout layout = centeredColumn();
        TextView title = textView(getString(R.string.backend_unavailable_title), 20, Color.rgb(31, 41, 55));
        TextView body = textView(getString(R.string.backend_unavailable_body), 15, Color.rgb(100, 116, 139));
        Button retry = new Button(this);
        retry.setText(getString(R.string.retry));
        retry.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                checkHealthAndLoad();
            }
        });
        layout.addView(title);
        layout.addView(body);
        layout.addView(retry);
        unavailableView = layout;
        unavailableView.setVisibility(View.GONE);
        root.addView(unavailableView);
    }

    private LinearLayout centeredColumn() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        layout.setPadding(40, 40, 40, 40);
        layout.setBackgroundColor(Color.rgb(247, 251, 255));
        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT);
        layout.setLayoutParams(params);
        return layout;
    }

    private TextView textView(String value, int sp, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color);
        view.setGravity(Gravity.CENTER);
        view.setPadding(0, 16, 0, 16);
        return view;
    }

    private void checkHealthAndLoad() {
        showLoading();
        new Thread(new Runnable() {
            @Override
            public void run() {
                final boolean healthy = isBackendHealthy();
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        if (healthy) {
                            showWeb();
                            webView.loadUrl(appUrl);
                        } else {
                            showUnavailable();
                        }
                    }
                });
            }
        }).start();
    }

    private boolean isBackendHealthy() {
        HttpURLConnection connection = null;
        try {
            URL url = new URL(healthUrl);
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(1500);
            connection.setReadTimeout(1500);
            connection.setRequestMethod("GET");
            int code = connection.getResponseCode();
            return code >= 200 && code < 300;
        } catch (IOException ignored) {
            return false;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private void showLoading() {
        loadingView.setVisibility(View.VISIBLE);
        unavailableView.setVisibility(View.GONE);
        webView.setVisibility(View.GONE);
    }

    private void showUnavailable() {
        loadingView.setVisibility(View.GONE);
        unavailableView.setVisibility(View.VISIBLE);
        webView.setVisibility(View.GONE);
    }

    private void showWeb() {
        loadingView.setVisibility(View.GONE);
        unavailableView.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
    }

    private boolean isAllowedLocalUrl(String value) {
        Uri uri = Uri.parse(value);
        String scheme = uri.getScheme();
        String host = uri.getHost();
        int port = uri.getPort();
        return "http".equals(scheme) && "127.0.0.1".equals(host) && port == 8000;
    }

    private boolean isAllowedLoopbackHttpUrl(String value) {
        if (value == null) {
            return false;
        }
        Uri uri = Uri.parse(value);
        String scheme = uri.getScheme();
        String host = uri.getHost();
        int port = uri.getPort();
        return "http".equals(scheme) && "127.0.0.1".equals(host) && port > 0;
    }

    private boolean isAllowedLoopbackOrigin(Uri uri) {
        if (uri == null) {
            return false;
        }
        String scheme = uri.getScheme();
        String host = uri.getHost();
        int port = uri.getPort();
        return "http".equals(scheme) && "127.0.0.1".equals(host) && port == 8000;
    }

    private boolean isOnlyAudioCapture(String[] resources) {
        return resources.length == 1
                && PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resources[0]);
    }

    private void requestRecordAudioPermissionFor(PermissionRequest request) {
        if (pendingAudioPermissionRequest != null) {
            pendingAudioPermissionRequest.deny();
        }
        pendingAudioPermissionRequest = request;
        if (android.os.Build.VERSION.SDK_INT >= 23) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQUEST_RECORD_AUDIO);
        }
    }

    private class LocalOnlyWebViewClient extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            return !isAllowedLocalUrl(request.getUrl().toString());
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            return !isAllowedLocalUrl(url);
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (android.os.Build.VERSION.SDK_INT >= 23 && request.isForMainFrame()) {
                showUnavailable();
            }
            super.onReceivedError(view, request, error);
        }

        @Override
        public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
            showUnavailable();
            super.onReceivedError(view, errorCode, description, failingUrl);
        }

        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
            if (!isAllowedLocalUrl(request.getUrl().toString())) {
                return emptyBlockedResponse();
            }
            return super.shouldInterceptRequest(view, request);
        }

        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, String url) {
            if (!isAllowedLocalUrl(url)) {
                return emptyBlockedResponse();
            }
            return super.shouldInterceptRequest(view, url);
        }

        private WebResourceResponse emptyBlockedResponse() {
            return new WebResourceResponse(
                    "text/plain",
                    "utf-8",
                    new ByteArrayInputStream(new byte[0]));
        }
    }

    private class LocalOnlyChromeClient extends WebChromeClient {
        @Override
        public void onPermissionRequest(final PermissionRequest request) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                if (!isAllowedLoopbackOrigin(request.getOrigin())) {
                    request.deny();
                    return;
                }
                String[] resources = request.getResources();
                if (!isOnlyAudioCapture(resources)) {
                    request.deny();
                    return;
                }
                if (checkRecordAudioGranted()) {
                    request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                    return;
                }
                requestRecordAudioPermissionFor(request);
                }
            });
        }
    }

    private boolean checkRecordAudioGranted() {
        return android.os.Build.VERSION.SDK_INT < 23
                || checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
    }
}
```

- [ ] **Step 2: Build debug APK**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/android-shell
./gradlew assembleDebug
```

Expected:

```text
BUILD SUCCESSFUL
```

APK path:

```text
android-shell/app/build/outputs/apk/debug/app-debug.apk
```

- [ ] **Step 3: Confirm build outputs are ignored**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git status --short
git ls-files android-shell/app/build android-shell/.gradle
```

Expected:

- Build output appears untracked at most, never tracked.
- `git ls-files ...` prints nothing.

- [ ] **Step 4: Commit MainActivity**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add android-shell/app/src/main/java/com/petagent/shell/MainActivity.java
git commit -m "feat: add petagent webview shell activity"
```

---

## Task 5: Local Regression Checks Before Phone Install

**Files:**

- No source changes unless checks fail.

- [ ] **Step 1: Run Android build**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/android-shell
./gradlew clean assembleDebug
```

Expected:

```text
BUILD SUCCESSFUL
```

- [ ] **Step 2: Run existing frontend checks**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- --run
npm run build
```

Expected:

- Vitest passes.
- Build passes.

Do not commit `frontend/dist`.

- [ ] **Step 3: Run targeted backend checks**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest \
  tests/test_voice_pipeline.py \
  tests/test_voice_contract.py \
  tests/test_text_chat.py \
  tests/test_v17_context_memory_state.py \
  -q
```

Expected:

- All selected tests pass.

- [ ] **Step 4: Check artifact hygiene**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git status --short
git ls-files frontend/dist backend/data backend/static/audio backend/secrets logs android-shell/app/build
```

Expected:

- No forbidden generated/runtime files are tracked.
- If `frontend/dist` exists after build, it remains untracked/ignored.

---

## Task 6: Nubia Install And Basic APK Entry Validation

**Files:**

- Create: `plan/V1.9/shell-apk-entry-validation.md`

- [ ] **Step 1: Create validation note**

Create `plan/V1.9/shell-apk-entry-validation.md` with this initial content:

```markdown
# V1.9 Shell APK Entry Validation

This file records Nubia field evidence for the shell APK entry.
Do not store runtime logs, audio, screenshots, APK files, secrets, or generated
frontend build output here.

## Preflight

- Date:
- Repo commit:
- ADB device:
- Android toolchain:
- APK package:
- APK version:
```

- [ ] **Step 2: Re-establish phone connection**

Run:

```bash
adb devices -l
adb forward tcp:18000 tcp:8000
adb forward tcp:18022 tcp:8022
adb forward --list
```

Expected:

- Nubia device is online.
- Forward rows exist for `18000` and `18022`.

- [ ] **Step 3: Verify Termux backend health**

Run:

```bash
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
curl -fsS http://127.0.0.1:18000/api/health
curl -fsS http://127.0.0.1:18000/build-info.json
```

Expected:

- SSH `id` includes `3003(inet)`.
- `scripts/status.sh` shows `context: ok`.
- Backend health is `ok=true`.
- Build info is reachable.

- [ ] **Step 4: Install debug APK**

Run:

```bash
adb install -r android-shell/app/build/outputs/apk/debug/app-debug.apk
```

Expected:

```text
Success
```

- [ ] **Step 5: Open APK**

Run:

```bash
adb shell monkey -p com.petagent.shell 1
```

Expected:

- APK opens on Nubia.
- If Android asks for microphone permission, grant it on the phone. If no
  prompt appears, check whether permission was already granted:

```bash
adb shell dumpsys package com.petagent.shell | grep -A20 'runtime permissions' | grep RECORD_AUDIO || true
```

- PetAgent page loads when backend is healthy.

- [ ] **Step 6: Capture basic screenshot**

Run:

```bash
adb shell screencap -p /sdcard/petagent-v19-apk-home.png
adb pull /sdcard/petagent-v19-apk-home.png /private/tmp/petagent-v19-apk-home.png
```

Expected:

- Screenshot shows the PetAgent UI inside the APK.

Record the screenshot path in
`plan/V1.9/shell-apk-entry-validation.md`; do not commit the screenshot.

- [ ] **Step 7: Validate backend-unavailable screen without stopping backend**

Use the debug-only health URL override first. This avoids disturbing the
currently healthy Termux backend and avoids racing the V1.8 manager restart
loop.

Run:

```bash
adb shell am force-stop com.petagent.shell
adb shell am start \
  -n com.petagent.shell/.MainActivity \
  --es petagent_debug_health_url http://127.0.0.1:65535/api/health
adb shell screencap -p /sdcard/petagent-v19-apk-unavailable.png
adb pull /sdcard/petagent-v19-apk-unavailable.png /private/tmp/petagent-v19-apk-unavailable.png
```

Expected:

- APK shows native unavailable screen.
- Backend remains healthy through the normal forwarded health endpoint:

```bash
curl -fsS http://127.0.0.1:18000/api/health
```

Relaunch normally:

```bash
adb shell am force-stop com.petagent.shell
adb shell monkey -p com.petagent.shell 1
```

Expected:

- APK loads the PetAgent page again.

- [ ] **Step 8: Optional disruptive backend-unavailable validation**

This is a disruptive validation because it temporarily stops the backend.
Run it only with explicit user approval.

1. Keep the phone connected.
2. Temporarily stop backend only if the user approves this validation.
3. Stop through Termux SSH. Note that `scripts/stop.sh` contains a `su -c`
   fallback for killing stray runtimes; this step is not a pure no-root
   operation and must be documented if run:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/stop.sh'
adb shell am force-stop com.petagent.shell
adb shell am start -W -n com.petagent.shell/.MainActivity
```

Expected:

- APK shows native unavailable screen.
- It does not show a fake pet reply.
- It offers retry.

Restore through real Termux SSH:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/termux_start_services.sh --ensure'
curl -fsS http://127.0.0.1:18000/api/health
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
```

If stopping backend is not approved, skip this step and mark it explicitly as
not run. Do not claim it passed.
If this step is run, the restore evidence must again show `3003(inet)`,
`context: ok`, `manager_context: ok`, and backend health `ok=true`.

- [ ] **Step 9: Commit validation note**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add plan/V1.9/shell-apk-entry-validation.md
git commit -m "docs: record v19 apk entry validation"
```

---

## Task 7: Real APK Voice Chain Validation

**Files:**

- Modify: `plan/V1.9/shell-apk-entry-validation.md`

- [ ] **Step 1: Prepare voice evidence windows**

Run:

```bash
ssh nubia-adb 'cd ~/Petagent && python - <<'"'"'PY'"'"'
import json
import sqlite3
from datetime import datetime
from pathlib import Path

con = sqlite3.connect("backend/data/pet.db")
baseline_path = Path("backend/data/logs/petagent_v19_voice_baseline.json")
baseline_path.parent.mkdir(parents=True, exist_ok=True)
baseline = {
    "started_at_utc": datetime.utcnow().isoformat(),
    "voice_debug_rows": len(Path("backend/data/logs/voice_debug.jsonl").read_text(encoding="utf-8").splitlines()) if Path("backend/data/logs/voice_debug.jsonl").exists() else 0,
    "raw_event_log_count": con.execute("SELECT COUNT(*) FROM raw_event_log").fetchone()[0],
    "agent_run_count": con.execute("SELECT COUNT(*) FROM agent_run").fetchone()[0],
    "audio_job_count": con.execute("SELECT COUNT(*) FROM audio_job").fetchone()[0],
}
baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
print(json.dumps(baseline, ensure_ascii=False))
PY'
ssh nubia-adb 'cd ~/Petagent && scripts/status.sh'
```

Record the baseline JSON in validation notes. Later evidence must filter by
`started_at_utc` or `voice_debug_rows`, not by a plain `tail`, so browser/old
voice rows cannot be mistaken for APK rows.

- [ ] **Step 2: Run five real APK voice attempts**

For each attempt:

1. Open APK on Nubia.
2. Tap the mic button once to start.
3. Speak near the Nubia or play audible Mac `say` text.
4. Tap the mic button once to send.
5. Wait for response/TTS to finish.
6. Capture screenshot.

Suggested Mac playback phrases:

```bash
say "V one point nine APK voice chain first test one two three four five"
say "V one point nine APK voice chain second test one two three four five"
say "V one point nine APK voice chain third test one two three four five"
say "V one point nine APK voice chain fourth test one two three four five"
say "V one point nine APK voice chain fifth test one two three four five"
```

Screenshot commands:

```bash
adb shell screencap -p /sdcard/petagent-v19-apk-voice-1.png
adb pull /sdcard/petagent-v19-apk-voice-1.png /private/tmp/petagent-v19-apk-voice-1.png
```

Repeat with filenames `voice-2` through `voice-5`.

- [ ] **Step 3: Inspect voice_debug rows**

Run:

```bash
ssh nubia-adb 'cd ~/Petagent && python - <<'"'"'PY'"'"'
import json
from pathlib import Path

baseline = json.loads(Path("backend/data/logs/petagent_v19_voice_baseline.json").read_text(encoding="utf-8"))
start_index = int(baseline["voice_debug_rows"])
rows = []
path = Path("backend/data/logs/voice_debug.jsonl")
if path.exists():
    for line in path.read_text(encoding="utf-8").splitlines()[start_index:]:
        row = json.loads(line)
        probe = row.get("audio_probe") or {}
        route = row.get("voice_route") or {}
        rows.append({
            "ts": row.get("ts"),
            "event": row.get("event"),
            "ok": row.get("ok"),
            "filename": row.get("filename"),
            "content_type": probe.get("content_type"),
            "size_bytes": probe.get("size_bytes"),
            "duration_s": probe.get("duration_s"),
            "user_text": row.get("user_text"),
            "error_class": row.get("error_class"),
            "selected": route.get("selected"),
            "thinking_mode": route.get("thinking_mode"),
            "asr_provider": route.get("asr_provider"),
            "brain_provider": route.get("brain_provider"),
        })
print(json.dumps(rows, ensure_ascii=False, indent=2))
PY'
```

For each of the five attempts, record:

- upload filename
- `audio_probe.content_type`
- `audio_probe.size_bytes`
- `ok`
- `error_class`
- `voice_route.selected`
- `voice_route.thinking_mode`
- `user_text`

Expected successful rows:

- top-level `event` is `voice_chat`.
- `audio_probe.content_type` is allowed.
- `audio_probe.size_bytes` is non-trivial.
- `voice_route.selected` is `unified`.
- `voice_route.thinking_mode` is `false`.
- `ok=true`.
- `user_text` is non-empty.

If an ASR timeout or other ASR failure occurs, verify it is explicit:

- `ok=false`
- `error_class` is present
- no fake reply
- no TTS job generated
- no LLM final action for that failed turn

Use this query to inspect failure-side effects since the baseline:

```bash
ssh nubia-adb 'cd ~/Petagent && python - <<'"'"'PY'"'"'
import json
import sqlite3
from pathlib import Path

baseline = json.loads(Path("backend/data/logs/petagent_v19_voice_baseline.json").read_text(encoding="utf-8"))
started = baseline["started_at_utc"]
con = sqlite3.connect("backend/data/pet.db")
con.row_factory = sqlite3.Row
print("agent_run_since_baseline")
for row in con.execute("""
    SELECT created_at, status, event_id, final_action_json
    FROM agent_run
    WHERE created_at >= ?
    ORDER BY created_at
""", (started,)):
    action = json.loads(row["final_action_json"] or "{}")
    print(row["created_at"], row["status"], row["event_id"], action.get("reply"), action.get("expression_key"))
print("audio_job_since_baseline")
for row in con.execute("""
    SELECT created_at, status, event_id, job_id, error_class
    FROM audio_job
    WHERE created_at >= ?
    ORDER BY created_at
""", (started,)):
    print(dict(row))
PY'
```

For any failed ASR row, there must be no corresponding successful LLM final
action and no newly created TTS job for that failed voice event.

- [ ] **Step 4: Confirm successful voice turns entered recent context**

Run this Python one-liner through Termux SSH:

```bash
ssh nubia-adb 'cd ~/Petagent && python - <<'"'"'PY'"'"'
import json
import sqlite3
from pathlib import Path

baseline = json.loads(Path("backend/data/logs/petagent_v19_voice_baseline.json").read_text(encoding="utf-8"))
started = baseline["started_at_utc"]
con = sqlite3.connect("backend/data/pet.db")
con.row_factory = sqlite3.Row
rows = con.execute("""
    SELECT event_id, event_type, user_text, pet_reply, created_at_utc
    FROM raw_event_log
    WHERE event_type = ?
      AND created_at_utc >= ?
      AND COALESCE(user_text, ?) != ?
      AND COALESCE(pet_reply, ?) != ?
    ORDER BY created_at_utc DESC
""", ("voice_message", started, "", "", "", "")).fetchall()
for row in rows:
    print(dict(row))
PY'
```

Expected:

- The latest successful APK voice turns appear as `voice_message`.
- `user_text` and `pet_reply` are non-empty.
- At least five successful APK voice turns appear after the baseline. If fewer
  appear, do not claim Task 7 passed.

- [ ] **Step 5: Confirm expression evidence**

Run:

```bash
ssh nubia-adb 'cd ~/Petagent && python - <<'"'"'PY'"'"'
import json
import sqlite3
from pathlib import Path

baseline = json.loads(Path("backend/data/logs/petagent_v19_voice_baseline.json").read_text(encoding="utf-8"))
started = baseline["started_at_utc"]
con = sqlite3.connect("backend/data/pet.db")
con.row_factory = sqlite3.Row
rows = con.execute("""
    SELECT ar.created_at, ar.status, ar.event_id, ar.final_action_json
    FROM agent_run ar
    JOIN raw_event_log rel ON rel.event_id = ar.event_id
    WHERE rel.event_type = ?
      AND ar.created_at >= ?
    ORDER BY ar.created_at DESC
""", ("voice_message", started)).fetchall()
for row in rows:
    action = json.loads(row["final_action_json"] or "{}")
    print(row["created_at"], row["status"], row["event_id"], action.get("expression_key"), action.get("reply"))
PY'
```

Expected:

- Latest successful voice runs have `status` terminal success.
- `expression_key` matches the final APK screenshot.
- After TTS playback, the phone does not show the question-mark fallback.

- [ ] **Step 6: Update validation note**

Append a table to `plan/V1.9/shell-apk-entry-validation.md`:

```markdown
## APK Voice Validation

| Attempt | Screenshot | Upload | Size | Content Type | ASR Text | Result | Expression |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| 1 | `/private/tmp/...` | `voice-...` |  |  |  |  |  |
| 2 | `/private/tmp/...` | `voice-...` |  |  |  |  |  |
| 3 | `/private/tmp/...` | `voice-...` |  |  |  |  |  |
| 4 | `/private/tmp/...` | `voice-...` |  |  |  |  |  |
| 5 | `/private/tmp/...` | `voice-...` |  |  |  |  |  |
```

Do not paste large logs into the validation file.

- [ ] **Step 7: Commit voice validation note**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add plan/V1.9/shell-apk-entry-validation.md
git commit -m "docs: record v19 apk voice validation"
```

---

## Task 8: Browser Coexistence Validation

**Files:**

- Modify: `plan/V1.9/shell-apk-entry-validation.md`

- [ ] **Step 1: Open original browser entry**

Run:

```bash
adb shell am start -a android.intent.action.VIEW -d http://127.0.0.1:8000/
```

Expected:

- Browser opens the existing PetAgent page.
- This is only validation assistance. Do not rely on ADB `am start` as runtime
  behavior.

- [ ] **Step 2: Run one browser interaction**

From the phone browser page, run either:

- one short text interaction, or
- one click-to-record voice interaction.

Expected:

- Browser entry still works after APK installation.
- Existing frontend behavior did not fork for APK.

- [ ] **Step 3: Check frontend heartbeat**

Run:

```bash
ssh nubia-adb 'cd ~/Petagent && scripts/status.sh'
```

Expected:

- `frontend_heartbeat_age_s` is fresh after either APK or browser use.
- `watchdog_stuck: false`.

- [ ] **Step 4: Update and commit validation**

Append:

```markdown
## Browser Coexistence

- Browser URL:
- Interaction type:
- Result:
- Heartbeat age:
- Notes:
```

Commit:

```bash
git add plan/V1.9/shell-apk-entry-validation.md
git commit -m "docs: record v19 browser coexistence validation"
```

---

## Task 9: Final Hygiene And Handoff

**Files:**

- Read: all touched files.
- Modify: `README.md` only if the user wants a permanent user-facing APK
  section after validation.

- [ ] **Step 1: Check forbidden files**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git status --short
git ls-files frontend/dist backend/data backend/static/audio backend/secrets logs android-shell/app/build
```

Expected:

- No forbidden runtime/build artifacts tracked.

- [ ] **Step 2: Summarize known limitations**

Ensure `plan/V1.9/shell-apk-entry-validation.md` says whether these are still
true:

- Termux:Boot installed or missing.
- Wake lock held or not held.
- Termux manager running or not running.
- APK cannot start backend by itself.
- APK keep-screen-on applies only while APK activity is visible.

- [ ] **Step 3: Final test command list**

Record final commands and results:

```bash
cd android-shell && ./gradlew clean assembleDebug
cd frontend && npm test -- --run && npm run build
cd backend && ../.venv/bin/python -m pytest tests/test_voice_pipeline.py tests/test_voice_contract.py tests/test_text_chat.py tests/test_v17_context_memory_state.py -q
```

- [ ] **Step 4: Final commit if README or validation changed**

Run:

```bash
git status --short
git add <changed-doc-files>
git commit -m "docs: finalize v19 shell apk validation"
```

Only commit if there are real doc changes not already committed.

## Stop Conditions

Stop and report instead of continuing if:

- ADB is offline during any claimed phone validation.
- SSH `id` does not include `3003(inet)`.
- Backend health cannot be restored through real Termux SSH.
- Android build tooling is missing and cannot build the APK.
- `RECORD_AUDIO` is not granted and cannot be granted. A missing permission
  prompt is not by itself a failure, because the permission may already be
  granted.
- APK voice recording works only through a new path rather than existing
  `/api/voice/chat`.
- A failed ASR turn generates a fake successful reply.
- Browser entry breaks after APK installation.
