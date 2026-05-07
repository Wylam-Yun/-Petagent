from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute("PRAGMA table_info(%s)" % table).fetchall()
    return any(row["name"] == column for row in rows)


def _ensure_column(
    connection: sqlite3.Connection, table: str, column: str, col_type: str, default: str = ""
) -> None:
    if not _column_exists(connection, table, column):
        ddl = "ALTER TABLE %s ADD COLUMN %s %s" % (table, column, col_type)
        if default:
            ddl += " DEFAULT %s" % default
        connection.execute(ddl)


class MemoryManager:
    """Manages memory table schema migration and CRUD for curated memories."""

    VALID_TYPES = {
        "user_preference",
        "relationship",
        "stable_memory",
        "important_quote",
        "recent_mood",
        "important_event",
        "habit",
    }

    def __init__(self, connection: sqlite3.Connection, config: Optional[Dict[str, Any]] = None) -> None:
        self.connection = connection
        self._migrate()
        cfg = config or {}
        self._TYPE_HALF_LIFE_DAYS = {
            "user_preference": cfg.get("decay_half_life_stable_days", 90),
            "relationship": cfg.get("decay_half_life_stable_days", 90),
            "habit": cfg.get("decay_half_life_stable_days", 90),
            "stable_memory": cfg.get("decay_half_life_stable_days", 90) * 2 / 3,
            "important_quote": 30,
            "recent_mood": cfg.get("decay_half_life_volatile_days", 14) / 2,
            "important_event": cfg.get("decay_half_life_volatile_days", 14),
        }

    def _migrate(self) -> None:
        with self.connection.locked():
            # Ensure base table exists
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                )
                """
            )
            # Add new columns
            _ensure_column(self.connection, "memory", "summary", "TEXT")
            _ensure_column(self.connection, "memory", "source_event_id", "TEXT")
            _ensure_column(self.connection, "memory", "source_episode_id", "TEXT")
            _ensure_column(self.connection, "memory", "confidence", "REAL", "0.8")
            _ensure_column(self.connection, "memory", "ttl_days", "INTEGER")
            _ensure_column(self.connection, "memory", "expires_at", "TEXT")
            _ensure_column(self.connection, "memory", "updated_at", "TEXT")
            _ensure_column(self.connection, "memory", "usage_count", "INTEGER", "0")

            # Indexes for scorer queries
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_type_expires_importance
                ON memory(type, expires_at, importance)
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_type_last_used
                ON memory(type, last_used_at)
                """
            )
            self.connection.commit()

    def save_curated(
        self,
        memory_type: str,
        content: str,
        importance: int = 3,
        confidence: float = 0.8,
        ttl_days: Optional[int] = None,
        source_event_id: Optional[str] = None,
        source_episode_id: Optional[str] = None,
        summary: Optional[str] = None,
        merge_with_id: Optional[int] = None,
    ) -> Optional[int]:
        """Save a curated memory. Returns memory id, or None if rejected."""
        if memory_type not in self.VALID_TYPES:
            return None
        if not content or len(content) > 500:
            return None
        now = datetime.utcnow().isoformat()
        expires_at = None
        if ttl_days is not None:
            from datetime import timedelta
            expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()

        if merge_with_id is not None:
            return self._merge(merge_with_id, content, importance, confidence, summary, now)

        with self.connection.locked():
            cursor = self.connection.execute(
                """
                INSERT INTO memory (
                    type, content, importance, confidence, summary,
                    source_event_id, source_episode_id,
                    ttl_days, expires_at, created_at, updated_at, usage_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    memory_type,
                    content,
                    importance,
                    confidence,
                    summary,
                    source_event_id,
                    source_episode_id,
                    ttl_days,
                    expires_at,
                    now,
                    now,
                ),
            )
            self.connection.commit()
            return cursor.lastrowid

    def _merge(
        self,
        memory_id: int,
        content: str,
        importance: int,
        confidence: float,
        summary: Optional[str],
        now: str,
    ) -> Optional[int]:
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT id FROM memory WHERE id = ?", (memory_id,)
            ).fetchone()
            if row is None:
                return None
            self.connection.execute(
                """
                UPDATE memory
                SET content = ?, importance = ?, confidence = ?,
                    summary = COALESCE(?, summary), updated_at = ?
                WHERE id = ?
                """,
                (content, importance, confidence, summary, now, memory_id),
            )
            self.connection.commit()
            return memory_id

    def scored_memories(
        self,
        limit: int = 4,
        user_text: str = "",
        exclude_expired: bool = True,
    ) -> List[Dict[str, Any]]:
        """Select relevant memories by type priority + time + decay + keywords."""
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT id, type, content, importance, confidence,
                       created_at, last_used_at, usage_count, summary
                FROM memory
                WHERE (? OR expires_at IS NULL OR expires_at > ?)
                ORDER BY id DESC
                LIMIT 50
                """,
                (not exclude_expired, now),
            ).fetchall()

        if not rows:
            return []

        scored = []
        keywords = self._extract_keywords(user_text)
        keyword_matched_ids: List[int] = []
        for row in rows:
            row_dict = dict(row)
            score, had_keyword_match = self._score_row(row_dict, keywords)
            scored.append((score, row_dict))
            if had_keyword_match:
                keyword_matched_ids.append(row_dict["id"])

        scored.sort(key=lambda x: x[0], reverse=True)
        result = []
        for score, row_dict in scored[:limit]:
            entry = {
                "id": row_dict["id"],
                "type": row_dict["type"],
                "content": row_dict["content"],
                "importance": row_dict["importance"],
            }
            if row_dict.get("summary"):
                entry["summary"] = row_dict["summary"]
            result.append(entry)

        # Only increment usage_count for keyword-matched memories (not all selected)
        if keyword_matched_ids:
            matched_in_result = [mid for mid in keyword_matched_ids if any(e["id"] == mid for e in result)]
            if matched_in_result:
                placeholders = ",".join("?" for _ in matched_in_result)
                with self.connection.locked():
                    self.connection.execute(
                        "UPDATE memory SET last_used_at = ?, usage_count = usage_count + 1 WHERE id IN (%s)" % placeholders,
                        (now, *matched_in_result),
                    )
                    self.connection.commit()

        return result

    def record_usage(self, memory_id: int) -> None:
        """Increment usage_count for a specific memory. Called on keyword match."""
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            self.connection.execute(
                "UPDATE memory SET last_used_at = ?, usage_count = usage_count + 1 WHERE id = ?",
                (now, memory_id),
            )
            self.connection.commit()

    def _decay_factor(self, created_at: str, memory_type: str) -> float:
        """Return 0.0-1.0 decay multiplier based on age."""
        try:
            created = datetime.fromisoformat(created_at)
            age_days = max(0, (datetime.utcnow() - created).total_seconds() / 86400)
        except (ValueError, TypeError):
            return 1.0
        half_life = self._TYPE_HALF_LIFE_DAYS.get(memory_type, 30)
        return 0.5 ** (age_days / half_life)

    def important_quotes(self, limit: int = 4) -> List[Dict[str, Any]]:
        """Fetch recent important_quote memories."""
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT id, content, importance, created_at
                FROM memory
                WHERE type = 'important_quote'
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY importance DESC, id DESC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "importance": row["importance"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def cleanup_expired(self) -> int:
        """Delete expired memories. Returns count deleted."""
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                DELETE FROM memory
                WHERE expires_at IS NOT NULL AND expires_at < ?
                """,
                (now,),
            )
            deleted = cursor.rowcount
            if deleted:
                self.connection.commit()
        return deleted

    def clear_all(self) -> None:
        """Delete all memories. Used by reset."""
        with self.connection.locked():
            self.connection.execute("DELETE FROM memory")
            self.connection.commit()

    def count(self) -> int:
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT COUNT(*) as cnt FROM memory"
            ).fetchone()
        return row["cnt"] if row else 0

    def _score_row(self, row: Dict[str, Any], keywords: List[str]) -> tuple:
        """Score a memory row. Returns (score, had_keyword_match)."""
        score = 0.0
        # Type priority
        type_priority = {
            "user_preference": 10,
            "relationship": 10,
            "stable_memory": 9,
            "important_quote": 8,
            "recent_mood": 5,
            "important_event": 4,
            "habit": 6,
        }
        score += type_priority.get(row.get("type", ""), 1)

        # Importance bonus
        score += row.get("importance", 3) * 0.5

        # Recency bonus (only for non-stable types)
        mem_type = row.get("type", "")
        if mem_type not in ("stable_memory", "relationship", "user_preference"):
            last_used = row.get("last_used_at") or row.get("created_at", "")
            if last_used:
                try:
                    used_dt = datetime.fromisoformat(last_used)
                    hours_ago = (datetime.utcnow() - used_dt).total_seconds() / 3600
                    if hours_ago < 24:
                        score += 3
                    elif hours_ago < 72:
                        score += 1
                except (ValueError, TypeError):
                    pass

        # Keyword match bonus
        had_keyword_match = False
        content = row.get("content", "")
        if keywords and content:
            matches = sum(1 for kw in keywords if kw in content)
            if matches > 0:
                had_keyword_match = True
                score += matches * 2

        # Apply decay to total score (stable types decay slowly, volatile fast)
        created_at = row.get("created_at", "")
        decay = self._decay_factor(created_at, mem_type)

        # Very restrained usage boost: capped at 15%
        usage = row.get("usage_count", 0)
        usage_boost = 1.0 + min(usage * 0.03, 0.15)

        final_score = score * decay * usage_boost
        return final_score, had_keyword_match

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract simple Chinese keywords from text using bigrams."""
        if not text:
            return []
        import re
        chars = re.findall(r"[\u4e00-\u9fff]", text)
        stop_chars = {"的", "了", "是", "在", "我", "你", "他", "她", "它", "们", "这", "那", "有", "和", "吗", "吧", "呢", "啊"}
        # Single meaningful chars
        singles = [c for c in chars if c not in stop_chars]
        # Bigrams for better matching
        bigrams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
        return singles + bigrams


class MemoryCandidateStore:
    """Stores pending memory candidates for curator processing."""

    VALID_REASONS = {"explicit_command", "llm_suggestion", "episode_end", "daily_summary"}

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_candidate (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_event_id TEXT NOT NULL,
                    episode_id TEXT NOT NULL,
                    candidate_text TEXT NOT NULL,
                    trigger_reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    processed_at TEXT
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_candidate_status_created
                ON memory_candidate(status, created_at)
                """
            )
            self.connection.commit()

    def add(
        self,
        source_event_id: str,
        episode_id: str,
        candidate_text: str,
        trigger_reason: str,
    ) -> int:
        """Add a memory candidate. Returns candidate id."""
        if trigger_reason not in self.VALID_REASONS:
            raise ValueError("Invalid trigger_reason: %s" % trigger_reason)
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                INSERT INTO memory_candidate (
                    source_event_id, episode_id, candidate_text,
                    trigger_reason, status, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (source_event_id, episode_id, candidate_text, trigger_reason, now),
            )
            self.connection.commit()
            return cursor.lastrowid

    def pending(self, limit: int = 8) -> List[Dict[str, Any]]:
        """Fetch pending candidates ordered by created_at."""
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT id, source_event_id, episode_id, candidate_text,
                       trigger_reason, created_at
                FROM memory_candidate
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_processed(self, candidate_id: int, status: str) -> None:
        """Mark a candidate as processed (saved/ignored/error)."""
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            self.connection.execute(
                """
                UPDATE memory_candidate
                SET status = ?, processed_at = ?
                WHERE id = ?
                """,
                (status, now, candidate_id),
            )
            self.connection.commit()

    def count_pending(self) -> int:
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT COUNT(*) as cnt FROM memory_candidate WHERE status = 'pending'"
            ).fetchone()
        return row["cnt"] if row else 0

    def clear_all(self) -> None:
        """Delete all candidates. Used by reset."""
        with self.connection.locked():
            self.connection.execute("DELETE FROM memory_candidate")
            self.connection.commit()


class SummaryJobStore:
    """Stores pending summary jobs for maintenance processing."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS summary_job (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id TEXT NOT NULL,
                    job_type TEXT NOT NULL DEFAULT 'episode',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    processed_at TEXT
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_summary_job_status
                ON summary_job(status, created_at)
                """
            )
            self.connection.commit()

    def enqueue(self, episode_id: str, job_type: str = "episode") -> int:
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                INSERT INTO summary_job (episode_id, job_type, status, created_at)
                VALUES (?, ?, 'pending', ?)
                """,
                (episode_id, job_type, now),
            )
            self.connection.commit()
            return cursor.lastrowid

    def pending(self, limit: int = 1) -> List[Dict[str, Any]]:
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT id, episode_id, job_type, created_at
                FROM summary_job
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_done(self, job_id: int) -> None:
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            self.connection.execute(
                "UPDATE summary_job SET status = 'done', processed_at = ? WHERE id = ?",
                (now, job_id),
            )
            self.connection.commit()

    def mark_failed(self, job_id: int) -> None:
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            self.connection.execute(
                "UPDATE summary_job SET status = 'failed', processed_at = ? WHERE id = ?",
                (now, job_id),
            )
            self.connection.commit()

    def count_pending_for_date(
        self,
        target_date: str,
        episode_store: Any = None,
        timezone_name: str = "Asia/Shanghai",
    ) -> int:
        """Count pending episode summary jobs whose episode ended on target_date.

        Looks up the closed episode's ended_at_utc from the episode table
        (not episode_summary, since pending jobs have no summary row yet).
        """
        with self.connection.locked():
            rows = self.connection.execute(
                "SELECT episode_id FROM summary_job WHERE status = 'pending' AND job_type = 'episode'"
            ).fetchall()
        if not rows:
            return 0
        if episode_store is None:
            return 0

        from app.runtime.summary_manager import _TZ_OFFSETS
        from datetime import timedelta

        tz_offset = _TZ_OFFSETS.get(timezone_name, timedelta(hours=8))
        count = 0
        for row in rows:
            ep_id = row["episode_id"]
            # Look up episode ended_at from the episode table
            try:
                episode = episode_store.get_episode(ep_id)
            except Exception:
                continue
            if not episode:
                continue
            ended = episode.get("ended_at_utc", "")
            if not ended:
                continue
            try:
                dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
                local_date = (dt + tz_offset).strftime("%Y-%m-%d")
                if local_date == target_date:
                    count += 1
            except (ValueError, AttributeError):
                pass
        return count

    def clear_all(self) -> None:
        with self.connection.locked():
            self.connection.execute("DELETE FROM summary_job")
            self.connection.commit()


class EpisodeSummaryStore:
    """Stores episode summaries."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS episode_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL,
                    key_events_json TEXT NOT NULL DEFAULT '[]',
                    mood_notes TEXT,
                    important_quotes_json TEXT NOT NULL DEFAULT '[]',
                    started_at_utc TEXT NOT NULL,
                    ended_at_utc TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                )
                """
            )
            self.connection.commit()

    def save(
        self,
        episode_id: str,
        summary: str,
        key_events: List[str],
        mood_notes: str,
        important_quotes: List[Dict[str, Any]],
        started_at_utc: str,
        ended_at_utc: str,
        ttl_days: int = 7,
    ) -> int:
        from datetime import timedelta
        now = datetime.utcnow().isoformat()
        expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                INSERT OR REPLACE INTO episode_summary (
                    episode_id, summary, key_events_json, mood_notes,
                    important_quotes_json, started_at_utc, ended_at_utc,
                    created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode_id,
                    summary,
                    json.dumps(key_events, ensure_ascii=False),
                    mood_notes,
                    json.dumps(important_quotes, ensure_ascii=False),
                    started_at_utc,
                    ended_at_utc,
                    now,
                    expires_at,
                ),
            )
            self.connection.commit()
            return cursor.lastrowid

    def recent(self, limit: int = 2) -> List[Dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT episode_id, summary, key_events_json, mood_notes,
                       important_quotes_json, started_at_utc, ended_at_utc
                FROM episode_summary
                WHERE expires_at IS NULL OR expires_at > ?
                ORDER BY ended_at_utc DESC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["key_events"] = json.loads(d.pop("key_events_json", "[]"))
            d["important_quotes"] = json.loads(d.pop("important_quotes_json", "[]"))
            result.append(d)
        return result

    def cleanup_expired(self) -> int:
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                "DELETE FROM episode_summary WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            deleted = cursor.rowcount
            if deleted:
                self.connection.commit()
        return deleted

    def get_by_episode(self, episode_id: str) -> Optional[Dict[str, Any]]:
        with self.connection.locked():
            row = self.connection.execute(
                """
                SELECT episode_id, summary, key_events_json, mood_notes,
                       important_quotes_json, started_at_utc, ended_at_utc
                FROM episode_summary WHERE episode_id = ?
                """,
                (episode_id,),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["key_events"] = json.loads(d.pop("key_events_json", "[]"))
        d["important_quotes"] = json.loads(d.pop("important_quotes_json", "[]"))
        return d

    def unsummarized_episodes(self, limit: int = 1) -> List[str]:
        """Find episode_ids that have events in raw_event_log but no summary."""
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT DISTINCT el.episode_id
                FROM raw_event_log el
                LEFT JOIN episode_summary es ON el.episode_id = es.episode_id
                WHERE es.episode_id IS NULL
                ORDER BY el.created_at_utc DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [row["episode_id"] for row in rows]

    def clear_all(self) -> None:
        with self.connection.locked():
            self.connection.execute("DELETE FROM episode_summary")
            self.connection.commit()


class DailySummaryStore:
    """Stores daily summaries."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_date TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL,
                    key_events_json TEXT NOT NULL DEFAULT '[]',
                    stable_memory_candidates_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                )
                """
            )
            self.connection.commit()

    def save(
        self,
        local_date: str,
        summary: str,
        key_events: List[str],
        stable_memory_candidates: List[Dict[str, Any]],
        ttl_days: int = 30,
    ) -> int:
        from datetime import timedelta
        now = datetime.utcnow().isoformat()
        expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                INSERT OR REPLACE INTO daily_summary (
                    local_date, summary, key_events_json,
                    stable_memory_candidates_json, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    local_date,
                    summary,
                    json.dumps(key_events, ensure_ascii=False),
                    json.dumps(stable_memory_candidates, ensure_ascii=False),
                    now,
                    expires_at,
                ),
            )
            self.connection.commit()
            return cursor.lastrowid

    def recent(self, limit: int = 3) -> List[Dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT local_date, summary, key_events_json,
                       stable_memory_candidates_json
                FROM daily_summary
                WHERE expires_at IS NULL OR expires_at > ?
                ORDER BY local_date DESC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["key_events"] = json.loads(d.pop("key_events_json", "[]"))
            d["stable_memory_candidates"] = json.loads(
                d.pop("stable_memory_candidates_json", "[]")
            )
            result.append(d)
        return result

    def exists(self, local_date: str) -> bool:
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT 1 FROM daily_summary WHERE local_date = ?",
                (local_date,),
            ).fetchone()
        return row is not None

    def cleanup_expired(self) -> int:
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                "DELETE FROM daily_summary WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            deleted = cursor.rowcount
            if deleted:
                self.connection.commit()
        return deleted

    def clear_all(self) -> None:
        with self.connection.locked():
            self.connection.execute("DELETE FROM daily_summary")
            self.connection.commit()


class MaintenanceStateStore:
    """Persists maintenance tick state across restarts."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS maintenance_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self.connection.commit()

    def get(self, key: str) -> Optional[str]:
        with self.connection.locked():
            row = self.connection.execute(
                "SELECT value FROM maintenance_state WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            self.connection.execute(
                """
                INSERT OR REPLACE INTO maintenance_state (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, value, now),
            )
            self.connection.commit()

    def clear_all(self) -> None:
        with self.connection.locked():
            self.connection.execute("DELETE FROM maintenance_state")
            self.connection.commit()
