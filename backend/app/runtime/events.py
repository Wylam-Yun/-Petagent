from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.runtime.interaction_catalog import all_event_ids


_INTERACTION_EVENTS = set(all_event_ids())
_SYSTEM_EVENTS = {
    "voice_message",
    "text_message",
    "wake_phrase",
    "exit_phrase",
    "context_refresh",
    "morning",
    "night",
    "long_idle",
    "battery_low",
    "charging_started",
    "charging_stopped",
    "sleepy_time",
    "user_return",
}
ALLOWED_EVENTS = _INTERACTION_EVENTS | _SYSTEM_EVENTS


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
