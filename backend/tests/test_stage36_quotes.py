"""Stage 3.6: Important quotes pipeline tests."""
from app.pet.state import PetStateStore
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.memory_store import (
    EpisodeSummaryStore,
    MemoryCandidateStore,
    MemoryManager,
)
from app.runtime.summary_manager import SummaryManager


class MockQuoteLLM:
    """LLM that returns quotes with varying importance."""
    name = "mock_quotes"

    def __init__(self, quotes=None):
        self._quotes = quotes or [
            {"quote": "明天有面试", "meaning": "用户提到重要事件", "importance": 4},
            {"quote": "今天好累", "meaning": "用户表达疲劳", "importance": 3},
            {"quote": "我喝了水", "meaning": "日常琐事", "importance": 1},
        ]

    def complete_json(self, messages):
        return {
            "summary": "用户聊了近况",
            "key_events": ["面试", "疲劳"],
            "mood_notes": "有点紧张",
            "important_quotes": self._quotes,
        }


def test_high_importance_quotes_become_candidates():
    state_store = PetStateStore(None)
    conn = state_store.connection
    episodes = EpisodeStore(conn)
    event_log = EventLogStore(conn)
    ess = EpisodeSummaryStore(conn)
    cs = MemoryCandidateStore(conn)

    ep, _ = episodes.get_or_create_current()
    event_log.record(
        event_id="evt-1",
        episode_id=ep["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="明天有面试，今天好累",
        pet_reply="加油！",
    )

    from app.runtime.memory_store import DailySummaryStore
    dss = DailySummaryStore(conn)

    sm = SummaryManager(MockQuoteLLM(), ess, dss, cs)
    sm.generate_episode_summary(
        episode_id=ep["episode_id"],
        event_log_store=event_log,
        episode_store=episodes,
    )

    # Quotes with importance >= 3 should be candidates
    pending = cs.pending(limit=10)
    episode_candidates = [c for c in pending if c["trigger_reason"] == "episode_end"]
    assert len(episode_candidates) >= 2  # importance 4 and 3

    # importance=1 quote should NOT be a candidate
    texts = [c["candidate_text"] for c in episode_candidates]
    assert not any("喝了水" in t for t in texts)


def test_quote_candidate_text_includes_meaning():
    state_store = PetStateStore(None)
    conn = state_store.connection
    episodes = EpisodeStore(conn)
    event_log = EventLogStore(conn)
    ess = EpisodeSummaryStore(conn)
    cs = MemoryCandidateStore(conn)

    ep, _ = episodes.get_or_create_current()
    event_log.record(
        event_id="evt-1",
        episode_id=ep["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="明天有面试",
        pet_reply="加油",
    )

    from app.runtime.memory_store import DailySummaryStore
    dss = DailySummaryStore(conn)

    sm = SummaryManager(MockQuoteLLM(), ess, dss, cs)
    sm.generate_episode_summary(
        episode_id=ep["episode_id"],
        event_log_store=event_log,
        episode_store=episodes,
    )

    pending = cs.pending(limit=10)
    episode_candidates = [c for c in pending if c["trigger_reason"] == "episode_end"]
    # At least one candidate should have the meaning appended
    assert any("(" in c["candidate_text"] for c in episode_candidates)


def test_quote_importance_threshold():
    """Only importance >= 3 should create candidates."""
    state_store = PetStateStore(None)
    conn = state_store.connection
    episodes = EpisodeStore(conn)
    event_log = EventLogStore(conn)
    ess = EpisodeSummaryStore(conn)
    cs = MemoryCandidateStore(conn)

    ep, _ = episodes.get_or_create_current()
    event_log.record(
        event_id="evt-1",
        episode_id=ep["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="普通对话",
        pet_reply="嗯",
    )

    from app.runtime.memory_store import DailySummaryStore
    dss = DailySummaryStore(conn)

    # All quotes have importance < 3
    llm = MockQuoteLLM(quotes=[
        {"quote": "今天天气不错", "meaning": "闲聊", "importance": 2},
        {"quote": "我吃了饭", "meaning": "日常", "importance": 1},
    ])
    sm = SummaryManager(llm, ess, dss, cs)
    sm.generate_episode_summary(
        episode_id=ep["episode_id"],
        event_log_store=event_log,
        episode_store=episodes,
    )

    # No candidates should be created
    episode_candidates = [
        c for c in cs.pending(limit=10)
        if c["trigger_reason"] == "episode_end"
    ]
    assert len(episode_candidates) == 0


def test_quotes_go_through_candidate_not_direct_memory():
    """Important quotes should enter memory_candidate, not memory directly."""
    state_store = PetStateStore(None)
    conn = state_store.connection
    episodes = EpisodeStore(conn)
    event_log = EventLogStore(conn)
    ess = EpisodeSummaryStore(conn)
    cs = MemoryCandidateStore(conn)
    mm = MemoryManager(conn)

    ep, _ = episodes.get_or_create_current()
    event_log.record(
        event_id="evt-1",
        episode_id=ep["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="明天有面试",
        pet_reply="加油",
    )

    from app.runtime.memory_store import DailySummaryStore
    dss = DailySummaryStore(conn)

    sm = SummaryManager(MockQuoteLLM(), ess, dss, cs)
    sm.generate_episode_summary(
        episode_id=ep["episode_id"],
        event_log_store=event_log,
        episode_store=episodes,
    )

    # Candidates should exist
    assert cs.count_pending() >= 1

    # But memory table should NOT have these quotes directly
    # (they need curator approval first)
    memories = mm.scored_memories(limit=10)
    # All memories should be from prior explicit saves, not from quotes
    # Since we didn't save anything to memory, count should be 0
    assert mm.count() == 0


def test_quotes_with_missing_fields_handled():
    """Quotes with missing fields should not crash."""
    state_store = PetStateStore(None)
    conn = state_store.connection
    episodes = EpisodeStore(conn)
    event_log = EventLogStore(conn)
    ess = EpisodeSummaryStore(conn)
    cs = MemoryCandidateStore(conn)

    ep, _ = episodes.get_or_create_current()
    event_log.record(
        event_id="evt-1",
        episode_id=ep["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="test",
        pet_reply="test",
    )

    from app.runtime.memory_store import DailySummaryStore
    dss = DailySummaryStore(conn)

    # Quote missing "quote" field
    llm = MockQuoteLLM(quotes=[
        {"meaning": "只有meaning", "importance": 4},
        {"quote": "", "meaning": "空quote", "importance": 4},
        {"quote": "有效引用", "importance": 5},
    ])
    sm = SummaryManager(llm, ess, dss, cs)
    result = sm.generate_episode_summary(
        episode_id=ep["episode_id"],
        event_log_store=event_log,
        episode_store=episodes,
    )

    assert result is not None
    # Should have created at least one candidate for the valid quote
    pending = cs.pending(limit=10)
    episode_candidates = [c for c in pending if c["trigger_reason"] == "episode_end"]
    assert len(episode_candidates) >= 1
