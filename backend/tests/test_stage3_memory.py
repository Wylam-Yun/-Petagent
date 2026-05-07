"""Stage 3 memory tests — updated to use MemoryManager (old MemoryStore removed)."""
from app.pet.state import PetStateStore
from app.runtime.memory_store import MemoryManager


def test_memory_manager_save_curated():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)

    mid = mm.save_curated(
        memory_type="user_preference",
        content="用户喜欢短回复",
        importance=4,
    )

    assert mid is not None
    scored = mm.scored_memories(limit=10)
    contents = [m["content"] for m in scored]
    assert "用户喜欢短回复" in contents


def test_memory_manager_rejects_invalid_type():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)

    mid = mm.save_curated(memory_type="invalid_type", content="test")
    assert mid is None


def test_memory_manager_rejects_empty_content():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)

    mid = mm.save_curated(memory_type="user_preference", content="")
    assert mid is None
