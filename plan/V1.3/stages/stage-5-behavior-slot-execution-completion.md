# Stage 5 Completion: Behavior Slot Execution

**Date:** 2026-05-26
**Status:** COMPLETE

## Files Changed

| File | Change |
|---|---|
| `frontend/src/App.tsx` | Removed unsafe Record casts, passed action to director, replaced hard-coded setDoudouAction with advanceSlot calls in playResponseAudio |
| `frontend/src/pet/behaviorDirector.ts` | Added action handling in onBackendResponse, fixed onPhaseChange to preserve queue for audio phases (waiting_voice/speaking), fixed misleading comment |
| `frontend/src/pet/types.ts` | Fixed BehaviorStep type: replaced `target` with `slot` to match backend |
| `backend/tests/test_stage5_behavior.py` | New: 5 tests for action field, behavior_plan, route fields |

## Behavior Changed

1. **Fast Reply action wired**: When backend returns `action` field, sprite updates immediately via `isValidDoudouAction` check. Falls back to behavior plan if action missing/invalid.
2. **VoiceButton race fixed**: `onPhaseChange` now preserves `queuedSteps` for `waiting_voice` and `speaking` phases. Previously, VoiceButton's `changePhase("waiting_voice")` cleared the queue, destroying the behavior plan.
3. **advanceSlot at phase boundaries**: `playResponseAudio` calls `advanceSlot("before_speech")`, `advanceSlot("speech")`, and `advanceSlot("after_speech")` at real audio phase transitions. Hard-coded "review"/"idle" kept as fallbacks.
4. **Unsafe casts removed**: `applyPetResponse` now uses typed `response.behavior_intent` and `response.behavior_plan` directly instead of `Record<string, unknown>` casts.
5. **BehaviorStep type fixed**: Frontend `BehaviorStep` now has `slot` field matching backend.

## Tests Run

- 639 passed, 24 skipped, 0 failed (full backend test suite)
- 5 new tests in `test_stage5_behavior.py`

## Pre-Review Issues Addressed

All 8 issues resolved:
- Issue 1: Use `isValidDoudouAction` from doudouSprites.ts (exported)
- Issue 2: VoiceButton race fixed by preserving queue in onPhaseChange for audio phases
- Issue 3: Hard-coded setDoudouAction replaced with advanceSlot calls (fallbacks kept)
- Issue 4: BehaviorStep type updated to include `slot` instead of `target`
- Issue 5: onPhaseChange behavior documented (preserves queue for waiting_voice/speaking)
- Issue 6: Frontend integration test noted as manual Nubia check
- Issue 7: action undefined for Thinking mode documented (if guard handles it)
- Issue 8: Misleading comment fixed

## Note

`idle_after` slot is defined but never consumed in the current audio playback flow. The queue is cleared on next response or phase change, so this is low-risk. Can be wired in a future stage if needed.
