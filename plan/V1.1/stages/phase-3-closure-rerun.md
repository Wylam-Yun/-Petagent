# Phase 3 Closure Rerun: Frontend UX Resilience

**Date:** 2026-05-22
**Mode:** strict closure rerun evidence for V1.1 Phase 3
**Base commits reviewed:** `23f662e`, `99f1f00`

## Scope

This closure rerun covers the Phase 3 requirements from `fix-spec-plan.md` and
the original stage plan `phase-3-frontend-ux-resilience.md`: STAB-016, 028, 030,
and 031.

The closure adds current plan-review and completion-review evidence, refreshes
the live API tests to match V1.1 public/token-protected endpoint boundaries, and
verifies frontend test/build behavior without committing `frontend/dist`.

## Current Findings To Close

1. `backend/tests/test_live_nubia.py` targets legacy endpoints and treats
   token-protected debug/runtime endpoints as public.
2. Live tests do not cover V1.1 endpoints added in Phase 1-3:
   `/api/health/watchdog`, `/api/runtime/client-config`,
   `/api/frontend/heartbeat`, audio jobs, debug runs/incidents, and no-token
   security checks.
3. Phase 3 needs fresh plan-review and completion-review evidence tied to the
   current codebase.
4. Frontend build verification must be explicit: `frontend/dist` is generated
   and untracked; build artifacts should not be committed.
5. Plan review found that V1.1 protected endpoint inventory is broader than
   debug/runtime/internal checks, and current code still exposes several
   protected endpoints without token checks.

## Implementation Plan

1. Run a read-only subagent plan review against this closure plan, the master
   plan, original Phase 3 stage plan, and current code.
2. Update `backend/tests/test_live_nubia.py`:
   - Keep `PETAGENT_TEST_URL` as the required base URL.
   - Add optional `PETAGENT_INTERNAL_TOKEN` and
     `PETAGENT_INTERNAL_TOKEN_FILE`.
   - Add helper headers for protected endpoints.
   - Add helper assertions for public endpoint success and protected endpoint
     403 without token.
   - Replace legacy `/api/context/debug`, `/api/memory/debug`,
     `/api/context/runs`, and unauthenticated `/api/runtime/skills` checks with
     V1.1-aware debug endpoints.
   - Cover the full V1.1 protected inventory from the master plan:
     `/api/health/deep`, `/api/debug/*`, `/api/internal/*`,
     `/api/context/debug`, `/api/context/runs`, `/api/memory/debug`,
     `/api/memory/curate`, `/api/memory/summarize`, `/api/runtime/reset`,
     `/api/runtime/skills`, and `/api/skills/{skill_id}/run`.
   - Keep live tests safe: no runtime reset, no destructive memory operations,
     no large uploads.
3. Define the V1.1 live scenario set in the test file:
   - `GET /api/health`
   - `GET /api/health/watchdog`
   - `GET /api/runtime/client-config`
   - `POST /api/frontend/heartbeat` and watchdog heartbeat age update
   - `GET /api/pet/state`
   - `GET /api/interactions`
   - `POST /api/text/chat` and optional `/api/audio/jobs/{id}` polling
   - `POST /api/pet/event`
   - protected `GET /api/debug/runs` and `GET /api/debug/incidents`
   - no-token protected boundary checks for debug/runtime/internal endpoints
4. Update local tests only if needed to match the live test helper behavior.
5. Add minimal token gates required for the V1.1 protected inventory if tests
   expose public protected endpoints:
   - Gate debug reads and management writes with `require_internal_token`.
   - Keep public companion endpoints token-free: `/api/health`,
     `/api/health/watchdog`, `/api/runtime/client-config`, `/api/pet/state`,
     `/api/interactions`, `/api/text/chat`, `/api/voice/chat`,
     `/api/frontend/heartbeat`, normal pet event/proactive reads.
   - Do not move broader security UX/pairing work out of Phase 4.
6. Add explicit frontend evidence:
   - Existing/new tests must cover public `/api/runtime/client-config` usage,
     progressive audio wait text, retry voice button, offline banner, and
     heartbeat/proactive polling pause while offline.
   - `npm run build` must produce `frontend/dist/build-info.json` with
     `git_sha`, `build_time`, and `source_hash`.
   - After build, confirm `frontend/dist` is not tracked or staged.
7. Run verification:
   - `cd backend && ../.venv/bin/python -m pytest tests/test_live_nubia.py -q`
     without `PETAGENT_TEST_URL` should skip cleanly.
   - `cd backend && ../.venv/bin/python -m pytest -q`
   - `cd frontend && npm test -- --run`
   - `cd frontend && npm run build`
   - Confirm `frontend/dist` remains untracked and is not staged.
8. Run completion review with a read-only subagent.
9. Fix completion-review findings if needed and rerun relevant tests.
10. Write compact handoff summary in this file.
11. Commit and push only Phase 3 closure changes.

## Nubia Checks

Phase 3 closure is local/provisional until final deployment updates Nubia to
latest `origin/main` and this command passes on the Android 6 device:

```bash
PETAGENT_TEST_URL=http://192.168.10.239:8000 \
PETAGENT_INTERNAL_TOKEN_FILE=/path/to/local/token-copy \
../.venv/bin/python -m pytest backend/tests/test_live_nubia.py -q
```

When running over `ssh nubia`, prefer loopback:

```bash
ssh nubia 'cd ~/Petagent/backend && PETAGENT_TEST_URL=http://127.0.0.1:8000 PETAGENT_INTERNAL_TOKEN_FILE=../backend/secrets/internal_token ../.venv/bin/python -m pytest tests/test_live_nubia.py -q'
```

If the token file path differs on Nubia, locate it before running tests and do
not print the token value.

## Rollback Notes

If live tests become too slow or flaky on weak networks, mark only provider-heavy
LLM/weather scenarios with a clear skip condition while keeping health,
watchdog, client-config, heartbeat, and security-boundary scenarios mandatory.
Do not make protected debug/internal endpoints public to satisfy live tests.

## Plan Review

Initial read-only subagent review returned `FIX`:

```json
{"verdict":"FIX","issues":["Security evidence is under-scoped: phase-3-closure-rerun.md only names debug/runtime/internal boundary checks, but V1.1 protected inventory in fix-spec-plan.md also includes /api/health/deep, /api/context/debug, /api/context/runs, /api/memory/debug, /api/memory/curate, /api/memory/summarize, /api/runtime/reset, and /api/skills/{skill_id}/run.","Current code evidence shows several protected-inventory endpoints are still public or destructive without token checks: backend/app/api/context.py, backend/app/api/memory.py, and backend/app/api/skills.py.","Frontend UX verification is too generic: npm test/build is listed, but the closure plan does not require explicit evidence for progressive audio wait text, retry voice, offline banner, polling pause/resume, or reconnect/session-resume behavior.","Nubia closure is deferred until a later deployment phase, so Phase 3 cannot be fully closed on the Android 6 target unless the result is marked provisional or the live Nubia run is mandatory now.","Build artifact handling needs sharper evidence: npm run build is listed, but the plan should require checking dist/build-info.json fields and proving frontend/dist remains ignored/untracked and unstaged."]}
```

Resolution: this plan now expands V1.1 live/security checks to the full
protected endpoint inventory, includes minimal token gates if tests expose public
protected endpoints, requires explicit frontend UX/build-info evidence, and marks
Nubia Phase 3 closure as provisional until the final deployment phase runs the
live suite on updated device code.

## Completion Review

Read-only subagent completion review returned `FIX`:

```json
{"verdict":"FIX","issues":["backend/tests/test_live_nubia.py no-token helper passes json= to httpx.get for GET cases; with PETAGENT_TEST_URL set, protected GET checks will raise TypeError instead of verifying 403.","backend/secrets/internal_token is untracked and not ignored, leaving a generated secret at risk of accidental commit."]}
```

Resolution:

- `_status()` in `test_live_nubia.py` now uses `httpx.get()` without a JSON
  body for GET protected-boundary checks.
- `.gitignore` now ignores `backend/secrets/`, preventing generated internal
  token files from appearing as untracked commit candidates.
- Reran backend targeted tests, full backend tests, frontend tests, frontend
  build, and build-info/git-status checks.

Verification:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_live_nubia.py tests/test_phase0_safety.py tests/test_stage35_api.py tests/test_stage36_api.py tests/test_stage3_skills_and_proactive.py -q
# 39 passed, 21 skipped in 0.62s

cd backend && ../.venv/bin/python -m pytest -q
# 525 passed, 24 skipped in 13.31s

cd frontend && npm test -- --run
# 13 test files passed, 40 tests passed

cd frontend && npm run build
# success; dist/build-info.json contains git_sha, build_time, source_hash

git status --short --ignored backend/secrets frontend/dist
# !! backend/secrets/
# !! frontend/dist/
```

## Compact Handoff

Phase 3 closure changed:

- `test_live_nubia.py` is now V1.1-aware and covers public health/watchdog,
  client config, frontend heartbeat, state/interactions, text/audio job,
  pet event, debug runs/incidents, deep health, and protected endpoint no-token
  boundaries.
- Protected endpoint inventory now has local regression coverage and minimal
  token gates for context debug/runs, memory debug/curate/summarize,
  runtime reset, and skill execution.
- `frontend/vite.config.ts` now includes `source_hash` in generated
  `dist/build-info.json`.
- `.gitignore` now ignores `backend/secrets/` as runtime secret material.

Tests:

- Targeted backend security/live tests: 39 passed, 21 skipped.
- Full backend suite: 525 passed, 24 skipped.
- Frontend tests: 40 passed.
- Frontend build: passed; `frontend/dist` remains ignored/untracked.

Nubia:

- Phase 3 remains provisional until final deployment updates Nubia to latest
  `origin/main` and runs the live test suite against `127.0.0.1:8000` or
  `192.168.10.239:8000` with the internal token available.

Next phase entry point:

- Phase 4 closure should review hardening follow-through after the expanded
  security gates, then final deployment should run the full live scenario set on
  the actual Nubia Android 6 device.
