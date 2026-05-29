"""V1.3 Background memory judgment queue.

Bounded, deduplicated, in-memory queue for background memory judgment.
Single-threaded processing. No SQLite. Lost on restart (acceptable).
"""
from __future__ import annotations

import collections
import logging
import re
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Normalize for dedup: strip + collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip())


class MemoryJudgmentQueue:
    """Background queue for memory judgment jobs."""

    def __init__(
        self,
        provider,
        provider_gate=None,
        max_pending: int = 5,
        timeout_seconds: int = 30,
    ) -> None:
        self._provider = provider
        self._provider_gate = provider_gate
        self._pending: collections.deque = collections.deque(maxlen=max_pending)
        self._lock = threading.Lock()
        self._seen: set = set()
        self._max_pending = max_pending
        self._timeout_seconds = timeout_seconds

    def enqueue(self, user_text: str, trigger_categories: List[str]) -> bool:
        """Enqueue a judgment job. Returns False if queue full or duplicate."""
        norm = _normalize(user_text)
        if not norm:
            return False
        with self._lock:
            if norm in self._seen:
                return False
            if len(self._pending) >= self._max_pending:
                return False
            self._seen.add(norm)
            self._pending.append({
                "user_text": user_text,
                "normalized": norm,
                "trigger_categories": trigger_categories,
            })
            return True

    def process_one(self) -> Optional[Dict[str, Any]]:
        """Process one pending job. Returns judgment result or None.

        Checks provider_gate before starting. Returns None if gate busy.
        """
        with self._lock:
            if not self._pending:
                return None
            # Check provider gate (Issue 12)
            if self._provider_gate is not None:
                try:
                    if not self._provider_gate.is_available("llm_slow"):
                        return None
                except Exception:
                    pass
            job = self._pending.popleft()
            self._seen.discard(job["normalized"])

        # Run outside lock — this calls the LLM
        try:
            from app.pet.prompt_builder import build_memory_judgment_messages
            messages = build_memory_judgment_messages(
                job["user_text"], job["trigger_categories"]
            )
            result = self._provider.complete_json(messages)
            return self._validate_judgment(result)
        except Exception:
            logger.warning("Memory judgment LLM call failed", exc_info=True)
            return None

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def _validate_judgment(self, result: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(result, dict):
            return None
        if not result.get("should_write"):
            return {"should_write": False}
        target = result.get("target", "")
        category = result.get("category", "")
        content = str(result.get("content", "")).strip()
        if target == "user.md":
            target = "memory.md"
        if target != "memory.md":
            return {"should_write": False}
        if category not in ("identity", "preference", "relationship", "project", "temporary"):
            return {"should_write": False}
        if not content:
            return {"should_write": False}
        return {
            "should_write": True,
            "target": target,
            "category": category,
            "content": content,
            "reason": str(result.get("reason", "")),
        }
