# Phase 0 Completion Handoff

## Summary
Phase 0 (Correctness + Safety Gates) is complete. All 7 STAB items implemented, tested, and reviewed.

## Changed Files

| File | Change |
|------|--------|
| `backend/app/providers/errors.py` | NEW — ProviderError hierarchy (7 classes) |
| `backend/app/api/auth.py` | NEW — Internal token gate (get_internal_token, require_internal_token, is_loopback) |
| `backend/app/providers/audio_omni.py` | STAB-002 — Use audio_understanding.api_key, configurable auth scheme |
| `backend/app/runtime/route_policy.py` | STAB-003 — Add brain field to RouteDecision |
| `backend/app/runtime/text_pipeline.py` | STAB-003 — Use decide_route() for brain selection, expose route_reason |
| `backend/app/runtime/voice_pipeline.py` | STAB-004 — thinking/slow voice uses audio understanding first |
| `backend/app/runtime/voice_types.py` | STAB-004 — Add emotion_source to VoiceRouteInfo |
| `backend/app/api/text.py` | STAB-019 — Catch ProviderError, return structured error_class |
| `backend/app/api/voice.py` | STAB-019 — Catch ProviderError, return structured error_class |
| `backend/app/api/pet.py` | STAB-027 — Remove apply_if_due from GET /state, add POST /session/resume |
| `backend/app/main.py` | STAB-032 — CORS allowlist, internal token setup |
| `backend/app/runtime/dispatcher.py` | STAB-029 — Strip energy from LLM state_delta |

## Test Results
- Backend: 353 passed, 16 skipped
- Frontend: 38 passed
- Frontend build: passed
- New test file: `backend/tests/test_phase0_safety.py` (15 tests for STAB-019/027/032)
- Updated test: `backend/tests/test_voice_pipeline.py` (thinking mode test updated)
- Updated test: `backend/tests/test_route_policy.py` (brain field assertions added)

## Review Status
- Plan review: PASS
- Completion review: PASS (after fixing 5 findings: missing tests, dead code)

## Nubia Check
Not yet performed — deploy Phase 0 to Nubia after commit.

## Next Phase
Phase 1: Mobile-Safe Runtime + Recovery (STAB-001, 005, 006, 007, 008, 009, 010, 013, 014, 015, 033, 036)

## Entry Point for Phase 1
- Start with STAB-015/CC-6: SQLite AudioJobStore
- Then STAB-006/CC-4: FastAPI lifespan
- Then STAB-036/CC-3: Health split (light/watchdog/deep)
- Key dependency: lifespan needs AudioJobStore for shutdown drain
