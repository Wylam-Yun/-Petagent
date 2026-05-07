"""Stage 3.7: Automated daily summary tests."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

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
    sm.generate_daily_summary.return_value = {"local_date": "2026-05-06", "summary": "test"}
    cfg = {
        "maintenance_min_interval_seconds": 0,
        "maintenance_max_items_per_tick": 8,
        "daily_summary_trigger_hour": 6,
        **overrides,
    }
    service = MaintenanceService(
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
    return service


def test_daily_summary_triggered_after_6am():
    """Daily summary should trigger when local hour >= 6 and target date hasn't been summarized."""
    service = _make_service()
    # Mock local time to be 7am on 2026-05-07
    fake_now = datetime(2026, 5, 7, 7, 0, 0)  # local time
    utc_now = fake_now - timedelta(hours=8)  # Asia/Shanghai = UTC+8

    with patch("app.runtime.maintenance.datetime") as mock_dt:
        mock_dt.utcnow.return_value = utc_now
        mock_dt.fromisoformat = datetime.fromisoformat
        result = service._tick_inner(force=True)

    # Should have triggered daily summary for 2026-05-06
    service.summary_manager.generate_daily_summary.assert_called_once_with("2026-05-06")


def test_daily_summary_not_triggered_before_6am():
    """Daily summary should NOT trigger before the configured trigger hour."""
    service = _make_service(daily_summary_trigger_hour=6)
    # Mock local time to be 5am
    fake_now = datetime(2026, 5, 7, 5, 0, 0)
    utc_now = fake_now - timedelta(hours=8)

    with patch("app.runtime.maintenance.datetime") as mock_dt:
        mock_dt.utcnow.return_value = utc_now
        mock_dt.fromisoformat = datetime.fromisoformat
        service._tick_inner(force=True)

    service.summary_manager.generate_daily_summary.assert_not_called()


def test_daily_summary_not_triggered_twice():
    """Once a daily summary is generated and saved, it shouldn't trigger again for the same date."""
    service = _make_service()
    # Set last_daily_summary_date to yesterday
    service.maintenance_state.set("last_daily_summary_date", "2026-05-06")

    fake_now = datetime(2026, 5, 7, 8, 0, 0)
    utc_now = fake_now - timedelta(hours=8)

    with patch("app.runtime.maintenance.datetime") as mock_dt:
        mock_dt.utcnow.return_value = utc_now
        mock_dt.fromisoformat = datetime.fromisoformat
        service._tick_inner(force=True)

    service.summary_manager.generate_daily_summary.assert_not_called()


def test_daily_summary_written_after_success():
    """last_daily_summary_date should be set AFTER successful generation, not on enqueue."""
    service = _make_service()
    fake_now = datetime(2026, 5, 7, 7, 0, 0)
    utc_now = fake_now - timedelta(hours=8)

    # Before tick, no last_daily_summary_date
    assert service.maintenance_state.get("last_daily_summary_date") is None

    with patch("app.runtime.maintenance.datetime") as mock_dt:
        mock_dt.utcnow.return_value = utc_now
        mock_dt.fromisoformat = datetime.fromisoformat
        service._tick_inner(force=True)

    # After successful tick, should be set to yesterday
    assert service.maintenance_state.get("last_daily_summary_date") == "2026-05-06"


def test_daily_summary_no_data_marks_done():
    """When no episode summaries exist for yesterday, treat as no-op and mark done."""
    service = _make_service()
    service.summary_manager.generate_daily_summary.return_value = None  # No data

    fake_now = datetime(2026, 5, 7, 7, 0, 0)
    utc_now = fake_now - timedelta(hours=8)

    with patch("app.runtime.maintenance.datetime") as mock_dt:
        mock_dt.utcnow.return_value = utc_now
        mock_dt.fromisoformat = datetime.fromisoformat
        service._tick_inner(force=True)

    # Should be marked as done (no-op) so cleanup/consolidation can still run
    assert service.maintenance_state.get("last_daily_summary_date") == "2026-05-06"


def test_daily_summary_blocks_when_pending_episode_jobs():
    """Daily summary should not trigger if pending episode summary jobs exist for target date."""
    service = _make_service()
    # Mock count_pending_for_date to return > 0
    service.summary_job_store.count_pending_for_date = MagicMock(return_value=2)

    fake_now = datetime(2026, 5, 7, 7, 0, 0)
    utc_now = fake_now - timedelta(hours=8)

    with patch("app.runtime.maintenance.datetime") as mock_dt:
        mock_dt.utcnow.return_value = utc_now
        mock_dt.fromisoformat = datetime.fromisoformat
        service._tick_inner(force=True)

    service.summary_manager.generate_daily_summary.assert_not_called()
