from app.db import create_state_store
from app.config import load_settings
from app.pet.guard import guard_action
from app.runtime.actions import PetAction, PetResponse, StateAffect
from app.runtime.context_store import EventLogStore


def test_pet_action_accepts_state_affect():
    action = PetAction(
        reply="嘿嘿，被夸到了。",
        mood="happy",
        face_type="happy",
        animation="bounce",
        vibration="light",
        state_affect=StateAffect(
            interaction_tone="affectionate",
            pet_effort="low",
            emotional_effect="encouraged",
            reason="用户夸了 Momo。",
        ),
    )

    assert action.state_affect.interaction_tone == "affectionate"
    assert action.state_affect.pet_effort == "low"
    assert action.state_affect.emotional_effect == "encouraged"


def test_guard_sanitizes_invalid_state_affect():
    action = guard_action(
        {
            "reply": "Momo 有点懵。",
            "mood": "idle",
            "state_affect": {
                "interaction_tone": "bad-tone",
                "pet_effort": "huge",
                "emotional_effect": "chaos",
                "reason": "x" * 260,
            },
        }
    )

    assert action.state_affect.interaction_tone == "neutral"
    assert action.state_affect.pet_effort == "none"
    assert action.state_affect.emotional_effect == "uncertain"
    assert len(action.state_affect.reason) <= 120


def test_guard_keeps_valid_state_affect():
    action = guard_action(
        {
            "reply": "Momo 被你鼓励到啦。",
            "mood": "happy",
            "state_affect": {
                "interaction_tone": "encouraging",
                "pet_effort": "low",
                "emotional_effect": "encouraged",
                "reason": "用户鼓励了 Momo。",
            },
        }
    )

    assert action.state_affect.interaction_tone == "encouraging"
    assert action.state_affect.pet_effort == "low"
    assert action.state_affect.emotional_effect == "encouraged"


def test_pet_response_can_expose_state_affect():
    response = PetResponse(
        reply="嘿嘿。",
        mood="happy",
        face_type="happy",
        animation="bounce",
        vibration="light",
        pet_state={"name": "Momo"},
        runtime={"event_id": "evt-test", "skills_used": []},
        state_affect={
            "interaction_tone": "affectionate",
            "pet_effort": "low",
            "emotional_effect": "happy",
            "reason": "用户摸了摸 Momo。",
        },
    )

    assert response.state_affect["interaction_tone"] == "affectionate"


def test_event_log_records_state_affect_json(tmp_path, monkeypatch):
    monkeypatch.setenv("PETAGENT_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    state_store = create_state_store(settings, testing=True)
    store = EventLogStore(state_store.connection)

    store.record(
        event_id="evt-affect",
        episode_id="ep-affect",
        event_type="praise_momo",
        source="runtime",
        user_text="夸夸",
        pet_reply="嘿嘿。",
        state_before={"energy": 70},
        state_after={"energy": 71},
        mood_after="happy",
        state_affect={
            "interaction_tone": "affectionate",
            "pet_effort": "low",
            "emotional_effect": "encouraged",
            "reason": "用户夸了 Momo。",
        },
    )

    rows = store.recent_events("ep-affect", limit=1)
    assert rows[0]["state_affect"]["interaction_tone"] == "affectionate"
