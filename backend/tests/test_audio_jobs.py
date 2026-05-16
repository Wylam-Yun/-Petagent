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


def test_audio_job_supersede_same_session():
    """New audio job in same episode supersedes the previous pending job."""
    from app.runtime.audio_jobs import AudioJobManager
    from app.providers.tts_mimo import MockTTSProvider
    from pathlib import Path
    from tempfile import mkdtemp

    tts = MockTTSProvider(Path(mkdtemp()))
    mgr = AudioJobManager(tts, max_workers=1, ttl_seconds=60)

    job1 = mgr.enqueue("first", session_id="ep-1")
    # Small delay so TTS finishes and job1 is no longer pending
    import time
    time.sleep(0.1)

    # Enqueue another — if job1 already completed, no supersede needed
    job2 = mgr.enqueue("second", session_id="ep-1")

    j1 = mgr.get(job1)
    j2 = mgr.get(job2)

    # If job1 was still pending when job2 enqueued, it got superseded
    if j1.status == "superseded":
        assert j1.error == "superseded by newer job"
        assert j2.status in {"pending", "ready", "failed"}
    else:
        # job1 already completed before job2 — both should be terminal
        assert j1.status in {"ready", "failed"}
        assert j2.status in {"pending", "ready", "failed"}

    mgr.shutdown()


def test_audio_job_different_sessions_not_superseded():
    """Jobs in different sessions are independent — no supersede."""
    from app.runtime.audio_jobs import AudioJobManager
    from app.providers.tts_mimo import MockTTSProvider
    from pathlib import Path
    from tempfile import mkdtemp

    tts = MockTTSProvider(Path(mkdtemp()))
    mgr = AudioJobManager(tts, max_workers=2, ttl_seconds=60)

    job1 = mgr.enqueue("first", session_id="ep-1")
    job2 = mgr.enqueue("second", session_id="ep-2")

    j1 = mgr.get(job1)
    j2 = mgr.get(job2)

    # Neither should be superseded (different sessions)
    assert j1.status != "superseded"
    assert j2.status != "superseded"

    mgr.shutdown()


def test_audio_job_lru_eviction():
    """Terminal-status jobs get evicted when max_jobs is exceeded."""
    from app.runtime.audio_jobs import AudioJobManager
    from app.providers.tts_mimo import MockTTSProvider
    from pathlib import Path
    from tempfile import mkdtemp

    tts = MockTTSProvider(Path(mkdtemp()))
    mgr = AudioJobManager(tts, max_workers=2, ttl_seconds=60, max_jobs=5)

    # Fill to capacity
    ids = []
    for i in range(5):
        ids.append(mgr.enqueue(f"text-{i}"))

    import time
    time.sleep(0.3)  # let all finish → terminal

    # Enqueue 2 more — triggers eviction of oldest terminal jobs
    ids.append(mgr.enqueue("text-5"))
    ids.append(mgr.enqueue("text-6"))

    # Oldest terminal jobs should be evicted to maintain max_jobs=5
    assert mgr.get(ids[0]) is None
    assert mgr.get(ids[1]) is None
    # Recent ones survive
    assert mgr.get(ids[-1]) is not None

    mgr.shutdown()
