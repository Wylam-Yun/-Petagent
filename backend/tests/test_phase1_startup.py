"""Tests for STAB-008: Startup/manager backoff flags."""
from __future__ import annotations

from fastapi.testclient import TestClient
from pathlib import Path

from app.main import create_app


def test_core_ready_true_after_lifespan():
    """After lifespan startup, core_ready should be True."""
    app = create_app(testing=True)
    with TestClient(app) as client:
        resp = client.get("/api/health/watchdog")
        assert resp.status_code == 200
        assert resp.json()["core_ready"] is True


def test_providers_ready_true_after_lifespan():
    """After lifespan startup, providers_ready should be True."""
    app = create_app(testing=True)
    with TestClient(app) as client:
        app.state.internal_token = "secret-token"
        resp = client.get(
            "/api/health/deep",
            headers={"Authorization": "Bearer secret-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["providers_ready"] is True


def test_watchdog_includes_core_ready():
    """Watchdog health should include core_ready flag."""
    app = create_app(testing=True)
    with TestClient(app) as client:
        resp = client.get("/api/health/watchdog")
        assert resp.status_code == 200
        assert resp.json()["core_ready"] is True


def test_deep_health_includes_providers_ready():
    """Deep health should include providers_ready flag."""
    app = create_app(testing=True)
    with TestClient(app) as client:
        app.state.internal_token = "secret-token"
        resp = client.get(
            "/api/health/deep",
            headers={"Authorization": "Bearer secret-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["providers_ready"] is True


def test_core_ready_false_before_lifespan():
    """Before lifespan, core_ready should be False."""
    app = create_app(testing=True)
    # Don't enter lifespan context
    assert app.state.core_ready is False
    assert app.state.providers_ready is False


def test_termux_manager_uses_mobile_safe_health_timeouts():
    """Manager health curl budgets should match Phase 1 mobile-safe plan."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "termux_service_manager.sh"
    text = script.read_text()
    assert 'HEALTH_CONNECT_TIMEOUT="${HEALTH_CONNECT_TIMEOUT:-2}"' in text
    assert 'HEALTH_MAX_TIME="${HEALTH_MAX_TIME:-8}"' in text
    assert 'HEALTH_CONFIRM_MAX_TIME="${HEALTH_CONFIRM_MAX_TIME:-15}"' in text
    assert 'WATCHDOG_MAX_TIME="${WATCHDOG_MAX_TIME:-8}"' in text
    assert 'petagent_health_confirm() {' in text
    assert 'curl -fsS --connect-timeout "$HEALTH_CONNECT_TIMEOUT" --max-time "$HEALTH_MAX_TIME"' in text
    assert 'curl -fsS --connect-timeout "$HEALTH_CONNECT_TIMEOUT" --max-time "$HEALTH_CONFIRM_MAX_TIME"' in text
    assert text.count('curl -fsS --connect-timeout "$WATCHDOG_CONNECT_TIMEOUT" --max-time "$WATCHDOG_MAX_TIME"') >= 2


def test_termux_start_services_can_clear_root_stale_lock():
    script = Path(__file__).resolve().parents[2] / "scripts" / "termux_start_services.sh"
    text = script.read_text()
    assert "su -c \"rm -rf '$LOCK_DIR' 2>/dev/null\"" in text
    assert "root-owned stale manager lock blocks startup" in text
    assert "stopping foreign service manager process" in text
    assert "manager lock points to non-manager pid" in text
    assert "stop_duplicate_repo_managers() {" in text
    assert "stopped duplicate repo manager process" in text
    assert "stopping foreign repo manager process" in text
    assert "keeping $kept_pid" in text


def test_termux_manager_can_clear_root_stale_lock():
    script = Path(__file__).resolve().parents[2] / "scripts" / "termux_service_manager.sh"
    text = script.read_text()
    assert 'CHECK_INTERVAL="${CHECK_INTERVAL:-30}"' in text
    assert 'PETAGENT_START_GRACE_SECONDS="${PETAGENT_START_GRACE_SECONDS:-45}"' in text
    assert 'HTTP_FAIL_MAX="${HTTP_FAIL_MAX:-5}"' in text
    assert "HOST=0.0.0.0 PORT=\"$PETAGENT_PORT\" PETAGENT_FOREGROUND=0 sh scripts/start.sh" in text
    assert "PETAGENT_FOREGROUND=1 sh scripts/start.sh" not in text
    assert "remove_stale_lock() {" in text
    assert "su -c \"rm -rf '$LOCK_DIR' 2>/dev/null\"" in text
    assert "remove_stale_lock || true" in text
    assert "Stopping foreign service manager process" in text
    assert "Manager lock points to non-manager pid" in text
    assert "HTTP half-alive state persisted after confirm; restarting" in text
    assert "orphan HTTP half-alive state persisted after confirm" in text
    assert "HTTP health recovered during confirm" in text
    assert "http_fail_count=0" in text


def test_start_script_supports_foreground_runtime_mode():
    script = Path(__file__).resolve().parents[2] / "scripts" / "start.sh"
    text = script.read_text()
    assert 'if [ "${PETAGENT_FOREGROUND:-0}" = "1" ]; then' in text
    assert "PetAgent runtime foreground on $HOST:$PORT" in text
    assert "exec env PYTHONPATH=\"$PROJECT_DIR/backend\" \"$PYTHON_BIN\" -m uvicorn app.main:app" in text
    assert "require_android_runtime_context" in text
    assert "PETAGENT_ALLOW_ROOT_RUNTIME" in text
    assert "Android socket permission requires the inet group (3003)" in text
    assert "PETAGENT_SKIP_ANDROID_CONTEXT_CHECK" in text


def test_termux_scripts_refuse_adb_su_network_context():
    repo = Path(__file__).resolve().parents[2]
    manager_text = (repo / "scripts" / "termux_service_manager.sh").read_text()
    start_services_text = (repo / "scripts" / "termux_start_services.sh").read_text()
    status_text = (repo / "scripts" / "status.sh").read_text()

    for text in (manager_text, start_services_text):
        assert "has_android_inet_group" in text
        assert "refuse_non_termux_network_context" in text
        assert "process_has_android_inet_group" in text
        assert "tr '\\011' ' '" in text
        assert "adb/su u0_a137 lacks Android inet group 3003" in text

    assert "android-context-health-guard-20260530" in manager_text
    assert "without Android inet group 3003" in manager_text
    assert "without valid Termux network context" in start_services_text
    assert "process_state()" in manager_text
    assert "process_state()" in start_services_text
    assert "context: not Termux app network context" in status_text
    assert "cannot start the web server socket" in status_text
    assert "tr '\\011' ' '" in status_text


def test_nubia_deploy_excludes_heavy_runtime_artifacts():
    script = Path(__file__).resolve().parents[2] / "scripts" / "deploy_nubia.sh"
    text = script.read_text()
    for excluded in [
        "--exclude='.git'",
        "--exclude='.venv'",
        "--exclude='backend/data'",
        "--exclude='backend/secrets'",
        "--exclude='backend/static/audio'",
        "--exclude='backend/tests'",
        "--exclude='frontend/node_modules'",
        "--exclude='frontend/src'",
        "--exclude='plan'",
    ]:
        assert excluded in text
    assert "frontend/dist" in text
    assert 'chown -R "$uid:$uid" "$remote_dir"' not in text
    assert "COPYFILE_DISABLE=1 tar" in text
    assert "--format=ustar" in text
    assert 'rm -rf "\\$remote_dir/backend/app" "\\$remote_dir/config" "\\$remote_dir/scripts" "\\$remote_dir/frontend/dist"' in text
    assert "find \"\\$remote_dir\" -name '._*' -type f -delete" in text
    assert "adb-launched background processes do not stay alive reliably" in text
    assert 'START_SERVICES="${START_SERVICES:-1}"' not in text
    assert 'export PATH="$REMOTE_HOME/../usr/bin:$REMOTE_HOME/../usr/bin/applets:/system/bin:/system/xbin:/su/bin"' in text


def test_v18_status_script_exposes_supervisor_state():
    script = Path(__file__).resolve().parents[2] / "scripts" / "status.sh"
    text = script.read_text()

    for expected in [
        "manager: running ($MANAGER_PID)",
        "manager: not running",
        "manager_context: ok",
        "manager_context: missing inet group 3003",
        "manager_context: not running",
        "sshd: listening",
        "sshd: not listening",
        "wake_lock: $(wake_lock_status)",
        "termux_boot: $(termux_boot_status)",
        "termux_package: stopped=$(termux_stopped_state)",
        "frontend_heartbeat_age_s:",
        "watchdog_stuck:",
    ]:
        assert expected in text

    assert "process_has_android_inet_group() {" in text
    assert "termux_service_manager.sh" in text
    assert ".service_manager.sh" in text
    assert "pm list packages" in text
    assert "dumpsys package com.termux" in text
    assert "dumpsys power" in text
    assert "Wake Locks: size=0" in text


def test_v18_start_services_has_safe_status_only_and_explicit_ensure_modes():
    script = Path(__file__).resolve().parents[2] / "scripts" / "termux_start_services.sh"
    text = script.read_text()

    assert "--status-only)" in text
    assert "--ensure|--termux-boot)" in text
    assert 'MODE="status-only"' in text
    assert 'MODE="ensure"' in text
    assert "print_status_only() {" in text
    assert "backend: $(backend_health_status)" in text
    assert "wake_lock: $(wake_lock_status)" in text
    assert "start_services: command mode=$MODE" in text
    assert "start_services: current identity:" in text
    assert "manager candidate pid=$pid" in text
    assert "missing Android inet group 3003" in text

    status_branch = text.index('if [ "$MODE" = "status-only" ]; then')
    ensure_branch = text.index("repair_android_context", status_branch)
    assert status_branch < ensure_branch
    assert "start_manager_if_needed" in text[ensure_branch:]
    assert "scripts/start.sh" not in text


def test_v18_manager_logs_wake_lock_and_browser_relaunch_results():
    script = Path(__file__).resolve().parents[2] / "scripts" / "termux_service_manager.sh"
    text = script.read_text()

    for expected in [
        'FRONTEND_STARTUP_SECONDS="${FRONTEND_STARTUP_SECONDS:-120}"',
        "termux-wake-lock command found",
        "termux-wake-lock returned success",
        "dumpsys not available; wake lock visibility cannot be verified",
        "wake lock post-check:",
        "termux-wake-lock succeeded but dumpsys did not show a Termux wake lock",
        "Frontend heartbeat stale (${heartbeat_age}s); relaunching browser target=$target_url",
        "Browser relaunch $label exit=$cmd_status output=$cmd_output",
        'run_browser_relaunch_command "termux-am start"',
        "termux-am socket unavailable",
        "Termux am wrapper apk missing",
        "WARNING: am command not available; cannot relaunch browser target=$target_url",
        'run_browser_relaunch_command "am start"',
        "android.intent.action.VIEW",
    ]:
        assert expected in text


def test_v18_start_script_warns_but_does_not_start_supervisor():
    script = Path(__file__).resolve().parents[2] / "scripts" / "start.sh"
    text = script.read_text()

    assert "warn_if_supervisor_missing() {" in text
    assert "manager_running() {" in text
    assert "WARNING: PetAgent runtime is healthy but termux_service_manager.sh is not running." in text
    assert (
        "Run scripts/termux_start_services.sh --ensure from the Termux app/SSH context "
        "to restore watchdog, wake lock, and browser recovery."
    ) in text
    assert "warn_if_supervisor_missing" in text
    assert "PetAgent runtime already healthy: $OLD_PID" in text
    assert "PetAgent runtime ready on $HOST:$PORT" in text
    assert "termux_start_services.sh --ensure" in text
    assert "sh scripts/termux_start_services.sh" not in text
