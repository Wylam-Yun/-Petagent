from app.runtime.context_store import EventLogStore
from app.pet.state import PetStateStore


def _record(store, event_id, episode_id, event_type, user_text, pet_reply, source="test"):
    store.record(
        event_id=event_id,
        episode_id=episode_id,
        event_type=event_type,
        source=source,
        user_text=user_text,
        pet_reply=pet_reply,
    )


def test_recent_dialogue_crosses_episodes_and_filters_non_dialogue(tmp_path):
    state = PetStateStore(tmp_path / "state.db")
    store = EventLogStore(state.connection)
    _record(store, "p1", "ep-a", "proactive", "", "早呀")
    _record(store, "b1", "ep-a", "feed_momo", "", "好吃")
    _record(store, "t1", "ep-a", "text_message", "一", "答一")
    _record(store, "v1", "ep-a", "voice_message", "二", "答二")
    _record(store, "w1", "ep-b", "wake_phrase", "豆豆", "在")
    _record(store, "t2", "ep-b", "text_message", "三", "答三")
    _record(store, "v2", "ep-b", "voice_message", "", "")
    _record(store, "t3", "ep-c", "text_message", "四", "答四")
    _record(store, "t4", "ep-c", "text_message", "五", "答五")
    _record(store, "t5", "ep-c", "text_message", "六", "答六")

    rows = store.recent_dialogue_turns(limit=5)
    assert [row["user"] for row in rows] == ["二", "三", "四", "五", "六"]
    assert [row["pet"] for row in rows] == ["答二", "答三", "答四", "答五", "答六"]


def test_context_refresh_does_not_record_history_or_close_episode():
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)
    before_episode = app.state.episode_manager.get_or_create_current()[0]["episode_id"]

    response = client.post("/api/context/refresh")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    after_episode = app.state.episode_manager.peek_current()["episode_id"]
    assert after_episode == before_episode
    assert app.state.event_log_store.count() == 0
