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
    client = TestClient(create_app(testing=True))

    response = client.post("/api/skills/unknown.run/run", json={})

    assert response.status_code == 404


def test_device_info_skill_returns_structured_result():
    client = TestClient(create_app(testing=True))
    client.post("/api/device/state", json={"battery": 64, "is_charging": True})

    response = client.post("/api/skills/device.info/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == "device.info"
    assert body["ok"] is True
    assert body["data"]["battery"] == 64
    assert body["data"]["is_charging"] is True


def test_weather_skill_failure_is_structured_when_provider_unavailable():
    client = TestClient(create_app(testing=True))

    response = client.post("/api/skills/weather.current/run", json={"location": "current"})

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == "weather.current"
    assert "ok" in body
    assert "error" in body


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
    assert "active" in response.json()
