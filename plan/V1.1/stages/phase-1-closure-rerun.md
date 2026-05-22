# Phase 1 Closure Rerun: Mobile-Safe Runtime + Recovery

**Date:** 2026-05-22
**Mode:** strict closure rerun evidence for V1.1 Phase 1
**Base commits reviewed:** `aa40327`, `b7c2fa2`

## Scope

This closure rerun covers the Phase 1 requirements from `fix-spec-plan.md` and
the original stage plan `phase-1-mobile-runtime-recovery.md`: STAB-001, 005,
006, 007, 008, 009, 010, 013, 014, 015, 033, and 036.

The closure does not rewrite history. It adds current, explicit evidence for
plan review, completion review, compact handoff, and fixes only the Phase 1
gaps found by review.

## Current Findings To Close

1. `GET /api/health/watchdog` does not expose `provider_inflight_age_s`, even
   though the master plan requires it.
2. `scripts/termux_service_manager.sh` uses `curl --connect-timeout 3
   --max-time 8` for light and watchdog health, not the Phase 1 1/2s and 1/3s
   budget.
3. Phase 1 needs fresh plan-review and completion-review evidence tied to the
   current codebase.
4. The proactive scheduler implementation must be checked by completion review
   against the “browser stale means no provider/TTS load” constraint.
5. Plan review found that provider inflight timing must include current LLM,
   ASR/audio-understanding, and TTS provider call sites; watchdog queue depth
   must avoid contended audio manager locks; stale frontend proactive triggers
   must not force LLM/TTS; manager curl budgets need static tests.

## Implementation Plan

1. Run a read-only subagent plan review against this closure plan, the master
   plan, original Phase 1 stage plan, and current code.
2. Add provider inflight timing to `ProviderGate`:
   - Store a `perf_counter()` start timestamp per provider type when the first
     slot is acquired.
   - Clear the timestamp when the provider type counter returns to zero.
   - Expose `inflight_age_s(provider_type=None)` where `None` returns the
     oldest active provider age, or `-1.0` when no provider is active.
   - Keep `get_usage()` backward compatible.
3. Route all current Phase 1 provider call sites through the gate:
   - Dispatcher LLM already uses `ProviderGate`; keep behavior.
   - Voice ASR calls acquire/release `asr`.
   - Voice audio-understanding calls acquire/release `audio_understanding`.
   - AudioJobManager TTS calls acquire/release `tts`.
   - If a provider gate is at capacity, voice fallback behavior remains
     companion-safe: return fallback understanding/transcript rather than
     crashing the pet loop; TTS jobs fail with sanitized `provider_busy`.
4. Expose `provider_inflight_age_s` from both `/api/health/watchdog` and
   `/api/health/deep` without acquiring dispatcher locks or doing provider/DB
   calls.
5. Make `audio_queue_depth` watchdog-safe:
   - Add a nonblocking/cached pending counter on `AudioJobManager`.
   - Update it under the audio job lock during enqueue/status transitions.
   - `pending_count()` becomes a lock-free read for watchdog use.
6. Stale frontend proactive trigger safety:
   - If `proactive_scheduler.is_frontend_stale()` is true, `/api/pet/proactive/trigger`
     must force `low_cost`, set `synthesize_voice=False`, and avoid the normal
     LLM brain even when `mode=llm` is requested.
   - Preserve read-only `/api/pet/proactive` behavior.
7. Align Termux manager curl timeouts:
   - `/api/health`: `--connect-timeout 1 --max-time 2`
   - `/api/health/watchdog`: `--connect-timeout 1 --max-time 3`
   - Browser heartbeat relaunch watchdog check also uses the watchdog budget.
8. Add/adjust tests:
   - ProviderGate age starts on acquire and resets on final release.
   - Watchdog includes `provider_inflight_age_s`.
   - Deep health includes `provider_inflight_age_s`.
   - Voice pipeline gates ASR and audio-understanding.
   - AudioJobManager gates TTS and pending count is nonblocking/cached.
   - Stale frontend proactive trigger ignores `mode=llm` and disables voice.
   - Static manager script test verifies 1/2s and 1/3s curl budgets.
9. Run local verification:
   - `cd backend && ../.venv/bin/python -m pytest tests/test_phase1_health.py tests/test_phase1_watchdog.py tests/test_phase1_dispatcher.py -q`
   - `cd backend && ../.venv/bin/python -m pytest tests/test_phase1_proactive.py tests/test_phase1_audio_jobs.py tests/test_phase1_startup.py -q`
   - `cd backend && ../.venv/bin/python -m pytest -q`
10. Run completion review with a read-only subagent.
11. Fix completion-review findings if needed and rerun relevant tests.
12. Write compact handoff summary in this file.
13. Commit and push only Phase 1 closure changes.

## Nubia Checks

After local commit/push and deployment phase, run:

