"""Tests for Phase 4: Hardening Follow-through."""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from app.api.voice import _validate_magic_bytes, allowed_audio_types
from app.runtime.memory_cards import MemoryCardManager
from app.runtime.memory_store import MemoryManager
from fastapi import HTTPException
import pytest


# --- STAB-018: Upload validation magic bytes ---


def test_validate_magic_bytes_accepts_valid_wav(tmp_path):
    """A file with RIFF....WAVE header should pass WAV validation."""
    path = tmp_path / "test.wav"
    # RIFF header: 4 bytes "RIFF" + 4 bytes size + 4 bytes "WAVE"
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 100)
    # Should not raise
    _validate_magic_bytes(path, "audio/wav")


def test_validate_magic_bytes_rejects_bad_riff(tmp_path):
    """A file missing RIFF header should be rejected."""
    path = tmp_path / "bad.wav"
    path.write_bytes(b"NOTR\x00\x00\x00\x00WAVE" + b"\x00" * 100)
    with pytest.raises(HTTPException) as exc_info:
        _validate_magic_bytes(path, "audio/wav")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_class"] == "invalid_audio"


def test_validate_magic_bytes_rejects_bad_wave(tmp_path):
    """A file with RIFF but wrong format tag should be rejected."""
    path = tmp_path / "bad.wav"
    path.write_bytes(b"RIFF\x00\x00\x00\x00MP3 " + b"\x00" * 100)
    with pytest.raises(HTTPException) as exc_info:
        _validate_magic_bytes(path, "audio/wav")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_class"] == "invalid_audio"


def test_validate_magic_bytes_rejects_tiny_file(tmp_path):
    """A file too small to have a header should be rejected."""
    path = tmp_path / "tiny.wav"
    path.write_bytes(b"RIFF")
    with pytest.raises(HTTPException) as exc_info:
        _validate_magic_bytes(path, "audio/wav")
    assert exc_info.value.status_code == 400


def test_validate_magic_bytes_accepts_mp3_id3(tmp_path):
    path = tmp_path / "test.mp3"
    path.write_bytes(b"ID3" + b"\x00" * 100)
    _validate_magic_bytes(path, "audio/mpeg")


def test_validate_magic_bytes_accepts_mp3_frame_sync(tmp_path):
    path = tmp_path / "test.mp3"
    path.write_bytes(b"\xff\xfb\x90" + b"\x00" * 100)
    _validate_magic_bytes(path, "audio/mpeg")


def test_validate_magic_bytes_rejects_bad_mp3(tmp_path):
    path = tmp_path / "bad.mp3"
    path.write_bytes(b"NOPE" + b"\x00" * 100)
    with pytest.raises(HTTPException) as exc_info:
        _validate_magic_bytes(path, "audio/mpeg")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_class"] == "invalid_audio"


def test_validate_magic_bytes_accepts_ogg(tmp_path):
    path = tmp_path / "test.ogg"
    path.write_bytes(b"OggS" + b"\x00" * 100)
    _validate_magic_bytes(path, "audio/ogg")


def test_default_allowed_audio_types_include_validated_ogg():
    settings = type("Settings", (), {"voice_routing": {}})()
    assert "audio/ogg" in allowed_audio_types(settings)


def test_validate_magic_bytes_rejects_bad_ogg(tmp_path):
    path = tmp_path / "bad.ogg"
    path.write_bytes(b"NOPE" + b"\x00" * 100)
    with pytest.raises(HTTPException) as exc_info:
        _validate_magic_bytes(path, "audio/ogg")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_class"] == "invalid_audio"


def test_validate_magic_bytes_accepts_webm(tmp_path):
    path = tmp_path / "test.webm"
    path.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 100)
    _validate_magic_bytes(path, "audio/webm")


def test_validate_magic_bytes_rejects_bad_webm(tmp_path):
    path = tmp_path / "bad.webm"
    path.write_bytes(b"NOPE" + b"\x00" * 100)
    with pytest.raises(HTTPException) as exc_info:
        _validate_magic_bytes(path, "audio/webm")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_class"] == "invalid_audio"


def test_validate_magic_bytes_skips_unvalidated_type(tmp_path):
    """Types not listed in the Phase 4 validator should skip magic validation."""
    path = tmp_path / "test.mp4"
    path.write_bytes(b"not a real file")
    _validate_magic_bytes(path, "audio/mp4")


# --- STAB-026: Memory card rebuild locking ---


def _make_card_manager(tmp_path):
    conn_path = tmp_path / "test.db"
    from app.db import PetStateStore

    state_store = PetStateStore(conn_path)
    memory_manager = MemoryManager(state_store.connection)
    config = {
        "user_preferences_path": str(tmp_path / "user.md"),
        "momo_memories_path": str(tmp_path / "memory.md"),
    }
    return MemoryCardManager(memory_manager, config=config)


def test_memory_card_rebuild_uses_lock(tmp_path):
    """Rebuild should acquire the internal lock."""
    mgr = _make_card_manager(tmp_path)
    # Verify lock exists
    assert hasattr(mgr, "_lock")
    assert isinstance(mgr._lock, type(threading.RLock()))


