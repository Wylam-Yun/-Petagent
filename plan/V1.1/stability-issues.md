# PetAgent V1.1 Stability And Engineering Issues

> Status: problem inventory only. No code changes are included in this document.

**Date:** 2026-05-20

**Goal:** Collect the stability, recovery, runtime, and product-readiness issues found while auditing PetAgent / Momo on the actual Nubia Android 6 runtime.

**Primary runtime:** Nubia NX531J, Android 6.0.1, Termux, FastAPI backend on `127.0.0.1:8000`, browser frontend served from `frontend/dist`.

---

## Field Snapshot

Observed on Nubia:

- Android: `6.0.1`, SDK 23, Nubia NX531J.
- Backend health: `/api/health` returns ok, `uvicorn` is running.
- PetAgent process: about `32MB` RSS, `2` threads, `10` file descriptors.
- System pressure: available memory around `200MB`, no swap, load average around `7-8`.
- Termux: partial wakelock is held, Termux is in Doze whitelist.
- Device state: `device_state` table is empty, so charging/battery-aware recovery is not currently active.
- Frontend: no browser/WebView/Via process was running during inspection; foreground Activity was Termux.
- SQLite: `pet.db` is small, `pet.db-wal` was about `1.9MB`, `wal_autocheckpoint=1000`.
- Runtime logs: no recent backend traceback after the current runtime stabilized.

Interpretation: the backend can stay alive, but the product is not yet a robust always-on desktop pet. The biggest risks are old Android system pressure, frontend non-persistence, hidden provider failures, slow request serialization, and weak recovery/observability.

---

## P0 / P1 Issues

### STAB-001: Frontend Desktop Pet Is Not Actually Persistent

The current proactive companionship loop lives in the browser frontend:

- `frontend/src/App.tsx`: `setInterval(..., 30_000)` polls `/api/pet/proactive`.
- Battery reporting also lives in the browser via Battery API.

Field observation showed no browser/WebView/Via process and foreground Activity was Termux. That means:

- backend is alive, but Momo is not visibly living on the desktop;
- proactive events do not fire unless the page remains open;
- battery/charging state may never be reported.

Impact: high. This directly affects the "long-term companion living on an old phone" goal.

Suggested direction:

- decide whether frontend must be kept foreground manually, kiosk-style, or via Android-side service/automation;
- make backend capable of lightweight proactive scheduling independent of frontend polling;
- add a visible "frontend heartbeat" or `/api/health` field showing whether the browser has checked in recently.

### STAB-002: MiMo Audio Understanding Uses The Wrong API Key

`audio_understanding` has its own `MIMO_API_KEY`, but `MiMoAudioUnderstandingProvider` checks and sends `settings.api_key`.

Relevant code:

- `backend/app/config.py`: global `api_key` is derived from TTS/LLM provider env names.
- `backend/app/providers/audio_omni.py`: `settings.api_key` is used for MiMo audio requests.

Field verification:

- SiliconFlow key against MiMo audio endpoint returned `401`.
- MiMo key against MiMo audio endpoint returned `200`.

Impact: high. Slow/fallback voice understanding silently becomes "uncertain / not heard", harming emotion and tone understanding.

Suggested direction:

- use `settings.audio_understanding.api_key`;
- expose provider error class in route info;
- add a smoke test where `SILICONFLOW_API_KEY != MIMO_API_KEY`.

### STAB-003: Route Policy Says Slow, But Actual Brain May Still Be Fast

Route policy can classify a complex text as slow, but `TextPipeline` selects brain only from `thinking_mode`.

Relevant code:

- `backend/app/runtime/route_policy.py`: complex keywords return `route="slow"`.
- `backend/app/runtime/text_pipeline.py`: `brain = slow_brain if thinking_mode else fast_brain`.
- `backend/app/runtime/dispatcher.py`: route decision is observability/policy, not the actual selected provider.

Observed behavior in a test request:

- runtime metadata said `route=slow`, `provider=slow_llm`;
- `text_route` said actual provider was fast.

