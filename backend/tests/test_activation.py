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


def test_activation_normalizes_common_momo_asr_aliases():
    client = TestClient(create_app(testing=True))

    wake = client.post(
        "/api/activation/wake",
        json={"phrase": "嗨 默默", "confidence": 0.86, "source": "foreground_voice"},
    )
    exit_response = client.post(
        "/api/activation/exit",
        json={"phrase": "摸摸休息吧", "confidence": 0.86, "source": "foreground_voice"},
    )

    assert wake.status_code == 200
    assert wake.json()["active"] is True
    assert exit_response.status_code == 200
    assert exit_response.json()["active"] is False


def test_activation_session_is_persisted_and_closed():
    app = create_app(testing=True)
    client = TestClient(app)
    wake = client.post(
        "/api/activation/wake",
        json={"phrase": "hi momo", "confidence": 0.86, "source": "foreground_voice"},
    )
    session_id = wake.json()["session_id"]

    client.post(
        "/api/activation/exit",
        json={"phrase": "momo休息吧", "confidence": 0.86, "source": "foreground_voice"},
    )

    row = app.state.state_store.connection.execute(
        """
        SELECT active, started_at, ended_at
        FROM activation_session
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    assert row is not None
    assert row["active"] == 0
    assert row["started_at"]
    assert row["ended_at"]
