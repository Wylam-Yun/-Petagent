"""Stage 3.6: Memory candidate store tests."""
from app.pet.state import PetStateStore
from app.runtime.memory_store import MemoryCandidateStore


def test_candidate_added_from_llm_suggestion():
    state_store = PetStateStore(None)
    cs = MemoryCandidateStore(state_store.connection)

    cid = cs.add(
        source_event_id="evt-1",
        episode_id="ep-1",
        candidate_text="用户喜欢短回复",
        trigger_reason="llm_suggestion",
    )
    assert cid > 0
    assert cs.count_pending() == 1


def test_candidate_added_from_explicit_command():
    state_store = PetStateStore(None)
    cs = MemoryCandidateStore(state_store.connection)

    cid = cs.add(
        source_event_id="evt-2",
        episode_id="ep-1",
        candidate_text="记住我喜欢短回复",
        trigger_reason="explicit_command",
    )
    assert cid > 0
    pending = cs.pending()
    assert len(pending) == 1
    assert pending[0]["trigger_reason"] == "explicit_command"


def test_candidate_from_episode_end():
    state_store = PetStateStore(None)
    cs = MemoryCandidateStore(state_store.connection)

    cid = cs.add(
        source_event_id="episode_summary:ep-1",
        episode_id="ep-1",
        candidate_text="用户说他很累 (表达疲劳状态)",
        trigger_reason="episode_end",
    )
    assert cid > 0


def test_candidate_pending_and_mark_processed():
    state_store = PetStateStore(None)
    cs = MemoryCandidateStore(state_store.connection)

    cs.add("evt-1", "ep-1", "candidate 1", "llm_suggestion")
    cs.add("evt-2", "ep-1", "candidate 2", "llm_suggestion")
    cs.add("evt-3", "ep-1", "candidate 3", "llm_suggestion")

    assert cs.count_pending() == 3
    pending = cs.pending(limit=2)
    assert len(pending) == 2

    cs.mark_processed(pending[0]["id"], "saved")
    cs.mark_processed(pending[1]["id"], "ignored")

    assert cs.count_pending() == 1


def test_candidate_invalid_trigger_reason():
    state_store = PetStateStore(None)
    cs = MemoryCandidateStore(state_store.connection)

    try:
        cs.add("evt-1", "ep-1", "test", "invalid_reason")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_candidate_clear_all():
    state_store = PetStateStore(None)
    cs = MemoryCandidateStore(state_store.connection)

    cs.add("evt-1", "ep-1", "candidate 1", "llm_suggestion")
    cs.add("evt-2", "ep-1", "candidate 2", "explicit_command")
    assert cs.count_pending() == 2

    cs.clear_all()
    assert cs.count_pending() == 0
