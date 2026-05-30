from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{8,}"),
    re.compile(r"nvapi-[a-zA-Z0-9]{8,}"),
    re.compile(r"tp-[a-zA-Z0-9]{8,}"),
    re.compile(r"github_pat_[a-zA-Z0-9]{8,}"),
    re.compile(r"ghp_[a-zA-Z0-9]{8,}"),
    re.compile(r"[A-Z_]+_KEY=\S+"),
    re.compile(r"[A-Z_]+_TOKEN=\S+"),
    re.compile(r"[A-Za-z0-9+/=]{40,}"),
]


def desensitize_text(text: str, max_length: int = 200) -> str:
    """Mask suspected secrets and truncate for debug output."""
    if not text:
        return ""
    result = str(text)
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    if len(result) > max_length:
        result = result[:max_length] + "..."
    return result


class EpisodeStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS episode (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    started_at_utc TEXT NOT NULL,
                    ended_at_utc TEXT,
                    last_event_at_utc TEXT NOT NULL,
                    close_reason TEXT,
                    summary TEXT,
                    summary_updated_at TEXT,
                    event_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_episode_status_last_event
                ON episode(status, last_event_at_utc)
                """
            )
            self.connection.commit()

    def get_or_create_current(
        self, now_utc: Optional[str] = None, idle_minutes: int = 45
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Return (current_episode, closed_episode_id_or_None).

        When idle timeout triggers, the old episode is closed and
        closed_episode_id is returned so the dispatcher can enqueue
        a summary job.
        """
        now = now_utc or datetime.utcnow().isoformat()
        with self.connection.locked():
            row = self.connection.execute(
                """
                SELECT episode_id, status, started_at_utc, ended_at_utc,
                       last_event_at_utc, close_reason, event_count
                FROM episode
                WHERE status = 'open'
                ORDER BY last_event_at_utc DESC
                LIMIT 1
                """
            ).fetchone()
            if row is not None:
                last_event = row["last_event_at_utc"]
                if self._should_rollover(last_event, now, idle_minutes):
                    closed_id = row["episode_id"]
                    self._close(closed_id, "idle_timeout", now)
                    new_ep = self._create(now)
                    return new_ep, closed_id
                return dict(row), None
            return self._create(now), None

    def peek_current(self) -> Optional[Dict[str, Any]]:
        """Return the current open episode without creating one. Returns None if no open episode."""
        with self.connection.locked():
            row = self.connection.execute(
                """
                SELECT episode_id, status, started_at_utc, ended_at_utc,
                       last_event_at_utc, close_reason, event_count
                FROM episode
                WHERE status = 'open'
                ORDER BY last_event_at_utc DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def close_current(self, reason: str, now_utc: Optional[str] = None) -> Optional[str]:
        """Close the current open episode. Returns the closed episode_id or None."""
        now = now_utc or datetime.utcnow().isoformat()
        with self.connection.locked():
            row = self.connection.execute(
                """
                SELECT episode_id FROM episode
                WHERE status = 'open'
                ORDER BY last_event_at_utc DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            self._close(row["episode_id"], reason, now)
            return row["episode_id"]

    def refresh_topic(self, now_utc: Optional[str] = None) -> tuple:
        """Close current episode (reason=context_refresh) and create a new one.

        Returns (new_episode, closed_episode_id_or_None).
        """
        now = now_utc or datetime.utcnow().isoformat()
        closed_id = self.close_current("context_refresh", now)
        return self._create(now), closed_id

    def update_event_count(self, episode_id: str, now_utc: Optional[str] = None) -> None:
        """Increment event_count and update last_event_at for an episode."""
        now = now_utc or datetime.utcnow().isoformat()
        with self.connection.locked():
            self.connection.execute(
                """
                UPDATE episode
                SET event_count = event_count + 1, last_event_at_utc = ?
                WHERE episode_id = ?
                """,
                (now, episode_id),
            )
            self.connection.commit()

    def get_episode(self, episode_id: str) -> Optional[Dict[str, Any]]:
        with self.connection.locked():
            row = self.connection.execute(
                """
                SELECT episode_id, status, started_at_utc, ended_at_utc,
                       last_event_at_utc, close_reason, event_count
                FROM episode WHERE episode_id = ?
                """,
                (episode_id,),
            ).fetchone()
        return dict(row) if row else None

    def _should_rollover(self, last_event_at: str, now: str, idle_minutes: int) -> bool:
        try:
            last = datetime.fromisoformat(last_event_at)
            current = datetime.fromisoformat(now)
            return (current - last) > timedelta(minutes=idle_minutes)
        except (ValueError, TypeError):
            return False

    def _close(self, episode_id: str, reason: str, now: str) -> None:
        self.connection.execute(
            """
            UPDATE episode
            SET status = 'closed', ended_at_utc = ?, close_reason = ?
            WHERE episode_id = ?
            """,
            (now, reason, episode_id),
        )
        self.connection.commit()

    def _create(self, now: str) -> Dict[str, Any]:
        episode_id = "ep-" + uuid4().hex
        row = {
            "episode_id": episode_id,
            "status": "open",
            "started_at_utc": now,
            "ended_at_utc": None,
            "last_event_at_utc": now,
            "close_reason": None,
            "event_count": 0,
        }
        with self.connection.locked():
            self.connection.execute(
                """
                INSERT INTO episode (episode_id, status, started_at_utc, last_event_at_utc, event_count)
                VALUES (?, 'open', ?, ?, 0)
                """,
                (episode_id, now, now),
            )
            self.connection.commit()
        return row


class EventLogStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    episode_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    user_text TEXT,
                    pet_reply TEXT,
                    skill_results_json TEXT,
                    state_before_json TEXT,
                    state_after_json TEXT,
                    mood_after TEXT,
                    created_at_utc TEXT NOT NULL,
                    created_at_local TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    importance_hint INTEGER NOT NULL DEFAULT 0,
                    summary_status TEXT NOT NULL DEFAULT 'raw'
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_raw_event_episode_created
                ON raw_event_log(episode_id, created_at_utc)
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_raw_event_created_status
                ON raw_event_log(created_at_utc, summary_status)
                """
            )
            self.connection.commit()
        self._ensure_state_affect_column()

    def _ensure_state_affect_column(self) -> None:
        with self.connection.locked():
            rows = self.connection.execute("PRAGMA table_info(raw_event_log)").fetchall()
            columns = {row["name"] for row in rows}
            if "state_affect_json" not in columns:
                self.connection.execute("ALTER TABLE raw_event_log ADD COLUMN state_affect_json TEXT")
                self.connection.commit()

    def record(
        self,
        event_id: str,
        episode_id: str,
        event_type: str,
        source: str,
        user_text: str = "",
        pet_reply: str = "",
        skill_results: Optional[List[Dict[str, Any]]] = None,
        state_before: Optional[Dict[str, Any]] = None,
        state_after: Optional[Dict[str, Any]] = None,
        mood_after: str = "",
        state_affect: Optional[Dict[str, Any]] = None,
        created_at_utc: Optional[str] = None,
        created_at_local: Optional[str] = None,
        timezone_name: str = "Asia/Shanghai",
        importance_hint: int = 0,
    ) -> None:
        now_utc = created_at_utc or datetime.utcnow().isoformat()
        if created_at_local is None:
            try:
                tz = timezone(timedelta(hours=8))
                created_at_local = datetime.now(tz).isoformat()
            except Exception:
                created_at_local = now_utc
        with self.connection.locked():
            self.connection.execute(
                """
                INSERT INTO raw_event_log (
                    event_id, episode_id, event_type, source,
                    user_text, pet_reply, skill_results_json,
                    state_before_json, state_after_json, mood_after,
                    state_affect_json,
                    created_at_utc, created_at_local, timezone,
                    importance_hint, summary_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'raw')
                """,
                (
                    event_id,
                    episode_id,
                    event_type,
                    source,
                    user_text or None,
                    pet_reply or None,
                    json.dumps(skill_results, ensure_ascii=False) if skill_results else None,
                    json.dumps(state_before, ensure_ascii=False) if state_before else None,
                    json.dumps(state_after, ensure_ascii=False) if state_after else None,
                    mood_after or None,
                    json.dumps(state_affect, ensure_ascii=False) if state_affect else None,
                    now_utc,
                    created_at_local,
                    timezone_name,
                    importance_hint,
                ),
            )
            self.connection.commit()

    def recent_events(
        self, episode_id: Optional[str] = None, limit: int = 6
    ) -> List[Dict[str, Any]]:
        with self.connection.locked():
            if episode_id:
                rows = self.connection.execute(
                    """
                    SELECT event_id, episode_id, event_type, source,
                           user_text, pet_reply, mood_after, created_at_utc,
                           state_affect_json
                    FROM raw_event_log
                    WHERE episode_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (episode_id, limit),
                ).fetchall()
            else:
                rows = self.connection.execute(
                    """
                    SELECT event_id, episode_id, event_type, source,
                           user_text, pet_reply, mood_after, created_at_utc,
                           state_affect_json
                    FROM raw_event_log
                    ORDER BY id DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [
            {
                **dict(row),
                "state_affect": json.loads(row["state_affect_json"]) if row["state_affect_json"] else None,
            }
            for row in rows
        ]

    def recent_dialogue_turns(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return latest durable foreground dialogue turns across episodes."""
        safe_limit = max(1, int(limit or 5))
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT event_id, event_type, source, user_text, pet_reply, created_at_utc
                FROM raw_event_log
                WHERE event_type IN ('text_message', 'voice_message')
                  AND user_text IS NOT NULL AND TRIM(user_text) != ''
                  AND pet_reply IS NOT NULL AND TRIM(pet_reply) != ''
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        result = [
            {
                "user": row["user_text"],
                "pet": row["pet_reply"],
                "created_at": row["created_at_utc"],
            }
            for row in rows
        ]
        result.reverse()
        return result

    def recent_events_bounded(
        self, limit: int = 200, max_bytes: int = 20480
    ) -> List[Dict[str, Any]]:
        """Read recent events with bounded serialized size (Nubia constraint)."""
        raw = self.recent_events(limit=limit)
        result = []
        total = 0
        for evt in raw:
            # Estimate size of user_text + pet_reply + mood
            size = 0
            for key in ("user_text", "pet_reply", "mood_after"):
                val = evt.get(key) or ""
                size += len(val.encode("utf-8"))
            if total + size > max_bytes:
                break
            result.append(evt)
            total += size
        return result

    def recall_events(
        self,
        *,
        since_utc: str,
        limit: int = 6,
        exclude_episode_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent raw events useful for temporal recall questions."""
        where = "created_at_utc >= ?"
        params: list = [since_utc]
        if exclude_episode_id:
            where += " AND episode_id != ?"
            params.append(exclude_episode_id)
        params.append(limit)
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT event_id, episode_id, event_type, source,
                       user_text, pet_reply, mood_after, created_at_utc,
                       state_affect_json
                FROM raw_event_log
                WHERE {where}
                  AND (user_text IS NOT NULL OR pet_reply IS NOT NULL)
                ORDER BY id DESC
                LIMIT ?
                """.format(where=where),
                params,
            ).fetchall()
        result = [
            {
                **dict(row),
                "state_affect": json.loads(row["state_affect_json"]) if row["state_affect_json"] else None,
            }
            for row in rows
        ]
        result.reverse()
        return result

    def count(self) -> int:
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT COUNT(*) as cnt FROM raw_event_log"
            ).fetchone()
        return row["cnt"] if row else 0

    def cleanup_if_needed(
        self, max_rows: int = 3000, current_episode_id: Optional[str] = None
    ) -> int:
        """V1.5 keeps raw history durable until explicit archival exists."""
        return 0


@dataclass(frozen=True)
class SuccessfulTurnResult:
    incremented: bool
    should_enqueue_memory: bool
    total: int
    since_memory_summary: int
    trigger_reason: str = ""


class SuccessfulTurnStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS successful_turn_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS successful_turn_event (
                    event_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                )
                """
            )
            self.connection.commit()

    def record_successful_turn(
        self, event_id: str, keyword_trigger: bool = False
    ) -> SuccessfulTurnResult:
        event_id = str(event_id or "").strip()
        if not event_id:
            snap = self.snapshot()
            return SuccessfulTurnResult(
                incremented=False,
                should_enqueue_memory=False,
                total=snap["successful_turn_count_total"],
                since_memory_summary=snap["successful_turn_count_since_memory_summary"],
            )
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            try:
                self.connection.execute(
                    "INSERT INTO successful_turn_event (event_id, created_at) VALUES (?, ?)",
                    (event_id, now),
                )
            except sqlite3.IntegrityError:
                snap = self._snapshot_locked()
                return SuccessfulTurnResult(
                    incremented=False,
                    should_enqueue_memory=False,
                    total=snap["successful_turn_count_total"],
                    since_memory_summary=snap["successful_turn_count_since_memory_summary"],
                )

            total = self._get_int_locked("successful_turn_count_total") + 1
            since = self._get_int_locked("successful_turn_count_since_memory_summary") + 1
            trigger_reason = ""
            should_enqueue = False
            if keyword_trigger:
                should_enqueue = True
                trigger_reason = "keyword"
            elif since >= 10:
                should_enqueue = True
                trigger_reason = "ten_turns"
            self._set_locked("successful_turn_count_total", str(total))
            self._set_locked(
                "successful_turn_count_since_memory_summary",
                "0" if should_enqueue else str(since),
            )
            self._set_locked("last_successful_turn_event_id", event_id)
            if should_enqueue:
                self._set_locked("last_memory_summary_event_id", event_id)
                self._set_locked("last_memory_summary_at", now)
            self.connection.commit()
            return SuccessfulTurnResult(
                incremented=True,
                should_enqueue_memory=should_enqueue,
                total=total,
                since_memory_summary=0 if should_enqueue else since,
                trigger_reason=trigger_reason,
            )

    def mark_memory_summary_enqueued(self, event_id: str) -> None:
        with self.connection.locked():
            self._set_locked("last_memory_summary_event_id", str(event_id or ""))
            self._set_locked("last_memory_summary_at", datetime.utcnow().isoformat())
            self.connection.commit()

    def snapshot(self) -> Dict[str, int]:
        with self.connection.locked():
            return self._snapshot_locked()

    def clear_all(self) -> None:
        with self.connection.locked():
            self.connection.execute("DELETE FROM successful_turn_state")
            self.connection.execute("DELETE FROM successful_turn_event")
            self.connection.commit()

    def _snapshot_locked(self) -> Dict[str, int]:
        return {
            "successful_turn_count_total": self._get_int_locked("successful_turn_count_total"),
            "successful_turn_count_since_memory_summary": self._get_int_locked(
                "successful_turn_count_since_memory_summary"
            ),
        }

    def _get_int_locked(self, key: str) -> int:
        row = self.connection.execute(
            "SELECT value FROM successful_turn_state WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return 0
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return 0

    def _set_locked(self, key: str, value: str) -> None:
        self.connection.execute(
            """
            INSERT INTO successful_turn_state (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
