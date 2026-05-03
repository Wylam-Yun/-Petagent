from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/pet")


@router.get("/state")
def get_pet_state(request: Request):
    return request.app.state.state_store.get_state()


@router.post("/event")
def post_pet_event(payload: Dict[str, Any], request: Request):
    return request.app.state.dispatcher.handle_event(payload).dict()
