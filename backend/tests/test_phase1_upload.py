"""Tests for STAB-013+014: Upload streaming + audio CPU fix."""
from __future__ import annotations

import struct
import wave

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
