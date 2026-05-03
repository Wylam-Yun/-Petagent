import pytest

from app.runtime.events import PetEvent, normalize_event


def test_pet_event_requires_type():
    with pytest.raises(ValueError):
        normalize_event({"payload": {"description": "missing type"}})


def test_pet_head_event_normalizes_to_schema_versioned_event():
    event = normalize_event(
        {"event": "pet_head", "payload": {"description": "用户摸了你的头"}}
    )

    assert isinstance(event, PetEvent)
    assert event.schema_version == "0.1"
    assert event.type == "pet_head"
    assert event.payload["description"] == "用户摸了你的头"