Impact: high. Observability is misleading and complex tasks may not actually use the deep path.

Suggested direction:

- centralize route decision before selecting the brain;
- ensure `route_info` and `runtime` describe the same provider;
- add tests for long-task keywords without manual thinking mode.

### STAB-004: Thinking Voice Path Still Starts With ASR

README describes slow/thinking voice mode as direct audio understanding, but `VoicePipeline.handle()` still calls `_run_asr_route()` first. If ASR succeeds, emotion is set to `uncertain` and tone notes say "fast ASR route only".

Relevant code:

- `backend/app/runtime/voice_pipeline.py`: thinking route still runs ASR path.

Impact: high for the "sound-based AI pet" goal. Momo may hear text but lose tone, sighs, laughter, silence, and emotional nuance.

Suggested direction:

- make thinking voice mode use audio understanding first;
- optionally keep ASR as a transcript assist, not as the only primary route;
- report whether tone/emotion came from ASR or audio understanding.

### STAB-005: A Single Dispatcher Lock Serializes All Events

`RuntimeDispatcher.handle_event()` uses one `RLock` around the entire event loop.

Relevant code:

- `backend/app/runtime/dispatcher.py`: `with self._event_lock`.

Any slow LLM/tool/provider call holds the event lock. Voice, text, touch interactions, context refresh, and proactive events then line up behind it.

Impact: high. A single 60s slow provider call can make the whole pet unresponsive. Under Starlette's default threadpool, this can also contribute to health check starvation during bursts.

Suggested direction:

- make DB state mutation serialized, not the full LLM/provider call;
- split event planning/generation from commit phase;
- add a short, lock-free health endpoint that never waits on the agent loop.

### STAB-006: FastAPI Has No Lifespan Or Shutdown Hook

The app does not define `lifespan` or `@app.on_event("shutdown")`. `AudioJobManager` owns a `ThreadPoolExecutor`, but it is not explicitly shut down.

Relevant code:

- `backend/app/main.py`: creates `AudioJobManager`.
- `backend/app/runtime/audio_jobs.py`: executor is created and has `shutdown()`.

Impact: medium-high. On SIGTERM or manager restart, in-flight TTS jobs and daemon maintenance threads can be hard killed. SQLite WAL should recover, but repeated abrupt shutdowns increase risk and make pending jobs vanish.

Suggested direction:

- add lifespan startup/shutdown;
- call `audio_job_manager.shutdown()`;
- stop accepting new jobs during shutdown;
- record shutdown reason and in-flight job counts.

### STAB-007: Uvicorn Runs Without Mobile-Safe Limits

`scripts/start.sh` runs raw uvicorn without limits.

Relevant code:

- `scripts/start.sh`: `python -m uvicorn app.main:app --host "$HOST" --port "$PORT"`.

Missing:

- `--limit-concurrency`;
- `--timeout-keep-alive`;
- `--limit-max-requests`;
- worker/process memory policy.

Impact: high on Android 6 with about 200MB available memory. A burst of uploads or slow requests can consume too many threads/connections and invite LMK kills.

Suggested direction:

- set conservative concurrency and keep-alive limits;
- consider a small request queue and explicit 503 when saturated;
- expose current active request count.

### STAB-008: Startup Path Is Heavy And Manager Backoff Can Create Long Death Windows

Startup builds the whole app synchronously: settings, DB schema/migrations, memory stores, cards, providers, audio job manager, static mount. On a loaded old phone this can exceed health windows.

Relevant code:

- `backend/app/main.py`: `create_app()`.
- `scripts/start.sh`: waits up to 120 seconds.
- `scripts/termux_service_manager.sh`: backs off for 600 seconds after repeated failures.

Impact: high. Manager logs previously showed alternating "runtime ready" and "health check timed out after 120s". Worst case, Momo can be dead for about 10 minutes.

Suggested direction:

- make `/api/health` available as early as possible;
- move expensive provider probes/cards rebuild into background startup tasks;
- separate "process is alive", "core DB ready", and "providers ready" health states;
- reduce backoff for known recoverable startup states.

---

