# Stage 4 Main-Agent Plan Review

**Date:** 2026-05-29

## Review Scope

Reviewed:

- `plan/V1.4/doudou-living-pet-and-memory-v1-spec.md`
- `plan/V1.4/stages/stage-4-single-notebook.md`
- `backend/app/runtime/notebook.py`
- `backend/app/runtime/context_manager.py`
- `backend/app/pet/prompt_builder.py`
- `backend/app/runtime/memory_judgment.py`
- `backend/app/runtime/memory_cards.py`
- related tests.

## Findings

No blocker found.

The current code still uses a V1.3 split model: fast reply selects one
`user.md` item and one `memory.md` item, thinking selects two arrays, and memory
judgment may ask to write `user.md`. Stage 4 needs to replace that prompt-facing
split without deleting compatibility code used by older tests and maintenance
paths.

`MemoryCardManager.rebuild()` already protects canonical `memory_cards/user.md`
and `memory.md`, so the "legacy rebuild cannot overwrite canonical notebook"
requirement is already mostly satisfied. Stage 4 should preserve and test that
behavior rather than refactor it.

The riskiest change is return-shape compatibility for `selected_card_items`.
The plan mitigates this by updating prompt builders to accept both old tuple
shape and new single-list shape during the transition.

## Decision

Proceed with Stage 4 implementation. Keep `user.md` physically present as a
stub for one release; do not delete it.
