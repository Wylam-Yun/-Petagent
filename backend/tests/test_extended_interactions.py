from fastapi.testclient import TestClient

from app.main import create_app
from app.pet.guard import guard_action
from app.runtime.events import normalize_event


def test_new_interaction_events_are_supported():
    for event_type in [
        "stay_with_me",
        "pet_pat",
        "praise_momo",
        "feed_momo",
        "comfort_me",
        "encourage_me",
        "listen_to_me",
        "tuck_in",
        "clean_face",
        "quiet_company",
        "take_a_break",
    ]:
        event = normalize_event({"event": event_type, "payload": {"description": event_type}})
        assert event.type == event_type


def test_guard_uses_feed_limit_for_hunger():
    action = guard_action(
        {
            "reply": "开饭啦。",
            "mood": "happy",
            "state_delta": {"hunger": -99},
        },
        event_type="feed_momo",
    )

    assert action.state_delta["hunger"] == -12


def test_guard_uses_clean_face_limit_for_cleanliness():
    action = guard_action(
        {
            "reply": "脸脸干净啦。",
            "mood": "shy",
            "state_delta": {"cleanliness": 99},
        },
        event_type="clean_face",
    )

    assert action.state_delta["cleanliness"] == 12


def test_extended_button_event_returns_contextual_response():
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/pet/event",
        json={
            "event": "praise_momo",
            "payload": {
                "description": "用户夸夸豆豆",
                "interaction_group": "pet_care",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"]
    assert "state_affect" in body
    assert body["runtime"]["episode_id"]
