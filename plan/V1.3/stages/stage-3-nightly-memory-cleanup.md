# Stage 3: Nightly Memory Cleanup

**Date:** 2026-05-26
**Goal:** Add nightly "整理小本本" cleanup that runs at local midnight. LLM proposes add/update/delete operations on user.md and memory.md. Backend validates and applies atomically with backup/restore safety.

## Pre-Review Issues Addressed

15 issues from pre-review (3 Critical, 7 Important, 5 Minor) — all addressed below.

## Scope

Backend only. No frontend changes. Builds on Stage 2's NotebookManager.

### 1. Nightly Cleanup Prompt Builder

**File:** `backend/app/pet/prompt_builder.py` (add function)

Add `build_nightly_cleanup_messages(user_content, memory_content, recent_events, current_time)`:
- System prompt: You are cleaning up 豆豆's notebook. Propose add/update/delete operations.
- User message: current user.md content, memory.md content, today's conversation summary, current local time
- Output schema (Issue 11: `old` field uses full raw line including `- ` prefix):
```json
{
  "add": [{"target": "memory.md", "category": "project", "content": "..."}],
  "update": [{"target": "memory.md", "old": "- [2026-05-25 20:42][project] ...", "new_category": "project", "new_content": "..."}],
  "delete": [{"target": "memory.md", "old": "- [2026-05-22 09:00][temporary] ...", "reason": "expired"}]
}
```
- Aging rules in system prompt:
  - `identity`: keep unless contradicted by newer explicit correction
  - `preference`: keep long term, merge duplicates
  - `relationship`: keep important, merge similar
  - `project`: after 3 days, summarize related items into one line
  - `temporary`: delete after 3 days unless promoted

### 2. Cleanup Operation Validator

**File:** `backend/app/runtime/notebook.py` (add methods to NotebookManager)

Add `apply_cleanup_operations(operations: Dict) -> Dict[str, int]` (Issue 10: acquires `self._lock` for entire validate-backup-apply-validate cycle; Issue 8: LLM call happens BEFORE lock acquisition):
- Validates each operation:
  - `add`: target whitelist, category whitelist, content not empty, not sensitive
  - `update`: old line must exist as **prefix match** against raw lines in file (Issue 6: prefix match on `- [YYYY-MM-DD` portion to handle timestamp precision differences), new_category valid, new_content not empty
  - `delete`: old line must exist as prefix match; **reject deletes of identity-category lines** (Issue 15: enforce "identity: keep" rule in validator, not just in prompt)
- Returns `{"adds": N, "updates": N, "deletes": N, "errors": N}`

Add `_backup_file(path: Path) -> Path`:
- Copy current file to `{name}.bak.{timestamp}` in same directory
- Return backup path

Add `_restore_backup(path: Path, backup_path: Path) -> bool`:
- Copy backup back to original path using atomic rename

Add `rewrite_file(path: Path, lines: List[str], backup_path: Path) -> bool` (Issue 5: validation definition):
- Atomic rewrite: write to temp file, os.replace
- Validation after write: re-read file, parse all lines with `_parse_line()`, confirm zero parse failures for new-format lines, verify line count matches
- On validation failure: restore backup, return False

### 3. Nightly Cleanup Runner

**File:** `backend/app/runtime/nightly_cleanup.py` (new)

```python
class NightlyCleanupRunner:
    def __init__(self, notebook_manager, provider, event_log_store,
                 maintenance_state, provider_gate, dispatcher=None):
        ...

    def should_run(self) -> bool:
        """Check if cleanup is due. Multiple safety gates (Issues 1, 3):"""

    def run(self) -> Dict[str, int]:
        """Execute one cleanup cycle. Returns operation counts.
        LLM call happens BEFORE notebook lock (Issue 8)."""
```

Safety gates in `should_run()` (Issues 1, 3):
- Run at most once per local day (check `last_cleanup_date` in maintenance_state, SQLite-backed so persists across restarts — Issue 14)
- Skip if `provider_gate.is_available("llm_slow")` is False (backpressure)
- Skip if `dispatcher.active_requests > 0` (active response)
- Skip if `dispatcher.event_loop_tick` is stale > 60s (Issue 3: health degradation — event loop stalled)
- `should_run()` returns empty result when not due, so lower priorities still run (Issue 4)

Timeout enforcement (Issue 1):
- `run()` uses `threading.Timer(60, cancel_flag.set)` to enforce 60s timeout
- LLM provider call wrapped in try/except with timeout check between operations
- If timeout fires, stop processing, return partial results, log warning

`run()` flow (Issue 8: LLM call before lock):
1. Read current user.md and memory.md content (no lock needed — read-only)
2. Read bounded event log (Issue 2: see section 6)
3. Call LLM provider with cleanup prompt → get operations
4. Validate operations (check targets, categories, identity protection)
5. Call `notebook_manager.apply_cleanup_operations(validated_ops)` — this acquires lock
6. Set `last_cleanup_date` in maintenance_state
7. Return operation counts

Uses `slow_llm_provider` (Issue 7: background task, no latency requirement).

### 4. Wire into Maintenance Service

**File:** `backend/app/runtime/maintenance.py` (modify)

Add nightly cleanup in `_tick_inner()`:
- Position: **after** Priority 1 (curator), **before** Priority 1.5 (judgment queue) — not Priority 0.5 (Issue 4: curator gets first chance since it processes user-visible memory writes)
- Only runs when `should_run()` returns True (cheap date check)
- If due and gates pass, call `nightly_cleanup_runner.run()`
- When not due, falls through to lower priorities (Issue 4)
- When cleanup runs and consumes the tick, that's acceptable — once per day
- Add `nightly_cleanup_runner` parameter to `__init__()`

