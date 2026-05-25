# Stage 3 Completion: Nightly Memory Cleanup

**Date:** 2026-05-26
**Status:** COMPLETE

## Files Changed

| File | Change |
|---|---|
| `backend/app/runtime/nightly_cleanup.py` | New: NightlyCleanupRunner with safety gates, 60s timeout, operation validation |
| `backend/app/pet/prompt_builder.py` | Added `build_nightly_cleanup_messages()` with aging rules, current time, conversation context |
| `backend/app/runtime/notebook.py` | Added `apply_cleanup_operations()`, `_backup_file()`, `_restore_backup()`, `_rewrite_and_validate()`, `_find_line_prefix()` |
| `backend/app/runtime/maintenance.py` | Added nightly cleanup at Priority 1.3 (between curator P1 and judgment queue P1.5). Added `nightly_cleanup_runner` param. |
| `backend/app/main.py` | Wires NightlyCleanupRunner with slow_llm_provider, provider_gate, dispatcher. Stores on app.state. |
| `backend/app/runtime/context_store.py` | Added `recent_events_bounded(limit=200, max_bytes=20480)` to EventLogStore |
| `backend/tests/test_nightly_cleanup.py` | New: 19 tests for safety gates, operations, validation, identity protection |

## Behavior Changed

1. **Nightly cleanup**: At local midnight, LLM proposes add/update/delete operations on user.md and memory.md. Backend validates and applies atomically with backup/restore.
2. **Aging rules enforced**: identity lines cannot be deleted (validator rejects), temporary deleted after 3 days, project summarized after 3 days.
3. **Safety gates**: once per day, skip during active responses, skip under provider backpressure, skip when event loop stale >60s, 60s timeout via threading.Timer.
4. **Bounded event log read**: 200 rows / 20KB max for cleanup prompt context.
5. **Atomic operations**: backup before rewrite, validate after write, restore on failure.

## Tests Run

- 616 passed, 24 skipped, 0 failed (full backend test suite)
- 19 new tests in `test_nightly_cleanup.py`

## Pre-Review Issues Addressed

All 15 issues resolved:
- Issue 1: threading.Timer(60s) timeout
- Issue 2: recent_events_bounded with max_bytes
- Issue 3: event_loop_tick staleness check in should_run()
- Issue 4: should_run() returns False when not due, falls through to lower priorities
- Issue 5: validation = re-read + parse + check line count
- Issue 6: prefix match on old lines
- Issue 7: uses slow_llm_provider
- Issue 8: LLM call before notebook lock
- Issue 9: test_apply_skips_update_when_old_line_missing
- Issue 10: lock held for entire validate-backup-apply-validate cycle
- Issue 11: old field uses full raw line with `- ` prefix
- Issue 12: test_cleanup_runner_handles_malformed_llm_output
- Issue 13: stored on app.state.nightly_cleanup_runner
- Issue 14: SQLite-backed maintenance_state persists across restarts
- Issue 15: identity deletion rejected in validator
