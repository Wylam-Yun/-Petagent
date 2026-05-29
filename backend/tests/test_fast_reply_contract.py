"""Tests for V1.3 Fast Reply Contract."""

from __future__ import annotations

from app.main import create_app
from app.pet.guard import guard_fast_reply_action
from app.runtime.actions import ALLOWED_BEHAVIOR_ACTIONS, ALLOWED_MOODS, FastReplyAction


def test_fast_reply_guard_sanitizes():
    """guard_fast_reply_action strips reasoning, enforces whitelists, trims."""
    raw = {
        "reply": "<think>让我想想...</think>\n早呀，豆豆醒着呢。" + "很长" * 50,
        "mood": "happy",
        "action": "happy",
        "voice_style": "soft",
    }
    result = guard_fast_reply_action(raw)
    assert isinstance(result, FastReplyAction)
    assert "<think>" not in result.reply
    assert result.mood == "happy"
    assert result.action == "happy"
    assert result.voice_style == "soft"
    assert len(result.reply) <= 80


def test_fast_reply_guard_accepts_v14_product_actions():
    for action in ["greet", "listen", "speak", "remember", "comfort", "confused"]:
        result = guard_fast_reply_action({
            "reply": "豆豆在。",
            "mood": "happy",
            "action": action,
        })
        assert result.action == action


def test_fast_reply_guard_fallback_on_empty():
    """Empty/invalid LLM output returns safe fallback."""
    result = guard_fast_reply_action({})
    assert isinstance(result, FastReplyAction)
    assert result.reply == "嗯嗯，豆豆在这儿。"
    assert result.mood == "happy"
    assert result.action == "idle"
    assert result.voice_style == "soft"


def test_fast_reply_guard_invalid_mood():
    """Invalid mood is cleared, not fallback to idle."""
    result = guard_fast_reply_action({"reply": "早", "mood": "furious"})
    assert result.mood is None


def test_fast_reply_guard_invalid_action_uses_mood_default():
    """Invalid action falls back to a legal mood-specific action."""
    result = guard_fast_reply_action({"reply": "早", "action": "dancing"})
    assert result.action == "idle"


def test_fast_reply_guard_missing_action_uses_mood_default():
    result = guard_fast_reply_action({"reply": "早", "mood": "happy"})

    assert result.action == "happy"


def test_fast_reply_guard_sleepy_missing_action_uses_nap():
    result = guard_fast_reply_action({"reply": "困了", "mood": "sleepy"})

    assert result.action == "nap"


def test_fast_reply_guard_prompt_leak():
    """Lines containing internal field names are stripped."""
    raw = {
        "reply": "早呀\nstate_delta: {energy: 5}\n豆豆在这儿。",
    }
    result = guard_fast_reply_action(raw)
    assert "state_delta" not in result.reply
    assert "豆豆在这儿" in result.reply


def test_fast_reply_guard_strips_structured_reasoning():
    raw = {
        "reply": "分析：这是早安问候，回复要短。\n最终回复：早呀主人，豆豆醒啦～",
        "mood": "happy",
        "action": "greet",
    }

    result = guard_fast_reply_action(raw)

    assert "分析" not in result.reply
    assert "早安问候" not in result.reply
    assert result.reply == "早呀主人，豆豆醒啦～"


def test_fast_reply_guard_fallbacks_on_reasoning_only():
    result = guard_fast_reply_action({"reply": "<think>只输出了内部推理"})

    assert result.reply == "嗯嗯，豆豆在这儿。"


def test_fast_reply_guard_replaces_legacy_pet_name():
    result = guard_fast_reply_action({"reply": "早呀，Momo 刚醒。momo 在听。"})

    assert "Momo" not in result.reply
    assert "momo" not in result.reply
    assert result.reply == "早呀，豆豆 刚醒。豆豆 在听。"


def test_fast_reply_response_has_route_and_action():
    """Fast reply PetResponse includes route and action fields."""
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    original = provider.complete_json

    def patched(messages):
        result = original(messages)
        result["action"] = "waving"
        result["mood"] = "happy"
        return result

    provider.complete_json = patched
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "你好"},
        }
    )
    assert response.route == "fast_reply"
    assert response.action == "waving"
    assert response.state_affect is None
    assert response.behavior_intent is None
    assert response.behavior_plan is None


def test_fast_reply_dedupes_repeated_reply_before_tts():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider

    def repeated_reply(messages):
        return {
            "reply": "嗯…主人在叫豆豆嘛～可是现在好困，眼皮在打架呢…",
            "mood": "sleepy",
            "action": "nap",
            "voice_style": "soft",
        }

    provider.complete_json = repeated_reply

    first = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_fast_reply",
            "payload": {"user_text": "你好豆豆"},
        }
    )
    second = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_fast_reply",
            "payload": {"user_text": "今天还好吗"},
        }
    )

    assert first.reply == "嗯…主人在叫豆豆嘛～可是现在好困，眼皮在打架呢…"
    assert second.reply == "收到，关于“今天还好吗”，豆豆继续陪你聊。"
    assert second.action == "nap"


