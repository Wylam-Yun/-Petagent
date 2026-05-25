# Stage 2 Completion: Card-Only Memory

**Date:** 2026-05-26
**Status:** COMPLETE

## Files Changed

| File | Change |
|---|---|
| `backend/app/runtime/notebook.py` | New: NotebookManager with dual-format parsing, deterministic selection, atomic append, migration |
| `backend/app/runtime/memory_triggers.py` | New: ~40 trigger phrases across 4 categories |
| `backend/app/runtime/memory_judgment.py` | New: Bounded judgment queue with dedup, provider gate check |
| `backend/app/pet/prompt_builder.py` | Added `build_memory_judgment_messages()`. Updated `build_fast_reply_messages()` to use `selected_card_items`. Updated `build_pet_messages()` to inject `notebook_user`/`notebook_memory` for thinking mode. |
| `backend/app/runtime/dispatcher.py` | Removed `_EXPLICIT_MEMORY_KEYWORDS`. Added trigger detection in post-commit. Added `memory_judgment_queue`/`notebook_manager` params. Set `memory_ack_hint` on PetResponse. Removed explicit command detection from `_collect_memory_candidates`. |
| `backend/app/runtime/memory_cards.py` | Added `_has_v13_format()` guard to skip rebuild when V1.3 notebook lines present. |
| `backend/app/runtime/context_manager.py` | Added `notebook_manager` param to `build()`. Calls `select_for_fast_reply()`/`select_for_thinking()` for fast_reply/thinking profiles. Stores in `selected_card_items`. |
| `backend/app/main.py` | Wires NotebookManager, MemoryJudgmentQueue into dispatcher, maintenance_service. Runs migration on startup. |
| `backend/app/runtime/maintenance.py` | Added judgment queue processing at Priority 1.5 (between curator and summary jobs). Added `memory_judgment_queue`/`notebook_manager` params. |
| `backend/app/runtime/actions.py` | Added `memory_ack_hint: Optional[str]` to PetResponse. |
| `backend/app/runtime/concurrency.py` | Added `is_available()` method to ProviderGate. |
| `backend/tests/test_notebook.py` | New: 17 tests for parsing, selection, append, migration |
| `backend/tests/test_memory_triggers.py` | New: 7 tests for trigger detection |
| `backend/tests/test_memory_judgment.py` | New: 10 tests for queue, dedup, validation, backpressure |
| `backend/tests/test_fast_reply_contract.py` | Added 3 tests: selected_card_items, memory_ack_hint, no-hint-without-trigger |
| `backend/tests/test_memory_cards.py` | Added 2 tests: legacy rebuild guard for V1.3 format |

## Behavior Changed

1. **Card format**: New V1.3 format `- [YYYY-MM-DD HH:MM][category] content` replaces old HTML-comment format. Parser handles both formats. One-time migration on startup.
2. **Card selection**: Deterministic priority-based selection (identity > preference > relationship > project > temporary, newer first). Fast reply: 1 user + 1 memory. Thinking: up to 8 user + 12 memory.
3. **Memory triggers**: Expanded from 6 keywords to ~40 phrases across 4 categories (explicit, preference, identity, relationship).
4. **Background judgment**: New bounded queue (max 5 pending, deduplicated) processes memory judgments via LLM during maintenance ticks. No blocking on fast reply path.
5. **Memory ack hint**: Explicit memory triggers set `memory_ack_hint="我先记到小本本"` on PetResponse (post-reply metadata field).
6. **Legacy rebuild guard**: `MemoryCardManager.rebuild()` skips when V1.3 notebook format lines detected, preventing old-format overwrites.
7. **Old trigger keywords removed**: `_EXPLICIT_MEMORY_KEYWORDS` removed from dispatcher, replaced by trigger detection system.

## Tests Run

- 597 passed, 24 skipped, 0 failed (full backend test suite)
- 39 new tests across 3 new files + 2 updated files
- Frontend TypeScript: not changed (no frontend modifications)

## Acceptance Checks

1. `pytest backend/tests/test_notebook.py -v` — 17 passed
2. `pytest backend/tests/test_memory_triggers.py -v` — 7 passed
3. `pytest backend/tests/test_memory_judgment.py -v` — 10 passed
4. `pytest backend/tests/test_fast_reply_contract.py -v` — 12 passed (9 existing + 3 new)
5. `pytest backend/tests/test_memory_cards.py -v` — 28 passed (26 existing + 2 new)
6. `pytest backend/tests/ -q` — 597 passed, 24 skipped
7. Fast reply prompt includes real card memory items (test_fast_reply_prompt_uses_selected_card_items)
8. Thinking prompt includes bounded card memory items (select_for_thinking with 8+12 cap)
9. No scored_memories/important_quotes/recall in fast_reply/thinking paths (verified in Stage 1 tests)
10. Legacy rebuild skips when V1.3 notebook format detected (test_legacy_rebuild_skips_when_v13_format_detected)
11. Old-format card files migrated on startup (test_migrate_old_format)
12. memory_ack_hint field present on fast reply PetResponse when explicit trigger detected (test_fast_reply_response_has_memory_ack_hint)

## Pre-Review Issues Addressed

All 14 issues from pre-review (4 Critical, 6 Important, 4 Minor) resolved:
- Issue 1: ContextManager gets notebook_manager, calls select_for_fast_reply/thinking
- Issue 2: _EXPLICIT_MEMORY_KEYWORDS removed, trigger system replaces it
- Issue 3: Dual-format parser handles old HTML-comment and new format
- Issue 4: memory_ack_hint as post-reply metadata field on PetResponse
- Issue 5: deque(maxlen=5) with threading.Lock, in-memory, provider_gate check
- Issue 6: _has_v13_format guard on rebuild
- Issue 7: main.py in Files Changed, full wiring
- Issue 8: Guard checks for `- [` pattern specifically
- Issue 9: migrate_if_needed() with 4-step process
- Issue 10: selected_card_items data flow via ContextManager
- Issue 11: .strip() + whitespace collapse normalization
- Issue 12: test_skips_judgment_under_backpressure added
- Issue 13: Old type mapping defined (recent_mood → temporary, etc.)
- Issue 14: maintenance.py in Files Changed

## Remaining Risks

- NotebookManager parser only recognizes lines starting with `- [` (new) or `- content <!-- ... -->` (old). Any future format changes need parser updates.
- Judgment queue is in-memory only — lost on restart. Acceptable since triggers are idempotent.
- `memory_card_manager` still active for proactive/recall profiles. Full deprecation deferred.
- Frontend does not yet use `memory_ack_hint` — Stage 5 could wire this into a visual indicator.
