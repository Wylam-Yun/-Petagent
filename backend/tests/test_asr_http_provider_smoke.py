import os
import wave
from pathlib import Path

import pytest

from app.config import load_settings
from app.providers.asr_http import HttpASRProvider


pytestmark = pytest.mark.smoke


def test_http_asr_smoke_transcribes_short_wav(tmp_path: Path):
    settings = load_settings()
    if not settings.asr or settings.asr.extra.get("protocol") != "http":
        pytest.skip("HTTP ASR provider is not configured")
    if not settings.asr.base_url:
        pytest.skip("ASR_BASE_URL is not configured")

    sample = os.environ.get("PETAGENT_ASR_SMOKE_WAV")
    sample_path = Path(sample) if sample else tmp_path / "sample.wav"
    if not sample:
        write_silent_wav(sample_path)

    result = HttpASRProvider(settings.asr).transcribe(sample_path, "audio/wav")

    assert result.provider == settings.asr.name
    assert 0 <= result.confidence <= 1
    assert "NVIDIA_API_KEY" not in os.environ.get("PYTEST_CURRENT_TEST", "")


def write_silent_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000)