```bash
ssh nubia 'curl -sS --connect-timeout 2 --max-time 5 http://127.0.0.1:8000/api/health'
ssh nubia 'curl -sS --connect-timeout 2 --max-time 5 http://127.0.0.1:8000/api/health/watchdog'
ssh nubia 'ps -A -o pid,ppid,stat,args | grep -E "[t]ermux_service_manager|[u]vicorn|[s]shd"'
```

Expected watchdog fields include `provider_inflight_age_s`,
`frontend_heartbeat_age_s`, `audio_queue_depth`, and `stuck`.

## Rollback Notes

If watchdog/provider changes regress health, revert only the `ProviderGate` age
fields, provider call-site gate wiring, cached pending counter, and health
response field. Existing concurrency limits remain intact. If field checks show
old Nubia curl budgets are too aggressive, relax only `scripts/termux_service_manager.sh`
timeouts back to 3/8s while keeping the health endpoint contract. If stale
frontend proactive suppression blocks desired visible pet behavior, disable only
the `mode=llm` override while keeping `synthesize_voice=False` for stale
frontend.

## Plan Review

Initial read-only subagent review returned `FIX`:

```json
{"verdict":"FIX","issues":["Provider inflight age plan only instruments ProviderGate, but current code gates only dispatcher LLM calls; ASR/audio-understanding in voice_pipeline.py and TTS in audio_jobs.py can be inflight while provider_inflight_age_s reports idle.","Watchdog health still calls audio_mgr.pending_count(), which takes AudioJobManager._lock; that lock is also held around SQLite store saves, so the closure plan does not fully protect the health lane from blocking.","Proactive scheduler risk is only delegated to completion review. Current /api/pet/proactive/trigger?mode=llm can still dispatch LLM and optional TTS without checking frontend heartbeat staleness.","Tests/Nubia checks do not prove the manager timeout change: no explicit script/static test for health 1/2s, watchdog 1/3s, or browser relaunch watchdog budget; Nubia checks use 2/5s and do not exercise provider_inflight_age_s under live inflight work.","Rollback notes cover ProviderGate/health fields only, not Termux timeout changes or any proactive stale-frontend mitigation."]}
```

Resolution: this plan now explicitly includes ASR/audio-understanding/TTS gate
coverage, a lock-free/cached audio queue depth, stale-frontend proactive trigger
suppression, static manager timeout tests, live field checks, and expanded
rollback notes.

## Completion Review

Read-only subagent completion review returned `FIX`:

```json
{"verdict":"FIX","issues":["backend/app/runtime/dispatcher.py:282-297 releases ProviderGate in finally even when acquire() raises ProviderBusyError. Under saturation, a rejected LLM request decrements an active provider slot it never acquired, clearing _started_at and making provider_inflight_age_s report idle while a provider call is still running."],"fix_items":["Track gate_acquired in RuntimeDispatcher before release, matching the ASR/audio_understanding/TTS patterns, and add a saturation regression test proving an acquire failure does not decrement active usage or reset provider_inflight_age_s."]}
```

Resolution:

- `RuntimeDispatcher` now tracks `gate_acquired` and only releases `ProviderGate`
  after successful acquire.
- Added `test_provider_gate_failed_acquire_does_not_reset_active_age`.
- Reran targeted Phase 1 tests and full backend suite.

Verification:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_phase1_dispatcher.py tests/test_audio_jobs.py tests/test_audio_job_store.py tests/test_phase1_health.py tests/test_phase1_watchdog.py tests/test_phase1_proactive.py tests/test_voice_pipeline.py tests/test_phase1_startup.py -q
# 69 passed in 1.22s

cd backend && ../.venv/bin/python -m pytest -q
# 512 passed, 16 skipped in 24.88s
```

## Compact Handoff

Phase 1 closure changed:

- `ProviderGate` tracks inflight provider age and exposes `inflight_age_s`.
- Watchdog/deep health now include `provider_inflight_age_s`, and watchdog marks
  `stuck` for stale provider calls.
- Dispatcher, voice pipeline, and audio jobs gate LLM, ASR, audio understanding,
  and TTS provider calls.
- `AudioJobManager.pending_count()` is now a cached lock-free watchdog read, with
  pending count adjusted on enqueue, terminal completion, supersede, expiry,
  restart-failed, and shutdown-failed transitions.
- Stale frontend proactive trigger forces `low_cost` and disables synthesized
  voice even when `mode=llm` is requested.
- Termux manager light health uses 1/2s curl budget; watchdog and browser
  relaunch checks use 1/3s.

Tests:

- Targeted Phase 1/audio/voice tests: 69 passed.
- Full backend suite: 512 passed, 16 skipped.

Nubia:

- Not deployed during Phase 1 closure. Final deployment phase must update Nubia
  from old `85e924d` to latest `origin/main`, restart manager/runtime, and run
  the V1.1 live API scenario set.

Next phase entry point:

- Phase 2 closure should address `audio_omni.py` provider error propagation and
  streaming/base64 memory behavior, then update related tests.