**File:** `backend/app/main.py` (modify)

- Create `NightlyCleanupRunner` with `slow_llm_provider` (Issue 7)
- Wire into `MaintenanceService`
- Store on `app.state.nightly_cleanup_runner` (Issue 13)
- Pass `dispatcher` reference for active_requests check

### 5. NotebookManager Rewrite Support

**File:** `backend/app/runtime/notebook.py` (enhance)

The `apply_cleanup_operations` method (Issue 10: holds `self._lock` for entire cycle):
1. Acquire `self._lock`
2. Read current file content
3. Apply deletes: remove lines matching prefix
4. Apply updates: replace lines matching prefix with new content
5. Apply adds: append new lines with backend timestamp
6. Backup current file
7. Write atomically (temp + os.replace)
8. Validate: re-read, parse, check line count
9. On validation failure: restore backup
10. Release lock

### 6. Event Log Bounded Read

**File:** `backend/app/runtime/context_store.py` (add method)

Add `recent_events_bounded(limit=200, max_bytes=20480)` to `EventLogStore` (Issue 2):
- Fetch `limit` rows using existing `recent_events(limit=limit)` logic
- Serialize each row to a compact string (user_text + pet_reply + mood)
- Accumulate until `max_bytes` reached, then stop
- Return the bounded list
- Implementation: Python-side byte counting after SQL fetch (simpler than SQL LENGTH, and the limit=200 cap makes it cheap)

### 7. Test Updates

**File:** `backend/tests/test_nightly_cleanup.py` (new)

New tests:
- `test_cleanup_prompt_includes_aging_rules`: prompt contains aging guidance
- `test_cleanup_prompt_includes_current_time`: prompt has local time
- `test_apply_add_operations`: valid adds are applied
- `test_apply_update_operations`: matching lines replaced
- `test_apply_delete_operations`: matching lines removed
- `test_apply_validates_target`: invalid target rejected
- `test_apply_validates_category`: invalid category rejected
- `test_apply_rejects_sensitive_content`: sensitive adds rejected
- `test_apply_skips_update_when_old_line_missing` (Issue 9): graceful skip
- `test_apply_rejects_identity_delete` (Issue 15): identity lines protected
- `test_backup_and_restore`: backup works, restore works
- `test_atomic_rewrite_validates`: corrupt write triggers restore
- `test_should_run_once_per_day`: second call returns False
- `test_should_run_skips_during_active_response`: active_requests > 0 → skip
- `test_should_run_skips_under_backpressure`: provider busy → skip
- `test_should_run_skips_when_event_loop_stale` (Issue 3): stale tick → skip
- `test_cleanup_runner_integration`: full cycle with mock LLM
- `test_cleanup_runner_handles_malformed_llm_output` (Issue 12): invalid JSON → graceful skip
- `test_cleanup_preserves_identity_lines`: identity items not deleted
- `test_cleanup_timeout` (Issue 1): 60s timeout enforced

**File:** `backend/tests/test_notebook.py` (update)

- Add tests for `apply_cleanup_operations`, `rewrite_file`, backup/restore

## Files Changed

| File | Change Type |
|---|---|
| `backend/app/runtime/nightly_cleanup.py` | New |
| `backend/app/pet/prompt_builder.py` | Modify (add cleanup prompt) |
| `backend/app/runtime/notebook.py` | Modify (add cleanup operations, backup/restore) |
| `backend/app/runtime/maintenance.py` | Modify (add nightly cleanup priority) |
| `backend/app/main.py` | Modify (wire NightlyCleanupRunner, store on app.state) |
| `backend/app/runtime/context_store.py` | Modify (add recent_events_bounded) |
| `backend/tests/test_nightly_cleanup.py` | New |
| `backend/tests/test_notebook.py` | Modify (add cleanup operation tests) |

## Nubia Constraints

- Cleanup runs at most once per local day (SQLite-backed maintenance_state)
- Skip during active responses (dispatcher.active_requests > 0)
- Skip under provider backpressure (provider_gate.is_available check)
- Skip when event loop stale > 60s (health degradation)
- Bounded event log read (200 rows / 20KB, Python-side byte counting)
- Short timeout (60s, threading.Timer)
- No WAL checkpoint coupling
- Atomic file writes with backup/restore
- Cleanup does not block fast reply or thinking responses
- LLM call happens BEFORE notebook lock acquisition
- Uses slow_llm_provider (no contention with fast reply path)

## Rollback / Compatibility

- Nightly cleanup is additive — existing code unaffected
- If cleanup fails, backup is restored, last valid content preserved
- `last_cleanup_date` in maintenance_state (SQLite) tracks completion, persists across restarts
- Old `MemoryCardManager` rebuild still guarded by V1.3 format check
- When not due, cleanup returns empty result so lower priorities still run

## Acceptance Checks

1. `pytest backend/tests/test_nightly_cleanup.py -v` — all pass
2. `pytest backend/tests/test_notebook.py -v` — all pass (updated)
3. `pytest backend/tests/ -q` — full suite passes
4. Cleanup prompt includes aging rules and current time
5. Add/update/delete operations validated before applying
6. Backup created before rewrite, restore on failure
7. Cleanup skips when active_requests > 0
8. Cleanup skips under provider backpressure
9. Cleanup skips when event loop stale > 60s
10. Cleanup runs at most once per local day
11. Atomic file writes (temp + os.replace)
12. 60s timeout enforced
13. Identity lines cannot be deleted
14. Malformed LLM output handled gracefully
15. LLM call happens before notebook lock
