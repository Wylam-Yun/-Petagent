from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_idle_debug_requires_token():
    app = create_app(testing=True)
    client = TestClient(app)
    response = client.get("/api/debug/idle-state")
    assert response.status_code == 403


def test_idle_debug_contains_required_fields_with_token():
    app = create_app(testing=True)
    client = TestClient(app)
    token = app.state.internal_token
    response = client.get("/api/debug/idle-state", headers={"x-internal-token": token})
    body = response.json()
    assert body["ok"] is True
    for key in [
        "eligible",
        "block_reason",
        "next_trigger_time",
        "backoff_step",
        "daily_count",
        "activity_counts",
        "last_suggested_activity",
        "last_rendered_expression_key",
        "last_validation_failure_reason",
        "last_submitted_tts_text",
        "last_submitted_tts_event_id",
        "last_submitted_tts_at",
        "last_idle_bubble_source",
    ]:
        assert key in body


def test_legacy_proactive_no_longer_generates_user_visible_text():
    app = create_app(testing=True)
    client = TestClient(app)
    check = client.get("/api/pet/proactive")
    assert check.status_code == 200
    assert check.json() == {"active": False, "legacy_disabled": True}
    trigger = client.post("/api/pet/proactive/trigger")
    assert trigger.status_code == 410
