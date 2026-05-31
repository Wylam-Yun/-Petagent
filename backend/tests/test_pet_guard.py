import pytest

from app.pet.guard import DEFAULT_STATE_DELTA_LIMITS, InvalidActionError, guard_action


def test_guard_replaces_invalid_mood_and_limits_delta():
    action = guard_action(
        {
            "reply": "豆豆在呢。",
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
    assert action.expression_key == "idle_soft"
    assert action.animation == "breathing"
    assert action.state_delta["intimacy"] == 3
    assert action.state_delta["loneliness"] == -10


def test_guard_raises_for_invalid_json():
    with pytest.raises(InvalidActionError):
        guard_action("not json")


def test_guard_allows_natural_length_replies_up_to_configured_limit():
    reply = "豆豆可以陪你把思路写清楚，先用哈希表记录见过的数字，再找目标差值。"

    action = guard_action({"reply": reply, "mood": "thinking"}, max_reply_chars=500)

    assert action.reply == "我可以陪你把思路写清楚，先用哈希表记录见过的数字，再找目标差值。"


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


def test_guard_strips_unclosed_think_block_with_final_reply():
    action = guard_action(
        {
            "reply": "<think>先判断用户是在打招呼。\n最终回复：早呀主人，豆豆醒着呢～",
            "mood": "happy",
        },
        max_reply_chars=500,
    )

    assert "<think>" not in action.reply
    assert "先判断" not in action.reply
    assert action.reply == "早呀主人，我醒着呢～"


def test_guard_strips_chinese_structured_reasoning_markers():
    action = guard_action(
        {
            "reply": "思考：用户在问早安，需要可爱简短回应。\n最终答案：早呀主人，豆豆来蹭蹭你。",
            "mood": "happy",
        },
        max_reply_chars=500,
    )

    assert "思考" not in action.reply
    assert "用户在问" not in action.reply
    assert action.reply == "早呀主人，我来蹭蹭你。"


def test_guard_strips_english_markdown_reasoning_markers():
    action = guard_action(
        {
            "reply": "**Analysis:** The user greeted the pet.\n\n**Final answer:** Morning,豆豆在这里。",
            "mood": "happy",
        },
        max_reply_chars=500,
    )

    assert "Analysis" not in action.reply
    assert "The user" not in action.reply
    assert action.reply == "Morning,我在这里。"


def test_guard_raises_when_reply_is_only_reasoning():
    with pytest.raises(InvalidActionError):
        guard_action(
            {
                "reply": "内部分析：用户在测试模型是否泄漏思考过程。",
                "mood": "thinking",
            },
            max_reply_chars=500,
        )


def test_guard_drops_reasoning_appended_after_visible_reply():
    action = guard_action(
        {
            "reply": "早呀主人，豆豆在这里。\n\n分析：这里不应该给用户看到。",
            "mood": "happy",
        },
        max_reply_chars=500,
    )

    assert action.reply == "早呀主人，我在这里。"


def test_guard_preserves_normal_user_facing_analysis_reply():
    reply = "分析：这件事可以先从最简单的入口看，再慢慢拆开。"
    action = guard_action({"reply": reply, "mood": "thinking"}, max_reply_chars=500)

    assert action.reply == reply


def test_guard_preserves_analysis_reply_that_mentions_user_as_topic():
    reply = "分析：用户画像可以先写使用场景，再写核心需求。"
    action = guard_action({"reply": reply, "mood": "thinking"}, max_reply_chars=500)

    assert action.reply == reply


def test_guard_replaces_legacy_pet_name_in_visible_reply():
    action = guard_action({"reply": "早呀，Momo 在这里。momo 刚醒。", "mood": "happy"})

    assert "Momo" not in action.reply
    assert "momo" not in action.reply
    assert action.reply == "早呀，我 在这里。我 刚醒。"


def test_guard_action_rejects_catalog_kaomoji_in_tts_reply():
    for reply in ["我在(´・ω・)", "我超开心(≧▽≦)"]:
        with pytest.raises(InvalidActionError) as exc_info:
            guard_action({"reply": reply, "mood": "happy"})
        assert exc_info.value.error_class == "llm_invalid_output"


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


def test_sanitize_prompt_leak_removes_internal_fields():
    from app.pet.guard import _sanitize_prompt_leak
    reply = "你好呀\nstate_delta: {energy: 5}\n今天天气不错"
    result = _sanitize_prompt_leak(reply)
    assert "state_delta" not in result
    assert "你好呀" in result
    assert "天气不错" in result


def test_sanitize_prompt_leak_all_leaked_returns_empty():
    from app.pet.guard import _sanitize_prompt_leak
    reply = "state_delta: {energy: 5}\nmemory_update: {should_save: true}"
    result = _sanitize_prompt_leak(reply)
    assert result == ""


def test_guard_action_strips_prompt_leak():
    action = guard_action({
        "reply": "你好呀\nstate_delta: {energy: 5}\ncognition_context: {profile: fast}",
        "mood": "happy",
    })
    assert "state_delta" not in action.reply
    assert "cognition_context" not in action.reply


def test_guard_preserves_valid_behavior_plan():
    action = guard_action({
        "reply": "豆豆开心~",
        "mood": "happy",
        "behavior_intent": "clingy_happy",
        "behavior_plan": [
            {"action": "comfort", "slot": "before_speech", "duration_ms": 1200},
            {"action": "speak", "slot": "speech", "duration_ms": 1000},
        ],
    })
    assert action.behavior_intent == "clingy_happy"
    assert action.behavior_plan is not None
    assert len(action.behavior_plan) == 2
    assert action.behavior_plan[0]["action"] == "comfort"
    assert action.behavior_plan[1]["action"] == "speak"


def test_guard_accepts_v14_product_behavior_actions():
    action = guard_action({
        "reply": "豆豆记住啦。",
        "mood": "happy",
        "behavior_plan": [
            {"action": "remember", "slot": "before_speech"},
            {"action": "happy", "slot": "speech"},
            {"action": "nap", "slot": "idle_after"},
            {"action": "sneak_eat", "slot": "after_speech"},
        ],
    })
    assert action.behavior_plan is not None
    assert [step["action"] for step in action.behavior_plan] == [
        "remember",
        "happy",
        "nap",
        "sneak_eat",
    ]


def test_guard_drops_unknown_behavior_actions():
    action = guard_action({
        "reply": "嗯",
        "mood": "idle",
        "behavior_plan": [
            {"action": "sleep", "slot": "speech", "duration_ms": 1000},
            {"action": "listen", "slot": "speech", "duration_ms": 1200},
        ],
    })
    assert action.behavior_plan is not None
    assert len(action.behavior_plan) == 1
    assert action.behavior_plan[0]["action"] == "listen"


def test_guard_repairs_unknown_behavior_slots():
    action = guard_action({
        "reply": "嗯",
        "mood": "idle",
        "behavior_plan": [
            {"action": "idle", "slot": "invalid", "duration_ms": 1000},
        ],
    })
    assert action.behavior_plan is not None
    assert action.behavior_plan[0]["slot"] == "speech"


def test_guard_clamps_behavior_duration():
    action = guard_action({
        "reply": "嗯",
        "mood": "idle",
        "behavior_plan": [
            {"action": "idle", "slot": "speech", "duration_ms": 100},
            {"action": "waving", "slot": "speech", "duration_ms": 9999},
        ],
    })
    assert action.behavior_plan is not None
    assert action.behavior_plan[0]["duration_ms"] == 600
    assert action.behavior_plan[1]["duration_ms"] == 2500


def test_guard_limits_behavior_plan_to_4_steps():
    action = guard_action({
        "reply": "嗯",
        "mood": "idle",
        "behavior_plan": [
            {"action": "idle", "slot": "speech", "duration_ms": 1000},
            {"action": "waving", "slot": "speech", "duration_ms": 1000},
            {"action": "jumping", "slot": "speech", "duration_ms": 1000},
            {"action": "failed", "slot": "speech", "duration_ms": 1000},
            {"action": "review", "slot": "speech", "duration_ms": 1000},
        ],
    })
    assert action.behavior_plan is not None
    assert len(action.behavior_plan) == 4


def test_guard_caps_behavior_total_duration():
    action = guard_action({
        "reply": "嗯",
        "mood": "idle",
        "behavior_plan": [
            {"action": "idle", "slot": "speech", "duration_ms": 2500},
            {"action": "waving", "slot": "speech", "duration_ms": 2500},
            {"action": "jumping", "slot": "speech", "duration_ms": 2500},
            {"action": "failed", "slot": "speech", "duration_ms": 2500},
        ],
    })
    assert action.behavior_plan is not None
    total = sum(s["duration_ms"] for s in action.behavior_plan)
    assert total <= 8000


def test_guard_returns_none_plan_for_invalid_input():
    action = guard_action({
        "reply": "嗯",
        "mood": "idle",
        "behavior_plan": "not a list",
    })
    assert action.behavior_plan is None


def test_guard_rejects_invalid_behavior_intent():
    action = guard_action({
        "reply": "嗯",
        "mood": "idle",
        "behavior_intent": "unknown_intent",
    })
    assert action.behavior_intent is None
