from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.runtime.actions import ALLOWED_BEHAVIOR_ACTIONS
from app.runtime.expressions import (
    ACTIVITY_RECOMMENDATIONS,
    ActivityRecommendation,
    contains_kaomoji,
    normalize_expression_key,
)

MAX_BUBBLE_CHARS = 20
DAILY_LIMIT = 10
DEFAULT_BACKOFF_MS = [5 * 60_000, 10 * 60_000, 20 * 60_000, 40 * 60_000, 90 * 60_000]

@dataclass(frozen=True)
class AmbientBubbleAction:
    bubble: str
    expression_key: str
    action: str
    source: str = "llm_generated"

def guard_ambient_bubble_output(
    raw: Any,
    recommendation: Optional[ActivityRecommendation] = None,
) -> Optional[AmbientBubbleAction]:
    if not isinstance(raw, dict):
        return None
    bubble = str(raw.get("bubble") or "").strip()
    if not bubble or len(bubble) > MAX_BUBBLE_CHARS:
        return None
    if "豆豆" in bubble or "我" not in bubble:
        return None
    if contains_kaomoji(bubble):
        return None
    expression_key = normalize_expression_key(raw.get("expression_key"), "idle")
    action = str(raw.get("action") or "idle")
    if action not in ALLOWED_BEHAVIOR_ACTIONS:
        return None
    if recommendation is not None:
        if expression_key not in recommendation.expression_keys:
            return None
        if action not in recommendation.actions:
            return None
    return AmbientBubbleAction(
        bubble=bubble,
        expression_key=expression_key,
        action=action,
    )


class AmbientBubbleService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.last_validation_failure_reason = ""
        self._generation_lock = threading.Lock()
        self._generation_inflight = False
        self.initialize()

    def initialize(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ambient_bubble_pending (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_date TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    suggested_activity TEXT NOT NULL,
                    activity_class TEXT NOT NULL,
                    bubble TEXT NOT NULL,
                    expression_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ambient_bubble_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_date TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    suggested_activity TEXT NOT NULL,
                    activity_class TEXT NOT NULL,
                    bubble TEXT NOT NULL,
                    expression_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self.connection.commit()

    def expire_pending(self) -> int:
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                UPDATE ambient_bubble_pending
                SET status = 'expired'
                WHERE status = 'pending' AND expires_at < ?
                """,
                (now,),
            )
            self.connection.commit()
        return cursor.rowcount

    def can_emit(self, local_date: str) -> Dict[str, Any]:
        self.expire_pending()
        state = self.debug_state(local_date)
        if state["daily_count"] >= DAILY_LIMIT:
            return {"eligible": False, "block_reason": "daily_limit"}
        if state["pending_count"] > 0:
            return {"eligible": False, "block_reason": "pending_exists"}
        return {"eligible": True, "block_reason": ""}

    def begin_generation(self, local_date: str) -> Dict[str, Any]:
        with self._generation_lock:
            if self._generation_inflight:
                return {"eligible": False, "block_reason": "ambient_inflight"}
            allowed = self.can_emit(local_date)
            if not allowed["eligible"]:
                return allowed
            self._generation_inflight = True
            return {"eligible": True, "block_reason": ""}

    def end_generation(self) -> None:
        with self._generation_lock:
            self._generation_inflight = False

    def select_activity(self, local_date: str) -> Optional[str]:
        state = self.debug_state(local_date)
        last_class = state.get("last_activity_class") or ""
        for name, rec in ACTIVITY_RECOMMENDATIONS.items():
            if rec.activity_class == last_class:
                continue
            count = state["activity_counts"].get(name, 0)
            limit = 1 if rec.strong_once_daily else 2
            if count < limit:
                return name
        self.last_validation_failure_reason = "no_available_activity"
        return None

    def create_pending(
        self,
        *,
        local_date: str,
        event_id: str,
        activity: str,
        activity_class: str,
        bubble: str,
        expression_key: str,
        action: str,
    ) -> bool:
        if not self.can_emit(local_date)["eligible"]:
            return False
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=2)
        with self.connection.locked():
            self.connection.execute(
                """
                INSERT INTO ambient_bubble_pending
                    (local_date, event_id, suggested_activity, activity_class, bubble,
                     expression_key, action, source, status, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    local_date,
                    event_id,
                    activity,
                    activity_class,
                    bubble,
                    expression_key,
                    action,
                    "llm_generated",
                    expires_at.isoformat(),
                    now.isoformat(),
                ),
            )
            self.connection.commit()
        return True

    def confirm_pending(self, event_id: str) -> bool:
        self.expire_pending()
        with self.connection.locked():
            row = self.connection.execute(
                """
                SELECT local_date, event_id, suggested_activity, activity_class,
                       bubble, expression_key, action, source
                FROM ambient_bubble_pending
                WHERE event_id = ? AND status = 'pending'
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                return False
            if self.debug_state(row["local_date"])["daily_count"] >= DAILY_LIMIT:
                return False
            self.connection.execute(
                """
                INSERT INTO ambient_bubble_log
                    (local_date, event_id, suggested_activity, activity_class,
                     bubble, expression_key, action, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["local_date"],
                    row["event_id"],
                    row["suggested_activity"],
                    row["activity_class"],
                    row["bubble"],
                    row["expression_key"],
                    row["action"],
                    row["source"],
                    datetime.utcnow().isoformat(),
                ),
            )
            self.connection.execute(
                "UPDATE ambient_bubble_pending SET status = 'confirmed' WHERE event_id = ?",
                (event_id,),
            )
            self.connection.commit()
        return True

    def cancel_pending(self, event_id: str) -> bool:
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                UPDATE ambient_bubble_pending
                SET status = 'cancelled'
                WHERE event_id = ? AND status = 'pending'
                """,
                (event_id,),
            )
            self.connection.commit()
        return cursor.rowcount > 0

    def record_failure(self, reason: str) -> None:
        self.last_validation_failure_reason = str(reason or "unknown")

    def debug_state(self, local_date: str) -> Dict[str, Any]:
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT suggested_activity, activity_class, expression_key, action, source
                FROM ambient_bubble_log
                WHERE local_date = ?
                ORDER BY id ASC
                """,
                (local_date,),
            ).fetchall()
            pending_row = self.connection.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM ambient_bubble_pending
                WHERE local_date = ? AND status = 'pending' AND expires_at >= ?
                """,
                (local_date, datetime.utcnow().isoformat()),
            ).fetchone()
        activity_counts: Dict[str, int] = {}
        for row in rows:
            activity = row["suggested_activity"]
            activity_counts[activity] = activity_counts.get(activity, 0) + 1
        last = rows[-1] if rows else None
        return {
            "daily_count": len(rows),
            "pending_count": pending_row["cnt"] if pending_row else 0,
            "activity_counts": activity_counts,
            "last_suggested_activity": last["suggested_activity"] if last else "",
            "last_activity_class": last["activity_class"] if last else "",
            "last_rendered_expression_key": last["expression_key"] if last else "",
            "last_rendered_action": last["action"] if last else "",
            "last_idle_bubble_source": last["source"] if last else "",
            "backoff_step": len(rows),
            "last_validation_failure_reason": self.last_validation_failure_reason,
        }
