from fastapi.testclient import TestClient

from app.main import create_app


def post_voice(client: TestClient, *, data=None, content_type="audio/wav"):
    return client.post(
        "/api/voice/chat",
        data=data or {},
        files={"file": ("voice.wav", b"RIFF mock wav bytes", content_type)},
    )


def test_voice_chat_uses_fast_route_by_default():
    client = TestClient(create_app(testing=True))

    response = post_voice(client)

    assert response.status_code == 200
    body = response.json()
    assert body["voice_route"]["requested"] == "auto"
    assert body["voice_route"]["selected"] == "fast"
    assert body["voice_route"]["thinking_mode"] is False
    assert body["voice_route"]["asr_provider"] == "mock_asr"
    assert body["voice_route"]["brain_provider"] == "mock_fast_llm"
    assert body["user_text"] == "我回来啦"


def test_voice_chat_uses_slow_route_when_thinking_mode_is_enabled():
    client = TestClient(create_app(testing=True))

    response = post_voice(client, data={"thinking_mode": "true"})

    assert response.status_code == 200
    body = response.json()
    assert body["voice_route"]["selected"] == "slow"
    assert body["voice_route"]["thinking_mode"] is True
    assert body["voice_route"]["brain_provider"] == "mock_slow_llm"
    assert body["audio_understanding"]["tone_notes"]


def test_voice_chat_falls_back_to_slow_route_when_asr_is_empty():
    app = create_app(testing=True)
    app.state.asr_provider.text = ""
    client = TestClient(app)

    response = post_voice(client)

    assert response.status_code == 200
    body = response.json()
    assert body["voice_route"]["selected"] == "slow"
    assert body["voice_route"]["fallback_reason"] == "asr_empty"
    assert body["reply"]


def test_voice_chat_uses_configured_upload_limits():
    app = create_app(testing=True)
    app.state.settings.voice_routing["allowed_audio_types"] = ["audio/wav"]
    app.state.settings.voice_routing["max_audio_bytes"] = 4
    client = TestClient(app)

    unsupported = post_voice(client, content_type="audio/webm")
    too_large = post_voice(client, content_type="audio/wav")

    assert unsupported.status_code == 400
    assert too_large.status_code == 413
