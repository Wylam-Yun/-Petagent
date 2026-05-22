# Phase 1: Mobile-Safe Runtime + Recovery

> Stage plan for V1.1 Phase 1. Covers STAB-001, 005, 006, 007, 008, 009, 010, 013, 014, 015, 033, 036.

**Date:** 2026-05-21
**Scope:** Mobile-safe runtime, recovery, health, concurrency, frontend persistence.
**Estimated effort:** 5-7 days
**Depends on:** Phase 0 (provider errors, auth token, CORS)

---

## Authoritative Implementation Order

Per master plan Section "Phase 1 — Mobile-Safe Runtime + Recovery":

1. **STAB-015 / CC-6** — SQLite AudioJobStore
2. **STAB-006 / CC-4** — FastAPI lifespan skeleton (with failed_shutdown drain)
3. **STAB-036 / CC-3** — Health split (light / watchdog / deep)
4. **STAB-007** — App-level heavy-route concurrency gates
5. **STAB-008** — Startup/manager backoff using lifespan + watchdog
6. **STAB-001** — Frontend heartbeat, default-browser intent, bounded proactive scheduler
7. **STAB-005** — Dispatcher snapshot/commit split + STAB-010 provider gate
8. **STAB-009 / CC-5** — Maintenance background worker (wired into split dispatcher)
9. **STAB-033** — Manager watchdog-stuck detection
10. **STAB-013 / STAB-014** — Upload streaming + audio CPU fixes

---

## Task 1: STAB-015 / CC-6 — SQLite AudioJobStore

**Problem:** AudioJobManager stores jobs in memory only. On restart, frontend polls job IDs that no longer exist.

**Fix:**
1. Create `backend/app/runtime/audio_job_store.py` with `AudioJobStore` class following the `memory_store.py` pattern:
   - Constructor takes `connection` (LockedSQLiteConnection)
   - `_ensure_table()` creates `audio_job` table with columns matching `AudioJob` fields plus V1.1 persistence fields: `job_id TEXT PRIMARY KEY`, `run_id TEXT`, `event_id TEXT`, `session_id TEXT`, `status TEXT`, `text TEXT`, `voice_style TEXT`, `provider TEXT`, `voice_url TEXT`, `audio_path TEXT`, `error TEXT`, `error_class TEXT`, `failure_reason TEXT`, `timings_json TEXT`, `created_at TEXT`, `updated_at TEXT`, `completed_at TEXT`, `expires_at TEXT`, `superseded_by TEXT`
   - Indexes: `(status, created_at)`, `(session_id, status, created_at)`, `(run_id)`, `(event_id)`
   - Methods: `save(job)`, `get(job_id)`, `mark_status(job_id, status, **kwargs)`, `mark_restart_failed()`, `cleanup_expired(ttl_seconds)`, `count_by_status(status)`
2. Refactor `AudioJobManager` to write-through to SQLite:
   - Keep in-memory cache for fast reads (last 50 done jobs)
   - On `enqueue()`: write to SQLite + in-memory
   - On `_run_job()` status changes: update SQLite
   - On `get()`: check in-memory first, then SQLite
   - On startup: `UPDATE audio_job SET status='failed_runtime_restart', failure_reason='runtime_restarted' WHERE status IN ('pending', 'running')`
3. Update `backend/app/api/audio.py`:
   - When `get()` returns a job with `status='failed_runtime_restart'`, return 404 with `reason: "runtime_restarted"` instead of the job data.

**Files:**
- `backend/app/runtime/audio_job_store.py` (new)
- `backend/app/runtime/audio_jobs.py` (refactor)
- `backend/app/api/audio.py` (structured 404)
- `backend/app/main.py` (wire up store)

