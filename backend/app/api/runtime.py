from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/runtime")


@router.get("/health")
def runtime_health(request: Request):
    settings = request.app.state.settings
    return {"ok": True, "runtime": settings.runtime_name, "pet": settings.pet_name}


@router.get("/skills")
def runtime_skills(request: Request):
    return {"skills": request.app.state.registry.list_skills()}
