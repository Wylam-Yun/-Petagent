"""Tests for STAB-015: SQLite AudioJobStore + write-through AudioJobManager."""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

from app.pet.state import LockedSQLiteConnection
from app.runtime.audio_job_store import AudioJobStore
from app.runtime.audio_jobs import AudioJob, AudioJobManager


def _make_connection() -> LockedSQLiteConnection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return LockedSQLiteConnection(conn)


def _make_store() -> AudioJobStore:
    return AudioJobStore(_make_connection())


def _make_manager(store: AudioJobStore | None = None, slow_tts: bool = False) -> AudioJobManager:
    tts = MagicMock()
    tts.name = "mock_tts"
    if slow_tts:
        import threading
        blocker = threading.Event()
        tts._blocker = blocker
        tts.synthesize.side_effect = lambda *a, **kw: blocker.wait(timeout=30) or "http://example.com/audio.mp3"
    else:
        tts.synthesize.return_value = "http://example.com/audio.mp3"
    return AudioJobManager(tts, store=store, max_workers=1, max_jobs=50)


# --- Schema contract ---


def test_audio_job_table_columns_match_dataclass():
    """Persisted columns should match AudioJob fields + V1.1 persistence fields."""
    store = _make_store()
    # All fields from AudioJob.dict() plus V1.1 fields
    expected_columns = {
        "job_id", "run_id", "event_id", "session_id", "status",
        "text", "voice_style", "provider", "voice_url", "audio_path",
        "error", "error_class", "failure_reason", "timings_json",
        "created_at", "updated_at", "completed_at", "expires_at", "superseded_by",
    }
    conn = store.connection
    rows = conn.execute("PRAGMA table_info(audio_job)").fetchall()
    actual_columns = {row["name"] for row in rows}
    assert expected_columns == actual_columns, (
        f"Missing: {expected_columns - actual_columns}, Extra: {actual_columns - expected_columns}"
    )


# --- Save / Get round-trip ---


def test_save_and_get_round_trip():
    store = _make_store()
    job = {
        "job_id": "aud-test123",
        "run_id": "run-1",
        "event_id": "evt-1",
        "session_id": "sess-1",
        "status": "pending",
        "text": "hello",
        "voice_style": "soft",
        "provider": "tts",
        "voice_url": None,
        "audio_path": None,
        "error": None,
        "error_class": None,
        "failure_reason": "",
        "timings_ms": {"tts": 100},
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "completed_at": None,
        "expires_at": None,
        "superseded_by": None,
    }
    store.save(job)
    fetched = store.get("aud-test123")
    assert fetched is not None
    assert fetched["job_id"] == "aud-test123"
    assert fetched["status"] == "pending"
    assert fetched["text"] == "hello"
    assert fetched["timings_ms"] == {"tts": 100}


def test_get_returns_none_for_missing():
    store = _make_store()
    assert store.get("nonexistent") is None


# --- mark_restart_failed ---


def test_mark_restart_failed_updates_pending_and_running():
    store = _make_store()
    for status in ("pending", "running", "ready", "failed"):
        store.save({
            "job_id": f"aud-{status}",
            "status": status,
            "text": "test",
            "voice_style": "soft",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        })

    count = store.mark_restart_failed()
    assert count == 2  # pending + running

    for status in ("pending", "running"):
        job = store.get(f"aud-{status}")
        assert job["status"] == "failed_runtime_restart"
        assert job["failure_reason"] == "runtime_restarted"
        assert job["completed_at"] is not None

    # Unaffected
    assert store.get("aud-ready")["status"] == "ready"
    assert store.get("aud-failed")["status"] == "failed"


# --- mark_shutdown_failed ---


def test_mark_shutdown_failed_updates_pending_and_running():
    store = _make_store()
    for status in ("pending", "running", "ready"):
        store.save({
            "job_id": f"aud-{status}",
            "status": status,
            "text": "test",
            "voice_style": "soft",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        })

    count = store.mark_shutdown_failed()
    assert count == 2

    for status in ("pending", "running"):
        job = store.get(f"aud-{status}")
        assert job["status"] == "failed_shutdown"
        assert job["failure_reason"] == "process_shutdown"

    assert store.get("aud-ready")["status"] == "ready"


# --- Per-session supersede persists across restart ---


def test_superseded_job_persisted_and_queryable():
    store = _make_store()
    # Simulate a superseded job
    store.save({
        "job_id": "aud-old",
        "session_id": "sess-1",
        "status": "superseded",
        "text": "old message",
        "voice_style": "soft",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:01",
        "superseded_by": "aud-new",
    })
    job = store.get("aud-old")
    assert job is not None
    assert job["status"] == "superseded"
    assert job["superseded_by"] == "aud-new"


