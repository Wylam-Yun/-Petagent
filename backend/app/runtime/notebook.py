"""NotebookManager: deterministic card-only memory for canonical memory.md.

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
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

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
_V14_MARKER = "<!-- v1.4_single_notebook -->"
_USER_STUB = (
    "<!-- v1.4_single_notebook_stub: canonical memory is memory.md -->\n"
)
_LOCAL_OFFSET = timedelta(hours=8)
_MAX_CONTENT_CJK = 120
_MAX_CONTENT_CHARS = 240
_FAST_MAX_ITEMS = 10
_FAST_MAX_CJK = 800
_THINKING_MAX_ITEMS = 20
_THINKING_MAX_CJK = 1600

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


def _local_timestamp() -> str:
    return (datetime.utcnow() + _LOCAL_OFFSET).strftime("%Y-%m-%d %H:%M")


def _is_too_long(text: str) -> bool:
    return _cjk_len(text) > _MAX_CONTENT_CJK or len(text) > _MAX_CONTENT_CHARS


@dataclass
class NotebookEntry:
    timestamp: str
    category: str
    content: str
    line_number: int
    raw: str


class NotebookManager:
    """Deterministic card-only memory manager for notebook files."""

    def __init__(self, user_path: Path, memory_path: Path) -> None:
        self._user_path = user_path
        self._memory_path = memory_path
        self._lock = threading.Lock()

    # ── Parsing ──

    def parse_user(self) -> List[NotebookEntry]:
        return self._parse_file(self._user_path)

    def parse_memory(self) -> List[NotebookEntry]:
        return self._parse_file(self._memory_path)

    def _parse_file(self, path: Path, max_entries: Optional[int] = 200) -> List[NotebookEntry]:
        if not path.exists():
            return []
        entries: List[NotebookEntry] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        # Cap to latest 200 parseable lines, preserving file order in the result.
        collected: List[NotebookEntry] = []
        for i, raw_line in reversed(list(enumerate(lines, 1))):
            entry = self._parse_line(raw_line, i)
            if entry is not None:
                collected.append(entry)
                if max_entries is not None and len(collected) >= max_entries:
                    break
        return list(reversed(collected))

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

    def select_for_fast_reply(self) -> List[str]:
        """Select up to 10 canonical memory.md lines for fast reply."""
        return self._select_canonical_for_fast(self.parse_memory())

    def select_for_thinking(self) -> List[str]:
        """Select up to 20 canonical memory.md lines for thinking mode."""
        return self._select_n(self.parse_memory(), _THINKING_MAX_ITEMS, _THINKING_MAX_CJK)

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

    def _select_canonical_for_fast(self, entries: List[NotebookEntry]) -> List[str]:
        if not entries:
            return []
        ranked = self._rank_entries(entries)
        caps = {
            "identity": 2,
            "preference": 3,
            "relationship_project": 3,
            "temporary": 2,
        }
        counts = {key: 0 for key in caps}
        result: List[str] = []
        total_cjk = 0
        for e in ranked:
            if len(result) >= _FAST_MAX_ITEMS:
                break
            bucket = e.category
            if e.category in ("relationship", "project"):
                bucket = "relationship_project"
            if bucket not in counts:
                continue
            if counts[bucket] >= caps[bucket]:
                continue
            cjk = _cjk_len(e.content)
            if total_cjk + cjk > _FAST_MAX_CJK:
                break
            result.append(e.content)
            counts[bucket] += 1
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
        if _is_too_long(content):
            logger.warning("append_line: content too long")
            return False
        if _is_sensitive(content):
            logger.warning("append_line: sensitive content rejected")
            return False
        # Reject if model embedded a timestamp
        if re.match(r"^\d{4}-\d{2}-\d{2}", content):
            logger.warning("append_line: content starts with timestamp (model error)")
            return False

        ts = _local_timestamp()
        line = f"- [{ts}][{category}] {content}\n"

        # V1.4 canonical notebook: all new writes go to memory.md. Keep accepting
        # user.md as a compatibility target from older judgment/cleanup prompts.
        path = self._memory_path

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
            if self._has_v14_marker(self._memory_path):
                return False

            if self._merge_split_notebooks():
                logger.info("migrate_if_needed: V1.4 single notebook migration completed")
                return True

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

    def _has_v14_marker(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            return _V14_MARKER in path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False

    def _merge_split_notebooks(self) -> bool:
        user_entries = self._parse_file(self._user_path, max_entries=None)
        memory_entries = self._parse_file(self._memory_path, max_entries=None)
        if not user_entries and not memory_entries:
            return False

        merged: List[NotebookEntry] = []
        seen: set[str] = set()
        for entry in [*user_entries, *memory_entries]:
            norm = _normalize_text(entry.content)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            merged.append(entry)

        if not merged:
            return False

        self._memory_path.parent.mkdir(parents=True, exist_ok=True)
        self._backup_file(self._memory_path)
        self._backup_file(self._user_path)

        lines = [_V14_MARKER]
        for entry in merged:
            ts = entry.timestamp or _local_timestamp()
            lines.append(f"- [{ts}][{entry.category}] {entry.content}")
        lines.append("")
        if not self._write_text_atomic(self._memory_path, "\n".join(lines)):
            return False
        self._write_text_atomic(self._user_path, _USER_STUB)
        return True

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
                ts = _local_timestamp()
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
        """Import old card paths into canonical memory.md if notebook files are empty."""
        user_empty = not self._user_path.exists() or self._user_path.stat().st_size == 0
        mem_empty = not self._memory_path.exists() or self._memory_path.stat().st_size == 0
        if not user_empty and not mem_empty:
            return False

        try:
            old_user_items = memory_card_manager.read_card("user_preferences") if user_empty else []
            old_memory_items = memory_card_manager.read_card("momo_memories") if mem_empty else []
        except Exception:
            logger.warning("_import_from_old_paths failed", exc_info=True)
            return False

        if not old_user_items and not old_memory_items:
            return False

        self._memory_path.parent.mkdir(parents=True, exist_ok=True)
        self._backup_file(self._memory_path)
        self._backup_file(self._user_path)
        ts = _local_timestamp()
        lines = [_V14_MARKER]
        seen: set[str] = set()
        for item in old_user_items:
            norm = _normalize_text(item)
            if norm and norm not in seen:
                seen.add(norm)
                lines.append(f"- [{ts}][preference] {item}")
        for item in old_memory_items:
            norm = _normalize_text(item)
            if norm and norm not in seen:
                seen.add(norm)
                lines.append(f"- [{ts}][temporary] {item}")
        lines.append("")
        if not self._write_text_atomic(self._memory_path, "\n".join(lines)):
            return False
        self._write_text_atomic(self._user_path, _USER_STUB)
        return True

    def _write_imported(self, path: Path, default_category: str, items: List[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = _local_timestamp()
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

    def _write_text_atomic(self, path: Path, content: str) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
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

    # ── Cleanup operations ──

    def apply_cleanup_operations(self, operations: Dict[str, Any]) -> Dict[str, int]:
        """Apply validated add/update/delete operations to notebook files.

        Acquires self._lock for entire validate-backup-apply-validate cycle.
        LLM call must happen BEFORE calling this method.
        """
        adds = operations.get("add", [])
        updates = operations.get("update", [])
        deletes = operations.get("delete", [])

        stats = {"adds": 0, "updates": 0, "deletes": 0, "errors": 0}
        adds = self._canonical_cleanup_items(adds)
        updates = self._canonical_cleanup_items(updates)
        deletes = self._canonical_cleanup_items(deletes)

        with self._lock:
            for target in ("memory.md",):
                path = self._memory_path
                if not path.exists() and not (
                    any(a.get("target") == target for a in adds)
                    or any(u.get("target") == target for u in updates)
                    or any(d.get("target") == target for d in deletes)
                ):
                    continue

                try:
                    current_lines = path.read_text(encoding="utf-8").splitlines()
                except OSError:
                    current_lines = []

                new_lines = list(current_lines)
                if not new_lines:
                    new_lines.append(_V14_MARKER)
                target_adds = [a for a in adds if a.get("target") == target]
                target_updates = [u for u in updates if u.get("target") == target]
                target_deletes = [d for d in deletes if d.get("target") == target]

                # Apply deletes (skip identity lines)
                for d in target_deletes:
                    old = d.get("old", "").strip()
                    if not old:
                        stats["errors"] += 1
                        continue
                    found_idx = self._find_line_prefix(new_lines, old)
                    if found_idx is None:
                        stats["errors"] += 1
                        continue
                    entry = self._parse_line(new_lines[found_idx], found_idx + 1)
                    if entry and entry.category == "identity":
                        logger.warning("apply_cleanup: rejecting identity delete")
                        stats["errors"] += 1
                        continue
                    new_lines.pop(found_idx)
                    stats["deletes"] += 1

                # Apply updates
                for u in target_updates:
                    old = u.get("old", "").strip()
                    new_cat = u.get("new_category", "")
                    new_content = u.get("new_content", "").strip()
                    if not old or new_cat not in _CATEGORY_WHITELIST or not new_content:
                        stats["errors"] += 1
                        continue
                    if _is_too_long(new_content) or _is_sensitive(new_content):
                        stats["errors"] += 1
                        continue
                    found_idx = self._find_line_prefix(new_lines, old)
                    if found_idx is None:
                        stats["errors"] += 1
                        continue
                    ts = _local_timestamp()
                    new_lines[found_idx] = f"- [{ts}][{new_cat}] {new_content}"
                    stats["updates"] += 1

                # Apply adds
                for a in target_adds:
                    cat = a.get("category", "")
                    content = str(a.get("content", "")).strip()
                    if cat not in _CATEGORY_WHITELIST or not content:
                        stats["errors"] += 1
                        continue
                    if _is_sensitive(content) or _is_too_long(content):
                        stats["errors"] += 1
                        continue
                    ts = _local_timestamp()
                    new_lines.append(f"- [{ts}][{cat}] {content}")
                    stats["adds"] += 1

                # Backup before rewrite
                backup_path = self._backup_file(path)
                if not self._rewrite_and_validate(path, new_lines, backup_path):
                    stats["errors"] += 1

        return stats

    def _canonical_cleanup_items(self, items: Any) -> List[Dict[str, Any]]:
        """Redirect legacy user.md cleanup targets to canonical memory.md."""
        if not isinstance(items, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            copied = dict(item)
            if copied.get("target") == "user.md":
                copied["target"] = "memory.md"
            normalized.append(copied)
        return normalized

    def _find_line_prefix(self, lines: List[str], old: str) -> Optional[int]:
        """Find line index by exact match or prefix match."""
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == old:
                return i
            # Prefix match on timestamp+category portion
            old_parts = old.split("] ", 2)
            if len(old_parts) >= 2:
                prefix = "] ".join(old_parts[:2])
                if prefix in stripped:
                    return i
        return None

    def _backup_file(self, path: Path) -> Optional[Path]:
        """Create a timestamped backup of the file."""
        if not path.exists():
            return None
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        backup_path = path.parent / f"{path.name}.bak.{ts}"
        try:
            import shutil
            shutil.copy2(str(path), str(backup_path))
            return backup_path
        except OSError:
            logger.warning("_backup_file failed for %s", path)
            return None

    def _restore_backup(self, path: Path, backup_path: Optional[Path]) -> bool:
        """Restore file from backup using atomic rename."""
        if backup_path is None or not backup_path.exists():
            return False
        try:
            os.replace(str(backup_path), str(path))
            return True
        except OSError:
            logger.warning("_restore_backup failed for %s", path)
            return False

    def _rewrite_and_validate(
        self, path: Path, lines: List[str], backup_path: Optional[Path]
    ) -> bool:
        """Atomically rewrite file and validate. Restore backup on failure."""
        content = "\n".join(lines) + "\n"
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
            self._restore_backup(path, backup_path)
            return False

        # Validate: re-read and parse new-format lines
        try:
            written = path.read_text(encoding="utf-8")
            parse_failures = 0
            for wl in written.splitlines():
                stripped = wl.strip()
                if stripped.startswith("- ["):
                    if self._parse_line(stripped, 0) is None:
                        parse_failures += 1
            if parse_failures > 0:
                logger.warning(
                    "rewrite_and_validate: %d parse failures, restoring backup",
                    parse_failures,
                )
                self._restore_backup(path, backup_path)
                return False
        except OSError:
            self._restore_backup(path, backup_path)
            return False

        # Clean up backup on success
        if backup_path and backup_path.exists():
            try:
                backup_path.unlink()
            except OSError:
                pass
        return True
