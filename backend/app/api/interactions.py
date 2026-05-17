from __future__ import annotations

from fastapi import APIRouter

from app.runtime.interaction_catalog import INTERACTION_CATALOG

router = APIRouter(prefix="/api/interactions")


@router.get("")
def list_interactions():
    return [
        {
            "event_id": d.event_id,
            "label": d.label,
            "group": d.group,
            "default_mood": d.default_mood,
            "default_animation": d.default_animation,
            "state_semantics": d.state_semantics,
        }
        for d in INTERACTION_CATALOG.values()
        if d.group != "debug"
    ]
