"""Stage 3.6: Schema migration tests."""
from app.pet.memory import MemoryStore
from app.pet.state import PetStateStore
from app.runtime.memory_store import (
    DailySummaryStore,
    EpisodeSummaryStore,
    MaintenanceStateStore,
    MemoryCandidateStore,
    MemoryManager,
    SummaryJobStore,
)


def test_memory_manager_creates_new_columns():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)

    # Verify new columns exist
    with state_store.connection.locked():
        rows = state_store.connection.execute("PRAGMA table_info(memory)").fetchall()
    col_names = {r["name"] for r in rows}
    for col in ["summary", "source_event_id", "source_episode_id",
                "confidence", "ttl_days", "expires_at", "updated_at", "usage_count"]:
        assert col in col_names, "Missing column: %s" % col


def test_existing_data_preserved_after_migration():
    state_store = PetStateStore(None)
    # Create old-style memory table and insert data
    old_store = MemoryStore(state_store.connection)
    old_store.save_from_update(
        type("MU", (), {"should_save": True, "content": "旧记忆"})()
    )

    # Now run migration
    mm = MemoryManager(state_store.connection)
    assert mm.count() >= 1

    # Old data should still be there
    scored = mm.scored_memories(limit=10)
    contents = [m["content"] for m in scored]
    assert "旧记忆" in contents


def test_new_tables_created():
    state_store = PetStateStore(None)
    MemoryManager(state_store.connection)
    MemoryCandidateStore(state_store.connection)
    SummaryJobStore(state_store.connection)
    EpisodeSummaryStore(state_store.connection)
    DailySummaryStore(state_store.connection)
    MaintenanceStateStore(state_store.connection)

    with state_store.connection.locked():
        rows = state_store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    table_names = {r["name"] for r in rows}
    for t in ["memory_candidate", "summary_job", "episode_summary",
              "daily_summary", "maintenance_state"]:
        assert t in table_names, "Missing table: %s" % t


def test_memory_indexes_created():
    state_store = PetStateStore(None)
    MemoryManager(state_store.connection)

    with state_store.connection.locked():
        rows = state_store.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    idx_names = {r["name"] for r in rows}
    assert "idx_memory_type_expires_importance" in idx_names
    assert "idx_memory_type_last_used" in idx_names
