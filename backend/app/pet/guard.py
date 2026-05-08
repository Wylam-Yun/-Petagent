from __future__ import annotations

import json
import re
from typing import Any, Dict

from app.runtime.actions import (
    ALLOWED_ANIMATIONS,
    ALLOWED_EMOTIONAL_EFFECTS,
    ALLOWED_INTERACTION_TONES,
    ALLOWED_MOODS,
    ALLOWED_PET_EFFORTS,
    ALLOWED_VIBRATIONS,
    ALLOWED_VOICE_STYLES,
    MOOD_ANIMATION_MAP,
    PetAction,
    StateAffect,
)


STATE_DELTA_LIMITS = {
    "energy": (-5, 5),
    "intimacy": (-1, 2),
    "hunger": (-5, 5),
    "cleanliness": (-2, 2),
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


def _guard_state_affect(raw: Any) -> StateAffect:
    data = raw if isinstance(raw, dict) else {}
    tone = str(data.get("interaction_tone") or "neutral")
    effort = str(data.get("pet_effort") or "none")
    effect = str(data.get("emotional_effect") or "uncertain")
    reason = str(data.get("reason") or "").strip()
    if tone not in ALLOWED_INTERACTION_TONES:
        tone = "neutral"
    if effort not in ALLOWED_PET_EFFORTS:
        effort = "none"
    if effect not in ALLOWED_EMOTIONAL_EFFECTS:
        effect = "uncertain"
    if len(reason) > 120:
        reason = reason[:119] + "…"
    return StateAffect(
        interaction_tone=tone,
        pet_effort=effort,
        emotional_effect=effect,
        reason=reason,
    )


def _strip_reasoning(reply: str) -> str:
    """Remove model thinking traces that accidentally landed in reply."""
    cleaned = re.sub(r"<think>.*?</think>", "", reply, flags=re.S | re.I).strip()
    cleaned = re.sub(r"(?is)^思考过程[:：].*?(?:最终回复[:：]|回答[:：])", "", cleaned).strip()
    cleaned = re.sub(r"(?is)^推理过程[:：].*?(?:最终回复[:：]|回答[:：])", "", cleaned).strip()
    return cleaned or FALLBACK_ACTION["reply"]


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

    reply = _trim_reply(
        _strip_reasoning(str(data.get("reply", FALLBACK_ACTION["reply"])).strip()),
        max_reply_chars,
    )

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
        state_affect=_guard_state_affect(data.get("state_affect") or {}),
        memory_update=data.get("memory_update") or {"should_save": False, "content": ""},
    )
