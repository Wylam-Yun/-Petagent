"""Single long-lived maintenance thread — replaces per-event daemon threads."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MaintenanceWorker:
    """Single long-lived thread for maintenance tasks.

    Design:
    - Fed by queue.Queue(maxsize=1) — notifications coalesce
    - notify() method: puts to queue (non-blocking, drops if full)
    - Loop: q.get(timeout=300) → calls maintenance_service.tick() → sleep until next slot
    - Wall-clock fallback: tick every 5 minutes regardless of notifications
    - stop() method: sets shutdown flag, joins thread with timeout
    """

    TICK_INTERVAL_SECONDS = 300  # 5 minutes

    def __init__(self, maintenance_service: Any) -> None:
        self._service = maintenance_service
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._shutdown = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="petagent-maintenance",
            daemon=True,
        )

    def start(self) -> None:
        """Start the maintenance worker thread."""
        if not self._thread.is_alive():
            self._thread.start()
            logger.info("Maintenance worker started")

    def notify(self) -> None:
        """Notify the worker that maintenance work is available.

        Non-blocking: drops notification if queue is full (coalesces).
        """
        try:
            self._queue.put_nowait(True)
        except queue.Full:
            pass  # Coalesce — worker will pick it up on next tick

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the maintenance worker thread."""
        self._shutdown.set()
        # Wake up the thread if it's waiting
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("Maintenance worker did not stop within %ss", timeout)
        else:
            logger.info("Maintenance worker stopped")

    def _run(self) -> None:
        """Main worker loop."""
        logger.info("Maintenance worker loop started")
        while not self._shutdown.is_set():
            try:
                # Wait for notification or timeout (wall-clock fallback)
                self._queue.get(timeout=self.TICK_INTERVAL_SECONDS)
            except queue.Empty:
                # Timeout — proceed with tick anyway (wall-clock fallback)
                pass

            if self._shutdown.is_set():
                break

            try:
                self._service.tick()
            except Exception:
                logger.warning("Maintenance tick failed", exc_info=True)

        logger.info("Maintenance worker loop exited")
