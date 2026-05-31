from __future__ import annotations

from typing import Any, Dict, Iterable, List


_QUESTION_MARKERS = (
    "？",
    "?",
    "嘛",
    "干嘛",
    "什么",
    "怎么",
    "为什么",
    "为啥",
    "几",
    "多少",
    "哪",
    "谁",
    "吗",
    "总结",
    "解释",
    "说说",
)
_REFUSAL_MARKERS = ("哪有空", "没空", "不管", "懒得", "不想理", "别烦")
_CONTEXT_EXCUSE_MARKERS = (
    "小本本",
    "记你",
    "记住你",
    "记进",
    "翻记忆",
    "记忆里",
    "手机使用时长",
)
_DIRECT_ANSWER_MARKERS: Dict[str, tuple[str, ...]] = {
    "星期": ("星期", "周一", "周二", "周三", "周四", "周五", "周六", "周日", "礼拜"),
    "超时": ("网络", "请求", "ASR", "服务", "响应", "timeout"),
    "心情": ("心情", "有点", "开心", "平静", "生气", "烦", "困", "还好"),
    "总结": ("刚才", "总结", "聊了", "说了", "提到"),
}


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    return any(marker in text for marker in markers)


def _is_question_or_task(user_text: str) -> bool:
    stripped = str(user_text or "").strip()
    if not stripped:
        return False
    return _contains_any(stripped, _QUESTION_MARKERS)


def _has_topic_answer_marker(user_text: str, reply: str) -> bool:
    for topic, markers in _DIRECT_ANSWER_MARKERS.items():
        if topic in user_text:
            return _contains_any(reply, markers)
    return True


def _recent_pet_replies(recent_context: Any) -> List[str]:
    if not isinstance(recent_context, list):
        return []
    replies: List[str] = []
    for item in recent_context:
        if isinstance(item, dict):
            text = str(item.get("pet") or item.get("pet_reply") or "").strip()
            if text:
                replies.append(text)
    return replies


def is_unified_reply_contract_violation(
    *,
    user_text: str,
    reply: str,
    recent_context: Any = None,
) -> bool:
    """Return True for replies that should fail instead of being recorded as success.

    This is intentionally narrow: it catches the observed V1.7 failure mode where
    the model turns recent context or memory into a refusal excuse for a normal
    user question. It does not generate replacement text and does not perform
    semantic memory deduplication.
    """
    current = str(user_text or "").strip()
    answer = str(reply or "").strip()
    if not _is_question_or_task(current) or not answer:
        return False

    refusal = _contains_any(answer, _REFUSAL_MARKERS)
    context_excuse = _contains_any(answer, _CONTEXT_EXCUSE_MARKERS)
    if refusal and context_excuse:
        return True

    if context_excuse and not _has_topic_answer_marker(current, answer):
        return True

    return False
