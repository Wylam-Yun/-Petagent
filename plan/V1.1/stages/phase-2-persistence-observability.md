# Phase 2: Persistence + Provider Observability — Stage Plan

**Date:** 2026-05-22
**Depends on:** Phase 0 (provider errors, auth, CORS), Phase 1 (lifespan, health, concurrency)
**Target:** Nubia NX531J, Android 6.0.1, Termux, ~200MB RAM, no swap

## Scope

STAB-011, 012, 017, 019-full, 020, 021, 022, 023, 024, 025, 037.
See master plan at `plan/V1.1/fix-spec-plan.md` lines 835–1051.

## Tasks (authoritative order)

1. **STAB-019/CC-1-full**: Expand provider error classes across all providers
2. **STAB-012**: Provider timeout tuples (connect, read)
3. **STAB-011**: Provider circuit breaker
4. **STAB-020**: Startup provider key probes
5. **STAB-021**: Structured error class in API responses
6. **STAB-024/CC-7**: AgentRunStore persistence (bounded 200 rows)
7. **STAB-025**: Memory candidate retry with backoff
8. **STAB-022**: WAL periodic checkpoint
9. **STAB-023**: Rolling DB backup
10. **STAB-037/CC-8**: Incident breadcrumb table
11. **STAB-017**: Wake fallback from audio understanding fields

## Key Files

### New files
- `backend/app/providers/errors.py` (expand from Phase 0 skeleton)
- `backend/app/providers/circuit.py` (new)
- `backend/app/providers/probes.py` (new)
- `backend/app/runtime/backup.py` (new)
- `backend/app/runtime/incident.py` (new)
- `backend/app/api/debug.py` (new — runs, incidents endpoints behind debug token)
- `backend/app/runtime/wake_detector.py` (new — STAB-017)

### Modified files
- `backend/app/providers/llm_mimo.py` (timeout tuples, structured errors)
- `backend/app/providers/tts_mimo.py` (timeout tuples, structured errors)
- `backend/app/providers/asr_http.py` (timeout tuples, structured errors)
- `backend/app/providers/audio_omni.py` (timeout tuples, structured errors)
- `backend/app/providers/asr_nvidia.py` (timeout tuples, structured errors)
- `backend/app/runtime/dispatcher.py` (catch ProviderError at boundary)
- `backend/app/runtime/route_policy.py` (RouteInfo with provider_failure)
- `backend/app/runtime/audio_jobs.py` (error_class on TTS failure)
- `backend/app/runtime/agent_run.py` (persistence)
- `backend/app/runtime/memory_curator.py` (retry logic)
- `backend/app/runtime/memory_store.py` (retry columns)
- `backend/app/runtime/maintenance.py` (WAL checkpoint, backup)
- `backend/app/runtime/voice_pipeline.py` (wake fallback)
- `backend/app/main.py` (probes, incident wiring)
- `backend/app/api/health.py` (deep health: provider status, backup time)

### Test files
- `backend/tests/test_phase2_providers.py` (provider errors, timeouts, circuit)
- `backend/tests/test_phase2_probes.py` (startup probes)
- `backend/tests/test_phase2_agent_run.py` (persistence)
- `backend/tests/test_phase2_memory_retry.py` (candidate retry)
- `backend/tests/test_phase2_wal_backup.py` (checkpoint, backup)
- `backend/tests/test_phase2_incident.py` (breadcrumb table)
- `backend/tests/test_phase2_wake.py` (wake fallback)

## Task Details

### Task 1: STAB-019/CC-1-full — Expand provider error classes

Phase 0 landed the skeleton. Phase 2 expands across all providers:

- `LLMProvider.generate()` raises `ProviderTimeoutError`, `ProviderAuthError`, etc. instead of returning `None`
- `FallbackLLMProvider` catches, records on RouteInfo, tries fallback
- `TTSProvider.synthesize()` raises structured errors; failure marks audio job `failed` with `error_class`
- `AudioUnderstandingProvider` raises; falls back but stores `error_class`
- `ASRProvider` raises; records `error_class` in voice pipeline

**Files:** `backend/app/providers/errors.py`, `llm_mimo.py`, `tts_mimo.py`, `audio_omni.py`, `asr_http.py`, `asr_nvidia.py`, `backend/app/runtime/dispatcher.py`, `backend/app/runtime/route_policy.py`, `backend/app/runtime/audio_jobs.py`

**Verify:** Mock timeout/401/500/malformed JSON at each provider boundary; assert correct exception class and `error_class` in route metadata.

### Task 2: STAB-012 — Provider timeout tuples

Replace scalar `timeout=120` with `(connect_timeout, read_timeout)` tuples:
- Fast LLM: (5, 15)
- Slow LLM: (5, 60)
- ASR: (5, 10)
- TTS primary: (5, 30), fallback: (5, 60)
- Audio understanding: (5, 20)

Add one retry on `ProviderTimeoutError` for fast paths only.

**Files:** All provider files with HTTP calls.

**Verify:** Unit tests with mocked connect vs read timeout; assert short-circuit behavior.

### Task 3: STAB-011 — Provider circuit breaker

Add `ProviderCircuit` per provider:
- Rolling 60s window, failure count >= 5 → open circuit for 60s
- Fallback wrapper skips primary when circuit open
- Log state transitions

