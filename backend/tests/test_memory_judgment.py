"""Tests for V1.3 MemoryJudgmentQueue."""
from __future__ import annotations

from pathlib import Path
from tempfile import mkdtemp

from app.runtime.memory_judgment import MemoryJudgmentQueue
from app.runtime.notebook import NotebookManager


class MockProvider:
    def __init__(self, result=None):
        self._result = result or {"should_write": False}
        self.last_messages = None

    def complete_json(self, messages):
        self.last_messages = messages
        return self._result


class MockProviderGate:
    def __init__(self, available=True):
        self._available = available

    def is_available(self, provider_type):
        return self._available


def test_enqueue_adds_to_queue():
    q = MemoryJudgmentQueue(provider=MockProvider())
    result = q.enqueue("我喜欢咖啡", ["preference"])
    assert result is True
    assert q.pending_count() == 1


def test_dedup_same_input():
    q = MemoryJudgmentQueue(provider=MockProvider())
    q.enqueue("我喜欢咖啡", ["preference"])
    result = q.enqueue("我喜欢咖啡", ["preference"])
    assert result is False
    assert q.pending_count() == 1


def test_dedup_normalized():
    q = MemoryJudgmentQueue(provider=MockProvider())
    q.enqueue("  我喜欢咖啡  ", ["preference"])
    result = q.enqueue("我喜欢咖啡", ["preference"])
    assert result is False


def test_queue_max_pending():
    q = MemoryJudgmentQueue(provider=MockProvider(), max_pending=2)
    q.enqueue("a", ["preference"])
    q.enqueue("b", ["preference"])
    result = q.enqueue("c", ["preference"])
    assert result is False
    assert q.pending_count() == 2


def test_process_one_calls_provider():
    provider = MockProvider(result={
        "should_write": True,
        "target": "user.md",
        "category": "preference",
        "content": "喜欢咖啡",
        "reason": "用户偏好",
    })
    q = MemoryJudgmentQueue(provider=provider)
    q.enqueue("我喜欢咖啡", ["preference"])
    result = q.process_one()
    assert result is not None
    assert result["should_write"] is True
    assert result["target"] == "memory.md"
    assert result["category"] == "preference"
    assert result["content"] == "喜欢咖啡"
    assert provider.last_messages is not None


def test_process_one_redirects_legacy_user_target_to_memory():
    provider = MockProvider(result={
        "should_write": True,
        "target": "user.md",
        "category": "identity",
        "content": "主人叫小明",
    })
    q = MemoryJudgmentQueue(provider=provider)
    q.enqueue("记住我叫小明", ["explicit"])
    result = q.process_one()
    assert result is not None
    assert result["should_write"] is True
    assert result["target"] == "memory.md"


def test_process_one_validates_output():
    provider = MockProvider(result={
        "should_write": True,
        "target": "bad.md",  # invalid
        "category": "preference",
        "content": "test",
    })
    q = MemoryJudgmentQueue(provider=provider)
    q.enqueue("test", ["preference"])
    result = q.process_one()
    assert result is not None
    assert result["should_write"] is False  # invalid target


def test_process_one_validates_category():
    provider = MockProvider(result={
        "should_write": True,
        "target": "memory.md",
        "category": "invalid",
        "content": "test",
    })
    q = MemoryJudgmentQueue(provider=provider)
    q.enqueue("test", ["preference"])
    result = q.process_one()
    assert result is not None
    assert result["should_write"] is False


def test_process_one_empty_queue():
    q = MemoryJudgmentQueue(provider=MockProvider())
    result = q.process_one()
    assert result is None


def test_skips_judgment_under_backpressure():
    gate = MockProviderGate(available=False)
    provider = MockProvider(result={
        "should_write": True,
        "target": "memory.md",
        "category": "preference",
        "content": "test",
    })
    q = MemoryJudgmentQueue(provider=provider, provider_gate=gate)
    q.enqueue("test", ["preference"])
    result = q.process_one()
    assert result is None
    # Item should still be in queue
    assert q.pending_count() == 1


def test_process_one_clears_seen_on_process():
    provider = MockProvider(result={"should_write": False})
    q = MemoryJudgmentQueue(provider=provider)
    q.enqueue("我喜欢咖啡", ["preference"])
    q.process_one()
    # After processing, same input can be enqueued again
    result = q.enqueue("我喜欢咖啡", ["preference"])
    assert result is True


def test_enqueue_turn_summary_processes_operations():
    provider = MockProvider(result={
        "memories": [{"category": "preference", "content": "喜欢短回复"}],
    })
    tmp = Path(mkdtemp())
    notebook = NotebookManager(tmp / "user.md", tmp / "memory.md")
    q = MemoryJudgmentQueue(provider=provider, notebook_manager=notebook)

    assert q.enqueue_turn_summary(
        user_text="我喜欢短回复",
        pet_reply="豆豆记住啦",
        route="fast_reply",
        selected_memory=["旧记忆"],
    ) is True

    result = q.process_one()

    assert result is not None
    assert result["should_write"] is True
    assert result["memories"] == [{"category": "preference", "content": "喜欢短回复"}]
    assert provider.last_messages is not None


def test_explicit_turn_summary_evicts_oldest_normal_job_when_full():
    provider = MockProvider(result={"memories": []})
    q = MemoryJudgmentQueue(provider=provider, max_pending=2)

    assert q.enqueue_turn_summary("普通1", "回复1", "fast_reply") is True
    assert q.enqueue_turn_summary("普通2", "回复2", "fast_reply") is True
    assert q.enqueue_turn_summary(
        "记住我喜欢咖啡",
        "我先记到小本本",
        "fast_reply",
        trigger_categories=["explicit"],
    ) is True

    assert q.pending_count() == 2
    q.process_one()
    assert "记住我喜欢咖啡" in provider.last_messages[1]["content"]


def test_invalid_turn_summary_output_is_ignored_safely():
    provider = MockProvider(result={
        "add": [{"category": "bad", "content": "x"}],
        "update": [{"old": "", "new_category": "preference", "new_content": "x"}],
        "delete": [{"old": ""}],
    })
    q = MemoryJudgmentQueue(provider=provider)
    q.enqueue_turn_summary("你好", "豆豆在", "fast_reply")

    result = q.process_one()

    assert result == {"should_write": False, "memories": None}
