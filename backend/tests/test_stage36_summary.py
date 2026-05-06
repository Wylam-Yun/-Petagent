"""Stage 3.6: SummaryManager tests."""
from app.pet.state import PetStateStore
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.memory_store import (
    DailySummaryStore,
    EpisodeSummaryStore,
    MemoryCandidateStore,
)
from app.runtime.summary_manager import SummaryManager


class MockSummaryLLM:
    name = "mock_summary"

    def __init__(self, result=None):
        self._result = result or {
            "summary": "用户和 Momo 聊了天气和心情",
            "key_events": ["聊了天气", "用户说有点累"],
            "mood_notes": "用户有点疲惫",
            "important_quotes": [
                {
                    "quote": "今天好累啊",
                    "meaning": "用户表达疲劳",
                    "importance": 3,
                }
            ],
        }

    def complete_json(self, messages):
        return self._result


def test_episode_summary_generated():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    ess = EpisodeSummaryStore(state_store.connection)
    dss = DailySummaryStore(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    ep, _ = episodes.get_or_create_current()
    event_log.record(
        event_id="evt-1",
        episode_id=ep["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="今天好累啊",
        pet_reply="辛苦啦，Momo 陪你",
        mood_after="concerned",
    )
    episodes.update_event_count(ep["episode_id"])

    sm = SummaryManager(MockSummaryLLM(), ess, dss, cs)
    result = sm.generate_episode_summary(
        episode_id=ep["episode_id"],
        event_log_store=event_log,
        episode_store=episodes,
    )

    assert result is not None
    assert result["episode_id"] == ep["episode_id"]
    assert "天气" in result["summary"] or "Momo" in result["summary"]

    # Episode summary should be saved
    summaries = ess.recent(limit=5)
    assert len(summaries) == 1
    assert summaries[0]["episode_id"] == ep["episode_id"]


def test_episode_summary_creates_quote_candidates():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    ess = EpisodeSummaryStore(state_store.connection)
    dss = DailySummaryStore(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    ep, _ = episodes.get_or_create_current()
    event_log.record(
        event_id="evt-1",
        episode_id=ep["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="今天好累啊",
        pet_reply="辛苦啦",
    )

    sm = SummaryManager(MockSummaryLLM(), ess, dss, cs)
    sm.generate_episode_summary(
        episode_id=ep["episode_id"],
        event_log_store=event_log,
        episode_store=episodes,
    )

    # Quote with importance >= 3 should be enqueued as candidate
    pending = cs.pending(limit=5)
    assert len(pending) >= 1
    assert any(c["trigger_reason"] == "episode_end" for c in pending)


def test_episode_summary_skips_low_importance_quotes():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    ess = EpisodeSummaryStore(state_store.connection)
    dss = DailySummaryStore(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    ep, _ = episodes.get_or_create_current()
    event_log.record(
        event_id="evt-1",
        episode_id=ep["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="我喝了水",
        pet_reply="好的",
    )

    llm = MockSummaryLLM({
        "summary": "用户喝了水",
        "key_events": ["喝水"],
        "mood_notes": "正常",
        "important_quotes": [
            {"quote": "我喝了水", "meaning": "日常琐事", "importance": 1}
        ],
    })
    sm = SummaryManager(llm, ess, dss, cs)
    sm.generate_episode_summary(
        episode_id=ep["episode_id"],
        event_log_store=event_log,
        episode_store=episodes,
    )

    # importance < 3 should NOT create candidate
    assert cs.count_pending() == 0


def test_cleanup_expired():
    state_store = PetStateStore(None)
    ess = EpisodeSummaryStore(state_store.connection)
    dss = DailySummaryStore(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    sm = SummaryManager(MockSummaryLLM(), ess, dss, cs)
    result = sm.cleanup_expired()
    assert "episode_summaries" in result
    assert "daily_summaries" in result


def test_summary_failure_does_not_block():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    ess = EpisodeSummaryStore(state_store.connection)
    dss = DailySummaryStore(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    ep, _ = episodes.get_or_create_current()
    event_log.record(
        event_id="evt-1",
        episode_id=ep["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="test",
        pet_reply="test",
    )

    class FailingLLM:
        name = "failing"
        def complete_json(self, messages):
            raise RuntimeError("LLM error")

    sm = SummaryManager(FailingLLM(), ess, dss, cs)
    result = sm.generate_episode_summary(
        episode_id=ep["episode_id"],
        event_log_store=event_log,
        episode_store=episodes,
    )

    # Should return None on failure, not raise
    assert result is None