## Runtime And Scheduling Issues

### STAB-009: Maintenance Starts A New Thread After Every Event

Every `handle_event()` creates a new daemon thread for maintenance.

Relevant code:

- `backend/app/runtime/dispatcher.py`: `threading.Thread(target=...).start()`.

Maintenance has a single-flight lock, so duplicate work is skipped, but thread creation itself still costs CPU and scheduling overhead on Android 6.

Impact: medium. During rapid interaction or load spikes, these threads are noise and can worsen latency.

Suggested direction:

- use one background maintenance worker;
- trigger it with an event/queue;
- add backpressure and named threads.

### STAB-010: Provider Calls Are Synchronous And Occupy Worker Threads

Providers use blocking `requests` calls. API routes offload voice/text to Starlette's threadpool, and provider calls can hold those threads for up to provider timeout.

Relevant code:

- `backend/app/providers/llm_mimo.py`
- `backend/app/providers/tts_mimo.py`
- `backend/app/providers/asr_http.py`
- `backend/app/providers/audio_omni.py`

Impact: medium-high. A few slow calls can consume worker threads and indirectly delay other requests.

Suggested direction:

- use shorter connect/read timeouts;
- move slow provider work to bounded internal executors;
- return explicit "busy" or queued state when saturated.

### STAB-011: No Circuit Breaker Or Provider Backoff

Fallback currently waits for the primary provider to fail every time. There is no provider health state, cool-down, or "skip known bad primary" period.

Relevant code:

- `FallbackLLMProvider`
- `FallbackTTSProvider`

Impact: medium-high. If a primary provider is down, every request first pays the full timeout tax.

Suggested direction:

- record provider failures by class;
- temporarily open a circuit after repeated timeout/401/5xx;
- expose circuit state in health/debug endpoints.

### STAB-012: Network Switches Can Stall Until Long Timeouts

Old Android Wi-Fi/network switches may leave sockets hanging. `requests` will wait until timeout. Current provider timeouts range up to 60s or 120s.

Impact: medium-high for voice responsiveness.

Suggested direction:

- use `(connect_timeout, read_timeout)` tuples;
- prefer 5-10s plus one retry for fast paths;
- keep long timeout only for explicit deep/thinking operations.

---

## Voice, Audio, And Upload Issues

### STAB-013: Voice Upload Reads Entire File Into RAM

`_save_upload()` does `await file.read()` and then `path.write_bytes(data)`.

Relevant code:

- `backend/app/api/voice.py`.

Impact: medium-high. The configured limit is 8MB. Multiple concurrent uploads can consume memory quickly on a phone with about 200MB available memory.

Suggested direction:

- stream upload to disk in chunks;
- reject as soon as cumulative bytes exceed limit;
- optionally use a lower mobile limit.

### STAB-014: Empty-Audio Detection Scans Entire WAV In Python

`is_probably_empty_audio()` reads all frames and loops over every 16-bit sample in Python.

Relevant code:

- `backend/app/providers/audio_omni.py`.

Impact: medium. On an 8MB WAV this can become seconds of pure CPU on old hardware.

Suggested direction:

- sample windows instead of scanning all frames;
- cap frames inspected;
- compute RMS/peak using `audioop` or array-based processing if available.

### STAB-015: AudioJobManager Is Memory-Only

Pending TTS jobs live only in process memory.

Relevant code:

- `backend/app/runtime/audio_jobs.py`.

Impact: high for restarts. If the process is killed/restarted after a text/voice response enqueues TTS, the frontend keeps polling an `audio_job_id` that no longer exists.

Suggested direction:

- persist jobs to SQLite;
- on startup mark old pending jobs as failed/recoverable;
- return structured 404 reason like `runtime_restarted`.

### STAB-016: Frontend Waits 15s For Audio While Backend May Need Much Longer

Frontend waits up to 15 seconds for audio jobs. Backend TTS primary and fallback can take much longer.

Relevant code:

- `frontend/src/App.tsx`: `waitForReadyAudio()`.
- `config/models.yaml`: TTS primary/fallback timeouts.

