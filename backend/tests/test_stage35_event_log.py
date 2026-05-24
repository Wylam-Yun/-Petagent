import json

from app.pet.state import PetStateStore
from app.runtime.context_store import EventLogStore, desensitize_text


def test_event_log_records_all_fields():
    state_store = PetStateStore(None)
    log = EventLogStore(state_store.connection)

    log.record(
        event_id="evt-test1",
        episode_id="ep-test1",
        event_type="voice_message",
        source="voice_fast",
        user_text="你好豆豆",
        pet_reply="你好呀！",
        skill_results=[{"skill_id": "weather.current", "result": {}}],
        state_before={"mood": "idle", "energy": 72},
        state_after={"mood": "happy", "energy": 70},
        mood_after="happy",
    )

    events = log.recent_events(episode_id="ep-test1", limit=10)
    assert len(events) == 1
    evt = events[0]
    assert evt["event_id"] == "evt-test1"
    assert evt["episode_id"] == "ep-test1"
    assert evt["event_type"] == "voice_message"
    assert evt["user_text"] == "你好豆豆"
    assert evt["pet_reply"] == "你好呀！"
    assert evt["mood_after"] == "happy"


def test_event_log_capacity_cleanup_summarized_first():
    state_store = PetStateStore(None)
    log = EventLogStore(state_store.connection)

    # Insert 5 events, mark 3 as summarized
    for i in range(5):
        log.record(
            event_id=f"evt-cap-{i}",
            episode_id="ep-cap",
            event_type="voice_message",
            source="voice_fast",
            user_text=f"message {i}",
            pet_reply=f"reply {i}",
        )

    # Mark first 3 as summarized
    with state_store.connection.locked():
        state_store.connection.execute(
            """
            UPDATE raw_event_log
            SET summary_status = 'summarized'
            WHERE event_id IN ('evt-cap-0', 'evt-cap-1', 'evt-cap-2')
            """
        )
        state_store.connection.commit()

    assert log.count() == 5
    deleted = log.cleanup_if_needed(max_rows=3, current_episode_id="ep-cap")
    assert deleted == 2
    assert log.count() == 3


def test_event_log_hard_limit_cleanup():
    state_store = PetStateStore(None)
    log = EventLogStore(state_store.connection)

    # Insert events in different episodes
    for i in range(6):
        log.record(
            event_id=f"evt-hard-{i}",
            episode_id=f"ep-old-{i}" if i < 3 else "ep-current",
            event_type="voice_message",
            source="voice_fast",
            user_text=f"message {i}",
            pet_reply=f"reply {i}",
            importance_hint=0,
        )

    assert log.count() == 6
    # Set max to 4, current episode is ep-current
    deleted = log.cleanup_if_needed(max_rows=4, current_episode_id="ep-current")
    assert deleted >= 1
    assert log.count() <= 4


def test_debug_desensitizes_secrets():
    # sk- pattern
    result = desensitize_text("my key is sk-abc123def456ghi789 and more")
    assert "sk-abc123def456ghi789" not in result
    assert "[REDACTED]" in result

    # KEY= pattern
    result = desensitize_text("ASR_API_KEY=supersecretvalue12345678")
    assert "supersecretvalue12345678" not in result
    assert "[REDACTED]" in result

    # ghp_ pattern
    result = desensitize_text("token is ghp_abcdefghij1234567890 ok")
    assert "ghp_abcdefghij1234567890" not in result
    assert "[REDACTED]" in result

    # Truncation (use text that won't match base64 pattern)
    long_text = "今天天气真好，" * 50  # 300 chars of Chinese text
    result = desensitize_text(long_text, max_length=200)
    assert len(result) <= 210  # 200 + "..."
    assert result.endswith("...")


def test_event_log_indexes_exist():
    state_store = PetStateStore(None)
    log = EventLogStore(state_store.connection)

    with state_store.connection.locked():
        rows = state_store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_raw_event%'"
        ).fetchall()
    names = {r["name"] for r in rows}
    assert "idx_raw_event_episode_created" in names
    assert "idx_raw_event_created_status" in names
