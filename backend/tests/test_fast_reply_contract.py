"""Tests for the V1.5 unified foreground reply contract."""

from __future__ import annotations

import pytest

from app.main import create_app
from app.pet.guard import InvalidActionError, guard_fast_reply_action
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


def test_fast_reply_guard_raises_on_empty():
    with pytest.raises(InvalidActionError):
        guard_fast_reply_action({})


def test_fast_reply_guard_invalid_mood():
    result = guard_fast_reply_action({"reply": "早", "mood": "furious"})
    assert result.mood == "idle"
    assert result.expression_key == "idle_soft"


def test_fast_reply_guard_invalid_action():
    """Invalid action is cleared."""
    result = guard_fast_reply_action({"reply": "早", "action": "dancing"})
    assert result.action is None


def test_fast_reply_guard_prompt_leak():
    """Lines containing internal field names are stripped."""
    raw = {
        "reply": "早呀\nstate_delta: {energy: 5}\n豆豆在这儿。",
    }
    result = guard_fast_reply_action(raw)
    assert "state_delta" not in result.reply
    assert "我在这儿" in result.reply


def test_fast_reply_guard_strips_structured_reasoning():
    raw = {
        "reply": "分析：这是早安问候，回复要短。\n最终回复：早呀主人，豆豆醒啦～",
        "mood": "happy",
        "action": "greet",
    }

    result = guard_fast_reply_action(raw)

    assert "分析" not in result.reply
    assert "早安问候" not in result.reply
    assert result.reply == "早呀主人，我醒啦～"


def test_fast_reply_guard_raises_on_reasoning_only():
    with pytest.raises(InvalidActionError):
        guard_fast_reply_action({"reply": "<think>只输出了内部推理"})


def test_fast_reply_guard_replaces_legacy_pet_name():
    result = guard_fast_reply_action({"reply": "早呀，Momo 刚醒。momo 在听。"})

    assert "Momo" not in result.reply
    assert "momo" not in result.reply
    assert result.reply == "早呀，我 刚醒。我 在听。"


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
    assert response.route == "unified"
    assert response.action == "waving"
    assert response.expression_key == "happy"
    assert response.state_affect is None
    assert response.behavior_intent is None
    assert response.behavior_plan is None


def test_thinking_response_has_route():
    """Thinking mode is accepted but ignored."""
    app = create_app(testing=True)
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "你好", "thinking_mode": True},
        }
    )
    assert response.route == "unified"
    assert response.runtime["context_profile"] == "unified"


def test_fast_reply_tts_debug_uses_sanitized_reply_only():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider

    provider.complete_json = lambda messages: {
        "reply": "豆豆来回答。",
        "mood": "happy",
        "expression_key": "happy",
        "action": "speak",
    }
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "你好"},
        }
    )

    assert response.reply == "我来回答。"
    assert response.expression_key == "happy"
    assert app.state.dispatcher.last_submitted_tts_text == response.reply
    assert app.state.dispatcher.last_submitted_tts_event_id == response.runtime["event_id"]
    assert app.state.dispatcher.last_submitted_tts_at


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
    memories = user_payload.get("long_term_memory", [])
    assert "我是小明" in memories
    assert "今天去了公园" in memories
    # Should NOT fall back to old memory_cards
    assert "旧数据" not in memories


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
    assert user_payload.get("long_term_memory") == []


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

    assert user_payload["long_term_memory"] == [f"记忆{i}" for i in range(10)]


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
    assert response.route == "unified"
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
        return {"memories": [{"category": "preference", "content": "喜欢短回复"}]}

    provider.complete_json = complete_json

    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "我喜欢短回复"},
        }
    )

    assert response.route == "unified"
    assert calls["count"] == 0
    assert queue.pending_count() == 1


def test_maintenance_processes_memory_summary_into_notebook():
    app = create_app(testing=True)
    queue = app.state.memory_judgment_queue
    provider = queue._provider

    def complete_json(messages):
        return {"memories": [{"category": "preference", "content": "偏好安静回应"}]}

    provider.complete_json = complete_json

    app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "记住今天先轻声聊一会"},
        }
    )
    result = app.state.maintenance_service.tick(force=True)

    assert result.get("memory_summary_rewrite") == 1
    assert "偏好安静回应" in app.state.notebook_manager.read_raw("memory.md")
