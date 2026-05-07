from __future__ import annotations

import json
from typing import Any, Dict

from app.runtime.actions import (
    ALLOWED_ANIMATIONS,
    ALLOWED_MOODS,
    ALLOWED_VIBRATIONS,
    ALLOWED_VOICE_STYLES,
    MOOD_ANIMATION_MAP,
    PetAction,
)


STATE_DELTA_LIMITS = {
    "energy": (-5, 5),
    "intimacy": (-1, 2),
    "hunger": (-5, 5),
    "loneliness": (-5, 2),
    "sleepiness": (-5, 5),
}

DEFAULT_MAX_REPLY_CHARS = 500

FALLBACK_ACTION = {
    "reply": "嗯嗯，Momo 在这儿。",
    "mood": "happy",
    "face_type": "happy",
    "animation": "breathing",
    "voice_style": "soft",
    "vibration": "light",
    "intent": "fallback",
    "autonomy_notes": "provider unavailable or invalid output",
    "state_delta": {
        "energy": 0,
        "intimacy": 0,
        "hunger": 0,
        "loneliness": -1,
        "sleepiness": 0,
    },
    "memory_update": {"should_save": False, "content": ""},
}


def _parse_action(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return dict(FALLBACK_ACTION)
    return dict(FALLBACK_ACTION)


def _clamp_delta(delta: Dict[str, Any]) -> Dict[str, int]:
    guarded: Dict[str, int] = {}
    for key, limits in STATE_DELTA_LIMITS.items():
        value = delta.get(key, 0)
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = 0
        low, high = limits
        guarded[key] = max(low, min(high, number))
    return guarded


def _trim_reply(reply: str, max_reply_chars: int) -> str:
    max_chars = max(1, int(max_reply_chars or DEFAULT_MAX_REPLY_CHARS))
    if len(reply) <= max_chars:
        return reply
    if max_chars == 1:
        return "…"
    return reply[: max_chars - 1] + "…"


def guard_action(raw: Any, max_reply_chars: int = DEFAULT_MAX_REPLY_CHARS) -> PetAction:
    data = _parse_action(raw)
    if not data.get("reply"):
        data = dict(FALLBACK_ACTION)

    mood = data.get("mood", "idle")
    if mood not in ALLOWED_MOODS:
        mood = "idle"
    face_type = data.get("face_type") or mood
    if face_type not in ALLOWED_MOODS:
        face_type = mood

    animation = data.get("animation") or MOOD_ANIMATION_MAP.get(mood, "breathing")
    if animation not in ALLOWED_ANIMATIONS:
        animation = MOOD_ANIMATION_MAP.get(mood, "breathing")

    voice_style = data.get("voice_style", "soft")
    if voice_style not in ALLOWED_VOICE_STYLES:
        voice_style = "soft"

    vibration = data.get("vibration", "none")
    if vibration not in ALLOWED_VIBRATIONS:
        vibration = "none"

    reply = _trim_reply(str(data.get("reply", FALLBACK_ACTION["reply"])).strip(), max_reply_chars)

    return PetAction(
        reply=reply,
        mood=mood,
        face_type=face_type,
        animation=animation,
        voice_style=voice_style,
        vibration=vibration,
        intent=str(data.get("intent", "stage1_response")),
        autonomy_notes=str(data.get("autonomy_notes", "")),
        state_delta=_clamp_delta(data.get("state_delta") or {}),
        memory_update=data.get("memory_update") or {"should_save": False, "content": ""},
    )