**Tests:**
- Schema contract test comparing persisted columns against AudioJob.dict() + V1.1 fields.
- Restart simulation: create pending/running rows, call `mark_restart_failed()`, verify status.
- Shutdown simulation: create pending row, call shutdown mark, verify `failed_shutdown`.
- Per-session supersede: older pending job becomes `superseded`, remains queryable after restart.
- Structured 404: poll a restart-failed job, verify `reason: "runtime_restarted"`.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "audio"`

---

## Task 2: STAB-006 / CC-4 — FastAPI Lifespan

**Problem:** No lifespan or shutdown hook. AudioJobManager executor is never shut down. In-flight jobs vanish on SIGTERM.

**Fix:**
1. Add `@asynccontextmanager async def lifespan(app)` in `backend/app/main.py`:
   - **Startup phase:** yield (app is ready)
   - **Shutdown phase:**
     - Set `app.state.shutdown_in_progress = True`
     - Call `audio_job_manager.shutdown()` — non-blocking executor shutdown
     - Mark all `pending`/`running` audio jobs as `failed_shutdown` in SQLite via `audio_job_store.mark_shutdown_failed()`
     - Stop maintenance worker (if exists, from Task 8)
     - Close SQLite connections via `state_store.close()`
     - Log shutdown reason and in-flight job counts
2. Update `AudioJobManager.shutdown()` to accept optional `drain_timeout_s` parameter. If provided, wait up to that duration for in-flight executor tasks before force-shutting down.
3. Add `AudioJobStore.mark_shutdown_failed()` method: `UPDATE audio_job SET status='failed_shutdown', failure_reason='process_shutdown' WHERE status IN ('pending', 'running')`.
2. Reject new `/api/voice/chat` and `/api/text/chat` when `shutdown_in_progress` is True (return 503 with `reason: shutting_down`).
3. Replace `app = FastAPI(...)` with `app = FastAPI(..., lifespan=lifespan)`.

**Files:**
- `backend/app/main.py`
- `backend/app/api/text.py` (shutdown gate)
- `backend/app/api/voice.py` (shutdown gate)

**Tests:**
- Integration test: send SIGTERM, verify graceful shutdown log + exit within 10s.
- Verify pending audio jobs are recorded as `failed_shutdown`.
- Verify new requests during shutdown get 503.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "shutdown or lifespan"`

---

## Task 3: STAB-036 / CC-3 — Health Split

**Problem:** `/api/health` returns only `{ok, name}`. No DB status, no watchdog counters, no provider state.

**Fix:**
1. Create `backend/app/api/health.py` with three endpoints:
   - **`GET /api/health`** (light, < 50ms): `{ok, name, version, build_hash, pid, started_at}`. No DB queries, no locks.
   - **`GET /api/health/watchdog`** (manager-safe, < 100ms): `{ok, core_ready, shutdown_in_progress, event_loop_tick_age_s, active_requests, agent_inflight_age_s, provider_inflight_age_s, audio_queue_depth, frontend_heartbeat_age_s}`. Reads only lock-free counters.
   - **`GET /api/health/deep`** (debug, token-protected, < 500ms): DB quick_check, WAL bytes, provider last status, audio backlog, candidate backlog, frontend heartbeat age.
2. Add lightweight counters to `RuntimeDispatcher`:
   - `event_loop_tick`: updated at start of `handle_event()`
   - `agent_inflight_start`: set when agent work begins, cleared when done
   - `active_requests`: incremented/decremented around event handling
3. Move the inline health route from `main.py` to the new router.
4. Register the health router in `main.py` before other routers.

**Files:**
- `backend/app/api/health.py` (new)
- `backend/app/main.py` (register router, remove inline health)
- `backend/app/runtime/dispatcher.py` (add counters)

