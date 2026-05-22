"""Tests for Phase 0 safety gates: STAB-019 (ProviderError catch), STAB-027 (state side effects), STAB-032 (auth/CORS)."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.auth import get_internal_token, is_loopback, require_internal_token
from app.main import create_app
from app.providers.errors import (
    ProviderAuthError,
    ProviderBadResponseError,
    ProviderNetworkError,
    ProviderQuotaError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


# --- STAB-019: ProviderError catch in API routes ---


def _make_app_with_failing_provider(error_class):
    """Create an app where the text pipeline raises a ProviderError."""
    app = create_app(testing=True)

    def _raise(*args, **kwargs):
        raise error_class(provider="test", message="test error")

    app.state.text_pipeline.handle = _raise
    app.state.voice_pipeline.handle = _raise
    return app


def test_text_chat_catches_provider_auth_error():
    app = _make_app_with_failing_provider(ProviderAuthError)
    client = TestClient(app)
    resp = client.post("/api/text/chat", json={"text": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["error_class"] == "provider_auth_failed"
    assert body["reply"]  # has fallback reply
    assert body["mood"] == "tired"


def test_text_chat_catches_provider_timeout():
    app = _make_app_with_failing_provider(ProviderTimeoutError)
    client = TestClient(app)
    resp = client.post("/api/text/chat", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["error_class"] == "provider_timeout"


def test_text_chat_catches_provider_unavailable():
    app = _make_app_with_failing_provider(ProviderUnavailableError)
    client = TestClient(app)
    resp = client.post("/api/text/chat", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["error_class"] == "provider_unavailable"


def test_text_chat_success_has_null_error_class():
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.post("/api/text/chat", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["error_class"] is None


def test_voice_chat_catches_provider_error():
    app = _make_app_with_failing_provider(ProviderAuthError)
    client = TestClient(app)
    resp = client.post(
        "/api/voice/chat",
        data={},
        files={"file": ("voice.wav", b"RIFF\x00\x00\x00\x00WAVE", "audio/wav")},
    )
    assert resp.status_code == 200
    assert resp.json()["error_class"] == "provider_auth_failed"


def test_voice_chat_success_has_null_error_class():
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.post(
        "/api/voice/chat",
        data={},
        files={"file": ("voice.wav", b"RIFF\x00\x00\x00\x00WAVE", "audio/wav")},
    )
    assert resp.status_code == 200
    assert resp.json()["error_class"] is None


# --- STAB-027: State side-effect removal ---


def test_get_pet_state_does_not_call_apply_if_due():
    app = create_app(testing=True)
    mock_tick = MagicMock()
    app.state.tick_service = mock_tick
    client = TestClient(app)
    client.get("/api/pet/state")
    mock_tick.apply_if_due.assert_not_called()


def test_post_session_resume_calls_apply_if_due():
    app = create_app(testing=True)
    mock_tick = MagicMock()
    app.state.tick_service = mock_tick
    client = TestClient(app)
    resp = client.post("/api/pet/session/resume")
    assert resp.status_code == 200
    mock_tick.apply_if_due.assert_called_once()
    assert "mood" in resp.json()  # returns state


def test_post_event_still_calls_apply_if_due():
    app = create_app(testing=True)
    # The dispatcher holds its own tick_service reference, so patch it there
    original_tick = app.state.dispatcher.tick_service
    mock_tick = MagicMock()
    app.state.dispatcher.tick_service = mock_tick
    client = TestClient(app)
    client.post("/api/pet/event", json={"type": "pet_head", "source": "runtime"})
    mock_tick.apply_if_due.assert_called_once()
    # Restore
    app.state.dispatcher.tick_service = original_tick


# --- STAB-032: Auth and CORS ---


def test_internal_token_generated_when_env_unset(monkeypatch):
    from pathlib import Path

    monkeypatch.delenv("DEBUG_INTERNAL_TOKEN", raising=False)
    settings = MagicMock()
    with tempfile.TemporaryDirectory() as td:
        settings.data_dir = Path(td) / "data"
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        token = get_internal_token(settings)
        assert len(token) == 48  # 24 bytes hex
        # Should persist (at data_dir.parent / "secrets" / "internal_token")
        token_path = Path(td) / "secrets" / "internal_token"
        assert token_path.exists()
        # Second call returns same token
        assert get_internal_token(settings) == token


def test_internal_token_from_env(monkeypatch):
    monkeypatch.setenv("DEBUG_INTERNAL_TOKEN", "test-token-123")
    settings = MagicMock()
    token = get_internal_token(settings)
    assert token == "test-token-123"


def test_is_loopback_localhost():
    request = MagicMock()
    request.client.host = "127.0.0.1"
    assert is_loopback(request) is True
    request.client.host = "::1"
    assert is_loopback(request) is True
    request.client.host = "192.168.1.1"
    assert is_loopback(request) is False


def test_require_internal_token_rejects_missing():
    app = create_app(testing=True)
    app.state.internal_token = "secret-token"
    client = TestClient(app)
    # Hit a debug endpoint (if exists) or test the dependency directly
    request = MagicMock()
    request.app.state.internal_token = "secret-token"
    request.headers = {}
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        require_internal_token(request)
    assert exc_info.value.status_code == 403


def test_require_internal_token_accepts_valid():
    request = MagicMock()
    request.app.state.internal_token = "secret-token"
    request.headers = {"authorization": "Bearer secret-token"}
    # Should not raise
    require_internal_token(request)


def test_cors_allows_loopback_origin():
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "http://127.0.0.1:8000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code in (200, 204)
    assert "access-control-allow-origin" in resp.headers
