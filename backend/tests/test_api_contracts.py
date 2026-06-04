from fastapi.testclient import TestClient

from app.main import create_app


def test_api_health_contract():
    client = TestClient(create_app(testing=True))

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["name"] == "豆豆"
    assert "version" in body
    assert "pid" in body
    assert "started_at" in body


def test_runtime_contracts():
    app = create_app(testing=True)
    client = TestClient(app)
    token = app.state.internal_token

    assert client.get("/api/runtime/health").json() == {
        "ok": True,
        "runtime": "PetAgent",
        "pet": "豆豆",
    }
    resp = client.get("/api/runtime/skills", headers={"Authorization": f"Bearer {token}"})
    skills = resp.json()["skills"]
    assert {skill["id"] for skill in skills} == {"device.info", "weather.current"}

    # Without token should be rejected
    resp_no_auth = client.get("/api/runtime/skills")
    assert resp_no_auth.status_code == 403


def test_siliconflow_config_status_is_loopback_only(monkeypatch, tmp_path):
    app = create_app(testing=True)
    app.state.settings.project_root = tmp_path
    client = TestClient(app)

    response = client.get("/api/runtime/provider-config/siliconflow")
    assert response.status_code == 403

    monkeypatch.setattr("app.api.runtime.is_loopback", lambda request: True)
    response = client.get("/api/runtime/provider-config/siliconflow")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["provider"] == "siliconflow"
    assert "api_key" not in body


def test_siliconflow_config_update_writes_env_without_returning_secret(monkeypatch, tmp_path):
    app = create_app(testing=True)
    app.state.settings.project_root = tmp_path
    client = TestClient(app)
    monkeypatch.setattr("app.api.runtime.is_loopback", lambda request: True)

    response = client.post(
        "/api/runtime/provider-config/siliconflow",
        json={
            "api_key": "sf-test-key-123456",
            "base_url": "https://api.siliconflow.example/v1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["api_key_configured"] is True
    assert body["base_url"] == "https://api.siliconflow.example/v1"
    assert "sf-test-key-123456" not in response.text

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "SILICONFLOW_API_KEY=sf-test-key-123456\n" in env_text
    assert "SILICONFLOW_BASE_URL=https://api.siliconflow.example/v1\n" in env_text
    assert "ASR_BASE_URL=https://api.siliconflow.example/v1\n" in env_text
    assert app.state.settings.llm.api_key == "sf-test-key-123456"
    assert app.state.settings.llm_fast.api_key == "sf-test-key-123456"
    assert app.state.settings.tts.api_key == "sf-test-key-123456"
    assert app.state.settings.asr.api_key == "sf-test-key-123456"


def test_siliconflow_config_rejects_invalid_values(monkeypatch, tmp_path):
    app = create_app(testing=True)
    app.state.settings.project_root = tmp_path
    client = TestClient(app)
    monkeypatch.setattr("app.api.runtime.is_loopback", lambda request: True)

    short_key = client.post(
        "/api/runtime/provider-config/siliconflow",
        json={"api_key": "short", "base_url": "https://api.siliconflow.example/v1"},
    )
    bad_url = client.post(
        "/api/runtime/provider-config/siliconflow",
        json={"api_key": "sf-test-key-123456", "base_url": "http://api.example/v1"},
    )

    assert short_key.status_code == 400
    assert short_key.json()["detail"]["error_class"] == "invalid_api_key"
    assert bad_url.status_code == 400
    assert bad_url.json()["detail"]["error_class"] == "invalid_base_url"


def test_tts_config_status_and_update_are_loopback_only(monkeypatch, tmp_path):
    app = create_app(testing=True)
    app.state.settings.project_root = tmp_path
    client = TestClient(app)

    response = client.get("/api/runtime/tts-config")
    assert response.status_code == 403

    monkeypatch.setattr("app.api.runtime.is_loopback", lambda request: True)
    status = client.get("/api/runtime/tts-config")

    assert status.status_code == 200
    body = status.json()
    assert body["ok"] is True
    assert body["mode"] == "siliconflow"
    assert "api_key" not in body

    update = client.post("/api/runtime/tts-config", json={"mode": "mimo"})
    assert update.status_code == 400
    assert update.json()["detail"]["error_class"] == "tts_not_switchable"


def test_tts_config_update_writes_env_for_switchable_provider(monkeypatch, tmp_path):
    from app.providers.tts_mimo import MockTTSProvider, SelectableTTSProvider

    app = create_app(testing=True)
    app.state.settings.project_root = tmp_path
    app.state.audio_job_manager.tts_provider = SelectableTTSProvider(
        {
            "siliconflow": MockTTSProvider(tmp_path / "sf"),
            "mimo": MockTTSProvider(tmp_path / "mimo"),
            "weilin": MockTTSProvider(tmp_path / "weilin"),
        },
        mode="siliconflow",
    )
    client = TestClient(app)
    monkeypatch.setattr("app.api.runtime.is_loopback", lambda request: True)

    response = client.post("/api/runtime/tts-config", json={"mode": "weilin"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["mode"] == "weilin"
    assert {item["mode"] for item in body["options"]} == {
        "siliconflow",
        "mimo",
        "weilin",
    }
    assert "api_key" not in response.text
    assert "PETAGENT_TTS_MODE=weilin\n" in (tmp_path / ".env").read_text(encoding="utf-8")
    assert app.state.settings.tts_mode == "weilin"


def test_runtime_restart_requires_loopback_and_confirmation(monkeypatch, tmp_path):
    app = create_app(testing=True)
    app.state.settings.project_root = tmp_path
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "stop.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "scripts" / "start.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    client = TestClient(app)

    denied = client.post("/api/runtime/restart", json={"confirm": "重启后端"})
    assert denied.status_code == 403

    monkeypatch.setattr("app.api.runtime.is_loopback", lambda request: True)
    bad_confirm = client.post("/api/runtime/restart", json={"confirm": "wrong"})
    assert bad_confirm.status_code == 400
    assert bad_confirm.json()["detail"]["error_class"] == "restart_confirmation_required"


def test_runtime_restart_schedules_background_restart(monkeypatch, tmp_path):
    app = create_app(testing=True)
    app.state.settings.project_root = tmp_path
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "stop.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "scripts" / "start.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    client = TestClient(app)
    monkeypatch.setattr("app.api.runtime.is_loopback", lambda request: True)
    scheduled = []
    monkeypatch.setattr(
        "app.api.runtime._schedule_runtime_restart",
        lambda project_root: scheduled.append(project_root),
    )

    response = client.post("/api/runtime/restart", json={"confirm": "重启后端"})

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert scheduled
    assert scheduled[0] == tmp_path


def test_pet_state_contract():
    client = TestClient(create_app(testing=True))

    response = client.get("/api/pet/state")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "0.1"
    assert body["name"] == "豆豆"
    assert 0 <= body["energy"] <= 100


def test_pet_event_contract_returns_behavior_package():
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/pet/event",
        json={"event": "pet_head", "payload": {"description": "用户摸了你的头"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"]
    assert body["mood"] in {
        "idle",
        "happy",
        "sad",
        "sleepy",
        "angry",
        "shy",
        "thinking",
        "concerned",
        "excited",
        "lonely",
    }
    assert "voice_url" in body
    assert body["runtime"]["skills_used"] == []
    assert body["pet_state"]["intimacy"] >= 42
