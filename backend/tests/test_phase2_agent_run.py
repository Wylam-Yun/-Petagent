"""Tests for STAB-024/CC-7: AgentRunStore persistence."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from app.pet.state import LockedSQLiteConnection
from app.runtime.agent_run_store import AgentRunStore


def _make_store(max_rows: int = 200) -> AgentRunStore:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    locked = LockedSQLiteConnection(conn)
    return AgentRunStore(locked, max_rows=max_rows)


def _make_run_dict(**overrides) -> dict:
    now = datetime.utcnow().isoformat()
    base = {
        "run_id": "run-test123",
        "event_id": "evt-abc",
        "episode_id": "ep-1",
        "route": "fast",
        "context_profile": "fast_companion",
        "provider": "fast_llm",
        "status": "completed",
        "timings_ms": {"llm": 150, "total": 200},
        "requested_tools": ["weather"],
        "final_action": {"reply": "hello", "mood": "happy"},
        "audio_job_id": "aud-xyz",
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base


def test_save_and_get():
    store = _make_store()
    run = _make_run_dict()
    store.save(run)

    result = store.get("run-test123")
    assert result is not None
    assert result["run_id"] == "run-test123"
    assert result["route"] == "fast"
    assert result["timings_ms"] == {"llm": 150, "total": 200}
    assert result["requested_tools"] == ["weather"]
    assert result["final_action"]["reply"] == "hello"


def test_save_overwrites():
    store = _make_store()
    store.save(_make_run_dict(status="started"))
    store.save(_make_run_dict(status="completed"))

    result = store.get("run-test123")
    assert result["status"] == "completed"


def test_get_missing():
    store = _make_store()
    assert store.get("nonexistent") is None


def test_cap_at_max_rows():
    store = _make_store(max_rows=5)
    for i in range(10):
        store.save(_make_run_dict(
            run_id="run-%03d" % i,
            created_at="2026-01-01T00:%02d:00" % i,
        ))

    assert store.count() == 5
    # Oldest should be gone
    assert store.get("run-000") is None
    assert store.get("run-001") is None
    # Newest should remain
    assert store.get("run-009") is not None


def test_recent():
    store = _make_store()
    for i in range(5):
        store.save(_make_run_dict(
            run_id="run-%03d" % i,
            created_at="2026-01-01T00:%02d:00" % i,
        ))

    recent = store.recent(limit=3)
    assert len(recent) == 3
    # Should be newest first
    assert recent[0]["run_id"] == "run-004"


def test_sanitizes_text():
    store = _make_store()
    store.save(_make_run_dict(
        sanitized_user_text="my api key is sk-abc123secret",
        sanitized_response_text="Bearer token=xyz found",
    ))

    result = store.get("run-test123")
    assert "sk-" not in result["sanitized_user_text"]
    assert "REDACTED" in result["sanitized_user_text"]
    assert "Bearer" not in result["sanitized_response_text"]


def test_handles_missing_fields():
    store = _make_store()
    store.save({"run_id": "run-minimal"})

    result = store.get("run-minimal")
    assert result is not None
    assert result["route"] == ""
    assert result["timings_ms"] == {}
    assert result["requested_tools"] == []
