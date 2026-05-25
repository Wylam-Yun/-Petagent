from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.pet.prompt_builder import build_pet_messages
from app.runtime.context import build_runtime_context
from app.runtime.events import normalize_event


def test_text_chat_uses_fast_route_by_default():
    client = TestClient(create_app(testing=True))

    response = client.post("/api/text/chat", json={"text": "我今天有点累"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_text"] == "我今天有点累"
    assert body["text_route"]["selected"] == "fast_reply"
    assert body["text_route"]["thinking_mode"] is False
    assert body["text_route"]["brain_provider"] == "mock_fast_llm"
    assert body["voice_url"] is None
    assert body["audio_job_id"]
    assert body["runtime"]["event_id"]


def test_text_chat_uses_slow_route_when_thinking_mode_is_enabled():
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/text/chat",
        json={"text": "帮我认真想想这个问题", "thinking_mode": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text_route"]["selected"] == "thinking"
    assert body["text_route"]["thinking_mode"] is True
    assert body["text_route"]["brain_provider"] == "mock_slow_llm"


def test_text_chat_rejects_empty_text():
    client = TestClient(create_app(testing=True))

    response = client.post("/api/text/chat", json={"text": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "Text message is empty"


def test_text_chat_rejects_too_long_text():
    client = TestClient(create_app(testing=True))

    response = client.post("/api/text/chat", json={"text": "x" * 2500})

    assert response.status_code == 413
    assert response.json()["detail"] == "Text message is too long"


def test_text_chat_handles_wake_and_exit_phrases():
    client = TestClient(create_app(testing=True))

    wake = client.post("/api/text/chat", json={"text": "嗨 momo"})
    exit_response = client.post("/api/text/chat", json={"text": "momo休息吧"})

    assert wake.status_code == 200
    assert wake.json()["activation"]["type"] == "wake"
    assert wake.json()["activation"]["active"] is True
    assert exit_response.status_code == 200
    assert exit_response.json()["activation"]["type"] == "exit"
    assert exit_response.json()["activation"]["active"] is False


def test_text_message_can_trigger_skill_planner():
    from app.skills.base import SkillResult

    app = create_app(testing=True)
    app.state.registry.run_skill = lambda skill_id, payload: SkillResult(
        skill_id=skill_id,
        ok=True,
        content="当前多云，约 22 度。",
        data={},
        confidence=0.9,
    )
    client = TestClient(app)

    response = client.post("/api/text/chat", json={"text": "今天适合出门吗"})

    assert response.status_code == 200
    # V1.3: tool keywords route to fast_reply with no tools
    assert response.json()["runtime"]["skills_used"] == []


def test_text_prompt_mentions_state_affect_and_contextual_buttons():
    settings = load_settings()
    event = normalize_event(
        {
            "event": "praise_momo",
            "payload": {"description": "用户夸夸豆豆", "interaction_group": "pet_care"},
        }
    )
    context = build_runtime_context(
        event,
        {"name": "豆豆", "mood": "happy", "energy": 70},
        cognition_context={"recent_exact_events": [{"user": "刚刚写了代码"}]},
    )

    messages = build_pet_messages(settings, event, context)
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert "state_affect" in user
    assert "按钮事件也必须结合最近上下文" in system
    assert "不要只根据按钮名机械回复" in system
