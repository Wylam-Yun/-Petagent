# Stage 2: Card-Only Memory

**Date:** 2026-05-26
**Goal:** Replace dynamic memory retrieval with deterministic card-only memory. New card format, new trigger rules, background judgment queue, atomic notebook writes. Wire real card selection into fast reply and thinking prompts.

## Pre-Review Issues Addressed

14 issues from pre-review subagent (4 Critical, 6 Important, 4 Minor) — all addressed below.

## Scope

Backend memory system only. No frontend changes. No nightly cleanup (Stage 3).

### 1. New Card Format and Parser

**File:** `backend/app/runtime/notebook.py` (new)

New `NotebookManager` class that owns the canonical card files directly:

```python
class NotebookManager:
    def __init__(self, user_path: Path, memory_path: Path):
        ...

    def parse_user(self) -> List[NotebookEntry]:
        """Parse user.md into structured entries. Handles BOTH old and new formats."""

    def parse_memory(self) -> List[NotebookEntry]:
        """Parse memory.md into structured entries. Handles BOTH old and new formats."""

    def select_for_fast_reply(self) -> Tuple[Optional[str], Optional[str]]:
        """Select 1 user.md item + 1 memory.md item deterministically."""

    def select_for_thinking(self) -> Tuple[List[str], List[str]]:
        """Select up to 8 user.md items + 12 memory.md items."""

    def append_line(self, target: str, category: str, content: str) -> bool:
        """Append a validated memory line with backend timestamp."""

    def read_raw(self, target: str) -> str:
        """Read raw file content."""

    def migrate_if_needed(self, memory_card_manager=None) -> bool:
        """One-time migration from old format to new format."""
```

`NotebookEntry` dataclass:
- `timestamp`: str (from file, empty for old-format lines)
- `category`: str (identity, preference, relationship, project, temporary)
- `content`: str
- `line_number`: int
- `raw`: str (original line)

**File format (new V1.3):**
```md
- [2026-05-25 20:42][preference] 主人希望豆豆快速回应优先。
- [2026-05-25 21:10][project] 主人正在调 PetAgent V1.3 的快速档。
```

**Dual-format parsing (addresses Issue 3):**
The parser recognizes TWO line formats:
1. New: `- [YYYY-MM-DD HH:MM][category] content`
2. Old: `- content <!-- source:memory:N type:T updated:D ttl:V -->`

For old-format lines:
- `timestamp` = empty string
- `category` inferred from `type:` field: `user_preference`→`preference`, `relationship`→`relationship`, `stable_memory`→`identity`, `important_quote`→`preference`, `recent_mood`→`temporary`, `important_event`→`project`, `habit`→`preference`
- `content` = text before `<!--` marker
- Lines with unrecognized format are preserved on disk but not parsed

**Migration (addresses Issue 9):**
`migrate_if_needed()` runs once on startup:
1. Check if canonical files have any new-format lines (`- [` pattern). If yes, skip.
2. Check if canonical files have old-format lines. If yes, convert in-place to new format.
3. If canonical files are empty, check old subdirectory paths (`user_preferences/card.md`, `momo_memories/card.md`). If they have data, import into new format.
4. Add `<!-- v1.3_migrated -->` header comment to mark migration complete.

**Selection rules (deterministic, no LLM):**
- Parse lines, group by category
- For `user.md`: prefer `identity` > `preference` > newer items
- For `memory.md`: prefer `relationship` > `project` > newer items
- Ignore malformed lines (preserve on disk)
- Cap parsed lines to latest 200 per file
- Cap selected prompt text to 400 Chinese characters total

### 2. Memory Trigger Rules

**File:** `backend/app/runtime/memory_triggers.py` (new)

Expanded trigger detection from 6 keywords to ~40 phrases per spec:

```python
EXPLICIT_MEMORY_TRIGGERS = [
    "记住", "你要记得", "帮我记", "别忘了", "以后记得",
    "以后你要知道", "这个很重要", "记到小本本", "写进小本本",
]

PREFERENCE_TRIGGERS = [
    "我喜欢", "我不喜欢", "我讨厌", "我害怕", "我习惯",
    "我希望你", "我更喜欢", "我不想要", "以后不要", "以后可以",
]

IDENTITY_TRIGGERS = [
    "我叫", "我的名字", "我是", "我的生日", "我住在",
    "我的工作", "我的学校", "我的猫", "我的家人", "我的朋友",
]

RELATIONSHIP_TRIGGERS = [
    "今天我们", "刚刚我们", "以后我们", "这是我们的",
    "你陪我", "我们约好", "这次要记住",
]

def detect_memory_triggers(user_text: str) -> List[str]:
    """Return list of matched trigger categories."""
```

