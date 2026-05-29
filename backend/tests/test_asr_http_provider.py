from pathlib import Path

import requests

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
    assert parse_transcript_json({"text": "你好豆豆"}) == ("你好豆豆", 1.0)
    assert parse_transcript_json({"transcript": "你好默默", "confidence": 0.72}) == (
        "你好默默",
        0.72,
    )
    assert parse_transcript_json(
        {"results": [{"alternatives": [{"transcript": "我回来啦", "confidence": 0.8}]}]}
    ) == ("我回来啦", 0.8)


def test_parse_transcript_json_uses_configured_paths_for_nested_provider():
    body = {
        "payload": {
            "speech": {
                "text": "豆豆我回来啦",
                "confidence_score": 0.64,
            }
        }
    }

    assert parse_transcript_json(
        body,
        text_paths=["payload.speech.text"],
        confidence_paths=["payload.speech.confidence_score"],
    ) == ("豆豆我回来啦", 0.64)


def test_http_asr_posts_multipart_audio_and_uses_proxy(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "你好豆豆", "confidence": 0.81}

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
    assert transcript.text == "你好豆豆"
    assert transcript.confidence == 0.81
    assert transcript.provider == "nvidia_http_asr"


def test_http_asr_can_send_binary_audio_with_custom_headers_and_response_paths(
    tmp_path: Path, monkeypatch
):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF custom wav")
    config = provider_config()
    config.name = "future_asr"
    config.extra.update(
        {
            "request_format": "binary",
            "endpoint": "/speech/transcribe",
            "auth_scheme": "custom",
            "api_key_header": "X-Future-Key",
            "api_key_prefix": "",
            "headers": {"X-Client": "petagent"},
            "query_params": {"model": "fast-zh", "language": "zh-CN"},
            "transcript_paths": ["result.text"],
            "confidence_paths": ["result.score"],
        }
    )
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"result": {"text": "今天有点累", "score": 0.77}}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("app.providers.asr_http.requests.post", fake_post)

    transcript = HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert captured["url"] == "https://asr.example/speech/transcribe"
    assert captured["headers"] == {
        "X-Future-Key": "test-key",
        "X-Client": "petagent",
        "Content-Type": "audio/wav",
    }
    assert captured["params"] == {"model": "fast-zh", "language": "zh-CN"}
    assert captured["data"] == b"RIFF custom wav"
    assert "files" not in captured
    assert transcript.text == "今天有点累"
    assert transcript.confidence == 0.77
    assert transcript.provider == "future_asr"


def test_http_asr_returns_empty_transcript_when_not_configured(tmp_path: Path):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    config = provider_config()
    config.base_url = None

    transcript = HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert transcript.text == ""
    assert transcript.confidence == 0.0
    assert transcript.error_code == "asr_not_configured"


def test_http_asr_reports_sanitized_http_error(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")

    class Response:
        status_code = 401

        def raise_for_status(self):
            error = requests.HTTPError("401 Client Error: token leaked")
            error.response = self
            raise error

    def fake_post(url, **kwargs):
        return Response()

    monkeypatch.setattr("app.providers.asr_http.requests.post", fake_post)

    transcript = HttpASRProvider(provider_config()).transcribe(audio, "audio/wav")

    assert transcript.text == ""
    assert transcript.confidence == 0.0
    assert transcript.error_code == "asr_http_401"
    assert transcript.error_message == "ASR HTTP request failed with status 401"
    assert "test-key" not in transcript.error_message
    assert "asr.example" not in transcript.error_message


def test_http_asr_retries_transient_5xx_then_succeeds(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    config = provider_config()
    config.extra["transient_retries"] = 1
    config.extra["retry_backoff_seconds"] = 0
    calls = []

    class ErrorResponse:
        status_code = 500

        def raise_for_status(self):
            error = requests.HTTPError("500 Server Error")
            error.response = self
            raise error

    class SuccessResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "早上好豆豆"}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return ErrorResponse() if len(calls) == 1 else SuccessResponse()

    monkeypatch.setattr("app.providers.asr_http.requests.post", fake_post)

    transcript = HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert len(calls) == 2
    assert transcript.text == "早上好豆豆"
    assert transcript.error_code == ""


def test_http_asr_uses_fallback_model_for_transient_retry(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    config = provider_config()
    config.extra["transient_retries"] = 1
    config.extra["retry_backoff_seconds"] = 0
    config.extra["fallback_models"] = ["iic/SenseVoiceSmall"]
    models = []

    class ErrorResponse:
        status_code = 500

        def raise_for_status(self):
            error = requests.HTTPError("500 Server Error")
            error.response = self
            raise error

    class SuccessResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "备用模型听清了"}

    def fake_post(url, **kwargs):
        models.append(kwargs["data"]["model"])
        return ErrorResponse() if len(models) == 1 else SuccessResponse()

    monkeypatch.setattr("app.providers.asr_http.requests.post", fake_post)

    transcript = HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert models == ["parakeet-ctc-0.6b-zh-cn", "iic/SenseVoiceSmall"]
    assert transcript.text == "备用模型听清了"
    assert transcript.error_code == ""


def test_http_asr_does_not_retry_client_errors(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    config = provider_config()
    config.extra["transient_retries"] = 2
    calls = []

    class ErrorResponse:
        status_code = 400

        def raise_for_status(self):
            error = requests.HTTPError("400 Client Error")
            error.response = self
            raise error

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return ErrorResponse()

    monkeypatch.setattr("app.providers.asr_http.requests.post", fake_post)

    transcript = HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert len(calls) == 1
    assert transcript.error_code == "asr_http_400"


def test_http_asr_does_not_retry_timeouts(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    config = provider_config()
    config.extra["transient_retries"] = 2
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        raise requests.Timeout("read timed out")

    monkeypatch.setattr("app.providers.asr_http.requests.post", fake_post)

    transcript = HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert len(calls) == 1
    assert transcript.error_code == "asr_timeout"


def test_http_asr_does_not_retry_bad_json(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    config = provider_config()
    config.extra["transient_retries"] = 2
    calls = []

    class BadJsonResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("not json")

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return BadJsonResponse()

    monkeypatch.setattr("app.providers.asr_http.requests.post", fake_post)

    transcript = HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert len(calls) == 1
    assert transcript.error_code == "asr_bad_response"


def test_timeout_tuple_keeps_total_under_scalar(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    config = provider_config()
    config.timeout_seconds = 6
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "你好"}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("app.providers.asr_http.requests.post", fake_post)

    HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert captured["timeout"] == (3, 3)
