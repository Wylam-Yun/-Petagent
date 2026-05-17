from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.runtime.actions import STATE_KEYS
from app.runtime.interaction_catalog import INTERACTION_CATALOG


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
        "intimacy": 4,
        "hunger": 0,
        "cleanliness": 0,
        "loneliness": -10,
        "sleepiness": 0,
    },
    "debug_happy": {"mood": "happy"},
    "debug_sleepy": {"mood": "sleepy", "sleepiness": 8, "energy": -5},
    "debug_angry": {"mood": "angry"},
    "voice_message": {"intimacy": 1, "loneliness": -4},
    "wake_phrase": {"mood": "happy", "loneliness": -3},
    "exit_phrase": {"mood": "sleepy", "sleepiness": 2},
    "morning": {"mood": "happy", "energy": 1, "loneliness": -1},
    "night": {"mood": "sleepy", "sleepiness": 3, "energy": -1},
    "long_idle": {"mood": "lonely", "loneliness": 2},
    "battery_low": {"mood": "sleepy", "energy": -3, "sleepiness": 2},
    "charging_started": {"mood": "happy", "energy": 5, "hunger": -5},
    "charging_stopped": {"mood": "idle"},
    "sleepy_time": {"mood": "sleepy", "sleepiness": 3},
    "user_return": {"mood": "happy", "loneliness": -5},
    "pet_pat": {"mood": "shy", "energy": 1, "intimacy": 2, "loneliness": -4},
    "praise_momo": {"mood": "happy", "energy": 4, "intimacy": 2, "loneliness": -2},
    "feed_momo": {"mood": "happy", "energy": 8, "intimacy": 1, "hunger": -10, "sleepiness": -2, "loneliness": -1},
    "stay_with_me": {"mood": "concerned", "intimacy": 1, "loneliness": -4},
    "comfort_me": {"mood": "concerned", "intimacy": 1, "loneliness": -6},
    "encourage_me": {"mood": "happy", "energy": -2, "intimacy": 2, "loneliness": -2},
    "listen_to_me": {"mood": "concerned", "intimacy": 1, "loneliness": -2},
    "tuck_in": {"mood": "sleepy", "sleepiness": 10, "energy": -1, "loneliness": -1},
    "clean_face": {"mood": "shy", "cleanliness": 10, "intimacy": 1},
    "quiet_company": {"mood": "idle", "loneliness": -4},
    "take_a_break": {"mood": "sleepy", "sleepiness": 3, "energy": 1, "loneliness": -3},
    "text_message": {"intimacy": 1, "loneliness": -3},
}


# Validate that all catalog button events have delta entries
_CATALOG_BUTTON_IDS = {k for k, v in INTERACTION_CATALOG.items() if v.group != "debug"}
_MISSING_DELTAS = _CATALOG_BUTTON_IDS - set(EVENT_DELTAS.keys())
assert not _MISSING_DELTAS, f"Catalog button events missing from EVENT_DELTAS: {_MISSING_DELTAS}"


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
