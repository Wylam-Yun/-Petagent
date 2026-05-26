"""Tests for V1.3 NotebookManager."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.runtime.notebook import NotebookEntry, NotebookManager


def _make_nm():
    """Create a NotebookManager with temp files."""
    tmpdir = tempfile.mkdtemp()
    user = Path(tmpdir) / "user.md"
    memory = Path(tmpdir) / "memory.md"
    return NotebookManager(user, memory), user, memory


def test_parse_valid_lines():
    nm, user, _ = _make_nm()
    user.write_text(
        "- [2026-05-25 20:42][preference] 主人希望豆豆快速回应优先。\n"
        "- [2026-05-25 21:10][project] 主人正在调 PetAgent V1.3。\n",
        encoding="utf-8",
    )
    entries = nm.parse_user()
    assert len(entries) == 2
    assert entries[0].category == "preference"
    assert entries[0].timestamp == "2026-05-25 20:42"
    assert "快速回应" in entries[0].content
    assert entries[1].category == "project"


def test_parse_old_format_lines():
    nm, user, _ = _make_nm()
    user.write_text(
        "<!-- memory_cards: user_preferences | rebuilt: 2026-05-25T16:33:16 -->\n"
        "- 喜欢短回复 <!-- source:memory:1 type:user_preference updated:2026-05-25 ttl:stable -->\n",
        encoding="utf-8",
    )
    entries = nm.parse_user()
    assert len(entries) == 1
    assert entries[0].content == "喜欢短回复"
    assert entries[0].category == "preference"  # user_preference -> preference
    assert entries[0].timestamp == ""


def test_parse_mixed_format():
    nm, user, _ = _make_nm()
    user.write_text(
        "<!-- memory_cards: user_preferences | rebuilt: 2026-05-25T16:33:16 -->\n"
        "- 喜欢短回复 <!-- source:memory:1 type:user_preference updated:2026-05-25 ttl:stable -->\n"
        "- [2026-05-26 10:00][identity] 我叫小明。\n",
        encoding="utf-8",
    )
    entries = nm.parse_user()
    assert len(entries) == 2
    assert entries[0].category == "preference"  # old format
    assert entries[1].category == "identity"  # new format


def test_parse_malformed_lines_ignored():
    nm, user, _ = _make_nm()
    user.write_text(
        "这不是一个有效的行\n"
        "- [2026-05-25 20:42][preference] 有效行\n"
        "<!-- header comment -->\n"
        "\n",
        encoding="utf-8",
    )
    entries = nm.parse_user()
    assert len(entries) == 1
    assert "有效行" in entries[0].content


def test_parse_file_uses_latest_200_parseable_lines():
    nm, user, _ = _make_nm()
    lines = [
        f"- [2026-05-25 10:{i % 60:02d}][preference] 偏好{i}\n"
        for i in range(250)
    ]
    user.write_text("".join(lines), encoding="utf-8")

    entries = nm.parse_user()

    assert len(entries) == 200
    assert entries[0].content == "偏好50"
    assert entries[-1].content == "偏好249"
    assert all(e.content != "偏好0" for e in entries)


def test_select_fast_reply():
    nm, user, memory = _make_nm()
    user.write_text(
        "- [2026-05-25 20:00][identity] 我叫小明。\n"
        "- [2026-05-25 21:00][preference] 喜欢咖啡。\n",
        encoding="utf-8",
    )
    memory.write_text(
        "- [2026-05-25 22:00][relationship] 今天去了公园。\n",
        encoding="utf-8",
    )
    user_item, memory_item = nm.select_for_fast_reply()
    assert user_item is not None
    assert "小明" in user_item  # identity > preference
    assert memory_item is not None
    assert "公园" in memory_item


def test_select_fast_reply_empty():
    nm, _, _ = _make_nm()
    user_item, memory_item = nm.select_for_fast_reply()
    assert user_item is None
    assert memory_item is None


def test_select_thinking():
    nm, user, memory = _make_nm()
    user_lines = [f"- [2026-05-25 {20+i:02d}:00][preference] 偏好{i}\n" for i in range(10)]
    user.write_text("".join(user_lines), encoding="utf-8")
    memory_lines = [f"- [2026-05-25 {20+i:02d}:00][project] 项目{i}\n" for i in range(15)]
    memory.write_text("".join(memory_lines), encoding="utf-8")
    user_items, memory_items = nm.select_for_thinking()
    assert len(user_items) <= 8
    assert len(memory_items) <= 12
    assert len(user_items) == 8  # should hit cap
    assert len(memory_items) == 12  # should hit cap


def test_append_line_adds_timestamp():
    nm, user, _ = _make_nm()
    result = nm.append_line("user.md", "preference", "喜欢短回复")
    assert result is True
    content = user.read_text(encoding="utf-8")
    assert "- [2026-" in content
    assert "[preference]" in content
    assert "喜欢短回复" in content


def test_append_line_uses_local_timestamp(monkeypatch):
    import app.runtime.notebook as notebook

    class FixedDateTime:
        @classmethod
        def utcnow(cls):
            from datetime import datetime
            return datetime(2026, 5, 25, 16, 30)

    monkeypatch.setattr(notebook, "datetime", FixedDateTime)
    nm, user, _ = _make_nm()
    assert nm.append_line("user.md", "preference", "喜欢短回复") is True
    assert "- [2026-05-26 00:30][preference]" in user.read_text(encoding="utf-8")


def test_append_line_rejects_overlong_content():
    nm, user, _ = _make_nm()
    assert nm.append_line("user.md", "preference", "很长" * 80) is False
    assert not user.exists()


def test_append_line_rejects_model_timestamp():
    nm, user, _ = _make_nm()
    result = nm.append_line("user.md", "preference", "2026-05-25 喜欢短回复")
    assert result is False
    assert not user.exists() or user.read_text(encoding="utf-8").strip() == ""


def test_append_line_validates_category():
    nm, user, _ = _make_nm()
    result = nm.append_line("user.md", "invalid_cat", "内容")
    assert result is False


def test_append_line_validates_target():
    nm, _, _ = _make_nm()
    result = nm.append_line("bad.md", "preference", "内容")
    assert result is False


def test_append_line_rejects_duplicates():
    nm, user, _ = _make_nm()
    nm.append_line("user.md", "preference", "喜欢咖啡")
    result = nm.append_line("user.md", "preference", "喜欢咖啡")
    assert result is False
    content = user.read_text(encoding="utf-8")
    assert content.count("喜欢咖啡") == 1


def test_append_line_rejects_secrets():
    nm, user, _ = _make_nm()
    # SENSITIVE_MARKERS includes things like password, token, etc.
    result = nm.append_line("user.md", "preference", "密码是123456 password=abc")
    assert result is False


def test_append_line_atomic():
    nm, user, _ = _make_nm()
    nm.append_line("user.md", "preference", "第一行")
    nm.append_line("user.md", "identity", "第二行")
    content = user.read_text(encoding="utf-8")
    lines = [l for l in content.splitlines() if l.strip()]
    assert len(lines) == 2
    assert "第一行" in lines[0]
    assert "第二行" in lines[1]


def test_migrate_old_format():
    nm, user, memory = _make_nm()
    user.write_text(
        "<!-- memory_cards: user_preferences | rebuilt: 2026-05-25 -->\n"
        "- 喜欢短回复 <!-- source:memory:1 type:user_preference updated:2026-05-25 ttl:stable -->\n",
        encoding="utf-8",
    )
    result = nm.migrate_if_needed()
    assert result is True
    content = user.read_text(encoding="utf-8")
    assert "v1.3_migrated" in content
    assert "[preference]" in content
    assert "喜欢短回复" in content


def test_migrate_skips_if_new_format_present():
    nm, user, _ = _make_nm()
    user.write_text(
        "- [2026-05-26 10:00][preference] 喜欢咖啡\n",
        encoding="utf-8",
    )
    result = nm.migrate_if_needed()
    assert result is False


def test_old_type_category_mapping():
    """All old types map to valid new categories."""
    nm, user, _ = _make_nm()
    user.write_text(
        "- 偏好 <!-- source:memory:1 type:user_preference updated:2026-05-25 ttl:stable -->\n"
        "- 关系 <!-- source:memory:2 type:relationship updated:2026-05-25 ttl:stable -->\n"
        "- 习惯 <!-- source:memory:3 type:habit updated:2026-05-25 ttl:stable -->\n"
        "- 记忆 <!-- source:memory:4 type:stable_memory updated:2026-05-25 ttl:stable -->\n"
        "- 名言 <!-- source:memory:5 type:important_quote updated:2026-05-25 ttl:stable -->\n"
        "- 心情 <!-- source:memory:6 type:recent_mood updated:2026-05-25 ttl:stable -->\n"
        "- 事件 <!-- source:memory:7 type:important_event updated:2026-05-25 ttl:stable -->\n",
        encoding="utf-8",
    )
    entries = nm.parse_user()
    cats = {e.content: e.category for e in entries}
    assert cats["偏好"] == "preference"
    assert cats["关系"] == "relationship"
    assert cats["习惯"] == "preference"
    assert cats["记忆"] == "identity"
    assert cats["名言"] == "preference"
    assert cats["心情"] == "temporary"
    assert cats["事件"] == "project"
