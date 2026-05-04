from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel

from app.config import Settings


def normalize_pet_name(text: str) -> str:
    normalized = str(text).strip().lower()
    for alias in ("默默", "摸摸"):
        normalized = normalized.replace(alias, "momo")
    return normalized


def normalize_activation_phrase(text: str) -> str:
    normalized = normalize_pet_name(text)
    for char in (" ", "\t", "\n", "，", "。", ",", ".", "!", "?", "！", "？", "、"):
        normalized = normalized.replace(char, "")
    return normalized


class ActivationState(BaseModel):
    schema_version: str = "0.1"
    active: bool = False
    session_id: Optional[str] = None
    activated_by: Optional[str] = None
    started_at: Optional[str] = None
    last_active_at: Optional[str] = None


class ActivationManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = ActivationState(schema_version=settings.schema_version)

    def min_confidence(self) -> float:
        raw = self.settings.app_config.get("activation", {}).get(
            "min_wake_confidence", 0.75
        )
        return float(raw)

    def wake_phrases(self) -> list:
        return self.settings.app_config.get("activation", {}).get("wake_phrases", [])

    def exit_phrases(self) -> list:
        return self.settings.app_config.get("activation", {}).get("exit_phrases", [])

    def phrase_matches(self, phrase: str, phrases: list) -> bool:
        normalized = normalize_activation_phrase(phrase)
        return any(
            normalized == normalize_activation_phrase(str(item)) for item in phrases
        )

    def wake(self, phrase: str, confidence: float, source: str) -> ActivationState:
        if confidence < self.min_confidence() or not self.phrase_matches(
            phrase, self.wake_phrases()
        ):
            return self.state.copy(update={"active": False, "session_id": None})
        now = datetime.utcnow().isoformat()
        self.state = ActivationState(
            schema_version=self.settings.schema_version,
            active=True,
            session_id="session-" + uuid4().hex,
            activated_by=source,
            started_at=now,
            last_active_at=now,
        )
        return self.state

    def exit(self, phrase: str, confidence: float) -> ActivationState:
        if confidence >= self.min_confidence() and self.phrase_matches(
            phrase, self.exit_phrases()
        ):
            self.state = self.state.copy(
                update={"active": False, "last_active_at": datetime.utcnow().isoformat()}
            )
        return self.state

    def as_dict(self) -> Dict[str, Any]:
        return self.state.dict()
