from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/pet")


@router.get("/state")
def get_pet_state(request: Request):
    request.app.state.tick_service.apply_if_due()
    return request.app.state.state_store.get_state()


@router.post("/event")
def post_pet_event(payload: Dict[str, Any], request: Request):
    return request.app.state.dispatcher.handle_event(payload).dict()


@router.get("/proactive")
def get_pet_proactive(request: Request):
    request.app.state.tick_service.apply_if_due()
    event = request.app.state.proactive_service.next_event()
    if event is None:
        return {"active": False}
    response = request.app.state.dispatcher.handle_event(
        event.dict(),
        brain=request.app.state.proactive_brain,
        synthesize_voice=False,
    ).dict()
    response["active"] = True
    return response
