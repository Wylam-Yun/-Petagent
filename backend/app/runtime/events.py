from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


ALLOWED_EVENTS = {
    "pet_head",
    "poke_face",
    "hug",
    "debug_happy",
    "debug_sleepy",
    "debug_angry",
    "voice_message",
    "wake_phrase",
    "exit_phrase",
    "morning",
    "night",
    "long_idle",
    "battery_low",
    "charging_started",
    "charging_stopped",
    "sleepy_time",
    "user_return",
}


class PetEvent(BaseModel):
    schema_version: str = "0.1"
    id: str = Field(default_factory=lambda: "evt-" + uuid4().hex)
    type: str
    source: str = "runtime"
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


def normalize_event(raw: Dict[str, Any]) -> PetEvent:
    event_type: Optional[str] = raw.get("type") or raw.get("event")
    if not event_type:
        raise ValueError("PetEvent requires type")
    if event_type not in ALLOWED_EVENTS:
        raise ValueError("Unsupported PetEvent type: %s" % event_type)
    payload = raw.get("payload") or {}
    source = raw.get("source") or "runtime"
    return PetEvent(type=event_type, source=source, payload=payload)