Impact: medium-high. User sees "sound did not come out" even if audio later succeeds.

Suggested direction:

- align frontend wait with backend job timeout profile;
- add progressive states like "voice is slow today";
- let user retry playback if job finishes late.

### STAB-017: Wake/Exit Phrases Fail When ASR Fails

Wake/exit detection uses `understanding.user_text`. If ASR fails and audio fallback also returns empty, `_classify_activation("")` cannot detect wake/exit.

Relevant code:

- `backend/app/runtime/voice_pipeline.py`.

Impact: medium-high. In weak network conditions, "Momo" may not wake Momo.

Suggested direction:

- add local/simple wake phrase support where possible;
- keep wake/exit path separate from full ASR;
- treat low-confidence wake-like audio differently from normal chat.

### STAB-018: Upload Validation Only Checks Content-Type And Size

The upload path trusts MIME content type and file size. It does not validate magic bytes or basic WAV structure before provider calls.

Impact: medium. Bad input can waste ASR/provider latency and quota.

Suggested direction:

- validate WAV header when content type says WAV;
- reject unsupported/invalid files before provider calls;
- include structured error response.

---

## Provider Observability Issues

### STAB-019: Provider Exceptions Are Silently Swallowed

Many provider errors collapse into `None` or fallback objects:

- LLM fallback catches all exceptions.
- TTS returns `None`.
- Audio understanding returns fallback uncertain result.

Impact: high for operations. `401`, timeout, bad JSON, provider quota, and network down look identical to the user and often to logs.

Suggested direction:

- define provider error classes;
- return sanitized error codes into route metadata;
- log provider name, status code, timeout class, and latency without secrets.

### STAB-020: No Startup Provider Key Probe

The app does not asynchronously check whether configured provider keys/base URLs/models are valid at startup.

Impact: medium-high. First user interaction discovers key expiry, model removal, quota failure, or proxy problems.

Suggested direction:

- add async/lazy provider probes after app starts;
- expose `last_success_at`, `last_error_class`, `model_available` in health/debug;
- keep probes lightweight and non-blocking.

### STAB-021: API Failure Response Lacks Structured Error Class

Voice/text requests usually return a normal pet response, even when ASR/LLM/TTS failed internally. Frontend gets little signal beyond missing `voice_url` or generic fallback text.

Impact: medium. UX copy cannot distinguish "did not hear", "could not think", "could not speak", or "network down".

Suggested direction:

- add `error_class`: `asr_failed`, `llm_failed`, `tts_failed`, `network_down`, `provider_auth_failed`;
- keep pet-friendly reply but include machine-readable diagnostics.

---

## Data And Persistence Issues

### STAB-022: WAL Has No Periodic Checkpoint Strategy

SQLite is in WAL mode. Field WAL was about `1.9MB`, below default auto-checkpoint threshold, but long-running low-write systems can keep WAL around for a long time.

Impact: medium over long runs. Read latency and recovery time can drift upward.

Suggested direction:

- checkpoint periodically, for example every N writes or every X minutes;
- prefer `PRAGMA wal_checkpoint(TRUNCATE)` during idle;
- report WAL size in debug/health.

### STAB-023: No Routine Rolling DB Backup

The DB is quarantined only when startup quick_check fails.

Impact: medium-high. If main DB and WAL are both damaged, there may be no recent good copy.

Suggested direction:

- create daily or N-interaction SQLite backups;
- keep a small rolling window;
- backup via SQLite backup API, not raw file copy while DB is hot.

### STAB-024: AgentRunRegistry Is Memory-Only

Recent agent run metadata is lost on process restart.

Relevant code:

- `backend/app/runtime/agent_run.py`.

Impact: medium. Postmortem debugging after a crash/restart has no run history.

Suggested direction:

- persist recent runs and key timings/errors to SQLite;
- keep payloads sanitized and bounded.

### STAB-025: Memory Candidate Errors Are Not Retried

If the curator LLM fails, candidates are marked `error`.

Relevant code:

- `backend/app/runtime/memory_curator.py`.

