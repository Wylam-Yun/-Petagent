"""Tests for STAB-033: Manager watchdog-stuck detection."""
from __future__ import annotations

from time import perf_counter

from fastapi.testclient import TestClient

from app.main import create_app


def test_watchdog_not_stuck_normal():
    """Watchdog should report stuck=False under normal conditions."""
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.get("/api/health/watchdog")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stuck"] is False
    assert body["event_loop_tick_age_s"] < 5
    assert body["agent_inflight_age_s"] < 0  # Not inflight


def test_watchdog_stuck_on_stale_tick():
    """Watchdog should report stuck=True when event_loop_tick is stale."""
    app = create_app(testing=True)
    # Simulate stale tick by setting it far in the past
    app.state.dispatcher.event_loop_tick = perf_counter() - 120
    client = TestClient(app)
    resp = client.get("/api/health/watchdog")
    body = resp.json()
    assert body["stuck"] is True
    assert body["event_loop_tick_age_s"] > 90


def test_watchdog_stuck_on_stale_agent():
    """Watchdog should report stuck=True when agent_inflight is stale."""
    app = create_app(testing=True)
    # Simulate stale agent inflight
    app.state.dispatcher.agent_inflight_start = perf_counter() - 120
    client = TestClient(app)
    resp = client.get("/api/health/watchdog")
    body = resp.json()
    assert body["stuck"] is True
    assert body["agent_inflight_age_s"] > 90


def test_watchdog_stuck_on_stale_provider():
    """Watchdog should report stuck=True when a provider call is stale."""
    app = create_app(testing=True)
    app.state.provider_gate.acquire("llm_slow")
    app.state.provider_gate._started_at["llm_slow"] = perf_counter() - 120
    client = TestClient(app)
    try:
        resp = client.get("/api/health/watchdog")
        body = resp.json()
        assert body["stuck"] is True
        assert body["provider_inflight_age_s"] > 90
    finally:
        app.state.provider_gate.release("llm_slow")


def test_watchdog_not_stuck_with_recent_tick():
    """Watchdog should report stuck=False when tick is recent."""
    app = create_app(testing=True)
    # Set recent tick
    app.state.dispatcher.event_loop_tick = perf_counter() - 10
    app.state.dispatcher.agent_inflight_start = 0  # Not inflight
    client = TestClient(app)
    resp = client.get("/api/health/watchdog")
    body = resp.json()
    assert body["stuck"] is False
