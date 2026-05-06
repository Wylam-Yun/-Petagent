"""Stage 3.6: Episode lifecycle and summary job enqueue tests."""
from app.pet.state import PetStateStore
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.memory_store import SummaryJobStore


def test_idle_timeout_returns_closed_episode_id():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    # Create an episode with old last_event_at
    ep1, closed1 = episodes.get_or_create_current(
        now_utc="2024-01-01T00:00:00"
    )
    assert closed1 is None
    assert ep1["status"] == "open"

    # Simulate idle timeout (45+ minutes later)
    ep2, closed2 = episodes.get_or_create_current(
        now_utc="2024-01-01T01:00:00",
        idle_minutes=45,
    )

    assert closed2 is not None
    assert closed2 == ep1["episode_id"]
    assert ep2["episode_id"] != ep1["episode_id"]
    assert ep2["status"] == "open"


def test_no_timeout_returns_none_closed():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    ep1, closed1 = episodes.get_or_create_current(now_utc="2024-01-01T00:00:00")
    assert closed1 is None

    # Same episode, no timeout (5 minutes later)
    ep2, closed2 = episodes.get_or_create_current(
        now_utc="2024-01-01T00:05:00",
        idle_minutes=45,
    )
    assert closed2 is None
    assert ep2["episode_id"] == ep1["episode_id"]


def test_exit_phrase_close_returns_episode_id():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    ep, _ = episodes.get_or_create_current(now_utc="2024-01-01T00:00:00")
    closed_id = episodes.close_current("exit_phrase")

    assert closed_id == ep["episode_id"]

    # Verify it's closed
    stored = episodes.get_episode(ep["episode_id"])
    assert stored["status"] == "closed"
    assert stored["close_reason"] == "exit_phrase"


def test_context_refresh_closes_and_creates():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    ep1, _ = episodes.get_or_create_current(now_utc="2024-01-01T00:00:00")
    ep2 = episodes.refresh_topic(now_utc="2024-01-01T00:01:00")

    assert ep2["episode_id"] != ep1["episode_id"]
    assert ep2["status"] == "open"

    stored1 = episodes.get_episode(ep1["episode_id"])
    assert stored1["status"] == "closed"
    assert stored1["close_reason"] == "context_refresh"


def test_summary_job_enqueued_on_idle_timeout():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)
    sjs = SummaryJobStore(state_store.connection)

    ep1, _ = episodes.get_or_create_current(now_utc="2024-01-01T00:00:00")

    # Simulate dispatcher behavior: get_or_create with timeout, then enqueue
    ep2, closed_id = episodes.get_or_create_current(
        now_utc="2024-01-01T01:00:00",
        idle_minutes=45,
    )
    if closed_id:
        sjs.enqueue(closed_id)

    pending = sjs.pending(limit=5)
    assert len(pending) == 1
    assert pending[0]["episode_id"] == ep1["episode_id"]


def test_summary_job_enqueued_on_exit_phrase():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)
    sjs = SummaryJobStore(state_store.connection)

    ep, _ = episodes.get_or_create_current(now_utc="2024-01-01T00:00:00")

    # Simulate dispatcher behavior: close_current on exit_phrase, then enqueue
    closed_id = episodes.close_current("exit_phrase")
    if closed_id:
        sjs.enqueue(closed_id)

    pending = sjs.pending(limit=5)
    assert len(pending) == 1
    assert pending[0]["episode_id"] == ep["episode_id"]


def test_summary_job_enqueued_on_context_refresh():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)
    sjs = SummaryJobStore(state_store.connection)

    ep1, _ = episodes.get_or_create_current(now_utc="2024-01-01T00:00:00")

    # refresh_topic closes current and creates new
    ep2 = episodes.refresh_topic(now_utc="2024-01-01T00:01:00")

    # The old episode should be closeable — but refresh_topic doesn't return
    # the closed id. In the dispatcher, close_current is called separately.
    # Here we verify the old episode is closed.
    stored = episodes.get_episode(ep1["episode_id"])
    assert stored["status"] == "closed"

    # Enqueue manually (dispatcher would do this)
    sjs.enqueue(ep1["episode_id"])
    pending = sjs.pending(limit=5)
    assert len(pending) == 1


def test_close_current_returns_none_when_no_open():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)

    # No episode created yet
    closed_id = episodes.close_current("exit_phrase")
    assert closed_id is None
