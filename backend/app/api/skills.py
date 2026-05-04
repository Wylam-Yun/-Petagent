from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/skills")


@router.get("")
def list_skills(request: Request):
    return {"skills": request.app.state.registry.list_skills()}


@router.post("/{skill_id}/run")
def run_skill(skill_id: str, payload: Dict[str, Any], request: Request):
    registry = request.app.state.registry
    if not registry.has_skill(skill_id):
        raise HTTPException(status_code=404, detail="Unknown skill")
    return registry.run_skill_dict(skill_id, payload)
