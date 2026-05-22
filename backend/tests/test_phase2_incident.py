"""Tests for STAB-037/CC-8: Incident breadcrumb store."""
from __future__ import annotations

import sqlite3

from app.pet.state import LockedSQLiteConnection
from app.runtime.incident import IncidentStore


def _make_store(max_rows: int = 500) -> IncidentStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    locked = LockedSQLiteConnection(conn)
    return IncidentStore(locked, max_rows=max_rows)


def test_record_and_recent():
    store = _make_store()
    store.record("provider_error", {"provider": "llm", "error_class": "timeout"})
    store.record("audio_job_failed", {"job_id": "aud-123"})

    recent = store.recent(limit=10)
    assert len(recent) == 2
    # Newest first
    assert recent[0]["kind"] == "audio_job_failed"
    assert recent[0]["payload"]["job_id"] == "aud-123"
    assert recent[1]["kind"] == "provider_error"


def test_cap_at_max_rows():
    store = _make_store(max_rows=5)
    for i in range(10):
        store.record("test_event", {"index": i})

    assert store.count() == 5
    recent = store.recent(limit=10)
    assert len(recent) == 5
    # Newest events should remain
    assert recent[0]["payload"]["index"] == 9


def test_count_empty():
    store = _make_store()
    assert store.count() == 0


def test_record_does_not_raise_on_error():
    """Recording an incident should never crash the caller."""
    store = _make_store()
    # This should succeed without error
    store.record("test", {"data": "value"})
    assert store.count() == 1


# --- Debug API tests ---


def test_debug_runs_requires_token():
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    resp = client.get("/api/debug/runs")
    assert resp.status_code == 403


def test_debug_runs_with_token():
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    token = app.state.internal_token
    client = TestClient(app)

    resp = client.get("/api/debug/runs", headers={"Authorization": "Bearer %s" % token})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "runs" in data
    assert "total" in data


def test_debug_incidents_requires_token():
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    resp = client.get("/api/debug/incidents")
    assert resp.status_code == 403


def test_debug_incidents_with_token():
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    token = app.state.internal_token
    client = TestClient(app)

    # Record an incident first
    app.state.incident_store.record("test", {"data": "value"})

    resp = client.get("/api/debug/incidents", headers={"Authorization": "Bearer %s" % token})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["total"] >= 1
