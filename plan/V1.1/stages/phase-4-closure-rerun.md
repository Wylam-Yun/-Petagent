# Phase 4 Closure Rerun: Hardening Follow-through

**Date:** 2026-05-22
**Mode:** strict closure rerun evidence for V1.1 Phase 4
**Base commits reviewed:** `9851080`, `1be439d`

## Scope

This closure rerun covers the Phase 4 requirements from `fix-spec-plan.md` and
the original stage plan `phase-4-hardening.md`: STAB-018, STAB-026,
STAB-032-hardening, STAB-034, and STAB-035.

The closure does not rewrite earlier Phase 4 history. It adds current
plan-review and completion-review evidence, then fixes only Phase 4 hardening
gaps found against the current codebase.

## Current Findings To Close

1. Upload validation currently checks WAV magic bytes only. The master plan
   requires WAV, MP3, OGG, and WebM magic-byte checks after the streaming upload
   save.
2. `MemoryCardManager.rebuild()` and `clear()` are locked, but
   `read_card_with_provenance()` remains lock-free while the master plan asks to
   serialize read-with-provenance too.
3. Phase 4 proxy supervision exists in `scripts/termux_service_manager.sh`, but
   it needs a separate restart backoff/counter and static regression evidence
   that `ensure_proxy()` is called each manager loop and logs restart
   attempts/results.
4. Phase 4 security hardening needs concrete token rotation/re-pair support,
   rejected debug/internal auth breadcrumbs, and fresh evidence after Phase 3
   expanded the protected endpoint inventory.
5. Runtime log rotation exists in `MaintenanceWorker`, but it uses
   `read_bytes()` to copy the whole log during rotation. On Android 6 this
   should be changed to a bounded streaming copy before truncation.
6. Log paths and token operation steps are not documented for the Nubia
   operator flow.
7. Phase 4 needs fresh plan-review, completion-review, test, compact handoff,
   commit, and push evidence tied to the current codebase.

## Implementation Plan

1. Run a read-only subagent plan review against this closure plan, the master
   plan, original Phase 4 stage plan, `stability-issues.md`, and current code.
2. Update upload magic validation in `backend/app/api/voice.py`:
   - Keep allowed MIME types and streaming upload limits unchanged.
   - Validate only the first few bytes required for each supported type.
   - WAV: `RIFF....WAVE`.
   - MP3: `ID3` or MPEG frame sync beginning with `0xFF` and top three bits of
     the next byte set.
   - OGG: `OggS`.
   - WebM: EBML header `1A 45 DF A3`.
   - Keep `audio/mp4` accepted but do not add partial MP4 validation in this
     closure unless review requires it, because the master plan names WebM/OGG
     and the original Phase 4 stage plan narrowed validation to WAV.
   - On mismatch, delete the upload and return HTTP 400 with
     `error_class: "invalid_audio"`.
   - Keep validation in `voice.py` for this closure instead of adding
     `backend/app/runtime/audio_validation.py`, because the existing upload
     validation is already localized there and splitting a tiny helper would
     add churn without reducing Phase 4 risk.
3. Update tests for upload validation:
   - Add accept/reject tests for MP3, OGG, and WebM.
   - Adjust existing local WebM voice-contract fixtures to include a minimal
     valid WebM magic header so normal voice-first tests keep exercising the
     voice path instead of the validator.
4. Update `MemoryCardManager.read_card_with_provenance()` to acquire the same
   `RLock` used by `rebuild()` and `clear()`.
   - Preserve atomic replace writes and the old-path migration fallback.
   - Keep `read_card()` behavior unchanged through the locked provenance read.
   - Add a regression test that explicitly exercises concurrent
     rebuild/read-with-provenance calls.
5. Harden runtime log rotation in `backend/app/runtime/maintenance_worker.py`:
   - Replace whole-file `read_bytes()` copy with a streaming `shutil.copyfileobj`
     copy to `.log.old`, then truncate the active log.
   - Keep best-effort behavior and avoid crashing the maintenance worker.
   - Keep the mobile default at 512KB.
