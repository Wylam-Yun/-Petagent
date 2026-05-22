import time

from fastapi.testclient import TestClient

from app.main import create_app


def test_pet_event_includes_timings_in_runtime():
    client = TestClient(create_app(testing=True))
    response = client.post("/api/pet/event", json={"event": "hug", "payload": {}})
    assert response.status_code == 200
    body = response.json()
    runtime = body["runtime"]
    assert "timings_ms" in runtime
    timings = runtime["timings_ms"]
    assert "llm" in timings
    assert "total" in timings
    assert timings["llm"] >= 0
    assert timings["total"] >= 0
    assert "provider" in runtime
    assert "route" in runtime
    assert "status" in runtime


def test_text_chat_includes_timings():
    client = TestClient(create_app(testing=True))
    response = client.post("/api/text/chat", json={"text": "你好"})
    assert response.status_code == 200
    body = response.json()
    assert "text_route" in body
    timings = body["text_route"]["timings_ms"]
    assert "total" in timings
    assert timings["total"] >= 0
    # runtime.timings_ms from dispatcher instrumentation
    runtime = body["runtime"]
    assert "llm" in runtime["timings_ms"]
    assert "total" in runtime["timings_ms"]


def test_audio_job_includes_audio_queue():
    client = TestClient(create_app(testing=True))
    response = client.post("/api/text/chat", json={"text": "讲个故事"})
    assert response.status_code == 200
    body = response.json()
    job_id = body.get("audio_job_id")
    assert job_id is not None

    deadline = time.time() + 3.0
    job = None
    while time.time() < deadline:
        r = client.get(f"/api/audio/jobs/{job_id}")
        assert r.status_code == 200
        job = r.json()
        if job["status"] in {"ready", "failed", "expired"}:
            break
        time.sleep(0.02)

    assert job is not None
    assert "audio_queue" in job["timings_ms"]
    assert job["timings_ms"]["audio_queue"] >= 0


def test_run_endpoint_shows_timings():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/pet/event", json={"event": "hug", "payload": {}})
    response = client.get(
        "/api/context/runs?limit=1",
        headers={"Authorization": f"Bearer {app.state.internal_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["runs"]) >= 1
    run = data["runs"][0]
    assert "timings_ms" in run
    assert "total" in run["timings_ms"]
    assert "llm" in run["timings_ms"]
    assert run["route"] in {"fast", "slow"}
    assert isinstance(run["provider"], str)
    assert run["status"] in {"completed", "failed"}


def test_timing_values_are_sane():
    client = TestClient(create_app(testing=True))
    response = client.post("/api/pet/event", json={"event": "feed_momo", "payload": {}})
    assert response.status_code == 200
    timings = response.json()["runtime"]["timings_ms"]
    assert timings["llm"] >= 0
    assert timings["tool"] >= 0  # always present, 0 when tools not used
    assert timings["total"] >= timings["llm"]