Impact: high for memory reliability. Network/provider failure can permanently drop important "remember this" content.

Suggested direction:

- add retryable status and attempt count;
- distinguish validation rejection from provider failure;
- keep explicit memory commands durable until processed or user clears them.

### STAB-026: Memory Card Rebuild Needs Explicit Locking Review

`MemoryCardManager.rebuild()` writes card files atomically via temp file and replace, which is good. But rebuild can be triggered from multiple paths, and there is no explicit manager-level lock.

Impact: low-medium. Concurrent rebuilds should usually end safely due to atomic replace, but output ordering can be nondeterministic.

Suggested direction:

- add an internal `RLock`;
- serialize rebuild/clear/read-with-provenance if needed;
- add a concurrency test.

---

## State And Pet Experience Issues

### STAB-027: `GET /api/pet/state` Has Side Effects

Reading state applies time decay.

Relevant code:

- `backend/app/api/pet.py`: `get_pet_state()` calls `tick_service.apply_if_due()`.

Impact: high for UX. Merely opening the page can push Momo to extreme tired/lonely states after idle time.

Suggested direction:

- separate `GET state` from `POST tick` or `POST session/resume`;
- make resume decay gentler and explainable;
- cap loneliness/energy changes per visible session.

### STAB-028: Tick Decay Can Push Momo To Extremes

Tick caps intervals at 12, but each interval can add loneliness and subtract energy. Long idle plus no device charging state can drive `energy=0`, `loneliness=100`.

Impact: high for "养宠感". It can feel punitive rather than alive.

Suggested direction:

- use nonlinear decay with soft caps;
- make "rested while away" possible;
- account for time of day and charging from Android/Termux, not only frontend.

### STAB-029: Pet Effort May Double-Deduct Energy

Dispatcher applies LLM `state_delta` and then force-applies pet effort fatigue.

Relevant code:

- `backend/app/runtime/dispatcher.py`.

Impact: medium. If the LLM already deducted energy, medium/high effort can double count.

Suggested direction:

- make effort-to-state mapping deterministic outside LLM;
- ask LLM for `state_affect` only, not numeric deltas for energy;
- or clearly tell the LLM not to include effort fatigue in `state_delta`.

---

## Frontend And Deployment Issues

### STAB-030: Frontend Has No Explicit Online/Offline Recovery State

`requestJson()` throws generic errors. The app catches many failures and changes bubble text, but there is no explicit offline banner, retry policy, or reconnect state.

Impact: medium. During Wi-Fi drops, users get generic "try again" behavior rather than clear recovery.

Suggested direction:

- listen to `online`/`offline`;
- add request timeouts and retry/backoff for polling;
- show a pet-like reconnecting state.

### STAB-031: Frontend Dist Is Not Tied To Source Version

`frontend/dist` is ignored by git. The phone can serve a bundle built from an older source state.

Impact: medium-high. Fixes may be deployed to source but not to the actual browser artifact.

Suggested direction:

- add build/deploy step that always rebuilds dist on phone or copies verified dist;
- expose frontend build hash in `/api/health` or page;
- fail startup or warn if dist is missing/stale.

### STAB-032: CORS Configuration Is Both Broken And Too Open

FastAPI is configured with `allow_origins=["*"]` and `allow_credentials=True`.

Relevant code:

- `backend/app/main.py`.

Impact:

- browser spec rejects wildcard origin with credentials;
- LAN malicious pages can call open APIs if no auth is added.

Suggested direction:

- define explicit allowed origins;
- add local pairing/token for unsafe operations;
- protect reset/debug endpoints.

---

## Service Manager And Android Operations

### STAB-033: Service Manager Does Not Restart Some Deep-Stuck States

Current manager intentionally keeps the runtime if process and port are alive even when HTTP health fails. This avoids restart storms, but a wedged app can remain wedged.

Relevant code:

- `scripts/termux_service_manager.sh`.

Impact: medium. Stable-but-dead states may not self-heal.

Suggested direction:

