from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def test_voice_chat_returns_behavior_package_for_audio_upload():
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/voice/chat",
        files={"file": ("hello.webm", b"momo audio bytes", "audio/webm")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_text"]
    assert body["audio_understanding"]["detected_emotion"] in {
        "calm",
        "tired",
        "happy",
        "sad",
        "angry",
        "anxious",
        "uncertain",
    }
    assert 0 <= body["audio_understanding"]["confidence"] <= 1
    assert body["reply"]
    assert body["voice_url"] is not None
    assert body["runtime"]["skills_used"] == []
    assert body["runtime"]["event_id"]
    assert body["pet_state"]["schema_version"] == "0.1"


def test_voice_chat_rejects_unsupported_audio_type():
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/voice/chat",
        files={"file": ("note.txt", b"not audio", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported audio content type" in response.json()["detail"]


def test_voice_chat_rejects_audio_larger_than_limit():
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/voice/chat",
        files={"file": ("large.webm", b"x" * (8 * 1024 * 1024 + 1), "audio/webm")},
    )

    assert response.status_code == 413
    assert "Audio file is too large" in response.json()["detail"]


def test_voice_chat_falls_back_when_audio_provider_fails():
    app = create_app(testing=True)
    app.state.audio_provider.fail = True
    client = TestClient(app)

    response = client.post(
        "/api/voice/chat",
        data={"route": "slow"},
        files={"file": ("noise.webm", b"noise", "audio/webm")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_text"] == ""
    assert body["audio_understanding"] == {
        "user_text": "",
        "detected_emotion": "uncertain",
        "tone_notes": "没有稳定识别到语音",
        "non_verbal": "",
        "confidence": 0.0,
    }
    assert body["reply"]


def test_voice_chat_does_not_create_accumulating_debug_log(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("PETAGENT_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/voice/chat",
        files={"file": ("hello.webm", b"momo audio bytes", "audio/webm")},
    )

    assert response.status_code == 200
    assert not (tmp_path / "data" / "logs" / "voice_debug.jsonl").exists()
