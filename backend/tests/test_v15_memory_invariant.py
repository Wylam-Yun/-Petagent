from app.runtime.notebook import NotebookManager


def test_memory_overwrite_rejects_more_than_ten_lines(tmp_path):
    user = tmp_path / "user.md"
    memory = tmp_path / "memory.md"
    memory.write_text("- [2026-05-30 10:00][identity] 旧记忆\n", encoding="utf-8")
    notebook = NotebookManager(user, memory)
    lines = [
        {"category": "preference", "content": f"记忆{i}"}
        for i in range(11)
    ]
    assert notebook.overwrite_memory_lines(lines) is False
    assert "旧记忆" in memory.read_text(encoding="utf-8")


def test_memory_overwrite_accepts_ten_valid_lines(tmp_path):
    notebook = NotebookManager(tmp_path / "user.md", tmp_path / "memory.md")
    lines = [
        {"category": "preference", "content": f"记忆{i}"}
        for i in range(10)
    ]
    assert notebook.overwrite_memory_lines(lines) is True
    content = (tmp_path / "memory.md").read_text(encoding="utf-8")
    assert content.count("[preference]") == 10
