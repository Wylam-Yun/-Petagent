"""V1.3 NotebookManager: deterministic card-only memory for user.md and memory.md.

Handles both new V1.3 format and legacy HTML-comment format.
No LLM calls. No SQLite. Pure file reads + atomic writes.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.runtime.memory_policy import SENSITIVE_MARKERS

logger = logging.getLogger(__name__)

_NEW_LINE_RE = re.compile(
    r"^- \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\[(\w+)\] (.+)$"
)
_OLD_LINE_RE = re.compile(
    r"^- (.+?) <!-- source:memory:\d+ type:(\S+) updated:\S+ ttl:\S+ -->$"
)

_CATEGORY_WHITELIST = {"identity", "preference", "relationship", "project", "temporary"}

_OLD_TYPE_TO_CATEGORY = {
    "user_preference": "preference",
    "relationship": "relationship",
    "habit": "preference",
    "stable_memory": "identity",
    "important_quote": "preference",
    "recent_mood": "temporary",
    "important_event": "project",
}

_TARGET_WHITELIST = {"user.md", "memory.md"}

_CJK_RANGE = ("一", "鿿")


def _is_cjk(ch: str) -> bool:
    return _CJK_RANGE[0] <= ch <= _CJK_RANGE[1]


def _cjk_len(text: str) -> int:
    return sum(1 for ch in text if _is_cjk(ch))


def _normalize_text(text: str) -> str:
    """Normalize for dedup: strip + collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip())


def _is_sensitive(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS)


@dataclass
class NotebookEntry:
    timestamp: str
    category: str
    content: str
    line_number: int
    raw: str


