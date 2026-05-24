"""Proactive event scheduler — ticks independently of browser polling."""
from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProactiveScheduler:
    """Backend-driven proactive event scheduler.

    Design:
    - Ticks independently of browser
    - Bounded queue of max 20 proactive events
    - Coalesces same-kind events in 15-min buckets
    - When frontend heartbeat is stale (>90s): no LLM/TTS calls, only deterministic hints
    - After restart: one catch_up event summarizing offline interval
    """

    MAX_QUEUE = 20
    COALESCE_BUCKET_MINUTES = 15
    STALE_HEARTBEAT_SECONDS = 90

    def __init__(self) -> None:
        self._events: deque = deque(maxlen=self.MAX_QUEUE)
        self._lock = threading.Lock()
        self._last_heartbeat_at: Optional[datetime] = None
        self._started_at = datetime.utcnow()

    def record_heartbeat(self, user_agent_hash: str = "") -> None:
        """Record a frontend heartbeat."""
        with self._lock:
            self._last_heartbeat_at = datetime.utcnow()

    def heartbeat_age_s(self) -> float:
        """Seconds since last frontend heartbeat, or -1 if never seen."""
        with self._lock:
            if self._last_heartbeat_at is None:
                return -1.0
            return (datetime.utcnow() - self._last_heartbeat_at).total_seconds()

    def is_frontend_stale(self) -> bool:
        """True if frontend heartbeat is older than STALE_HEARTBEAT_SECONDS."""
        age = self.heartbeat_age_s()
        if age < 0:
            return True  # Never seen
        return age > self.STALE_HEARTBEAT_SECONDS

    def enqueue(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> bool:
        """Enqueue a proactive event. Returns True if enqueued.

        Coalesces same-kind events within COALESCE_BUCKET_MINUTES window.
        If frontend is stale and not force, only deterministic hints are enqueued.
        """
        if not force and self.is_frontend_stale():
            # Only allow deterministic hints when frontend is stale
            deterministic_types = {"mood_hint", "energy_hint", "state_hint"}
            if event_type not in deterministic_types:
                logger.debug("Skipping proactive event %s (frontend stale)", event_type)
                return False

        now = datetime.utcnow()
        bucket = now.replace(
            minute=(now.minute // self.COALESCE_BUCKET_MINUTES) * self.COALESCE_BUCKET_MINUTES,
            second=0,
            microsecond=0,
        )

        with self._lock:
            # Check for coalescing: same event_type in same bucket
            for existing in self._events:
                if (
                    existing["event_type"] == event_type
                    and existing.get("bucket") == bucket.isoformat()
                ):
                    logger.debug("Coalescing proactive event %s in bucket %s", event_type, bucket)
                    return False

            if len(self._events) >= self.MAX_QUEUE:
                # Drop oldest
                self._events.popleft()

            self._events.append({
                "event_type": event_type,
                "payload": payload or {},
                "bucket": bucket.isoformat(),
                "enqueued_at": now.isoformat(),
            })
            logger.info("Enqueued proactive event: %s", event_type)
            return True

    def drain(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Drain up to limit events from the queue."""
        with self._lock:
            events = []
            for _ in range(min(limit, len(self._events))):
                events.append(self._events.popleft())
        return events

    def catch_up_event(self) -> Optional[Dict[str, Any]]:
        """Generate a catch_up event after restart summarizing offline interval."""
        with self._lock:
            # Check if we already enqueued a catch_up
            for existing in self._events:
                if existing["event_type"] == "catch_up":
                    return None

            offline_seconds = (datetime.utcnow() - self._started_at).total_seconds()
            if offline_seconds < 60:
                return None

            event = {
                "event_type": "catch_up",
                "payload": {
                    "offline_seconds": int(offline_seconds),
                    "message": f"豆豆 was offline for {int(offline_seconds)} seconds",
                },
                "bucket": self._started_at.isoformat(),
                "enqueued_at": datetime.utcnow().isoformat(),
            }
            self._events.append(event)
            return event

    def queue_depth(self) -> int:
        """Current queue depth."""
        with self._lock:
            return len(self._events)
