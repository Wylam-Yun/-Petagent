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
    assert '--connect-timeout 1 --max-time 2 "http://127.0.0.1:$PETAGENT_PORT/api/health"' in text
    assert text.count('--connect-timeout 1 --max-time 3 "http://127.0.0.1:$PETAGENT_PORT/api/health/watchdog"') >= 2


def test_termux_start_services_can_clear_root_stale_lock():
    script = Path(__file__).resolve().parents[2] / "scripts" / "termux_start_services.sh"
    text = script.read_text()
    assert "su -c \"rm -rf '$LOCK_DIR' 2>/dev/null\"" in text
    assert "root-owned stale manager lock blocks startup" in text
    assert "stopping foreign service manager process" in text
    assert "manager lock points to non-manager pid" in text


def test_termux_manager_can_clear_root_stale_lock():
    script = Path(__file__).resolve().parents[2] / "scripts" / "termux_service_manager.sh"
    text = script.read_text()
    assert "remove_stale_lock() {" in text
    assert "su -c \"rm -rf '$LOCK_DIR' 2>/dev/null\"" in text
    assert "remove_stale_lock || true" in text
    assert "Stopping foreign service manager process" in text
    assert "Manager lock points to non-manager pid" in text


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
    assert "find \"\\$remote_dir\" -name '._*' -type f -delete" in text
    assert "adb-launched background processes do not stay alive reliably" in text
    assert 'START_SERVICES="${START_SERVICES:-1}"' not in text
    assert 'export PATH="$REMOTE_HOME/../usr/bin:$REMOTE_HOME/../usr/bin/applets:/system/bin:/system/xbin:/su/bin"' in text
