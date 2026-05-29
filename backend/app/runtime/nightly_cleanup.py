"""Nightly Memory Cleanup Runner.

Runs at local midnight to "整理小本本". LLM proposes add/update/delete
operations on canonical memory.md. Backend validates and applies atomically.

Safety gates: once per day, skip during active responses, skip under
provider backpressure, skip when event loop stale, 60s timeout.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, time, timedelta, timezone
from time import perf_counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60


class NightlyCleanupRunner:
    """Background nightly cleanup for notebook files."""

    def __init__(
        self,
        notebook_manager,
        provider,
        event_log_store,
        maintenance_state,
        provider_gate=None,
        dispatcher=None,
        cleanup_window_start: time = time(0, 0),
        cleanup_window_end: time = time(1, 0),
    ) -> None:
        self._notebook = notebook_manager
        self._provider = provider
        self._event_log = event_log_store
        self._maintenance_state = maintenance_state
        self._provider_gate = provider_gate
        self._dispatcher = dispatcher
        self._cleanup_window_start = cleanup_window_start
        self._cleanup_window_end = cleanup_window_end

    def should_run(self, force: bool = False) -> bool:
        """Check all safety gates. Returns True if cleanup should proceed."""
        if not force and not self._is_in_cleanup_window():
            return False

        # Gate 1: once per local day
        last = self._maintenance_state.get("last_cleanup_date")
        today = self._today_local()
        if last == today:
            return False

        # Gate 2: provider backpressure
        if self._provider_gate is not None:
            try:
                if not self._provider_gate.is_available("llm_slow"):
                    return False
            except Exception:
                pass

        # Gate 3: active response
        if self._dispatcher is not None:
            if getattr(self._dispatcher, "active_requests", 0) > 0:
                return False

        # Gate 4: event loop stale (health degradation)
        if self._dispatcher is not None:
            tick = getattr(self._dispatcher, "event_loop_tick", 0)
            if tick > 0:
                elapsed = perf_counter() - tick
                if elapsed > 60:
                    return False

        return True

    def run(self, force: bool = False) -> Dict[str, int]:
        """Execute one cleanup cycle with 60s timeout.

        LLM call happens BEFORE notebook lock (apply_cleanup_operations acquires lock).
        """
        if not self.should_run(force=force):
            return {}

        cancel_flag = threading.Event()
        timer = threading.Timer(_TIMEOUT_SECONDS, cancel_flag.set)
        timer.daemon = True
        timer.start()

        try:
            return self._run_inner(cancel_flag)
        finally:
            timer.cancel()

    def _run_inner(self, cancel_flag: threading.Event) -> Dict[str, int]:
        # Step 1: Read current notebook content (no lock needed)
        # V1.4: memory.md is the only prompt-facing notebook. user.md is a
        # migration stub and must not influence cleanup decisions.
        memory_content = self._notebook.read_raw("memory.md")

        if cancel_flag.is_set():
            logger.warning("Nightly cleanup timed out reading files")
            return {}

        # Step 2: Read bounded event log
        recent_events = []
        if self._event_log is not None:
            try:
                recent_events = self._event_log.recent_events_bounded(
                    limit=200, max_bytes=20480
                )
            except Exception:
                logger.warning("Failed to read event log for cleanup", exc_info=True)

        if cancel_flag.is_set():
            logger.warning("Nightly cleanup timed out reading events")
            return {}

        # Step 3: Build prompt and call LLM
        from app.pet.prompt_builder import build_nightly_cleanup_messages
        now_local = self._get_local_now()
        current_time = now_local.strftime("%Y-%m-%d %H:%M %A")

        # Format recent events for prompt
        event_lines = []
        for evt in recent_events[:50]:  # cap for prompt size
            user = evt.get("user_text", "")
            pet = evt.get("pet_reply", "")
            if user:
                event_lines.append(f"用户: {user}")
            if pet:
                event_lines.append(f"豆豆: {pet}")

        messages = build_nightly_cleanup_messages(memory_content, event_lines, current_time)

        try:
            result = self._provider.complete_json(messages)
        except Exception:
            logger.warning("Nightly cleanup LLM call failed", exc_info=True)
            return {}

        if cancel_flag.is_set():
            logger.warning("Nightly cleanup timed out after LLM call")
            return {}

        # Step 4: Validate operations
        operations = self._validate_operations(result)
        if not operations:
            logger.info("Nightly cleanup: no valid operations")
            self._maintenance_state.set("last_cleanup_date", self._today_local())
            return {"no_ops": 1}

        # Step 5: Apply operations (acquires notebook lock)
        stats = self._notebook.apply_cleanup_operations(operations)

        # Step 6: Mark as done
        self._maintenance_state.set("last_cleanup_date", self._today_local())
        logger.info("Nightly cleanup completed: %s", stats)
        return stats

    def _validate_operations(self, result: Any) -> Optional[Dict[str, Any]]:
        """Validate LLM output structure. Returns cleaned operations or None."""
        if not isinstance(result, dict):
            return None

        ops: Dict[str, Any] = {"add": [], "update": [], "delete": []}

        for op_type in ("add", "update", "delete"):
            items = result.get(op_type, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                if op_type == "add":
                    target = item.get("target", "")
                    cat = item.get("category", "")
                    content = str(item.get("content", "")).strip()
                    if target == "user.md":
                        target = "memory.md"
                    if target == "memory.md" and cat and content:
                        ops["add"].append({"target": "memory.md", "category": cat, "content": content})
                elif op_type == "update":
                    target = item.get("target", "")
                    old = str(item.get("old", "")).strip()
                    new_cat = item.get("new_category", "")
                    new_content = str(item.get("new_content", "")).strip()
                    if target == "user.md":
                        target = "memory.md"
                    if target == "memory.md" and old and new_cat and new_content:
                        ops["update"].append({
                            "target": "memory.md", "old": old,
                            "new_category": new_cat, "new_content": new_content,
                        })
                elif op_type == "delete":
                    target = item.get("target", "")
                    old = str(item.get("old", "")).strip()
                    if target == "user.md":
                        target = "memory.md"
                    if target == "memory.md" and old:
                        ops["delete"].append({"target": "memory.md", "old": old})

        has_any = bool(ops["add"] or ops["update"] or ops["delete"])
        return ops if has_any else None

    def _today_local(self) -> str:
        return self._get_local_now().strftime("%Y-%m-%d")

    def _get_local_now(self) -> datetime:
        return datetime.utcnow() + self._get_tz_offset()

    def _is_in_cleanup_window(self) -> bool:
        local_time = self._get_local_now().time()
        start = self._cleanup_window_start
        end = self._cleanup_window_end
        if start <= end:
            return start <= local_time < end
        return local_time >= start or local_time < end

    def _get_tz_offset(self) -> timedelta:
        tz_name = "Asia/Shanghai"
        if self._dispatcher and hasattr(self._dispatcher, "context_manager"):
            cm = self._dispatcher.context_manager
            if cm:
                tz_name = getattr(cm, "timezone_name", "Asia/Shanghai")
        offsets = {
            "Asia/Shanghai": timedelta(hours=8),
            "Asia/Tokyo": timedelta(hours=9),
            "US/Eastern": timedelta(hours=-5),
            "US/Pacific": timedelta(hours=-8),
            "Europe/London": timedelta(hours=0),
        }
        return offsets.get(tz_name, timedelta(hours=8))
