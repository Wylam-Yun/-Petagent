from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from app.runtime.actions import (
    ALLOWED_ANIMATIONS,
    ALLOWED_BEHAVIOR_ACTIONS,
    ALLOWED_BEHAVIOR_INTENTS,
    ALLOWED_BEHAVIOR_SLOTS,
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


DEFAULT_STATE_DELTA_LIMITS = {
    "energy": (-8, 8),
    "intimacy": (-3, 3),
    "hunger": (-10, 8),
    "cleanliness": (-8, 10),
    "loneliness": (-10, 4),
    "sleepiness": (-8, 10),
}

EVENT_STATE_DELTA_LIMITS = {
    "feed_momo": {"hunger": (-12, 2), "energy": (-3, 8)},
    "charging_started": {"hunger": (-5, 2), "energy": (-3, 8)},
    "clean_face": {"cleanliness": (-2, 12)},
    "tuck_in": {"sleepiness": (-2, 12), "energy": (-5, 3)},
    "hug": {"intimacy": (-3, 5), "loneliness": (-12, 4)},
}

DEFAULT_MAX_REPLY_CHARS = 500

MAX_BEHAVIOR_STEPS = 4
MAX_BEHAVIOR_TOTAL_MS = 8000
MIN_BEHAVIOR_DURATION_MS = 600
MAX_BEHAVIOR_DURATION_MS = 2500

_BEHAVIOR_DEFAULT_DURATIONS = {
    "failed": 900,
    "waving": 1200,
    "jumping": 1200,
    "idle": 1400,
    "waiting": 1400,
    "review": 1400,
    "running": 1400,
    "running-left": 1400,
    "running-right": 1400,
}


def _sanitize_behavior_plan(raw: Any) -> Optional[list]:
    if not isinstance(raw, list):
        return None
    steps = []
    for item in raw:
        if len(steps) >= MAX_BEHAVIOR_STEPS:
            break
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        if not isinstance(action, str) or action not in ALLOWED_BEHAVIOR_ACTIONS:
            continue
        slot = item.get("slot", "speech")
        if not isinstance(slot, str) or slot not in ALLOWED_BEHAVIOR_SLOTS:
            slot = "speech"
        duration = item.get("duration_ms")
        default = _BEHAVIOR_DEFAULT_DURATIONS.get(action, 1400)
        if duration is None or not isinstance(duration, (int, float)):
            duration = default
        duration = max(MIN_BEHAVIOR_DURATION_MS, min(MAX_BEHAVIOR_DURATION_MS, int(duration)))
        steps.append({"action": action, "slot": slot, "duration_ms": duration})
    if not steps:
        return None
    # Enforce total duration cap
    total = 0
    capped = []
    for step in steps:
        if total + step["duration_ms"] > MAX_BEHAVIOR_TOTAL_MS:
            break
        capped.append(step)
        total += step["duration_ms"]
    return capped or None


def _sanitize_behavior_intent(raw: Any) -> Optional[str]:
    if isinstance(raw, str) and raw in ALLOWED_BEHAVIOR_INTENTS:
        return raw
    return None

FALLBACK_ACTION = {
    "reply": "嗯嗯，豆豆在这儿。",
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
        "cleanliness": 0,
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


def _limits_for_event(event_type: str = "") -> Dict[str, tuple]:
    limits = dict(DEFAULT_STATE_DELTA_LIMITS)
    for key, value in EVENT_STATE_DELTA_LIMITS.get(event_type, {}).items():
        limits[key] = value
    return limits


def _clamp_delta(delta: Dict[str, Any], event_type: str = "") -> Dict[str, int]:
    guarded: Dict[str, int] = {}
    limits_by_key = _limits_for_event(event_type)
    for key, limits in limits_by_key.items():
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


_PROMPT_LEAK_PATTERNS = re.compile(
    r"(?:state_delta|memory_update|cognition_context|output_schema|"
    r"scene_context|系统提示|上下文字段|skill_requests|provider_profile|JSON|规则)",
    re.IGNORECASE,
)


def _strip_reasoning(reply: str) -> str:
    """Remove model thinking traces that accidentally landed in reply."""
    cleaned = re.sub(r"<think>.*?</think>", "", reply, flags=re.S | re.I).strip()
    cleaned = re.sub(r"(?is)^思考过程[:：].*?(?:最终回复[:：]|回答[:：])", "", cleaned).strip()
    cleaned = re.sub(r"(?is)^推理过程[:：].*?(?:最终回复[:：]|回答[:：])", "", cleaned).strip()
    cleaned = re.sub(r"(?is)^(?:let me think|here'?s? (?:my )?reasoning|step[- ]by[- ]step)[:\s].*?(?=\n\n|\Z)", "", cleaned).strip()
    cleaned = re.sub(r"(?i)\*\*(?:thinking|reasoning|step[- ]by[- ]step)\*\*[:\s].*?(?=\n\n|\Z)", "", cleaned, flags=re.S).strip()
    return cleaned or FALLBACK_ACTION["reply"]


def _sanitize_prompt_leak(reply: str) -> str:
    """Remove lines containing internal field names that should never appear in user replies."""
    lines = reply.split("\n")
    clean = [line for line in lines if not _PROMPT_LEAK_PATTERNS.search(line)]
    result = "\n".join(clean).strip()
    return result or FALLBACK_ACTION["reply"]


def guard_action(
    raw: Any,
    max_reply_chars: int = DEFAULT_MAX_REPLY_CHARS,
    event_type: str = "",
) -> PetAction:
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

    reply = _strip_reasoning(str(data.get("reply", "")).strip())
    reply = _sanitize_prompt_leak(reply)
    if not reply:
        reply = FALLBACK_ACTION["reply"]
    reply = _trim_reply(reply, max_reply_chars)

    return PetAction(
        reply=reply,
        mood=mood,
        face_type=face_type,
        animation=animation,
        voice_style=voice_style,
        vibration=vibration,
        intent=str(data.get("intent", "stage1_response")),
        autonomy_notes=str(data.get("autonomy_notes", "")),
        state_delta=_clamp_delta(data.get("state_delta") or {}, event_type),
        state_affect=_guard_state_affect(data.get("state_affect") or {}),
        memory_update=data.get("memory_update") or {"should_save": False, "content": ""},
        behavior_intent=_sanitize_behavior_intent(data.get("behavior_intent")),
        behavior_plan=_sanitize_behavior_plan(data.get("behavior_plan")),
    )
