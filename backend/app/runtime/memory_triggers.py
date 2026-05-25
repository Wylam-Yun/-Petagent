"""V1.3 Memory trigger detection: ~40 trigger phrases for background judgment.

No LLM calls. Pure string matching. Returns matched trigger categories.
"""
from __future__ import annotations

from typing import List

EXPLICIT_MEMORY_TRIGGERS = [
    "记住", "你要记得", "帮我记", "别忘了", "以后记得",
    "以后你要知道", "这个很重要", "记到小本本", "写进小本本",
]

PREFERENCE_TRIGGERS = [
    "我喜欢", "我不喜欢", "我讨厌", "我害怕", "我习惯",
    "我希望你", "我更喜欢", "我不想要", "以后不要", "以后可以",
]

IDENTITY_TRIGGERS = [
    "我叫", "我的名字", "我是", "我的生日", "我住在",
    "我的工作", "我的学校", "我的猫", "我的家人", "我的朋友",
]

RELATIONSHIP_TRIGGERS = [
    "今天我们", "刚刚我们", "以后我们", "这是我们的",
    "你陪我", "我们约好", "这次要记住",
]

_ALL_TRIGGERS = {
    "explicit": EXPLICIT_MEMORY_TRIGGERS,
    "preference": PREFERENCE_TRIGGERS,
    "identity": IDENTITY_TRIGGERS,
    "relationship": RELATIONSHIP_TRIGGERS,
}


def detect_memory_triggers(user_text: str) -> List[str]:
    """Return list of matched trigger categories. Empty if no triggers found."""
    if not user_text or not user_text.strip():
        return []
    matched = []
    for category, phrases in _ALL_TRIGGERS.items():
        for phrase in phrases:
            if phrase in user_text:
                matched.append(category)
                break  # one match per category is enough
    return matched
