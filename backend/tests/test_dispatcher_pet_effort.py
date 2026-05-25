import json

from app.main import create_app


def _dispatch_with_effort(effort: str):
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    original = provider.complete_json

    def patched(messages):
        result = original(messages)
        result["state_affect"] = {
            "interaction_tone": "neutral",
            "pet_effort": effort,
            "emotional_effect": "uncertain",
            "reason": "test",
        }
        return result

    provider.complete_json = patched
    # Use thinking_mode=True to exercise full PetAction path with effort/state_delta
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "你好", "thinking_mode": True},
        }
    )
    return response, app


def test_low_effort_no_fatigue():
    response, _ = _dispatch_with_effort("none")
    assert response.pet_state["energy"] >= 0


def test_medium_effort_reduces_energy():
    response_before, _ = _dispatch_with_effort("none")
    response_after, _ = _dispatch_with_effort("medium")
    assert response_after.pet_state["energy"] <= response_before.pet_state["energy"]


def test_high_effort_text_message_lowers_energy():
    response_before, _ = _dispatch_with_effort("none")
    response_after, _ = _dispatch_with_effort("high")
    assert response_after.pet_state["energy"] < response_before.pet_state["energy"]
    assert response_after.pet_state["sleepiness"] >= response_before.pet_state["sleepiness"]


def test_high_effort_overrides_positive_energy_delta():
    """Even if LLM outputs energy=+8, pet_effort=high must guarantee net decrease."""
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    original = provider.complete_json

    def patched(messages):
        result = original(messages)
        result["state_delta"]["energy"] = 8  # LLM tries to boost energy
        result["state_affect"] = {
            "interaction_tone": "neutral",
            "pet_effort": "high",
            "emotional_effect": "uncertain",
            "reason": "长任务",
        }
        return result

    provider.complete_json = patched

    # Get baseline energy
    baseline, _ = _dispatch_with_effort("none")
    baseline_energy = baseline.pet_state["energy"]

    # Dispatch with high effort + positive energy delta
    provider.complete_json = patched
    response = app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "帮我写代码", "thinking_mode": True},
        }
    )
    # Energy must be lower than baseline despite LLM's +8
    assert response.pet_state["energy"] < baseline_energy


def test_event_log_stores_state_affect():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    original = provider.complete_json

    def patched(messages):
        result = original(messages)
        result["state_affect"] = {
            "interaction_tone": "affectionate",
            "pet_effort": "medium",
            "emotional_effect": "happy",
            "reason": "用户在和豆豆玩",
        }
        return result

    provider.complete_json = patched
    app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "你好", "thinking_mode": True},
        }
    )

    recent = app.state.event_log_store.recent_events(limit=1)
    assert len(recent) >= 1
    last = recent[0]
    assert last["state_affect"]["pet_effort"] == "medium"
    assert last["state_affect"]["interaction_tone"] == "affectionate"


def test_event_log_stores_state_before_after():
    app = create_app(testing=True)

    app.state.dispatcher.handle_event(
        {
            "type": "text_message",
            "source": "runtime",
            "payload": {"user_text": "你好"},
        }
    )

    # state_before and state_after are stored in DB but not returned by recent_events()
    # Verify by querying the raw_event_log table directly
    conn = app.state.state_store.connection
    with conn.locked():
        rows = conn.execute(
            "SELECT state_before_json, state_after_json FROM raw_event_log ORDER BY id DESC LIMIT 1"
        ).fetchall()
    assert len(rows) >= 1
    row = rows[0]
    state_before = json.loads(row["state_before_json"])
    state_after = json.loads(row["state_after_json"])
    assert isinstance(state_before, dict)
    assert isinstance(state_after, dict)
    assert "energy" in state_before
    assert "energy" in state_after
