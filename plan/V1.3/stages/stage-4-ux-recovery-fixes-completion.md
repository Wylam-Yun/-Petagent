# Stage 4 Completion: UX Recovery Fixes

**Date:** 2026-05-26
**Status:** COMPLETE

## Files Changed

| File | Change |
|---|---|
| `backend/app/api/audio.py` | Added retry endpoint, return failed_runtime_restart jobs, removed 404 for restart-failed |
| `backend/app/runtime/audio_jobs.py` | Added retry() with idempotency cache, error_class field, ProviderError mapping, error_class in failure paths |
| `backend/app/runtime/audio_job_store.py` | No changes (error_class column already existed) |
| `frontend/src/App.tsx` | Removed postPetEvent from tap handler, rewrote handleRetryAudio to use retry endpoint |
| `frontend/src/pet/types.ts` | Added BehaviorStep, PetResponse fields (action, route, memory_ack_hint, behavior_intent, behavior_plan, voice_style), AudioJob error_class + new status values |
| `frontend/src/pet/api.ts` | Added postAudioRetry, disabled POST retries in requestJson |
| `frontend/src/pet/errorMessages.ts` | Added audio error classes (network, timeout, auth_config, infrastructure) |
| `backend/tests/test_audio_retry.py` | New: 18 tests for retry endpoint, error classification, idempotency |
| `backend/tests/test_stage4_ux.py` | New: 2 tests for backward compat and retry endpoint |
| `backend/tests/test_audio_job_store.py` | Updated: restart-failed test now expects 200 with error_class |

## Behavior Changed

1. **Sprite tap is local-only**: `handleDoudouTap()` no longer calls `postPetEvent("pet_head")`. Tap remains local (animation + bubble, no backend call).
2. **Audio retry endpoint**: `POST /api/audio/jobs/{id}/retry` creates a new job from terminal failed/expired jobs. Idempotent within 5s window.
3. **Error classification**: Audio jobs now have `error_class` field: network, timeout, auth_config, infrastructure, unknown. Mapped from ProviderError hierarchy.
4. **failed_runtime_restart visible**: `GET /api/audio/jobs/{id}` returns restart-failed jobs instead of 404. Error_class=infrastructure for restart/shutdown failures.
5. **POST retries disabled**: `requestJson` in frontend no longer retries POST/PUT/DELETE requests (prevents duplicate LLM/TTS work).
6. **Frontend types complete**: PetResponse includes action, route, memory_ack_hint, behavior_intent, behavior_plan, voice_style. AudioJob includes error_class and new terminal statuses.

## Tests Run

- 634 passed, 24 skipped, 0 failed (full backend test suite)
- 20 new tests across `test_audio_retry.py` and `test_stage4_ux.py`

## Pre-Review Issues Addressed

All 15 issues resolved:
- Issue 1: POST retry idempotency (5s dedup window + POST retries disabled)
- Issue 2: TouchArea deferred (explicitly noted as out of scope)
- Issue 3: playback error_class removed (backend-only classification)
- Issue 4: ProviderError mapping specified
- Issue 5: infrastructure error_class for restart/shutdown failures
- Issue 6: handleRetryAudio in Files Changed table
- Issue 7: Use existing errorMessages.ts (no duplicate)
- Issue 8: Frontend tests noted as manual Nubia check
- Issue 9: Test files consolidated
- Issue 10: pending status instead of running
- Issue 11: tts_empty maps to auth_config
- Issue 12: POST retries disabled + idempotency
- Issue 13: session_id preserved from old job
- Issue 14: failed_runtime_restart now visible
- Issue 15: voice_style on PetResponse type