**Tests:**
- Smoke test: `/api/health` returns < 50ms with expected fields.
- Smoke test: `/api/health/watchdog` returns < 100ms without acquiring dispatcher lock.
- Smoke test: `/api/health/deep` returns < 500ms with token, 403 without token.
- Counter test: after `handle_event()`, `event_loop_tick_age_s` is < 5.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "health"`

---

## Task 4: STAB-007 — App-Level Concurrency Gates

**Problem:** `run_in_threadpool()` offloads entire pipelines to Starlette's default threadpool. A few slow calls can consume all worker threads, starving health checks.

**Fix:**
1. Create `backend/app/runtime/concurrency.py` with:
   - `AgentWorkExecutor(max_workers=4, max_queue=8)` — bounded executor for text/voice pipelines.
   - `async submit_agent_work(fn, *args, timeout_s=120)` — submits to executor, returns 503 `{error_class: "server_busy"}` when queue is full.
2. In `text.py` and `voice.py`: replace `run_in_threadpool(...)` with `await submit_agent_work(...)`.
3. Do NOT gate: `/api/health`, `/api/health/watchdog`, `/api/health/deep`, `/api/runtime/client-config`, static files, audio job polling.
4. Update `scripts/start.sh` uvicorn args:
   ```
   --limit-max-requests 2000 --timeout-keep-alive 15 --timeout-graceful-shutdown 10 --backlog 32
   ```
   Do NOT add `--limit-concurrency` (can reject health checks).

**Files:**
- `backend/app/runtime/concurrency.py` (new)
- `backend/app/api/text.py`
- `backend/app/api/voice.py`
- `scripts/start.sh`

**Tests:**
- Saturated queue test: mock slow pipeline, fire N parallel requests, verify heavy routes return 503 when saturated, health remains responsive.
- Queue depth test: verify max_queue=8 is enforced.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "concurrency or busy"`

---

## Task 5: STAB-008 — Startup/Manager Backoff

**Problem:** Heavy synchronous startup can exceed health windows. Manager backs off 600s after failures. Momo can be dead for 10 minutes.

**Fix:**
1. In `main.py` lifespan startup: schedule heavy work (provider probes, memory card rebuild, summary warmup) as `asyncio.create_task()` background tasks. Core DB and stores are ready immediately.
2. Add `core_ready: bool` flag on `app.state`, set True after stores are initialized.
3. Add `providers_ready: bool` to deep health (set True after background probes complete).
4. In `scripts/termux_service_manager.sh`:
   - Call `/api/health` with `curl --connect-timeout 1 --max-time 2`
   - Call `/api/health/watchdog` with `--connect-timeout 1 --max-time 3`
   - During startup grace (process alive + `core_ready=false`): do NOT increment fail counter
   - Reduce `BACKOFF_SECONDS` from 600 to 120 for known recoverable startup states
   - Keep 600s for repeated hard process death

**Files:**
- `backend/app/main.py` (background startup tasks)
- `backend/app/api/health.py` (core_ready flag)
- `scripts/termux_service_manager.sh` (watchdog-aware health check)

**Tests:**
- Simulate slow provider probe: verify `/api/health` answers in < 1s.
- Manager test: simulate `core_ready=false`, verify no fail counter increment.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "startup or health"`

---

## Task 6: STAB-001 — Frontend Heartbeat + Browser Relaunch + Proactive Scheduler

**Problem:** Browser not persistent. No heartbeat. Proactive events only fire when browser polls.

**Fix:**
1. Add `POST /api/frontend/heartbeat` endpoint: stores `{last_seen_at, user_agent_hash}` in process counters.
2. Add `ProactiveScheduler` in backend (`backend/app/runtime/proactive_scheduler.py`):
   - Ticks independently of browser
   - Bounded queue of max 20 proactive events
   - Coalesces same-kind events in 15-min buckets
   - When `frontend_heartbeat_age_s > 90`: no LLM/TTS calls, only deterministic state hints
   - After restart: one `catch_up` event summarizing offline interval
3. In `scripts/termux_service_manager.sh`:
   - After backend health is ready, launch browser via Android intent:
     `am start -a android.intent.action.VIEW -d http://127.0.0.1:8000/`
   - If backend healthy but `frontend_heartbeat_age_s > 90`: attempt one browser relaunch per cooldown
   - `FRONTEND_STARTUP_SECONDS=120s`
4. Frontend: add heartbeat POST every 30s (in `App.tsx`).

