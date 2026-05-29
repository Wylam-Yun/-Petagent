from __future__ import annotations

import json

from app.config import load_settings
from app.main import create_app
from app.pet.prompt_builder import build_thinking_messages
from app.runtime.context import build_runtime_context
from app.runtime.events import normalize_event


def _thinking_context():
    event = normalize_event(
        {
            "type": "text_message",
            "source": "text",
            "payload": {"user_text": "认真帮我想想"},
        }
    )
    return build_runtime_context(
        event,
        {"mood": "thinking", "energy": 70, "intimacy": 10, "sleepiness": 20},
        device_state={"battery": 80},
        skill_results=[{"skill_id": "weather.current", "content": "晴"}],
        cognition_context={
            "context_profile": "thinking",
            "current_time": {"local": "2026-05-26T20:00:00"},
            "recent_exact_events": [{"user": "前一句", "pet": "回应"}],
            "temporal_recall_events": [{"user": "旧事"}],
            "episode_summaries": [{"summary": "摘要"}],
            "daily_digest": {"content": "日报"},
            "relevant_memories": [{"content": "数据库记忆"}],
            "important_quotes": [{"content": "重要引用"}],
            "memory_cards": {
                "user_preferences": ["旧卡片偏好"],
                "momo_memories": ["旧卡片记忆"],
            },
            "selected_card_items": [
                "用户喜欢短回复",
                "正在修 PetAgent V1.4",
            ],
        },
    )


def test_thinking_prompt_excludes_forbidden_fields():
    messages = build_thinking_messages(
        load_settings(),
        normalize_event(
            {
                "type": "text_message",
                "source": "text",
                "payload": {"user_text": "认真帮我想想"},
            }
        ),
        _thinking_context(),
    )
    payload = json.loads(messages[1]["content"])

    assert payload["user_input"] == "认真帮我想想"
    assert "notebook_user" not in payload
    assert payload["notebook_memory"] == ["用户喜欢短回复", "正在修 PetAgent V1.4"]
    assert payload["recent_dialogue"] == [{"user": "前一句", "pet": "回应"}]
    assert "memory_update" not in json.dumps(payload, ensure_ascii=False)

    forbidden = [
        "current_time",
        "device_state",
        "skill_results",
        "temporal_recall_events",
        "episode_summaries",
        "daily_digest",
        "relevant_memories",
        "important_quotes",
        "memory_cards",
        "output_schema",
    ]
    for field in forbidden:
        assert field not in payload


def test_brain_generate_thinking_uses_thinking_builder():
    app = create_app(testing=True)
    captured = {}
    provider = app.state.dispatcher.brain.provider

    def complete_json(messages):
        captured["messages"] = messages
        return {
            "reply": "豆豆认真想好了。",
            "mood": "thinking",
            "face_type": "thinking",
            "animation": "tilt",
            "voice_style": "soft",
            "vibration": "none",
            "state_delta": {},
            "state_affect": {
                "interaction_tone": "neutral",
                "pet_effort": "medium",
                "emotional_effect": "calm",
                "reason": "思考模式回复",
            },
            "behavior_intent": "neutral_companion",
            "behavior_plan": [],
        }

    provider.complete_json = complete_json
    app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "认真帮我想想", "thinking_mode": True},
        }
    )

    payload = json.loads(captured["messages"][1]["content"])
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "current_time" not in payload
    assert "device_state" not in payload
    assert "memory_cards" not in payload
    assert "memory_update" not in serialized
    assert "OUTPUT_SCHEMA_HINT" not in serialized


def test_thinking_prompt_caps_notebook_memory_to_20():
    event = normalize_event(
        {
            "type": "text_message",
            "source": "text",
            "payload": {"user_text": "认真帮我想想"},
        }
    )
    context = build_runtime_context(
        event,
        {"mood": "thinking", "energy": 70, "intimacy": 10, "sleepiness": 20},
        cognition_context={
            "context_profile": "thinking",
            "recent_exact_events": [],
            "selected_card_items": [f"记忆{i}" for i in range(25)],
        },
    )

    messages = build_thinking_messages(load_settings(), event, context)
    payload = json.loads(messages[1]["content"])

    assert payload["notebook_memory"] == [f"记忆{i}" for i in range(20)]


def test_thinking_voice_prompt_does_not_question_successful_asr():
    event = normalize_event(
        {
            "type": "voice_message",
            "source": "voice_thinking",
            "payload": {"user_text": "继续陪我聊中文", "thinking_mode": True},
        }
    )
    context = build_runtime_context(
        event,
        {"mood": "thinking", "energy": 70, "intimacy": 10, "sleepiness": 20},
        cognition_context={
            "context_profile": "thinking",
            "recent_exact_events": [],
            "selected_card_items": [],
        },
    )

    messages = build_thinking_messages(load_settings(), event, context)
    system_prompt = messages[0]["content"]

    assert "低置信" not in system_prompt
    assert "可能不完整" not in system_prompt
    assert "不要归因到语音识别质量" in system_prompt
