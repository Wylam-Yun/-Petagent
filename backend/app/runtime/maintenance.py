from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from app.runtime.memory_store import (
    DailySummaryStore,
    EpisodeSummaryStore,
    MemoryCandidateStore,
    MemoryManager,
    MaintenanceStateStore,
    SummaryJobStore,
)

logger = logging.getLogger(__name__)


class MaintenanceService:
    """Lazy maintenance: processes small batches of candidates and summaries.

    Called AFTER dispatcher returns response (outside event lock).
    Uses maintenance_state table to persist tick timing across restarts.
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
        self.min_interval_seconds = cfg.get("maintenance_min_interval_seconds", 300)
        self.max_items_per_tick = cfg.get("maintenance_max_items_per_tick", 8)

    def tick(self, force: bool = False) -> Dict[str, int]:
        """Run one small maintenance batch. Returns activity summary."""
        if not force and not self._should_run():
            return {"skipped": True}

        result: Dict[str, int] = {}
        self.maintenance_state.set("last_tick_at", datetime.utcnow().isoformat())

        # Priority 1: Process pending memory candidates (curator)
        try:
            if self.candidate_store.count_pending() > 0:
                curator_result = self.curator.curate_batch(self.candidate_store)
                result.update(curator_result)
                return result
        except Exception:
            logger.warning("Curator batch failed", exc_info=True)
            result["curator_error"] = 1

        # Priority 2: Process pending summary jobs
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
        except Exception:
            logger.warning("Memory cleanup failed", exc_info=True)

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
                self.summary_job_store.mark_failed(job_id)
        except Exception:
            logger.warning("Episode summary failed for %s", episode_id, exc_info=True)
            self.summary_job_store.mark_failed(job_id)
