"""Single long-lived maintenance thread — replaces per-event daemon threads."""
from __future__ import annotations

import logging
import os
import queue
import shutil
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_LOG_BYTES = 512 * 1024  # 512 KB


class MaintenanceWorker:
    """Single long-lived thread for maintenance tasks.

Design:
- Fed by queue.Queue(maxsize=1) — notifications coalesce
- notify() method: puts to queue (non-blocking, drops if full)
- Loop: q.get(timeout=300) → notification calls maintenance_service.tick(force=True)
- Wall-clock fallback: tick every 5 minutes with normal interval gating
    - stop() method: sets shutdown flag, joins thread with timeout
    """

    TICK_INTERVAL_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        maintenance_service: Any,
        log_path: Optional[Path] = None,
        max_log_bytes: int = DEFAULT_MAX_LOG_BYTES,
    ) -> None:
        self._service = maintenance_service
        self._log_path = log_path
        self._max_log_bytes = max_log_bytes
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

    def _rotate_log(self) -> None:
        """Rotate runtime.log if it exceeds max size."""
        if self._log_path is None:
            return
        try:
            if not self._log_path.exists():
                return
            size = self._log_path.stat().st_size
            if size <= self._max_log_bytes:
                return
            old_path = self._log_path.with_suffix(".log.old")
            # Copy in chunks so old Android devices never hold the full log in memory.
            with self._log_path.open("rb") as src, old_path.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=64 * 1024)
            with self._log_path.open("wb"):
                pass
            logger.info("Rotated runtime.log (%d bytes)", size)
        except OSError:
            pass  # Best-effort; don't crash maintenance over log rotation

    def _run(self) -> None:
        """Main worker loop."""
        logger.info("Maintenance worker loop started")
        while not self._shutdown.is_set():
            try:
                # Wait for notification or timeout (wall-clock fallback)
                notified = self._queue.get(timeout=self.TICK_INTERVAL_SECONDS)
            except queue.Empty:
                # Timeout — proceed with tick anyway (wall-clock fallback)
                notified = False

            if self._shutdown.is_set():
                break

            try:
                self._service.tick(force=bool(notified))
            except Exception:
                logger.warning("Maintenance tick failed", exc_info=True)

            # Runtime log rotation
            try:
                self._rotate_log()
            except Exception:
                pass  # Best-effort

        logger.info("Maintenance worker loop exited")
