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


def _base_state(**overrides):
    state = {
        "mood": "idle",
        "energy": 50,
        "intimacy": 40,
        "hunger": 50,
        "cleanliness": 80,
        "loneliness": 50,
        "sleepiness": 20,
    }
    state.update(overrides)
    return state


def test_feed_momo_reduces_hunger_significantly():
    updated = apply_event_rules(_base_state(), "feed_momo")
    assert updated["hunger"] <= 40  # 50 - 10


def test_feed_momo_restores_energy():
    updated = apply_event_rules(_base_state(), "feed_momo")
    assert updated["energy"] >= 58  # 50 + 8


def test_tuck_in_raises_sleepiness():
    updated = apply_event_rules(_base_state(), "tuck_in")
    assert updated["sleepiness"] >= 30  # 20 + 10


def test_hug_strongest_loneliness_reduction():
    updated = apply_event_rules(_base_state(), "hug")
    assert updated["loneliness"] <= 40  # 50 - 10


def test_clean_face_significant_cleanliness_boost():
    updated = apply_event_rules(_base_state(), "clean_face")
    assert updated["cleanliness"] >= 90  # 80 + 10


def test_encourage_me_costs_energy():
    updated = apply_event_rules(_base_state(), "encourage_me")
    assert updated["energy"] < 50  # 50 - 2


def test_encourage_me_raises_intimacy():
    updated = apply_event_rules(_base_state(), "encourage_me")
    assert updated["intimacy"] > 40  # 40 + 2
