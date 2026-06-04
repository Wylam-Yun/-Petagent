package com.petagent.shell;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AppOpsManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
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
import android.widget.Toast;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {
    private static final String DEFAULT_APP_URL = "http://127.0.0.1:8000/";
    private static final String DEFAULT_HEALTH_URL = "http://127.0.0.1:8000/api/health";
    private static final String TERMUX_PACKAGE = "com.termux";
    private static final String TERMUX_ACTIVITY = "com.termux.app.TermuxActivity";
    private static final String DEBUG_HEALTH_URL_EXTRA = "petagent_debug_health_url";
    private static final String INTERNAL_RETURN_EXTRA = "petagent_internal_return";
    private static final int REQUEST_RECORD_AUDIO = 1001;
    private static final long RECOVERY_POLL_INTERVAL_MS = 2000L;
    private static final int RECOVERY_MAX_POLL_ATTEMPTS = 30;
    private static final long RETURN_AFTER_TERMUX_LAUNCH_MS = 5000L;

    private FrameLayout root;
    private WebView webView;
    private View loadingView;
    private View unavailableView;
    private TextView unavailableBodyView;
    private String appUrl = DEFAULT_APP_URL;
    private String healthUrl = DEFAULT_HEALTH_URL;
    private boolean debugHealthOverrideActive;
    private Handler mainHandler;
    private Runnable recoveryPollRunnable;
    private Runnable returnToShellRunnable;
    private int healthCheckGeneration;
    private int recoveryPollAttempts;
    private boolean termuxAutoLaunchAttempted;
    private boolean destroyed;
    private PermissionRequest pendingAudioPermissionRequest;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        mainHandler = new Handler(Looper.getMainLooper());
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
        if (webView != null
                && webView.getVisibility() == View.GONE
                && unavailableView != null
                && unavailableView.getVisibility() != View.VISIBLE) {
            checkHealthAndLoad();
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        configureDebugOverrides();
        if (intent.getBooleanExtra(INTERNAL_RETURN_EXTRA, false)) {
            startHealthCheck(false);
        } else {
            checkHealthAndLoad();
        }
    }

    @Override
    protected void onDestroy() {
        destroyed = true;
        cancelRecoveryCallbacks();
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }

    private void configureDebugOverrides() {
        healthUrl = DEFAULT_HEALTH_URL;
        debugHealthOverrideActive = false;
        if (!isDebuggable()) {
            return;
        }
        String debugHealthUrl = getIntent().getStringExtra(DEBUG_HEALTH_URL_EXTRA);
        if (isAllowedLoopbackHttpUrl(debugHealthUrl)) {
            healthUrl = debugHealthUrl;
            debugHealthOverrideActive = true;
        }
    }

    private boolean isDebuggable() {
        return (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
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
                && isRecordAudioAppOpAllowed()
                && isAllowedLoopbackOrigin(request.getOrigin())) {
            request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
        } else {
            showAudioPermissionBlockedToast();
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
        unavailableBodyView = textView(getString(R.string.backend_unavailable_body), 15, Color.rgb(100, 116, 139));
        Button openTermux = new Button(this);
        openTermux.setText(getString(R.string.open_termux));
        openTermux.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                openTermuxAndPoll();
            }
        });
        Button retry = new Button(this);
        retry.setText(getString(R.string.retry));
        retry.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                checkHealthAndLoad();
            }
        });
        layout.addView(title);
        layout.addView(unavailableBodyView);
        layout.addView(openTermux);
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
        startHealthCheck(true);
    }

    private void startHealthCheck(final boolean resetRecovery) {
        if (resetRecovery) {
            cancelRecoveryPoll();
            recoveryPollAttempts = 0;
            termuxAutoLaunchAttempted = false;
            showLoading();
        }
        final int generation = ++healthCheckGeneration;
        final boolean shouldAutoRecover = !debugHealthOverrideActive;
        new Thread(new Runnable() {
            @Override
            public void run() {
                final boolean healthy = isBackendHealthy();
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        if (destroyed || generation != healthCheckGeneration) {
                            return;
                        }
                        if (healthy) {
                            showWeb();
                            webView.loadUrl(appUrl);
                        } else {
                            handleUnhealthyBackend(shouldAutoRecover);
                        }
                    }
                });
            }
        }).start();
    }

    private void handleUnhealthyBackend(boolean shouldAutoRecover) {
        showUnavailable();
        if (!shouldAutoRecover) {
            setUnavailableBody(R.string.backend_recovery_manual_hint);
            return;
        }
        if (!termuxAutoLaunchAttempted) {
            termuxAutoLaunchAttempted = true;
            if (launchTermux()) {
                setUnavailableBody(R.string.backend_recovery_opened_termux);
                scheduleReturnToShell();
            } else {
                setUnavailableBody(R.string.termux_missing);
            }
        } else if (recoveryPollAttempts == 0) {
            setUnavailableBody(R.string.backend_recovery_waiting);
        }
        scheduleRecoveryPoll();
    }

    private void openTermuxAndPoll() {
        cancelRecoveryPoll();
        recoveryPollAttempts = 0;
        termuxAutoLaunchAttempted = true;
        showUnavailable();
        if (launchTermux()) {
            setUnavailableBody(R.string.backend_recovery_opened_termux);
            scheduleReturnToShell();
            scheduleRecoveryPoll();
        } else {
            setUnavailableBody(R.string.termux_missing);
        }
    }

    private boolean launchTermux() {
        Intent explicitTermuxIntent = new Intent(Intent.ACTION_MAIN);
        explicitTermuxIntent.addCategory(Intent.CATEGORY_LAUNCHER);
        explicitTermuxIntent.setComponent(new ComponentName(TERMUX_PACKAGE, TERMUX_ACTIVITY));
        explicitTermuxIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (startTermuxIntent(explicitTermuxIntent)) {
            return true;
        }

        Intent termuxIntent = getPackageManager().getLaunchIntentForPackage(TERMUX_PACKAGE);
        if (termuxIntent == null || !isTermuxIntent(termuxIntent)) {
            Toast.makeText(this, R.string.termux_missing, Toast.LENGTH_LONG).show();
            return false;
        }
        termuxIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (startTermuxIntent(termuxIntent)) {
            return true;
        }
        Toast.makeText(this, R.string.termux_missing, Toast.LENGTH_LONG).show();
        return false;
    }

    private boolean isTermuxIntent(Intent intent) {
        ComponentName componentName = intent.getComponent();
        return componentName != null && TERMUX_PACKAGE.equals(componentName.getPackageName());
    }

    private boolean startTermuxIntent(Intent intent) {
        try {
            startActivity(intent);
            return true;
        } catch (RuntimeException ignored) {
            return false;
        }
    }

    private void scheduleReturnToShell() {
        if (returnToShellRunnable != null) {
            mainHandler.removeCallbacks(returnToShellRunnable);
        }
        returnToShellRunnable = new Runnable() {
            @Override
            public void run() {
                if (destroyed) {
                    return;
                }
                Intent shellIntent = new Intent(MainActivity.this, MainActivity.class);
                shellIntent.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                shellIntent.putExtra(INTERNAL_RETURN_EXTRA, true);
                if (debugHealthOverrideActive) {
                    shellIntent.putExtra(DEBUG_HEALTH_URL_EXTRA, healthUrl);
                }
                startActivity(shellIntent);
            }
        };
        mainHandler.postDelayed(returnToShellRunnable, RETURN_AFTER_TERMUX_LAUNCH_MS);
    }

    private void scheduleRecoveryPoll() {
        cancelRecoveryPoll();
        if (recoveryPollAttempts >= RECOVERY_MAX_POLL_ATTEMPTS) {
            setUnavailableBody(R.string.backend_recovery_timeout);
            return;
        }
        recoveryPollRunnable = new Runnable() {
            @Override
            public void run() {
                if (destroyed) {
                    return;
                }
                recoveryPollAttempts += 1;
                startHealthCheck(false);
            }
        };
        mainHandler.postDelayed(recoveryPollRunnable, RECOVERY_POLL_INTERVAL_MS);
    }

    private void cancelRecoveryPoll() {
        if (mainHandler != null && recoveryPollRunnable != null) {
            mainHandler.removeCallbacks(recoveryPollRunnable);
        }
        recoveryPollRunnable = null;
    }

    private void cancelRecoveryCallbacks() {
        cancelRecoveryPoll();
        if (mainHandler != null && returnToShellRunnable != null) {
            mainHandler.removeCallbacks(returnToShellRunnable);
        }
        returnToShellRunnable = null;
    }

    private void setUnavailableBody(int resId) {
        if (unavailableBodyView != null) {
            unavailableBodyView.setText(resId);
        }
    }

    private void recoverFromWebError() {
        checkHealthAndLoad();
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
        cancelRecoveryPoll();
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
                recoverFromWebError();
            }
            super.onReceivedError(view, request, error);
        }

        @Override
        public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
            recoverFromWebError();
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
                        if (!isRecordAudioAppOpAllowed()) {
                            showAudioPermissionBlockedToast();
                            request.deny();
                            return;
                        }
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

    private boolean isRecordAudioAppOpAllowed() {
        if (android.os.Build.VERSION.SDK_INT < 19) {
            return true;
        }
        AppOpsManager appOpsManager = (AppOpsManager) getSystemService(Context.APP_OPS_SERVICE);
        if (appOpsManager == null) {
            return true;
        }
        try {
            int mode = appOpsManager.checkOpNoThrow(
                    AppOpsManager.OPSTR_RECORD_AUDIO,
                    android.os.Process.myUid(),
                    getPackageName());
            return mode == AppOpsManager.MODE_ALLOWED || mode == AppOpsManager.MODE_DEFAULT;
        } catch (RuntimeException ignored) {
            return true;
        }
    }

    private void showAudioPermissionBlockedToast() {
        Toast.makeText(this, R.string.audio_permission_blocked, Toast.LENGTH_LONG).show();
    }
}
