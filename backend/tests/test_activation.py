from fastapi.testclient import TestClient

from app.main import create_app


def test_activation_wake_creates_active_session():
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/activation/wake",
        json={"phrase": "hi momo", "confidence": 0.82, "source": "foreground_voice"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active"] is True
    assert body["session_id"]
    assert body["reply"]
    assert body["voice_url"] is not None


def test_activation_wake_rejects_low_confidence():
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/activation/wake",
        json={"phrase": "hi momo", "confidence": 0.2, "source": "foreground_voice"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active"] is False
    assert body["session_id"] is None


def test_activation_exit_ends_active_session():
    client = TestClient(create_app(testing=True))
    client.post(
        "/api/activation/wake",
        json={"phrase": "hi momo", "confidence": 0.82, "source": "foreground_voice"},
    )

    response = client.post(
        "/api/activation/exit",
        json={"phrase": "momo休息吧", "confidence": 0.86, "source": "foreground_voice"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["active"] is False
    assert body["reply"]
    assert body["voice_url"] is not None
