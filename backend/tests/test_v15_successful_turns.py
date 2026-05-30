from app.pet.state import PetStateStore
from app.runtime.context_store import SuccessfulTurnStore


def test_successful_turn_counter_persists_and_triggers_every_ten(tmp_path):
    state = PetStateStore(tmp_path / "state.db")
    store = SuccessfulTurnStore(state.connection)
    triggered = []
    for idx in range(1, 21):
        result = store.record_successful_turn(f"event-{idx}", keyword_trigger=False)
        if result.should_enqueue_memory:
            triggered.append(idx)
    assert triggered == [10, 20]

    reloaded = SuccessfulTurnStore(state.connection)
    assert reloaded.snapshot()["successful_turn_count_total"] == 20
    assert reloaded.record_successful_turn("event-20", keyword_trigger=False).incremented is False


def test_keyword_trigger_enqueues_without_waiting_for_tenth_turn(tmp_path):
    state = PetStateStore(tmp_path / "state.db")
    store = SuccessfulTurnStore(state.connection)
    result = store.record_successful_turn("event-1", keyword_trigger=True)
    assert result.incremented is True
    assert result.should_enqueue_memory is True