6. Add Phase 4 token operation support in `backend/app/api/auth.py` and
   `backend/app/api/debug.py`:
   - Add a small helper to resolve the persisted internal token path.
   - Add a token rotation endpoint under `/api/debug/token/rotate` protected by
     the current internal token.
   - Generate and persist a replacement token with mode `0600`, update
     `app.state.internal_token`, and return only a token fingerprint plus path,
     never the raw token.
   - Treat this as the local re-pair primitive: the operator reads the new
     token from the existing local token file on the phone or Mac tunnel.
7. Add rejected debug/internal auth breadcrumbs:
   - When a request to a protected endpoint lacks or fails the token check,
     record a sanitized `auth_rejected` incident if an incident store is
     available.
   - Include path, method, client host, and reason only; never log token values.
   - Keep token rejection status at HTTP 403.
8. Add proxy supervision backoff in `scripts/termux_service_manager.sh`:
   - Add `PROXY_BACKOFF_SECONDS` and a loop-local `proxy_fail_count`.
   - Make `ensure_proxy()` return success/failure so the main loop can apply a
     separate backoff without blocking runtime/sshd checks unless repeated
     proxy restart failures happen.
   - Keep `start_proxy_once()` for startup behavior and keep the disable file
     semantics.
9. Document operator steps:
   - Update `README.md` with V1.1 internal token, rotation/re-pair, live test,
     and log path notes.
   - Add `docs/operations.md` with Nubia runtime checks, token handling, log
     locations, proxy supervision, and live API command examples.
10. Add/adjust Phase 4 hardening tests:
   - Static manager script test for `ensure_proxy()` definition, loop call,
     port `7897` check, restart log messages, and separate proxy backoff
     variables/counter.
   - Token boundary/security tests from Phase 3 remain part of the targeted
     Phase 4 verification set, with new coverage for token rotation and
     rejected-auth incidents.
   - Log rotation test still proves old log content is copied and active log is
     truncated.
11. Run local verification:
   - `cd backend && ../.venv/bin/python -m pytest tests/test_phase4_hardening.py tests/test_phase0_safety.py tests/test_phase2_incident.py -q`
   - `cd backend && ../.venv/bin/python -m pytest tests/test_voice_contract.py tests/test_voice_pipeline.py tests/test_api_contracts.py tests/test_phase1_startup.py -q`
   - `cd backend && ../.venv/bin/python -m pytest -q`
   - `cd frontend && npm test -- --run`
   - `cd frontend && npm run build`
   - Confirm `backend/secrets/` and `frontend/dist/` remain ignored/untracked.
12. Run completion review with a read-only subagent comparing the master plan,
   this stage plan, current code, and actual diff.
13. Fix completion-review findings if needed and rerun relevant tests.
14. Write compact handoff summary in this file because slash commands cannot be
    executed from this environment.
15. Commit and push only Phase 4 closure changes.

## Nubia Checks

After Phase 4 commit/push, the final deployment step updates Nubia to latest
`origin/main`, restarts the Termux manager/runtime, and runs the live suite.
Phase 4-specific device checks should include:

```bash
ssh nubia 'curl -sS --connect-timeout 2 --max-time 5 http://127.0.0.1:8000/api/health'
ssh nubia 'curl -sS --connect-timeout 2 --max-time 5 http://127.0.0.1:8000/api/health/watchdog'
ssh nubia 'ps -A -o pid,ppid,stat,args | grep -E "[t]ermux_service_manager|[u]vicorn|[s]shd"'
ssh nubia 'tail -n 80 ~/Petagent/logs/manager.log 2>/dev/null || true'
```

The 10-scenario live API test remains the final proof that public endpoints,
token-protected endpoints, watchdog, heartbeat, client config, incidents, runs,
and audio job persistence all behave on Android 6.

## Rollback Notes

If expanded magic-byte validation rejects a real browser recording on Nubia,
revert only the affected non-WAV validator while keeping WAV validation and
structured `invalid_audio` responses. If memory-card read locking causes
unexpected contention, keep rebuild/clear locking and narrow the read lock to
path resolution plus file read only. If streaming log rotation fails on Termux,
revert only the copy implementation to the previous rotate behavior while
retaining size checks. If token rotation breaks operator access, keep the
existing persisted token path and disable only the rotate endpoint while
preserving the token gate. If proxy backoff delays runtime recovery, adjust only
`PROXY_BACKOFF_SECONDS`/counter logic and keep proxy supervision observable. Do
not make protected endpoints public to satisfy tests.