**Files:**
- `backend/app/runtime/proactive_scheduler.py` (new)
- `backend/app/api/frontend.py` (new)
- `backend/app/api/health.py` (heartbeat counter)
- `scripts/termux_service_manager.sh` (browser relaunch)
- `frontend/src/App.tsx` (heartbeat)

**Tests:**
- Scheduler: bounded queue never exceeds 20, same-kind events coalesce.
- Stale heartbeat: scheduler suppresses provider/TTS calls when no frontend.
- Manager: stale heartbeat triggers browser relaunch path.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "proactive or heartbeat"`

---

## Task 7: STAB-005 + STAB-010 — Dispatcher Snapshot/Commit Split + Provider Gate

**Problem:** Single `_event_lock` serializes all events including slow LLM/TTS calls. One 60s call blocks everything.

**Fix (incremental, versioned commit):**
1. **Prerequisite:** Add `version INTEGER NOT NULL DEFAULT 0` column to `pet_state` table via `_ensure_column()` migration in `PetStateStore.initialize()`. Load/save methods must read/write this column. Increment version on each save.
2. Split `handle_event()` into three phases:
   - **Locked snapshot:** acquire lock, read state + version, reserve event_id/run_id, apply tick, release lock.
   - **Slow work outside lock:** route policy, LLM, provider calls, audio understanding, tool planning. Use immutable snapshot.
   - **Locked commit:** re-acquire lock, CAS on version (`WHERE version = expected_version`), commit state delta, record event/run, enqueue audio job. If CAS fails (version changed), re-read state and recompute deterministic deltas once, then retry CAS.
3. Side-effect map (from master plan):
   - Snapshot: read state, reserve IDs, apply tick
   - Outside lock: route policy, LLM, context, skills (read-only), construct delta
   - Commit: CAS state, write event/run, enqueue audio job
   - After commit: enqueue persisted audio job, notify maintenance worker (Task 8)
4. Add `ProviderGate` in `concurrency.py`: cap external provider concurrency (`llm_fast=2, llm_slow=1, asr=1, tts=2, audio_understanding=1`). When gate full, fast paths return `error_class: "provider_busy"`.

**Files:**
- `backend/app/runtime/dispatcher.py` (major refactor)
- `backend/app/runtime/concurrency.py` (ProviderGate)
- `backend/app/pet/state.py` (version column migration)

**Tests:**
- Existing dispatcher tests must still pass.
- Concurrency test: simultaneous events, state deltas applied exactly once.
- CAS test: concurrent state writes don't lose updates.
- Provider gate test: 10 slow calls, verify health remains responsive.
- Version migration test: existing DB gets version column added.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q`

---

## Task 8: STAB-009 / CC-5 — Maintenance Background Worker

**Depends on:** Task 7 (dispatcher split). The worker is wired into the post-commit phase of the split dispatcher.

**Problem:** Every `handle_event()` creates a new daemon thread for maintenance. Thread creation overhead on Android 6.

**Fix:**
1. Create `backend/app/runtime/maintenance_worker.py` with `MaintenanceWorker`:
   - Single long-lived thread named `petagent-maintenance`
   - Fed by `queue.Queue(maxsize=1)` — notifications coalesce
   - `notify()` method: puts to queue (non-blocking, drops if full)
   - Loop: `q.get(timeout=300)` → calls `maintenance_service.tick()` → sleep until next slot
   - Wall-clock fallback: tick every 5 minutes regardless of notifications
   - `stop()` method: sets shutdown flag, joins thread with timeout
2. In `dispatcher.py`: in the post-commit phase (from Task 7), replace `threading.Thread(target=...).start()` with `worker.notify()`.
3. In `main.py`: create `MaintenanceWorker`, start it, pass to dispatcher. Stop in lifespan shutdown.

**Files:**
- `backend/app/runtime/maintenance_worker.py` (new)
- `backend/app/runtime/dispatcher.py` (replace thread spawn in post-commit)
- `backend/app/main.py` (wire up worker, stop in lifespan)

