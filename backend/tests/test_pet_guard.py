from app.pet.guard import guard_action


def test_guard_replaces_invalid_mood_and_limits_delta():
    action = guard_action(
        {
            "reply": "Momo 在呢。",
            "mood": "not-a-mood",
            "face_type": "not-a-face",
            "animation": "not-animation",
            "vibration": "light",
            "state_delta": {"intimacy": 999, "loneliness": -999},
            "memory_update": {"should_save": False, "content": ""},
        }
    )

    assert action.mood == "idle"
    assert action.face_type == "idle"
    assert action.animation == "breathing"
    assert action.state_delta["intimacy"] == 2
    assert action.state_delta["loneliness"] == -5


def test_guard_uses_fallback_for_invalid_json():
    action = guard_action("not json")

    assert action.reply == "嗯嗯，Momo 在这儿。"
    assert action.mood == "happy"
