"""Bounded executor for heavy API routes (text/voice pipelines)."""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class AgentWorkExecutor:
    """Bounded ThreadPoolExecutor for text/voice pipelines.

    When the queue is full (in-flight tasks >= max_workers + max_queue),
    raises ServerBusyError instead of blocking.
    """

    def __init__(self, max_workers: int = 4, max_queue: int = 8) -> None:
        self.max_workers = max_workers
        self.max_queue = max_queue
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._inflight = 0
        self._lock = threading.Lock()

    async def submit(
        self,
        fn: Callable[..., Any],
        timeout_s: float = 120,
    ) -> Any:
        """Submit work to the bounded executor.

        Returns the result of fn().
        Raises ServerBusyError if the queue is full.
        """
        with self._lock:
            if self._inflight >= self.max_workers + self.max_queue:
                raise ServerBusyError()
            self._inflight += 1

        try:
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(self._executor, fn)
            return await asyncio.wait_for(future, timeout=timeout_s)
        finally:
            with self._lock:
                self._inflight -= 1

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)


class ServerBusyError(Exception):
    """Raised when the agent work queue is full."""
    error_class = "server_busy"


class ProviderBusyError(Exception):
    """Raised when a specific provider type is at capacity."""
    error_class = "provider_busy"


class ProviderGate:
    """Caps external provider concurrency by provider type.

    Default limits:
    - llm_fast: 2
    - llm_slow: 1
    - asr: 1
    - tts: 2
    - audio_understanding: 1
    """

    DEFAULT_LIMITS = {
        "llm_fast": 2,
        "llm_slow": 1,
        "asr": 1,
        "tts": 2,
        "audio_understanding": 1,
    }

    def __init__(self, limits: Optional[dict] = None) -> None:
        self._limits = dict(self.DEFAULT_LIMITS)
        if limits:
            self._limits.update(limits)
        self._counters: Dict[str, int] = {k: 0 for k in self._limits}
        self._lock = threading.Lock()

    def acquire(self, provider_type: str) -> None:
        """Acquire a slot for the given provider type.

        Raises ProviderBusyError if at capacity.
        """
        limit = self._limits.get(provider_type, 1)
        with self._lock:
            current = self._counters.get(provider_type, 0)
            if current >= limit:
                raise ProviderBusyError(f"Provider {provider_type} is busy ({current}/{limit})")
            self._counters[provider_type] = current + 1

    def release(self, provider_type: str) -> None:
        """Release a slot for the given provider type."""
        with self._lock:
            current = self._counters.get(provider_type, 0)
            self._counters[provider_type] = max(0, current - 1)

    def get_usage(self) -> Dict[str, Dict[str, int]]:
        """Get current usage for all provider types."""
        with self._lock:
            return {
                ptype: {"current": self._counters.get(ptype, 0), "limit": limit}
                for ptype, limit in self._limits.items()
            }
