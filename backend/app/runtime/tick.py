from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional

from app.pet.rules import clamp_state
from app.pet.state import PetStateStore
from app.runtime.device import DeviceStateStore


class TickService:
    def __init__(
        self,
        state_store: PetStateStore,
        device_store: DeviceStateStore,
        interval_seconds: int = 300,
    ) -> None:
        self.state_store = state_store
        self.device_store = device_store
        self.interval_seconds = interval_seconds
        self.connection: sqlite3.Connection = state_store.connection
        self.initialize()

    def initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def set_last_tick(self, value: datetime) -> None:
        self.connection.execute(
            """
            INSERT INTO runtime_meta (key, value) VALUES ('last_tick_at', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (value.isoformat(),),
        )
        self.connection.commit()

    def get_last_tick(self) -> Optional[datetime]:
        row = self.connection.execute(
            "SELECT value FROM runtime_meta WHERE key = 'last_tick_at'"
        ).fetchone()
        if row is None:
            return None
        try:
            return datetime.fromisoformat(row["value"])
        except ValueError:
            return None

    def apply_if_due(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        current = now or datetime.utcnow()
        last_tick = self.get_last_tick()
        if last_tick is None:
            self.set_last_tick(current)
            return self.state_store.get_state()
        elapsed = int((current - last_tick).total_seconds())
        if elapsed < self.interval_seconds:
            return self.state_store.get_state()
        intervals = max(1, min(12, elapsed // self.interval_seconds))
        state = self.state_store.get_state()
        device = self.device_store.get_state()
        last_interaction = self._parse_datetime(state.get("last_interaction_at"))

        state["energy"] = int(state.get("energy", 0)) - intervals
        state["hunger"] = int(state.get("hunger", 0)) + intervals
        state["loneliness"] = int(state.get("loneliness", 0)) + intervals
        if current.hour >= 23 or current.hour <= 6:
            state["sleepiness"] = int(state.get("sleepiness", 0)) + 3 * intervals
            state["energy"] = int(state.get("energy", 0)) - intervals
        if last_interaction and (current - last_interaction).total_seconds() > 3600:
            state["loneliness"] = int(state.get("loneliness", 0)) + 5 * intervals
        if device.get("is_charging") is True:
            state["energy"] = int(state.get("energy", 0)) + 2 * intervals
            state["hunger"] = int(state.get("hunger", 0)) - 3 * intervals

        saved = self.state_store.save_state(clamp_state(state))
        self.set_last_tick(current)
        return saved

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None
