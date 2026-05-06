from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.runtime.memory_store import (
    DailySummaryStore,
    EpisodeSummaryStore,
    MemoryCandidateStore,
)

logger = logging.getLogger(__name__)

EPISODE_SUMMARY_PROMPT = """你是 Momo 的记忆助手。请根据以下对话事件，生成一份 episode 摘要。

输出 JSON：
{
  "summary": "这轮对话主要发生了什么（1-2句话）",
  "key_events": ["关键事件1", "关键事件2"],
  "mood_notes": "用户情绪变化描述",
  "important_quotes": [
    {
      "quote": "用户原话",
      "meaning": "这句话的含义/重要性",
      "importance": 4
    }
  ]
}

重要程度 importance: 1-5
- 5: 永久重要（核心偏好、关系定义）
- 4: 30天内重要（近期计划、重要事件）
- 3: 7天内重要（一般情绪、小偏好）
- 2: 仅当天有意义
- 1: 不值得长期记住

规则：
1. 流水账不进 important_quotes
2. 只提取有情绪重量或长期价值的原话
3. summary 要简洁，不超过 100 字"""

DAILY_SUMMARY_PROMPT = """你是 Momo 的记忆助手。请根据以下 episode 摘要，生成每日总结。

输出 JSON：
{
  "summary": "今天整体发生了什么（2-3句话）",
  "key_events": ["今天最重要的1-3件事"],
  "stable_memory_candidates": [
    {
      "content": "值得长期记住的事实",
      "memory_type": "stable_memory",
      "importance": 3
    }
  ]
}

规则：
1. 只提炼真正值得后续知道的信息
2. 流水账不要
3. stable_memory_candidates 可以为空"""


class SummaryManager:
    """Generates episode and daily summaries using LLM."""

    def __init__(
        self,
        brain_provider: Any,
        episode_summary_store: EpisodeSummaryStore,
        daily_summary_store: DailySummaryStore,
        candidate_store: MemoryCandidateStore,
        timezone_name: str = "Asia/Shanghai",
    ) -> None:
        self.provider = brain_provider
        self.episode_summary_store = episode_summary_store
        self.daily_summary_store = daily_summary_store
        self.candidate_store = candidate_store
        self.timezone_name = timezone_name

    def generate_episode_summary(
        self,
        episode_id: str,
        event_log_store: Any,
        episode_store: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate summary for a closed episode. Returns summary dict or None."""
        # Get events for this episode
        events = event_log_store.recent_events(episode_id=episode_id, limit=50)
        if not events:
            return None

        # Get episode metadata
        episode = episode_store.get_episode(episode_id) if episode_store else None
        started_at = (episode.get("started_at_utc") or "") if episode else ""
        ended_at = (episode.get("ended_at_utc") or datetime.utcnow().isoformat()) if episode else datetime.utcnow().isoformat()

        # Build event text for LLM
        event_lines = []
        for evt in reversed(events):
            user_text = evt.get("user_text", "")
            pet_reply = evt.get("pet_reply", "")
            mood = evt.get("mood_after", "")
            line = ""
            if user_text:
                line += "用户: %s" % user_text
            if pet_reply:
                line += " | Momo: %s" % pet_reply
            if mood:
                line += " [%s]" % mood
            if line:
                event_lines.append(line.strip())

        if not event_lines:
            return None

        try:
            result = self._call_episode_llm(event_lines)
        except Exception:
            logger.warning("Episode summary LLM call failed for %s", episode_id, exc_info=True)
            return None

        summary_text = str(result.get("summary", ""))[:200]
        key_events = result.get("key_events", [])
        if not isinstance(key_events, list):
            key_events = []
        mood_notes = str(result.get("mood_notes", ""))
        important_quotes = result.get("important_quotes", [])
        if not isinstance(important_quotes, list):
            important_quotes = []

        # Save episode summary
        self.episode_summary_store.save(
            episode_id=episode_id,
            summary=summary_text,
            key_events=key_events[:5],
            mood_notes=mood_notes[:200],
            important_quotes=important_quotes[:5],
            started_at_utc=started_at,
            ended_at_utc=ended_at,
        )

        # Enqueue important quotes as candidates (importance >= 3)
        for quote in important_quotes:
            if not isinstance(quote, dict):
                continue
            imp = int(quote.get("importance", 0))
            if imp >= 3:
                quote_text = str(quote.get("quote", "")).strip()
                meaning = str(quote.get("meaning", "")).strip()
                if quote_text:
                    candidate_text = quote_text
                    if meaning:
                        candidate_text += " (%s)" % meaning
                    try:
                        self.candidate_store.add(
                            source_event_id="episode_summary:%s" % episode_id,
                            episode_id=episode_id,
                            candidate_text=candidate_text[:200],
                            trigger_reason="episode_end",
                        )
                    except Exception:
                        logger.warning("Failed to enqueue quote candidate", exc_info=True)

        return {
            "episode_id": episode_id,
            "summary": summary_text,
            "key_events": key_events,
            "mood_notes": mood_notes,
        }

    def generate_daily_summary(self, local_date: str) -> Optional[Dict[str, Any]]:
        """Generate daily summary from episode summaries."""
        # Check if already exists
        if self.daily_summary_store.exists(local_date):
            return None

        # Get recent episode summaries
        episode_summaries = self.episode_summary_store.recent(limit=10)
        if not episode_summaries:
            return None

        # Filter to today's episodes (approximate by checking ended_at)
        today_summaries = []
        for ep in episode_summaries:
            ended = ep.get("ended_at_utc", "")
            if ended and ended.startswith(local_date[:7]):  # Same month at least
                today_summaries.append(ep)

        if not today_summaries:
            today_summaries = episode_summaries[:3]

        try:
            result = self._call_daily_llm(today_summaries)
        except Exception:
            logger.warning("Daily summary LLM call failed", exc_info=True)
            return None

        summary_text = str(result.get("summary", ""))[:300]
        key_events = result.get("key_events", [])
        if not isinstance(key_events, list):
            key_events = []
        stable_candidates = result.get("stable_memory_candidates", [])
        if not isinstance(stable_candidates, list):
            stable_candidates = []

        self.daily_summary_store.save(
            local_date=local_date,
            summary=summary_text,
            key_events=key_events[:5],
            stable_memory_candidates=stable_candidates[:3],
        )

        return {
            "local_date": local_date,
            "summary": summary_text,
            "key_events": key_events,
        }

    def cleanup_expired(self) -> Dict[str, int]:
        """Clean up expired summaries. Returns counts."""
        return {
            "episode_summaries": self.episode_summary_store.cleanup_expired(),
            "daily_summaries": self.daily_summary_store.cleanup_expired(),
        }

    def _call_episode_llm(self, event_lines: List[str]) -> Dict[str, Any]:
        event_text = "\n".join(event_lines[-20:])  # Cap at 20 lines
        messages = [
            {"role": "system", "content": EPISODE_SUMMARY_PROMPT},
            {"role": "user", "content": "对话事件：\n%s" % event_text},
        ]
        return self.provider.complete_json(messages)

    def _call_daily_llm(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary_text = ""
        for i, ep in enumerate(summaries):
            summary_text += "\n%d. %s" % (i + 1, ep.get("summary", ""))
            mood = ep.get("mood_notes", "")
            if mood:
                summary_text += " [%s]" % mood

        messages = [
            {"role": "system", "content": DAILY_SUMMARY_PROMPT},
            {"role": "user", "content": "今天的 episode 摘要：%s" % summary_text},
        ]
        return self.provider.complete_json(messages)