### 3. Background Memory Judgment Queue

**File:** `backend/app/runtime/memory_judgment.py` (new)

Bounded queue with deduplication (addresses Issues 5, 11):

```python
class MemoryJudgmentQueue:
    def __init__(self, provider, provider_gate=None, max_pending=5, timeout_seconds=30):
        self._pending = collections.deque(maxlen=max_pending)  # Issue 5a
        self._lock = threading.Lock()  # Issue 5b: sync threading model
        self._seen: set = set()  # normalized inputs for dedup
        ...

    def enqueue(self, user_text: str, trigger_categories: List[str]) -> bool:
        """Enqueue a judgment job. Returns False if queue full or duplicate.
        Dedup by .strip() + whitespace collapse (Issue 11)."""

    def process_one(self) -> Optional[Dict[str, Any]]:
        """Process one pending job. Returns judgment result or None.
        Checks provider_gate.is_available() before starting (Issue 12)."""

    def pending_count(self) -> int
```

Constraints:
- At most 1 running at a time
- At most 5 pending
- Deduplicate by `.strip()` + whitespace collapse (Issue 11)
- Short timeout (30s)
- Small output budget
- In-memory only — lost on restart is acceptable (triggers are idempotent) (Issue 5c)
- Check `provider_gate.is_available()` before starting judgment (Issue 12)

### 4. Memory Judgment Prompt

**File:** `backend/app/pet/prompt_builder.py` (add function)

Add `build_memory_judgment_messages(user_text, trigger_categories)`:
- System prompt: judge whether to write to notebook
- User message: the user text and matched triggers
- Output schema: `{should_write, target, category, content, reason}`
- Allowed targets: `user.md`, `memory.md`
- Allowed categories: `identity`, `preference`, `relationship`, `project`, `temporary`

### 5. Atomic Notebook Append with Validation

**File:** `backend/app/runtime/notebook.py` (in NotebookManager)

`append_line()` must:
- Validate target whitelist (`user.md`, `memory.md`)
- Validate category whitelist
- Reject unsafe content (secrets, PII per policy)
- Reject duplicate lines
- Add backend timestamp (model must not output timestamps)
- Use process-local write lock
- Write to temp file, atomic rename
- Validate after write

### 6. Legacy Rebuild Prevention

**File:** `backend/app/runtime/memory_cards.py`

Modify `MemoryCardManager.rebuild()` (addresses Issues 6, 8):
- Check if canonical V1.3 notebook files have content
- If canonical files have V1.3 format lines (lines starting with `- [`), skip rebuild
- Log a warning that rebuild was skipped due to V1.3 notebook presence
- Keep legacy rebuild available for empty/migration scenarios only
- Guard checks specifically for `- [` pattern (not just "any content exists") to avoid breaking tests that use temp dirs with empty files (Issue 8)

### 7. Wire Card Selection into Prompt Builders

**File:** `backend/app/runtime/context_manager.py` (addresses Issues 1, 10)

Update `ContextManager.build()`:
- Add `notebook_manager` parameter (alongside existing `memory_card_manager`)
- When `profile in ("fast_reply", "thinking")` and `notebook_manager` is provided:
  - For fast_reply: call `notebook_manager.select_for_fast_reply()`, store result in `cognition_context["selected_card_items"]`
  - For thinking: call `notebook_manager.select_for_thinking()`, store result in `cognition_context["selected_card_items"]`
- Old `memory_cards` key still populated from `memory_card_manager` for backward compatibility (proactive, recall profiles)

**File:** `backend/app/pet/prompt_builder.py`

Update `build_fast_reply_messages()`:
- Read from `cognition_context["selected_card_items"]` if present (new path)
- Fall back to `cognition_context["memory_cards"]` (old path, for backward compat)
- Replace empty `memory_hints` with real selected items

Update `build_pet_messages()` (thinking mode path):
- When `cognition_context` has `selected_card_items`, use those for richer context
- Include up to 8 user.md items + 12 memory.md items

### 8. Wire Memory Triggers into Fast Reply Path

**File:** `backend/app/runtime/dispatcher.py` (addresses Issue 2, 4)

