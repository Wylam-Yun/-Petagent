from datetime import datetime, timedelta

from app.pet.state import PetStateStore
from app.runtime.context_store import EpisodeStore


def _now():
    return datetime.utcnow().isoformat()


def test_consecutive_voice_events_same_episode():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    ep1 = episodes.get_or_create_current()
    episodes.update_event_count(ep1["episode_id"])
    episodes.update_event_count(ep1["episode_id"])

    ep2 = episodes.get_or_create_current()
    assert ep2["episode_id"] == ep1["episode_id"]
    assert ep2["event_count"] == 2


def test_45min_idle_creates_new_episode():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    old_time = (datetime.utcnow() - timedelta(minutes=50)).isoformat()
    ep1 = episodes.get_or_create_current(now_utc=old_time)

    now = datetime.utcnow().isoformat()
    ep2 = episodes.get_or_create_current(now_utc=now, idle_minutes=45)

    assert ep2["episode_id"] != ep1["episode_id"]
    assert ep2["status"] == "open"

    # Old episode should be closed
    old = episodes.get_episode(ep1["episode_id"])
    assert old["status"] == "closed"
    assert old["close_reason"] == "idle_timeout"


def test_context_refresh_closes_and_creates_episode():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    ep1 = episodes.get_or_create_current()
    new_ep = episodes.refresh_topic()

    assert new_ep["episode_id"] != ep1["episode_id"]
    assert new_ep["status"] == "open"

    old = episodes.get_episode(ep1["episode_id"])
    assert old["status"] == "closed"
    assert old["close_reason"] == "context_refresh"


def test_exit_phrase_closes_episode():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    ep1 = episodes.get_or_create_current()
    episodes.update_event_count(ep1["episode_id"])
    closed_id = episodes.close_current("exit_phrase")

    assert closed_id == ep1["episode_id"]
    closed = episodes.get_episode(ep1["episode_id"])
    assert closed["status"] == "closed"
    assert closed["close_reason"] == "exit_phrase"


def test_close_current_when_no_open_episode():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    result = episodes.close_current("exit_phrase")
    assert result is None


def test_episode_indexes_exist():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    with state_store.connection.locked():
        rows = state_store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_episode_status_last_event'"
        ).fetchall()
    assert len(rows) == 1
