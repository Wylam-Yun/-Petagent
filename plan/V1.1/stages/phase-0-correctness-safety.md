# Phase 0: Correctness + Safety Gates

> Stage plan for V1.1 Phase 0. Covers STAB-002, 003, 004, 019-skeleton, 027, 029, 032-min.

**Date:** 2026-05-21
**Scope:** Low-risk, high-value correctness fixes. All changes are local and well-bounded.
**Estimated effort:** 1-2 days

---

## STAB Items Covered

| STAB | Description | Risk |
|------|-------------|------|
| 002 | MiMo audio understanding uses wrong API key | Low - single file change |
| 003 | Route policy says slow but brain stays fast | Medium - touches pipeline/dispatcher |
| 004 | Thinking voice path still starts with ASR | Medium - voice pipeline change |
| 019 | Provider error skeleton (minimal Phase 0 scope) | Low - new module + wiring |
| 027 | GET /api/pet/state has tick side effects | Low - API route change |
| 029 | Pet effort double-deducts energy | Low - dispatcher logic fix |
| 032 | Minimal CORS/internal auth safety gate (CC-0) | Medium - new auth module + CORS change |

---

## Implementation Order

### Task 1: STAB-002 — Fix MiMo audio understanding API key

**Problem:** `MiMoAudioUnderstandingProvider.understand()` uses `self.settings.api_key` (global fallback = TTS or LLM key) instead of `self.settings.audio_understanding.api_key` (MIMO_API_KEY). Also hardcodes `"api-key"` header instead of using the configurable auth scheme pattern from `MiMoLLMProvider._headers()`.

**Fix:**
1. In `backend/app/providers/audio_omni.py`, `MiMoAudioUnderstandingProvider.__init__`:
   - Store `self.provider_config = settings.audio_understanding`
   - Compute `api_key = self.provider_config.api_key or self.settings.api_key`
2. In `understand()`:
   - Use `api_key` (from init) instead of `self.settings.api_key`
   - Use configurable auth scheme from `self.provider_config.extra.get("auth_scheme", "api-key")` matching the pattern in `llm_mimo.py`
   - Update header accordingly: bearer → `Authorization: Bearer ...`, custom → `api-key: ...`, default → `api-key: ...`

**Files:** `backend/app/providers/audio_omni.py`

**Tests:**
- Unit test: mock `settings` with `MIMO_API_KEY != SILICONFLOW_API_KEY`, verify the request header carries the MiMo key.
- Unit test: verify `auth_scheme=bearer` produces `Authorization: Bearer ...` header.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "audio"`

---

### Task 2: STAB-003 — Route policy brain selection truthfulness

**Problem:** `TextPipeline.handle()` selects brain purely from `thinking_mode` (binary), ignoring `RouteDecision` from `decide_route()`. The dispatcher applies `decide_route()` internally for tools/context, but the actual brain used for LLM generation may not match `decision.provider_profile`. A complex keyword text with `thinking_mode=False` gets `route=slow` from policy but `fast_brain` from pipeline.

**Fix:**
1. Add a `brain` field to `RouteDecision` in `route_policy.py` — value is `"slow"` when `route == "slow"`, else `"fast"`.
2. In `TextPipeline.handle()`, call `decide_route()` first to get the decision, then select brain from `decision.brain` instead of `thinking_mode`.
3. Expose `decision.route` and `decision.reason` in `TextRouteInfo` so the API response reflects the actual route taken.
4. Update `TextRouteInfo.selected` to come from `decision.route` instead of the `thinking_mode` binary.

**Files:**
- `backend/app/runtime/route_policy.py` — add `brain` field to `RouteDecision`
- `backend/app/runtime/text_pipeline.py` — use `decide_route()` for brain selection
- `backend/app/runtime/voice_types.py` — no change needed (voice uses its own route info)

**Tests:**
- Test: complex keyword text with `thinking_mode=False` → brain should be `slow_brain`, `selected="slow"`.
- Test: simple text with `thinking_mode=False` → brain should be `fast_brain`, `selected="fast"`.
- Test: simple text with `thinking_mode=True` → brain should be `slow_brain`, `selected="slow"`.
- Update existing `test_text_chat.py` tests if assertions change.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/test_text_chat.py -q`

---

### Task 3: STAB-004 — Thinking voice path uses audio understanding first

**Problem:** When `thinking_mode=True` or `requested_route="slow"`, `VoicePipeline.handle()` runs `_run_asr_route()` with `slow_brain`. ASR runs first; if it succeeds, emotion is set to `"uncertain"` and tone notes say `"fast ASR route only"`. The audio understanding provider (which can detect tone, emotion, non-verbal cues) is only used as a fallback when ASR fails.

