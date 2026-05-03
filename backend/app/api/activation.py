from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/activation")


class ActivationRequest(BaseModel):
    phrase: str = ""
    confidence: float = 0.0
    source: str = "foreground_voice"


def _activation_response(
    *, active: bool, session_id: str, runtime_response: Any
) -> Dict[str, Any]:
    body = runtime_response.dict()
    return {
        "schema_version": body.get("schema_version", "0.1"),
        "active": active,
        "session_id": session_id,
        "reply": body["reply"],
        "mood": body["mood"],
        "face_type": body["face_type"],
        "animation": body["animation"],
        "vibration": body["vibration"],
        "voice_url": body["voice_url"],
        "pet_state": body["pet_state"],
        "runtime": body["runtime"],
    }


@router.post("/wake")
def post_activation_wake(payload: ActivationRequest, request: Request):
    state = request.app.state.activation_manager.wake(
        payload.phrase, payload.confidence, payload.source
    )
    if not state.active:
        return {
            "schema_version": request.app.state.settings.schema_version,
            "active": False,
            "session_id": None,
            "reply": "唔，Momo 好像没听清。",
            "mood": "concerned",
            "face_type": "concerned",
            "animation": "tilt",
            "vibration": "none",
            "voice_url": None,
            "pet_state": request.app.state.state_store.get_state(),
            "runtime": {"event_id": None, "skills_used": []},
        }
    runtime_response = request.app.state.dispatcher.handle_event(
        {
            "type": "wake_phrase",
            "source": payload.source,
            "payload": {"phrase": payload.phrase, "confidence": payload.confidence},
        }
    )
    return _activation_response(
        active=True, session_id=state.session_id or "", runtime_response=runtime_response
    )


@router.post("/exit")
def post_activation_exit(payload: ActivationRequest, request: Request):
    state = request.app.state.activation_manager.exit(payload.phrase, payload.confidence)
    runtime_response = request.app.state.dispatcher.handle_event(
        {
            "type": "exit_phrase",
            "source": payload.source,
            "payload": {"phrase": payload.phrase, "confidence": payload.confidence},
        }
    )
    return _activation_response(
        active=state.active,
        session_id=state.session_id or "",
        runtime_response=runtime_response,
    )
