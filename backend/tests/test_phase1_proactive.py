"""Tests for STAB-001: Frontend heartbeat + proactive scheduler."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app
from app.runtime.proactive_scheduler import ProactiveScheduler


def test_heartbeat_endpoint():
    """Heartbeat endpoint should return ok."""
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.post("/api/frontend/heartbeat", json={"user_agent": "test-browser"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_heartbeat_updates_age():
    """Heartbeat should update the scheduler's last_seen_at."""
    app = create_app(testing=True)
    client = TestClient(app)
    # Before heartbeat
    age_before = app.state.proactive_scheduler.heartbeat_age_s()
    assert age_before < 0  # Never seen

    # Send heartbeat
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})

    # After heartbeat
    age_after = app.state.proactive_scheduler.heartbeat_age_s()
    assert 0 <= age_after < 1


def test_watchdog_includes_heartbeat_age():
    """Watchdog health should include frontend_heartbeat_age_s."""
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.get("/api/health/watchdog")
    assert resp.status_code == 200
    assert "frontend_heartbeat_age_s" in resp.json()


def test_proactive_scheduler_enqueue():
    """Scheduler should enqueue events."""
    scheduler = ProactiveScheduler()
    # Enqueue when frontend is stale (never seen)
    # Only deterministic hints should work
    result = scheduler.enqueue("mood_hint", {"mood": "happy"})
    assert result is True
    assert scheduler.queue_depth() == 1


def test_proactive_scheduler_coalescing():
    """Same-kind events in same bucket should coalesce."""
    scheduler = ProactiveScheduler()
    scheduler.record_heartbeat()  # Make frontend not stale

    result1 = scheduler.enqueue("morning", {"text": "good morning"})
    assert result1 is True

    result2 = scheduler.enqueue("morning", {"text": "good morning again"})
    assert result2 is False  # Coalesced
    assert scheduler.queue_depth() == 1


def test_proactive_scheduler_bounded_queue():
    """Queue should not exceed MAX_QUEUE."""
    scheduler = ProactiveScheduler()
    scheduler.record_heartbeat()

    for i in range(25):
        scheduler.enqueue(f"event_{i}", {"i": i}, force=True)

    assert scheduler.queue_depth() <= scheduler.MAX_QUEUE


def test_proactive_scheduler_stale_frontend_blocks_non_deterministic():
    """When frontend is stale, non-deterministic events should be skipped."""
    scheduler = ProactiveScheduler()
    # Frontend never seen = stale
    assert scheduler.is_frontend_stale() is True

    # Non-deterministic event should be skipped
    result = scheduler.enqueue("morning", {"text": "good morning"})
    assert result is False

    # Deterministic hint should work
    result = scheduler.enqueue("mood_hint", {"mood": "happy"})
    assert result is True


def test_proactive_scheduler_drain():
    """Drain should return and remove events."""
    scheduler = ProactiveScheduler()
    scheduler.record_heartbeat()

    scheduler.enqueue("event_1", force=True)
    scheduler.enqueue("event_2", force=True)
    scheduler.enqueue("event_3", force=True)

    drained = scheduler.drain(limit=2)
    assert len(drained) == 2
    assert scheduler.queue_depth() == 1


def test_catch_up_event():
    """Catch_up event should be generated after offline interval."""
    scheduler = ProactiveScheduler()
    # Simulate offline by setting _started_at in the past
    scheduler._started_at = datetime.utcnow() - timedelta(minutes=5)

    event = scheduler.catch_up_event()
    assert event is not None
    assert event["event_type"] == "catch_up"
    assert event["payload"]["offline_seconds"] >= 300


def test_catch_up_event_not_duplicated():
    """Only one catch_up event should be generated."""
    scheduler = ProactiveScheduler()
    scheduler._started_at = datetime.utcnow() - timedelta(minutes=5)

    event1 = scheduler.catch_up_event()
    event2 = scheduler.catch_up_event()
    assert event1 is not None
    assert event2 is None  # Already enqueued


def test_catch_up_event_skips_short_offline():
    """No catch_up event for offline < 60 seconds."""
    scheduler = ProactiveScheduler()
    scheduler._started_at = datetime.utcnow() - timedelta(seconds=30)

    event = scheduler.catch_up_event()
    assert event is None
