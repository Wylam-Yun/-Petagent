"""Tests for V1.3 Nightly Memory Cleanup."""
from __future__ import annotations

import tempfile
import threading
from datetime import datetime
from pathlib import Path
from time import perf_counter
from unittest.mock import MagicMock

from app.runtime.nightly_cleanup import NightlyCleanupRunner
from app.runtime.notebook import NotebookManager


def _make_runner(**overrides):
    """Create a NightlyCleanupRunner with mock dependencies."""
    tmpdir = tempfile.mkdtemp()
    user = Path(tmpdir) / "user.md"
    memory = Path(tmpdir) / "memory.md"
    user.write_text("<!-- v1.4_single_notebook_stub: canonical memory is memory.md -->\n", encoding="utf-8")
    memory.write_text(
        "<!-- v1.4_single_notebook -->\n"
        "- [2026-05-20 10:00][identity] 我叫小明。\n"
        "- [2026-05-20 11:00][preference] 喜欢咖啡。\n"
        "- [2026-05-23 09:00][temporary] 今天心情好。\n"
        "- [2026-05-23 10:00][project] 在调 PetAgent V1.3。\n",
        encoding="utf-8",
    )
    nm = NotebookManager(user, memory)

    provider = MagicMock()
    provider.complete_json.return_value = {"add": [], "update": [], "delete": []}

    ms = MagicMock()
    ms.get.return_value = None  # last_cleanup_date not set

    gate = MagicMock()
    gate.is_available.return_value = True

    dispatcher = MagicMock()
    dispatcher.active_requests = 0
    dispatcher.event_loop_tick = perf_counter()  # current = not stale

    elog = MagicMock()
    elog.recent_events_bounded.return_value = []

    runner = NightlyCleanupRunner(
        notebook_manager=nm,
        provider=provider,
        event_log_store=elog,
        maintenance_state=ms,
        provider_gate=gate,
        dispatcher=dispatcher,
    )
    runner._get_local_now = MagicMock(return_value=datetime(2026, 5, 26, 0, 30))
    return runner, nm, provider, ms, gate, dispatcher


def test_cleanup_prompt_includes_aging_rules():
    """Cleanup prompt should contain aging rules."""
    from app.pet.prompt_builder import build_nightly_cleanup_messages

    messages = build_nightly_cleanup_messages("内容", [], "2026-05-26 00:00 Monday")
    system = messages[0]["content"]
    assert "identity" in system
    assert "temporary" in system
    assert "3 天" in system or "3天" in system


def test_cleanup_prompt_includes_current_time():
    from app.pet.prompt_builder import build_nightly_cleanup_messages

    messages = build_nightly_cleanup_messages("内容", [], "2026-05-26 00:00 Monday")
    import json
    payload = json.loads(messages[1]["content"])
    assert "2026-05-26" in payload["current_time"]
    assert "user_md" not in payload


def test_apply_add_operations():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [{"target": "memory.md", "category": "relationship", "content": "今天去了公园"}],
        "update": [],
        "delete": [],
    }
    result = runner.run()
    assert result.get("adds", 0) == 1
    content = nm.read_raw("memory.md")
    assert "今天去了公园" in content


def test_apply_add_creates_canonical_memory_file_when_missing():
    nm, _, memory = _make_nm_simple()
    assert not memory.exists()

    result = nm.apply_cleanup_operations({
        "add": [{"target": "memory.md", "category": "relationship", "content": "今天去了公园"}],
        "update": [],
        "delete": [],
    })

    assert result.get("adds") == 1
    content = memory.read_text(encoding="utf-8")
    assert "v1.4_single_notebook" in content
    assert "今天去了公园" in content


def test_apply_update_operations():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [],
        "update": [{
            "target": "user.md",
            "old": "- [2026-05-20 11:00][preference] 喜欢咖啡。",
            "new_category": "preference",
            "new_content": "喜欢咖啡和茶。",
        }],
        "delete": [],
    }
    result = runner.run()
    assert result.get("updates", 0) == 1
    content = nm.read_raw("memory.md")
    assert "喜欢咖啡和茶" in content
    assert "single_notebook_stub" in nm.read_raw("user.md")


def test_apply_delete_operations():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [],
        "update": [],
        "delete": [{"target": "user.md", "old": "- [2026-05-23 09:00][temporary] 今天心情好。"}],
    }
    result = runner.run()
    assert result.get("deletes", 0) == 1
    content = nm.read_raw("memory.md")
    assert "今天心情好" not in content


def test_apply_validates_target():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [{"target": "bad.md", "category": "preference", "content": "test"}],
        "update": [],
        "delete": [],
    }
    result = runner.run()
    # bad.md target should be rejected by validator
    assert result.get("errors", 0) >= 1 or result.get("adds", 0) == 0


def test_apply_validates_category():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [{"target": "user.md", "category": "invalid_cat", "content": "test"}],
        "update": [],
        "delete": [],
    }
    result = runner.run()
    assert result.get("errors", 0) >= 1 or result.get("adds", 0) == 0


def test_apply_rejects_sensitive_content():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [{"target": "user.md", "category": "preference", "content": "密码是123456 password=abc"}],
        "update": [],
        "delete": [],
    }
    result = runner.run()
    assert result.get("errors", 0) >= 1 or result.get("adds", 0) == 0


def test_apply_rejects_model_timestamp_in_content():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [{"target": "memory.md", "category": "preference", "content": "2026-05-29 喜欢短回复"}],
        "update": [],
        "delete": [],
    }
    result = runner.run()
    assert result.get("errors", 0) >= 1 or result.get("adds", 0) == 0
    assert "2026-05-29 喜欢短回复" not in nm.read_raw("memory.md")