## Plan Review

Initial read-only subagent review returned `FIX`:

```json
{"verdict":"FIX","issues":["STAB-032-hardening is under-scoped versus master plan: token rotation/re-pair, rejected debug/internal request audit breadcrumbs, and README/operator docs are missing.","STAB-034 proxy supervision lacks separate backoff/regression coverage.","STAB-035 log consolidation documentation is missing.","STAB-018 file mapping omits the master-plan audio_validation.py decision."]}
```

Resolution: this plan now adds token rotation/re-pair support, rejected-auth
incident breadcrumbs, proxy restart backoff, README and `docs/operations.md`
updates, static regression tests for proxy supervision/backoff, token rotation
and auth rejection tests, and an explicit decision to keep tiny audio validation
helpers in `voice.py` for surgical closure.

## Completion Review

Read-only subagent completion review returned `FIX`:

```json
{"verdict":"FIX","findings":["/api/internal/incident is token-protected but not loopback-restricted; master plan requires loopback plus shared secret.","CORS hardening is not fully verified: tests only assert loopback is allowed, not that unlisted origins are rejected."]}
```

Resolution:

- `/api/internal/incident` now requires both the internal token and loopback.
  Non-loopback attempts record a sanitized `auth_rejected` incident with
  `reason=non_loopback_internal`.
- Added tests that a valid token from non-loopback is rejected and that loopback
  plus token is accepted.
- Added a CORS preflight regression proving an unlisted LAN origin does not get
  `access-control-allow-origin`.

Read-only subagent completion re-review after fixes returned `PASS`:

```json
{"verdict":"PASS","findings":[],"phase4_requirements":{"STAB-018":"PASS","STAB-026":"PASS","STAB-032":"PASS","STAB-034":"PASS","STAB-035":"PASS"}}
```

Verification:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_phase4_hardening.py tests/test_phase0_safety.py tests/test_phase2_incident.py -q
# 50 passed in 0.42s

cd backend && ../.venv/bin/python -m pytest tests/test_voice_contract.py tests/test_voice_pipeline.py tests/test_api_contracts.py tests/test_phase1_startup.py -q
# 24 passed in 0.52s

cd backend && ../.venv/bin/python -m pytest -q
# 540 passed, 24 skipped in 23.52s

cd frontend && npm test -- --run
# 13 test files passed, 40 tests passed

cd frontend && npm run build
# success; dist/build-info.json contains git_sha, build_time, source_hash

git status --short --ignored backend/secrets frontend/dist
# !! backend/secrets/
# !! frontend/dist/
```

## Compact Handoff

Phase 4 closure changed:

- Upload validation now checks WAV, MP3, OGG, and WebM magic bytes with bounded
  header reads and structured `invalid_audio` responses. `audio/ogg` is included
  in the default/config allowed types.
- `MemoryCardManager.read_card_with_provenance()` is serialized with the same
  `RLock` used by rebuild/clear while preserving atomic file replace behavior.
- Runtime log rotation now streams to `.log.old` in 64KB chunks before
  truncating the active log.
- Internal token handling now has path/fingerprint helpers, a protected
  `/api/debug/token/rotate` endpoint that never returns the raw token, and
  sanitized `auth_rejected` incidents for failed protected requests.
- `/api/internal/incident` now requires loopback plus token.
- Termux manager proxy supervision now has a separate failure counter and
  `PROXY_BACKOFF_SECONDS`.
- `README.md` and `docs/operations.md` document token handling, rotate/re-pair,
  Nubia checks, proxy supervision, log paths, and the live API command.

Tests:

- Phase 4/security/incident targeted tests: 50 passed.
- Voice/API/manager targeted tests: 24 passed.
- Full backend suite: 540 passed, 24 skipped.
- Frontend tests: 40 passed.
- Frontend build: passed; build-info has `git_sha`, `build_time`,
  `source_hash`.

Nubia:

- Not deployed during the Phase 4 commit. Final deployment must update Nubia to
  latest `origin/main`, restart manager/runtime, and run the 10-scenario live
  API suite against `http://127.0.0.1:8000` with the internal token file.

Next step:

- Commit and push Phase 4 closure, then deploy latest code to Nubia and run
  `backend/tests/test_live_nubia.py` on-device.
