# Stage 4: UX Recovery Fixes

**Date:** 2026-05-26
**Goal:** Fix UX issues from V1.2 review: remove sprite tap slow path, add audio retry endpoint, add audio error classification, complete frontend response types, disable POST retries.

## Scope

Backend API changes + frontend type changes. No LLM prompt changes.

**Deferred:** TouchArea local conversion (praise/feed/hug buttons). The spec mentions "Convert More/TouchArea interactions to local deterministic behavior" but this requires a larger frontend refactor (mapping each interaction to a local animation + bubble). Tracked separately; not blocking V1.3.

### 1. Remove Sprite Tap Slow Path

**Issue:** `handleDoudouTap()` in frontend calls `postPetEvent("pet_head")` which goes through full LLM/TTS pipeline.

**Fix:** Remove the `postPetEvent("pet_head")` call from sprite tap handler. Ordinary taps remain local-only (no backend sync). State/log sync via a lightweight endpoint is deferred — not needed for V1.3.

**File:** `frontend/src/App.tsx`
- Remove `postPetEvent("pet_head")` call after `director.onTap()`
- Tap remains purely local: sprite animation + bubble, no backend call

**Test:** `backend/tests/test_stage4_ux.py` (new)
- `test_pet_head_event_still_works`: /api/pet/event still accepts pet_head (backward compat)
- Note: "sprite tap doesn't call API" is a frontend behavior — verify manually on Nubia (Stage 6)

### 2. Audio Retry Endpoint

**File:** `backend/app/api/audio.py` (modify)

Add `POST /api/audio/jobs/{job_id}/retry`:
- Only retry terminal failed/expired jobs
- Create new job with same text, voice_style, and session_id from old job (empty run_id/event_id — retry is not tied to a specific run)
- Return new job_id
- Old job remains in terminal state
- Idempotent: if the same old job_id is retried twice within 5 seconds, return the same new job_id (prevent duplicate TTS from requestJson retries — see Section 6)

**File:** `backend/app/runtime/audio_jobs.py` (verify/modify)

Ensure `AudioJobManager` has a `retry(job_id)` method:
- Look up old job by id
- Verify status is terminal (failed/expired)
- Create new job with old job's text, voice_style, and session_id
- Return new job_id

**File:** `backend/tests/test_audio_retry.py` (new)
- `test_retry_failed_job`: failed job → new job id returned
- `test_retry_expired_job`: expired job → new job id returned
- `test_retry_pending_job_rejected`: pending job → 400
- `test_retry_completed_job_rejected`: completed job → 400
- `test_retry_uses_old_text_and_style`: new job has same text/voice_style/session_id
- `test_retry_idempotent`: same old job_id retried within 5s returns same new job_id

### 3. Audio Error Classification

**File:** `backend/app/runtime/audio_jobs.py` (modify)

Add `error_class` field to audio job responses. Map from existing `ProviderError` hierarchy:

| ProviderError subclass | audio error_class |
|---|---|
| `ProviderNetworkError` | `network` |
| `ProviderTimeoutError` | `timeout` |
| `ProviderAuthError` | `auth_config` |
| `ProviderQuotaError` | `auth_config` |
| TTS returned empty voice_url | `auth_config` |
| Job exceeded TTL (expired) | `timeout` |
| `mark_restart_failed` / `mark_shutdown_failed` | `infrastructure` |
| Anything else | `unknown` |

Set `error_class` in:
- `_run_job()` catch block: map from ProviderError subclass
- `_run_job()` tts-returned-empty branch: set `auth_config`
- `mark_restart_failed()`: set `infrastructure`
- `mark_shutdown_failed()`: set `infrastructure`

**File:** `backend/app/api/audio.py` (modify)

- Include `error_class` in job status response JSON
- Change `get_audio_job`: return `failed_runtime_restart` jobs (with error_class) instead of 404. The frontend needs to see these jobs to display the error and allow retry.

**File:** `frontend/src/pet/errorMessages.ts` (modify)

Add audio error classes to existing `ERROR_BUBBLE_MAP`:
```typescript
network: "网络刚刚没连上，豆豆发不出声音。",
timeout: "声音生成太慢了，等一下再试。",
auth_config: "发声服务配置可能有问题。",
infrastructure: "系统刚刚重启了，声音没发出来。",
unknown: "声音刚刚没出来。",
```

Do NOT create a separate `AUDIO_ERROR_COPY` map in types.ts — use the existing error copy system.

**File:** `backend/tests/test_audio_retry.py` (update)
- `test_failed_job_has_error_class`: verify error_class in response
- `test_infrastructure_error_class`: mark_restart_failed sets error_class=infrastructure

### 4. Frontend Response Types

**File:** `frontend/src/types.ts` (modify)