**Files:** `backend/app/providers/circuit.py`, `FallbackLLMProvider`, `FallbackTTSProvider`

**Verify:** Simulate 5 consecutive timeouts; assert primary skipped on 6th call; assert circuit closes after 60s.

### Task 4: STAB-020 — Startup provider key probes

From lifespan, schedule `asyncio.create_task` per provider:
- Tiny request (LLM 1-token, TTS empty, ASR silent)
- 5s timeout each, never block startup
- Cache results for at least 10 minutes to avoid quota consumption
- Record `last_success_at` / `last_error_class`
- Surface via deep health

**Files:** `backend/app/providers/probes.py`, `backend/app/main.py`

**Verify:** Unit test that probes mark `providers_ready` correctly; failure doesn't crash startup; cached results returned within 10-min window.

### Task 5: STAB-021 — Structured error class in API responses

Phase 0 added `error_class` field. Phase 2:
- Normalize class labels across providers
- Expose `route_info.provider_failure` in response
- Frontend maps classes to bubble copy

**Files:** `backend/app/api/text.py`, `backend/app/api/voice.py`, `frontend/src/App.tsx`

**Verify:** Integration test with mocked auth failure; assert response carries `error_class`.

### Task 6: STAB-024/CC-7 — AgentRunStore persistence

Table `agent_run(id, started_at, ended_at, route, brain, error_class, timings_json, sanitized_user_text, sanitized_response_text)`. Cap at 200 rows. Expose at `GET /api/debug/runs?limit=20`.

**Files:** `backend/app/runtime/agent_run.py`, `backend/app/runtime/memory_store.py`, `backend/app/api/debug.py`

**Verify:** Run 250 events; assert only 200 remain. Assert sanitization scrubs keys/tokens.

### Task 7: STAB-025 — Memory candidate retry with backoff

Add `attempt_count` and `next_retry_at` columns to `memory_candidate`:
- Provider failure → `status='retryable'`, exponential backoff (2^attempt min, capped 1h, max 5 attempts)
- Validation failure → permanent `error`

**Files:** `backend/app/runtime/memory_curator.py`, `backend/app/runtime/memory_store.py`, `backend/app/runtime/maintenance.py`

**Verify:** Simulate timeout 4 times; assert retry then eventual permanent fail.

### Task 8: STAB-022 — WAL periodic checkpoint

From maintenance worker, every 30 minutes (or every 100 writes, whichever first):
- `PRAGMA wal_checkpoint(PASSIVE)`
- Report WAL bytes via deep health
- TRUNCATE only during idle/shutdown

**Files:** `backend/app/runtime/maintenance.py`, `backend/app/api/health.py`

**Verify:** Unit test asserts PASSIVE checkpoint runs without blocking writers. TRUNCATE-shrinks-WAL test during idle/shutdown. Field check confirms no long request pause.

### Task 9: STAB-023 — Rolling DB backup

`DatabaseBackupManager` from maintenance worker:
- Once per day + before schema migrations
- `sqlite3.Connection.backup()` to `backend/data/backups/pet-YYYYMMDD-HHMMSS.db`
- Keep 7 routine + 3 pre-migration backups; prune older
- Surface last backup time in deep health

**Files:** `backend/app/runtime/backup.py`, `backend/app/runtime/maintenance.py`

**Verify:** Unit test creates/restores backup; asserts integrity. Migration test asserts backup is created before `PRAGMA user_version` changes. Concurrent write test confirms no long block.

### Task 10: STAB-037/CC-8 — Incident breadcrumb table

Table `runtime_incident(ts, kind, payload_json)`, capped ~500 rows:
- Provider errors write a row
- Audio job failures write a row
- Manager restart writes via `/api/internal/incident`
- Expose at `GET /api/debug/incidents?limit=50` behind debug token

**Files:** `backend/app/runtime/incident.py`, `backend/app/api/debug.py`, `scripts/termux_service_manager.sh`

**Verify:** Simulate provider failure; assert row inserted. Assert oldest pruned past cap. Assert endpoint rejects missing token.

### Task 11: STAB-017 — Wake fallback from audio understanding fields

When ASR fails, use existing `AudioUnderstanding` fields:
- Parse `user_text`, `tone_notes`, `non_verbal` for wake phrases
- Require confidence >= threshold
- Include `wake_source` in response: `"asr"`, `"audio_keyword"`, `"none"`

**Files:** `backend/app/runtime/voice_pipeline.py`, `backend/app/runtime/wake_detector.py` (new)

**Verify:** Unit test where ASR returns empty but audio understanding has wake keyword; assert wake fires above threshold. Low-confidence fixture must not wake.

## Verification

```bash
cd backend && ../.venv/bin/python -m pytest -q
cd frontend && npm test -- --run && npm run build
ssh nubia 'curl -s http://127.0.0.1:8000/api/health/deep -H "Authorization: Bearer $(cat ~/Petagent/backend/secrets/internal_token)"'
```

## Risks

- Provider timeout changes may cause premature timeouts on slow networks. Start with generous tuples, tune from Nubia field data.
- Circuit breaker false positives during transient noise. Window-based threshold mitigates.
- Backup disk space on phone. 200KB DB × 7 = 1.4MB, negligible.
- Wake fallback false wakes from ambient noise. Require confidence threshold + exact phrase match.
- Startup probes must not consume provider quota loudly. Use minimal payloads, cache results for >= 10 minutes.
