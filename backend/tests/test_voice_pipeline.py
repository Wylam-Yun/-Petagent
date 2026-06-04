from fastapi.testclient import TestClient

from app.main import create_app
from app.runtime.voice_types import ASRTranscript


def post_voice(client: TestClient, *, data=None, content_type="audio/wav"):
    return client.post(
        "/api/voice/chat",
        data=data or {},
        files={"file": ("voice.wav", b"RIFF\x00\x00\x00\x00WAVE", content_type)},
    )


def test_voice_chat_uses_unified_route_by_default():
    client = TestClient(create_app(testing=True))

    response = post_voice(client)

    assert response.status_code == 200
    body = response.json()
    assert body["voice_route"]["requested"] == "auto"
    assert body["voice_route"]["selected"] == "unified"
    assert body["voice_route"]["thinking_mode"] is False
    assert body["voice_route"]["asr_provider"] == "mock_asr"
    assert body["voice_route"]["brain_provider"] == "mock_fast_llm"
    assert body["user_text"] == "我回来啦"


def test_voice_chat_ignores_thinking_mode():
    client = TestClient(create_app(testing=True))

    response = post_voice(client, data={"thinking_mode": "true"})

    assert response.status_code == 200
    body = response.json()
    assert body["voice_route"]["selected"] == "unified"
    assert body["voice_route"]["thinking_mode"] is False
    assert body["voice_route"]["brain_provider"] == "mock_fast_llm"


def test_thinking_mode_still_uses_asr_route():
    app = create_app(testing=True)
    client = TestClient(app)

    response = post_voice(client, data={"thinking_mode": "true"})

    assert response.status_code == 200
    body = response.json()
    assert body["voice_route"]["selected"] == "unified"
    assert body["voice_route"]["asr_provider"] == "mock_asr"
    assert body["voice_route"]["emotion_source"] == "asr"
    assert body["user_text"] == "我回来啦"


def test_thinking_mode_stays_on_unified_asr_chain():
    app = create_app(testing=True)
    client = TestClient(app)

    response = post_voice(client, data={"thinking_mode": "true"})

    assert response.status_code == 200
    body = response.json()
    assert body["voice_route"]["selected"] == "unified"
    assert not hasattr(app.state.voice_pipeline, "audio_provider")
    assert body["voice_route"]["asr_provider"] == "mock_asr"
    assert body["reply"]


def test_fast_voice_asr_failure_returns_structured_failure():
    app = create_app(testing=True)
    app.state.asr_provider.text = ""
    client = TestClient(app)

    response = post_voice(client)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error_class"] == "asr_empty"
    assert body["voice_route"]["selected"] == "unified"
    assert body["voice_route"]["fallback_reason"] == "asr_empty"
    assert body["voice_route"]["asr_error_code"] == "asr_empty"
    assert body["reply"] == ""
    assert body["audio_job_id"] is None
    assert body["voice_url"] is None


def test_fast_voice_asr_error_returns_structured_failure():
    class FailingASR:
        name = "future_asr"

        def transcribe(self, audio_path, content_type):
            return ASRTranscript(
                text="",
                confidence=0.0,
                provider=self.name,
                error_code="asr_http_401",
                error_message="ASR HTTP request failed with status 401",
            )

    app = create_app(testing=True)
    app.state.voice_pipeline.asr_provider = FailingASR()
    client = TestClient(app)

    response = post_voice(client)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error_class"] == "asr_http_401"
    assert body["reply"] == ""
    route = body["voice_route"]
    assert route["selected"] == "unified"
    assert route["fallback_reason"] == "asr_provider_error"
    assert route["asr_error_code"] == "asr_http_401"


def test_thinking_voice_stops_when_asr_empty():
    app = create_app(testing=True)
    app.state.asr_provider.text = ""
    client = TestClient(app)

    response = post_voice(client, data={"thinking_mode": "true"})

    assert response.status_code == 200
    body = response.json()
    assert body["voice_route"]["selected"] == "unified"
    assert body["ok"] is False
    assert body["reply"] == ""


def test_voice_pipeline_gates_asr_but_not_audio_understanding():
    app = create_app(testing=True)
    gate = app.state.provider_gate
    seen = []
    original_acquire = gate.acquire

    def track(provider_type):
        seen.append(provider_type)
        original_acquire(provider_type)

    gate.acquire = track
    client = TestClient(app)

    fast = post_voice(client)
    slow = post_voice(client, data={"thinking_mode": "true"})

    assert fast.status_code == 200
    assert slow.status_code == 200
    assert "asr" in seen
    assert "audio_understanding" not in seen


def test_voice_chat_uses_configured_upload_limits():
    app = create_app(testing=True)
    app.state.settings.voice_routing["allowed_audio_types"] = ["audio/wav"]
    app.state.settings.voice_routing["max_audio_bytes"] = 4
    client = TestClient(app)

    unsupported = post_voice(client, content_type="audio/webm")
    too_large = post_voice(client, content_type="audio/wav")

    assert unsupported.status_code == 400
    assert too_large.status_code == 413
