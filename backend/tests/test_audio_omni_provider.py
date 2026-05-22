from pathlib import Path
from unittest.mock import MagicMock

import base64
import pytest
import requests

from app.config import load_settings
from app.providers.errors import (
    ProviderAuthError,
    ProviderBadResponseError,
    ProviderNetworkError,
    ProviderQuotaError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.providers.audio_omni import (
    AudioUnderstanding,
    MockAudioUnderstandingProvider,
    MiMoAudioUnderstandingProvider,
    encode_audio_base64_chunked,
    parse_audio_understanding,
)


def test_parse_audio_understanding_accepts_valid_json_text():
    parsed = parse_audio_understanding(
        '{"user_text":"我回来啦","detected_emotion":"happy",'
        '"tone_notes":"声音轻快","non_verbal":"","confidence":0.91}'
    )

    assert parsed == AudioUnderstanding(
        user_text="我回来啦",
        detected_emotion="happy",
        tone_notes="声音轻快",
        non_verbal="",
        confidence=0.91,
    )


def test_parse_audio_understanding_falls_back_for_invalid_json():
    parsed = parse_audio_understanding("not json")

    assert parsed.detected_emotion == "uncertain"
    assert parsed.user_text == ""
    assert parsed.confidence == 0.0


def test_parse_audio_understanding_clamps_confidence_and_unknown_emotion():
    parsed = parse_audio_understanding(
        {
            "user_text": "我有点烦",
            "detected_emotion": "furious",
            "tone_notes": "声音有点急",
            "non_verbal": "叹气",
            "confidence": 2,
        }
    )

    assert parsed.detected_emotion == "uncertain"
    assert parsed.confidence == 1.0


def test_mock_audio_provider_returns_fallback_when_missing_file(tmp_path: Path):
    provider = MockAudioUnderstandingProvider()

    result = provider.understand(tmp_path / "missing.wav", "audio/wav")

    assert result.detected_emotion == "uncertain"
    assert result.confidence == 0.0


def test_mimo_audio_provider_falls_back_for_silent_wav_without_network(
    tmp_path: Path, monkeypatch
):
    import wave

    sample = tmp_path / "silent.wav"
    with wave.open(str(sample), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000)
    settings = load_settings(
        env={"MIMO_API_KEY": "fake", "MIMO_BASE_URL": "https://example.invalid/v1"}
    )
    calls = []
    monkeypatch.setattr(
        "app.providers.audio_omni.requests.post",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = MiMoAudioUnderstandingProvider(settings).understand(sample, "audio/wav")

    assert result.detected_emotion == "uncertain"
    assert result.confidence == 0.0
    assert calls == []


def _settings_for_audio_provider(**overrides):
    settings = load_settings(
        env={"MIMO_API_KEY": "fake-key", "MIMO_BASE_URL": "https://example.test/v1"}
    )
    config = settings.audio_understanding
    for key, value in overrides.items():
        setattr(config, key, value)
    return settings


def _write_non_silent_wav(path: Path) -> None:
    import wave

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        frames = []
        for index in range(16000):
            sample = 600 if index % 2 == 0 else -600
            frames.append(sample.to_bytes(2, "little", signed=True))
        handle.writeframes(b"".join(frames))


def test_encode_audio_base64_chunked_matches_standard_base64(tmp_path: Path):
    audio = tmp_path / "sample.bin"
    payload = bytes(range(251)) * 257
    audio.write_bytes(payload)

    encoded = encode_audio_base64_chunked(audio, chunk_size=1025)

    assert encoded == base64.b64encode(payload).decode("ascii")


def test_mimo_audio_provider_raises_auth_error_when_key_missing(tmp_path: Path):
    audio = tmp_path / "voice.wav"
    _write_non_silent_wav(audio)
    settings = _settings_for_audio_provider(api_key="")

    with pytest.raises(ProviderAuthError):
        MiMoAudioUnderstandingProvider(settings).understand(audio, "audio/wav")


def test_mimo_audio_provider_does_not_fall_back_to_global_api_key(tmp_path: Path):
    audio = tmp_path / "voice.wav"
    _write_non_silent_wav(audio)
    settings = load_settings(
        env={
            "SILICONFLOW_API_KEY": "global-key",
            "MIMO_BASE_URL": "https://example.test/v1",
        }
    )
    settings.audio_understanding.api_key = ""
    settings.api_key = "global-key"

    with pytest.raises(ProviderAuthError) as exc_info:
        MiMoAudioUnderstandingProvider(settings).understand(audio, "audio/wav")

    assert exc_info.value.code == "missing_api_key"


def test_mimo_audio_provider_raises_timeout(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    _write_non_silent_wav(audio)
    provider = MiMoAudioUnderstandingProvider(_settings_for_audio_provider())
    monkeypatch.setattr(
        "app.providers.audio_omni.requests.post",
        MagicMock(side_effect=requests.Timeout("read timed out")),
    )

    with pytest.raises(ProviderTimeoutError):
        provider.understand(audio, "audio/wav")


def test_mimo_audio_provider_raises_network_error(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    _write_non_silent_wav(audio)
    provider = MiMoAudioUnderstandingProvider(_settings_for_audio_provider())
    monkeypatch.setattr(
        "app.providers.audio_omni.requests.post",
        MagicMock(side_effect=requests.ConnectionError("dns failed")),
    )

    with pytest.raises(ProviderNetworkError):
        provider.understand(audio, "audio/wav")


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderQuotaError),
        (500, ProviderUnavailableError),
    ],
)
def test_mimo_audio_provider_maps_http_errors(tmp_path: Path, monkeypatch, status, expected):
    audio = tmp_path / "voice.wav"
    _write_non_silent_wav(audio)
    provider = MiMoAudioUnderstandingProvider(_settings_for_audio_provider())
    response = MagicMock()
    response.status_code = status
    response.raise_for_status.side_effect = requests.HTTPError(response=response)
    monkeypatch.setattr("app.providers.audio_omni.requests.post", MagicMock(return_value=response))

    with pytest.raises(expected):
        provider.understand(audio, "audio/wav")


def test_mimo_audio_provider_raises_bad_response_for_malformed_body(
    tmp_path: Path, monkeypatch
):
    audio = tmp_path / "voice.wav"
    _write_non_silent_wav(audio)
    provider = MiMoAudioUnderstandingProvider(_settings_for_audio_provider())
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
    monkeypatch.setattr("app.providers.audio_omni.requests.post", MagicMock(return_value=response))

    with pytest.raises(ProviderBadResponseError):
        provider.understand(audio, "audio/wav")
