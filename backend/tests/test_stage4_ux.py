"""Tests for V1.3 Stage 4: UX Recovery Fixes."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_pet_head_event_still_works():
    """Backend still accepts pet_head events (backward compat)."""
    client = TestClient(create_app(testing=True))
    response = client.post("/api/pet/event", json={"event": "pet_head", "payload": {}})
    assert response.status_code == 200
    body = response.json()
    assert body["reply"]


def test_audio_retry_endpoint_exists():
    """POST /api/audio/jobs/{id}/retry returns appropriate status codes."""
    app = create_app(testing=True)
    app.state.audio_job_manager.tts_provider.fail = True
    client = TestClient(app)

    # Non-existent job → 404
    response = client.post("/api/audio/jobs/nonexistent/retry")
    assert response.status_code == 404

    # Create a failed job
    resp = client.post("/api/text/chat", json={"text": "测试"})
    job_id = resp.json().get("audio_job_id")
    if not job_id:
        return

    import time
    deadline = time.time() + 3
    while time.time() < deadline:
        r = client.get(f"/api/audio/jobs/{job_id}")
        if r.json()["status"] in {"ready", "failed", "expired"}:
            break
        time.sleep(0.02)

    # Retry failed job → 200
    retry_resp = client.post(f"/api/audio/jobs/{job_id}/retry")
    assert retry_resp.status_code == 200
    assert retry_resp.json()["new_job_id"]
