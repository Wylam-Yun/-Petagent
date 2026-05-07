from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List

# DEPRECATED: SENSITIVE_MARKERS and infer_memory_type moved to app.runtime.memory_policy
# Import from there instead. Kept here for backward compatibility.
from app.runtime.memory_policy import SENSITIVE_MARKERS, infer_memory_type  # noqa: F401


class InteractionLogStore:
    """DEPRECATED: kept for /api/runtime/reset and Stage 3 tests.

    The new EventLogStore (app.runtime.context_store) is the primary event logger.
    This store is only used by the reset API to clear interaction_log table.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS interaction_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    user_text TEXT,
                    pet_reply TEXT NOT NULL,
                    mood TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self.connection.commit()

    def record(
        self, event_type: str, pet_reply: str, mood: str, user_text: str = ""
    ) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                INSERT INTO interaction_log (event_type, user_text, pet_reply, mood, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    user_text or None,
                    pet_reply,
                    mood,
                    datetime.utcnow().isoformat(),
                ),
            )
            self.connection.commit()

    def recent_dialogue(self, limit: int = 3) -> List[Dict[str, Any]]:
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT event_type, user_text, pet_reply, mood
                FROM interaction_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "user": row["user_text"] or "",
                "pet": row["pet_reply"],
                "mood": row["mood"],
            }
            for row in rows
        ]
