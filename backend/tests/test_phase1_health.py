"""Tests for STAB-036: Health split (light/watchdog/deep)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_light_returns_expected_fields():
    """Light health should return ok, name, version, pid, started_at."""
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "name" in body
    assert "version" in body
    assert "pid" in body
    assert "started_at" in body


def test_health_watchdog_returns_expected_fields():
    """Watchdog health should return counters."""
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.get("/api/health/watchdog")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "core_ready" in body
    assert "shutdown_in_progress" in body
    assert "event_loop_tick_age_s" in body
    assert "active_requests" in body
    assert "agent_inflight_age_s" in body
    assert "audio_queue_depth" in body


def test_health_watchdog_reflects_shutdown():
    """Watchdog should reflect shutdown_in_progress state."""
    app = create_app(testing=True)
    app.state.shutdown_in_progress = True
    client = TestClient(app)
    resp = client.get("/api/health/watchdog")
    assert resp.json()["shutdown_in_progress"] is True


def test_health_deep_requires_token():
    """Deep health should return 403 without token."""
    app = create_app(testing=True)
    app.state.internal_token = "secret-token"
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/health/deep")
    assert resp.status_code == 403


def test_health_deep_accepts_valid_token():
    """Deep health should return 200 with valid token."""
    app = create_app(testing=True)
    app.state.internal_token = "secret-token"
    client = TestClient(app)
    resp = client.get(
        "/api/health/deep",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "db_quick_check" in body
    assert "wal_bytes" in body
    assert "audio_pending" in body
    assert "candidate_backlog" in body


def test_health_endpoint_not_gated_by_shutdown():
    """All health endpoints should work during shutdown."""
    app = create_app(testing=True)
    app.state.shutdown_in_progress = True
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health/watchdog").status_code == 200
