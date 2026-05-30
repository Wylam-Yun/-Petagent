from fastapi.testclient import TestClient

from app.main import create_app


def test_pet_event_writes_interaction_log():
    app = create_app(testing=True)
    client = TestClient(app)

    response = client.post("/api/pet/event", json={"event": "pet_head", "payload": {}})

    assert response.status_code == 200
    rows = app.state.interaction_log.recent_dialogue(limit=3)
    assert rows
    assert rows[0]["event_type"] == "pet_head"
    assert rows[0]["pet"] == response.json()["reply"]


def test_voice_chat_ignores_llm_memory_update_in_foreground_path():
    """V1.5 memory writes are background summaries, not foreground memory_update."""
    app = create_app(testing=True)

    class MemoryLLM:
        name = "memory_llm"

        def complete_json(self, messages):
            return {
                "reply": "辛苦啦，豆豆陪你慢慢缓一下。",
                "mood": "concerned",
                "face_type": "concerned",
                "animation": "tilt",
                "voice_style": "soft",
                "vibration": "light",
                "state_delta": {"loneliness": -2},
                "memory_update": {
                    "should_save": True,
                    "content": "用户今天很累，需要温柔陪伴。",
                },
            }

    app.state.voice_pipeline.fast_brain.provider = MemoryLLM()

    # Disable maintenance tick so candidates aren't processed mid-test
    app.state.dispatcher.maintenance_service = None
    client = TestClient(app)

    response = client.post(
        "/api/voice/chat",
        data={"thinking_mode": "true"},
        files={"file": ("voice.wav", b"RIFF\x00\x00\x00\x00WAVE", "audio/wav")},
    )

    assert response.status_code == 200
    # Stage 3.6: memory_update goes to candidate store, not directly to memory
    pending = app.state.memory_candidate_store.pending(limit=5)
    texts = [c["candidate_text"] for c in pending]
    assert "用户今天很累，需要温柔陪伴。" not in texts


def test_voice_weather_question_fast_reply_no_skills():
    """V1.3: fast reply voice does not execute skills."""
    app = create_app(testing=True)
    app.state.asr_provider.text = "今天适合出门吗"

    class PlanningLLM:
        name = "planning_llm"

        def complete_json(self, messages):
            content = messages[-1]["content"]
            if "skill_requests" in content:
                return {
                    "skill_requests": [
                        {"skill_id": "weather.current", "payload": {"location": "current"}}
                    ],
                    "reason": "用户询问出门天气",
                }
            return {
                "reply": "天气刚刚没问到，但出门前可以看一眼窗外哦。",
                "mood": "concerned",
            }

    app.state.voice_pipeline.fast_brain.provider = PlanningLLM()
    client = TestClient(app)

    response = client.post(
        "/api/voice/chat",
        files={"file": ("voice.wav", b"RIFF\x00\x00\x00\x00WAVE", "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    # V1.3: fast reply does not execute skills
    assert body["runtime"]["skills_used"] == []
