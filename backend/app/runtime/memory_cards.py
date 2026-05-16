from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.runtime.memory_policy import SENSITIVE_MARKERS
from app.runtime.memory_store import MemoryManager

logger = logging.getLogger(__name__)

_CARD_LINE_RE = re.compile(
    r"^- (.+?) <!-- source:memory:(\d+) type:(\S+) updated:(\S+) ttl:(\S+) -->$"
)

_CARD_TYPE_MAP = {
    "user_preference": "user_preferences",
    "relationship": "user_preferences",
    "habit": "user_preferences",
    "stable_memory": "user_preferences",
    "important_event": "momo_memories",
    "recent_mood": "momo_memories",
    "important_quote": "momo_memories",
}


def _cjk_len(text: str) -> int:
    return sum(1 for c in text if "一" <= c <= "鿿")


def _truncate_to_cjk(text: str, max_chars: int) -> Optional[str]:
    """Truncate text to max_chars CJK characters. Returns None if nothing meaningful remains."""
    cjk_count = 0
    for i, c in enumerate(text):
        if "一" <= c <= "鿿":
            cjk_count += 1
        if cjk_count > max_chars:
            return text[:i] + "..."
    return text


def _chinese_bigrams(text: str) -> set:
    chars = re.findall(r"[一-鿿]", text)
    if len(chars) < 2:
        return set(chars)
    return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}


def _is_sensitive(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS)


def _ttl_label(expires_at: Optional[str]) -> str:
    if not expires_at:
        return "stable"
    return "expires:%s" % expires_at[:10]


def _deduplicate(items: List[Dict[str, Any]], threshold: float = 0.6) -> List[Dict[str, Any]]:
    """Remove near-duplicate items by bigram overlap. Keeps higher importance."""
    if len(items) <= 1:
        return items
    bigrams = [_chinese_bigrams(it["content"]) for it in items]
    keep = [True] * len(items)
    for i in range(len(items)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(items)):
            if not keep[j]:
                continue
            a, b = bigrams[i], bigrams[j]
            if not a or not b:
                continue
            overlap = len(a & b) / min(len(a), len(b))
            if overlap >= threshold:
                # Drop the lower-importance one; if equal, drop the newer (higher id)
                if items[i]["importance"] > items[j]["importance"]:
                    keep[j] = False
                elif items[j]["importance"] > items[i]["importance"]:
                    keep[i] = False
                elif items[i]["id"] > items[j]["id"]:
                    keep[i] = False
                else:
                    keep[j] = False
    return [it for it, k in zip(items, keep) if k]


class MemoryCardManager:
    """Read-only projection of SQLite memories into lightweight markdown cards.

    Cards are caches, not a second source of truth. The SQLite memory table
    remains authoritative.
    """

    VALID_REASONS = {
        "curator_saved",
        "memory_merged",
        "memory_expired",
        "runtime_reset",
        "manual_debug",
    }

    def __init__(
        self,
        memory_manager: MemoryManager,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        cfg = config or {}
        self.memory_manager = memory_manager
        self.max_card_cjk_chars = int(cfg.get("max_card_cjk_chars", 200))
        self.max_item_cjk_chars = int(cfg.get("max_item_cjk_chars", 20))
        self.max_items_per_card = int(cfg.get("max_items_per_card", 10))
        self.min_importance = int(cfg.get("min_importance", 2))
        base = Path(cfg.get("card_base_dir", "backend/data/memory_cards"))
        self._paths = {
            "user_preferences": Path(cfg.get("user_preferences_path", base / "user_preferences" / "card.md")),
            "momo_memories": Path(cfg.get("momo_memories_path", base / "momo_memories" / "card.md")),
        }

    def rebuild(self, reason: str) -> Dict[str, int]:
        """Rebuild both card files from SQLite. Returns {items_written, items_rejected}."""
        if reason not in self.VALID_REASONS:
            return {"items_written": 0, "items_rejected": 0}

        all_memories = self.memory_manager.memories_for_cards(limit=200)

        groups: Dict[str, List[Dict[str, Any]]] = {
            "user_preferences": [],
            "momo_memories": [],
        }
        for mem in all_memories:
            card_name = _CARD_TYPE_MAP.get(mem["type"])
            if card_name and mem["importance"] >= self.min_importance:
                groups[card_name].append(mem)

        total_written = 0
        total_rejected = 0

        for card_name, items in groups.items():
            processed = self._process_card_items(card_name, items)
            self._write_card(self._paths[card_name], processed, card_name, reason)
            total_written += len(processed)
            total_rejected += max(0, len(items) - len(processed))

        return {"items_written": total_written, "items_rejected": total_rejected}

    def clear(self) -> None:
        """Write empty card files. Used during runtime reset."""
        for card_name in ("user_preferences", "momo_memories"):
            self._write_card(self._paths[card_name], [], card_name, "runtime_reset")

    def read_card(self, card_name: str) -> List[str]:
        """Read card file and return list of content strings (no HTML comments)."""
        return [item["content"] for item in self.read_card_with_provenance(card_name)]

    def read_card_with_provenance(self, card_name: str) -> List[Dict[str, str]]:
        """Read card file and return list of {content, source_id, type, updated, ttl}."""
        path = self._paths.get(card_name)
        if path is None or not path.exists():
            return []
        result = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                parsed = self._parse_line(line)
                if parsed:
                    result.append(parsed)
        except OSError:
            return []
        return result

    def _process_card_items(self, card_name: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Filter sensitive
        items = [it for it in items if not _is_sensitive(it["content"])]
        # Deduplicate
        items = _deduplicate(items)
        # Sort by importance DESC then id DESC (already sorted from query, but re-sort after dedup)
        items.sort(key=lambda it: (-it["importance"], -it["id"]))
        # Truncate long items
        processed = []
        for it in items:
            truncated = _truncate_to_cjk(it["content"], self.max_item_cjk_chars)
            if truncated is not None:
                processed.append({**it, "content": truncated})
        # Enforce max_items_per_card
        processed = processed[: self.max_items_per_card]
        # Enforce max_card_cjk_chars total
        result = []
        total_chars = 0
        for it in processed:
            item_chars = _cjk_len(it["content"])
            if total_chars + item_chars > self.max_card_cjk_chars:
                break
            result.append(it)
            total_chars += item_chars
        return result

    def _write_card(
        self, path: Path, items: List[Dict[str, Any]], card_name: str, reason: str
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.utcnow().isoformat()
        lines = ["<!-- memory_cards: %s | rebuilt: %s | reason: %s -->" % (card_name, now, reason)]
        for it in items:
            ttl = _ttl_label(it.get("expires_at"))
            lines.append(
                "- %s <!-- source:memory:%s type:%s updated:%s ttl:%s -->"
                % (it["content"], it["id"], it["type"], it.get("created_at", "")[:10], ttl)
            )
        content = "\n".join(lines) + "\n"

        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            fd = -1  # mark as closed
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
            raise

    @staticmethod
    def _parse_line(line: str) -> Optional[Dict[str, str]]:
        m = _CARD_LINE_RE.match(line.strip())
        if m:
            return {
                "content": m.group(1),
                "source_id": m.group(2),
                "type": m.group(3),
                "updated": m.group(4),
                "ttl": m.group(5),
            }
        return None
