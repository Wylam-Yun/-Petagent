from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/pet")


@router.get("/state")
def get_pet_state(request: Request):
    return request.app.state.state_store.get_state()


@router.post("/session/resume")
def post_session_resume(request: Request):
    request.app.state.tick_service.apply_if_due()
    return request.app.state.state_store.get_state()


@router.post("/event")
def post_pet_event(payload: Dict[str, Any], request: Request):
    return request.app.state.dispatcher.handle_event(payload).dict()


def _proactive_mode(request: Request, requested: str = "") -> str:
    configured = (
        request.app.state.settings.app_config.get("proactive", {}).get("mode", "low_cost")
    )
    mode = (requested or configured or "low_cost").strip().lower()
    return mode if mode in {"low_cost", "llm"} else "low_cost"


@router.get("/proactive")
def get_pet_proactive(request: Request):
    """Read-only check for pending proactive event. No side effects."""
    event = request.app.state.proactive_service.check_candidate()
    if event is None:
        return {"active": False}
    return {"active": True, "candidate": event.type}


@router.post("/proactive/trigger")
def trigger_pet_proactive(request: Request, mode: str = ""):
    """Trigger a proactive event (records + dispatches)."""
    request.app.state.tick_service.apply_if_due()
    event = request.app.state.proactive_service.next_event()
    if event is None:
        return {"active": False}
    selected_mode = _proactive_mode(request, mode)
    proactive_config = request.app.state.settings.app_config.get("proactive", {})
    synthesize_voice = bool(proactive_config.get("synthesize_voice", False))
    response = request.app.state.dispatcher.handle_event(
        event.dict(),
        brain=(
            request.app.state.proactive_brain
            if selected_mode == "low_cost"
            else request.app.state.dispatcher.brain
        ),
        synthesize_voice=synthesize_voice if selected_mode == "llm" else False,
    ).dict()
    response["active"] = True
    response["runtime"]["proactive_mode"] = selected_mode
    return response
