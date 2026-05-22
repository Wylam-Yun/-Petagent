"""SQLite persistence for runtime incident breadcrumbs (CC-8)."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from app.pet.state import LockedSQLiteConnection

logger = logging.getLogger(__name__)


class IncidentStore:
    """Persists runtime incident breadcrumbs to SQLite.

    Capped at max_rows (default 500). Oldest rows pruned on insert.
    """

    def __init__(
        self,
        connection: "LockedSQLiteConnection",
        max_rows: int = 500,
    ) -> None:
        self.connection = connection
        self.max_rows = max_rows
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_incident (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_incident_ts
                ON runtime_incident(ts)
                """
            )
            self.connection.commit()

    def record(self, kind: str, payload: Dict[str, Any]) -> None:
        """Insert an incident breadcrumb, then prune oldest if over cap."""
        now = datetime.utcnow().isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)[:2000]
        try:
            with self.connection.locked():
                self.connection.execute(
                    "INSERT INTO runtime_incident (ts, kind, payload_json) VALUES (?, ?, ?)",
                    (now, kind, payload_json),
                )
                # Prune oldest if over cap
                self.connection.execute(
                    """
                    DELETE FROM runtime_incident
                    WHERE id NOT IN (
                        SELECT id FROM runtime_incident
                        ORDER BY ts DESC
                        LIMIT ?
                    )
                    """,
                    (self.max_rows,),
                )
                self.connection.commit()
        except Exception:
            logger.warning("Failed to record incident", exc_info=True)

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch most recent incidents."""
        with self.connection.locked():
            rows = self.connection.execute(
                "SELECT * FROM runtime_incident ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                d["payload"] = {}
            result.append(d)
        return result

    def count(self) -> int:
        """Total number of stored incidents."""
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT COUNT(*) as cnt FROM runtime_incident"
            ).fetchone()
        return row["cnt"] if row else 0
