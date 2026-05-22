"""Tests for STAB-025: Memory candidate retry with exponential backoff."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.db import PetStateStore
from app.runtime.memory_store import MemoryCandidateStore


def _make_store() -> MemoryCandidateStore:
    return MemoryCandidateStore(PetStateStore(None).connection)


def test_mark_retryable_sets_status_and_next_retry():
    cs = _make_store()
    cid = cs.add("evt-1", "ep-1", "测试内容", "explicit_command")
    cs.mark_retryable(cid, attempt_count=1)

    # Should no longer be pending
    assert cs.count_pending() == 0

    # Should be fetched by pending() since next_retry_at is in the future
    # (but the query filters by next_retry_at <= now, so it won't show up yet)
    rows = cs.pending(limit=10)
    assert len(rows) == 0


def test_mark_retryable_expired_backoff_returns_candidate():
    cs = _make_store()
    cid = cs.add("evt-1", "ep-1", "过期候选", "explicit_command")

    # Manually set next_retry_at to the past
    past = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
    with cs.connection.locked():
        cs.connection.execute(
            "UPDATE memory_candidate SET status = 'retryable', attempt_count = 1, next_retry_at = ? WHERE id = ?",
            (past, cid),
        )
        cs.connection.commit()

    rows = cs.pending(limit=10)
    assert len(rows) == 1
    assert rows[0]["id"] == cid


def test_mark_retryable_max_attempts_becomes_error():
    cs = _make_store()
    cid = cs.add("evt-1", "ep-1", "超限候选", "explicit_command")
    cs.mark_retryable(cid, attempt_count=5)

    # Should be marked as error, not retryable
    assert cs.count_pending() == 0
    rows = cs.pending(limit=10)
    assert len(rows) == 0


def test_exponential_backoff_increasing_delay():
    cs = _make_store()
    cid = cs.add("evt-1", "ep-1", "递增测试", "explicit_command")

    # attempt 1: delay = 2^1 = 2 min
    cs.mark_retryable(cid, attempt_count=1)
    with cs.connection.locked():
        row = cs.connection.execute(
            "SELECT next_retry_at FROM memory_candidate WHERE id = ?", (cid,)
        ).fetchone()

    next_retry = datetime.fromisoformat(row["next_retry_at"])
    now = datetime.utcnow()
    delay = (next_retry - now).total_seconds() / 60
    # Should be approximately 2 minutes (allow 10s tolerance)
    assert 1.5 < delay < 2.5


def test_exponential_backoff_last_valid_attempt():
    cs = _make_store()
    cid = cs.add("evt-1", "ep-1", "最后有效尝试", "explicit_command")

    # attempt 4: 2^4 = 16 min (max valid attempt before >= 5 becomes error)
    cs.mark_retryable(cid, attempt_count=4)
    with cs.connection.locked():
        row = cs.connection.execute(
            "SELECT next_retry_at, status FROM memory_candidate WHERE id = ?", (cid,)
        ).fetchone()

    assert row["status"] == "retryable"
    next_retry = datetime.fromisoformat(row["next_retry_at"])
    now = datetime.utcnow()
    delay = (next_retry - now).total_seconds() / 60
    # Should be approximately 16 minutes (allow 1min tolerance)
    assert 15 < delay < 17


def test_pending_includes_both_pending_and_retryable():
    cs = _make_store()
    # Add a normal pending candidate
    cs.add("evt-1", "ep-1", "正常待处理", "explicit_command")
    # Add a retryable candidate with past next_retry_at
    cid2 = cs.add("evt-2", "ep-2", "可重试", "explicit_command")
    past = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
    with cs.connection.locked():
        cs.connection.execute(
            "UPDATE memory_candidate SET status = 'retryable', attempt_count = 1, next_retry_at = ? WHERE id = ?",
            (past, cid2),
        )
        cs.connection.commit()

    rows = cs.pending(limit=10)
    assert len(rows) == 2


def test_curator_marks_retryable_on_llm_failure():
    from app.runtime.memory_curator import MemoryCurator
    from app.runtime.memory_store import MemoryManager

    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    cs.add("evt-1", "ep-1", "重要记忆", "explicit_command")

    class FailingLLM:
        name = "failing"
        def complete_json(self, messages):
            raise RuntimeError("LLM unavailable")

    curator = MemoryCurator(FailingLLM(), mm)
    result = curator.curate_batch(cs)

    assert result["retried"] == 1
    assert result["errors"] == 0
    assert cs.count_pending() == 0
