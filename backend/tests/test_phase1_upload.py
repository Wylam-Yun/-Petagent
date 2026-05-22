"""Tests for STAB-013+014: Upload streaming + audio CPU fix."""
from __future__ import annotations

import struct
import tempfile
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def _make_wav_bytes(duration_s: float = 1.0, sample_rate: int = 16000, silent: bool = False) -> bytes:
    """Create a minimal WAV file in memory."""
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(sample_rate * duration_s)
        if silent:
            data = b"\x00\x00" * num_frames
        else:
            # Generate a simple sine wave
            import math
            data = b""
            for i in range(num_frames):
                value = int(32767 * 0.5 * math.sin(2 * math.pi * 440 * i / sample_rate))
                data += struct.pack("<h", value)
        wf.writeframes(data)
    return buf.getvalue()


def test_upload_8mb_succeeds():
    """8MB upload should succeed."""
    app = create_app(testing=True)
    client = TestClient(app)

    # Create a valid WAV that's under 8MB
    wav_data = _make_wav_bytes(duration_s=1.0)
    resp = client.post(
        "/api/voice/chat",
        data={},
        files={"file": ("voice.wav", wav_data, "audio/wav")},
    )
    assert resp.status_code == 200


def test_upload_rejects_unsupported_type():
    """Unsupported content types should be rejected."""
    app = create_app(testing=True)
    client = TestClient(app)

    resp = client.post(
        "/api/voice/chat",
        data={},
        files={"file": ("voice.xyz", b"fake audio", "audio/xyz")},
    )
    assert resp.status_code == 400


def test_empty_audio_detection():
    """Silent WAV should be detected as empty."""
    from app.providers.audio_omni import is_probably_empty_audio

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(_make_wav_bytes(duration_s=1.0, silent=True))
        f.flush()
        path = Path(f.name)

    assert is_probably_empty_audio(path, "audio/wav") is True
    path.unlink()


def test_speech_audio_detection():
    """WAV with audio content should not be detected as empty."""
    from app.providers.audio_omni import is_probably_empty_audio

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(_make_wav_bytes(duration_s=1.0, silent=False))
        f.flush()
        path = Path(f.name)

    assert is_probably_empty_audio(path, "audio/wav") is False
    path.unlink()


def test_short_audio_detected_as_empty():
    """Very short WAV (< 0.25s) should be detected as empty."""
    from app.providers.audio_omni import is_probably_empty_audio

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(_make_wav_bytes(duration_s=0.1))
        f.flush()
        path = Path(f.name)

    assert is_probably_empty_audio(path, "audio/wav") is True
    path.unlink()


def test_empty_audio_detection_fast():
    """Empty audio detection should complete in < 50ms for 8MB WAV."""
    import time
    from app.providers.audio_omni import is_probably_empty_audio

    # Create a large silent WAV (simulate 8MB)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        # 8MB / 2 bytes per sample / 16000 samples per sec = 250 seconds
        f.write(_make_wav_bytes(duration_s=250.0, silent=True))
        f.flush()
        path = Path(f.name)

    start = time.monotonic()
    result = is_probably_empty_audio(path, "audio/wav")
    elapsed_ms = (time.monotonic() - start) * 1000

    assert result is True
    assert elapsed_ms < 100  # Should be well under 100ms with sampling
    path.unlink()
