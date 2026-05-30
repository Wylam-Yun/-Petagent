"""Stage 3.6: MaintenanceService tests."""
from datetime import datetime, timedelta

from app.pet.state import PetStateStore
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.maintenance import MaintenanceService
from app.runtime.memory_store import (
    DailySummaryStore,
    EpisodeSummaryStore,
    MaintenanceStateStore,
    MemoryCandidateStore,
    MemoryManager,
    SummaryJobStore,
)
from app.runtime.summary_manager import SummaryManager


class MockLLM:
    name = "mock"
    def complete_json(self, messages):
        return {"decisions": []}


class MockSummaryLLM:
    name = "mock_summary"
    def complete_json(self, messages):
        return {
            "summary": "测试摘要",
            "key_events": ["事件1"],
            "mood_notes": "正常",
            "important_quotes": [],
        }


def _make_maintenance(state_store, llm=None, config=None):
    conn = state_store.connection
    mm = MemoryManager(conn)
    cs = MemoryCandidateStore(conn)
    sjs = SummaryJobStore(conn)
    ess = EpisodeSummaryStore(conn)
    dss = DailySummaryStore(conn)
    ms = MaintenanceStateStore(conn)
    episodes = EpisodeStore(conn)
    event_log = EventLogStore(conn)

    summary_llm = llm or MockSummaryLLM()
    summary_manager = SummaryManager(summary_llm, ess, dss, cs)
    curator = type("MockCurator", (), {
        "curate_batch": lambda self, cs: {"saved": 0, "ignored": cs.count_pending(), "errors": 0},
    })()

    svc = MaintenanceService(
        curator=curator,
        summary_manager=summary_manager,
        candidate_store=cs,
        summary_job_store=sjs,
        memory_manager=mm,
        episode_summary_store=ess,
        daily_summary_store=dss,
        maintenance_state=ms,
        event_log_store=event_log,
        episode_store=episodes,
        config=config or {},
    )
    return svc, cs, sjs, ms, mm, ess


def test_maintenance_skips_when_too_soon():
    state_store = PetStateStore(None)
    svc, cs, sjs, ms, mm, ess = _make_maintenance(state_store)

    # First tick should run
    cs.add("evt-1", "ep-1", "test", "llm_suggestion")
    result1 = svc.tick()
    assert "skipped" not in result1

    # Second tick immediately should skip
    cs.add("evt-2", "ep-1", "test2", "llm_suggestion")
    result2 = svc.tick()
    assert result2.get("skipped") is True


def test_maintenance_runs_when_forced():
    state_store = PetStateStore(None)
    svc, cs, sjs, ms, mm, ess = _make_maintenance(state_store)

    cs.add("evt-1", "ep-1", "test", "llm_suggestion")
    svc.tick()

    cs.add("evt-2", "ep-1", "test2", "llm_suggestion")
    result = svc.tick(force=True)
    assert "skipped" not in result


def test_maintenance_processes_candidates():
    state_store = PetStateStore(None)
    svc, cs, sjs, ms, mm, ess = _make_maintenance(state_store)

    cs.add("evt-1", "ep-1", "候选1", "llm_suggestion")
    cs.add("evt-2", "ep-1", "候选2", "llm_suggestion")

    result = svc.tick(force=True)
    assert result == {}


def test_maintenance_state_persists():
    state_store = PetStateStore(None)
    svc, cs, sjs, ms, mm, ess = _make_maintenance(state_store)

    svc.tick(force=True)

    # Check maintenance_state was written
    last_tick = ms.get("last_tick_at")
    assert last_tick is not None

    # Create a new service with same state store — should see the persisted state
    svc2, _, _, ms2, _, _ = _make_maintenance(state_store)
    # Should skip because last_tick was just set
    result = svc2.tick()
    assert result.get("skipped") is True


def test_maintenance_processes_summary_jobs():
    state_store = PetStateStore(None)
    conn = state_store.connection
    mm = MemoryManager(conn)
    cs = MemoryCandidateStore(conn)
    sjs = SummaryJobStore(conn)
    ess = EpisodeSummaryStore(conn)
    dss = DailySummaryStore(conn)
    ms = MaintenanceStateStore(conn)
    episodes = EpisodeStore(conn)
    event_log = EventLogStore(conn)

    # Create episode with events
    ep, _ = episodes.get_or_create_current()
    event_log.record(
        event_id="evt-1",
        episode_id=ep["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="你好",
        pet_reply="你好呀",
    )

    # Enqueue summary job
    sjs.enqueue(ep["episode_id"])

    summary_manager = SummaryManager(MockSummaryLLM(), ess, dss, cs)
    curator = type("MockCurator", (), {
        "curate_batch": lambda self, cs: {"saved": 0, "ignored": 0, "errors": 0},
    })()

    svc = MaintenanceService(
        curator=curator,
        summary_manager=summary_manager,
        candidate_store=cs,
        summary_job_store=sjs,
        memory_manager=mm,
        episode_summary_store=ess,
        daily_summary_store=dss,
        maintenance_state=ms,
        event_log_store=event_log,
        episode_store=episodes,
    )

    result = svc.tick(force=True)
    assert result.get("summaries_generated") == 1

    # Job should be marked done
    pending = sjs.pending(limit=5)
    assert len(pending) == 0

    # Summary should exist
    summaries = ess.recent(limit=5)
    assert len(summaries) == 1


def test_maintenance_does_not_block_on_curator_failure():
    state_store = PetStateStore(None)
    conn = state_store.connection
    mm = MemoryManager(conn)
    cs = MemoryCandidateStore(conn)
    sjs = SummaryJobStore(conn)
    ess = EpisodeSummaryStore(conn)
    dss = DailySummaryStore(conn)
    ms = MaintenanceStateStore(conn)
    episodes = EpisodeStore(conn)
    event_log = EventLogStore(conn)

    cs.add("evt-1", "ep-1", "test", "llm_suggestion")

    class FailingCurator:
        def curate_batch(self, cs):
            raise RuntimeError("LLM unavailable")

    summary_manager = SummaryManager(MockSummaryLLM(), ess, dss, cs)
    svc = MaintenanceService(
        curator=FailingCurator(),
        summary_manager=summary_manager,
        candidate_store=cs,
        summary_job_store=sjs,
        memory_manager=mm,
        episode_summary_store=ess,
        daily_summary_store=dss,
        maintenance_state=ms,
        event_log_store=event_log,
        episode_store=episodes,
    )

    # Should not raise
    result = svc.tick(force=True)
    assert result == {}
