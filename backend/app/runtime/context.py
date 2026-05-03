from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.runtime.events import PetEvent


class RuntimeContext(BaseModel):
    schema_version: str = "0.1"
    event: Dict[str, Any]
    pet_state: Dict[str, Any]
    recent_memory: List[str] = Field(default_factory=list)
    recent_dialogue: List[Dict[str, str]] = Field(default_factory=list)
    skill_results: List[Dict[str, Any]] = Field(default_factory=list)


def build_runtime_context(event: PetEvent, pet_state: Dict[str, Any]) -> RuntimeContext:
    return RuntimeContext(event=event.dict(), pet_state=pet_state)