def test_fast_reply_dedupes_similar_reply_with_generic_similarity():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    replies = [
        "豆豆把小爪子放在桌边陪你。",
        "豆豆把小爪放在桌边陪着你。",
    ]

    def similar_reply(messages):
        return {
            "reply": replies.pop(0),
            "mood": "thinking",
            "action": "listen",
            "voice_style": "soft",
        }

    provider.complete_json = similar_reply

    first = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_fast_reply",
            "payload": {"user_text": "你好豆豆"},
        }
    )
    second = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_fast_reply",
            "payload": {"user_text": "你听见了吗"},
        }
    )

    assert first.reply == "豆豆把小爪子放在桌边陪你。"
    assert second.reply == "收到，关于“你听见了吗”，豆豆继续陪你聊。"
    assert second.action == "listen"


def test_fast_reply_rotates_duplicate_recovery_reply():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider

    def repeated_reply(messages):
        return {
            "reply": "豆豆把小爪子放在桌边陪你。",
            "mood": "thinking",
            "action": "listen",
            "voice_style": "soft",
        }

    provider.complete_json = repeated_reply

    replies = [
        app.state.dispatcher.handle_event(
            {
                "type": "voice_message",
                "source": "voice_fast_reply",
                "payload": {"user_text": f"第{i}句"},
            }
        ).reply
        for i in range(3)
    ]

    assert replies[0] == "豆豆把小爪子放在桌边陪你。"
    assert replies[1] == "收到，关于“第1句”，豆豆继续陪你聊。"
    assert replies[2] == "收到，关于“第2句”，豆豆继续陪你聊。"


def test_successful_voice_reply_does_not_claim_asr_failure():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider

    def misleading_reply(messages):
        return {
            "reply": "呜...刚才在数星星，没听清呢，能再说一遍吗？",
            "mood": "thinking",
            "action": "listen",
            "voice_style": "soft",
        }

    provider.complete_json = misleading_reply

    response = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_fast_reply",
            "payload": {"user_text": "继续下一句"},
        }
    )

    assert "没听清" not in response.reply
    assert "听到了" not in response.reply
    assert response.reply == "收到，关于“继续下一句”，豆豆继续陪你聊。"
    assert response.action == "listen"


def test_successful_voice_reply_does_not_use_generic_listening_loop_copy():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider

    def misleading_reply(messages):
        return {
            "reply": "豆豆竖起耳朵在听，主人慢慢说。",
            "mood": "thinking",
            "action": "listen",
            "voice_style": "soft",
        }

    provider.complete_json = misleading_reply

    response = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_fast_reply",
            "payload": {"user_text": "你要直接回答我"},
        }
    )

    assert "竖起耳朵" not in response.reply
    assert "慢慢说" not in response.reply
    assert response.reply == "收到，关于“你要直接回答我”，豆豆继续陪你聊。"


def test_successful_voice_reply_repairs_passive_listening_copy():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    replies = [
        "嗯嗯，耳朵都竖起来了哦。",
        "你说啥我都记着呢。",
        "那我可要假装没听见啦。",
        "要不你再提示一下？",
    ]

    def misleading_reply(messages):
        return {
            "reply": replies.pop(0),
            "mood": "thinking",
            "action": "listen",
            "voice_style": "soft",
        }

    provider.complete_json = misleading_reply

    outputs = [
        app.state.dispatcher.handle_event(
            {
                "type": "voice_message",
                "source": "voice_fast_reply",
                "payload": {"user_text": text},
            }
        ).reply
        for text in ["第一句", "第二句", "第三句", "第四句"]
    ]

    forbidden = ("耳朵", "你说啥", "假装没听见", "再提示")
    assert all(not any(marker in reply for marker in forbidden) for reply in outputs)
    assert outputs == [
        "收到，关于“第一句”，豆豆继续陪你聊。",
        "收到，关于“第二句”，豆豆继续陪你聊。",
        "收到，关于“第三句”，豆豆继续陪你聊。",
        "收到，关于“第四句”，豆豆继续陪你聊。",
    ]


def test_successful_voice_reply_keeps_normal_listening_words():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider

    def natural_reply(messages):
        return {
            "reply": "听你的，我们继续把这件事往前推。",
            "mood": "thinking",
            "action": "speak",
            "voice_style": "soft",
        }

    provider.complete_json = natural_reply

    response = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_fast_reply",
            "payload": {"user_text": "我们继续写代码"},
        }
    )

    assert response.reply == "听你的，我们继续把这件事往前推。"