**Tests:**
- Stress test: fire 100 events in 5s, assert thread count stays constant.
- Worker stop test: verify clean shutdown within 5s.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "maintenance"`

---

## Task 9: STAB-033 — Manager Watchdog-Stuck Detection

**Problem:** Manager restarts on HTTP health failure but doesn't detect stuck states (process alive, port listening, but agent loop wedged).

**Fix:**
1. Define `STUCK` state from watchdog counters:
   - `agent_inflight_age_s > 90`
   - `event_loop_tick_age_s > 90`
   - `provider_inflight_age_s > configured_timeout + 30`
2. In `scripts/termux_service_manager.sh`:
   - After light health passes, call `/api/health/watchdog`
   - Parse watchdog JSON for stuck indicators
   - Maintain `STUCK_COUNT` variable (file-based persistence across manager restarts)
   - Increment on stuck detection, reset on healthy
   - Restart runtime after 3 consecutive stuck cycles
   - Separate from the existing `FAIL_COUNT` (process/port death)
3. Manager restart on stuck uses existing backoff logic but shorter (120s vs 600s).

**Files:**
- `scripts/termux_service_manager.sh`
- `backend/app/api/health.py` (watchdog counters already added in Task 3)

**Tests:**
- Manager script test: simulate stale watchdog counters, assert restart after 3 consecutive stuck cycles.
- Simulate one slow watchdog response, assert no restart.

**Verify:** Manual Nubia test: hold provider work outside dispatcher lock, confirm manager observes STUCK.

---

## Task 10: STAB-013 / STAB-014 — Upload Streaming + Audio CPU Fix

**Problem:** Voice upload reads entire file into RAM (8MB). Empty-audio detection scans all frames in Python.

**Fix:**
1. **STAB-013:** Replace `await file.read()` + `path.write_bytes(data)` in `_save_upload()` with chunked streaming:
   ```python
   total = 0
   limit = max_audio_bytes(settings)
   with path.open("wb") as out:
       while True:
           chunk = await file.read(64 * 1024)
           if not chunk: break
           total += len(chunk)
           if total > limit:
               out.close()
               path.unlink(missing_ok=True)
               raise HTTPException(413, "Audio file is too large")
           out.write(chunk)
   ```
2. **STAB-014:** Replace per-sample loop in `is_probably_empty_audio()` with sampled RMS over up to 16 windows of 4096 frames. Use `audioop.rms` if available. Cap total frames at 64k.

**Files:**
- `backend/app/api/voice.py`
- `backend/app/providers/audio_omni.py`

**Tests:**
- 9MB upload returns 413 without OOM.
- 8MB upload saves correctly.
- Empty-audio detection < 50ms on 8MB WAV.
- Known-silent and known-speech samples detected correctly.

**Verify:** `cd backend && ../.venv/bin/python -m pytest tests/ -q -k "audio or upload"`

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
ssh nubia 'curl -s http://127.0.0.1:8000/api/health/watchdog'
# Burst upload test: check RSS stays < 80MB
# Reboot phone: confirm browser relaunch within 120s
# Kill -9 runtime: confirm audio jobs marked failed on restart
```

---

## Rollback Notes

- Each task is independently revertable.
- STAB-005 (dispatcher split) has highest risk — behind config flag if needed.
- STAB-001 (proactive scheduler) is additive — can be disabled without breaking existing flow.
- Health endpoints are additive — old `/api/health` behavior preserved.

---

## Commit Boundary

One commit per task group:
1. STAB-015 + STAB-006 (AudioJobStore + lifespan)
2. STAB-036 + STAB-007 + STAB-008 (health + concurrency + startup)
3. STAB-001 (heartbeat + scheduler + browser relaunch)
4. STAB-005 + STAB-010 (dispatcher split + provider gate)
5. STAB-009 (maintenance worker)
6. STAB-033 (manager watchdog-stuck detection)
7. STAB-013 + STAB-014 (upload + audio CPU)
