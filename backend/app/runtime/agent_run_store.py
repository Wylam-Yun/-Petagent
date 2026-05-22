"""SQLite persistence for AgentRun — bounded store for postmortem."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.pet.state import LockedSQLiteConnection


class AgentRunStore:
    """Persists agent run metadata to SQLite for postmortem debugging.

    Capped at max_rows (default 200). Oldest rows deleted after each insert.
    """

    def __init__(
        self,
        connection: "LockedSQLiteConnection",
        max_rows: int = 200,
    ) -> None:
        self.connection = connection
        self.max_rows = max_rows
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_run (
                    run_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL DEFAULT '',
                    episode_id TEXT NOT NULL DEFAULT '',
                    route TEXT NOT NULL DEFAULT '',
                    context_profile TEXT NOT NULL DEFAULT '',
                    provider TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'started',
                    error TEXT,
                    timings_json TEXT NOT NULL DEFAULT '{}',
                    sanitized_user_text TEXT NOT NULL DEFAULT '',
                    sanitized_response_text TEXT NOT NULL DEFAULT '',
                    requested_tools_json TEXT NOT NULL DEFAULT '[]',
                    final_action_json TEXT,
                    audio_job_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_run_created
                ON agent_run(created_at)
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_run_episode
                ON agent_run(episode_id)
                """
            )
            self.connection.commit()

    def save(self, run_dict: Dict[str, Any]) -> None:
        """Insert or replace an agent run row, then cap at max_rows."""
        now = datetime.utcnow().isoformat()
        timings_json = json.dumps(run_dict.get("timings_ms") or {}, ensure_ascii=False)
        tools_json = json.dumps(run_dict.get("requested_tools") or [], ensure_ascii=False)
        action_json = json.dumps(run_dict.get("final_action"), ensure_ascii=False) if run_dict.get("final_action") else None

        # Sanitize text fields — strip anything that looks like a key or token
        user_text = _sanitize_text(run_dict.get("sanitized_user_text", ""))
        response_text = _sanitize_text(run_dict.get("sanitized_response_text", ""))

        with self.connection.locked():
            self.connection.execute(
                """
                INSERT OR REPLACE INTO agent_run (
                    run_id, event_id, episode_id, route, context_profile,
                    provider, status, error, timings_json,
                    sanitized_user_text, sanitized_response_text,
                    requested_tools_json, final_action_json, audio_job_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_dict["run_id"],
                    run_dict.get("event_id", ""),
                    run_dict.get("episode_id", ""),
                    run_dict.get("route", ""),
                    run_dict.get("context_profile", ""),
                    run_dict.get("provider", ""),
                    run_dict.get("status", "started"),
                    run_dict.get("error"),
                    timings_json,
                    user_text,
                    response_text,
                    tools_json,
                    action_json,
                    run_dict.get("audio_job_id"),
                    run_dict.get("created_at", now),
                    run_dict.get("updated_at", now),
                ),
            )
            # Cap at max_rows — delete oldest
            self.connection.execute(
                """
                DELETE FROM agent_run
                WHERE run_id NOT IN (
                    SELECT run_id FROM agent_run
                    ORDER BY created_at DESC
                    LIMIT ?
                )
                """,
                (self.max_rows,),
            )
            self.connection.commit()

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a run by ID, or None if not found."""
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT * FROM agent_run WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch most recent runs."""
        with self.connection.locked():
            rows = self.connection.execute(
                "SELECT * FROM agent_run ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def count(self) -> int:
        """Total number of stored runs."""
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT COUNT(*) as cnt FROM agent_run"
            ).fetchone()
        return row["cnt"] if row else 0


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    timings_json = d.pop("timings_json", "{}")
    tools_json = d.pop("requested_tools_json", "[]")
    action_json = d.pop("final_action_json", None)
    try:
        d["timings_ms"] = json.loads(timings_json) if timings_json else {}
    except (json.JSONDecodeError, TypeError):
        d["timings_ms"] = {}
    try:
        d["requested_tools"] = json.loads(tools_json) if tools_json else []
    except (json.JSONDecodeError, TypeError):
        d["requested_tools"] = []
    try:
        d["final_action"] = json.loads(action_json) if action_json else None
    except (json.JSONDecodeError, TypeError):
        d["final_action"] = None
    return d


def _sanitize_text(text: str) -> str:
    """Strip anything that looks like a key or token from text."""
    if not text:
        return ""
    result = text
    for marker in ("sk-", "tp-", "nvapi-", "Bearer ", "token="):
        idx = result.find(marker)
        if idx >= 0:
            result = result[:idx] + "[REDACTED]"
            break
    return result[:500]  # Cap length
