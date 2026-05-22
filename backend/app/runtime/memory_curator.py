from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from app.runtime.memory_policy import SENSITIVE_MARKERS, infer_memory_type
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
        """Process pending candidates. Returns {saved, ignored, errors, retried}."""
        candidates = candidate_store.pending(limit=self.max_batch)
        if not candidates:
            return {"saved": 0, "ignored": 0, "errors": 0, "retried": 0}

        result = {"saved": 0, "ignored": 0, "errors": 0, "retried": 0}
        try:
            decisions = self._call_llm(candidates)
        except Exception:
            logger.warning("Curator LLM call failed, marking for retry", exc_info=True)
            for cand in candidates:
                attempt = cand.get("attempt_count", 0) + 1
                candidate_store.mark_retryable(cand["id"], attempt)
                result["retried"] += 1
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

    def consolidate_batch(self, memory_manager: MemoryManager, limit: int = 4) -> Dict[str, int]:
        """Find and merge duplicate/similar memories. Returns {merged, skipped}."""
        result: Dict[str, int] = {"merged": 0, "skipped": 0}
        try:
            pairs = self._find_similar_pairs(memory_manager, limit)
            if not pairs:
                return result
            decisions = self._call_consolidation_llm(pairs)
            for i, (mem_a, mem_b) in enumerate(pairs):
                decision = decisions[i] if i < len(decisions) else None
                if decision is None or not decision.get("merge", False):
                    result["skipped"] += 1
                    continue
                try:
                    self._execute_merge(mem_a, mem_b, decision, memory_manager)
                    result["merged"] += 1
                except Exception:
                    logger.warning("Merge execution failed", exc_info=True)
                    result["skipped"] += 1
        except Exception:
            logger.warning("Consolidation batch failed", exc_info=True)
        return result

    def _find_similar_pairs(
        self, memory_manager: MemoryManager, limit: int
    ) -> List[tuple]:
        """Find pairs of memories with overlapping keywords by type."""
        pairs: List[tuple] = []
        with memory_manager.connection.locked():
            rows = memory_manager.connection.execute(
                "SELECT id, type, content, importance FROM memory ORDER BY type, id DESC LIMIT 100"
            ).fetchall()

        by_type: Dict[str, List[dict]] = {}
        for row in rows:
            d = dict(row)
            by_type.setdefault(d["type"], []).append(d)

        for mem_type, members in by_type.items():
            if len(members) < 2:
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a_bigrams = self._chinese_bigrams(members[i]["content"])
                    b_bigrams = self._chinese_bigrams(members[j]["content"])
                    if not a_bigrams or not b_bigrams:
                        continue
                    overlap = len(a_bigrams & b_bigrams) / min(len(a_bigrams), len(b_bigrams))
                    if overlap >= 0.4:
                        pairs.append((members[i], members[j]))
                        if len(pairs) >= limit:
                            return pairs
        return pairs

    @staticmethod
    def _chinese_bigrams(text: str) -> set:
        """Extract Chinese character bigrams for similarity comparison."""
        import re
        chars = re.findall(r"[\u4e00-\u9fff]", text)
        if len(chars) < 2:
            return set(chars)
        return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}

    def _call_consolidation_llm(self, pairs: List[tuple]) -> List[Dict[str, Any]]:
        """Ask LLM which pairs to merge and how."""
        pair_text = ""
        for i, (a, b) in enumerate(pairs):
            pair_text += "\n%d. [%s] A: \"%s\" (importance=%d) vs B: \"%s\" (importance=%d)" % (
                i + 1, a["type"], a["content"], a["importance"],
                b["content"], b["importance"],
            )

        system_prompt = (
            "你是记忆整合助手。判断以下记忆对是否重复/相似，是否应合并。\n\n"
            "输出 JSON：\n"
            '{"decisions": [{"merge": true, "keep_id": 1, "merged_content": "合并后内容", "merged_importance": 4, "reason": "..."}]}\n\n'
            "规则：\n"
            "1. 只有真正重复或高度相似才合并\n"
            "2. 保留更完整/更重要的那条\n"
            "3. merged_content 不超过 100 字\n"
            "4. 不确定就不合并 (merge=false)"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "记忆对：%s" % pair_text},
        ]
        raw = self.provider.complete_json(messages)
        decisions = raw.get("decisions", [])
        if not isinstance(decisions, list):
            return []
        return decisions

    def _execute_merge(
        self,
        mem_a: Dict[str, Any],
        mem_b: Dict[str, Any],
        decision: Dict[str, Any],
        memory_manager: MemoryManager,
    ) -> None:
        """Execute a merge: update one memory, delete the other."""
        keep_id = decision.get("keep_id")
        if keep_id is None:
            keep_id = mem_a["id"]
        try:
            keep_id = int(keep_id)
        except (TypeError, ValueError):
            keep_id = mem_a["id"]

        merged_content = str(decision.get("merged_content", "")).strip()
        if not merged_content:
            merged_content = mem_a["content"] if keep_id == mem_a["id"] else mem_b["content"]

        merged_importance = int(decision.get("merged_importance", max(mem_a["importance"], mem_b["importance"])))
        merged_importance = max(1, min(5, merged_importance))

        delete_id = mem_b["id"] if keep_id == mem_a["id"] else mem_a["id"]

        now = datetime.utcnow().isoformat()
        with memory_manager.connection.locked():
            memory_manager.connection.execute(
                "UPDATE memory SET content = ?, importance = ?, updated_at = ? WHERE id = ?",
                (merged_content, merged_importance, now, keep_id),
            )
            memory_manager.connection.execute(
                "DELETE FROM memory WHERE id = ?", (delete_id,)
            )
            memory_manager.connection.commit()
