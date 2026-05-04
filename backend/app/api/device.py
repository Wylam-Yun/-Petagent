from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/device")


class DeviceStateRequest(BaseModel):
    battery: Optional[int] = None
    is_charging: Optional[bool] = None


@router.post("/state")
def post_device_state(payload: DeviceStateRequest, request: Request):
    state = request.app.state.device_store.save_state(
        battery=payload.battery,
        is_charging=payload.is_charging,
    )
    return state


@router.get("/state")
def get_device_state(request: Request):
    return request.app.state.device_store.get_state()
