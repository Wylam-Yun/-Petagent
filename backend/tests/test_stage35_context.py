import json
from datetime import datetime, timedelta

from app.pet.state import PetStateStore
from app.runtime.context import RuntimeContext, build_runtime_context
from app.runtime.context_manager import ContextManager
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.events import PetEvent


def test_context_manager_respects_budget():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)

    episode, _ = episodes.get_or_create_current()
    cm = ContextManager({"max_context_chars": 500, "recent_exact_turns": 6})

    # Add many events to exceed budget
    for i in range(10):
        event_log.record(
            event_id=f"evt-budget-{i}",
            episode_id=episode["episode_id"],
            event_type="voice_message",
            source="voice_fast",
            user_text=f"这是一条比较长的用户消息，用来测试上下文预算裁剪功能 {i}",
            pet_reply=f"这是 Momo 的回复，也稍微长一点来帮助测试 {i}",
        )

    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "测试"})
    pet_state = state_store.get_state()

    context = cm.build(
        event=event,
        pet_state=pet_state,
        episode=episode,
        event_log_store=event_log,
    )

    serialized = json.dumps(context, ensure_ascii=False)
    # Budget metadata itself is ~300+ chars, so allow some slack
    assert len(serialized) <= 800
    assert context["context_budget"]["max_chars"] == 500
    assert context["context_budget"]["used_chars"] > 0
    # Events should be trimmed - not all 10 should remain
    assert len(context["recent_exact_events"]) < 10


def test_prompt_serializer_excludes_old_fields():
    from app.pet.prompt_builder import serialize_for_prompt

    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "你好"})
    pet_state = {"mood": "idle", "energy": 72}
    cognition = {
        "current_time": {"utc": "2024-01-01", "local": "2024-01-01"},
        "current_episode": {"episode_id": "ep-1"},
        "recent_exact_events": [],
        "relevant_memories": ["用户喜欢短回复"],
    }

    payload = serialize_for_prompt(
        event=event,
        pet_state=pet_state,
        cognition_context=cognition,
    )

    # Should have cognition_context
    assert "cognition_context" in payload
    assert payload["cognition_context"]["relevant_memories"] == ["用户喜欢短回复"]

    # Should NOT have old fields
    assert "recent_memory" not in payload
    assert "recent_dialogue" not in payload
    assert "runtime_context" not in payload


def test_prompt_serializer_used_by_skill_planner():
    from app.pet.prompt_builder import build_skill_plan_messages
    from app.config import load_settings

    settings = load_settings()
    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "今天天气怎么样"})
    context = RuntimeContext(
        event=event.dict(),
        pet_state={"mood": "idle"},
        recent_memory=["旧记忆不应出现"],
        recent_dialogue=[{"user": "旧对话", "pet": "旧回复"}],
        cognition_context={"current_episode": {"episode_id": "ep-1"}},
    )

    messages = build_skill_plan_messages(settings, event, context)
    user_msg = json.loads(messages[1]["content"])

    # Should use cognition_context, not old fields
    assert "cognition_context" in user_msg
    assert "recent_memory" not in user_msg
    assert "recent_dialogue" not in user_msg
    assert "runtime_context" not in user_msg


def test_both_paths_use_same_context():
    from app.pet.prompt_builder import build_pet_messages, build_skill_plan_messages
    from app.config import load_settings

    settings = load_settings()
    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "你好"})
    context = RuntimeContext(
        event=event.dict(),
        pet_state={"mood": "idle"},
        cognition_context={"current_episode": {"episode_id": "ep-1"}},
    )

    pet_messages = build_pet_messages(settings, event, context)
    skill_messages = build_skill_plan_messages(settings, event, context)

    pet_payload = json.loads(pet_messages[1]["content"])
    skill_payload = json.loads(skill_messages[1]["content"])

    # Both should use the same cognition_context structure
    assert "cognition_context" in pet_payload
    assert "cognition_context" in skill_payload
    assert pet_payload["cognition_context"] == skill_payload["cognition_context"]


def test_episode_rollover_on_idle():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)

    cm = ContextManager({"idle_episode_minutes": 45})

    # Create episode at old time
    old_time = (datetime.utcnow() - timedelta(minutes=50)).isoformat()
    ep1, _ = episodes.get_or_create_current(now_utc=old_time)
    event_log.record(
        event_id="evt-old",
        episode_id=ep1["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="旧消息",
        pet_reply="旧回复",
    )

    # Now trigger rollover
    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "新消息"})
    ep2, _ = episodes.get_or_create_current()
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep2,
        event_log_store=event_log,
    )

    # New episode should have no events from old episode
    assert context["current_episode"]["episode_id"] != ep1["episode_id"]
    assert len(context["recent_exact_events"]) == 0


def test_runtime_context_has_cognition_field():
    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "你好"})
    context = build_runtime_context(
        event,
        pet_state={"mood": "idle"},
        cognition_context={"current_episode": {"episode_id": "ep-1"}},
    )
    assert context.schema_version == "0.2"
    assert context.cognition_context == {"current_episode": {"episode_id": "ep-1"}}

    # Without cognition_context, should default to empty dict
    context2 = build_runtime_context(event, pet_state={"mood": "idle"})
    assert context2.cognition_context == {}
