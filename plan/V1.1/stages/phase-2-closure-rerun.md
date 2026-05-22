# Phase 2 Closure Rerun: Persistence + Provider Observability

**Date:** 2026-05-22
**Mode:** strict closure rerun evidence for V1.1 Phase 2
**Base commits reviewed:** `200bd58`, `1ed0491`, `8484834`

## Scope

This closure rerun covers the Phase 2 requirements from `fix-spec-plan.md` and
the original stage plan `phase-2-persistence-observability.md`: STAB-011, 012,
017, 019-full, 020, 021, 022, 023, 024, 025, and 037.

The closure adds current plan-review and completion-review evidence, then fixes
the provider observability gap found in `audio_omni.py`.

## Current Findings To Close

1. `MiMoAudioUnderstandingProvider.understand()` catches every exception and
   returns fallback, hiding auth, timeout, HTTP, network, quota, and bad-response
   failures from route/provider observability.
2. `MiMoAudioUnderstandingProvider.understand()` base64-encodes
   `audio_path.read_bytes()`, which reads the whole audio file into memory before
   encoding. This violates the Android 6 low-memory guidance.
3. Voice fallback should stay companion-safe: user-facing voice flows may fall
   back to ASR/fallback understanding, but route metadata must retain structured
   provider failure information.
4. Phase 2 needs fresh plan-review and completion-review evidence tied to the
   current codebase.
5. Plan review found that missing configured audio-understanding API key/base
   URL must be structured provider failure metadata, not silent fallback; chunked
   base64 must be boundary-correct and avoid accumulated raw/encoded chunk
   lists; both slow and ASR-fallback voice paths need tests.

## Implementation Plan

1. Run a read-only subagent plan review against this closure plan, the master
   plan, original Phase 2 stage plan, and current code.
2. Update `backend/app/providers/audio_omni.py`:
   - Keep local non-provider conditions as fallback only for missing file and
     probably empty/silent audio.
   - Missing API key raises `ProviderAuthError`; missing base URL raises
     structured `ProviderError(code="not_configured")`.
   - Replace broad `except Exception: return FALLBACK_AUDIO_UNDERSTANDING` with
     `ProviderError` subclasses using the existing `app.providers.errors`
     hierarchy.
   - Use explicit classes for timeout, connection, HTTP 401/403, 429, 5xx, and
     malformed JSON/schema response.
   - Encode audio with a chunked helper instead of `audio_path.read_bytes()`:
     no whole raw bytes object, no accumulated encoded chunk list, and
     base64-safe chunk boundaries by carrying 0-2 leftover bytes between reads.
     The final string must match `base64.b64encode(file_bytes).decode("ascii")`
     in tests because MiMo requires one JSON base64 field.
3. Update `backend/app/runtime/voice_pipeline.py`:
   - Catch `ProviderError` around audio-understanding calls.
   - Continue companion-safe fallback behavior.
   - Populate `VoiceRouteInfo.provider_failure` with `exc.to_dict()` on both
     primary slow route and ASR fallback route.
   - Preserve existing `fallback_reason` values unless the only reason is
     provider failure, where `audio_understanding_error` is acceptable.
4. Add/adjust tests:
   - Audio understanding raises `ProviderTimeoutError`, `ProviderAuthError`,
     `ProviderUnavailableError`, `ProviderQuotaError`, `ProviderNetworkError`,
     and `ProviderBadResponseError` for mocked provider failures.
   - Audio encoding helper reads in chunks by observing multiple `read()` calls
     for a file larger than one chunk.
   - Voice slow route exposes `voice_route.provider_failure.error_class` while
     preserving a normal Momo response via fallback.
   - Fast ASR fallback route preserves `fallback_reason`, selected route, and
     normal reply while surfacing audio-understanding `provider_failure`.
5. Run verification:
   - `cd backend && ../.venv/bin/python -m pytest tests/test_audio_omni_provider.py tests/test_phase2_providers.py tests/test_voice_pipeline.py -q`
   - `cd backend && ../.venv/bin/python -m pytest -q`
