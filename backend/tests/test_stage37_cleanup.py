"""Stage 3.7: Maintenance data cleanup tests."""
from datetime import datetime, timedelta

from app.pet.state import PetStateStore
from app.runtime.memory_store import (
    MemoryCandidateStore,
    SummaryJobStore,
)
from app.runtime.maintenance import MaintenanceService
from unittest.mock import MagicMock


def _make_service():
    state_store = PetStateStore(None)
    conn = state_store.connection
    cs = MemoryCandidateStore(conn)
    sjs = SummaryJobStore(conn)
    return cs, sjs


def test_old_processed_candidates_cleaned_by_processed_at():
    """Candidates processed >7 days ago should be cleaned up."""
    cs, sjs = _make_service()

    # Add a candidate and mark it processed 8 days ago
    cid = cs.add("ev1", "ep1", "测试内容", "llm_suggestion")
    old_time = (datetime.utcnow() - timedelta(days=8)).isoformat()
    with cs.connection.locked():
        cs.connection.execute(
            "UPDATE memory_candidate SET status = 'saved', processed_at = ? WHERE id = ?",
            (old_time, cid),
        )
        cs.connection.commit()

    service = MaintenanceService(
        curator=MagicMock(), summary_manager=MagicMock(),
        candidate_store=cs, summary_job_store=sjs,
        memory_manager=MagicMock(), episode_summary_store=MagicMock(),
        daily_summary_store=MagicMock(), maintenance_state=MagicMock(),
    )

    cleaned = service._cleanup_old_maintenance_data()
    assert cleaned >= 1

    # Verify it's gone
    with cs.connection.locked():
        row = cs.connection.execute(
            "SELECT 1 FROM memory_candidate WHERE id = ?", (cid,)
        ).fetchone()
    assert row is None


def test_old_done_jobs_cleaned_by_processed_at():
    """Done/failed jobs processed >3 days ago should be cleaned up."""
    cs, sjs = _make_service()

    # Enqueue a job and mark it done 4 days ago
    jid = sjs.enqueue("ep_old")
    old_time = (datetime.utcnow() - timedelta(days=4)).isoformat()
    with sjs.connection.locked():
        sjs.connection.execute(
            "UPDATE summary_job SET status = 'done', processed_at = ? WHERE id = ?",
            (old_time, jid),
        )
        sjs.connection.commit()

    service = MaintenanceService(
        curator=MagicMock(), summary_manager=MagicMock(),
        candidate_store=cs, summary_job_store=sjs,
        memory_manager=MagicMock(), episode_summary_store=MagicMock(),
        daily_summary_store=MagicMock(), maintenance_state=MagicMock(),
    )

    cleaned = service._cleanup_old_maintenance_data()
    assert cleaned >= 1


def test_pending_candidates_not_cleaned():
    """Pending candidates should NOT be cleaned up regardless of age."""
    cs, sjs = _make_service()

    # Add a pending candidate (created now, but status is pending)
    cs.add("ev1", "ep1", "待处理", "llm_suggestion")

    service = MaintenanceService(
        curator=MagicMock(), summary_manager=MagicMock(),
        candidate_store=cs, summary_job_store=sjs,
        memory_manager=MagicMock(), episode_summary_store=MagicMock(),
        daily_summary_store=MagicMock(), maintenance_state=MagicMock(),
    )

    cleaned = service._cleanup_old_maintenance_data()
    assert cleaned == 0

    # Verify it's still there
    assert cs.count_pending() == 1


def test_just_processed_not_cleaned():
    """A candidate that was just processed (processed_at is recent) should NOT be cleaned."""
    cs, sjs = _make_service()

    # Add and immediately process
    cid = cs.add("ev1", "ep1", "刚刚处理", "llm_suggestion")
    cs.mark_processed(cid, "saved")  # processed_at = now

    service = MaintenanceService(
        curator=MagicMock(), summary_manager=MagicMock(),
        candidate_store=cs, summary_job_store=sjs,
        memory_manager=MagicMock(), episode_summary_store=MagicMock(),
        daily_summary_store=MagicMock(), maintenance_state=MagicMock(),
    )

    cleaned = service._cleanup_old_maintenance_data()
    assert cleaned == 0
