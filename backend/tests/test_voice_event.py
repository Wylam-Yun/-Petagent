from app.main import create_app
from app.runtime.events import normalize_event


def test_voice_message_normalizes_as_pet_event():
    event = normalize_event(
        {
            "type": "voice_message",
            "source": "voice",
            "payload": {
                "user_text": "我今天好累",
                "audio_understanding": {
                    "detected_emotion": "tired",
                    "tone_notes": "语气低",
                    "non_verbal": "叹气",
                    "confidence": 0.76,
                },
            },
        }
    )

    assert event.type == "voice_message"
    assert event.source == "voice"
    assert event.payload["user_text"] == "我今天好累"


def test_voice_message_runs_through_runtime_dispatcher():
    app = create_app(testing=True)

    response = app.state.dispatcher.handle_event(
        {
            "type": "voice_message",
            "source": "voice",
            "payload": {
                "user_text": "我今天好累",
                "audio_understanding": {
                    "detected_emotion": "tired",
                    "tone_notes": "语气低",
                    "non_verbal": "叹气",
                    "confidence": 0.76,
                },
            },
        }
    )

    assert response.reply
    assert response.runtime["event_id"]
    assert response.pet_state["schema_version"] == "0.1"
