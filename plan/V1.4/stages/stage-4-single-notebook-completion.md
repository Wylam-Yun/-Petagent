# V1.4 Stage 4 Completion: Single Notebook Migration And Selection

**Date:** 2026-05-29
**Commit:** pending at time of writing

## Result

Stage 4 makes `backend/data/memory_cards/memory.md` the canonical prompt-facing
notebook. `user.md` remains only as a migration compatibility stub and is no
longer used as a prompt source for fast reply, thinking mode, memory judgment,
or nightly cleanup.

Fast mode now selects up to 10 canonical notebook lines. Thinking mode selects
up to 20 canonical notebook lines. Both paths avoid SQLite scored memory,
retrieval, daily digest, tools, device state, and current time.

## Changed Files

- `backend/app/runtime/notebook.py`
  - changes fast/thinking selection to return `list[str]` from canonical
    `memory.md`;
  - adds V1.4 single-notebook marker and `user.md` stub;
  - migrates parseable `user.md` and `memory.md` lines into canonical
    `memory.md`;
  - deduplicates migrated content;
  - backs up both old files before rewrite;
  - redirects `append_line("user.md", ...)` to `memory.md`;
  - redirects legacy cleanup operations targeting `user.md` to `memory.md`;
  - creates canonical `memory.md` during cleanup add operations if missing.
- `backend/app/runtime/context_manager.py`
  - treats `selected_card_items` as the V1.4 single notebook list for
    `fast_reply` and `thinking`.
- `backend/app/pet/prompt_builder.py`
  - reads V1.4 selected notebook lines with V1.3 tuple compatibility;
  - fast prompt caps memory hints at 10;
  - thinking prompt uses only `notebook_memory` and caps at 20;
  - memory judgment and nightly cleanup schemas now target `memory.md`.
- `backend/app/runtime/memory_judgment.py`
  - redirects legacy `target=user.md` model output to `memory.md`.
- `backend/app/runtime/nightly_cleanup.py`
  - reads only canonical `memory.md` for cleanup prompt input;
  - redirects legacy cleanup targets to `memory.md`.
- Backend tests updated for V1.4 single-notebook behavior.

## Verification

Compile check:

```bash
python -m py_compile \
  backend/app/runtime/notebook.py \
  backend/app/pet/prompt_builder.py \
  backend/app/runtime/context_manager.py \
  backend/app/runtime/memory_judgment.py \
  backend/app/runtime/nightly_cleanup.py
```

Focused backend tests:

```bash
pytest \
  backend/tests/test_notebook.py \
  backend/tests/test_fast_reply_contract.py \
  backend/tests/test_thinking_prompt_contract.py \
  backend/tests/test_memory_cards.py \
  backend/tests/test_memory_judgment.py \
  backend/tests/test_nightly_cleanup.py
```

Result:

```text
107 passed
```

## Completion Review

No blocker found.

The main compatibility risk was nightly cleanup: if it continued reading or
writing `user.md`, the product model would silently split again after midnight.
That path now reads only `memory.md`, asks the model to target only `memory.md`,
and still accepts old `user.md` targets by redirecting them before applying
operations.

The migration parser now reads all parseable lines during merge rather than the
normal latest-200 prompt cap, so old notebook content is not truncated during
the one-time conversion.

## Risks Carried Forward

- Physical `user.md` path and config keys remain for compatibility in this
  release.
- Older tests and maintenance code may still mention `user.md` as a legacy
  alias, but prompt and write paths now canonicalize to `memory.md`.
- Stage 5 still needs after-turn memory summarization; Stage 4 only prepares the
  canonical notebook and selection behavior.

## Acceptance Criteria Audit

- Canonical prompt memory reads from `memory.md`: yes.
- Migration preserves and deduplicates old `user.md` and `memory.md` content:
  yes.
- Fast prompt contains up to 10 canonical lines within budget: yes.
- Thinking prompt uses bounded canonical notebook lines: yes.
- `user.md` is not used as prompt source after migration: yes.
- `append_line("user.md", ...)` redirects to `memory.md`: yes.
- Nightly cleanup does not reintroduce split notebook behavior: yes.
- Legacy `MemoryCardManager.rebuild()` protection remains covered: yes.
- Backend focused tests pass: yes.
