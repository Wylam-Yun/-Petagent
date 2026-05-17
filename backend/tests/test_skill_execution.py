"""Integration tests verifying LLM-planned skills actually execute through the agent loop."""

from __future__ import annotations

from app.main import create_app


def test_llm_planned_weather_skill_executes():
    """LLM skill plan with weather.current must actually run, not get dropped by guard."""
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    original = provider.complete_json

    skill_called = {}
    original_run = app.state.registry.run_skill

    def track_run(skill_id, payload):
        skill_called[skill_id] = payload
        return original_run(skill_id, payload)

    app.state.registry.run_skill = track_run

    def plan_with_weather(messages):
        result = original(messages)
        # Inject a weather skill request into the action response
        result["skill_requests"] = [
            {"skill_id": "weather.current", "payload": {"location": "current"}}
        ]
        return result

    provider.complete_json = plan_with_weather
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "今天适合出门吗"},
        }
    )

    assert "weather.current" in skill_called
    assert "weather.current" in response.runtime.get("skills_used", [])


def test_llm_planned_device_info_executes():
    """LLM skill plan with device.info must actually run."""
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    original = provider.complete_json

    skill_called = {}
    original_run = app.state.registry.run_skill

    def track_run(skill_id, payload):
        skill_called[skill_id] = payload
        return original_run(skill_id, payload)

    app.state.registry.run_skill = track_run

    def plan_with_device(messages):
        result = original(messages)
        result["skill_requests"] = [
            {"skill_id": "device.info", "payload": {}}
        ]
        return result

    provider.complete_json = plan_with_device
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "电量多少"},
        }
    )

    assert "device.info" in skill_called
    assert "device.info" in response.runtime.get("skills_used", [])


def test_unknown_skill_id_filtered_by_guard():
    """Unknown skill_id must be filtered out, not crash."""
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    original = provider.complete_json

    skill_called = {}
    original_run = app.state.registry.run_skill

    def track_run(skill_id, payload):
        skill_called[skill_id] = payload
        return original_run(skill_id, payload)

    app.state.registry.run_skill = track_run

    def plan_with_unknown(messages):
        result = original(messages)
        result["skill_requests"] = [
            {"skill_id": "nonexistent.skill", "payload": {}}
        ]
        return result

    provider.complete_json = plan_with_unknown
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "帮我查个东西"},
        }
    )

    assert "nonexistent.skill" not in skill_called
    # Should not crash, and no unknown skill in used list
    assert "nonexistent.skill" not in response.runtime.get("skills_used", [])