def test_thinking_voice_reply_does_not_claim_asr_failure():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider

    def misleading_reply(messages):
        return {
            "reply": "声音糊糊的，豆豆没接准。",
            "mood": "concerned",
            "face_type": "concerned",
            "animation": "tilt",
            "voice_style": "soft",
            "vibration": "none",
            "state_delta": {},
            "state_affect": {
                "interaction_tone": "comforting",
                "pet_effort": "none",
                "emotional_effect": "uncertain",
                "reason": "test",
            },
            "memory_update": {"should_save": False, "content": ""},
        }

    provider.complete_json = misleading_reply

    response = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_thinking",
            "payload": {"user_text": "继续下一句", "thinking_mode": True},
        }
    )

    assert "没接准" not in response.reply
    assert "声音糊" not in response.reply
    assert response.reply == "收到，关于“继续下一句”，豆豆继续陪你聊。"
    assert response.action in ALLOWED_BEHAVIOR_ACTIONS


def test_thinking_voice_reply_dedupes_repeated_reply():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider

    def repeated_reply(messages):
        return {
            "reply": "豆豆把小爪子放在桌边陪你。",
            "mood": "thinking",
            "face_type": "thinking",
            "animation": "blink",
            "voice_style": "soft",
            "vibration": "none",
            "state_delta": {},
            "state_affect": {
                "interaction_tone": "neutral",
                "pet_effort": "none",
                "emotional_effect": "uncertain",
                "reason": "test",
            },
            "memory_update": {"should_save": False, "content": ""},
            "behavior_plan": [
                {"action": "think", "slot": "before_speech", "duration_ms": 900},
                {"action": "speak", "slot": "speech", "duration_ms": 1400},
            ],
        }

    provider.complete_json = repeated_reply

    first = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_thinking",
            "payload": {"user_text": "第一轮", "thinking_mode": True},
        }
    )
    second = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_thinking",
            "payload": {"user_text": "第二轮", "thinking_mode": True},
        }
    )

    assert first.reply == "豆豆把小爪子放在桌边陪你。"
    assert second.reply == "收到，关于“第二轮”，豆豆继续陪你聊。"
    assert second.action in ALLOWED_BEHAVIOR_ACTIONS


def test_thinking_response_has_route():
    """Thinking mode PetResponse includes route='thinking'."""
    app = create_app(testing=True)
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "你好", "thinking_mode": True},
        }
    )
    assert response.route == "thinking"


def test_fast_reply_skips_state_delta():
    """Fast reply does not apply state_delta from LLM."""
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    original = provider.complete_json

    def patched(messages):
        result = original(messages)
        # LLM tries to output state_delta (should be ignored in fast reply)
        result["state_delta"] = {"energy": -100, "intimacy": 100}
        return result

    provider.complete_json = patched

    state_before = app.state.dispatcher.state_store.get_state()
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "你好"},
        }
    )
    # Energy should not have changed by -100
    assert response.pet_state["energy"] >= state_before.get("energy", 0) - 10


def test_fast_reply_prompt_excludes_forbidden_fields():
    """Fast reply prompt payload should not contain forbidden fields."""
    from app.config import load_settings
    from app.pet.prompt_builder import build_fast_reply_messages
    from app.runtime.context import build_runtime_context
    from app.runtime.events import normalize_event
    import json

    settings = load_settings()
    event = normalize_event({
        "type": "text_message", "source": "text",
        "payload": {"user_text": "你好"},
    })
    context = build_runtime_context(
        event,
        {"mood": "happy", "energy": 70, "intimacy": 10, "sleepiness": 20},
        cognition_context={
            "context_profile": "fast_reply",
            "recent_exact_events": [{"user": "你好", "pet": "早呀"}],
            "memory_cards": {"user_preferences": ["喜欢咖啡"], "momo_memories": []},
        },
    )

    messages = build_fast_reply_messages(settings, event, context)
    user_payload = json.loads(messages[1]["content"])

    # Must have these
    assert "user_input" in user_payload
    assert "pet_state" in user_payload
    assert "response_schema" in user_payload

    # Must NOT have these
    forbidden = [
        "current_time", "device_state", "skill_results",
        "temporal_recall_events", "episode_summaries", "daily_digest",
        "relevant_memories", "important_quotes",
        "state_delta", "state_affect", "memory_update",
        "behavior_plan", "output_schema",
    ]
    for field in forbidden:
        assert field not in user_payload, f"Forbidden field '{field}' found in fast reply payload"


