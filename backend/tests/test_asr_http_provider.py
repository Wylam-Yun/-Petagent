from pathlib import Path

from app.config import ProviderConfig
from app.providers.asr_http import HttpASRProvider, parse_transcript_json


def provider_config() -> ProviderConfig:
    return ProviderConfig(
        name="nvidia_http_asr",
        model="parakeet-ctc-0.6b-zh-cn",
        base_url="https://asr.example",
        api_key_env="NVIDIA_API_KEY",
        timeout_seconds=15,
        api_key="test-key",
        extra={
            "endpoint": "/v1/audio/transcriptions",
            "language_code": "zh-CN",
            "auth_scheme": "bearer",
            "proxy_url": "http://127.0.0.1:7897",
        },
    )


def test_parse_transcript_json_accepts_common_shapes():
    assert parse_transcript_json({"text": "你好 Momo"}) == ("你好 Momo", 1.0)
    assert parse_transcript_json({"transcript": "你好默默", "confidence": 0.72}) == (
        "你好默默",
        0.72,
    )
    assert parse_transcript_json(
        {"results": [{"alternatives": [{"transcript": "我回来啦", "confidence": 0.8}]}]}
    ) == ("我回来啦", 0.8)


def test_http_asr_posts_multipart_audio_and_uses_proxy(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "你好 Momo", "confidence": 0.81}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("app.providers.asr_http.requests.post", fake_post)

    transcript = HttpASRProvider(provider_config()).transcribe(audio, "audio/wav")

    assert captured["url"] == "https://asr.example/v1/audio/transcriptions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["data"]["language"] == "zh-CN"
    assert captured["data"]["model"] == "parakeet-ctc-0.6b-zh-cn"
    assert captured["proxies"] == {
        "http": "http://127.0.0.1:7897",
        "https": "http://127.0.0.1:7897",
    }
    assert transcript.text == "你好 Momo"
    assert transcript.confidence == 0.81
    assert transcript.provider == "nvidia_http_asr"


def test_http_asr_returns_empty_transcript_when_not_configured(tmp_path: Path):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    config = provider_config()
    config.base_url = None

    transcript = HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert transcript.text == ""
    assert transcript.confidence == 0.0
