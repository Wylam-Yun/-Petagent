import os
import wave
from pathlib import Path

import pytest

from app.config import load_settings
from app.providers.audio_omni import ALLOWED_EMOTIONS, MiMoAudioUnderstandingProvider


pytestmark = pytest.mark.smoke


def test_mimo_audio_understanding_smoke_accepts_short_wav(tmp_path: Path):
    settings = load_settings()
    if not settings.api_key or not settings.audio_understanding.base_url:
        pytest.skip("MIMO_API_KEY or MIMO_BASE_URL is not configured")

    sample = tmp_path / "sample_noise.wav"
    write_short_silent_wav(sample)

    provider = MiMoAudioUnderstandingProvider(settings)
    result = provider.understand(sample, "audio/wav")

    assert result.detected_emotion in ALLOWED_EMOTIONS
    assert 0 <= result.confidence <= 1
    assert len(result.tone_notes) < 200
    assert "MIMO_API_KEY" not in os.environ.get("PYTEST_CURRENT_TEST", "")


def write_short_silent_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000)
