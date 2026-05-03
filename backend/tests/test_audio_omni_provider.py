from pathlib import Path

from app.config import load_settings
from app.providers.audio_omni import (
    AudioUnderstanding,
    MockAudioUnderstandingProvider,
    MiMoAudioUnderstandingProvider,
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
