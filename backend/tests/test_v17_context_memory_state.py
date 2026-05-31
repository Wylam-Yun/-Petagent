from __future__ import annotations

import json

from app.config import load_settings
from app.main import create_app
from app.pet.guard import guard_fast_reply_action
from app.pet.prompt_builder import build_unified_foreground_messages
from app.runtime.context import build_runtime_context
from app.runtime.events import normalize_event


def _payload_for_state(pet_state):
    settings = load_settings()
    event = normalize_event({
        "type": "text_message",
        "source": "text",
        "payload": {"user_text": "今天星期几"},
    })
    context = build_runtime_context(
        event,
        pet_state,
        cognition_context={
            "context_profile": "unified",
            "current_time": {
                "utc": "2026-05-31T15:00:00",
                "local": "2026-05-31T23:00:00",
                "timezone": "Asia/Shanghai",
            },
            "recent_exact_events": [
                {"user": "你在干嘛", "pet": "我在玩", "created_at": "2026-05-31T10:00:00"}
            ],
            "selected_card_items": ["- [2026-05-31 10:00][preference] 用户喜欢咖啡。"],
        },
    )
    messages = build_unified_foreground_messages(settings, event, context)
    return messages, json.loads(messages[1]["content"])


def test_unified_prompt_uses_v17_payload_sections():
    messages, payload = _payload_for_state({
        "mood": "angry",
        "energy": 10,
        "intimacy": 80,
        "sleepiness": 86,
    })

    assert "current_user_message" in payload
    assert "current_time" in payload
    assert "recent_conversation_context" in payload
    assert "long_term_memory" in payload
    assert "pet_state" in payload
    assert "reply_contract" in payload
    assert "response_schema" in payload
    assert "user_input" not in payload
    assert "recent_dialogue" not in payload
    assert "sleepiness" not in payload["pet_state"]

    system = messages[0]["content"]
    assert "最近上下文" in system
    assert "长期记忆" in system
    assert "不是措辞模板" in system
    assert "只在相关时使用" in system
    assert "不要自称" in system
    assert "回复主语" in system or "台词主语" in system
    assert "必须先给出直接答案" in system
    assert "current_time 为准" in system
    assert "不能把 recent_conversation_context" in system
    assert "相似句式" in system
    assert "才主动提 long_term_memory" in system


def test_unified_pet_state_has_levels_and_no_sleepiness():
    _, payload = _payload_for_state({
        "mood": "angry",
        "energy": 10,
        "intimacy": 80,
        "sleepiness": 86,
    })

    assert payload["pet_state"] == {
        "mood": "angry",
        "energy": 10,
        "energy_level": "low",
        "intimacy": 80,
        "intimacy_level": "high",
    }


def test_unified_prompt_includes_current_local_time_for_time_questions():
    _, payload = _payload_for_state({"mood": "idle", "energy": 50, "intimacy": 50})

    assert payload["current_time"] == {
        "local": "2026-05-31T23:00:00",
        "local_date": "2026-05-31",
        "local_time": "23:00",
        "weekday": "星期日",
        "utc": "2026-05-31T15:00:00",
        "timezone": "Asia/Shanghai",
    }


def test_unified_schema_includes_only_energy_intimacy_state_delta():
    _, payload = _payload_for_state({"mood": "idle", "energy": 50, "intimacy": 50})
    state_delta = payload["response_schema"]["state_delta"]

    assert set(state_delta) == {"energy", "intimacy"}
    assert "sleepiness" not in json.dumps(payload["response_schema"], ensure_ascii=False)
    assert payload["reply_contract"]["must_answer_current_user_message_first"] is True
    assert payload["reply_contract"]["invalid_if_reply_uses_context_or_memory_as_refusal_reason"] is True
    assert payload["reply_contract"]["on_invalid_output_backend_fails_this_turn_without_fallback"] is True


def test_no_friendly_fallback_constants_remain():
    from app.pet import guard

    assert not hasattr(guard, "FALLBACK_ACTION")
    assert not hasattr(guard, "FAST_REPLY_FALLBACK")


def test_fast_reply_guard_accepts_only_energy_intimacy_state_delta():
    action = guard_fast_reply_action({
        "reply": "我在。",
        "mood": "happy",
        "state_delta": {
            "energy": -2,
            "intimacy": 1,
            "sleepiness": 99,
            "hunger": 99,
        },
    })

    assert action.state_delta == {"energy": -2, "intimacy": 1}


def test_fast_reply_guard_ignores_invalid_state_delta_values():
    action = guard_fast_reply_action({
        "reply": "我在。",
        "state_delta": {"energy": -100, "intimacy": True},
    })

    assert action.state_delta == {}


