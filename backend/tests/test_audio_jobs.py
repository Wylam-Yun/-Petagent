from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import create_app


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 2.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = client.get(f"/api/audio/jobs/{job_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in {"ready", "failed", "expired"}:
            return last
        time.sleep(0.02)
    return last


def test_text_chat_returns_audio_job_without_inline_voice_url():
    client = TestClient(create_app(testing=True))

    response = client.post("/api/text/chat", json={"text": "我今天有点累"})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"]
    assert body["voice_url"] is None
    assert body["audio_job_id"]

    job = _wait_for_job(client, body["audio_job_id"])
    assert job["status"] == "ready"
    assert job["voice_url"].startswith("/static/audio/")


def test_audio_job_reports_failed_tts_without_blocking_response():
    app = create_app(testing=True)
    app.state.audio_job_manager.tts_provider.fail = True
    client = TestClient(app)

    response = client.post("/api/pet/event", json={"event": "pet_head", "payload": {}})

    assert response.status_code == 200
    body = response.json()
    assert body["voice_url"] is None
    assert body["audio_job_id"]

    job = _wait_for_job(client, body["audio_job_id"])
    assert job["status"] == "failed"
    assert job["voice_url"] is None


def test_proactive_low_cost_does_not_create_audio_job():
    client = TestClient(create_app(testing=True))

    response = client.get("/api/pet/proactive")
    body = response.json()

    if body.get("active"):
        assert body["voice_url"] is None
        assert body["audio_job_id"] is None
