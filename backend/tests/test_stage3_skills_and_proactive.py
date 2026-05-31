from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app
from app.pet.state import PetStateStore
from app.runtime.device import DeviceStateStore
from app.runtime.proactive import ProactiveService


def test_skills_api_lists_builtin_whitelisted_skills():
    client = TestClient(create_app(testing=True))

    response = client.get("/api/skills")

    assert response.status_code == 200
    skill_ids = {item["id"] for item in response.json()["skills"]}
    assert {"device.info", "weather.current"}.issubset(skill_ids)


def test_unknown_skill_returns_404():
    app = create_app(testing=True)
    client = TestClient(app)

    assert client.post("/api/skills/unknown.run/run", json={}).status_code == 403
    response = client.post(
        "/api/skills/unknown.run/run",
        json={},
        headers={"Authorization": f"Bearer {app.state.internal_token}"},
    )

    assert response.status_code == 404


def test_device_info_skill_returns_structured_result():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/device/state", json={"battery": 64, "is_charging": True})

    response = client.post(
        "/api/skills/device.info/run",
        json={},
        headers={"Authorization": f"Bearer {app.state.internal_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == "device.info"
    assert body["ok"] is True
    assert body["data"]["battery"] == 64
    assert body["data"]["is_charging"] is True


def test_weather_skill_failure_is_structured_when_provider_unavailable():
    app = create_app(testing=True)
    app.state.registry._skill_configs["weather.current"]["config"][
        "provider"
    ] = "disabled"
    client = TestClient(app)

    response = client.post(
        "/api/skills/weather.current/run",
        json={"location": "current"},
        headers={"Authorization": f"Bearer {app.state.internal_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == "weather.current"
    assert "ok" in body
    assert "error" in body


def test_weather_skill_uses_configured_network_provider(monkeypatch):
    app = create_app(testing=True)
    weather_config = app.state.registry._skill_configs["weather.current"]["config"]
    weather_config["provider"] = "wttr_in"
    weather_config.pop("mock_weather", None)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "current_condition": [
                    {
                        "temp_C": "22",
                        "FeelsLikeC": "21",
                        "humidity": "60",
                        "windspeedKmph": "8",
                        "weatherDesc": [{"value": "多云"}],
                    }
                ]
            }

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            assert url.startswith("https://wttr.in")
            assert params == {"format": "j1"}
            assert timeout == 5
            return FakeResponse()

    monkeypatch.setattr("app.runtime.registry.requests.Session", lambda: FakeSession())
    client = TestClient(app)

    response = client.post(
        "/api/skills/weather.current/run",
        json={"location": "current"},
        headers={"Authorization": f"Bearer {app.state.internal_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["temperature_c"] == 22
    assert "22" in body["content"]


def test_proactive_morning_only_triggers_once_per_day():
    state_store = PetStateStore(None)
    device = DeviceStateStore(state_store.connection)
    proactive = ProactiveService(state_store, device)
    morning = datetime(2026, 5, 4, 9, 0, 0)

    first = proactive.next_event(now=morning)
    second = proactive.next_event(now=morning + timedelta(minutes=5))

    assert first is not None
    assert first.type == "morning"
    assert second is None


def test_proactive_api_returns_inactive_when_no_candidate():
    client = TestClient(create_app(testing=True))

    response = client.get("/api/pet/proactive")

    assert response.status_code == 200
    assert response.json() == {"active": False, "legacy_disabled": True}


def test_proactive_api_low_cost_trigger_is_disabled_for_v16():
    app = create_app(testing=True)
    state = app.state.state_store.get_state()
    state["last_interaction_at"] = (datetime.utcnow() - timedelta(hours=2)).isoformat()
    state["updated_at"] = state["last_interaction_at"]
    app.state.state_store.save_state(state)
    client = TestClient(app)

    response = client.post("/api/pet/proactive/trigger")

    assert response.status_code == 410
    assert response.json()["detail"]["error_class"] == "legacy_proactive_disabled"


def test_proactive_api_llm_mode_trigger_is_disabled_for_v16():
    app = create_app(testing=True)
    state = app.state.state_store.get_state()
    state["last_interaction_at"] = (datetime.utcnow() - timedelta(hours=2)).isoformat()
    state["updated_at"] = state["last_interaction_at"]
    app.state.state_store.save_state(state)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})

    response = client.post("/api/pet/proactive/trigger?mode=llm")

    assert response.status_code == 410
    assert response.json()["detail"]["error_class"] == "legacy_proactive_disabled"
