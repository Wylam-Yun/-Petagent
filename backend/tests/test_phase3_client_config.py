"""Tests for STAB-016: Client config endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_client_config_returns_public_fields():
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.get("/api/runtime/client-config")
    assert resp.status_code == 200
    data = resp.json()
    assert "audio_wait_ms" in data
    assert "audio_progressive" in data
    assert "pet_name" in data
    assert data["audio_wait_ms"] > 0


def test_client_config_no_sensitive_fields():
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.get("/api/runtime/client-config")
    data = resp.json()
    # Must not expose provider keys, proxy, DB, or incident data
    sensitive_keys = {"api_key", "tts_api_key", "proxy_url", "db_path", "internal_token"}
    for key in sensitive_keys:
        assert key not in data, f"Sensitive key '{key}' exposed in client config"


def test_client_config_audio_progressive_is_dict():
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.get("/api/runtime/client-config")
    data = resp.json()
    progressive = data["audio_progressive"]
    assert isinstance(progressive, dict)
    assert len(progressive) > 0
    # Keys should be numeric strings (milliseconds)
    for key in progressive:
        assert key.isdigit(), f"Progressive key '{key}' is not a millisecond value"


def test_health_includes_build_hash():
    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "build_hash" in data
