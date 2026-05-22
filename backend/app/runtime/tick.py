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
        with self.connection.locked():
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
        with self.connection.locked():
            self.connection.execute(
                """
                INSERT INTO runtime_meta (key, value) VALUES ('last_tick_at', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (value.isoformat(),),
            )
            self.connection.commit()

    def get_last_tick(self) -> Optional[datetime]:
        with self.connection.locked():
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

        # Logistic/saturating decay: delta = base * (1 - current/100)
        # Decay slows as state nears the edge (e.g. energy=10 → very slow further drop)
        energy = int(state.get("energy", 50))
        hunger = int(state.get("hunger", 50))
        loneliness = int(state.get("loneliness", 50))

        energy_delta = max(1, int(intervals * (1.0 - energy / 100.0) + 0.5))
        hunger_delta = max(1, int(intervals * (1.0 - hunger / 100.0) + 0.5))
        loneliness_delta = max(1, int(intervals * (1.0 - loneliness / 100.0) + 0.5))

        state["energy"] = max(0, energy - energy_delta)
        state["hunger"] = min(100, hunger + hunger_delta)
        state["loneliness"] = min(100, loneliness + loneliness_delta)

        # Night penalty
        if current.hour >= 23 or current.hour <= 6:
            sleepiness = int(state.get("sleepiness", 0))
            sleepiness_delta = max(1, int(3 * intervals * (1.0 - sleepiness / 100.0) + 0.5))
            state["sleepiness"] = min(100, sleepiness + sleepiness_delta)
            state["energy"] = max(0, int(state.get("energy", 0)) - energy_delta)

        # Lonely bonus: extra loneliness if no interaction for > 1h
        if last_interaction and (current - last_interaction).total_seconds() > 3600:
            current_loneliness = int(state.get("loneliness", 0))
            extra = max(1, int(3 * intervals * (1.0 - current_loneliness / 100.0) + 0.5))
            state["loneliness"] = min(100, current_loneliness + extra)

        # Rest while away: if idle > 6h since last interaction and energy < 50, recover energy
        # Uses wall-clock idle since last interaction (not per-tick elapsed)
        if last_interaction:
            idle_since_interaction = (current - last_interaction).total_seconds() / 3600.0
        else:
            idle_since_interaction = elapsed / 3600.0
        if idle_since_interaction > 6 and energy < 50:
            rest_bonus = min(20, idle_since_interaction / 3.0)
            state["energy"] = int(state.get("energy", 0)) + round(rest_bonus)

        # Charging accelerates recovery
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