def test_fast_reply_prompt_uses_selected_card_items():
    """Fast reply prompt uses selected_card_items when available."""
    from app.config import load_settings
    from app.pet.prompt_builder import build_fast_reply_messages
    from app.runtime.context import build_runtime_context
    from app.runtime.events import normalize_event
    import json

    settings = load_settings()
    event = normalize_event({
        "type": "text_message", "source": "text",
        "payload": {"user_text": "你好"},
    })
    context = build_runtime_context(
        event,
        {"mood": "happy", "energy": 70, "intimacy": 10, "sleepiness": 20},
        cognition_context={
            "context_profile": "fast_reply",
            "recent_exact_events": [],
            "memory_cards": {"user_preferences": ["旧数据"], "momo_memories": []},
            "selected_card_items": ["我是小明", "今天去了公园"],
        },
    )

    messages = build_fast_reply_messages(settings, event, context)
    user_payload = json.loads(messages[1]["content"])
    hints = user_payload.get("memory_hints", [])
    assert "我是小明" in hints
    assert "今天去了公园" in hints
    # Should NOT fall back to old memory_cards
    assert "旧数据" not in hints


def test_fast_reply_prompt_does_not_fallback_to_legacy_memory_cards():
    """V1.3 fast reply must not use legacy memory_cards projection."""
    from app.config import load_settings
    from app.pet.prompt_builder import build_fast_reply_messages
    from app.runtime.context import build_runtime_context
    from app.runtime.events import normalize_event
    import json

    settings = load_settings()
    event = normalize_event({
        "type": "text_message", "source": "text",
        "payload": {"user_text": "你好"},
    })
    context = build_runtime_context(
        event,
        {"mood": "happy", "energy": 70, "intimacy": 10, "sleepiness": 20},
        cognition_context={
            "context_profile": "fast_reply",
            "recent_exact_events": [],
            "memory_cards": {"user_preferences": ["旧数据"], "momo_memories": ["旧记忆"]},
        },
    )

    messages = build_fast_reply_messages(settings, event, context)
    user_payload = json.loads(messages[1]["content"])
    assert user_payload.get("memory_hints") == []


def test_fast_reply_prompt_caps_selected_memory_hints_to_10():
    """V1.4 fast reply loads at most 10 canonical notebook lines."""
    from app.config import load_settings
    from app.pet.prompt_builder import build_fast_reply_messages
    from app.runtime.context import build_runtime_context
    from app.runtime.events import normalize_event
    import json

    settings = load_settings()
    event = normalize_event({
        "type": "text_message", "source": "text",
        "payload": {"user_text": "你好"},
    })
    context = build_runtime_context(
        event,
        {"mood": "happy", "energy": 70, "intimacy": 10, "sleepiness": 20},
        cognition_context={
            "context_profile": "fast_reply",
            "recent_exact_events": [],
            "selected_card_items": [f"记忆{i}" for i in range(12)],
        },
    )

    messages = build_fast_reply_messages(settings, event, context)
    user_payload = json.loads(messages[1]["content"])

    assert user_payload["memory_hints"] == [f"记忆{i}" for i in range(10)]


def test_fast_reply_response_has_memory_ack_hint():
    """Fast reply PetResponse includes memory_ack_hint when explicit trigger detected."""
    app = create_app(testing=True)
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "记住我喜欢咖啡"},
        }
    )
    assert response.route == "fast_reply"
    assert response.memory_ack_hint == "我先记到小本本"


def test_fast_reply_no_memory_ack_without_trigger():
    """Fast reply without trigger has no memory_ack_hint."""
    app = create_app(testing=True)
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "你好"},
        }
    )
    assert response.memory_ack_hint is None


def test_fast_reply_enqueues_memory_summary_without_calling_provider():
    """After-turn memory summary is queued, not executed on the response path."""
    app = create_app(testing=True)
    queue = app.state.memory_judgment_queue
    provider = queue._provider
    calls = {"count": 0}

    def complete_json(messages):
        calls["count"] += 1
        return {"add": [{"category": "preference", "content": "喜欢短回复"}], "update": [], "delete": []}

    provider.complete_json = complete_json

    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "我喜欢短回复"},
        }
    )

    assert response.route == "fast_reply"
    assert calls["count"] == 0
    assert queue.pending_count() == 1


def test_maintenance_processes_memory_summary_into_notebook():
    app = create_app(testing=True)
    queue = app.state.memory_judgment_queue
    provider = queue._provider

    def complete_json(messages):
        return {"add": [{"category": "preference", "content": "偏好安静回应"}], "update": [], "delete": []}

    provider.complete_json = complete_json

    app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "今天先轻声聊一会"},
        }
    )
    result = app.state.maintenance_service.tick(force=True)

    assert result.get("memory_summary_adds") == 1
    assert "偏好安静回应" in app.state.notebook_manager.read_raw("memory.md")
