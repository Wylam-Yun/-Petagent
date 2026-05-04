import os
from pathlib import Path

import pytest

from app.config import load_settings
from app.providers.asr_nvidia import NvidiaParakeetASRProvider


pytestmark = pytest.mark.smoke


def test_nvidia_parakeet_asr_smoke_transcribes_user_sample():
    settings = load_settings()
    sample_path = os.environ.get("PETAGENT_ASR_SMOKE_WAV")
    if not settings.asr or not settings.asr.api_key or not settings.asr.base_url:
        pytest.skip("NVIDIA ASR credentials are not configured")
    if not sample_path or not Path(sample_path).exists():
        pytest.skip("PETAGENT_ASR_SMOKE_WAV is not configured")

    provider = NvidiaParakeetASRProvider(settings.asr)
    if provider.riva is None:
        pytest.skip("nvidia-riva-client is not installed")

    transcript = provider.transcribe(Path(sample_path), "audio/wav")

    assert transcript.provider == "nvidia_parakeet"
    assert transcript.text
    assert 0 <= transcript.confidence <= 1
    assert "NVIDIA_API_KEY" not in os.environ.get("PYTEST_CURRENT_TEST", "")