# --- cleanup_expired ---


def test_cleanup_expired_removes_old_terminal_jobs():
    store = _make_store()
    # Old terminal job
    store.save({
        "job_id": "aud-old-done",
        "status": "ready",
        "text": "done",
        "voice_style": "soft",
        "created_at": "2020-01-01T00:00:00",
        "updated_at": "2020-01-01T00:00:00",
    })
    # Recent terminal job
    from datetime import datetime
    store.save({
        "job_id": "aud-new-done",
        "status": "ready",
        "text": "done",
        "voice_style": "soft",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    })

    deleted = store.cleanup_expired(ttl_seconds=900)
    assert deleted == 1
    assert store.get("aud-old-done") is None
    assert store.get("aud-new-done") is not None


# --- count_by_status ---


def test_count_by_status():
    store = _make_store()
    for i in range(3):
        store.save({
            "job_id": f"aud-p{i}",
            "status": "pending",
            "text": "test",
            "voice_style": "soft",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        })
    store.save({
        "job_id": "aud-ready1",
        "status": "ready",
        "text": "test",
        "voice_style": "soft",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    })
    assert store.count_by_status("pending") == 3
    assert store.count_by_status("ready") == 1
    assert store.count_by_status("failed") == 0


# --- AudioJobManager write-through integration ---


def test_manager_enqueue_persists_to_store():
    store = _make_store()
    mgr = _make_manager(store, slow_tts=True)
    job_id = mgr.enqueue("hello world", session_id="sess-1")
    # Should be in both memory and SQLite (still pending because TTS is blocked)
    job_mem = mgr.get(job_id)
    assert job_mem is not None
    job_db = store.get(job_id)
    assert job_db is not None
    assert job_db["status"] == "pending"
    assert job_db["text"] == "hello world"
    mgr.tts_provider._blocker.set()  # unblock TTS


def test_manager_get_falls_back_to_store_after_restart():
    """Simulate restart: in-memory cache is empty, but SQLite has the job."""
    store = _make_store()
    store.save({
        "job_id": "aud-old-job",
        "status": "ready",
        "text": "hello",
        "voice_style": "soft",
        "run_id": "run-1",
        "event_id": "evt-1",
        "session_id": "sess-1",
        "provider": "tts",
        "voice_url": "http://example.com/audio.mp3",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:01",
    })

    # New manager (simulates restart — empty in-memory cache)
    mgr = _make_manager(store)
    job = mgr.get("aud-old-job")
    assert job is not None
    assert job.status == "ready"
    assert job.voice_url == "http://example.com/audio.mp3"


def test_manager_mark_restart_failed():
    store = _make_store()
    mgr = _make_manager(store, slow_tts=True)
    mgr.enqueue("test1", session_id="sess-1")
    mgr.enqueue("test2", session_id="sess-2")

    count = mgr.mark_restart_failed()
    assert count == 2

    # All should be failed_runtime_restart in store
    assert store.count_by_status("failed_runtime_restart") == 2
    assert store.count_by_status("pending") == 0
    mgr.tts_provider._blocker.set()


def test_manager_mark_shutdown_failed():
    store = _make_store()
    mgr = _make_manager(store, slow_tts=True)
    mgr.enqueue("test1", session_id="sess-1")

    count = mgr.mark_shutdown_failed()
    assert count == 1
    assert store.count_by_status("failed_shutdown") == 1
    mgr.tts_provider._blocker.set()


# --- Structured 404 test ---


def test_structured_404_for_restart_failed_job():
    """Restart-failed jobs are now visible (with error_class) so retry is reachable."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    store = app.state.audio_job_store
    # Simulate a restart-failed job in the store
    store.save({
        "job_id": "aud-restart-lost",
        "status": "failed_runtime_restart",
        "text": "lost message",
        "voice_style": "soft",
        "failure_reason": "runtime_restarted",
        "error_class": "infrastructure",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:01",
        "completed_at": "2026-01-01T00:00:01",
    })

    client = TestClient(app)
    resp = client.get("/api/audio/jobs/aud-restart-lost")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed_runtime_restart"
    assert body["error_class"] == "infrastructure"


def test_structured_404_for_shutdown_failed_job():
    """Shutdown-failed jobs also return structured 404."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    store = app.state.audio_job_store
    store.save({
        "job_id": "aud-shutdown-lost",
        "status": "failed_shutdown",
        "text": "lost message",
        "voice_style": "soft",
        "failure_reason": "process_shutdown",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:01",
        "completed_at": "2026-01-01T00:00:01",
    })

    client = TestClient(app)
    resp = client.get("/api/audio/jobs/aud-shutdown-lost")
    # Shutdown-failed jobs are not treated as 404 — only restart-failed is
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed_shutdown"
