from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set


EXPRESSION_MAP: Dict[str, str] = {
    "idle_soft": "(・ω・)",
    "idle_wink": "(｡•̀ᴗ-)✧",
    "happy": "(^▽^)",
    "happy_big": "(≧▽≦)",
    "excited": "٩(ˊᗜˋ*)و",
    "shy": "(//▽//)",
    "clingy": "(*ﾉωﾉ)",
    "thinking": "(・・?)",
    "confused": "(。ヘ°)",
    "concerned": "(´・ω・)",
    "sad": "(｡•́︿•̀｡)",
    "crying": "(╥﹏╥)",
    "sleepy": "(-_-) zzz",
    "tired": "(￣o￣)",
    "annoyed": "(｀へ´)",
    "wronged": "(｡•́︿•̀｡)",
    "proud": "(๑•̀ㅂ•́)و✧",
    "playful": "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧",
    "lonely": "(._.)",
    "calm": "( ˘ω˘ )",
}

EXPRESSION_KEYS: Set[str] = set(EXPRESSION_MAP)

KAOMOJI_MARKERS = tuple(
    sorted(
        {
            *EXPRESSION_MAP.values(),
            "(^",
            "(｡",
            "(・",
            "(//",
            "٩(",
            "(╥",
            "(-_",
            "(￣",
            "(｀",
            "(๑",
            "(ﾉ",
            "(._",
            "( ˘",
            "(。",
            "(*ﾉ",
            "(≧",
            "(´",
            "(・・",
            "´・",
            "•̀",
            "•́",
            "ヘ°",
        },
        key=len,
        reverse=True,
    )
)

MOOD_EXPRESSION_FALLBACK: Dict[str, str] = {
    "idle": "idle_soft",
    "happy": "happy",
    "sad": "sad",
    "sleepy": "sleepy",
    "tired": "tired",
    "angry": "annoyed",
    "shy": "shy",
    "thinking": "thinking",
    "concerned": "concerned",
    "excited": "excited",
    "lonely": "lonely",
}


@dataclass(frozen=True)
class ActivityRecommendation:
    activity: str
    activity_class: str
    expression_keys: List[str]
    actions: List[str]
    strong_once_daily: bool = False


ACTIVITY_RECOMMENDATIONS: Dict[str, ActivityRecommendation] = {
    "stay_near": ActivityRecommendation(
        "stay_near", "near", ["idle_soft", "calm", "clingy"], ["idle", "greet"]
    ),
    "pretend_busy": ActivityRecommendation(
        "pretend_busy",
        "mischief",
        ["idle_wink", "proud", "playful"],
        ["pretend_busy", "remember"],
        True,
    ),
    "patrol": ActivityRecommendation(
        "patrol", "active", ["proud", "idle_wink", "happy"], ["wander", "running"]
    ),
    "self_groom": ActivityRecommendation(
        "self_groom", "care", ["calm", "happy", "shy"], ["self_groom"]
    ),
    "sneak_snack": ActivityRecommendation(
        "sneak_snack",
        "mischief",
        ["playful", "shy", "wronged"],
        ["sneak_eat"],
        True,
    ),
    "lazy_save_power": ActivityRecommendation(
        "lazy_save_power", "lazy", ["tired", "sleepy", "idle_wink"], ["lazy_idle", "nap"]
    ),
    "peek_user": ActivityRecommendation(
        "peek_user", "near", ["clingy", "idle_wink", "lonely"], ["listen", "greet"]
    ),
    "claim_corner": ActivityRecommendation(
        "claim_corner",
        "mischief",
        ["playful", "proud", "annoyed"],
        ["tease", "happy"],
        True,
    ),
    "watch_tiny_show": ActivityRecommendation(
        "watch_tiny_show",
        "mischief",
        ["playful", "thinking", "idle_wink"],
        ["watch_tv", "pretend_busy"],
        True,
    ),
    "quiet_guard": ActivityRecommendation(
        "quiet_guard", "quiet", ["calm", "idle_soft", "concerned"], ["idle", "listen"]
    ),
    "sleepy_curl": ActivityRecommendation(
        "sleepy_curl", "sleepy", ["sleepy", "tired", "calm"], ["nap", "lazy_idle"]
    ),
}


def expression_for_mood(mood: Optional[str]) -> str:
    return MOOD_EXPRESSION_FALLBACK.get(str(mood or ""), "idle_soft")


def normalize_expression_key(value: object, mood: object = None) -> str:
    if isinstance(value, str) and value in EXPRESSION_KEYS:
        return value
    return expression_for_mood(str(mood) if isinstance(mood, str) else None)


def contains_kaomoji(text: str) -> bool:
    return any(marker in str(text or "") for marker in KAOMOJI_MARKERS)


def activity_recommendation(activity: str) -> ActivityRecommendation:
    return ACTIVITY_RECOMMENDATIONS[activity]