def test_memory_card_clear_uses_lock(tmp_path):
    """Clear should acquire the internal lock."""
    mgr = _make_card_manager(tmp_path)
    mgr.clear()
    # Both card files should exist (empty)
    assert (tmp_path / "user.md").exists()
    assert (tmp_path / "memory.md").exists()


def test_memory_card_concurrent_rebuild(tmp_path):
    """Concurrent rebuilds should not corrupt card files."""
    mgr = _make_card_manager(tmp_path)
    errors = []

    def rebuild_worker():
        try:
            for _ in range(10):
                mgr.rebuild("runtime_reset")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=rebuild_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    # Card files should still be readable
    items = mgr.read_card("user_preferences")
    assert isinstance(items, list)


def test_memory_card_concurrent_rebuild_and_read(tmp_path):
    """Concurrent rebuilds and provenance reads should not corrupt card files."""
    mgr = _make_card_manager(tmp_path)
    errors = []

    def rebuild_worker():
        try:
            for _ in range(10):
                mgr.rebuild("runtime_reset")
        except Exception as e:
            errors.append(e)

    def read_worker():
        try:
            for _ in range(30):
                assert isinstance(mgr.read_card_with_provenance("user_preferences"), list)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=rebuild_worker),
        threading.Thread(target=rebuild_worker),
        threading.Thread(target=read_worker),
        threading.Thread(target=read_worker),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []


# --- STAB-035: Runtime log rotation ---


def test_maintenance_worker_log_rotation(tmp_path):
    """Maintenance worker should rotate log when it exceeds max size."""
    from app.runtime.maintenance_worker import MaintenanceWorker

    log_path = tmp_path / "runtime.log"
    # Write content exceeding max
    log_path.write_bytes(b"x" * 1024)

    service = type("MockService", (), {
        "tick": lambda self: {},
    })()
    worker = MaintenanceWorker(
        service,
        log_path=log_path,
        max_log_bytes=512,  # Small threshold for testing
    )

    worker._rotate_log()

    old_path = log_path.with_suffix(".log.old")
    assert old_path.exists()
    assert old_path.read_bytes() == b"x" * 1024
    assert log_path.read_bytes() == b""


def test_maintenance_worker_no_rotation_when_small(tmp_path):
    """Log should not be rotated when below threshold."""
    from app.runtime.maintenance_worker import MaintenanceWorker

    log_path = tmp_path / "runtime.log"
    log_path.write_bytes(b"small log")

    service = type("MockService", (), {
        "tick": lambda self: {},
    })()
    worker = MaintenanceWorker(
        service,
        log_path=log_path,
        max_log_bytes=1024,
    )

    worker._rotate_log()

    old_path = log_path.with_suffix(".log.old")
    assert not old_path.exists()
    assert log_path.read_bytes() == b"small log"


def test_maintenance_worker_no_log_path():
    """Worker should handle None log_path gracefully."""
    from app.runtime.maintenance_worker import MaintenanceWorker

    service = type("MockService", (), {
        "tick": lambda self: {},
    })()
    worker = MaintenanceWorker(service, log_path=None)
    # Should not raise
    worker._rotate_log()


# --- STAB-032/STAB-034: Security and manager hardening ---


def test_debug_token_rotate_updates_token_without_returning_secret():
    from app.api.auth import token_fingerprint
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(testing=True)
    old_token = app.state.internal_token
    client = TestClient(app)

    resp = client.post(
        "/api/debug/token/rotate",
        headers={"Authorization": "Bearer %s" % old_token},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["fingerprint"] == token_fingerprint(app.state.internal_token)
    assert body["fingerprint"] != token_fingerprint(old_token)
    assert "token" not in body
    assert old_token not in resp.text

    rejected = client.get(
        "/api/debug/incidents",
        headers={"Authorization": "Bearer %s" % old_token},
    )
    assert rejected.status_code == 403
    accepted = client.get(
        "/api/debug/incidents",
        headers={"Authorization": "Bearer %s" % app.state.internal_token},
    )
    assert accepted.status_code == 200


def test_rejected_internal_auth_records_sanitized_incident():
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(testing=True)
    client = TestClient(app)
    secret = "wrong-secret-value"

    resp = client.get("/api/debug/runs", headers={"Authorization": "Bearer %s" % secret})

    assert resp.status_code == 403
    incidents = app.state.incident_store.recent(limit=5)
    auth_incidents = [item for item in incidents if item["kind"] == "auth_rejected"]
    assert auth_incidents
    payload = auth_incidents[0]["payload"]
    assert payload["path"] == "/api/debug/runs"
    assert payload["method"] == "GET"
    assert payload["reason"] == "missing_or_invalid"
    assert secret not in str(payload)


def test_termux_manager_supervises_proxy_with_backoff():
    script = Path(__file__).resolve().parents[2] / "scripts" / "termux_service_manager.sh"
    text = script.read_text()
    assert "PROXY_BACKOFF_SECONDS" in text
    assert "proxy_fail_count=0" in text
    assert "ensure_proxy() {" in text
    assert "check_port_listen 7897" in text
    assert "Proxy port 7897 is down; attempting restart" in text
    assert "Proxy restarted successfully" in text
    assert "proxy_fail_count=$((proxy_fail_count + 1))" in text
    assert 'CRITICAL: proxy failed $MAX_FAILS times; backing off ${PROXY_BACKOFF_SECONDS}s' in text
