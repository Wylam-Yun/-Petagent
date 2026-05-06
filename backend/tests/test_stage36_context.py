"""Stage 3.6: ContextManager scored memory tests."""
import json
from datetime import datetime

from app.pet.state import PetStateStore
from app.runtime.context_manager import ContextManager
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.events import PetEvent
from app.runtime.memory_store import EpisodeSummaryStore, MemoryManager


def test_context_manager_uses_scored_memories():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)

    # Add some memories
    mm.save_curated("user_preference", "用户喜欢短回复", importance=4)
    mm.save_curated("relationship", "用户希望被叫 William", importance=5)
    mm.save_curated("recent_mood", "用户最近有点累", importance=3)

    ep, _ = episodes.get_or_create_current()
    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "你好"})

    cm = ContextManager({"relevant_memory_items": 4})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
    )

    assert len(context["relevant_memories"]) > 0
    # Should contain scored memories with type info
    for mem in context["relevant_memories"]:
        assert "type" in mem
        assert "content" in mem


def test_episode_summaries_in_context():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    ess = EpisodeSummaryStore(state_store.connection)

    ep, _ = episodes.get_or_create_current()

    # Save a summary
    ess.save(
        episode_id="ep-old",
        summary="之前聊了天气",
        key_events=["天气查询"],
        mood_notes="开心",
        important_quotes=[],
        started_at_utc="2024-01-01T00:00:00",
        ended_at_utc="2024-01-01T00:30:00",
    )

    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "你好"})
    cm = ContextManager({"recent_episode_summaries": 2})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
        episode_summary_store=ess,
    )

    assert len(context["episode_summaries"]) == 1
    assert context["episode_summaries"][0]["summary"] == "之前聊了天气"


def test_important_quotes_in_context():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)

    mm.save_curated("important_quote", "用户说明天有面试", importance=4)
    mm.save_curated("important_quote", "用户喜欢猫", importance=3)

    ep, _ = episodes.get_or_create_current()
    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "你好"})

    cm = ContextManager({"relevant_memory_items": 4})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
    )

    assert len(context["important_quotes"]) >= 1


def test_budget_trimming_with_new_fields():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    ess = EpisodeSummaryStore(state_store.connection)

    # Add many memories to exceed budget
    for i in range(10):
        mm.save_curated("user_preference", "记忆内容%d" % i, importance=3)

    ess.save("ep-old", "摘要", ["事件"], "情绪", [], "2024-01-01", "2024-01-01")

    ep, _ = episodes.get_or_create_current()
    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "测试"})

    cm = ContextManager({"max_context_chars": 500, "relevant_memory_items": 4})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
        episode_summary_store=ess,
    )

    serialized = json.dumps(context, ensure_ascii=False)
    # Should be within budget (with some slack for metadata)
    assert len(serialized) <= 1000
    assert context["context_budget"]["used_chars"] > 0


def test_stable_memories_not_dominated_by_recency():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)

    # Old stable memory should still rank high
    mm.save_curated("relationship", "用户叫 William", importance=5)
    # Recent but low-priority memory
    mm.save_curated("recent_mood", "用户今天喝了咖啡", importance=2)

    ep, _ = episodes.get_or_create_current()
    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "你好"})

    cm = ContextManager({"relevant_memory_items": 2})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
    )

    contents = [m["content"] for m in context["relevant_memories"]]
    # Relationship should be included despite being older
    assert "用户叫 William" in contents
