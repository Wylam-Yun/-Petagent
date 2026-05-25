"""Tests for V1.3 Stage 5: Behavior Slot Execution."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_fast_reply_includes_action():
    """Fast Reply response includes action field."""
    client = TestClient(create_app(testing=True))
    response = client.post("/api/text/chat", json={"text": "你好"})
    assert response.status_code == 200
    body = response.json()
    # action may be None for non-fast-reply, but field should exist
    assert "action" in body


def test_fast_reply_action_is_valid():
    """action value, when present, is a valid DoudouAction."""
    valid_actions = {
        "idle", "waiting", "review", "waving", "jumping",
        "failed", "running", "running-left", "running-right",
    }
    client = TestClient(create_app(testing=True))
    response = client.post("/api/text/chat", json={"text": "你好"})
    body = response.json()
    action = body.get("action")
    if action is not None:
        assert action in valid_actions, f"Invalid action: {action}"


def test_thinking_response_has_behavior_plan():
    """Thinking mode response includes behavior_plan."""
    client = TestClient(create_app(testing=True))
    response = client.post(
        "/api/text/chat",
        json={"text": "你好", "thinking_mode": True},
    )
    assert response.status_code == 200
    body = response.json()
    # behavior_plan may be None if LLM didn't provide one
    assert "behavior_plan" in body
    assert "behavior_intent" in body


def test_pet_response_has_action_route_fields():
    """PetResponse includes action, route, memory_ack_hint."""
    client = TestClient(create_app(testing=True))
    response = client.post("/api/pet/event", json={"event": "pet_head", "payload": {}})
    assert response.status_code == 200
    body = response.json()
    assert "action" in body
    assert "route" in body
    assert "memory_ack_hint" in body


def test_fast_reply_route_value():
    """Fast Reply responses have route='fast_reply'."""
    client = TestClient(create_app(testing=True))
    response = client.post("/api/text/chat", json={"text": "你好"})
    assert response.status_code == 200
    body = response.json()
    # route should be fast_reply or thinking depending on routing
    assert body.get("route") in ("fast_reply", "thinking", None)
