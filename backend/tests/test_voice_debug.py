from __future__ import annotations

import json
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.providers.audio_omni import MiMoAudioUnderstandingProvider


def test_voice_chat_records_upload_debug_entry(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PETAGENT_DATA_DIR", str(tmp_path / "data"))
    app = create_app(testing=True)
    client = TestClient(app)

    response = client.post(
        "/api/voice/chat",
        files={"file": ("hello.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 200
    entries = _read_debug_entries(tmp_path / "data" / "logs" / "voice_debug.jsonl")
    upload = next(entry for entry in entries if entry["event"] == "upload_received")
    assert upload["filename"].endswith(".wav")
    assert upload["content_type"] == "audio/wav"
    assert upload["size_bytes"] > 44
    assert upload["audio_probe"]["format"] == "wav"
    assert upload["audio_probe"]["duration_seconds"] > 0
    assert upload["audio_probe"]["max_amplitude"] > 0


def test_mimo_audio_provider_records_raw_model_reply(tmp_path: Path, monkeypatch):
    sample = tmp_path / "hello.wav"
    sample.write_bytes(_wav_bytes())
    settings = load_settings(
        env={
            "PETAGENT_DATA_DIR": str(tmp_path / "data"),
            "MIMO_API_KEY": "fake",
            "MIMO_BASE_URL": "https://example.invalid/v1",
        }
    )

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"user_text":"我今天有点累","detected_emotion":"tired",'
                                '"tone_notes":"声音低一点","non_verbal":"","confidence":0.82}'
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        "app.providers.audio_omni.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = MiMoAudioUnderstandingProvider(settings).understand(sample, "audio/wav")

    assert result.user_text == "我今天有点累"
    entries = _read_debug_entries(tmp_path / "data" / "logs" / "voice_debug.jsonl")
    provider = next(entry for entry in entries if entry["event"] == "audio_provider_result")
    assert provider["filename"] == "hello.wav"
    assert provider["status_code"] == 200
    assert provider["parsed"]["detected_emotion"] == "tired"
    assert "我今天有点累" in provider["raw_content"]
    assert "fake" not in json.dumps(provider, ensure_ascii=False)


def _wav_bytes() -> bytes:
    path = Path("/tmp/petagent-debug-test.wav")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes((1000).to_bytes(2, "little", signed=True) * 16000)
    return path.read_bytes()


def _read_debug_entries(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
