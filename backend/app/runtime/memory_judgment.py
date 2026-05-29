"""Background memory summary queue.

Bounded, deduplicated, in-memory queue for after-turn notebook updates.
Single-threaded processing. No SQLite. Lost on restart is acceptable because
the canonical notebook is an experience enhancer, not the source of truth for a
transaction.
"""
from __future__ import annotations

import collections
import logging
import re
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CATEGORY_WHITELIST = {"identity", "preference", "relationship", "project", "temporary"}


def _normalize(text: str) -> str:
    """Normalize for dedup: strip + collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip())


class MemoryJudgmentQueue:
    """Background queue for memory judgment and after-turn summary jobs."""

    def __init__(
        self,
        provider,
        provider_gate=None,
        max_pending: int = 5,
        timeout_seconds: int = 30,
        notebook_manager=None,
    ) -> None:
        self._provider = provider
        self._provider_gate = provider_gate
        self._pending: collections.deque = collections.deque(maxlen=max_pending)
        self._lock = threading.Lock()
        self._seen: set = set()
        self._max_pending = max_pending
        self._timeout_seconds = timeout_seconds
        self._notebook_manager = notebook_manager

    def enqueue(self, user_text: str, trigger_categories: List[str]) -> bool:
        """Enqueue a legacy judgment job. Returns False if full or duplicate."""
        norm = _normalize(user_text)
        if not norm:
            return False
        return self._enqueue_job({
            "kind": "judgment",
            "dedup_key": f"judgment:{norm}",
            "user_text": user_text,
            "trigger_categories": trigger_categories,
            "priority": bool("explicit" in (trigger_categories or [])),
        })

    def enqueue_turn_summary(
        self,
        user_text: str,
        pet_reply: str,
        route: str,
        selected_memory: Optional[List[str]] = None,
        trigger_categories: Optional[List[str]] = None,
    ) -> bool:
        """Enqueue an after-turn summary job without blocking the response."""
        norm_user = _normalize(user_text)
        norm_reply = _normalize(pet_reply)
        if not norm_user or not norm_reply:
            return False
        triggers = trigger_categories or []
        return self._enqueue_job({
            "kind": "turn_summary",
            "dedup_key": f"summary:{norm_user}|{norm_reply}",
            "user_text": user_text,
            "pet_reply": pet_reply,
            "route": route or "fast_reply",
            "selected_memory": list(selected_memory or [])[:10],
            "trigger_categories": triggers,
            "priority": bool("explicit" in triggers),
        })

    def _enqueue_job(self, job: Dict[str, Any]) -> bool:
        dedup_key = str(job.get("dedup_key") or "")
        if not dedup_key:
            return False
        with self._lock:
            if dedup_key in self._seen:
                return False
            if len(self._pending) >= self._max_pending:
                if not job.get("priority"):
                    return False
                if not self._evict_oldest_non_priority_locked():
                    return False
            self._seen.add(dedup_key)
            if job.get("priority"):
                self._pending.appendleft(job)
            else:
                self._pending.append(job)
            return True

    def _evict_oldest_non_priority_locked(self) -> bool:
        for idx in range(len(self._pending) - 1, -1, -1):
            job = self._pending[idx]
            if job.get("priority"):
                continue
            removed = self._pending[idx]
            del self._pending[idx]
            self._seen.discard(str(removed.get("dedup_key") or ""))
            return True
        return False

    def process_one(self) -> Optional[Dict[str, Any]]:
        """Process one pending job. Returns result or None.

        Checks provider_gate before starting. Returns None if gate busy.
        """
        with self._lock:
            if not self._pending:
                return None
            if self._provider_gate is not None:
                try:
                    if not self._provider_gate.is_available("llm_slow"):
                        return None
                except Exception:
                    pass
            job = self._pending.popleft()
            self._seen.discard(str(job.get("dedup_key") or ""))

        try:
            if job.get("kind") == "turn_summary":
                return self._process_turn_summary(job)
            return self._process_legacy_judgment(job)
        except Exception:
            logger.warning("Memory summary LLM call failed", exc_info=True)
            return None

    def _process_legacy_judgment(self, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from app.pet.prompt_builder import build_memory_judgment_messages

        messages = build_memory_judgment_messages(
            str(job.get("user_text") or ""),
            list(job.get("trigger_categories") or []),
        )
        result = self._provider.complete_json(messages)
        return self._validate_judgment(result)

    def _process_turn_summary(self, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        from app.pet.prompt_builder import build_memory_summary_messages

        memory_content = ""
        if self._notebook_manager is not None:
            memory_content = self._notebook_manager.read_raw("memory.md")
        messages = build_memory_summary_messages(
            user_text=str(job.get("user_text") or ""),
            pet_reply=str(job.get("pet_reply") or ""),
            route=str(job.get("route") or "fast_reply"),
            selected_memory=list(job.get("selected_memory") or []),
            memory_content=memory_content,
            trigger_categories=list(job.get("trigger_categories") or []),
        )
        result = self._provider.complete_json(messages)
        operations = self._validate_operations(result)
        if operations is None:
            return {"should_write": False, "operations": None}
        return {
            "should_write": bool(
                operations["add"] or operations["update"] or operations["delete"]
            ),
            "operations": operations,
        }

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
        if category not in _CATEGORY_WHITELIST:
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

    def _validate_operations(self, result: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(result, dict):
            return None
        operations: Dict[str, List[Dict[str, str]]] = {"add": [], "update": [], "delete": []}
        for item in result.get("add", []) if isinstance(result.get("add", []), list) else []:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "")
            content = str(item.get("content") or "").strip()
            if category in _CATEGORY_WHITELIST and content:
                operations["add"].append({
                    "target": "memory.md",
                    "category": category,
                    "content": content,
                })
        for item in result.get("update", []) if isinstance(result.get("update", []), list) else []:
            if not isinstance(item, dict):
                continue
            old = str(item.get("old") or "").strip()
            new_category = str(item.get("new_category") or "")
            new_content = str(item.get("new_content") or "").strip()
            if old and new_category in _CATEGORY_WHITELIST and new_content:
                operations["update"].append({
                    "target": "memory.md",
                    "old": old,
                    "new_category": new_category,
                    "new_content": new_content,
                })
        for item in result.get("delete", []) if isinstance(result.get("delete", []), list) else []:
            if not isinstance(item, dict):
                continue
            old = str(item.get("old") or "").strip()
            if old:
                operations["delete"].append({
                    "target": "memory.md",
                    "old": old,
                    "reason": str(item.get("reason") or ""),
                })
        return operations
