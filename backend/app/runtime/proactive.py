from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from app.pet.state import PetStateStore
from app.runtime.device import DeviceStateStore
from app.runtime.events import PetEvent


class ProactiveService:
    def __init__(self, state_store: PetStateStore, device_store: DeviceStateStore) -> None:
        self.state_store = state_store
        self.device_store = device_store
        self.connection: sqlite3.Connection = state_store.connection
        self.initialize()

    def initialize(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS proactive_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                triggered_at TEXT NOT NULL,
                user_responded INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.connection.commit()

    def next_event(self, now: Optional[datetime] = None) -> Optional[PetEvent]:
        current = now or datetime.utcnow()
        if self._triggered_recently(None, current, minutes=30):
            return None
        event_type = self._candidate(current)
        if not event_type:
            return None
        self.record(event_type, current)
        return PetEvent(
            type=event_type,
            source="proactive",
            payload={"description": "Momo 主动陪伴事件", "time": current.isoformat()},
        )

    def record(self, event_type: str, when: Optional[datetime] = None) -> None:
        self.connection.execute(
            """
            INSERT INTO proactive_log (event_type, triggered_at, user_responded)
            VALUES (?, ?, 0)
            """,
            (event_type, (when or datetime.utcnow()).isoformat()),
        )
        self.connection.commit()

    def _candidate(self, now: datetime) -> Optional[str]:
        state = self.state_store.get_state()
        device = self.device_store.get_state()
        if 8 <= now.hour <= 10 and not self._triggered_today("morning", now):
            return "morning"
        if 22 <= now.hour <= 23 and not self._triggered_today("night", now):
            return "night"
        if device.get("battery") is not None and device["battery"] < 20:
            if not self._triggered_recently("battery_low", now, minutes=120):
                return "battery_low"
        if device.get("is_charging") is True and device.get("was_charging") is False:
            if not self._triggered_recently("charging_started", now, minutes=30):
                return "charging_started"
        if device.get("is_charging") is False and device.get("was_charging") is True:
            if not self._triggered_recently("charging_stopped", now, minutes=30):
                return "charging_stopped"
        last_interaction = self._parse_datetime(state.get("last_interaction_at"))
        if last_interaction and now - last_interaction > timedelta(minutes=90):
            if not self._triggered_recently("long_idle", now, minutes=60):
                return "long_idle"
        if now.hour >= 23 or now.hour <= 6:
            if not self._triggered_recently("sleepy_time", now, minutes=120):
                return "sleepy_time"
        return None

    def _triggered_today(self, event_type: str, now: datetime) -> bool:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        row = self.connection.execute(
            """
            SELECT 1 FROM proactive_log
            WHERE event_type = ? AND triggered_at >= ?
            LIMIT 1
            """,
            (event_type, start),
        ).fetchone()
        return row is not None

    def _triggered_recently(
        self, event_type: Optional[str], now: datetime, minutes: int
    ) -> bool:
        since = (now - timedelta(minutes=minutes)).isoformat()
        if event_type is None:
            row = self.connection.execute(
                "SELECT 1 FROM proactive_log WHERE triggered_at >= ? LIMIT 1",
                (since,),
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT 1 FROM proactive_log
                WHERE event_type = ? AND triggered_at >= ?
                LIMIT 1
                """,
                (event_type, since),
            ).fetchone()
        return row is not None

    def _parse_datetime(self, value) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None
