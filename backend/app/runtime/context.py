from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.runtime.events import PetEvent


class RuntimeContext(BaseModel):
    schema_version: str = "0.2"
    event: Dict[str, Any]
    pet_state: Dict[str, Any]
    recent_memory: List[str] = Field(default_factory=list)
    recent_dialogue: List[Dict[str, str]] = Field(default_factory=list)
    device_state: Dict[str, Any] = Field(default_factory=dict)
    skill_results: List[Dict[str, Any]] = Field(default_factory=list)
    cognition_context: Dict[str, Any] = Field(default_factory=dict)


def build_runtime_context(
    event: PetEvent,
    pet_state: Dict[str, Any],
    recent_memory: Optional[List[str]] = None,
    recent_dialogue: Optional[List[Dict[str, str]]] = None,
    device_state: Optional[Dict[str, Any]] = None,
    skill_results: Optional[List[Dict[str, Any]]] = None,
    cognition_context: Optional[Dict[str, Any]] = None,
) -> RuntimeContext:
    return RuntimeContext(
        event=event.dict(),
        pet_state=pet_state,
        recent_memory=recent_memory or [],
        recent_dialogue=recent_dialogue or [],
        device_state=device_state or {},
        skill_results=skill_results or [],
        cognition_context=cognition_context or {},
    )
