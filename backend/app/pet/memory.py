from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List

from app.runtime.actions import MemoryUpdate


SENSITIVE_MARKERS = {
    "身份证",
    "银行卡",
    "密码",
    "api key",
    "token",
    "密钥",
    "住址",
}


def infer_memory_type(content: str) -> str:
    lowered = content.lower()
    if "喜欢" in content or "不喜欢" in content or "偏好" in content:
        return "user_preference"
    if "累" in content or "烦" in content or "难过" in content or "开心" in content:
        return "recent_mood"
    if "明天" in content or "面试" in content or "项目" in content:
        return "important_event"
    if "经常" in content or "习惯" in content:
        return "habit"
    if "叫我" in content or "称呼" in content or "william" in lowered:
        return "relationship"
    return "important_event"


class MemoryStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                )
                """
            )
            self.connection.commit()

    def save_from_update(self, update: MemoryUpdate) -> bool:
        if not update.should_save:
            return False
        content = str(update.content or "").strip()
        if not self._is_allowed(content):
            return False
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            self.connection.execute(
                """
                INSERT INTO memory (type, content, importance, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (infer_memory_type(content), content, 3, now, None),
            )
            self.connection.commit()
        return True

    def recent_memory(self, limit: int = 6) -> List[str]:
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT id, content FROM memory
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            now = datetime.utcnow().isoformat()
            ids = [row["id"] for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                self.connection.execute(
                    "UPDATE memory SET last_used_at = ? WHERE id IN (%s)" % placeholders,
                    (now, *ids),
                )
                self.connection.commit()
        return [str(row["content"]) for row in rows]

    def _is_allowed(self, content: str) -> bool:
        if not content:
            return False
        if len(content) > 60:
            return False
        lowered = content.lower()
        return not any(marker in lowered for marker in SENSITIVE_MARKERS)


class InteractionLogStore:
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