Ensure `PetResponse` type includes:
- `action?: string` (fast reply action)
- `route?: string` (fast_reply / thinking)
- `memory_ack_hint?: string`
- `behavior_intent?: string`
- `behavior_plan?: BehaviorStep[]`
- `voice_style?: string`

Ensure `AudioJob` type includes:
- `error_class?: string`
- Update status union: add `"failed_runtime_restart" | "failed_shutdown"` to existing `"pending" | "ready" | "failed" | "expired" | "superseded"`

**File:** `frontend/src/pet/api.ts` (verify)

Ensure API response parsing handles new fields without unsafe casts.

### 5. Frontend Audio Retry

**File:** `frontend/src/App.tsx` (modify)

Rewrite `handleRetryAudio()`:
- Call `postAudioRetry(lastAudioJobId)` (new API function)
- Store returned new job_id
- Poll new job_id instead of old one

**File:** `frontend/src/pet/api.ts` (modify)

Add `postAudioRetry(jobId: string)` function that calls `POST /api/audio/jobs/{jobId}/retry`.

### 6. Disable POST Retries

**Issue:** `requestJson` in `frontend/src/pet/api.ts` retries ALL requests (including POSTs) up to 2 times. This can duplicate LLM/TTS work on timeout.

**File:** `frontend/src/pet/api.ts` (modify)

In `requestJson`: skip retries for POST/PUT/DELETE methods. Only retry GET requests (which are idempotent by nature).

```typescript
// Only retry idempotent methods
if (method === "GET" && attempt < maxRetries) {
  // existing retry logic
}
```

This is the simplest fix. No idempotency keys needed.

### 7. Test Updates

**File:** `backend/tests/test_stage4_ux.py` (new)

- `test_pet_head_event_still_works`: /api/pet/event still accepts pet_head
- `test_audio_retry_endpoint_exists`: POST /api/audio/jobs/{id}/retry returns 200/404/400

**File:** `backend/tests/test_audio_retry.py` (new — consolidates all audio retry/error tests)

- `test_retry_failed_job`: failed → new job id
- `test_retry_expired_job`: expired → new job id
- `test_retry_pending_job_rejected`: pending → 400
- `test_retry_completed_job_rejected`: completed → 400
- `test_retry_uses_old_text_and_style`: same text/voice_style/session_id
- `test_retry_idempotent`: duplicate retry within 5s returns same new job_id
- `test_failed_job_has_error_class`: failed job response includes error_class
- `test_infrastructure_error_class`: restart/shutdown failure sets error_class=infrastructure
- `test_expired_job_error_class_is_timeout`: expired job error_class=timeout
- `test_tts_empty_error_class_is_auth_config`: empty TTS return sets error_class=auth_config
- `test_failed_runtime_restart_visible`: get_audio_job returns failed_runtime_restart with error_class

## Files Changed

| File | Change Type |
|---|---|
| `frontend/src/App.tsx` | Modify (remove postPetEvent from tap handler, rewrite handleRetryAudio) |
| `frontend/src/types.ts` | Modify (add PetResponse/AudioJob fields) |
| `frontend/src/pet/api.ts` | Modify (add postAudioRetry, disable POST retries) |
| `frontend/src/pet/errorMessages.ts` | Modify (add audio error class copy) |
| `backend/app/api/audio.py` | Modify (add retry endpoint, error_class in response, return failed_runtime_restart) |
| `backend/app/runtime/audio_jobs.py` | Modify (add retry method, error_class field, ProviderError mapping) |
| `backend/tests/test_stage4_ux.py` | New (backward compat + endpoint exists) |
| `backend/tests/test_audio_retry.py` | New (all audio retry + error class tests) |

## Nubia Constraints

- Audio retry creates a new job (no mutation of terminal jobs)
- Error classification is backend-side (frontend just displays copy)
- Sprite tap removal is purely frontend (no backend change needed)
- Retry endpoint is lightweight (no LLM call, just TTS re-enqueue)
- POST retries disabled to prevent duplicate LLM/TTS work
- Retry idempotency via 5s dedup window (prevents requestJson double-fire)
- failed_runtime_restart jobs now visible (with error_class) so retry is reachable

## Acceptance Checks

1. Sprite tap does not call /api/pet/event (manual Nubia check)
2. POST /api/audio/jobs/{id}/retry returns new job id for failed/expired jobs
3. Audio job responses include error_class (network/timeout/auth_config/infrastructure/unknown)
4. Frontend PetResponse type includes action, route, memory_ack_hint, behavior_intent, behavior_plan, voice_style
5. Frontend AudioJob type includes error_class
6. POST requests in frontend are not retried by requestJson
7. Duplicate retry calls within 5s return same new job_id
8. failed_runtime_restart jobs are visible via get_audio_job
9. Full test suite passes