def test_apply_skips_duplicate_add_content():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [{"target": "memory.md", "category": "preference", "content": "喜欢咖啡。"}],
        "update": [],
        "delete": [],
    }
    result = runner.run()
    assert result.get("adds", 0) == 0
    assert result.get("errors", 0) >= 1
    assert nm.read_raw("memory.md").count("喜欢咖啡。") == 1


def test_apply_skips_update_when_old_line_missing():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [],
        "update": [{
            "target": "user.md",
            "old": "- [2026-01-01 00:00][preference] 不存在的行",
            "new_category": "preference",
            "new_content": "新内容",
        }],
        "delete": [],
    }
    result = runner.run()
    assert result.get("errors", 0) >= 1 or result.get("updates", 0) == 0


def test_apply_rejects_identity_delete():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [],
        "update": [],
        "delete": [{"target": "user.md", "old": "- [2026-05-20 10:00][identity] 我叫小明。"}],
    }
    result = runner.run()
    # Identity lines should NOT be deleted
    assert result.get("deletes", 0) == 0
    content = nm.read_raw("memory.md")
    assert "我叫小明" in content


def test_backup_and_restore():
    nm, user, _ = _make_nm_simple()
    user.write_text("- [2026-05-20 10:00][preference] 喜欢咖啡\n", encoding="utf-8")
    backup = nm._backup_file(user)
    assert backup is not None
    assert backup.exists()
    # Modify original
    user.write_text("corrupted", encoding="utf-8")
    # Restore
    assert nm._restore_backup(user, backup) is True
    content = user.read_text(encoding="utf-8")
    assert "喜欢咖啡" in content


def test_atomic_rewrite_validates():
    nm, user, _ = _make_nm_simple()
    user.write_text("- [2026-05-20 10:00][preference] 原始内容\n", encoding="utf-8")
    backup = nm._backup_file(user)
    # Write valid content
    assert nm._rewrite_and_validate(user, ["- [2026-05-20 10:00][preference] 新内容"], backup) is True
    assert "新内容" in user.read_text(encoding="utf-8")


def test_should_run_once_per_day():
    runner, _, _, ms, _, _ = _make_runner()
    # First call: no last_cleanup_date → should run
    ms.get.return_value = None
    assert runner.should_run() is True
    # Simulate: cleanup ran today
    ms.get.return_value = runner._today_local()
    assert runner.should_run() is False


def test_should_run_only_inside_midnight_window():
    runner, _, provider, ms, _, _ = _make_runner()
    ms.get.return_value = None
    runner._get_local_now = MagicMock(return_value=datetime(2026, 5, 26, 12, 0))

    assert runner.should_run() is False
    assert runner.run() == {}
    provider.complete_json.assert_not_called()

    runner._get_local_now = MagicMock(return_value=datetime(2026, 5, 26, 0, 30))
    assert runner.should_run() is True


def test_force_bypasses_midnight_window():
    runner, _, _, ms, _, _ = _make_runner()
    ms.get.return_value = None
    runner._get_local_now = MagicMock(return_value=datetime(2026, 5, 26, 12, 0))

    assert runner.should_run() is False
    assert runner.should_run(force=True) is True


def test_should_run_skips_during_active_response():
    runner, _, _, ms, _, dispatcher = _make_runner()
    ms.get.return_value = None
    dispatcher.active_requests = 1
    assert runner.should_run() is False


def test_should_run_skips_under_backpressure():
    runner, _, _, ms, gate, _ = _make_runner()
    ms.get.return_value = None
    gate.is_available.return_value = False
    assert runner.should_run() is False


def test_should_run_skips_when_event_loop_stale():
    runner, _, _, ms, _, dispatcher = _make_runner()
    ms.get.return_value = None
    dispatcher.event_loop_tick = perf_counter() - 120  # 120s ago
    assert runner.should_run() is False


def test_cleanup_runner_integration():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = {
        "add": [{"target": "memory.md", "category": "project", "content": "新项目"}],
        "update": [],
        "delete": [{"target": "user.md", "old": "- [2026-05-23 09:00][temporary] 今天心情好。"}],
    }
    result = runner.run()
    assert result.get("adds", 0) == 1
    assert result.get("deletes", 0) == 1
    # Verify cleanup date was set
    ms.set.assert_any_call("last_cleanup_date", ms.set.call_args_list[-1][0][1])


def test_cleanup_runner_handles_malformed_llm_output():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    provider.complete_json.return_value = "not a dict"
    result = runner.run()
    # Should not crash, should mark as done
    ms.set.assert_any_call("last_cleanup_date", ms.set.call_args_list[-1][0][1])


def test_cleanup_preserves_identity_lines():
    runner, nm, provider, ms, gate, dispatcher = _make_runner()
    # Try to delete identity line AND a valid temporary line
    provider.complete_json.return_value = {
        "add": [],
        "update": [],
        "delete": [
            {"target": "user.md", "old": "- [2026-05-20 10:00][identity] 我叫小明。"},
            {"target": "user.md", "old": "- [2026-05-23 09:00][temporary] 今天心情好。"},
        ],
    }
    result = runner.run()
    # Identity should be preserved, temporary should be deleted
    content = nm.read_raw("memory.md")
    assert "我叫小明" in content
    assert "今天心情好" not in content


def _make_nm_simple():
    tmpdir = tempfile.mkdtemp()
    user = Path(tmpdir) / "user.md"
    memory = Path(tmpdir) / "memory.md"
    return NotebookManager(user, memory), user, memory
