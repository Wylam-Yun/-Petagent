from app.pet.rules import apply_event_rules, clamp_state


def test_clamp_state_keeps_numbers_between_zero_and_hundred():
    state = {
        "energy": 150,
        "intimacy": -4,
        "hunger": 20,
        "cleanliness": 80,
        "loneliness": 200,
        "sleepiness": -30,
    }

    clamped = clamp_state(state)

    assert clamped["energy"] == 100
    assert clamped["intimacy"] == 0
    assert clamped["loneliness"] == 100
    assert clamped["sleepiness"] == 0


def test_pet_head_increases_intimacy_and_reduces_loneliness():
    state = {
        "mood": "idle",
        "energy": 70,
        "intimacy": 40,
        "hunger": 30,
        "cleanliness": 80,
        "loneliness": 50,
        "sleepiness": 20,
    }

    updated = apply_event_rules(state, "pet_head")

    assert updated["mood"] == "shy"
    assert updated["intimacy"] == 42
    assert updated["loneliness"] == 45
