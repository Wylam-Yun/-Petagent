"""Tests for STAB-009: Maintenance background worker."""
from __future__ import annotations

import time
import threading
from unittest.mock import MagicMock

from app.runtime.maintenance_worker import MaintenanceWorker


def test_worker_starts_and_stops():
    """Worker should start and stop cleanly."""
    service = MagicMock()
    worker = MaintenanceWorker(service)
    worker.start()
    assert worker._thread.is_alive()
    worker.stop(timeout=2)
    assert not worker._thread.is_alive()


def test_worker_calls_tick_on_notify():
    """Worker should call maintenance_service.tick() when notified."""
    service = MagicMock()
    worker = MaintenanceWorker(service)
    worker.start()
    worker.notify()
    time.sleep(0.2)  # Give worker time to process
    service.tick.assert_called()
    worker.stop(timeout=2)


def test_worker_coalesces_notifications():
    """Multiple rapid notifies should coalesce (queue maxsize=1)."""
    service = MagicMock()
    worker = MaintenanceWorker(service)
    worker.start()

    # Send many rapid notifications
    for _ in range(10):
        worker.notify()

    time.sleep(0.3)
    # Should have ticked at least once, but not 10 times
    # (queue coalesces — worker processes one at a time)
    assert service.tick.call_count >= 1
    assert service.tick.call_count <= 3  # Not 10
    worker.stop(timeout=2)


def test_worker_wall_clock_fallback():
    """Worker should tick on timeout even without notifications."""
    service = MagicMock()
    worker = MaintenanceWorker(service)
    # Set short timeout for test
    worker.TICK_INTERVAL_SECONDS = 0.2
    worker.start()

    # Don't notify — wait for wall-clock fallback
    time.sleep(0.5)
    service.tick.assert_called()
    worker.stop(timeout=2)


def test_worker_stop_joins_thread():
    """stop() should join the thread within timeout."""
    service = MagicMock()
    worker = MaintenanceWorker(service)
    worker.start()

    start = time.monotonic()
    worker.stop(timeout=2)
    elapsed = time.monotonic() - start

    assert elapsed < 2.5  # Should join quickly
    assert not worker._thread.is_alive()


def test_worker_survives_tick_exception():
    """Worker should continue after tick() raises."""
    service = MagicMock()
    service.tick.side_effect = [Exception("boom"), None]
    worker = MaintenanceWorker(service)
    worker.start()

    worker.notify()
    time.sleep(0.3)
    # First tick raises, but worker should still be alive
    assert worker._thread.is_alive()

    worker.notify()
    time.sleep(0.3)
    # Second tick should succeed
    assert service.tick.call_count >= 2
    worker.stop(timeout=2)
