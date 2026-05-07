"""Memory policy constants and helpers shared across the memory pipeline."""

from __future__ import annotations

SENSITIVE_MARKERS = {
    "身份证",
    "银行卡",
    "密码",
    "api key",
    "token",
    "密钥",
    "住址",
}


def infer_memory_type(content: str) -> str:
    """Infer memory type from content keywords."""
    lowered = content.lower()
    if "喜欢" in content or "不喜欢" in content or "偏好" in content:
        return "user_preference"
    if "累" in content or "烦" in content or "难过" in content or "开心" in content:
        return "recent_mood"
    if "明天" in content or "面试" in content or "项目" in content:
        return "important_event"
    if "经常" in content or "习惯" in content:
        return "habit"
    if "叫我" in content or "称呼" in content or "william" in lowered:
        return "relationship"
    return "important_event"
