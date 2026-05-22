"""Tests for STAB-008: Startup/manager backoff flags."""
from __future__ import annotations

from fastapi.testclient import TestClient

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
