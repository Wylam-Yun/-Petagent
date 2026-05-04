from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


STATE_COLUMNS = [
    "name",
    "mood",
    "energy",
    "intimacy",
    "hunger",
    "cleanliness",
    "loneliness",
    "sleepiness",
    "mode",
    "last_interaction_at",
    "updated_at",
]


class LockedSQLiteConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = threading.RLock()

    @contextmanager
    def locked(self) -> Iterator["LockedSQLiteConnection"]:
        with self._lock:
            yield self

    def execute(self, *args, **kwargs):
        with self._lock:
            return self._connection.execute(*args, **kwargs)

    def commit(self) -> None:
        with self._lock:
            self._connection.commit()

    def cursor(self):
        return self._connection.cursor()

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


def default_state(name: str = "Momo") -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    return {
        "schema_version": "0.1",
        "name": name,
        "mood": "idle",
        "energy": 72,
        "intimacy": 40,
        "hunger": 30,
        "cleanliness": 85,
        "loneliness": 35,
        "sleepiness": 15,
        "mode": "idle",
        "last_interaction_at": now,
        "updated_at": now,
    }


class PetStateStore:
    def __init__(self, db_path: Optional[Path], pet_name: str = "Momo") -> None:
        self.pet_name = pet_name
        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            raw_connection = sqlite3.connect(str(db_path), check_same_thread=False)
        else:
            raw_connection = sqlite3.connect(":memory:", check_same_thread=False)
        raw_connection.row_factory = sqlite3.Row
        raw_connection.execute("PRAGMA busy_timeout = 5000")
        if db_path is not None:
            raw_connection.execute("PRAGMA journal_mode = WAL")
            raw_connection.execute("PRAGMA synchronous = NORMAL")
        self.connection = LockedSQLiteConnection(raw_connection)
        self.initialize()

    def initialize(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    version TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pet_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    name TEXT NOT NULL,
                    mood TEXT NOT NULL,
                    energy INTEGER NOT NULL,
                    intimacy INTEGER NOT NULL,
                    hunger INTEGER NOT NULL,
                    cleanliness INTEGER NOT NULL,
                    loneliness INTEGER NOT NULL,
                    sleepiness INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    last_interaction_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, '0.1')"
            )
            state = default_state(self.pet_name)
            self.connection.execute(
                """
                INSERT OR IGNORE INTO pet_state (
                    id, name, mood, energy, intimacy, hunger, cleanliness,
                    loneliness, sleepiness, mode, last_interaction_at, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(state[column] for column in STATE_COLUMNS),
            )
            self.connection.commit()

    def get_state(self) -> Dict[str, Any]:
        with self.connection.locked():
            row = self.connection.execute("SELECT * FROM pet_state WHERE id = 1").fetchone()
        if row is None:
            state = default_state(self.pet_name)
            self.save_state(state)
            return state
        data = {key: row[key] for key in STATE_COLUMNS}
        data["schema_version"] = "0.1"
        return data

    def save_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        saved = dict(state)
        now = datetime.utcnow().isoformat()
        saved["updated_at"] = now
        saved.setdefault("last_interaction_at", now)
        with self.connection.locked():
            self.connection.execute(
                """
                UPDATE pet_state SET
                    name = ?, mood = ?, energy = ?, intimacy = ?, hunger = ?,
                    cleanliness = ?, loneliness = ?, sleepiness = ?, mode = ?,
                    last_interaction_at = ?, updated_at = ?
                WHERE id = 1
                """,
                tuple(saved[column] for column in STATE_COLUMNS),
            )
            self.connection.commit()
        saved["schema_version"] = "0.1"
        return saved
