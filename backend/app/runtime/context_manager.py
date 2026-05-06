from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


class ContextManager:
    """Assembles a budgeted cognition context for LLM prompts."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self.timezone_name = cfg.get("timezone", "Asia/Shanghai")
        self.recent_exact_turns = cfg.get("recent_exact_turns", 6)
        self.recent_episode_summaries = cfg.get("recent_episode_summaries", 2)
        self.relevant_memory_items = cfg.get("relevant_memory_items", 4)
        self.max_context_chars = cfg.get("max_context_chars", 4500)
        self.raw_max_rows = cfg.get("raw_max_rows", 3000)
        self.idle_episode_minutes = cfg.get("idle_episode_minutes", 45)

    def build(
        self,
        event: Any,
        pet_state: Dict[str, Any],
        episode: Optional[Dict[str, Any]],
        event_log_store: Any,
        memory_store: Any = None,
        device_state: Optional[Dict[str, Any]] = None,
        skill_results: Optional[List[Dict[str, Any]]] = None,
        memory_manager: Any = None,
        episode_summary_store: Any = None,
    ) -> Dict[str, Any]:
        """Build a cognition context dict with budget control."""
        now_utc = datetime.utcnow()
        tz_offset = self._get_tz_offset()
        now_local = now_utc + tz_offset

        current_time = {
            "utc": now_utc.isoformat(),
            "local": now_local.isoformat(),
            "timezone": self.timezone_name,
            "minutes_since_last": self._minutes_since_last(pet_state, now_utc),
        }

        current_episode = {}
        if episode:
            current_episode = {
                "episode_id": episode.get("episode_id", ""),
                "started_at": episode.get("started_at_utc", ""),
                "event_count": episode.get("event_count", 0),
            }

        # Recent exact events from current episode
        recent_exact_events: List[Dict[str, Any]] = []
        if episode and event_log_store:
            raw_events = event_log_store.recent_events(
                episode_id=episode.get("episode_id"),
                limit=self.recent_exact_turns,
            )
            for evt in raw_events:
                entry: Dict[str, Any] = {
                    "event_type": evt.get("event_type", ""),
                    "created_at": evt.get("created_at_utc", ""),
                }
                if evt.get("user_text"):
                    entry["user"] = evt["user_text"]
                if evt.get("pet_reply"):
                    entry["pet"] = evt["pet_reply"]
                if evt.get("mood_after"):
                    entry["mood"] = evt["mood_after"]
                recent_exact_events.append(entry)
            recent_exact_events.reverse()

        # Scored memories from MemoryManager (Stage 3.6)
        relevant_memories: List[Dict[str, Any]] = []
        if memory_manager is not None:
            user_text = str(event.payload.get("user_text", "") if hasattr(event, "payload") else "")
            try:
                relevant_memories = memory_manager.scored_memories(
                    limit=self.relevant_memory_items,
                    user_text=user_text,
                )
            except Exception:
                relevant_memories = []
        elif memory_store is not None:
            # Backward compat: old MemoryStore returns List[str]
            try:
                raw = memory_store.recent_memory(limit=self.relevant_memory_items)
                relevant_memories = [{"content": m, "type": "unknown"} for m in raw]
            except Exception:
                relevant_memories = []

        # Episode summaries (Stage 3.6)
        episode_summaries: List[Dict[str, Any]] = []
        if episode_summary_store is not None:
            try:
                episode_summaries = episode_summary_store.recent(
                    limit=self.recent_episode_summaries
                )
            except Exception:
                episode_summaries = []

        # Important quotes from memory table (Stage 3.6)
        important_quotes: List[Dict[str, Any]] = []
        if memory_manager is not None:
            try:
                important_quotes = memory_manager.important_quotes(limit=4)
            except Exception:
                important_quotes = []

        # Build context and trim to budget
        context = {
            "current_time": current_time,
            "current_episode": current_episode,
            "recent_exact_events": recent_exact_events,
            "episode_summaries": episode_summaries,
            "relevant_memories": relevant_memories,
            "important_quotes": important_quotes,
            "context_budget": {
                "max_chars": self.max_context_chars,
                "used_chars": 0,
                "items_selected": 0,
            },
            "selection_notes": [],
        }

        context = self._trim_to_budget(context)
        return context

    def _trim_to_budget(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Enforce max_context_chars by trimming lower-priority items."""
        serialized = json.dumps(context, ensure_ascii=False)
        used = len(serialized)
        notes = context.get("selection_notes", [])

        if used <= self.max_context_chars:
            context["context_budget"]["used_chars"] = used
            context["context_budget"]["items_selected"] = (
                len(context.get("recent_exact_events", []))
                + len(context.get("relevant_memories", []))
                + len(context.get("episode_summaries", []))
                + len(context.get("important_quotes", []))
            )
            return context

        # Trim: first drop episode summaries, then important quotes, then trim events
        if context.get("episode_summaries"):
            context["episode_summaries"] = []
            notes.append("dropped episode_summaries to fit budget")
        if context.get("important_quotes"):
            context["important_quotes"] = []
            notes.append("dropped important_quotes to fit budget")

        serialized = json.dumps(context, ensure_ascii=False)
        if len(serialized) > self.max_context_chars:
            events = context.get("recent_exact_events", [])
            while events and len(json.dumps(context, ensure_ascii=False)) > self.max_context_chars:
                events.pop(0)
                notes.append("trimmed oldest exact event")
            context["recent_exact_events"] = events

        serialized = json.dumps(context, ensure_ascii=False)
        if len(serialized) > self.max_context_chars:
            mems = context.get("relevant_memories", [])
            while mems and len(json.dumps(context, ensure_ascii=False)) > self.max_context_chars:
                mems.pop()
                notes.append("trimmed oldest memory")
            context["relevant_memories"] = mems

        context["selection_notes"] = notes
        final = json.dumps(context, ensure_ascii=False)
        context["context_budget"]["used_chars"] = len(final)
        context["context_budget"]["items_selected"] = (
            len(context.get("recent_exact_events", []))
            + len(context.get("relevant_memories", []))
            + len(context.get("episode_summaries", []))
            + len(context.get("important_quotes", []))
        )
        return context

    def _minutes_since_last(self, pet_state: Dict[str, Any], now_utc: datetime) -> int:
        last = pet_state.get("last_interaction_at")
        if not last:
            return -1
        try:
            last_dt = datetime.fromisoformat(last)
            delta = now_utc - last_dt
            return int(delta.total_seconds() / 60)
        except (ValueError, TypeError):
            return -1

    def _get_tz_offset(self) -> timedelta:
        """Return timezone offset. Default to Asia/Shanghai (UTC+8)."""
        offsets = {
            "Asia/Shanghai": timedelta(hours=8),
            "Asia/Tokyo": timedelta(hours=9),
            "US/Eastern": timedelta(hours=-5),
            "US/Pacific": timedelta(hours=-8),
            "Europe/London": timedelta(hours=0),
        }
        return offsets.get(self.timezone_name, timedelta(hours=8))
