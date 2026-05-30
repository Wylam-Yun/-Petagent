from fastapi.testclient import TestClient

from app.main import create_app


def _auth_headers(app):
    return {"Authorization": f"Bearer {app.state.internal_token}"}


def test_context_refresh_endpoint():
    app = create_app(testing=True)
    client = TestClient(app)

    response = client.post("/api/context/refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "episode" in body
    assert body["episode"]["status"] == "open"
    assert body["reply"]  # has a reply string


def test_context_refresh_creates_new_episode():
    app = create_app(testing=True)
    client = TestClient(app)

    # First refresh
    r1 = client.post("/api/context/refresh")
    ep1 = r1.json()["episode"]["episode_id"]

    # Second refresh
    r2 = client.post("/api/context/refresh")
    ep2 = r2.json()["episode"]["episode_id"]

    assert ep1 != ep2


def test_context_refresh_logs_event():
    app = create_app(testing=True)
    client = TestClient(app)

    client.post("/api/context/refresh")

    # Check that context_refresh event was logged
    log = app.state.event_log_store
    events = log.recent_events(limit=5)
    types = [e["event_type"] for e in events]
    assert "context_refresh" in types


def test_context_debug_endpoint_requires_debug_enabled():
    app = create_app(testing=True)
    client = TestClient(app)

    assert client.get("/api/context/debug").status_code == 403
    response = client.get("/api/context/debug", headers=_auth_headers(app))
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["debug_enabled"] is False
    # Should not have detailed events when debug is disabled
    assert "recent_events" not in body


def test_context_debug_endpoint_returns_detail_when_enabled():
    app = create_app(testing=True)
    # Override debug_enabled
    app.state.settings.app_config.setdefault("cognition_context", {})["debug_enabled"] = True
    client = TestClient(app)

    response = client.get("/api/context/debug", headers=_auth_headers(app))
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["debug_enabled"] is True
    assert "recent_events" in body
    assert "context_config" in body


def test_voice_exit_phrase_pre_detection_updates_activation():
    """VoicePipeline should classify exit phrases and update ActivationManager."""
    app = create_app(testing=True)
    app.state.asr_provider.text = "momo休息吧"

    client = TestClient(app)

    response = client.post(
        "/api/voice/chat",
        files={"file": ("voice.wav", b"RIFF\x00\x00\x00\x00WAVE", "audio/wav")},
    )
    assert response.status_code == 200

    # Activation session should be ended
    activation = app.state.activation_manager
    assert activation.state.active is False


def test_context_debug_desensitizes_user_text():
    app = create_app(testing=True)
    app.state.settings.app_config.setdefault("cognition_context", {})["debug_enabled"] = True

    # First dispatch an event with a secret-like text
    app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice_fast",
            "payload": {"user_text": "我的 API key 是 sk-abc123def456ghi789jkl012"},
        }
    )

    client = TestClient(app)
    response = client.get("/api/context/debug", headers=_auth_headers(app))
    body = response.json()

    if "recent_events" in body:
        for evt in body["recent_events"]:
            assert "sk-abc123def456ghi789jkl012" not in evt.get("user_text", "")
