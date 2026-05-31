from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def _ambient_payload(**overrides):
    payload = {
        "local_date": "2026-05-31",
        "scene": "post_conversation_idle",
        "idle_step": 0,
        "idle_elapsed_ms": 5 * 60_000,
        "client_state": {
            "visible": True,
            "foreground": True,
            "screen_on": True,
            "idle": True,
            "busy": False,
            "input_active": False,
            "recording": False,
            "waiting_llm": False,
            "waiting_tts": False,
            "playing_tts": False,
        },
    }
    payload.update(overrides)
    return payload


def test_ambient_check_blocks_stale_frontend():
    app = create_app(testing=True)
    client = TestClient(app)

    response = client.post("/api/pet/ambient/check", json=_ambient_payload())

    body = response.json()
    assert body["eligible"] is False
    assert body["block_reason"] in {"frontend_stale", "heartbeat_stale"}


def test_ambient_trigger_generates_without_tts_or_history():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})

    app.state.fast_brain.provider.complete_json = lambda messages: {
        "bubble": "我轻轻待着。",
        "expression_key": "idle_soft",
        "action": "idle",
    }

    before_events = app.state.event_log_store.count()
    response = client.post("/api/pet/ambient/trigger", json=_ambient_payload())
    body = response.json()
    assert body["active"] is True
    assert body["event_id"].startswith("ambient-")
    assert body["bubble"] == "我轻轻待着。"
    assert body["expression_key"] == "idle_soft"
    assert body["audio_job_id"] is None
    assert body["voice_url"] is None
    assert app.state.ambient_bubble_service.debug_state("2026-05-31")["daily_count"] == 0
    assert app.state.event_log_store.count() == before_events

    confirm = client.post("/api/pet/ambient/confirm", json={"event_id": body["event_id"]})
    assert confirm.status_code == 200
    assert confirm.json()["ok"] is True
    assert app.state.ambient_bubble_service.debug_state("2026-05-31")["daily_count"] == 1


def test_ambient_cancel_does_not_count():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})
    app.state.fast_brain.provider.complete_json = lambda messages: {
        "bubble": "我轻轻待着。",
        "expression_key": "idle_soft",
        "action": "idle",
    }
    response = client.post("/api/pet/ambient/trigger", json=_ambient_payload())
    event_id = response.json()["event_id"]
    cancelled = client.post("/api/pet/ambient/cancel", json={"event_id": event_id})
    assert cancelled.json()["ok"] is True
    assert app.state.ambient_bubble_service.debug_state("2026-05-31")["daily_count"] == 0


def test_ambient_provider_busy_returns_explicit_block_reason():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})
    app.state.provider_gate.acquire("llm_fast")
    app.state.provider_gate.acquire("llm_fast")
    try:
        response = client.post("/api/pet/ambient/trigger", json=_ambient_payload())
    finally:
        app.state.provider_gate.release("llm_fast")
        app.state.provider_gate.release("llm_fast")
    assert response.json()["active"] is False
    assert response.json()["block_reason"] == "provider_busy"


def test_ambient_invalid_llm_output_is_silent_failure():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})
    app.state.fast_brain.provider.complete_json = lambda messages: {
        "bubble": "刚刚没有偷懒。",
        "expression_key": "playful",
        "action": "lazy_idle",
    }

    response = client.post("/api/pet/ambient/trigger", json=_ambient_payload())

    body = response.json()
    assert body == {"active": False, "block_reason": "validation_failed"}
    assert app.state.ambient_bubble_service.debug_state("2026-05-31")["daily_count"] == 0


def test_ambient_trigger_uses_fast_brain_not_slow_dispatcher_brain():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})

    def slow_should_not_run(messages):
        raise AssertionError("ambient should use fast brain")

    app.state.dispatcher.brain.provider.complete_json = slow_should_not_run
    app.state.fast_brain.provider.complete_json = lambda messages: {
        "bubble": "我轻轻待着。",
        "expression_key": "idle_soft",
        "action": "idle",
    }

    response = client.post("/api/pet/ambient/trigger", json=_ambient_payload())

    body = response.json()
    assert body["active"] is True
    assert body["bubble"] == "我轻轻待着。"


def test_ambient_rejects_action_mismatched_with_selected_activity():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})
    app.state.fast_brain.provider.complete_json = lambda messages: {
        "bubble": "我正在假装很忙。",
        "expression_key": "idle_wink",
        "action": "sneak_eat",
    }

    response = client.post("/api/pet/ambient/trigger", json=_ambient_payload())

    assert response.json() == {"active": False, "block_reason": "validation_failed"}


def test_ambient_check_reports_specific_busy_blockers():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})

    cases = [
        ("input_active", {"input_active": True}),
        ("recording", {"recording": True}),
        ("waiting_llm", {"waiting_llm": True}),
        ("waiting_tts", {"waiting_tts": True}),
        ("playing_tts", {"playing_tts": True}),
    ]
    for expected, client_state_update in cases:
        payload = _ambient_payload()
        payload["client_state"].update(client_state_update)
        response = client.post("/api/pet/ambient/check", json=payload)
        body = response.json()
        assert body["eligible"] is False
        assert body["block_reason"] == expected
