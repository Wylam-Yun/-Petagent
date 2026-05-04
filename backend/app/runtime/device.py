from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional


class DeviceStateStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS device_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                battery INTEGER,
                is_charging INTEGER,
                was_charging INTEGER,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def save_state(
        self, battery: Optional[int] = None, is_charging: Optional[bool] = None
    ) -> Dict[str, Any]:
        previous = self.get_state()
        was_charging = previous.get("is_charging")
        clean_battery = None if battery is None else max(0, min(100, int(battery)))
        clean_charging = None if is_charging is None else bool(is_charging)
        now = datetime.utcnow().isoformat()
        self.connection.execute(
            """
            INSERT INTO device_state (id, battery, is_charging, was_charging, updated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                battery = excluded.battery,
                is_charging = excluded.is_charging,
                was_charging = excluded.was_charging,
                updated_at = excluded.updated_at
            """,
            (
                clean_battery,
                None if clean_charging is None else int(clean_charging),
                None if was_charging is None else int(bool(was_charging)),
                now,
            ),
        )
        self.connection.commit()
        return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        row = self.connection.execute(
            "SELECT battery, is_charging, was_charging, updated_at FROM device_state WHERE id = 1"
        ).fetchone()
        if row is None:
            return {
                "battery": None,
                "is_charging": None,
                "was_charging": None,
                "updated_at": None,
            }
        return {
            "battery": row["battery"],
            "is_charging": None if row["is_charging"] is None else bool(row["is_charging"]),
            "was_charging": None if row["was_charging"] is None else bool(row["was_charging"]),
            "updated_at": row["updated_at"],
        }
