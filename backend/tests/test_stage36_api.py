"""Stage 3.6: API endpoint tests."""
from fastapi.testclient import TestClient

from app.main import create_app
from app.runtime.memory_store import MemoryCandidateStore, MemoryManager


def _auth_headers(app):
    return {"Authorization": f"Bearer {app.state.internal_token}"}


def test_memory_debug_returns_desensitized_data():
    app = create_app(testing=True)
    app.state.settings.app_config.setdefault("cognition_context", {})["debug_enabled"] = True

    # Add a memory with a fake secret
    mm = app.state.memory_manager
    mm.save_curated("user_preference", "用户 API key 是 sk-abc123def456", importance=3)

    client = TestClient(app)
    assert client.get("/api/memory/debug").status_code == 403
    response = client.get("/api/memory/debug", headers=_auth_headers(app))
    assert response.status_code == 200
    body = response.json()

    assert body["ok"] is True
    assert body["debug_enabled"] is True
    assert "memories" in body
    assert len(body["memories"]) >= 1
    # Secret should be redacted
    for mem in body["memories"]:
        assert "sk-abc123def456" not in mem["content"]


def test_memory_debug_disabled_by_default():
    app = create_app(testing=True)
    client = TestClient(app)

    response = client.get("/api/memory/debug", headers=_auth_headers(app))
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["debug_enabled"] is False


def test_memory_curate_endpoint():
    app = create_app(testing=True)
    cs = app.state.memory_candidate_store
    cs.add("evt-1", "ep-1", "用户喜欢短回复", "explicit_command")

    client = TestClient(app)
    assert client.post("/api/memory/curate").status_code == 403
    response = client.post("/api/memory/curate", headers=_auth_headers(app))
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    # Should have processed something (saved, ignored, or errors)
    assert "saved" in body or "ignored" in body or "errors" in body


def test_memory_summarize_episode_no_active():
    app = create_app(testing=True)
    client = TestClient(app)

    response = client.post(
        "/api/memory/summarize",
        json={"mode": "episode"},
        headers=_auth_headers(app),
    )
    # Should fail if no active episode with events
    assert response.status_code in (200, 400)


def test_memory_summarize_invalid_mode():
    app = create_app(testing=True)
    client = TestClient(app)

    response = client.post(
        "/api/memory/summarize",
        json={"mode": "invalid"},
        headers=_auth_headers(app),
    )
    assert response.status_code == 400


def test_runtime_reset_requires_confirmation():
    app = create_app(testing=True)
    # Add some data
    mm = app.state.memory_manager
    mm.save_curated("user_preference", "测试记忆", importance=3)

    client = TestClient(app)

    # Non-loopback requests still require auth before confirmation is checked.
    assert client.post("/api/runtime/reset", json={}).status_code == 403
    response = client.post("/api/runtime/reset", json={}, headers=_auth_headers(app))
    assert response.status_code == 400

    # With wrong confirm value → 400
    response = client.post(
        "/api/runtime/reset",
        json={"confirm": "wrong"},
        headers=_auth_headers(app),
    )
    assert response.status_code == 400

    # Memory should still exist
    assert mm.count() >= 1


def test_runtime_reset_allows_loopback_frontend_without_token(monkeypatch):
    app = create_app(testing=True)
    client = TestClient(app)
    monkeypatch.setattr("app.api.memory.is_loopback", lambda request: True)

    response = client.post("/api/runtime/reset", json={"confirm": "重新认识"})

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_runtime_reset_clears_everything():
    app = create_app(testing=True)
    mm = app.state.memory_manager
    cs = app.state.memory_candidate_store
    ess = app.state.episode_summary_store

    # Add data
    mm.save_curated("user_preference", "测试记忆", importance=3)
    cs.add("evt-1", "ep-1", "候选记忆", "llm_suggestion")

    client = TestClient(app)

    # Correct confirmation
    response = client.post(
        "/api/runtime/reset",
        json={"confirm": "重新认识"},
        headers=_auth_headers(app),
    )
    assert response.status_code == 200
    body = response.json()

    assert body["ok"] is True
    assert "pet_state" in body
    assert "reply" in body
    assert "豆豆" not in body["reply"]

    # All data cleared
    assert mm.count() == 0
    assert cs.count_pending() == 0