**Fix:**
1. In `VoicePipeline.handle()`, when `thinking_mode=True` or `requested == "slow"`:
   - Call `_run_audio_understanding_route()` first (new method).
   - This runs `self.audio_provider.understand()` to get full `AudioUnderstanding` (user_text, emotion, tone_notes, non_verbal, confidence).
   - If audio understanding returns usable text (non-empty `user_text` with confidence >= threshold), use it directly.
   - Optionally run ASR afterward as `transcript_assist` for text enrichment, but do not gate on ASR success.
   - If audio understanding fails or returns empty, fall back to ASR route as today.
2. Add `emotion_source` field to `VoiceRouteInfo`: `"audio_understanding"`, `"asr"`, or `"fallback"`.
3. For `thinking_mode=False` / `requested == "fast"`: keep existing ASR-first path unchanged.

**Files:**
- `backend/app/runtime/voice_pipeline.py` — add `_run_audio_understanding_route()`, modify `handle()` branching
- `backend/app/runtime/voice_types.py` — add `emotion_source` field to `VoiceRouteInfo`

**Tests:**
- Test: thinking voice request invokes audio understanding provider before ASR provider.
- Test: when audio understanding returns valid text, ASR is not called.
- Test: when audio understanding fails, falls back to ASR route.
- Test: `emotion_source` field is correctly set in route_info.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "voice"`

---

### Task 4: STAB-019 — Provider error skeleton (CC-1 minimal)

**Problem:** Provider exceptions collapse into `None` or silent fallback. No structured error types exist. API routes have no try/except around pipeline calls — all provider failures become unstructured 500s.

**Fix (minimal Phase 0 scope):**
1. Create `backend/app/providers/errors.py` with error class hierarchy:
   - `ProviderError(Exception)` base with `provider`, `code`, `status`, `latency_ms`, `message`
   - `ProviderAuthError` (401/403)
   - `ProviderTimeoutError` (connect/read timeout)
   - `ProviderUnavailableError` (5xx)
   - `ProviderQuotaError` (429)
   - `ProviderBadResponseError` (JSON/schema invalid)
   - `ProviderNetworkError` (DNS/connection refused)
   - Each has stable `error_class` string label.
2. In `backend/app/api/text.py` and `backend/app/api/voice.py`:
   - Wrap `run_in_threadpool(...)` in try/except for `ProviderError`.
   - On `ProviderError`, return structured 500 response with `error_class` field instead of raw 500.
   - Log the provider error with sanitized details (no secrets).
3. Add `error_class` field to text and voice API response bodies (always present, `null` on success).

**Files:**
- `backend/app/providers/errors.py` (new)
- `backend/app/api/text.py`
- `backend/app/api/voice.py`

**Tests:**
- Test: mock provider that raises `ProviderAuthError` → API returns structured response with `error_class: "provider_auth_failed"`.
- Test: mock provider that raises `ProviderTimeoutError` → API returns with `error_class: "provider_timeout"`.
- Test: successful request has `error_class: null`.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "text or voice"`

---

### Task 5: STAB-032 — Minimal CORS/internal auth safety gate (CC-0)

**Problem:** CORS is `allow_origins=["*"]` with all methods/headers allowed. No auth middleware exists. Debug/internal endpoints will be added in later phases — they need protection before landing.

**Fix:**
1. Create `backend/app/api/auth.py` with:
   - `get_internal_token(settings)` function that reads `DEBUG_INTERNAL_TOKEN` env var, or generates and persists a token to `backend/data/secrets/internal_token` with `0600` permissions.
   - `require_internal_token(request)` dependency that validates `Authorization: Bearer <token>` header. Returns 403 if missing/invalid.
   - `is_loopback(request)` helper that checks if request comes from `127.0.0.1` or `::1`.
2. In `backend/app/main.py`:
   - Replace `allow_origins=["*"]` with explicit origin allowlist from config:
     - `http://127.0.0.1:8000`, `http://localhost:8000` (local frontend)
     - Configurable LAN origin from `settings.app_config.get("cors", {}).get("allowed_origins", [])`
     - Default to loopback only if no config.
   - Keep `allow_credentials=True` only with explicit origins (browser spec rejects wildcard + credentials).
   - Store `internal_token` on `app.state` for use by protected endpoints.
