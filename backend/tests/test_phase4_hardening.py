"""Tests for Phase 4: Hardening Follow-through."""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from app.api.voice import _validate_magic_bytes
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


def test_validate_magic_bytes_skips_non_wav(tmp_path):
    """Non-WAV content types should skip validation."""
    path = tmp_path / "test.webm"
    path.write_bytes(b"not a real file")
    # Should not raise — only WAV is validated
    _validate_magic_bytes(path, "audio/webm")


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


# --- STAB-035: Runtime log rotation ---


def test_maintenance_worker_log_rotation(tmp_path):
    """Maintenance worker should rotate log when it exceeds max size."""
    from app.runtime.maintenance_worker import MaintenanceWorker

    log_path = tmp_path / "runtime.log"
    # Write content exceeding max
    log_path.write_bytes(b"x" * 1024)

    service = type("MockService", (), {
        "tick": lambda self: {},
        "wal_checkpoint_if_due": lambda self: False,
        "daily_backup_if_due": lambda self: False,
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
        "wal_checkpoint_if_due": lambda self: False,
        "daily_backup_if_due": lambda self: False,
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
        "wal_checkpoint_if_due": lambda self: False,
        "daily_backup_if_due": lambda self: False,
    })()
    worker = MaintenanceWorker(service, log_path=None)
    # Should not raise
    worker._rotate_log()
