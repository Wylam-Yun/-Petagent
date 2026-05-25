# Stage 1 Completion: Fast Reply Contract

**Date:** 2026-05-26
**Status:** COMPLETE

## Files Changed

| File | Change |
|---|---|
| `backend/app/runtime/route_policy.py` | Route values: "fast"→"fast_reply", "slow"→"thinking". Tool/long-task keywords → fast_reply with no tools. |
| `backend/app/runtime/context_manager.py` | Added `fast_reply` (1 turn, card-only) and `thinking` (6 turns, card-only) profiles. Disabled temporal_recall for V1.3 profiles. |
| `backend/app/pet/prompt_builder.py` | Added `build_fast_reply_messages()` with minimal payload. Updated profile matching for fast_reply/thinking. |
| `backend/app/runtime/actions.py` | Added `FastReplyAction` model. Added `action` and `route` fields to `PetResponse`. |
| `backend/app/pet/guard.py` | Added `guard_fast_reply_action()` with 80-char trim, whitelist validation, fallback. |
| `backend/app/pet/brain.py` | Added `generate_fast_reply_action()` method. |
| `backend/app/runtime/dispatcher.py` | Fast reply branch: uses fast reply brain/guard, skips state_delta/effort/memory, still persists mood+timestamp. |
| `backend/app/runtime/text_pipeline.py` | Source strings updated to "text_fast_reply"/"text_thinking". |
| `backend/app/runtime/voice_pipeline.py` | Route names updated. Fast ASR failure returns local recovery (no slow fallback). |
| `backend/app/runtime/voice_types.py` | Added `asr_failed_hint` field to `VoiceRouteInfo`. |
| `backend/tests/test_route_policy.py` | Rewritten for new route/profile names. |
| `backend/tests/test_text_chat.py` | Updated assertions for fast_reply/thinking routes. |
| `backend/tests/test_voice_pipeline.py` | Rewritten: fast ASR failure → local recovery, thinking ASR failure → slow fallback. |
| `backend/tests/test_fast_reply_contract.py` | New: 9 tests for guard, response shape, prompt payload. |
| `backend/tests/test_agent_run.py` | Updated profile name assertions. |
| `backend/tests/test_memory_cards.py` | Updated profile names, rewrote thinking mode test for card-only. |
| `backend/tests/test_interaction_catalog.py` | Updated profile name. |
| `backend/tests/test_phase2_agent_run.py` | Updated profile/route names. |
| `backend/tests/test_dispatcher_pet_effort.py` | Added thinking_mode=True to exercise full PetAction path. |
| `backend/tests/test_e6_metrics.py` | Updated route name assertion. |
| `backend/tests/test_skill_execution.py` | Rewritten: V1.3 fast reply does not execute skills. |
| `backend/tests/test_stage3_runtime_integration.py` | Updated: memory_update/skills only in thinking mode. |

## Behavior Changed

1. **Default text/voice route** → `fast_reply` (was `fast`). Tool/long-task keywords no longer switch to slow/tools.
2. **Thinking mode** → `thinking` route with `allow_tools=False` (was `slow` with tools enabled).
3. **Fast reply prompt** → minimal payload (1 turn, 4 pet_state fields, memory_hints placeholder, no retrieval fields).
4. **Fast reply response** → includes `action` and `route` fields, no `state_affect`/`behavior_intent`/`behavior_plan`.
5. **Fast voice ASR failure** → returns local recovery with `asr_failed_hint="没听清"` (was: falls back to audio_understanding).
6. **Context profiles** → `fast_reply` and `thinking` use card-only memory, no scored memories/quotes/digest/summaries.

## Tests Run

- 558 passed, 24 skipped, 0 failed (full backend test suite)
- 9 new tests in `test_fast_reply_contract.py`
- Frontend TypeScript: `npx tsc --noEmit` — clean

## Skipped Checks

- Nubia live smoke test (device not connected during implementation)

## Remaining Risks

- `build_fast_reply_messages` uses empty `memory_hints` placeholder — Stage 2 wires real card selection
- Frontend does not yet use `PetResponse.action` or `PetResponse.route` — Stage 5 wires behavior execution
- `build_thinking_messages()` deferred — thinking route uses existing `build_pet_messages()` with updated profile

## Completion Review

Result: PASS (subagent review confirmed all 15 pre-review issues addressed, implementation matches plan and spec)
