from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from app.pet.memory import SENSITIVE_MARKERS, infer_memory_type
from app.runtime.context_store import desensitize_text
from app.runtime.memory_store import MemoryCandidateStore, MemoryManager

logger = logging.getLogger(__name__)

CURATOR_SYSTEM_PROMPT = """你是一个记忆管理助手。你的任务是判断用户和 Momo 的对话中哪些信息值得长期记住。

候选记忆格式：每条有 trigger_reason（来源）和 candidate_text（原文）。

判断规则：
1. 明确偏好（"我喜欢短回复"、"以后叫我 William"）→ 保存
2. 关系信息（称呼、角色边界）→ 保存
3. 重要事件（明天面试、项目截止）→ 保存
4. 近期情绪（反复出现的累/烦/开心）→ 可以保存
5. 流水账（"我喝了水"、"我打开网页"）→ 不保存
6. 敏感信息（密码、地址、银行卡）→ 不保存

输出 JSON：
{
  "decisions": [
    {
      "save": true,
      "memory_type": "user_preference",
      "content": "用户喜欢短回复",
      "importance": 4,
      "ttl_days": 30,
      "confidence": 0.9,
      "merge_with_memory_id": null,
      "reason": "明确偏好"
    }
  ]
}

memory_type 枚举：user_preference, relationship, stable_memory, important_quote, recent_mood, important_event, habit
importance: 1-5（5=永久重要）
ttl_days: null 表示长期保留，数字表示保留天数
merge_with_memory_id: 如果和已有记忆重复，填已有记忆的 id，否则 null"""

MAX_CONTENT_LENGTH = 200


class MemoryCurator:
    """Uses LLM to batch-process memory candidates into curated memories."""

    def __init__(self, brain_provider: Any, memory_manager: MemoryManager, max_batch: int = 8) -> None:
        self.provider = brain_provider
        self.memory_manager = memory_manager
        self.max_batch = max_batch

    def curate_batch(self, candidate_store: MemoryCandidateStore) -> Dict[str, int]:
        """Process pending candidates. Returns {saved, ignored, errors}."""
        candidates = candidate_store.pending(limit=self.max_batch)
        if not candidates:
            return {"saved": 0, "ignored": 0, "errors": 0}

        result = {"saved": 0, "ignored": 0, "errors": 0}
        try:
            decisions = self._call_llm(candidates)
        except Exception:
            logger.warning("Curator LLM call failed", exc_info=True)
            for cand in candidates:
                candidate_store.mark_processed(cand["id"], "error")
            result["errors"] = len(candidates)
            return result

        for i, cand in enumerate(candidates):
            decision = decisions[i] if i < len(decisions) else None
            if decision is None:
                candidate_store.mark_processed(cand["id"], "error")
                result["errors"] += 1
                continue

            try:
                saved = self._apply_decision(cand, decision)
                if saved:
                    candidate_store.mark_processed(cand["id"], "saved")
                    result["saved"] += 1
                else:
                    candidate_store.mark_processed(cand["id"], "ignored")
                    result["ignored"] += 1
            except Exception:
                logger.warning("Failed to apply curator decision", exc_info=True)
                candidate_store.mark_processed(cand["id"], "error")
                result["errors"] += 1

        return result

    def _call_llm(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Call LLM to get decisions for candidates."""
        candidate_text = ""
        for i, cand in enumerate(candidates):
            candidate_text += "\n%d. [%s] %s" % (
                i + 1,
                cand["trigger_reason"],
                cand["candidate_text"],
            )

        messages = [
            {"role": "system", "content": CURATOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "以下是待判断的候选记忆：%s\n\n请为每条候选输出一个 decision。" % candidate_text,
            },
        ]

        raw = self.provider.complete_json(messages)
        decisions = raw.get("decisions", [])
        if not isinstance(decisions, list):
            return []
        return decisions

    def _apply_decision(self, candidate: Dict[str, Any], decision: Dict[str, Any]) -> bool:
        """Apply a curator decision. Returns True if saved."""
        if not decision.get("save", False):
            return False

        content = str(decision.get("content", "")).strip()
        if not content or len(content) > MAX_CONTENT_LENGTH:
            return False

        # Check sensitive markers
        lowered = content.lower()
        if any(marker in lowered for marker in SENSITIVE_MARKERS):
            return False

        memory_type = str(decision.get("memory_type", "important_event"))
        if memory_type not in MemoryManager.VALID_TYPES:
            memory_type = "important_event"

        importance = int(decision.get("importance", 3))
        importance = max(1, min(5, importance))

        confidence = float(decision.get("confidence", 0.8))
        confidence = max(0.0, min(1.0, confidence))

        ttl_days = decision.get("ttl_days")
        if ttl_days is not None:
            try:
                ttl_days = int(ttl_days)
            except (TypeError, ValueError):
                ttl_days = None

        merge_id = decision.get("merge_with_memory_id")
        if merge_id is not None:
            try:
                merge_id = int(merge_id)
            except (TypeError, ValueError):
                merge_id = None

        memory_id = self.memory_manager.save_curated(
            memory_type=memory_type,
            content=content,
            importance=importance,
            confidence=confidence,
            ttl_days=ttl_days,
            source_event_id=candidate.get("source_event_id"),
            source_episode_id=candidate.get("episode_id"),
            merge_with_id=merge_id,
        )
        return memory_id is not None