def test_unified_applies_energy_and_intimacy_state_delta():
    app = create_app(testing=True)
    app.state.state_store.save_state({
        **app.state.state_store.get_state(),
        "energy": 50,
        "intimacy": 40,
        "mood": "idle",
        "sleepiness": 15,
    })
    app.state.dispatcher.brain.provider.complete_json = lambda messages: {
        "reply": "我听到啦。",
        "mood": "happy",
        "expression_key": "happy",
        "action": "speak",
        "voice_style": "normal",
        "state_delta": {"energy": -2, "intimacy": 1, "sleepiness": 99},
    }

    response = app.state.dispatcher.handle_event({
        "type": "text_message",
        "source": "runtime",
        "payload": {"user_text": "你好"},
    }, synthesize_voice=False)

    assert response.pet_state["energy"] == 48
    assert response.pet_state["intimacy"] == 42  # text_message rule +1, LLM delta +1
    assert response.pet_state["sleepiness"] == 15
    runs = app.state.agent_run_store.recent(limit=1)
    assert runs[0]["final_action"]["state_delta"] == {"energy": -2, "intimacy": 1}


def test_successful_turn_counter_counts_only_v17_eligible_events():
    app = create_app(testing=True)
    app.state.dispatcher.brain.provider.complete_json = lambda messages: {
        "reply": "我在。",
        "mood": "happy",
        "expression_key": "happy",
        "action": "speak",
        "voice_style": "normal",
    }

    app.state.dispatcher.handle_event(
        {"type": "morning", "source": "proactive", "payload": {}},
        synthesize_voice=False,
    )
    assert app.state.successful_turn_store.snapshot()["successful_turn_count_total"] == 0

    app.state.dispatcher.handle_event({
        "type": "text_message",
        "source": "runtime",
        "payload": {"user_text": "你好"},
    }, synthesize_voice=False)
    assert app.state.successful_turn_store.snapshot()["successful_turn_count_total"] == 1


def test_unified_context_contract_violation_is_explicit_failure_without_history():
    app = create_app(testing=True)
    app.state.event_log_store.record(
        event_id="old-1",
        episode_id="ep-old",
        event_type="text_message",
        source="runtime",
        user_text="你在干嘛",
        pet_reply="我正忙着记你玩手机，小本本都快写满了。",
    )
    app.state.event_log_store.record(
        event_id="old-2",
        episode_id="ep-old",
        event_type="text_message",
        source="runtime",
        user_text="今天星期几",
        pet_reply="我忙着记你玩手机，哪有空管今天星期几。",
    )
    before_count = app.state.event_log_store.count()
    before_state = app.state.state_store.get_state()
    app.state.dispatcher.brain.provider.complete_json = lambda messages: {
        "reply": "哼，我正忙着记你玩手机的事呢，小本本都快写满了，哪有空管今天星期几。",
        "mood": "angry",
        "expression_key": "annoyed",
        "action": "pretend_busy",
        "voice_style": "normal",
        "state_delta": {"energy": -2, "intimacy": 1},
    }

    response = app.state.dispatcher.handle_event({
        "type": "text_message",
        "source": "runtime",
        "payload": {"user_text": "今天星期几"},
    }, synthesize_voice=False)

    assert response.reply == ""
    assert response.runtime["error_class"] == "llm_context_contract_violation"
    assert app.state.event_log_store.count() == before_count
    assert app.state.successful_turn_store.snapshot()["successful_turn_count_total"] == 0
    assert response.pet_state["energy"] == before_state["energy"]
    assert response.pet_state["intimacy"] == before_state["intimacy"]
    runs = app.state.agent_run_store.recent(limit=1)
    assert runs[0]["status"] == "failed"
    assert runs[0]["error"] == "llm_context_contract_violation"


def test_unified_context_contract_retry_can_recover_with_llm_answer():
    app = create_app(testing=True)
    app.state.event_log_store.record(
        event_id="old-1",
        episode_id="ep-old",
        event_type="text_message",
        source="runtime",
        user_text="你在干嘛",
        pet_reply="我正忙着记你玩手机，小本本都快写满了。",
    )
    app.state.event_log_store.record(
        event_id="old-2",
        episode_id="ep-old",
        event_type="text_message",
        source="runtime",
        user_text="今天星期几",
        pet_reply="我忙着记你玩手机，哪有空管今天星期几。",
    )
    calls = {"count": 0}

    def complete_json(messages):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "reply": "哼，我正忙着记你玩手机的事呢，小本本都快写满了，哪有空管今天星期几。",
                "mood": "angry",
                "expression_key": "annoyed",
                "action": "pretend_busy",
                "voice_style": "normal",
            }
        return {
            "reply": "今天是星期日。我有点别扭，但还是先告诉你。",
            "mood": "idle",
            "expression_key": "idle_soft",
            "action": "speak",
            "voice_style": "normal",
            "state_delta": {"energy": 0, "intimacy": 1},
        }

    app.state.dispatcher.brain.provider.complete_json = complete_json

    response = app.state.dispatcher.handle_event({
        "type": "text_message",
        "source": "runtime",
        "payload": {"user_text": "今天星期几"},
    }, synthesize_voice=False)

    assert calls["count"] == 2
    assert response.reply == "今天是星期日。我有点别扭，但还是先告诉你。"
    assert response.runtime["status"] == "completed"
    recent = app.state.event_log_store.recent_dialogue_turns(limit=1)
    assert recent[0]["pet"] == "今天是星期日。我有点别扭，但还是先告诉你。"
