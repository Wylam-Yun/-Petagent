"""Stage 3.6: MemoryCurator tests."""
from app.pet.state import PetStateStore
from app.runtime.memory_curator import MemoryCurator
from app.runtime.memory_store import MemoryCandidateStore, MemoryManager


class MockCuratorLLM:
    """Mock LLM that returns predefined curator decisions."""
    name = "mock_curator"

    def __init__(self, decisions=None):
        self._decisions = decisions or []

    def complete_json(self, messages):
        return {"decisions": self._decisions}


def test_curator_saves_user_preference():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    cs.add("evt-1", "ep-1", "我喜欢短回复", "explicit_command")

    llm = MockCuratorLLM([{
        "save": True,
        "memory_type": "user_preference",
        "content": "用户喜欢短回复",
        "importance": 4,
        "ttl_days": 30,
        "confidence": 0.9,
        "merge_with_memory_id": None,
        "reason": "明确偏好",
    }])
    curator = MemoryCurator(llm, mm)
    result = curator.curate_batch(cs)

    assert result["saved"] == 1
    assert result["ignored"] == 0
    assert result["errors"] == 0
    assert cs.count_pending() == 0

    scored = mm.scored_memories(limit=5)
    assert any(m["content"] == "用户喜欢短回复" for m in scored)


def test_curator_saves_relationship():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    cs.add("evt-1", "ep-1", "以后叫我 William", "explicit_command")

    llm = MockCuratorLLM([{
        "save": True,
        "memory_type": "relationship",
        "content": "用户希望被叫 William",
        "importance": 5,
        "ttl_days": None,
        "confidence": 0.95,
        "merge_with_memory_id": None,
        "reason": "称呼偏好",
    }])
    curator = MemoryCurator(llm, mm)
    result = curator.curate_batch(cs)

    assert result["saved"] == 1
    scored = mm.scored_memories(limit=5)
    types = [m["type"] for m in scored]
    assert "relationship" in types


def test_curator_ignores_trivial():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    cs.add("evt-1", "ep-1", "我刚刚喝了水", "llm_suggestion")

    llm = MockCuratorLLM([{
        "save": False,
        "reason": "流水账，不值得记住",
    }])
    curator = MemoryCurator(llm, mm)
    result = curator.curate_batch(cs)

    assert result["saved"] == 0
    assert result["ignored"] == 1
    assert mm.count() == 0


def test_curator_handles_llm_failure():
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
    # Candidate should be marked for retry, not left pending
    assert cs.count_pending() == 0


def test_curator_rejects_sensitive_content():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    cs.add("evt-1", "ep-1", "我的密码是123456", "llm_suggestion")

    llm = MockCuratorLLM([{
        "save": True,
        "memory_type": "important_event",
        "content": "用户的密码是123456",
        "importance": 3,
        "confidence": 0.8,
        "merge_with_memory_id": None,
        "reason": "test",
    }])
    curator = MemoryCurator(llm, mm)
    result = curator.curate_batch(cs)

    # Should be rejected due to sensitive marker "密码"
    assert result["saved"] == 0


def test_curator_merge_with_existing():
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    cs = MemoryCandidateStore(state_store.connection)

    # Create an existing memory
    mem_id = mm.save_curated(
        memory_type="user_preference",
        content="用户喜欢短回复",
        importance=3,
    )
    assert mem_id is not None

    # Candidate that should merge
    cs.add("evt-2", "ep-1", "我喜欢简短的回复", "explicit_command")

    llm = MockCuratorLLM([{
        "save": True,
        "memory_type": "user_preference",
        "content": "用户喜欢简短回复",
        "importance": 4,
        "confidence": 0.9,
        "merge_with_memory_id": mem_id,
        "reason": "重复偏好，合并",
    }])
    curator = MemoryCurator(llm, mm)
    result = curator.curate_batch(cs)

    assert result["saved"] == 1
    assert mm.count() == 1  # Still only 1 memory (merged)
