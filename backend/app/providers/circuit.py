"""Provider circuit breaker — skips primary after repeated failures."""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from app.providers.errors import ProviderError

logger = logging.getLogger(__name__)


class ProviderCircuit:
    """Tracks recent failures and opens circuit when threshold is exceeded.

    Design:
    - Rolling window of 60 seconds
    - If failure count >= threshold (default 5) within window, open circuit
    - Circuit stays open for cooldown_seconds (default 60)
    - After cooldown, circuit half-closes: next call goes through, success closes it
    - Thread-safe
    """

    def __init__(
        self,
        name: str = "",
        threshold: int = 5,
        window_seconds: float = 60.0,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self.name = name
        self.threshold = threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._failures: list[float] = []
        self._opened_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        """True if circuit is open (primary should be skipped)."""
        with self._lock:
            if self._opened_at is None:
                return False
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.cooldown_seconds:
                # Half-close: allow one attempt
                return False
            return True

    def record_success(self) -> None:
        """Record a successful call — closes circuit."""
        with self._lock:
            self._opened_at = None
            self._failures.clear()

    def record_failure(self) -> None:
        """Record a failed call — may open circuit."""
        now = time.monotonic()
        with self._lock:
            # Prune old failures outside window
            cutoff = now - self.window_seconds
            self._failures = [t for t in self._failures if t > cutoff]
            self._failures.append(now)

            if len(self._failures) >= self.threshold and self._opened_at is None:
                self._opened_at = now
                logger.warning(
                    "Circuit %s opened after %d failures in %ds",
                    self.name, len(self._failures), int(self.window_seconds),
                )

    def reset(self) -> None:
        """Manually reset the circuit."""
        with self._lock:
            self._opened_at = None
            self._failures.clear()
