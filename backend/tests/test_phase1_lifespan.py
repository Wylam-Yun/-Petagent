"""Tests for STAB-006: FastAPI lifespan + shutdown gate."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_lifespan_sets_shutdown_flag():
    """App should have shutdown_in_progress=False on startup."""
    app = create_app(testing=True)
    assert getattr(app.state, "shutdown_in_progress", False) is False


def test_shutdown_gate_text_chat_returns_503():
    """Text chat should return 503 when shutdown_in_progress is True."""
    app = create_app(testing=True)
    app.state.shutdown_in_progress = True
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/text/chat", json={"text": "hello"})
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["reason"] == "shutting_down"


def test_shutdown_gate_voice_chat_returns_503():
    """Voice chat should return 503 when shutdown_in_progress is True."""
    app = create_app(testing=True)
    app.state.shutdown_in_progress = True
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/voice/chat",
        data={},
        files={"file": ("voice.wav", b"RIFF\x00\x00\x00\x00WAVE", "audio/wav")},
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["reason"] == "shutting_down"


def test_text_chat_works_when_not_shutting_down():
    """Text chat should work normally when shutdown_in_progress is False."""
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.post("/api/text/chat", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["error_class"] is None


def test_voice_chat_works_when_not_shutting_down():
    """Voice chat should work normally when shutdown_in_progress is False."""
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.post(
        "/api/voice/chat",
        data={},
        files={"file": ("voice.wav", b"RIFF\x00\x00\x00\x00WAVE", "audio/wav")},
    )
    assert resp.status_code == 200
    assert resp.json()["error_class"] is None


def test_health_not_gated_by_shutdown():
    """Health endpoint should still work during shutdown."""
    app = create_app(testing=True)
    app.state.shutdown_in_progress = True
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
