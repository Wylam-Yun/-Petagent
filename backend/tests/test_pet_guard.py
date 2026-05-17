from app.pet.guard import DEFAULT_STATE_DELTA_LIMITS, guard_action


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
    assert action.state_delta["intimacy"] == 3
    assert action.state_delta["loneliness"] == -10


def test_guard_uses_fallback_for_invalid_json():
    action = guard_action("not json")

    assert action.reply == "嗯嗯，Momo 在这儿。"
    assert action.mood == "happy"


def test_guard_allows_natural_length_replies_up_to_configured_limit():
    reply = "Momo 可以陪你把思路写清楚，先用哈希表记录见过的数字，再找目标差值。"

    action = guard_action({"reply": reply, "mood": "thinking"}, max_reply_chars=500)

    assert action.reply == reply


def test_guard_truncates_at_configured_reply_limit():
    reply = "呀" * 520

    action = guard_action({"reply": reply, "mood": "happy"}, max_reply_chars=500)

    assert len(action.reply) == 500
    assert action.reply.endswith("…")


def test_guard_strips_reasoning_from_reply():
    action = guard_action(
        {
            "reply": "<think>先分析用户昨天问了什么，再组织回答。</think>昨天我们主要聊了记忆测试。",
            "mood": "thinking",
        },
        max_reply_chars=500,
    )

    assert "<think>" not in action.reply
    assert "先分析" not in action.reply
    assert action.reply == "昨天我们主要聊了记忆测试。"


def test_guard_allows_large_feed_momo_hunger_delta():
    action = guard_action(
        {"reply": "吃饱啦~", "mood": "happy", "state_delta": {"hunger": -10}},
        event_type="feed_momo",
    )
    assert action.state_delta["hunger"] == -10


def test_guard_allows_large_sleepiness_delta():
    action = guard_action(
        {"reply": "困了", "mood": "sleepy", "state_delta": {"sleepiness": 10}},
    )
    assert action.state_delta["sleepiness"] == 10


def test_guard_still_clamps_extreme_values():
    action = guard_action(
        {"reply": "嗯嗯", "mood": "happy", "state_delta": {"energy": 99}},
    )
    assert action.state_delta["energy"] == 8


def test_guard_default_limits_match_expected_ranges():
    assert DEFAULT_STATE_DELTA_LIMITS["energy"] == (-8, 8)
    assert DEFAULT_STATE_DELTA_LIMITS["sleepiness"] == (-8, 10)
    assert DEFAULT_STATE_DELTA_LIMITS["loneliness"] == (-10, 4)
