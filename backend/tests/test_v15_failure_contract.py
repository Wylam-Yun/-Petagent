from fastapi.testclient import TestClient

from app.main import create_app


class RaisingProvider:
    name = "raising_provider"

    def complete_json(self, messages):
        raise RuntimeError("provider down")


class InvalidJsonProvider:
    name = "invalid_json_provider"

    def complete_json(self, messages):
        return "{broken json"


class CapturingProvider:
    name = "capturing_provider"

    def __init__(self):
        self.messages = []

    def complete_json(self, messages):
        self.messages.append(messages)
        return {"reply": "收到啦", "mood": "happy", "action": "happy"}


def _client_with_provider(provider):
    app = create_app(testing=True)
    app.state.text_pipeline.fast_brain.provider = provider
    app.state.text_pipeline.slow_brain.provider = provider
    app.state.dispatcher.brain.provider = provider
    return TestClient(app)


def test_text_llm_provider_exception_is_explicit_failure_without_history():
    client = _client_with_provider(RaisingProvider())
    response = client.post("/api/text/chat", json={"text": "你好"})
    body = response.json()
    assert response.status_code == 200
    assert body["error_class"] in {"llm_provider_error", "llm_invalid_output", "provider_busy"}
    assert body["reply"] == ""
    assert client.app.state.event_log_store.count() == 0


def test_text_invalid_llm_output_is_not_friendly_fallback():
    client = _client_with_provider(InvalidJsonProvider())
    response = client.post("/api/text/chat", json={"text": "你好"})
    body = response.json()
    assert response.status_code == 200
    assert body["error_class"] == "llm_invalid_output"
    assert "豆豆在这儿" not in body.get("reply", "")
    assert client.app.state.event_log_store.count() == 0


def test_text_thinking_mode_is_accepted_but_ignored():
    provider = CapturingProvider()
    client = _client_with_provider(provider)
    response = client.post(
        "/api/text/chat",
        json={"text": "认真想一下", "thinking_mode": True},
    )
    body = response.json()
    assert body["error_class"] is None
    assert body["runtime"]["context_profile"] == "unified"
    assert body["text_route"]["thinking_mode"] is False


def test_voice_legacy_route_thinking_is_ignored_on_asr_failure(tmp_path):
    app = create_app(testing=True)

    class EmptyASR:
        name = "empty_asr"

        def transcribe(self, audio_path, content_type):
            from app.runtime.voice_types import ASRTranscript

            return ASRTranscript(
                text="",
                confidence=0.0,
                provider=self.name,
                error_code="asr_empty",
            )

    app.state.voice_pipeline.asr_provider = EmptyASR()
    client = TestClient(app)
    audio = b"RIFF\x24\x00\x00\x00WAVEfmt "
    response = client.post(
        "/api/voice/chat",
        files={"file": ("voice.wav", audio, "audio/wav")},
        data={"thinking_mode": "true", "route": "thinking"},
    )
    body = response.json()
    assert body["ok"] is False
    assert body["error_class"] == "asr_empty"
    assert body["voice_route"]["thinking_mode"] is False
    assert body["voice_route"]["selected"] == "unified"
