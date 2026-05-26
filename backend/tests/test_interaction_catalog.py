from app.runtime.interaction_catalog import (
    INTERACTION_CATALOG,
    InteractionDef,
    all_event_ids,
    button_event_ids,
    event_animation_map,
    event_description_map,
    event_ids_by_group,
    event_label_map,
    get_interaction,
)

# Expected button events (excluding debug)
BUTTON_EVENT_IDS = {
    "pet_head", "poke_face", "hug", "pet_pat", "praise_momo", "feed_momo",
    "tuck_in", "clean_face", "stay_with_me", "comfort_me", "encourage_me",
    "listen_to_me", "quiet_company", "take_a_break",
}

DEBUG_EVENT_IDS = {"debug_happy", "debug_sleepy", "debug_angry"}


def test_all_button_events_in_catalog():
    for eid in BUTTON_EVENT_IDS:
        assert eid in INTERACTION_CATALOG, f"{eid} missing from catalog"


def test_catalog_event_ids_match_whitelist():
    from app.runtime.events import ALLOWED_EVENTS

    for eid in all_event_ids():
        assert eid in ALLOWED_EVENTS, f"catalog event {eid} not in ALLOWED_EVENTS"


def test_get_interaction_returns_def():
    result = get_interaction("feed_momo")
    assert result is not None
    assert isinstance(result, InteractionDef)
    assert result.event_id == "feed_momo"
    assert result.label == "投喂"
    assert result.group == "pet_care"
    assert result.default_mood == "happy"
    assert result.default_animation == "bounce"


def test_get_interaction_unknown_returns_none():
    assert get_interaction("nonexistent_event") is None


def test_button_event_ids_excludes_debug():
    ids = button_event_ids()
    for eid in DEBUG_EVENT_IDS:
        assert eid not in ids
    for eid in BUTTON_EVENT_IDS:
        assert eid in ids


def test_event_animation_map_complete():
    amap = event_animation_map()
    for eid in BUTTON_EVENT_IDS:
        assert eid in amap
        assert amap[eid] in {
            "breathing", "bounce", "droop", "slowBlink", "shake",
            "wiggle", "blink", "tilt", "jump", "small",
        }


def test_event_ids_by_group():
    pet_care = event_ids_by_group("pet_care")
    companion = event_ids_by_group("emotional_companion")
    debug = event_ids_by_group("debug")
    assert "feed_momo" in pet_care
    assert "comfort_me" in companion
    assert "debug_happy" in debug
    assert len(pet_care) + len(companion) + len(debug) == len(INTERACTION_CATALOG)


def test_event_label_map_keys():
    lmap = event_label_map()
    for eid in BUTTON_EVENT_IDS:
        assert eid in lmap
        assert isinstance(lmap[eid], str)
        assert len(lmap[eid]) > 0


def test_event_description_map_keys():
    dmap = event_description_map()
    for eid in BUTTON_EVENT_IDS:
        assert eid in dmap
        assert isinstance(dmap[eid], str)
        assert len(dmap[eid]) > 0


def test_state_semantics_are_dicts():
    for defn in INTERACTION_CATALOG.values():
        assert isinstance(defn.state_semantics, dict)
        for key in defn.state_semantics:
            assert key in {
                "energy", "intimacy", "hunger", "cleanliness",
                "loneliness", "sleepiness",
            }
            assert defn.state_semantics[key] in {"up", "down"}


def test_prompt_injects_button_semantics():
    from app.config import load_settings
    from app.pet.prompt_builder import build_pet_messages
    from app.runtime.context import build_runtime_context
    from app.runtime.events import PetEvent

    settings = load_settings()
    event = PetEvent(type="feed_momo", source="runtime")
    context = build_runtime_context(
        event=event,
        pet_state={"mood": "idle", "energy": 50},
        cognition_context={"context_profile": "fast_reply"},
    )
    messages = build_pet_messages(settings, event, context)
    system_content = messages[0]["content"]
    assert "当前按钮语义" in system_content
    assert "投喂" in system_content


def test_text_event_no_button_semantics():
    from app.config import load_settings
    from app.pet.prompt_builder import build_pet_messages
    from app.runtime.context import build_runtime_context
    from app.runtime.events import PetEvent

    settings = load_settings()
    event = PetEvent(type="text_message", source="runtime")
    context = build_runtime_context(
        event=event,
        pet_state={"mood": "idle", "energy": 50},
        cognition_context={"context_profile": "fast_reply"},
    )
    messages = build_pet_messages(settings, event, context)
    system_content = messages[0]["content"]
    assert "当前按钮语义" not in system_content


def test_all_catalog_entries_have_valid_mood():
    from app.runtime.actions import ALLOWED_MOODS

    for defn in INTERACTION_CATALOG.values():
        assert defn.default_mood in ALLOWED_MOODS, (
            f"{defn.event_id} has invalid mood {defn.default_mood}"
        )


def test_all_catalog_entries_have_valid_animation():
    from app.runtime.actions import ALLOWED_ANIMATIONS

    for defn in INTERACTION_CATALOG.values():
        assert defn.default_animation in ALLOWED_ANIMATIONS, (
            f"{defn.event_id} has invalid animation {defn.default_animation}"
        )


def test_post_pet_event_simplified_payload():
    """Frontend sends {event, payload: {}} — backend must handle it."""
    from app.runtime.events import normalize_event

    for eid in button_event_ids():
        event = normalize_event({"event": eid, "payload": {}})
        assert event.type == eid
        assert event.source == "runtime"


def test_state_semantics_match_event_deltas():
    """Catalog state_semantics direction must agree with EVENT_DELTAS sign."""
    from app.pet.rules import EVENT_DELTAS

    for defn in INTERACTION_CATALOG.values():
        if defn.group == "debug":
            continue
        delta = EVENT_DELTAS.get(defn.event_id, {})
        for key, direction in defn.state_semantics.items():
            delta_val = delta.get(key, 0)
            if direction == "up":
                assert delta_val >= 0, (
                    f"{defn.event_id} semantics say {key}=up but delta is {delta_val}"
                )
            elif direction == "down":
                assert delta_val <= 0, (
                    f"{defn.event_id} semantics say {key}=down but delta is {delta_val}"
                )


def test_api_interactions_endpoint():
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app(testing=True))
    response = client.get("/api/interactions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 15  # 15 button events, no debug
    event_ids = {item["event_id"] for item in data}
    assert "feed_momo" in event_ids
    assert "debug_happy" not in event_ids
    # Each item has required fields
    for item in data:
        assert "label" in item
        assert "group" in item
        assert "default_mood" in item
        assert "default_animation" in item
        assert "state_semantics" in item
        assert item["requires_model"] is False


def test_catalog_interactions_default_to_local_only():
    for item in INTERACTION_CATALOG.values():
        if item.group == "debug":
            continue
        assert item.requires_model is False
