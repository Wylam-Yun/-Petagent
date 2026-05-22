from fastapi.testclient import TestClient

from app.main import create_app


def test_api_health_contract():
    client = TestClient(create_app(testing=True))

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["name"] == "Momo"
    assert "version" in body
    assert "pid" in body
    assert "started_at" in body


def test_runtime_contracts():
    client = TestClient(create_app(testing=True))

    assert client.get("/api/runtime/health").json() == {
        "ok": True,
        "runtime": "PetAgent",
        "pet": "Momo",
    }
    skills = client.get("/api/runtime/skills").json()["skills"]
    assert {skill["id"] for skill in skills} == {"device.info", "weather.current"}


def test_pet_state_contract():
    client = TestClient(create_app(testing=True))

    response = client.get("/api/pet/state")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "0.1"
    assert body["name"] == "Momo"
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