3. Protected endpoint inventory (for future phases — add the dependency but don't create endpoints yet):
   - `/api/debug/*`, `/api/internal/*`, `/api/context/debug`, `/api/context/runs`
   - `/api/memory/debug`, `/api/memory/curate`, `/api/memory/summarize`
   - `/api/runtime/reset`, `/api/skills/{skill_id}/run`
4. Public endpoints stay token-free: `/`, static, `/api/health`, text/voice chat, pet state/event, audio polling, client config.

**Files:**
- `backend/app/api/auth.py` (new)
- `backend/app/main.py`

**Tests:**
- Test: request from allowed origin succeeds.
- Test: request from unlisted origin is rejected by CORS.
- Test: `/api/debug/*` without token returns 403 (once debug endpoints exist; for now, test the dependency function directly).
- Test: internal token is generated and persisted when `DEBUG_INTERNAL_TOKEN` is not set.
- Test: internal token from env var is used when set.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q`

---

### Task 6: STAB-027 — Remove tick side effects from GET /api/pet/state

**Problem:** `GET /api/pet/state` calls `tick_service.apply_if_due()` every time. Reading state mutates it. Opening the page after idle time pushes Momo to extreme tired/lonely states.

**Fix:**
1. Remove `tick_service.apply_if_due()` from `get_pet_state()` in `backend/app/api/pet.py`.
2. Add `POST /api/pet/session/resume` endpoint that explicitly calls `tick_service.apply_if_due()` and returns the new state. This is the "I'm back" signal.
3. Keep `apply_if_due()` in `POST /api/pet/event` and `POST /api/pet/proactive/trigger` (these are interaction events, not reads).
4. Frontend change: call `POST /api/pet/session/resume` once on app load and on `online` event, not on every poll. (Frontend changes deferred to Phase 3; backend endpoint lands now.)

**Files:**
- `backend/app/api/pet.py`

**Tests:**
- Test: `GET /api/pet/state` does not call `apply_if_due` (mock tick_service, verify not called).
- Test: `POST /api/pet/session/resume` calls `apply_if_due` and returns state.
- Test: `POST /api/pet/event` still calls `apply_if_due`.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "pet or state"`

---

### Task 7: STAB-029 — Fix pet effort energy double-deduction

**Problem:** In `dispatcher._handle_event_inner()` lines 263-277:
1. `apply_state_delta(ruled_state, action.state_delta)` applies the LLM's state_delta (which may include negative energy).
2. Then pet_effort fatigue deducts additional energy on top.
If the LLM's `state_delta.energy` is negative AND pet_effort is medium/high, both reductions stack.

**Fix:**
1. Strip `energy` from `action.state_delta` before applying it. The dispatcher is the sole authority for energy changes via pet_effort.
2. Log a warning if the LLM returned `energy` in `state_delta` (for observability).
3. Keep the existing effort logic: `medium` → -2, `high` → -5 + sleepiness +1.
4. The `min()` guard remains as a safety net.

**Files:**
- `backend/app/runtime/dispatcher.py`

**Tests:**
- Test: mocked LLM returning `state_delta={energy: -10}` with medium effort → energy should decrease by only 2 (effort), not 12.
- Test: mocked LLM returning `state_delta={intimacy: 5}` with high effort → intimacy increases by 5, energy decreases by 5.
- Test: `state_delta` with no energy key + low effort → no energy change from effort.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "dispatcher or energy"`

---

## Verification Plan

### Local verification (after all tasks):
```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest -q
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- --run
npm run build
```

### Nubia field check:
```bash
ssh nubia 'curl -s http://127.0.0.1:8000/api/health'
# Smoke test voice with thinking on/off
# Verify MiMo audio understanding works with correct key
# Confirm debug/internal endpoints reject missing token
```

---

## Rollback Notes

- STAB-002: Revert `audio_omni.py` single file change.
- STAB-003: Keep old `thinking_mode` selector behind config flag if needed.
- STAB-004: Per-route flag to disable audio-understanding-first path.
- STAB-019: Remove `errors.py` and revert API route changes.
- STAB-027: Re-add `apply_if_due()` to `get_pet_state()`.
- STAB-029: Revert energy stripping in dispatcher.
- STAB-032: Revert CORS to wildcard (not recommended).

---

## Commit Boundary

One commit for the entire Phase 0, with message:
```
fix(V1.1-Phase0): correctness + safety gates

- STAB-002: use audio_understanding.api_key for MiMo audio provider
- STAB-003: route policy brain selection truthfulness
- STAB-004: thinking voice uses audio understanding first
- STAB-019: provider error class skeleton (CC-1)
- STAB-027: remove tick side effects from GET /api/pet/state
- STAB-029: fix pet effort energy double-deduction
- STAB-032: minimal CORS allowlist + internal token gate (CC-0)
```