In fast reply Phase 2 (after LLM call, before Phase 3):
- Call `detect_memory_triggers(user_text)` on the user input
- If triggers match, call `memory_judgment_queue.enqueue(user_text, categories)`
- Do NOT block on the judgment result
- If explicit memory trigger detected, set `memory_ack_hint` field on PetResponse (Issue 4: post-reply metadata, not appended to reply text)
- **Remove** `_EXPLICIT_MEMORY_KEYWORDS` list — the new trigger system replaces it (Issue 2)
- `_collect_memory_candidates()` remains for thinking mode's LLM-suggested `memory_update` (the explicit command detection part is removed since triggers handle it)

**File:** `backend/app/runtime/actions.py`

Add `memory_ack_hint: Optional[str] = None` to `PetResponse` (Issue 4: clean post-reply field).

### 9. Wire Memory Judgment Processing

**File:** `backend/app/runtime/maintenance.py` (addresses Issues 5d, 14)

Add judgment queue processing at Priority 1.5 (between curator at P1 and summary jobs at P2):
- Add `memory_judgment_queue` parameter to `MaintenanceService.__init__()` (Issue 14)
- In `_tick_inner()`, after Priority 1 (curator), before Priority 2 (summaries):
  ```python
  # Priority 1.5: Process memory judgment queue
  try:
      if self.memory_judgment_queue and self.memory_judgment_queue.pending_count() > 0:
          judgment = self.memory_judgment_queue.process_one()
          if judgment and judgment.get("should_write"):
              self.notebook_manager.append_line(
                  judgment["target"], judgment["category"], judgment["content"]
              )
              result["memory_judgment_written"] = 1
  except Exception:
      logger.warning("Memory judgment processing failed", exc_info=True)
  ```
- If judgment returns `should_write=True`, call `notebook.append_line(target, category, content)`
- Write failures are logged but don't block responses

### 10. Remove Dynamic Retrieval from Prompt Paths

**File:** `backend/app/runtime/context_manager.py`

For `fast_reply` and `thinking` profiles:
- Ensure `scored_memories()` is NOT called
- Ensure `important_quotes()` is NOT called
- Ensure `episode_summary_store.recent()` is NOT called
- Ensure `daily_summary_store.recent()` is NOT called
- These are already disabled in Stage 1, but verify no code path re-enables them

### 11. main.py Wiring

**File:** `backend/app/main.py` (addresses Issue 7)

- Create `NotebookManager` instance after `MemoryCardManager` creation
- Pass `NotebookManager` to `RuntimeDispatcher` (new constructor parameter)
- Pass `NotebookManager` to `ContextManager.build()` via dispatcher
- Pass `NotebookManager` to `MaintenanceService` (new constructor parameter)
- Pass `MemoryJudgmentQueue` to `MaintenanceService` and `RuntimeDispatcher`
- Run `notebook_manager.migrate_if_needed(memory_card_manager)` on startup (non-testing only)

### 12. Dispatcher Trigger Integration

**File:** `backend/app/runtime/dispatcher.py` (addresses Issue 2)

- Remove `_EXPLICIT_MEMORY_KEYWORDS` list entirely
- Remove the explicit command detection block from `_collect_memory_candidates()` (lines 587-600)
- Keep the LLM-suggested `memory_update` part of `_collect_memory_candidates()` for thinking mode
- Add `memory_judgment_queue` and `notebook_manager` constructor parameters
- In fast reply post-commit: call `detect_memory_triggers(user_text)`, enqueue if matched
- In thinking post-commit: also call `detect_memory_triggers(user_text)`, enqueue if matched

### 13. Test Updates

**File:** `backend/tests/test_notebook.py` (new)

New tests:
- `test_parse_valid_lines`: parse lines with timestamp+category+content
- `test_parse_old_format_lines`: parse old HTML-comment format lines, infer category
- `test_parse_mixed_format`: file with both old and new format lines
- `test_parse_malformed_lines_ignored`: malformed lines preserved but not parsed
- `test_migrate_old_format`: migration converts old format to new
- `test_migrate_skips_if_new_format_present`: migration skips if new lines exist
- `test_select_fast_reply`: selects 1 user + 1 memory item by priority
- `test_select_thinking`: selects up to 8 user + 12 memory items
- `test_append_line_adds_timestamp`: backend adds timestamp, rejects model timestamps
- `test_append_line_validates_category`: rejects unknown categories
- `test_append_line_rejects_duplicates`: duplicate content not appended
- `test_append_line_rejects_secrets`: sensitive content rejected
- `test_append_line_atomic`: file is valid after append

