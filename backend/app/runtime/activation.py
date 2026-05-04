from __future__ import annotations

import sqlite3
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
    ended_at: Optional[str] = None


class ActivationManager:
    def __init__(self, settings: Settings, connection: Optional[sqlite3.Connection] = None) -> None:
        self.settings = settings
        self.connection = connection
        self.state = ActivationState(schema_version=settings.schema_version)
        if self.connection is not None:
            self.initialize()
            self.state = self.load_active_state()

    def initialize(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activation_session (
                    session_id TEXT PRIMARY KEY,
                    active INTEGER NOT NULL,
                    activated_by TEXT,
                    started_at TEXT NOT NULL,
                    last_active_at TEXT,
                    ended_at TEXT
                )
                """
            )
            self.connection.commit()

    def load_active_state(self) -> ActivationState:
        if self.connection is None:
            return self.state
        with self.connection.locked():
            row = self.connection.execute(
                """
                SELECT session_id, active, activated_by, started_at, last_active_at, ended_at
                FROM activation_session
                WHERE active = 1
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return ActivationState(schema_version=self.settings.schema_version)
        return ActivationState(
            schema_version=self.settings.schema_version,
            active=bool(row["active"]),
            session_id=row["session_id"],
            activated_by=row["activated_by"],
            started_at=row["started_at"],
            last_active_at=row["last_active_at"],
            ended_at=row["ended_at"],
        )

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
        self.persist_state()
        return self.state

    def exit(self, phrase: str, confidence: float) -> ActivationState:
        if confidence >= self.min_confidence() and self.phrase_matches(
            phrase, self.exit_phrases()
        ):
            now = datetime.utcnow().isoformat()
            self.state = self.state.copy(
                update={"active": False, "last_active_at": now, "ended_at": now}
            )
            self.persist_state()
        return self.state

    def as_dict(self) -> Dict[str, Any]:
        return self.state.dict()

    def persist_state(self) -> None:
        if self.connection is None or not self.state.session_id:
            return
        with self.connection.locked():
            self.connection.execute(
                """
                INSERT INTO activation_session (
                    session_id, active, activated_by, started_at, last_active_at, ended_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    active = excluded.active,
                    activated_by = excluded.activated_by,
                    started_at = excluded.started_at,
                    last_active_at = excluded.last_active_at,
                    ended_at = excluded.ended_at
                """,
                (
                    self.state.session_id,
                    int(self.state.active),
                    self.state.activated_by,
                    self.state.started_at or datetime.utcnow().isoformat(),
                    self.state.last_active_at,
                    self.state.ended_at,
                ),
            )
            self.connection.commit()
