from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from app.runtime.memory_store import (
    DailySummaryStore,
    EpisodeSummaryStore,
    MemoryCandidateStore,
    MemoryManager,
    MaintenanceStateStore,
    SummaryJobStore,
)

if TYPE_CHECKING:
    from app.runtime.backup import DatabaseBackupManager

logger = logging.getLogger(__name__)

_TZ_OFFSETS = {
    "Asia/Shanghai": timedelta(hours=8),
    "Asia/Tokyo": timedelta(hours=9),
    "US/Eastern": timedelta(hours=-5),
    "US/Pacific": timedelta(hours=-8),
    "Europe/London": timedelta(hours=0),
}


class MaintenanceService:
    """Lazy maintenance: processes small batches of candidates and summaries.

    Called AFTER dispatcher returns response (outside event lock).
    Uses maintenance_state table to persist tick timing across restarts.
    Single-flight guard ensures at most one tick runs at a time.
    """

    def __init__(
        self,
        curator: Any,
        summary_manager: Any,
        candidate_store: MemoryCandidateStore,
        summary_job_store: SummaryJobStore,
        memory_manager: MemoryManager,
        episode_summary_store: EpisodeSummaryStore,
        daily_summary_store: DailySummaryStore,
        maintenance_state: MaintenanceStateStore,
        event_log_store: Any = None,
        episode_store: Any = None,
        config: Optional[Dict[str, Any]] = None,
        memory_card_manager: Any = None,
        backup_manager: Optional["DatabaseBackupManager"] = None,
        connection: Any = None,
        memory_judgment_queue: Any = None,
        notebook_manager: Any = None,
        nightly_cleanup_runner: Any = None,
    ) -> None:
        cfg = config or {}
        self.curator = curator
        self.summary_manager = summary_manager
        self.candidate_store = candidate_store
        self.summary_job_store = summary_job_store
        self.memory_manager = memory_manager
        self.episode_summary_store = episode_summary_store
        self.daily_summary_store = daily_summary_store
        self.maintenance_state = maintenance_state
        self.event_log_store = event_log_store
        self.episode_store = episode_store
        self.memory_card_manager = memory_card_manager
        self.backup_manager = backup_manager
        self.connection = connection
        self.memory_judgment_queue = memory_judgment_queue
        self.notebook_manager = notebook_manager
        self.nightly_cleanup_runner = nightly_cleanup_runner
        self.min_interval_seconds = cfg.get("maintenance_min_interval_seconds", 300)
        self.max_items_per_tick = cfg.get("maintenance_max_items_per_tick", 8)
        self.daily_summary_trigger_hour = cfg.get("daily_summary_trigger_hour", 6)
        self.consolidation_enabled = cfg.get("consolidation_enabled", True)
        self.candidate_cleanup_days = cfg.get("candidate_cleanup_days", 7)
        self.job_cleanup_days = cfg.get("job_cleanup_days", 3)
        self.wal_checkpoint_interval_seconds = cfg.get("wal_checkpoint_interval_seconds", 1800)
        self._running_lock = threading.Lock()
        self._write_count = 0
        self._last_wal_checkpoint_at: Optional[datetime] = None
        self._wal_checkpoint_retry_after: Optional[datetime] = None
        self._last_backup_date: Optional[str] = None

    def tick(self, force: bool = False) -> Dict[str, int]:
        """Run one small maintenance batch. Returns activity summary.

        Single-flight: if a tick is already running, returns skipped immediately.
        """
        if not self._running_lock.acquire(blocking=False):
            return {"skipped": True, "reason": "already_running"}
        try:
            if not force and not self._should_run():
                return {"skipped": True}
            return self._tick_inner(force=force)
        finally:
            self._running_lock.release()

    def _tick_inner(self, force: bool = False) -> Dict[str, int]:
        """Actual tick logic, protected by single-flight lock."""
        result: Dict[str, int] = {}
        self.maintenance_state.set("last_tick_at", datetime.utcnow().isoformat())

        # Priority 1: Process pending memory candidates (curator)
        try:
            if self.candidate_store.count_pending() > 0:
                curator_result = self.curator.curate_batch(self.candidate_store)
                result.update(curator_result)
                if curator_result.get("saved", 0) > 0 and self.memory_card_manager:
                    try:
                        card_result = self.memory_card_manager.rebuild("curator_saved")
                        result["cards_rebuilt"] = card_result.get("items_written", 0)
                    except Exception:
                        logger.warning("Card rebuild after curator save failed", exc_info=True)
                return result
        except Exception:
            logger.warning("Curator batch failed", exc_info=True)
            result["curator_error"] = 1

        # Priority 1.3: Nightly cleanup (V1.3, once per day)
        try:
            if self.nightly_cleanup_runner and self.nightly_cleanup_runner.should_run(force=force):
                cleanup_result = self.nightly_cleanup_runner.run(force=force)
                if cleanup_result:
                    result.update({"cleanup_%s" % k: v for k, v in cleanup_result.items()})
                    return result
        except Exception:
            logger.warning("Nightly cleanup failed", exc_info=True)

        # Priority 1.5: Process memory judgment queue (V1.3)
        try:
            if self.memory_judgment_queue and self.memory_judgment_queue.pending_count() > 0:
                judgment = self.memory_judgment_queue.process_one()
                if judgment and judgment.get("should_write") and self.notebook_manager:
                    self.notebook_manager.append_line(
                        judgment["target"], judgment["category"], judgment["content"]
                    )
                    result["memory_judgment_written"] = 1
        except Exception:
            logger.warning("Memory judgment processing failed", exc_info=True)

        # Priority 2: Process pending episode summary jobs
        try:
            pending_jobs = self.summary_job_store.pending(limit=1)
            if pending_jobs:
                job = pending_jobs[0]
                if job["job_type"] == "episode":
                    self._process_episode_summary_job(job)
                    result["summaries_generated"] = 1
                return result
        except Exception:
            logger.warning("Summary job processing failed", exc_info=True)
            result["summary_error"] = 1

        # Priority 2.5: Daily summary for YESTERDAY (if due)
        try:
            if self._daily_summary_due():
                target_date = self._yesterday_local_date()
                # If already exists (e.g. manual trigger), treat as done
                if self.daily_summary_store.exists(target_date):
                    self.maintenance_state.set("last_daily_summary_date", target_date)
                elif self._all_episode_summaries_processed(target_date):
                    daily_result = self._process_daily_summary(target_date)
                    if daily_result:
                        result["daily_summary_generated"] = 1
                        self.maintenance_state.set("last_daily_summary_date", target_date)
                    else:
                        # No data for that date — mark as done, don't retry forever
                        self.maintenance_state.set("last_daily_summary_date", target_date)
                    return result
                # If episode summaries not yet processed, fall through to other priorities
        except Exception:
            logger.warning("Daily summary check failed", exc_info=True)

        # Priority 3: Cleanup expired data
        try:
            cleanup = self.summary_manager.cleanup_expired()
            if any(v > 0 for v in cleanup.values()):
                result.update({"cleanup_%s" % k: v for k, v in cleanup.items()})
                return result
        except Exception:
            logger.warning("Cleanup failed", exc_info=True)

        # Priority 4: Memory cleanup
        try:
            deleted = self.memory_manager.cleanup_expired()
            if deleted > 0:
                result["memory_expired"] = deleted
                if self.memory_card_manager:
                    try:
                        self.memory_card_manager.rebuild("memory_expired")
                    except Exception:
                        logger.warning("Card rebuild after expiration failed", exc_info=True)
                return result
        except Exception:
            logger.warning("Memory cleanup failed", exc_info=True)

        # Priority 5: Cleanup old processed candidates and done jobs
        try:
            cleaned = self._cleanup_old_maintenance_data()
            if cleaned > 0:
                result["maintenance_cleaned"] = cleaned
                return result
        except Exception:
            logger.warning("Maintenance cleanup failed", exc_info=True)

        # Priority 6: Memory consolidation (once per day)
        try:
            if self.consolidation_enabled and self._consolidation_due():
                consolidated = self.curator.consolidate_batch(self.memory_manager)
                if consolidated:
                    result.update(consolidated)
                    self.maintenance_state.set(
                        "last_consolidation_date", self._current_local_date()
                    )
                    if consolidated.get("merged", 0) > 0 and self.memory_card_manager:
                        try:
                            self.memory_card_manager.rebuild("memory_merged")
                        except Exception:
                            logger.warning("Card rebuild after merge failed", exc_info=True)
                    return result
        except Exception:
            logger.warning("Memory consolidation failed", exc_info=True)

        return result

    def _should_run(self) -> bool:
        """Check if enough time has passed since last tick."""
        last = self.maintenance_state.get("last_tick_at")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            elapsed = (datetime.utcnow() - last_dt).total_seconds()
            return elapsed >= self.min_interval_seconds
        except (ValueError, TypeError):
            return True

    def _get_local_now(self) -> datetime:
        """Get current local time based on timezone config."""
        tz_name = self.summary_manager.timezone_name if self.summary_manager else "Asia/Shanghai"
        offset = _TZ_OFFSETS.get(tz_name, timedelta(hours=8))
        return datetime.utcnow() + offset

    def _current_local_date(self) -> str:
        return self._get_local_now().strftime("%Y-%m-%d")

    def _yesterday_local_date(self) -> str:
        return (self._get_local_now() - timedelta(days=1)).strftime("%Y-%m-%d")

    def _daily_summary_due(self) -> bool:
        """Check if daily summary for yesterday is due."""
        local_now = self._get_local_now()
        if local_now.hour < self.daily_summary_trigger_hour:
            return False
        target_date = self._yesterday_local_date()
        last = self.maintenance_state.get("last_daily_summary_date")
        return last != target_date

    def _all_episode_summaries_processed(self, target_date: str) -> bool:
        """Check that all episode summaries for target_date are done (no pending jobs)."""
        pending_count = self.summary_job_store.count_pending_for_date(
            target_date,
            episode_store=self.episode_store,
            timezone_name=self.summary_manager.timezone_name if self.summary_manager else "Asia/Shanghai",
        )
        return pending_count == 0

    def _process_daily_summary(self, target_date: str) -> Optional[Dict[str, Any]]:
        """Generate daily summary for target_date. Returns result dict or None."""
        result = self.summary_manager.generate_daily_summary(target_date)
        return result

    def _cleanup_old_maintenance_data(self) -> int:
        """Remove old processed candidates and done/failed jobs.

        Uses processed_at (not created_at) and Python-generated ISO cutoff.
        Cutoffs come from config (candidate_cleanup_days, job_cleanup_days).
        """
        now = datetime.utcnow()
        candidate_cutoff = (now - timedelta(days=self.candidate_cleanup_days)).isoformat()
        job_cutoff = (now - timedelta(days=self.job_cleanup_days)).isoformat()

        cleaned = 0
        with self.candidate_store.connection.locked():
            cur = self.candidate_store.connection.execute(
                "DELETE FROM memory_candidate WHERE status != 'pending' AND processed_at < ?",
                (candidate_cutoff,),
            )
            cleaned += cur.rowcount
            if cur.rowcount:
                self.candidate_store.connection.commit()

        with self.summary_job_store.connection.locked():
            cur = self.summary_job_store.connection.execute(
                "DELETE FROM summary_job WHERE status IN ('done', 'failed') AND processed_at < ?",
                (job_cutoff,),
            )
            cleaned += cur.rowcount
            if cur.rowcount:
                self.summary_job_store.connection.commit()

        return cleaned

    def _consolidation_due(self) -> bool:
        """Check if memory consolidation is due (once per day)."""
        last = self.maintenance_state.get("last_consolidation_date")
        today = self._current_local_date()
        return last != today

    def _process_episode_summary_job(self, job: Dict[str, Any]) -> None:
        """Process a single episode summary job."""
        episode_id = job["episode_id"]
        job_id = job["id"]
        try:
            result = self.summary_manager.generate_episode_summary(
                episode_id=episode_id,
                event_log_store=self.event_log_store,
                episode_store=self.episode_store,
            )
            if result:
                self.summary_job_store.mark_done(job_id)
            else:
                self.summary_job_store.mark_failed(
                    job_id,
                    error_message="summary manager returned no summary",
                )
        except Exception as exc:
            logger.warning("Episode summary failed for %s", episode_id, exc_info=True)
            self.summary_job_store.mark_failed(job_id, error_message=str(exc))

    def rebuild_memory_cards(self, reason: str) -> Dict[str, int]:
        """Public facade for explicit card rebuilds (e.g., manual debug)."""
        if not self.memory_card_manager:
            return {"error": "no_card_manager"}
        return self.memory_card_manager.rebuild(reason)

    def record_write(self) -> None:
        """Increment write counter for WAL checkpoint scheduling."""
        self._write_count += 1

    def wal_checkpoint_if_due(self) -> bool:
        """Run PASSIVE WAL checkpoint if due (time or write count).

        Returns True if checkpoint was run.
        """
        now = datetime.utcnow()
        retry_after = getattr(self, "_wal_checkpoint_retry_after", None)
        if retry_after is not None and now < retry_after:
            return False

        time_due = False
        if self._last_wal_checkpoint_at is None:
            time_due = True
        else:
            elapsed = (now - self._last_wal_checkpoint_at).total_seconds()
            time_due = elapsed >= self.wal_checkpoint_interval_seconds

        write_due = self._write_count >= 100

        if not time_due and not write_due:
            return False

        if self.connection is None:
            return False

        try:
            with self.connection.locked():
                raw = getattr(self.connection, "_connection", self.connection)
                wal_row = raw.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                wal_bytes = int(wal_row[1]) if wal_row and len(wal_row) > 1 else 0
            self._last_wal_checkpoint_at = now
            self._wal_checkpoint_retry_after = None
            self._write_count = 0
            if wal_bytes > 0:
                logger.info("WAL checkpoint: %d bytes", wal_bytes)
            return True
        except Exception:
            self._wal_checkpoint_retry_after = now + timedelta(minutes=5)
            logger.warning("WAL checkpoint failed", exc_info=True)
            return False

    def daily_backup_if_due(self) -> bool:
        """Create a routine backup if not done today.

        Returns True if backup was created.
        """
        if self.backup_manager is None:
            return False

        today = datetime.utcnow().strftime("%Y-%m-%d")
        if self._last_backup_date == today:
            return False

        path = self.backup_manager.create_routine_backup()
        if path:
            self._last_backup_date = today
            logger.info("Daily backup created: %s", path.name)
            return True
        return False

    def wal_truncate_idle(self) -> bool:
        """TRUNCATE WAL during idle/shutdown (only when no active writers).

        Returns True if TRUNCATE was attempted.
        """
        if self.connection is None:
            return False
        try:
            with self.connection.locked():
                raw = getattr(self.connection, "_connection", self.connection)
                raw.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.info("WAL TRUNCATE completed")
            return True
        except Exception:
            logger.warning("WAL TRUNCATE failed", exc_info=True)
            return False
