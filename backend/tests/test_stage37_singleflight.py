"""Stage 3.7: MaintenanceService single-flight guard tests."""
import threading
import time
from unittest.mock import MagicMock

from app.pet.state import PetStateStore
from app.runtime.maintenance import MaintenanceService
from app.runtime.memory_store import (
    DailySummaryStore,
    EpisodeSummaryStore,
    MaintenanceStateStore,
    MemoryCandidateStore,
    MemoryManager,
    SummaryJobStore,
)


def _make_service(**overrides):
    state_store = PetStateStore(None)
    conn = state_store.connection
    mm = MemoryManager(conn)
    cs = MemoryCandidateStore(conn)
    sjs = SummaryJobStore(conn)
    ess = EpisodeSummaryStore(conn)
    dss = DailySummaryStore(conn)
    ms = MaintenanceStateStore(conn)
    curator = MagicMock()
    curator.curate_batch.return_value = {"saved": 0, "ignored": 0, "errors": 0}
    curator.consolidate_batch.return_value = {"merged": 0, "skipped": 0}
    sm = MagicMock()
    sm.cleanup_expired.return_value = {"episode_summaries": 0, "daily_summaries": 0}
    sm.timezone_name = "Asia/Shanghai"
    cfg = {
        "maintenance_min_interval_seconds": 0,
        "maintenance_max_items_per_tick": 8,
        **overrides,
    }
    return MaintenanceService(
        curator=curator,
        summary_manager=sm,
        candidate_store=cs,
        summary_job_store=sjs,
        memory_manager=mm,
        episode_summary_store=ess,
        daily_summary_store=dss,
        maintenance_state=ms,
        event_log_store=MagicMock(),
        episode_store=MagicMock(),
        config=cfg,
    )


def test_concurrent_ticks_only_one_runs():
    """Only one tick should execute at a time; others return skipped."""
    service = _make_service()
    results = []
    barrier = threading.Barrier(3, timeout=5)

    def run_tick():
        barrier.wait()
        result = service.tick(force=True)
        results.append(result)

    threads = [threading.Thread(target=run_tick) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    skipped_count = sum(1 for r in results if r.get("skipped"))
    executed_count = sum(1 for r in results if not r.get("skipped"))
    assert executed_count == 1, "Expected exactly 1 tick to execute, got %d" % executed_count
    assert skipped_count == 2, "Expected 2 ticks to be skipped, got %d" % skipped_count


def test_lock_released_after_tick():
    """After a tick completes, the next tick should be able to acquire the lock."""
    service = _make_service()
    r1 = service.tick(force=True)
    assert not r1.get("skipped"), "First tick should execute"
    r2 = service.tick(force=True)
    assert not r2.get("skipped"), "Second tick should execute after first releases lock"


def test_lock_released_on_exception():
    """If a tick raises, the lock should still be released."""
    service = _make_service()
    # Force an error inside tick
    service.curator.curate_batch.side_effect = RuntimeError("boom")
    r1 = service.tick(force=True)
    # Should not be skipped (it ran, just errored)
    assert not r1.get("skipped")
    # Next tick should still work
    service.curator.curate_batch.side_effect = None
    service.curator.curate_batch.return_value = {"saved": 0, "ignored": 0, "errors": 0}
    r2 = service.tick(force=True)
    assert not r2.get("skipped"), "Lock should be released after exception"
