"""SQLite persistence for AudioJob — write-through store for restart recovery."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.pet.state import LockedSQLiteConnection


class AudioJobStore:
    """Persists audio jobs to SQLite so they survive process restarts.

    Follows the memory_store.py pattern: constructor takes connection,
    _ensure_table() creates schema, all CRUD wrapped in connection.locked().
    """

    def __init__(self, connection: "LockedSQLiteConnection") -> None:
        self.connection = connection
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audio_job (
                    job_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL DEFAULT '',
                    event_id TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    text TEXT NOT NULL,
                    voice_style TEXT NOT NULL DEFAULT '',
                    provider TEXT NOT NULL DEFAULT '',
                    voice_url TEXT,
                    audio_path TEXT,
                    error TEXT,
                    error_class TEXT,
                    failure_reason TEXT,
                    timings_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    expires_at TEXT,
                    superseded_by TEXT
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audio_job_status_created
                ON audio_job(status, created_at)
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audio_job_session_status_created
                ON audio_job(session_id, status, created_at)
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audio_job_run_id
                ON audio_job(run_id)
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audio_job_event_id
                ON audio_job(event_id)
                """
            )
            self.connection.commit()

    def save(self, job: Dict[str, Any]) -> None:
        """Insert or replace an audio job row."""
        now = datetime.utcnow().isoformat()
        timings_json = json.dumps(job.get("timings_ms") or {}, ensure_ascii=False)
        with self.connection.locked():
            self.connection.execute(
                """
                INSERT OR REPLACE INTO audio_job (
                    job_id, run_id, event_id, session_id, status,
                    text, voice_style, provider, voice_url, audio_path,
                    error, error_class, failure_reason, timings_json,
                    created_at, updated_at, completed_at, expires_at, superseded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["job_id"],
                    job.get("run_id", ""),
                    job.get("event_id", ""),
                    job.get("session_id", ""),
                    job["status"],
                    job.get("text", ""),
                    job.get("voice_style", ""),
                    job.get("provider", ""),
                    job.get("voice_url"),
                    job.get("audio_path"),
                    job.get("error"),
                    job.get("error_class"),
                    job.get("failure_reason"),
                    timings_json,
                    job.get("created_at", now),
                    job.get("updated_at", now),
                    job.get("completed_at"),
                    job.get("expires_at"),
                    job.get("superseded_by"),
                ),
            )
            self.connection.commit()

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a job by ID, or None if not found."""
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT * FROM audio_job WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def mark_restart_failed(self) -> int:
        """Mark all pending/running jobs as failed on runtime restart.

        Returns count of affected rows.
        """
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                UPDATE audio_job
                SET status = 'failed_runtime_restart',
                    failure_reason = 'runtime_restarted',
                    error = 'runtime restarted while job was in-flight',
                    updated_at = ?,
                    completed_at = ?
                WHERE status IN ('pending', 'running')
                """,
                (now, now),
            )
            count = cursor.rowcount
            if count:
                self.connection.commit()
        return count

    def mark_shutdown_failed(self) -> int:
        """Mark all pending/running jobs as failed on graceful shutdown.

        Returns count of affected rows.
        """
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                UPDATE audio_job
                SET status = 'failed_shutdown',
                    failure_reason = 'process_shutdown',
                    error = 'process shutdown while job was in-flight',
                    updated_at = ?,
                    completed_at = ?
                WHERE status IN ('pending', 'running')
                """,
                (now, now),
            )
            count = cursor.rowcount
            if count:
                self.connection.commit()
        return count

    def cleanup_expired(self, ttl_seconds: int = 900) -> int:
        """Delete terminal jobs older than ttl_seconds. Returns count deleted."""
        from datetime import timedelta

        cutoff = (datetime.utcnow() - timedelta(seconds=ttl_seconds)).isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                DELETE FROM audio_job
                WHERE status IN ('ready', 'failed', 'expired', 'superseded',
                                 'failed_runtime_restart', 'failed_shutdown')
                  AND updated_at < ?
                """,
                (cutoff,),
            )
            deleted = cursor.rowcount
            if deleted:
                self.connection.commit()
        return deleted

    def count_by_status(self, status: str) -> int:
        """Count jobs with a given status."""
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT COUNT(*) as cnt FROM audio_job WHERE status = ?",
                (status,),
            ).fetchone()
        return row["cnt"] if row else 0

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        timings_json = d.pop("timings_json", "{}")
        try:
            d["timings_ms"] = json.loads(timings_json) if timings_json else {}
        except (json.JSONDecodeError, TypeError):
            d["timings_ms"] = {}
        return d