class NotebookManager:
    """Deterministic card-only memory manager for V1.3 notebook files."""

    def __init__(self, user_path: Path, memory_path: Path) -> None:
        self._user_path = user_path
        self._memory_path = memory_path
        self._lock = threading.Lock()

    # ── Parsing ──

    def parse_user(self) -> List[NotebookEntry]:
        return self._parse_file(self._user_path)

    def parse_memory(self) -> List[NotebookEntry]:
        return self._parse_file(self._memory_path)

    def _parse_file(self, path: Path) -> List[NotebookEntry]:
        if not path.exists():
            return []
        entries: List[NotebookEntry] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        # Cap to latest 200 parseable lines
        count = 0
        for i, raw_line in enumerate(lines, 1):
            if count >= 200:
                break
            entry = self._parse_line(raw_line, i)
            if entry is not None:
                entries.append(entry)
                count += 1
        return entries

    def _parse_line(self, raw: str, line_number: int) -> Optional[NotebookEntry]:
        raw = raw.strip()
        if not raw or raw.startswith("<!--"):
            return None
        # New format: - [YYYY-MM-DD HH:MM][category] content
        m = _NEW_LINE_RE.match(raw)
        if m:
            ts, cat, content = m.group(1), m.group(2), m.group(3)
            if cat in _CATEGORY_WHITELIST:
                return NotebookEntry(ts, cat, content, line_number, raw)
            return None
        # Old format: - content <!-- source:memory:N type:T ... -->
        m = _OLD_LINE_RE.match(raw)
        if m:
            content, old_type = m.group(1), m.group(2)
            cat = _OLD_TYPE_TO_CATEGORY.get(old_type, "temporary")
            return NotebookEntry("", cat, content, line_number, raw)
        return None

    # ── Selection ──

    def select_for_fast_reply(self) -> Tuple[Optional[str], Optional[str]]:
        """Select 1 user.md item + 1 memory.md item by priority."""
        user_item = self._select_one(self.parse_user())
        memory_item = self._select_one(self.parse_memory())
        return (user_item, memory_item)

    def select_for_thinking(self) -> Tuple[List[str], List[str]]:
        """Select up to 8 user.md items + 12 memory.md items."""
        user_items = self._select_n(self.parse_user(), 8, 200)
        memory_items = self._select_n(self.parse_memory(), 12, 200)
        return (user_items, memory_items)

    def _select_one(self, entries: List[NotebookEntry]) -> Optional[str]:
        if not entries:
            return None
        ranked = self._rank_entries(entries)
        return ranked[0].content if ranked else None

    def _select_n(
        self, entries: List[NotebookEntry], max_count: int, max_cjk: int
    ) -> List[str]:
        if not entries:
            return []
        ranked = self._rank_entries(entries)
        result: List[str] = []
        total_cjk = 0
        for e in ranked:
            if len(result) >= max_count:
                break
            cjk = _cjk_len(e.content)
            if total_cjk + cjk > max_cjk:
                break
            result.append(e.content)
            total_cjk += cjk
        return result

    def _rank_entries(self, entries: List[NotebookEntry]) -> List[NotebookEntry]:
        """Rank: identity > preference > relationship > project > temporary, then newer."""
        priority = {"identity": 0, "preference": 1, "relationship": 2, "project": 3, "temporary": 4}
        return sorted(
            entries,
            key=lambda e: (priority.get(e.category, 9), -e.line_number),
        )

    # ── Append ──

    def append_line(self, target: str, category: str, content: str) -> bool:
        """Append a validated memory line with backend timestamp. Returns True on success."""
        if target not in _TARGET_WHITELIST:
            logger.warning("append_line: invalid target %s", target)
            return False
        if category not in _CATEGORY_WHITELIST:
            logger.warning("append_line: invalid category %s", category)
            return False
        content = content.strip()
        if not content:
            return False
        if _is_sensitive(content):
            logger.warning("append_line: sensitive content rejected")
            return False
        # Reject if model embedded a timestamp
        if re.match(r"^\d{4}-\d{2}-\d{2}", content):
            logger.warning("append_line: content starts with timestamp (model error)")
            return False

        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        line = f"- [{ts}][{category}] {content}\n"

        path = self._user_path if target == "user.md" else self._memory_path

        with self._lock:
            # Duplicate check
            if self._line_exists(path, content):
                logger.info("append_line: duplicate skipped for %s", target)
                return False
            return self._atomic_append(path, line)

    def _line_exists(self, path: Path, content: str) -> bool:
        if not path.exists():
            return False
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if content in line:
                    return True
        except OSError:
            pass
        return False

    def _atomic_append(self, path: Path, line: str) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        if path.exists():
            try:
                existing = path.read_text(encoding="utf-8")
            except OSError:
                existing = ""
        new_content = existing + line
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            os.write(fd, new_content.encode("utf-8"))
            os.close(fd)
            fd = -1
            os.replace(tmp_path, str(path))
            return True
        except OSError:
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return False

    # ── Raw read ──

    def read_raw(self, target: str) -> str:
        path = self._user_path if target == "user.md" else self._memory_path
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    # ── Migration ──

    def migrate_if_needed(self, memory_card_manager=None) -> bool:
        """One-time migration from old format to new. Returns True if migration ran."""
        with self._lock:
            # Check if new format already present
            for path in (self._user_path, self._memory_path):
                if self._has_new_format(path):
                    logger.info("migrate_if_needed: new format detected, skipping")
                    return False

            # Convert old-format lines in-place
            migrated = False
            for path in (self._user_path, self._memory_path):
                if self._convert_old_format(path):
                    migrated = True

            # If canonical files are empty, try old subdirectory paths
            if not migrated and memory_card_manager is not None:
                migrated = self._import_from_old_paths(memory_card_manager)

            if migrated:
                logger.info("migrate_if_needed: migration completed")
            return migrated

    def _has_new_format(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("- ["):
                    return True
        except OSError:
            pass
        return False

    def _convert_old_format(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False

        new_lines = ["<!-- v1.3_migrated -->"]
        changed = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("<!--"):
                # Skip old header comments
                changed = True
                continue
            m = _OLD_LINE_RE.match(stripped)
            if m:
                content, old_type = m.group(1), m.group(2)
                cat = _OLD_TYPE_TO_CATEGORY.get(old_type, "temporary")
                ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
                new_lines.append(f"- [{ts}][{cat}] {content}")
                changed = True
            elif stripped.startswith("- "):
                # Bare bullet without format — preserve as-is
                new_lines.append(line)
            # Skip empty lines between items

        if not changed:
            return False

        new_lines.append("")  # trailing newline
        content = "\n".join(new_lines)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            fd = -1
            os.replace(tmp_path, str(path))
            return True
        except OSError:
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return False

    def _import_from_old_paths(self, memory_card_manager) -> bool:
        """Import from old subdirectory paths if canonical files are empty."""
        user_empty = not self._user_path.exists() or self._user_path.stat().st_size == 0
        mem_empty = not self._memory_path.exists() or self._memory_path.stat().st_size == 0
        if not user_empty and not mem_empty:
            return False

        imported = False
        try:
            if user_empty:
                old_items = memory_card_manager.read_card("user_preferences")
                if old_items:
                    self._write_imported(self._user_path, "preference", old_items)
                    imported = True
            if mem_empty:
                old_items = memory_card_manager.read_card("momo_memories")
                if old_items:
                    self._write_imported(self._memory_path, "temporary", old_items)
                    imported = True
        except Exception:
            logger.warning("_import_from_old_paths failed", exc_info=True)
        return imported

    def _write_imported(self, path: Path, default_category: str, items: List[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        lines = ["<!-- v1.3_migrated -->"]
        for item in items:
            lines.append(f"- [{ts}][{default_category}] {item}")
        lines.append("")
        content = "\n".join(lines)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            fd = -1
            os.replace(tmp_path, str(path))
        except OSError:
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
