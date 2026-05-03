from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.runtime.actions import STATE_KEYS


EVENT_DELTAS = {
    "pet_head": {
        "mood": "shy",
        "energy": 0,
        "intimacy": 2,
        "hunger": 0,
        "cleanliness": 0,
        "loneliness": -5,
        "sleepiness": 0,
    },
    "poke_face": {
        "mood": "angry",
        "energy": 0,
        "intimacy": 0,
        "hunger": 0,
        "cleanliness": 0,
        "loneliness": -1,
        "sleepiness": 0,
    },
    "hug": {
        "mood": "happy",
        "energy": 0,
        "intimacy": 3,
        "hunger": 0,
        "cleanliness": 0,
        "loneliness": -8,
        "sleepiness": 0,
    },
    "debug_happy": {"mood": "happy"},
    "debug_sleepy": {"mood": "sleepy", "sleepiness": 8, "energy": -5},
    "debug_angry": {"mood": "angry"},
}


def clamp_value(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, min(100, number))


def clamp_state(state: Dict[str, Any]) -> Dict[str, Any]:
    updated = deepcopy(state)
    for key in STATE_KEYS:
        if key in updated:
            updated[key] = clamp_value(updated[key])
    return updated


def apply_event_rules(state: Dict[str, Any], event_type: str) -> Dict[str, Any]:
    updated = deepcopy(state)
    delta = EVENT_DELTAS.get(event_type, {})
    if "mood" in delta:
        updated["mood"] = delta["mood"]
    for key in STATE_KEYS:
        if key in delta:
            updated[key] = int(updated.get(key, 0)) + int(delta[key])
    return clamp_state(updated)


def apply_state_delta(state: Dict[str, Any], delta: Dict[str, int]) -> Dict[str, Any]:
    updated = deepcopy(state)
    for key in STATE_KEYS:
        if key in delta:
            updated[key] = int(updated.get(key, 0)) + int(delta[key])
    return clamp_state(updated)
