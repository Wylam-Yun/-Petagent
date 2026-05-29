# V1.4 Stage 4: Single Notebook Migration And Selection

**Date:** 2026-05-29
**Project:** `/Users/wylam/Documents/workspace/Petagent`

## Goal

Move prompt-facing memory to one canonical notebook:

```text
backend/data/memory_cards/memory.md
```

`user.md` remains as compatibility input for migration, but fast/thinking prompt
selection should read canonical `memory.md` only after migration.

## Scope

In scope:

- merge existing `user.md` and `memory.md` into canonical `memory.md`;
- backup old files before migration rewrite;
- leave `user.md` as a compatibility stub after successful merge;
- fast mode selects up to 10 short lines from canonical memory;
- thinking mode selects up to 20 lines from canonical memory;
- redirect future `append_line("user.md", ...)` writes to canonical memory;
- keep legacy `MemoryCardManager.rebuild()` protection intact;
- update prompt builder tests and notebook tests.

Out of scope:

- MiMo after-turn summarization;
- strict 10-line disk cap;
- deleting old memory card code;
- changing nightly cleanup provider.

## Selection Policy

Fast prompt selection:

- up to 10 lines;
- budget 800 CJK characters;
- category targets:
  - up to 2 `identity`;
  - up to 3 `preference`;
  - up to 3 `relationship`/`project`;
  - up to 2 `temporary`;
- priority within category is newest first.

Thinking selection:

- up to 20 lines;
- budget 1600 CJK characters;
- same category priority, less strict per-category cap.

Return shape:

```python
select_for_fast_reply() -> list[str]
select_for_thinking() -> list[str]
```

`ContextManager` still stores this in `selected_card_items` for compatibility,
but the value becomes a single list instead of `(user_items, memory_items)`.

## Migration Policy

On startup migration:

1. Parse both existing files.
2. If canonical `memory.md` already contains V1.4 marker, skip.
3. Merge parseable entries from both files.
4. Deduplicate normalized content.
5. Sort by original file order with `user.md` entries first, then existing
   `memory.md` entries.
6. Backup both files.
7. Rewrite `memory.md` with `<!-- v1.4_single_notebook -->`.
8. Rewrite `user.md` as a compatibility stub pointing to `memory.md`.

If there are no parseable entries, fall back to existing V1.3 migration/import
logic.

## Acceptance Criteria

- `memory.md` becomes canonical for prompt selection.
- Fast prompt loads up to 10 memory lines from canonical memory.
- Thinking prompt loads up to 20 memory lines from canonical memory.
- Existing split notebook data is preserved and deduplicated.
- `user.md` is not used as a prompt source after migration.
- Appending to `user.md` redirects to canonical memory.
- Legacy card rebuild cannot overwrite canonical notebook.
- Backend tests pass for notebook, prompt contract, memory judgment, and memory
  card protection.