**File:** `backend/tests/test_memory_triggers.py` (new)

New tests:
- `test_explicit_triggers_detected`: "记住这个", "帮我记" match
- `test_preference_triggers_detected`: "我喜欢咖啡" matches
- `test_identity_triggers_detected`: "我叫小明" matches
- `test_relationship_triggers_detected`: "今天我们去了公园" matches
- `test_no_trigger_on_normal_text`: "你好" doesn't match
- `test_multiple_triggers`: "我喜欢咖啡，记住这个" matches both

**File:** `backend/tests/test_memory_judgment.py` (new)

New tests:
- `test_enqueue_adds_to_queue`: job appears in pending
- `test_dedup_same_input`: duplicate normalized input rejected
- `test_queue_max_pending`: rejects when queue full
- `test_process_one_calls_provider`: LLM called with correct prompt
- `test_process_one_validates_output`: invalid target/category rejected
- `test_process_one_appends_to_notebook`: valid judgment writes to file
- `test_skips_judgment_under_backpressure`: provider_gate busy → no judgment (Issue 12)

**File:** `backend/tests/test_fast_reply_contract.py` (update)

- Update `test_fast_reply_prompt_excludes_forbidden_fields` to verify memory_hints now has real content
- Add test for `memory_ack_hint` field on PetResponse

**File:** `backend/tests/test_memory_cards.py` (update)

- Add test that legacy rebuild skips when V1.3 notebook format detected

## Files Changed

| File | Change Type |
|---|---|
| `backend/app/runtime/notebook.py` | New |
| `backend/app/runtime/memory_triggers.py` | New |
| `backend/app/runtime/memory_judgment.py` | New |
| `backend/app/pet/prompt_builder.py` | Modify (add judgment prompt, wire cards) |
| `backend/app/runtime/dispatcher.py` | Modify (wire triggers + judgment, remove old keywords) |
| `backend/app/runtime/memory_cards.py` | Modify (legacy rebuild guard) |
| `backend/app/runtime/context_manager.py` | Modify (add notebook_manager param, selected_card_items) |
| `backend/app/main.py` | Modify (wire NotebookManager, MemoryJudgmentQueue) |
| `backend/app/runtime/maintenance.py` | Modify (integrate judgment queue processing) |
| `backend/app/runtime/actions.py` | Modify (add memory_ack_hint to PetResponse) |
| `backend/tests/test_notebook.py` | New |
| `backend/tests/test_memory_triggers.py` | New |
| `backend/tests/test_memory_judgment.py` | New |
| `backend/tests/test_fast_reply_contract.py` | Modify |
| `backend/tests/test_memory_cards.py` | Modify |

## Nubia Constraints

- No SQLite queries in prompt path (deterministic file reads only)
- Background judgment queue bounded (max 5 pending, 1 running)
- Judgment timeout 30s to avoid blocking
- File writes use atomic rename (no partial writes)
- No new provider calls in fast reply path (judgment is background)
- Queue is in-memory (lost on restart acceptable — triggers are idempotent)

## Rollback / Compatibility

- Old `MemoryCardManager` kept for legacy compatibility
- Old `MemoryManager` SQLite tables kept for logs/debugging
- New `NotebookManager` is additive, doesn't break existing code
- Card format change is a migration boundary (old format lines converted on first startup)
- `memory_cards` key still populated in cognition_context for proactive/recall profiles
- `selected_card_items` key is new — old code ignores it, new code reads it

## Acceptance Checks

1. `pytest backend/tests/test_notebook.py -v` — all pass
2. `pytest backend/tests/test_memory_triggers.py -v` — all pass
3. `pytest backend/tests/test_memory_judgment.py -v` — all pass
4. `pytest backend/tests/test_fast_reply_contract.py -v` — all pass (updated)
5. `pytest backend/tests/test_memory_cards.py -v` — all pass (updated)
6. `pytest backend/tests/ -q` — full suite passes
7. Fast reply prompt includes real card memory items
8. Thinking prompt includes bounded card memory items
9. No `scored_memories`, `important_quotes`, `recall_events`, `episode_summary_store.recent`, `daily_summary_store.recent` called in fast_reply/thinking prompt paths
10. Legacy rebuild skips when V1.3 notebook format detected
11. Old-format card files are migrated to new format on startup
12. `memory_ack_hint` field present on fast reply PetResponse when explicit trigger detected
