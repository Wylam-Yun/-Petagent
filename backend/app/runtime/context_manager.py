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
        self.recall_event_limit = cfg.get("recall_event_limit", 6)
        self.recall_lookback_hours = cfg.get("recall_lookback_hours", 48)

    def build(
        self,
        event: Any,
        pet_state: Dict[str, Any],
        episode: Optional[Dict[str, Any]],
        event_log_store: Any,
        device_state: Optional[Dict[str, Any]] = None,
        skill_results: Optional[List[Dict[str, Any]]] = None,
        memory_manager: Any = None,
        episode_summary_store: Any = None,
        daily_summary_store: Any = None,
        context_profile: Optional[str] = None,
        memory_card_manager: Any = None,
    ) -> Dict[str, Any]:
        """Build a cognition context dict with budget control."""
        # Profile-specific budget overrides
        profile = context_profile or "default"
        effective_recent_turns = self.recent_exact_turns
        effective_memory_items = self.relevant_memory_items
        effective_episode_summaries = self.recent_episode_summaries
        include_daily_digest = True
        include_episode_summaries = True
        include_important_quotes = True

        if profile == "fast_companion":
            effective_recent_turns = min(self.recent_exact_turns, 4)
            effective_memory_items = min(self.relevant_memory_items, 2)
            include_daily_digest = False
            include_episode_summaries = False
            include_important_quotes = False
        elif profile == "recall":
            effective_recent_turns = min(self.recent_exact_turns, 4)
            include_daily_digest = False
        elif profile == "tool":
            effective_recent_turns = min(self.recent_exact_turns, 4)
            effective_memory_items = min(self.relevant_memory_items, 2)
            include_daily_digest = False
            include_episode_summaries = False
        elif profile == "long_task":
            pass  # use all defaults
        elif profile == "proactive":
            effective_recent_turns = min(self.recent_exact_turns, 2)
            effective_memory_items = min(self.relevant_memory_items, 1)
            include_daily_digest = False
            include_episode_summaries = False
            include_important_quotes = False

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
                limit=effective_recent_turns,
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

        temporal_recall_events: List[Dict[str, Any]] = []
        if event_log_store and self._wants_temporal_recall(event):
            cutoff = (now_utc - timedelta(hours=self.recall_lookback_hours)).isoformat()
            current_episode_id = episode.get("episode_id") if episode else None
            try:
                recall_events = event_log_store.recall_events(
                    since_utc=cutoff,
                    limit=self.recall_event_limit,
                    exclude_episode_id=current_episode_id,
                )
            except Exception:
                recall_events = []
            for evt in recall_events:
                entry = {
                    "event_type": evt.get("event_type", ""),
                    "created_at": evt.get("created_at_utc", ""),
                    "episode_id": evt.get("episode_id", ""),
                }
                if evt.get("user_text"):
                    entry["user"] = evt["user_text"]
                if evt.get("pet_reply"):
                    entry["pet"] = evt["pet_reply"]
                if evt.get("mood_after"):
                    entry["mood"] = evt["mood_after"]
                temporal_recall_events.append(entry)

        # Scored memories OR memory cards
        relevant_memories: List[Dict[str, Any]] = []
        memory_cards: Optional[Dict[str, List[str]]] = None
        use_cards = profile in ("fast_companion", "proactive") and memory_card_manager is not None

        if use_cards:
            try:
                memory_cards = {
                    "user_preferences": memory_card_manager.read_card("user_preferences"),
                    "momo_memories": memory_card_manager.read_card("momo_memories"),
                }
            except Exception:
                memory_cards = {"user_preferences": [], "momo_memories": []}
        elif memory_manager is not None:
            user_text = str(event.payload.get("user_text", "") if hasattr(event, "payload") else "")
            try:
                relevant_memories = memory_manager.scored_memories(
                    limit=effective_memory_items,
                    user_text=user_text,
                )
            except Exception:
                relevant_memories = []

        # Episode summaries
        episode_summaries: List[Dict[str, Any]] = []
        if include_episode_summaries and episode_summary_store is not None:
            try:
                episode_summaries = episode_summary_store.recent(
                    limit=effective_episode_summaries
                )
            except Exception:
                episode_summaries = []

        # Important quotes from memory table
        important_quotes: List[Dict[str, Any]] = []
        if include_important_quotes and memory_manager is not None:
            try:
                important_quotes = memory_manager.important_quotes(limit=4)
            except Exception:
                important_quotes = []

        # Daily digest (Stage 3.7)
        daily_digest = None
        if include_daily_digest and daily_summary_store is not None:
            try:
                recent_daily = daily_summary_store.recent(limit=1)
                if recent_daily:
                    daily_digest = recent_daily[0]
            except Exception:
                daily_digest = None

        # Build context and trim to budget
        context = {
            "context_profile": profile,
            "current_time": current_time,
            "current_episode": current_episode,
            "recent_exact_events": recent_exact_events,
            "temporal_recall_events": temporal_recall_events,
            "episode_summaries": episode_summaries,
            "daily_digest": daily_digest,
            "relevant_memories": relevant_memories,
            "memory_cards": memory_cards,
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
            context["context_budget"]["items_selected"] = self._count_items(context)
            return context

        # Trim: daily_digest first, then episode summaries, then important quotes, then events
        if context.get("daily_digest"):
            context["daily_digest"] = None
            notes.append("dropped daily_digest to fit budget")
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

        serialized = json.dumps(context, ensure_ascii=False)
        if len(serialized) > self.max_context_chars:
            recall_events = context.get("temporal_recall_events", [])
            while recall_events and len(json.dumps(context, ensure_ascii=False)) > self.max_context_chars:
                recall_events.pop(0)
                notes.append("trimmed oldest temporal recall event")
            context["temporal_recall_events"] = recall_events

        # Last resort: trim memory_cards (already bounded by max_card_cjk_chars)
        serialized = json.dumps(context, ensure_ascii=False)
        if len(serialized) > self.max_context_chars:
            cards = context.get("memory_cards")
            if cards:
                for key in ("momo_memories", "user_preferences"):
                    items = cards.get(key, [])
                    while items and len(json.dumps(context, ensure_ascii=False)) > self.max_context_chars:
                        items.pop()
                        notes.append("trimmed memory_cards.%s" % key)
                    cards[key] = items

        context["selection_notes"] = notes
        final = json.dumps(context, ensure_ascii=False)
        context["context_budget"]["used_chars"] = len(final)
        context["context_budget"]["items_selected"] = self._count_items(context)
        return context

    def _count_items(self, context: Dict[str, Any]) -> int:
        count = (
            len(context.get("recent_exact_events", []))
            + len(context.get("temporal_recall_events", []))
            + len(context.get("relevant_memories", []))
            + len(context.get("episode_summaries", []))
            + len(context.get("important_quotes", []))
            + (1 if context.get("daily_digest") else 0)
        )
        cards = context.get("memory_cards")
        if cards:
            count += len(cards.get("user_preferences", []))
            count += len(cards.get("momo_memories", []))
        return count

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

    def _wants_temporal_recall(self, event: Any) -> bool:
        payload = getattr(event, "payload", {}) or {}
        text = str(payload.get("user_text") or payload.get("text") or "")
        if not text:
            return False
        keywords = [
            "昨天",
            "前天",
            "刚刚",
            "之前",
            "上次",
            "回顾",
            "聊了啥",
            "聊了什么",
            "说了啥",
            "说了什么",
            "记得",
            "想起来",
        ]
        return any(keyword in text for keyword in keywords)