- distinguish startup grace, slow health, and sustained unhealthy;
- restart only after repeated independent health failures;
- include a "light health" endpoint that cannot block on agent work.

### STAB-034: Proxy Is Started Once But Not Supervised

`start_proxy_once()` runs only at manager start.

Impact: medium. If `mihomo` or port `7897` dies later, provider calls using proxy can degrade until manual intervention.

Suggested direction:

- check proxy port on each manager loop;
- optionally test a lightweight external endpoint;
- restart proxy with backoff if down.

### STAB-035: Logs Are Fragmented And Partly Outside Project

Runtime log is in `backend/data/logs/runtime.log`; manager logs are in home dotfiles. `~/Petagent/logs` is empty.

Impact: low-medium. Debugging requires knowing multiple paths.

Suggested direction:

- document log paths;
- optionally symlink or centralize logs under `backend/data/logs`;
- add log rotation for runtime log, not only manager log.

---

## Health And Observability Gaps

### STAB-036: `/api/health` Is Too Shallow

Current health only returns `{ok, name}`. It does not check:

- DB quick status;
- WAL size;
- provider last status;
- frontend bundle hash;
- audio job backlog;
- memory candidate backlog;
- proxy status;
- frontend heartbeat.

Impact: medium-high. Manager and user both see "healthy" when important subsystems may be stale.

Suggested direction:

- keep `/api/health` light and non-blocking;
- add `/api/health/deep` or `/api/runtime/status`;
- never let deep health block basic manager liveness.

### STAB-037: No Production Incident Breadcrumbs

Provider errors, route decisions, audio job failures, memory curator failures, and restart reasons are not persisted in a durable, queryable way.

Impact: medium. "Momo stopped speaking" is hard to diagnose after the fact.

Suggested direction:

- create bounded `runtime_incident` or `runtime_metric` table;
- persist sanitized error classes and timings;
- expose last N incidents in debug mode.

---

## Suggested Fix Order

1. Fix MiMo audio key usage and add provider error classes.
2. Make route decision select the actual brain/provider for text and voice.
3. Decouple `/api/pet/state` read from aggressive tick decay.
4. Add mobile-safe uvicorn limits and a non-blocking light health endpoint.
5. Add FastAPI lifespan shutdown for audio jobs and maintenance.
6. Replace per-event maintenance thread creation with one bounded worker.
7. Persist audio jobs and recent agent run metadata.
8. Add memory candidate retry for provider failures.
9. Add provider probes, circuit breaker, and shorter fast-path timeouts.
10. Make proactive/frontend heartbeat explicit and decide how the browser stays alive.
11. Add WAL checkpoint and rolling DB backups.
12. Add build hash/deploy verification for `frontend/dist`.
13. Harden upload streaming and audio validation.
14. Add auth/pairing and correct CORS policy before user-facing distribution.

---

## Verification Commands Used During Audit

Representative commands:

```bash
ssh nubia 'curl -sS --max-time 5 http://127.0.0.1:8000/api/health'
ssh nubia 'ps -A -o pid,ppid,stat,rss,args | grep -E "[t]ermux_service_manager|[u]vicorn|[s]shd"'
ssh nubia 'free -m; cat /proc/loadavg'
ssh nubia 'su -c "dumpsys power | grep -Ei \"Wake Locks|PARTIAL_WAKE_LOCK|mWakefulness\" -A4 -B2"'
ssh nubia 'cd ~/Petagent && .venv/bin/python - <<PY
import sqlite3
con = sqlite3.connect("backend/data/pet.db")
print(con.execute("PRAGMA journal_mode").fetchone())
print(con.execute("PRAGMA wal_autocheckpoint").fetchone())
PY'
cd /Users/wylam/Documents/workspace/Petagent/backend && ../.venv/bin/python -m pytest -q
cd /Users/wylam/Documents/workspace/Petagent/frontend && npm test -- --run
cd /Users/wylam/Documents/workspace/Petagent/frontend && npm run build
```

Observed test results at audit time:

- Backend: `337 passed, 16 skipped`.
- Frontend tests: `38 passed`.
- Frontend build: passed.

