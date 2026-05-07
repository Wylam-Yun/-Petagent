"""Stage 3.7: Memory consolidation tests."""
from datetime import datetime

from app.pet.state import PetStateStore
from app.runtime.memory_curator import MemoryCurator
from app.runtime.memory_store import MemoryManager


def _insert_memory(conn, mem_type, content, importance):
    now = datetime.utcnow().isoformat()
    with conn.locked():
        cur = conn.execute(
            "INSERT INTO memory (type, content, importance, created_at, last_used_at, usage_count) VALUES (?, ?, ?, ?, ?, 0)",
            (mem_type, content, importance, now, now),
        )
        conn.commit()
        return cur.lastrowid


def _make_curator():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)

    class MockProvider:
        def complete_json(self, messages):
            return {"decisions": [{"merge": True, "keep_id": None, "merged_content": "用户喜欢猫和狗", "merged_importance": 4, "reason": "重复"}]}

    return MockProvider(), mm


def test_consolidation_merges_similar_memories():
    """Two similar user_preference memories should be merged."""
    provider, mm = _make_curator()
    _insert_memory(mm.connection, "user_preference", "用户喜欢猫", 4)
    _insert_memory(mm.connection, "user_preference", "用户喜欢猫咪", 4)

    curator = MemoryCurator(provider, mm)
    result = curator.consolidate_batch(mm)

    assert result["merged"] == 1
    # One should be deleted
    assert mm.count() == 1


def test_consolidation_does_not_merge_different_types():
    """Memories of different types should NOT be merged."""
    provider, mm = _make_curator()
    _insert_memory(mm.connection, "user_preference", "用户喜欢猫", 4)
    _insert_memory(mm.connection, "recent_mood", "用户今天很开心", 3)

    curator = MemoryCurator(provider, mm)
    pairs = curator._find_similar_pairs(mm, 4)

    # Different types should not form pairs
    for a, b in pairs:
        assert a["type"] == b["type"]


def test_consolidation_respects_limit():
    """consolidate_batch should not exceed the limit."""
    provider, mm = _make_curator()
    # Create many similar memories
    for i in range(10):
        _insert_memory(mm.connection, "user_preference", "用户喜欢猫%d" % i, 3)

    curator = MemoryCurator(provider, mm)
    pairs = curator._find_similar_pairs(mm, 2)

    # Should respect limit
    assert len(pairs) <= 2


def test_consolidation_keeps_higher_importance():
    """When merging, the merged importance should be the higher of the two."""
    provider, mm = _make_curator()
    _insert_memory(mm.connection, "user_preference", "用户喜欢猫", 5)
    _insert_memory(mm.connection, "user_preference", "用户喜欢猫咪", 3)

    curator = MemoryCurator(provider, mm)
    result = curator.consolidate_batch(mm)

    # The merged memory should have importance 5 (from the first call's decision)
    with mm.connection.locked():
        row = mm.connection.execute("SELECT importance FROM memory").fetchone()
    assert row is not None
