import pytest
from pydantic import ValidationError

from app.runtime.actions import PetAction, PetResponse


def test_pet_action_requires_reply():
    with pytest.raises(ValidationError):
        PetAction(mood="happy", face_type="happy", animation="bounce")


def test_pet_response_has_runtime_metadata():
    response = PetResponse(
        reply="嘿嘿，豆豆在呢。",
        mood="happy",
        face_type="happy",
        animation="bounce",
        vibration="light",
        pet_state={"name": "豆豆"},
        runtime={"event_id": "evt-test", "skills_used": []},
    )

    assert response.schema_version == "0.1"
    assert response.voice_url is None
    assert response.runtime["skills_used"] == []
