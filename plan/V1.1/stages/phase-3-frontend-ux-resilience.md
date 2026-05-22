# Phase 3: Frontend UX Resilience — Stage Plan

**Date:** 2026-05-22
**Depends on:** Phase 0, 1, 2 complete
**Target:** Nubia NX531J, Android 6.0.1, Termux, ~200MB RAM, no swap

## Scope

STAB-016, 028, 030, 031.
See master plan at `plan/V1.1/fix-spec-plan.md` lines 1054–1132.

## Tasks (authoritative order)

1. **STAB-016**: Frontend audio wait timing + progressive copy
2. **STAB-028**: Tick decay logistic curve
3. **STAB-030**: Frontend online/offline recovery
4. **STAB-031**: Frontend dist version tracking (build-info.json)

## Key Files

### New files
- `backend/app/api/client_config.py` (new — public client config endpoint)
- `frontend/src/hooks/useNetworkState.ts` (new — online/offline hook)
- `frontend/src/hooks/useClientConfig.ts` (new — fetch client config on load)
- `frontend/dist/build-info.json` (generated at build time)

### Modified files
- `backend/app/runtime/tick.py` (logistic decay curve)
- `backend/app/main.py` (register client_config router, read build-info)
- `backend/app/api/health.py` (expose build_hash in light health)
- `frontend/src/App.tsx` (progressive copy, online/offline banner, retry button)
- `frontend/src/pet/api.ts` (request timeout + retry, client config fetch)
- `frontend/vite.config.ts` (build-info plugin)
- `frontend/src/App.test.tsx` (update tests)

### Test files
- `backend/tests/test_phase3_tick.py` (logistic decay curve)
- `backend/tests/test_phase3_client_config.py` (client config endpoint)
- `frontend/src/App.test.tsx` (updated)

## Task Details

### Task 1: STAB-016 — Frontend audio wait timing + progressive copy

**Problem:** Frontend `waitForReadyAudio` waits 15s but backend may need 30s+ (primary TTS timeout 30s, fallback 60s). Users see premature "audio job timed out" errors.

**Fix:**
1. New `GET /api/runtime/client-config` endpoint returns public config:
   ```json
   {
     "audio_wait_ms": 90000,
     "audio_progressive": {
       "0": "Momo 准备声音…",
       "5000": "Momo 有点慢，再等一下…",
       "30000": "声音可能要再等一会儿…"
     }
   }
   ```
   No provider keys, proxy, DB, or incident data exposed.

2. Frontend fetches config once on app load via `useClientConfig` hook.

3. `waitForReadyAudio` uses config timeout instead of hardcoded 15s.

4. Progressive copy: bubble text updates at thresholds from config.

5. Add "重试发声" (retry voice) button that re-fetches the audio job when timeout occurs.

**Files:** `backend/app/api/client_config.py`, `backend/app/main.py`, `frontend/src/App.tsx`, `frontend/src/pet/api.ts`, `frontend/src/hooks/useClientConfig.ts`

**Verify:** Vitest mock that backend stalls 20s, assert progressive copy appears. API test asserts `/api/runtime/client-config` contains no sensitive fields.

### Task 2: STAB-028 — Tick decay logistic curve

**Problem:** Linear decay pushes Momo to extremes (energy=0, hunger=100) too quickly. After 12h idle, Momo is starving and exhausted.

**Fix:** In `tick_service.apply_if_due()`:
1. Replace linear decay with logistic/saturating curve:
   - `delta = base * (1 - current/100)` for negative effects (energy↓, hunger↑, loneliness↑)
   - Decay slows as state nears the edge (energy=10 → very slow further decay)
2. Add "rest while away" bonus: if `idle > 6h` and `energy < 50`, recover energy by `+min(20, idle_hours / 3)`
3. Charging signal accelerates rest recovery (already partially done, just tune)

**Files:** `backend/app/runtime/tick.py`, `backend/app/pet/state.py` (state delta helpers)

**Verify:** Snapshot test over 24h idle (48 intervals), assert energy never reaches 0 without interaction, assert loneliness doesn't pin at 100 forever.

### Task 3: STAB-030 — Frontend online/offline recovery

**Problem:** Frontend doesn't detect or react to network changes. Wi-Fi drop → silent failures, no reconnection attempt.

**Fix:**
1. New `useNetworkState()` hook:
   - Listens to `navigator.onLine`, `online`/`offline` events
   - Returns `{ isOnline: boolean }`
2. Show "正在重新连接 Momo…" banner during offline
3. Polling (heartbeat, proactive check) pauses while offline
4. On return to online, resume polling immediately. Note: STAB-027 (`POST /api/pet/session/resume`) is Phase 4 scope; for Phase 3, just resume polling and let the next tick apply decay.
5. `requestJson()` adds 8s timeout + 2 retries with exponential backoff (matching master spec)

**Files:** `frontend/src/hooks/useNetworkState.ts`, `frontend/src/App.tsx`, `frontend/src/pet/api.ts`

**Verify:** Vitest with mocked offline/online events, assert banner appears/disappears, polling pauses/resumes.

### Task 4: STAB-031 — Frontend dist version tracking

**Problem:** No way to know which frontend build is deployed. Debugging mismatched frontend/backend versions is hard.

**Fix:**
1. Vite plugin writes `frontend/dist/build-info.json` at build time:
   ```json
   {
     "git_sha": "abc1234",
     "build_time": "2026-05-22T10:00:00Z",
     "source_hash": "sha256-of-src"
   }
   ```
2. Backend reads `build-info.json` on startup, exposes via `/api/health` as `build_hash` field.
3. Frontend reads build-info on load, can show in debug panel.

**Files:** `frontend/vite.config.ts`, `backend/app/main.py`, `backend/app/api/health.py`, `scripts/start.sh` (warn if build-info missing/stale)

**Note on dist/ gitignore:** Master plan discusses committing `dist/` to lock deployed bundle to source. For V1.1, we will NOT commit `dist/` (too much repo bloat). Instead, `scripts/start.sh` warns if missing or stale. A nightly CI build is the better long-term solution.

**Verify:** Build runs, build-info.json present, health endpoint returns SHA.

## Verification

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest -q
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- --run
npm run build
ssh nubia 'curl -s http://127.0.0.1:8000/api/health'
```

## Risks

- Progressive copy thresholds may feel too slow or too fast. Tunable via config.
- Logistic decay must still feel "alive". Tune in field.
- `build-info.json` not present if frontend not built. Backend must handle gracefully.
- `useNetworkState` may not fire on all Android 6 browsers. Fallback: heartbeat timeout detection.
