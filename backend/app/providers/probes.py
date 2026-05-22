"""Startup provider probes — lightweight health checks (STAB-020)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ProviderProbeResult:
    """Result of a single provider probe."""

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        self.ok: bool = False
        self.error_class: str = ""
        self.latency_ms: int = 0
        self.last_success_at: Optional[float] = None
        self._cached_until: float = 0
        self._cache_ttl: float = 600  # 10 minutes


class ProviderProbeManager:
    """Manages startup probes for all providers.

    Probes run with short timeouts and cache results for 10 minutes
    to avoid consuming provider quota.
    """

    def __init__(self) -> None:
        self._results: Dict[str, ProviderProbeResult] = {}
        self._lock = asyncio.Lock()

    def get_result(self, provider_name: str) -> Optional[ProviderProbeResult]:
        """Get cached probe result for a provider."""
        return self._results.get(provider_name)

    def is_ready(self) -> bool:
        """True if all probed providers are healthy or probes not yet run."""
        if not self._results:
            return True  # No probes configured
        return all(r.ok for r in self._results.values())

    async def probe_llm(self, provider: Any) -> ProviderProbeResult:
        """Probe an LLM provider with a minimal request."""
        name = getattr(provider, "name", "llm")
        result = ProviderProbeResult(name)

        # Check cache
        cached = self._results.get(name)
        if cached and time.monotonic() < cached._cached_until:
            return cached

        start = time.monotonic()
        try:
            # Minimal probe: ask for a single character (run in thread to avoid blocking)
            await asyncio.to_thread(provider.complete_json, [{"role": "user", "content": "ping"}])
            result.ok = True
            result.last_success_at = time.monotonic()
        except Exception as exc:
            result.ok = False
            result.error_class = getattr(exc, "error_class", type(exc).__name__)
            logger.info("LLM probe %s failed: %s", name, result.error_class)
        result.latency_ms = int((time.monotonic() - start) * 1000)
        result._cached_until = time.monotonic() + result._cache_ttl

        self._results[name] = result
        return result

    async def probe_tts(self, provider: Any) -> ProviderProbeResult:
        """Probe a TTS provider with a minimal request."""
        name = getattr(provider, "name", "tts")
        result = ProviderProbeResult(name)

        cached = self._results.get(name)
        if cached and time.monotonic() < cached._cached_until:
            return cached

        start = time.monotonic()
        try:
            # Minimal probe: synthesize a short phrase (run in thread to avoid blocking)
            await asyncio.to_thread(provider.synthesize, "hi", "normal")
            result.ok = True
            result.last_success_at = time.monotonic()
        except Exception as exc:
            result.ok = False
            result.error_class = getattr(exc, "error_class", type(exc).__name__)
            logger.info("TTS probe %s failed: %s", name, result.error_class)
        result.latency_ms = int((time.monotonic() - start) * 1000)
        result._cached_until = time.monotonic() + result._cache_ttl

        self._results[name] = result
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Export probe results for deep health."""
        return {
            name: {
                "ok": r.ok,
                "error_class": r.error_class,
                "latency_ms": r.latency_ms,
                "last_success_at": r.last_success_at,
            }
            for name, r in self._results.items()
        }