6. Run completion review with a read-only subagent.
7. Fix completion-review findings if needed and rerun relevant tests.
8. Write compact handoff summary in this file.
9. Commit and push only Phase 2 closure changes.

## Nubia Checks

After final deployment, live checks must verify provider errors are observable:

```bash
ssh nubia 'curl -sS --connect-timeout 2 --max-time 5 http://127.0.0.1:8000/api/health/deep -H "Authorization: Bearer $TOKEN"'
```

The 10-scenario live suite should also assert debug runs/incidents include
provider failure metadata after a controlled internal incident or mocked/local
failure path. It must not leak API keys or raw provider payloads.

## Rollback Notes

If strict `audio_omni.py` errors break voice interaction, keep the provider
structured exceptions but temporarily downgrade only `voice_pipeline` handling
to fallback without surfacing `provider_failure`. Do not restore silent provider
swallowing inside the provider itself.

## Plan Review

Initial read-only subagent review returned `FIX`:

```json
{"verdict":"FIX","issues":["Plan incorrectly treats missing audio-understanding API key/base URL as silent fallback; Phase 2 requires configured provider/auth failures to propagate as structured ProviderError metadata while voice UX falls back safely.","Chunked base64 plan does not require boundary-correct encoding or avoiding chunk-list duplication, so it may still be incorrect or memory-spiky on Android 6/Termux.","Tests cover slow-route provider_failure but do not explicitly cover the ASR-fallback path preserving fallback_reason/reply while surfacing audio_understanding provider_failure."]}
```

Resolution: this plan now requires structured missing-config failures, a
boundary-correct streaming base64 helper with no raw/encoded chunk accumulation,
and tests for both slow and fast-ASR-fallback voice paths.

## Completion Review

Read-only subagent completion review returned `FIX`:

```json
{"verdict":"FIX","issues":["backend/app/providers/audio_omni.py:176 still falls back from settings.audio_understanding.api_key to settings.api_key, so a missing MIMO_API_KEY can silently use the SiliconFlow/global key instead of surfacing missing audio-understanding credentials as structured provider failure.","backend/app/providers/audio_omni.py:135 accumulates encoded_parts before join, violating the closure rerun requirement to avoid accumulated raw/encoded chunk lists even though read_bytes was removed."]}
```

Resolution:

- `MiMoAudioUnderstandingProvider` now uses only
  `settings.audio_understanding.api_key`; it does not fall back to the global
  API key.
- Added regression coverage for a present global key with missing
  audio-understanding key.
- `encode_audio_base64_chunked()` now streams encoded output to `io.StringIO`
  instead of accumulating an encoded chunk list, and still avoids
  `audio_path.read_bytes()`.
- Reran targeted Phase 2 tests and full backend suite.

Verification:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_audio_omni_provider.py tests/test_phase2_providers.py tests/test_voice_pipeline.py -q
# 42 passed in 0.43s

cd backend && ../.venv/bin/python -m pytest -q
# 524 passed, 16 skipped in 11.69s
```

## Compact Handoff

Phase 2 closure changed:

- `audio_omni.py` now raises structured provider errors for missing key,
  missing base URL, timeout, network, HTTP auth/quota/unavailable, and malformed
  provider response.
- Audio-understanding base64 encoding no longer uses `read_bytes()` and avoids
  raw whole-file reads or encoded chunk-list accumulation.
- `voice_pipeline` catches audio-understanding `ProviderError`, keeps Momo’s
  companion-safe fallback flow, and surfaces sanitized `provider_failure`
  metadata in `voice_route` for both slow/thinking and ASR-fallback routes.

Tests:

- Targeted Phase 2 provider/voice tests: 42 passed.
- Full backend suite: 524 passed, 16 skipped.

Nubia:

- Not deployed during Phase 2 closure. Final deployment phase must update Nubia
  to latest `origin/main`, restart manager/runtime, and run V1.1 live API tests
  with token-protected debug/deep endpoints.

Next phase entry point:

- Phase 3 closure should update V1.1-aware live API tests and verify frontend
  client config/build behavior without committing `frontend/dist`.
