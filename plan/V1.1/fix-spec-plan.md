# PetAgent V1.1 Fix Spec Plan

> Companion to `stability-issues.md`. Maps each STAB-XX to a concrete fix approach,
> grouped into phases by risk and dependency. Each entry is intended to be small
> enough to land as a self-contained PR with tests.

**Date:** 2026-05-20
**Target runtime:** Nubia NX531J, Android 6.0.1, Termux, FastAPI on `127.0.0.1:8000`,
~200MB free RAM, no swap, load average ~7-8, browser frontend served from `frontend/dist`.

## Review Resolution / Revision Notes

This revision incorporates the latest review findings into the executable plan:
STAB-001 and SQLite `AudioJobStore` move into Phase 1, provider error skeleton
and minimal internal/debug auth move into Phase 0, health is split into light /
watchdog / deep layers, dispatcher lock splitting now uses snapshot + versioned
commit, SQLite checkpoint/backup policy is made migration-safe, and wake fallback
uses existing audio-understanding fields only.

Second review resolution: Phase 1 now has an authoritative implementation
order, health is protected from saturation by app-level heavy-route gates rather
than relying on uvicorn `--limit-concurrency`, deep health stays debug-only, the
frontend reads a separate public client config endpoint, AudioJob persistence
mirrors the runtime job contract, dispatcher side effects are mapped explicitly,
and backend proactive scheduling is bounded so it cannot become a new always-on
provider/TTS load source.

---

## Guiding Constraints (apply to every fix)

1. **RAM is scarce.** Avoid loading whole files into memory. Avoid creating
   per-request threads. Cap concurrency. Prefer streaming and bounded queues.
2. **CPU is loaded.** Avoid pure-Python loops over large buffers. Avoid blocking
   the event loop. Move long work to bounded executors.
3. **Network is flaky.** Use `(connect_timeout, read_timeout)` tuples on every
   `requests` call. Fast paths get short timeouts plus one retry; only explicit
   thinking paths get long timeouts.
4. **Restarts must be cheap.** Anything in process memory that the user depends
   on across restarts (audio jobs, agent runs, recent incidents) must persist.
5. **Health must never block on the agent loop.** A wedged LLM call cannot make
   the manager think the runtime is dead.
6. **Surgical changes.** Match existing style; do not refactor adjacent code.

---

## Phasing Overview

| Phase | Theme | STAB items | Estimated effort |
|-------|-------|-----------|------------------|
| 0 | Correctness + safety gates (low risk, high value) | 002, 003, 004, 019-skeleton, 027, 029, 032-min | 1–2 days |
| 1 | Mobile-safe runtime + recovery + visible pet loop | 001, 005, 006, 007, 008, 009, 010, 013, 014, 015, 033, 036 | 5–7 days |
| 2 | Persistence extensions + provider observability | 011, 012, 017, 019-full, 020, 021, 022, 023, 024, 025, 037 | 4–6 days |
| 3 | Frontend UX resilience | 016, 028, 030, 031 | 2–3 days |
| 4 | Hardening follow-through | 018, 026, 032-hardening, 034, 035 | 1–2 days |

Phases are sequenced because later phases depend on infrastructure built in
earlier phases (lifespan, provider error classes, persistence stores).

---

## Mandatory Stage Execution Protocol

Every phase below is a **stage**. Do not implement a stage directly from this
master plan. Each stage must go through the same controlled workflow:

1. **Enter Plan mode first.** The implementing agent must switch to Plan mode
   or explicitly use a Plan-mode workflow before editing code. In that mode,
   write a stage-specific implementation plan that maps the selected phase to
   concrete files, tests, Nubia checks, rollback notes, and commit boundaries.
2. **Save the stage plan.** Store it under
   `plan/V1.1/stages/phase-N-<short-name>.md`. The plan must mention the exact
   STAB/CC items covered, the order of tasks, and the expected verification
   commands.
3. **Review the stage plan with a subagent.** Spawn a read-only subagent to
   review the stage plan against this master plan, `stability-issues.md`, and
   current project code. The review must return `PASS` or `FIX`.
4. **Revise the stage plan if needed.** If the subagent returns `FIX`, update
   the stage plan and repeat review or at least document the resolved findings
   before any implementation begins.
5. **Implement only the reviewed stage scope.** Do not pull work from later
   phases unless the reviewed stage plan explicitly says it is a dependency.
   Preserve unrelated user changes.
6. **Run local verification.** Run the tests and build commands named in the
   stage plan. For mobile/runtime stages, also run the specified `ssh nubia`
   field checks.
7. **Completion review with a subagent.** After implementation and tests, spawn
   a second read-only subagent. It must compare the completed code against:
   this master plan, the stage plan, project details, and the actual diff. It
   should look for missing requirements, regressions, weak tests, and Nubia
   runtime risks.
8. **Fix completion-review findings.** If the subagent returns `FIX`, repair
   the code and rerun relevant verification. Repeat review when the issue is
   substantial or risky.
9. **Compact context.** After the stage is reviewed and fixed, run one
   conversation `/compact` before committing, so the next stage starts with a
   clean handoff. If the environment cannot execute slash commands directly,
   write an explicit compact handoff summary containing changed files, tests,
   Nubia checks, unresolved risks, and next-stage entry point.
10. **Commit and push.** Commit only the stage changes and the stage plan/review
    artifacts. Push the branch after the commit. If `git push` is slow or times
    out because of network/proxy issues, run the user-defined terminal command
    `proxy` to enable the proxy, then retry `git push`.

No stage is considered complete until the stage plan review, implementation
verification, completion review, fixes, `/compact`, commit, and push are done.

### Stage Plan / Review Matrix

| Stage | Stage plan file | Plan-review focus | Completion-review focus |
|-------|-----------------|-------------------|-------------------------|
| Phase 0 | `plan/V1.1/stages/phase-0-correctness-safety.md` | MiMo key, route metadata, thinking voice path, provider error skeleton, CORS/token inventory, state side effects, energy deduction | API behavior stays compatible, token gate protects all sensitive endpoints, route/brain metadata is truthful, tests cover failure classes |
| Phase 1 | `plan/V1.1/stages/phase-1-mobile-runtime-recovery.md` | AudioJobStore before lifespan, health lane not blocked by load gates, default-browser intent, bounded proactive scheduler, dispatcher side-effect map | Nubia health/watchdog remains responsive under load, browser relaunch works with `FRONTEND_STARTUP_SECONDS=120s`, persisted jobs survive restart, no hidden thread/DB races |
| Phase 2 | `plan/V1.1/stages/phase-2-provider-persistence-observability.md` | Provider probes/circuit breakers/timeouts, WAL/checkpoint/backup, AgentRun/incident persistence, wake fallback from existing fields | Provider/API failures expose structured errors, WAL/backup does not stall old Android, incident/debug data is useful and token-protected |
| Phase 3 | `plan/V1.1/stages/phase-3-frontend-ux-resilience.md` | Client config endpoint usage, frontend reconnect, audio wait UX, tick tuning, build-info/versioning | Frontend survives Wi-Fi/browser recovery, uses `/api/runtime/client-config` not deep health, Momo state curves feel alive without cratering |
| Phase 4 | `plan/V1.1/stages/phase-4-hardening-followthrough.md` | Upload magic validation, memory-card rebuild lock, CORS/token hardening, proxy supervision, log consolidation | Security hardening is complete, proxy/log operations are observable, no sensitive endpoint remains public, long-run maintenance is easier to debug |

---

## Cross-Cutting Infrastructure

These pieces are introduced once and reused across many fixes. Build them first
within their respective phases.

### CC-0: Minimal internal/debug protection (Phase 0 prerequisite)

Before adding any `/api/debug/*` or `/api/internal/*` endpoint, add a small
security gate:

- CORS origin allowlist from config; default to loopback and configured phone
  LAN origin only.
- `DEBUG_INTERNAL_TOKEN` from env, or a generated token persisted once at
  `backend/data/secrets/internal_token` with mode `0600`. Backend, frontend
  debug tools, and `termux_service_manager.sh` read the same persisted secret;
  never rely on "printed once" logs as the only source of truth.
- Token required for debug reads, management writes, reset endpoints, skill
  execution, and incident writes. Initial protected inventory:
  `/api/debug/*`, `/api/internal/*`, `/api/context/debug`,
  `/api/context/runs`, `/api/memory/debug`, `/api/memory/curate`,
  `/api/memory/summarize`, `/api/runtime/reset`, and
  `/api/skills/{skill_id}/run`.
- Public user APIs stay token-free: `/`, static assets, `/api/health`,
  `/api/health/watchdog`, `/api/runtime/client-config`, normal text/voice/chat
  APIs, pet state/event APIs, and audio job polling.
- `/api/internal/incident` accepts only loopback plus shared secret when called
  by `termux_service_manager.sh`.

Phase 4 can improve pairing UX, but no sensitive endpoint lands before this
minimum is in place.

### CC-1: Provider error class hierarchy (Phase 0 skeleton, Phase 2 expansion)

New module `backend/app/providers/errors.py`:

```python
class ProviderError(Exception):
    def __init__(self, *, provider, code, status=None, latency_ms=None, message=""):
        ...

class ProviderAuthError(ProviderError): ...        # 401/403
class ProviderTimeoutError(ProviderError): ...     # connect/read timeout
class ProviderUnavailableError(ProviderError): ... # 5xx
class ProviderQuotaError(ProviderError): ...       # 429 / quota response
class ProviderBadResponseError(ProviderError): ... # JSON/schema invalid
class ProviderNetworkError(ProviderError): ...     # DNS / connection refused
```

Every provider raises one of these instead of returning `None`/silent fallback.
Fallback wrappers catch them, record the class on the route metadata, then try
the fallback. Phase 0 lands the minimal class hierarchy, `error_class`, and
structured text/voice response fields. Phase 2 adds provider probes, cooldowns,
and circuit breaker behavior. Callers see structured error info in `route_info`.

### CC-2: Route metadata schema

A single dataclass `RouteInfo` produced by route policy and consumed unchanged
by both `runtime` and `route_info` in API responses. Brain selection reads from
this object — never from `thinking_mode` directly. Adds `error_class` plus
provider failure fields (`provider`, `stage`, `fallback_used`) populated by
provider wrappers.

### CC-3: Health endpoints split

- `GET /api/health` is light process liveness only. It stays at < 50ms and
  returns `{ok, name, version, build_hash, pid, started_at}`. No DB queries,
  provider checks, frontend state, or agent locks.
- `GET /api/health/watchdog` is manager-safe stuck detection. It reads only
  lock-free / no-lock / low-cost counters updated by runtime code:
  `{event_loop_tick_age_s, active_requests, agent_inflight_age_s,
  provider_inflight_age_s, audio_queue_depth, frontend_heartbeat_age_s,
  core_ready, shutdown_in_progress}`. It must not acquire the dispatcher lock
  or hit provider/DB code paths that can block on writes.
- `GET /api/health/deep` is for humans and debugging. It may include DB
  quick_check, WAL bytes, last provider status, audio backlog, candidate
  backlog, proxy reachability, frontend heartbeat age, and build info.
  Manager does not directly depend on deep health. Deep health is protected by
  the CC-0 debug token; frontend runtime tuning must not read it directly.

### CC-4: FastAPI lifespan

`@asynccontextmanager async def lifespan(app)` replaces the current bare app
construction. Startup phase: build core stores synchronously, schedule provider
probes / card rebuild / heavy state warmup as background tasks. Shutdown phase:
stop accepting new audio jobs, drain executor, stop maintenance worker, close
SQLite connections. Depends on CC-6 being present first so shutdown can mark
pending/running audio jobs in SQLite.

### CC-5: Maintenance background worker

Replace `threading.Thread(target=...).start()` per event with a single
long-lived `MaintenanceWorker` thread fed by a `queue.Queue(maxsize=1)`. The
dispatcher just calls `worker.notify()`; if the queue is full the notification
is coalesced. Started/stopped from lifespan.

### CC-6: SQLite-backed AudioJobStore (Phase 1 prerequisite for lifespan)

New table mirrors the current `AudioJob` runtime contract instead of inventing
a smaller shape:

`audio_job(job_id TEXT PRIMARY KEY, run_id TEXT, event_id TEXT, session_id TEXT,
status TEXT, text TEXT, voice_style TEXT, provider TEXT, voice_url TEXT,
audio_path TEXT, error TEXT, error_class TEXT, failure_reason TEXT,
timings_json TEXT, created_at TEXT, updated_at TEXT, completed_at TEXT,
expires_at TEXT, superseded_by TEXT)`.

Indexes: `(status, created_at)`, `(session_id, status, created_at)`,
`(run_id)`, `(event_id)`. The in-memory dict becomes a write-through cache. On
startup, any `pending`/`running` row is re-marked `failed_runtime_restart`.
Graceful shutdown marks in-flight rows `failed_shutdown`; per-session
supersede/expired states persist with `failure_reason`. Frontend polling for
restart-failed rows returns a structured 404 with `reason:
runtime_restarted`.

### CC-7: SQLite-backed AgentRunStore (bounded)

Table `agent_run(id, started_at, ended_at, route, brain, error_class,
timings_json, sanitized_user_text, sanitized_response_text)`. Cap at 200 rows
via `DELETE WHERE id NOT IN (SELECT id FROM agent_run ORDER BY started_at DESC
LIMIT 200)` after each insert. Used for postmortem.

### CC-8: Incident breadcrumb table

Table `runtime_incident(ts, kind, payload_json)`. Capped to ~500 rows. Logged
on provider errors, audio job failures, manager restart reasons (written via
small `/api/internal/incident` endpoint called from manager scripts and
protected by CC-0).

### CC-9: Public client runtime config

Add `GET /api/runtime/client-config` for frontend-safe, non-secret runtime
profile. It returns only values the browser needs:
`{audio_job_poll_interval_ms, audio_job_deadline_ms, tts_primary_timeout_s,
tts_fallback_timeout_s, frontend_heartbeat_interval_s, frontend_stale_after_s,
build_hash}`. It must not expose provider keys, proxy state, DB paths, incident
counts, or deep health details. The frontend uses this endpoint instead of
`/api/health/deep`.

---

## Phase 0 — Correctness + Safety Gates (1–2 days, low risk)

Goal: wrong-key auth, wrong-brain selection, surprising state side effects.
All Phase 0 changes are local, well-bounded, and backed by unit tests.

### STAB-002 — MiMo audio understanding uses wrong API key

**Fix:** In `MiMoAudioUnderstandingProvider`, replace every reference to
`self.settings.api_key` with `self.settings.audio_understanding.api_key` (and
mirror for the fallback config block). Drop the global `api_key` derivation in
`config.py` from being used by audio paths; if other providers truly need it,
keep the derivation but never read it from audio_omni.

**Files:** `backend/app/providers/audio_omni.py`,
`backend/app/config.py` (audit usages).

**Tests:** unit test with `MIMO_API_KEY != SILICONFLOW_API_KEY`, assert request
header carries the MiMo key. Add an integration smoke test guarded by env vars
that POSTs a tiny WAV through the audio understanding path.

**Risk:** if some provider implicitly relied on the derived `settings.api_key`,
log a warning during config load. Rollback: revert single file change.

### STAB-003 — Route policy says slow but brain stays fast

**Fix:** Build CC-2 `RouteInfo`. `RoutePolicy.decide(...)` returns it,
including the resolved provider name. `TextPipeline.handle()` chooses brain
from `route_info.brain`, not from `thinking_mode`. `dispatcher.runtime`
metadata is populated from the same object. `thinking_mode` becomes one of
several inputs to `decide()`, not the final selector.

**Files:** `backend/app/runtime/route_policy.py`,
`backend/app/runtime/text_pipeline.py`,
`backend/app/runtime/voice_pipeline.py`,
`backend/app/runtime/dispatcher.py`.

**Tests:** for each combination (manual thinking off + complex keyword,
manual thinking on + simple text, manual off + simple), assert `runtime.brain
== route_info.brain` and that the actual provider invoked matches.

**Risk:** existing tests may assert old behavior. Update them to assert the
new invariant. Rollback: keep old selector behind a config flag for one
release if needed (prefer not to).

### STAB-004 — Thinking voice path still starts with ASR

**Fix:** In `VoicePipeline.handle()`, branch on `route_info.brain == "slow"`:
call `_run_audio_understanding_route()` first, optionally call ASR afterward
to enrich `transcript_assist` field. For `route_info.brain == "fast"`, keep
ASR-first as today. Pass through tone/emotion source field
(`emotion_source: "audio_understanding" | "asr" | "fallback"`).

**Files:** `backend/app/runtime/voice_pipeline.py`.

**Tests:** unit test that thinking voice request invokes audio understanding
provider before ASR provider. Snapshot test of route_info fields.

**Risk:** audio understanding latency may exceed ASR. Document expected
latency in route metadata. Rollback: per-route flag.

### STAB-019 — Provider error skeleton and route failure metadata

**Fix:** Land the minimal CC-1 skeleton in Phase 0, before deeper provider
observability work:
- Add `ProviderError` and subclasses with stable `error_class` labels.
- Convert provider boundary failures to structured errors without leaking raw
  exception text or secrets.
- Add `route_info.provider_failure` fields:
  `{provider, stage, error_class, fallback_used}`.
- Add `error_class` to text and voice API responses; frontend maps unknown
  classes to neutral recovery copy.

This Phase 0 work is intentionally small. Provider probes, circuit breaker,
failure windows, and cooldown behavior remain Phase 2.

**Files:** `backend/app/providers/errors.py`,
`backend/app/runtime/route_policy.py`,
`backend/app/runtime/dispatcher.py`,
`backend/app/api/text.py`, `backend/app/api/voice.py`.

**Tests:** mock timeout, 401, 500, and malformed JSON at provider boundaries;
assert `error_class` and `route_info.provider_failure` are populated and the
API still returns structured text/voice failure responses.

**Risk:** exception leakage to API responses. Catch at the dispatcher/API
boundary; never let `ProviderError` reach Starlette.

### STAB-032 — Minimal CORS/internal auth safety gate

**Fix:** Before any debug or internal endpoint lands, implement CC-0:
1. Replace broad CORS with an origin allowlist from config:
   loopback, the deployed `127.0.0.1:8000` frontend, and the configured phone
   LAN origin only.
2. Add `DEBUG_INTERNAL_TOKEN` support. If unset, generate once and persist to
   `backend/data/secrets/internal_token` with `0600` permissions. Print only
   the path and a short fingerprint to `runtime.log`, not the full token.
3. Build a protected endpoint inventory and enforce it in tests:
   - debug reads: `/api/debug/*`, `/api/context/debug`,
     `/api/context/runs`, `/api/memory/debug`;
   - management writes: `/api/memory/curate`, `/api/memory/summarize`,
     `/api/runtime/reset`, `/api/skills/{skill_id}/run`;
   - internal writes: `/api/internal/*`, including `/api/internal/incident`.
4. Keep normal user APIs token-free: text/voice chat, pet state/event,
   activation, audio polling, light/watchdog health, client config, and static
   frontend assets.
5. Manager incident writes use loopback plus shared secret; non-loopback
   requests without token get 403.

**Files:** `backend/app/main.py`,
`backend/app/api/auth.py` (new),
`backend/app/api/debug.py`,
`backend/app/api/internal.py`,
`scripts/termux_service_manager.sh`.

**Tests:** unit test allowed loopback origin succeeds, unlisted origin is
rejected by CORS, `/api/debug/*` and `/api/internal/incident` return 403
without token, manager loopback call succeeds with shared secret. Add one test
per protected endpoint category above so future debug routes cannot accidentally
land public.

**Risk:** breaks ad-hoc scripts hitting debug endpoints. Document token usage
when those endpoints are introduced.

### STAB-027 — `GET /api/pet/state` has tick side effects

**Fix:** Remove `tick_service.apply_if_due()` from `get_pet_state()`. Add
`POST /api/pet/session/resume` that explicitly applies decay and returns the
new state. Frontend calls resume on app load and on `online` event, not on
every poll. `GET state` becomes pure read.

**Files:** `backend/app/api/pet.py`, `frontend/src/App.tsx`,
`frontend/src/api.ts` (or equivalent).

**Tests:** unit test that `GET state` does not call `apply_if_due`. Frontend
unit test that resume is called once per session, not per poll.

**Risk:** breaks any external script polling `GET state` and expecting decay.
Acceptable since there is no external client.

### STAB-029 — Pet effort double-deducts energy

**Fix:** Decide one source of truth. Recommended: keep effort fatigue in
dispatcher (deterministic), and instruct the LLM via system prompt to not
include energy in `state_delta`. Add validator that strips `energy` from
LLM-returned `state_delta` and logs a warning (counts toward CC-8 incident
breadcrumbs once that exists).

**Files:** `backend/app/runtime/dispatcher.py`,
`backend/app/runtime/prompts/*` (system prompt updates).

**Tests:** unit test that a mocked LLM returning `state_delta={energy: -10}`
plus medium effort still deducts only the deterministic effort amount.

**Risk:** if intimacy/loneliness deltas were also tangled with energy,
re-audit. Rollback: revert validator.

---

## Phase 1 — Mobile-Safe Runtime + Recovery (5–7 days)

Goal: backend can take load and restarts without melting the phone or sitting
in a 10-minute death window, and the desktop pet remains visibly alive after
reboot or browser process death.

Authoritative implementation order inside Phase 1:

1. `STAB-015` / CC-6 SQLite `AudioJobStore`.
2. `STAB-006` / CC-4 lifespan skeleton that can safely drain persisted jobs.
3. `STAB-036` / CC-3 health split with light, watchdog, and token-protected
   deep health.
4. `STAB-007` app-level heavy-route concurrency gates that preserve health
   lane.
5. `STAB-008` startup/manager changes, now allowed to use lifespan background
   warmup and watchdog counters.
6. `STAB-001` frontend heartbeat, default-browser intent relaunch, and bounded
   backend proactive scheduler.
7. `STAB-009` maintenance worker.
8. `STAB-005` dispatcher snapshot/commit split and `STAB-010` provider
   concurrency guard.
9. `STAB-013` / `STAB-014` upload and audio CPU fixes.

The section order below groups related product/runtime concerns, but the list
above is the execution order for workers.

### STAB-001 — Frontend desktop pet not actually persistent

**Fix (minimal V1.1 closed loop):** Adopt Termux manager default-browser
intent relaunch plus backend proactive scheduling as the Phase 1 minimum:
1. Add `POST /api/frontend/heartbeat` from the browser every 30s. Store only
   `{last_seen_at, user_agent_hash, visible}` in process counters and, if cheap,
   the incident table for restart breadcrumbs.
2. Add `ProactiveScheduler` in the backend. It ticks independently of the
   browser, but it is deliberately cheap when the frontend is absent:
   - keep a persisted bounded queue of at most 20 proactive events;
   - coalesce same-kind events inside a 15-minute bucket;
   - when `frontend_heartbeat_age_s > 90`, do not call LLM, TTS, or provider
     APIs; record only deterministic lightweight state/proactive hints;
   - after runtime restart, create at most one `catch_up` event summarizing the
     offline interval instead of replaying every missed tick.
   The frontend consumes queued events by existing polling or SSE if already
   available.
3. Add a Nubia setup script/doc path for autostart: Termux:Boot starts the
   backend; `scripts/termux_service_manager.sh` launches the default browser
   with Android intent after backend health is ready:
   `am start -a android.intent.action.VIEW -d http://127.0.0.1:8000/`.
   Fully Kiosk Browser / WebView shell are deferred options, not V1.1
   requirements.
4. Manager uses heartbeat age from `/api/health/watchdog`; if the backend is
   healthy but `frontend_heartbeat_age_s > 90`, it attempts one browser relaunch
   per configured cooldown instead of restarting the backend.

**Files:** new `backend/app/runtime/proactive_scheduler.py`,
`backend/app/api/frontend.py`,
`backend/app/api/proactive.py`,
`backend/app/api/health.py`,
`frontend/src/App.tsx`,
`scripts/termux_service_manager.sh`,
`docs/phone-setup.md`.

**Tests:** unit test that scheduler emits/records bounded events without a
connected browser; assert queue length never exceeds 20; assert same-kind events
coalesce; assert stale heartbeat suppresses provider/TTS calls; frontend test
that heartbeat posts on load/visibility return; manager script test with stale
heartbeat asserts browser relaunch path is selected.

**Acceptance:** after phone reboot, browser is foreground and Momo visible
within `FRONTEND_STARTUP_SECONDS=120s`; `/api/health/watchdog`
reports `frontend_heartbeat_age_s < 90`; proactive events continue for 24h
without browser polling as the only scheduler; during that 24h no-browser
period scheduler DB rows stay bounded, RSS remains stable, and provider call
count for proactive work is zero; closing the browser and waiting one manager
loop causes relaunch/recovery without backend restart.

**Risk:** Android 6 browser relaunch reliability varies. Keep the relaunch
command configurable and log every attempt to CC-8.

### STAB-007 — Uvicorn runs without mobile-safe limits

**Fix:** Do not rely on uvicorn `--limit-concurrency` as the primary load
shedding mechanism, because it can reject `/api/health` before the app can make
a route-aware decision. Use app-level gates for heavy routes and keep the
manager health lane available:

1. Add `backend/app/runtime/concurrency.py` with:
   - `AgentWorkExecutor(max_workers=4, max_queue=8)` for blocking text/voice
     pipelines currently wrapped by `run_in_threadpool`;
   - `async submit_agent_work(fn, *, timeout_s)` that returns 503
     `{error_class: "server_busy"}` when the bounded queue is full;
   - separate `ProviderGate` semaphore counters for provider calls (completed
     under STAB-010).
2. Replace `run_in_threadpool()` in `/api/text/chat` and `/api/voice/chat`
   with `await submit_agent_work(...)`. Starlette's default threadpool is no
   longer consumed by the whole pipeline.
3. Apply heavy-route gating to `/api/pet/event`, `/api/pet/proactive/trigger`,
   activation endpoints, and any skill execution endpoint that can run tools.
4. Do not gate `/api/health`, `/api/health/watchdog`,
   `/api/runtime/client-config`, static frontend files, or audio job polling.
5. Keep safe uvicorn process-level limits that do not block the health lane:
```
python -m uvicorn app.main:app \
  --host "$HOST" --port "$PORT" \
  --limit-max-requests 2000 \
  --timeout-keep-alive 15 \
  --timeout-graceful-shutdown 10 \
  --backlog 32
```
Avoid `--limit-concurrency` for V1.1 unless field tests prove it is necessary;
if it is added later, manager tests must prove saturation is not mistaken for a
dead runtime.

**Files:** `scripts/start.sh`,
new `backend/app/runtime/concurrency.py`,
`backend/app/api/text.py`,
`backend/app/api/voice.py`,
`backend/app/api/pet.py`,
`backend/app/api/activation.py`,
`backend/app/main.py` (structured 503).

**Tests:** load test script `scripts/dev/burst_uploads.sh` that fires N parallel
voice uploads and asserts steady-state behavior: heavy routes return structured
busy responses when saturated, RSS stays bounded, `/api/health` remains < 50ms,
`/api/health/watchdog` remains < 100ms, and the manager does not restart the
runtime during saturation.

**Risk:** too-tight app gates cause spurious 503. Start with 4 running / 8 queued
heavy jobs and adjust based on field RSS readings. Rollback: raise gate limits,
not uvicorn process-wide concurrency.

### STAB-008 — Heavy startup + manager backoff = 10-minute death window

**Fix (split into dependency-safe commits):**
1. After STAB-036, make `/api/health` reachable as soon as the FastAPI app
   object exists, before provider probes or memory-card work.
2. After STAB-006 lifespan exists, move heavy startup work (provider probes,
   memory card rebuild, summary store warmup) into background tasks scheduled
   from lifespan.
3. Add `core_ready: bool` to `/api/health/watchdog`; add `providers_ready:
   bool` to token-protected `/api/health/deep` for human debugging.
4. In `scripts/termux_service_manager.sh`, call `/api/health` with
   `curl --connect-timeout 1 --max-time 2`, then `/api/health/watchdog` with
   `--connect-timeout 1 --max-time 3`. Treat HTTP fail during startup grace as
   "still starting" (no fail counter increment) when process+port alive and
   watchdog says `core_ready=false`. Reduce `BACKOFF_SECONDS` from 600 to 120
   for known recoverable startup states (kept at 600 for repeated hard process
   death).

**Files:** `backend/app/main.py`, `scripts/start.sh`,
`scripts/termux_service_manager.sh`.

**Tests:** simulate slow provider probe, confirm `/api/health` answers in
< 1s and `/api/health/watchdog` answers in < 3s, confirm manager doesn't
increment fail counter during startup grace. Add ordering test/documentation
check that STAB-008 background warmup is implemented only after STAB-006
lifespan.

**Risk:** background probe failures must not silently leave the app in a
half-working state. Surface them via `/api/health/deep`.

### STAB-015 — AudioJobManager is memory-only

**Fix:** Implement CC-6 before lifespan/shutdown work. Refactor
`AudioJobManager` to write-through to SQLite. On startup, `UPDATE audio_job
SET status='failed_runtime_restart' WHERE status IN ('pending', 'running')`.
`GET /api/audio_jobs/{id}` returns 404 with `reason: "runtime_restarted"` for
these rows. Cache last 50 done jobs in memory for fast reads.

**Files:** `backend/app/runtime/audio_jobs.py`,
`backend/app/runtime/memory_store.py` (or dedicated migration file),
`backend/app/api/audio_jobs.py`.

**Tests:** restart simulation test confirms pending/running jobs are marked
failed and frontend gets a structured 404. Add a shutdown fixture that creates
a pending row before SIGTERM so STAB-006 can assert `failed_shutdown`.
Add schema contract test that compares persisted columns against
`AudioJob.dict()` plus V1.1 persistence fields (`text`, `voice_style`,
`audio_path`, `completed_at`, `expires_at`, `failure_reason`, `superseded_by`).
Add per-session test where an older pending job becomes `superseded` and remains
queryable after restart.

**Risk:** SQLite write contention with main event lock. Use a separate
connection for audio jobs (already pattern for other stores).

### STAB-006 — No FastAPI lifespan or shutdown hook

**Fix:** Implement CC-4 after STAB-015. Wire `audio_job_manager.shutdown(timeout=5)`,
`maintenance_worker.stop()`, and `connection.close()` for the DB. Reject new
`/api/voice/chat` and `/api/text/chat` once shutdown begins (return 503 with
`reason: shutting_down`).

**Files:** `backend/app/main.py`, `backend/app/runtime/audio_jobs.py`,
`backend/app/runtime/maintenance.py`.

**Tests:** integration test that sends SIGTERM and verifies graceful shutdown
log lines + exit within 10s. Verify pending audio jobs are recorded as
`failed_shutdown` in CC-6 store.

**Risk:** lifespan is mandatory in newer Starlette; ensure version pinned.

### STAB-009 — Maintenance creates a new thread per event

**Fix:** Implement CC-5 `MaintenanceWorker`. Replace
`threading.Thread(target=..., daemon=True).start()` in
`RuntimeDispatcher._try_maintenance_tick()` with `worker.notify()`. The worker
loops `q.get(timeout=...)`, calls `tick()`, sleeps until next slot. Thread is
named `petagent-maintenance` for ps visibility.

**Files:** new `backend/app/runtime/maintenance_worker.py`,
`backend/app/runtime/dispatcher.py`, `backend/app/main.py`.

**Tests:** stress test sends 100 events in 5s, asserts thread count stays
constant (~3 named threads), maintenance still progresses.

**Risk:** if notifications coalesce too aggressively, candidate backlog could
grow. Add a wall-clock-based fallback tick every 5 minutes regardless of
notifications.

### STAB-005 — Single dispatcher lock serializes everything

**Fix (incremental, versioned commit):** Split `handle_event()` into:
1. **Locked snapshot/reservation:** acquire the dispatcher lock briefly, read
   pet state + memory/version counters, reserve an `episode_id` / run id, and
   persist an `agent_run` started marker if available. Release the lock before
   any provider work.
2. **Slow work outside lock:** route policy, LLM/provider calls, audio/TTS,
   and tool planning run outside the lock using the immutable snapshot and
   reservation metadata. No shared mutable state is changed here.
3. **Locked compare-and-commit:** re-acquire the lock, compare state version
   and episode reservation, then either commit the computed delta or recompute
   the delta against fresh state before writing. Deduplicate memory candidates
   by deterministic key before insert.

Side-effect map for the split:

| Stage | Allowed work | Forbidden work |
|-------|--------------|----------------|
| Locked snapshot/reservation | apply due tick once; read `pet_state.version`; reserve `event_id`, `run_id`, `episode_id`; insert raw event / run-start marker | provider calls, TTS, skill execution, long DB scans |
| Outside lock | route policy from immutable snapshot; LLM/provider/audio-understanding calls; read-only context/memory reads; construct proposed state delta and response | writing pet state, closing/opening episodes, inserting memory candidates, running non-idempotent skills |
| Outside lock skills/tools | only explicitly read-only or idempotent skills; mutating skills must enqueue a job or run in commit phase | arbitrary filesystem/process/network side effects tied to the pet state transaction |
| Locked compare-and-commit | CAS on `pet_state.version`; write final state delta; update episode; write event/run completion; insert memory candidate with deterministic idempotency key | provider calls or any operation that can wait on network |
| After commit | enqueue persisted audio job linked by `run_id/event_id/session_id`; notify maintenance worker | changing committed pet state |

Add `pet_state.version` or equivalent monotonic CAS token before splitting the
lock. If CAS fails, recompute deterministic deltas against fresh state or retry
once; never blindly overwrite the newer state.

The current single-RLock semantics are preserved only for snapshot and commit
boundaries; provider latency no longer serializes unrelated interactions.

**Files:** `backend/app/runtime/dispatcher.py`.

**Tests:** existing dispatcher tests must still pass. Add concurrency tests
that fire simultaneous events and assert:
- state deltas are all applied exactly once against versioned state;
- episode/run counters have no gaps or duplicates;
- memory candidates are deduplicated under concurrent identical events;
- both responses return within ~2× single-event latency, not serialized 1×N.
- non-idempotent skills are rejected or queued instead of running outside the
  commit boundary.

**Risk:** plan/commit split could expose race conditions on shared brain
state. Audit `slow_brain`, `fast_brain`, provider wrappers, skill registry, and
context/memory readers for thread safety. Rollback: re-acquire lock around slow
work behind a config flag.

### STAB-010 — Provider calls block worker threads

**Fix:** Address provider blocking in Phase 1 with two explicit layers:
1. STAB-007 moves whole blocking text/voice pipelines off Starlette's default
   threadpool into a bounded `AgentWorkExecutor`, so health/watchdog/static
   requests do not wait behind slow agent work.
2. Add `ProviderGate` inside `backend/app/runtime/concurrency.py` to cap
   external provider concurrency independently of agent work. Suggested mobile
   profile: `llm_fast=2`, `llm_slow=1`, `asr=1`, `tts=2`,
   `audio_understanding=1`. When the gate is full, fast paths return
   `error_class: "provider_busy"` or fall back; thinking paths may wait up to
   their configured budget.

This does **not** claim that submitting a provider call from inside a blocking
pipeline frees the Starlette worker. The worker is freed by the STAB-007 API
boundary change; the provider gate only bounds outbound network pressure.

**Files:** `backend/app/runtime/concurrency.py`,
`backend/app/api/text.py`,
`backend/app/api/voice.py`,
`backend/app/runtime/dispatcher.py`,
`backend/app/runtime/voice_pipeline.py`.

**Tests:** simulate 10 slow provider calls and assert `/api/health` and
`/api/health/watchdog` remain responsive; assert provider calls respect gate
limits; assert heavy routes return structured busy/fallback responses instead
of exhausting Starlette's default threadpool.

**Risk:** too-small provider gates make Momo feel unavailable. Start with the
mobile profile above and tune from Nubia field timings.

### STAB-013 — Voice upload reads entire file into RAM

**Fix:** Replace `await file.read()` + `path.write_bytes(data)` in
`_save_upload()` with a chunked loop:
```python
hasher = ...  # optional integrity
total = 0
limit = max_audio_bytes(settings)
with path.open("wb") as out:
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            out.close()
            path.unlink(missing_ok=True)
            raise HTTPException(413, "Audio file is too large")
        out.write(chunk)
```
Lower `max_audio_bytes` default for mobile profile to 4MB unless config
override.

**Files:** `backend/app/api/voice.py`, `config/app.yaml` if applicable.

**Tests:** unit test with 9MB upload returns 413 without OOM. Unit test that
8MB upload is saved correctly.

**Risk:** none significant.

### STAB-014 — Empty-audio detection scans entire WAV in pure Python

**Fix:** Replace per-sample loop in `is_probably_empty_audio()` with sampled
RMS over up to 16 windows of 4096 frames each, distributed across the file.
Use `audioop.rms` if available (it is in stdlib). Cap total frames inspected
at 64k regardless of file size.

**Files:** `backend/app/providers/audio_omni.py`.

**Tests:** benchmark test asserts < 50ms on a 8MB WAV (down from likely
seconds). Functional test on known-silent and known-speech samples.

**Risk:** sampled detection may miss a silent file with a single loud spike.
Acceptable; the goal is "probably empty", not certainty.

### STAB-033 — Manager doesn't restart watchdog-stuck states

**Fix:** Extend `scripts/termux_service_manager.sh` health probe to call
`/api/health` for liveness and `/api/health/watchdog` for stuck detection.
Define `STUCK` state only from watchdog counters, e.g.
`agent_inflight_age_s > 90`, `event_loop_tick_age_s > 90`, or
`provider_inflight_age_s > configured_timeout + 30`. Restart on sustained
STUCK state after 3 consecutive failed/stuck cycles.

**Files:** `scripts/termux_service_manager.sh`,
`backend/app/api/health.py` (add metrics).

**Tests:** manager script tests with curl timeout set to
`--connect-timeout 1 --max-time 3`; simulate stale watchdog counters and assert
restart only after 3 consecutive stuck cycles. Simulate one slow watchdog
response and assert no restart. Manual: simulate wedge by holding provider work
outside the dispatcher lock and confirm manager observes STUCK.

**Risk:** restart loops if watchdog counters are buggy. Gate restart behind
consecutive failures, process+port checks, and existing backoff; deep health is
never used for manager decisions.

### STAB-036 — `/api/health` is too shallow

**Fix:** Implement CC-3 as three endpoints.

`/api/health` returns only:
```
{ ok, name, version, build_hash, pid, started_at }
```

`/api/health/watchdog` returns only low-cost counters safe for the manager:
```
{
  ok, core_ready, shutdown_in_progress,
  event_loop_tick_age_s, active_requests,
  agent_inflight_age_s, provider_inflight_age_s,
  audio_queue_depth,
  frontend_heartbeat_age_s
}
```

`/api/health/deep` returns human/debug detail:
```
{
  ok, name, version, build_hash,
  core_ready, providers_ready,
  db: { quick_check, wal_bytes, journal_mode },
  audio_jobs: { pending, running, failed_24h },
  candidates: { pending, error },
  providers: { llm: {last_status, last_error_class, last_success_at}, ... },
  proxy: { reachable, last_check_at },
  frontend: { last_heartbeat_at, age_s },
  agent: { lock_held_s, last_event_age_s }
}
```
It requires the CC-0 debug token. Frontend code reads
`/api/runtime/client-config` for public runtime timing/profile values instead
of deep health.

**Files:** new `backend/app/api/health.py` or extend existing one,
`backend/app/main.py` to register,
`backend/app/api/runtime.py` or `backend/app/api/client_config.py` for CC-9.

**Tests:** smoke test asserts light endpoint returns < 50ms, watchdog returns
< 100ms without acquiring dispatcher lock or DB write locks, and deep endpoint
returns < 500ms in normal conditions when called with token. Manager test
asserts only light/watchdog are called. API test asserts deep health returns
403 without token while `/api/runtime/client-config` remains public and
sanitized.

**Risk:** deep endpoint may itself stall; it is for humans only. Document.

---

## Phase 2 — Persistence + Provider Observability (4–6 days)

### STAB-019 — Provider exceptions silently swallowed

**Fix:** Expand the Phase 0 CC-1 skeleton across all provider call sites:
- `LLM` providers raise `ProviderTimeoutError` / `ProviderAuthError` etc.
  instead of returning `None`. `FallbackLLMProvider` catches, records the
  failure on the active `RouteInfo`, tries fallback.
- TTS likewise; failure marks audio job `failed` with `error_class`.
- Audio understanding likewise; falls back to `FALLBACK_AUDIO_UNDERSTANDING`
  but stores the actual `error_class` on the result for inclusion in route
  metadata.

**Files:** `backend/app/providers/*`, `backend/app/runtime/route_policy.py`,
`backend/app/runtime/dispatcher.py`.

**Tests:** for each provider, mock httpx/requests responses (timeout, 401,
500, malformed JSON) and assert correct exception class. Assert
`route_info.errors` contains the class label.

**Risk:** exception leakage to API responses. Catch at the dispatcher
boundary; never let `ProviderError` reach Starlette.

### STAB-021 — API failure responses lack structured error class

**Fix:** Phase 0 already adds `error_class` to text and voice response bodies.
Phase 2 broadens the frontend and debug usage: normalize class labels, expose
provider failure details in `route_info.provider_failure`, and let the frontend
choose bubble copy (`"我刚刚没听清"` vs `"网络好像不太给力"` vs `"嗓子有点哑"`)
without parsing raw provider messages.

**Files:** `backend/app/api/text.py`, `backend/app/api/voice.py`,
`frontend/src/App.tsx`.

**Tests:** integration test with mocked auth failure asserts response carries
`error_class: "asr_failed"` (or similar).

**Risk:** frontend mapping must exist for new classes; default to neutral
copy for unknown classes.

### STAB-020 — No startup provider key probe

**Fix:** From CC-4 lifespan, schedule `asyncio.create_task` per provider that
performs a tiny request (e.g. LLM 1-token completion or TTS empty input). On
success record `last_success_at`. On failure record `last_error_class`. Surface
via deep health. Probes run with 5s timeout each so they never block startup.

**Files:** new `backend/app/providers/probes.py`,
`backend/app/main.py`.

**Tests:** unit test that probes mark `providers_ready` correctly, and that
failure does not crash startup.

**Risk:** probes must not consume quota loudly. Use minimal payloads, and
cache results for at least 10 minutes.

### STAB-011 — No circuit breaker

**Fix:** Add `ProviderCircuit` per provider that tracks recent failures over
a rolling 60s window. If failure count >= 5 within window, open circuit for
60s — fallback wrapper skips primary and goes straight to secondary. Log
state transitions to CC-8.

**Files:** new `backend/app/providers/circuit.py`,
`FallbackLLMProvider`, `FallbackTTSProvider`.

**Tests:** simulate 5 consecutive timeouts, assert primary is skipped on the
6th call. Assert circuit closes after 60s of no failures.

**Risk:** false-positive opens during transient noise. Window-based threshold
mitigates.

### STAB-012 — Network switches stall until long timeouts

**Fix:** Audit every `requests.post/get` call in `backend/app/providers/*`.
Replace `timeout=120` style scalars with tuples `(connect_timeout=5,
read_timeout=N)` where N depends on path:
- Fast LLM: 15s
- Slow/thinking LLM: 60s
- ASR: 10s
- TTS: 30s primary, 60s fallback
- Audio understanding: 20s

Add one retry on `ProviderTimeoutError` for fast paths only.

**Files:** `backend/app/providers/llm_mimo.py`,
`backend/app/providers/tts_mimo.py`, `backend/app/providers/asr_http.py`,
`backend/app/providers/audio_omni.py`, plus any siliconflow/parakeet variants.

**Tests:** unit tests with `requests_mock` simulating connect timeout vs read
timeout, assert short-circuit behavior.

**Risk:** premature timeout causes more retries. Keep retry count = 1 only.

### STAB-024 — AgentRunRegistry is memory-only

**Fix:** Implement CC-7. Persist run metadata (sanitized text, timings, errors,
route, brain) to `agent_run` table. Cap at 200 rows by deleting oldest after
each insert. Expose at `GET /api/debug/runs?limit=20`.

**Files:** `backend/app/runtime/agent_run.py`,
`backend/app/runtime/memory_store.py`,
`backend/app/api/debug.py`.

**Tests:** integration test that runs 250 events, asserts only 200 remain.

**Risk:** sanitization must scrub keys/tokens. Reuse `_sanitize_error` pattern
from audio_jobs.

### STAB-025 — Memory candidate errors not retried

**Fix:** Add `attempt_count` and `next_retry_at` columns to `memory_candidate`.
On curator failure, mark `status='retryable'`, `attempt_count += 1`,
`next_retry_at = now + 2^attempt minutes` (capped at 1h, max 5 attempts).
Distinguish provider failure (`error_class` populated → retryable) from
validation failure (→ permanent `error`).

**Files:** `backend/app/runtime/memory_curator.py`,
`backend/app/runtime/memory_store.py`,
`backend/app/runtime/maintenance.py` (filter pending to include retryable
where `next_retry_at <= now`).

**Tests:** simulate timeout 4 times, assert retry then eventual permanent
fail. Validation reject path remains immediate `error`.

**Risk:** retryable-forever loops. Cap at 5 attempts, then permanent.

### STAB-022 — WAL has no periodic checkpoint

**Fix:** From maintenance worker, every 30 minutes (or every 100 writes,
whichever first) call `PRAGMA wal_checkpoint(PASSIVE)` against the main
connection. Report WAL bytes via deep health. Use `TRUNCATE` only when the
runtime is idle or during graceful shutdown after new writes are stopped.

**Files:** `backend/app/runtime/maintenance.py`,
`backend/app/runtime/memory_store.py` (helper),
`backend/app/api/health.py`.

**Tests:** unit test asserts PASSIVE checkpoint runs without blocking active
writers. Android field check under concurrent voice/text writes confirms no
long request pause (> 500ms attributable to checkpoint). Shutdown/idle test
asserts TRUNCATE can shrink WAL when no writers are active.

**Risk:** PASSIVE may not shrink WAL immediately. Prefer non-blocking behavior
on old Android; TRUNCATE is reserved for idle/shutdown.

### STAB-023 — No routine rolling DB backup

**Fix:** New `DatabaseBackupManager` runs from maintenance worker once per
day (configurable) and before every schema migration. Uses
`sqlite3.Connection.backup()` (online API) to write to
`backend/data/backups/pet-YYYYMMDD-HHMMSS.db` or
`pre-migration-<version>-YYYYMMDD-HHMMSS.db`. Keep 7 most recent routine
backups plus the last 3 pre-migration backups; prune older. Surface last
backup time and last pre-migration backup in deep health.

**Files:** new `backend/app/runtime/backup.py`,
`backend/app/runtime/maintenance.py`.

**Tests:** unit test creates backup, restores from it, asserts data integrity.
Migration test asserts backup is created before `PRAGMA user_version` changes.
Concurrent write test on old Android profile confirms backup does not block
normal writes for more than a short bounded window.

**Risk:** disk space on phone. 200KB DB × 7 = 1.4MB, negligible. Configurable
retention.

### STAB-037 — No production incident breadcrumbs

**Fix:** Implement CC-8. Provider error wrapper writes a row on each
`ProviderError`. Audio job failures write a row. `scripts/termux_service_manager.sh`
on restart writes via `curl -X POST /api/internal/incident` (or appends to a
file the backend reads on startup if API is unreachable). The internal incident
endpoint is protected by CC-0: loopback plus shared secret / internal token.
The shared secret comes from `DEBUG_INTERNAL_TOKEN` or
`backend/data/secrets/internal_token`, so manager and backend use the same
stable token across restarts.
Expose at `GET /api/debug/incidents?limit=50` behind the debug token.

**Files:** `backend/app/runtime/incident.py`,
`backend/app/api/debug.py`,
`scripts/termux_service_manager.sh`.

**Tests:** simulate provider failure, assert row inserted. Assert oldest
rows pruned past cap. Assert incident/debug endpoints reject missing token.

**Risk:** incident write failure must not break the request that triggered
it. Wrap in try/except, log to runtime.log on failure.

### STAB-017 — Wake/exit phrases fail when ASR fails

**Fix:** Add a lightweight wake-word path that runs even when full ASR fails:
- For V1.1, parse only existing `AudioUnderstanding` fields: `user_text`,
  `tone_notes`, and `non_verbal`.
  If ASR is empty but these fields contain configured wake phrases
  (`"momo"`, `"莫莫"`, etc.) with sufficient provider confidence, treat as
  wake.
- If confidence is low, text is ambiguous, or only non-verbal cues are present,
  do not wake; instead record `wake_source="none"` and optionally ask for
  clarification when the frontend is already active.
- Optionally integrate a tiny offline keyword spotter (e.g. Vosk small
  Chinese model, ~50MB) gated by config flag — defer to Phase 4 if size
  is a concern. Document this as Phase 2.5 stretch.
- Always include `wake_source` in response: `"asr"`, `"audio_keyword"`,
  `"offline"`, `"none"`.

**Files:** `backend/app/runtime/voice_pipeline.py`,
`backend/app/runtime/wake_detector.py` (new, lightweight only).

**Tests:** unit test where ASR returns empty but `user_text` or `tone_notes`
includes a wake keyword, assert wake activation fires only above threshold.
Add low-confidence and ambient false-wake fixtures that must not wake.

**Risk:** false wakes from ambient noise. Require `confidence >= threshold`
on the audio understanding side and exact/near-exact phrase match; log
near-miss counts for threshold tuning.

---

## Phase 3 — Frontend UX Resilience (2–3 days)

### STAB-016 — Frontend waits 15s for audio while backend may need much longer

**Fix:** Read frontend-safe audio timing from CC-9
`/api/runtime/client-config` once on app load. Do not read
`/api/health/deep`, because deep health is debug-token-protected and contains
operator details. Set frontend wait based on public config:
- primary timeout 30s + fallback 60s → frontend waits 90s
- show progressive copy: 0–5s `"莫莫在准备声音"`, 5–30s `"莫莫好像有点慢"`,
  30s+ `"声音可能要再等一下"`, fail at backend deadline + 5s buffer.

**Files:** `frontend/src/App.tsx`, `frontend/src/api.ts`,
`backend/app/api/runtime.py` or new `backend/app/api/client_config.py`.

**Tests:** Vitest mock that backend stalls 20s, assert progressive copy
appears, then audio plays. API test asserts `/api/runtime/client-config`
contains no provider key, proxy, DB, or incident fields.

**Risk:** users may give up before the 90s deadline. Add a "重试发声" button
that re-calls the audio job endpoint.

### STAB-028 — Tick decay can push Momo to extremes

**Fix:** In `tick_service.apply_if_due()`:
- Replace linear per-interval decay with logistic / saturating curve:
  `delta = base * (1 - current/100)` so decay slows as state nears the
  edge.
- Add "rest while away" bonus: if `idle > 6h` and previous state was
  `energy < 50`, recover energy by `+min(20, 6h_idle / 3h)`.
- Charging signal (when device_state populated by frontend or
  ADB-bridged) accelerates rest recovery.

**Files:** `backend/app/runtime/tick.py`,
`backend/app/pet/state.py` (state delta helpers).

**Tests:** snapshot tests over 24h idle, assert energy never reaches 0
without explicit interaction, assert loneliness doesn't pin at 100 forever.

**Risk:** the curve must still feel "alive". Tune in field.

### STAB-030 — Frontend has no explicit online/offline recovery

**Fix:** Add `useNetworkState()` hook listening to `navigator.onLine`,
`online`/`offline` events. Show a small "正在重新连接 momo" banner during
offline. Polling pauses while offline; on return, calls `POST
/api/pet/session/resume` (from STAB-027) to apply decay once.
`requestJson()` adds 8s timeout + 2 retries with exponential backoff.

**Files:** `frontend/src/App.tsx`, `frontend/src/hooks/useNetworkState.ts`,
`frontend/src/api.ts`.

**Tests:** Vitest with mocked offline/online, assert UI states.

**Risk:** none significant.

### STAB-031 — Frontend dist not tied to source version

**Fix:**
1. Vite build writes `frontend/dist/build-info.json` containing `{ git_sha,
   build_time, source_hash }` (use a small Vite plugin).
2. Backend reads it on startup and exposes via `/api/health.build_hash`.
3. Frontend reads it on load and shows in a footer/debug panel.
4. `scripts/start.sh` warns if `dist/build-info.json` is missing or if
   `dist/` mtime is older than `frontend/src/` mtime.
5. Consider committing `dist/` (remove from `.gitignore`) for V1.1 to lock
   the deployed bundle to source — discuss with the team before changing
   gitignore.

**Files:** `frontend/vite.config.ts`, `frontend/dist/.gitkeep` or
gitignore change, `backend/app/main.py` (read build-info), `scripts/start.sh`.

**Tests:** build runs, build-info.json is present, health endpoint returns
the SHA.

**Risk:** committing `dist/` increases repo size. Alternative: nightly CI
job that builds and uploads dist to release artifact, plus a deploy script
that downloads it.

---

## Phase 4 — Hardening (1–2 days)

### STAB-018 — Upload validation only checks content-type and size

**Fix:** After saving the upload (already cheap from STAB-013 streaming),
validate magic bytes:
- WAV: bytes 0–3 == `b"RIFF"`, bytes 8–11 == `b"WAVE"`.
- MP3: ID3 header or `0xFF 0xFB`.
- OGG: `b"OggS"`.
- WebM: `b"\x1A\x45\xDF\xA3"`.

If mismatch, delete file and return 400 with `error_class: "invalid_audio"`.

**Files:** `backend/app/api/voice.py`,
`backend/app/runtime/audio_validation.py` (new).

**Tests:** unit test with truncated/wrong-magic file returns 400.

**Risk:** none significant.

### STAB-026 — Memory card rebuild needs explicit locking

**Fix:** Add `self._rebuild_lock = threading.RLock()` to `MemoryCardManager`,
acquire in `rebuild()`, `clear()`, `read_with_provenance()`. Keep atomic file
writes as today.

**Files:** `backend/app/runtime/memory_card_manager.py`.

**Tests:** concurrency test fires 5 parallel `rebuild()` calls, asserts all
return successfully, asserts final card content matches single-rebuild
expected output.

**Risk:** none significant.

### STAB-032 — CORS/auth hardening follow-through

**Fix:** Phase 0 lands the minimum allowlist + token gate before any debug or
internal endpoint. Phase 4 tightens the operator experience:
1. Move hard-coded dev origins into config and document the Nubia LAN origin.
2. Add token rotation / re-pair command for the local browser.
3. Add audit breadcrumbs for rejected debug/internal requests without logging
   token values.
4. Document README/operator steps for obtaining and rotating the pairing token.

**Files:** `backend/app/main.py`,
`backend/app/api/auth.py` (new),
`backend/app/api/debug.py`,
`frontend/src/api.ts` (attach token).

**Tests:** unit test that LAN-origin without token gets 403 on `/api/debug/*`,
origin not in allowlist is rejected by CORS, and token rotation invalidates the
old token.

**Risk:** breaks any external script using the API. Acceptable; document
how to whitelist.

### STAB-034 — Proxy started once but not supervised

**Fix:** In `scripts/termux_service_manager.sh`, replace
`start_proxy_once()` with `ensure_proxy_running()`, called every loop
iteration. Check port `7897` (or configured) via `nc -z 127.0.0.1 7897`. If
down, attempt restart with the same backoff logic as the runtime (separate
counter).

**Files:** `scripts/termux_service_manager.sh`.

**Tests:** manual: kill `mihomo`, observe manager restarts it within one
loop interval.

**Risk:** if proxy itself is genuinely broken, restart loops hit backoff
and stop, which is the desired behavior.

### STAB-035 — Logs fragmented and partly outside project

**Fix:**
1. Move manager log from home dotfiles to `~/Petagent/logs/manager.log`
   via env var override in `termux_service_manager.sh`.
2. Add log rotation for `runtime.log` (size-based, e.g.
   `RotatingFileHandler(maxBytes=2*1024*1024, backupCount=5)`).
3. Document log paths in `README.md` and `docs/operations.md`.

**Files:** `scripts/termux_service_manager.sh`,
`backend/app/main.py` (logging setup),
`README.md`.

**Tests:** none beyond manual verification.

**Risk:** none.

---

## Verification Strategy

### Per-phase gates

Each phase ends with these passes before merge:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest -q
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- --run
npm run build
```

Plus phase-specific field check via `ssh nubia`:

- **Phase 0:** smoke test voice with thinking on/off, confirm route metadata
  matches actual brain. Verify MiMo audio understanding via known-empty WAV.
  Confirm debug/internal endpoints reject missing token before Phase 2 endpoints
  are added.
- **Phase 1:** burst-upload test, check RSS stays < 80MB, no manager restart,
  light health < 50ms and watchdog < 100ms even during saturated heavy routes,
  deep health < 500ms when called with token. Reboot phone and confirm the
  manager's default-browser intent makes the browser foreground visible within
  `FRONTEND_STARTUP_SECONDS=120s`, heartbeat age < 90s, 24h proactive continues
  with bounded queue size and zero provider/TTS calls while no frontend is
  connected, and closing the browser triggers relaunch/recovery. Kill -9 the
  runtime, restart, confirm pending audio jobs are marked failed and frontend
  gets structured 404.
- **Phase 2:** confirm provider failures expose structured classes, circuit
  breaker/probes behave under mocked outages, PASSIVE WAL checkpoint does not
  block concurrent writes, and pre-migration backup is created before schema
  version changes.
- **Phase 3:** simulate Wi-Fi drop and frontend reconnect. Confirm frontend
  reads `/api/runtime/client-config` rather than deep health. Leave browser
  closed for 1 hour, reopen, and confirm Momo state didn't crater because
  backend scheduler kept bounded proactive state.
- **Phase 4:** issue cross-origin request from a different LAN IP, confirm
  CORS rejects. Stop proxy, confirm manager restarts it.

### Field acceptance signals

The release is ready when:
- Manager log shows zero `CRITICAL: PetAgent failed 5 times` entries over
  72 hours of normal use.
- `/api/health/watchdog` reports `core_ready=true` within 10s of a
  manager-triggered restart.
- `/api/health/watchdog` reports `frontend_heartbeat_age_s < 90` during normal
  foreground operation, and browser relaunch restores heartbeat after closure.
- During 16+ concurrent heavy requests, `/api/health` and
  `/api/health/watchdog` remain responsive and manager does not restart.
- With browser closed for 24h, proactive backlog remains bounded and no
  provider/TTS calls are made for background proactive work.
- A typical voice round-trip (record → response with audio) completes in
  < 8s on fast path; thinking path < 20s.
- WAL size normally stays under 5MB; PASSIVE checkpoints never create long
  writer stalls, and TRUNCATE runs only during idle/shutdown.
- Frontend reconnects gracefully across Wi-Fi switch.

---

## Rollout Order Recap

Aligned with the suggested fix order in `stability-issues.md`:

1. STAB-002 + provider error class skeleton (Phase 0 / CC-1 stub)
2. STAB-003, STAB-004 (Phase 0)
3. STAB-032 minimal CORS/internal token gate + protected endpoint inventory (Phase 0 / CC-0)
4. STAB-027, STAB-029 (Phase 0)
5. STAB-015 (CC-6 SQLite AudioJobStore) before lifespan (Phase 1)
6. STAB-006, CC-4 lifespan/shutdown skeleton (Phase 1)
7. STAB-036, CC-3 light/watchdog/token-protected deep health + CC-9 client config (Phase 1)
8. STAB-007 app-level heavy-route gates preserving health lane (Phase 1)
9. STAB-008 startup/manager backoff using lifespan + watchdog (Phase 1)
10. STAB-001 heartbeat + default-browser intent autostart + bounded backend scheduler (Phase 1)
11. STAB-009, CC-5 maintenance worker (Phase 1)
12. STAB-005 versioned dispatcher snapshot/commit + STAB-010 provider gate (Phase 1)
13. STAB-013, STAB-014 upload/audio CPU fixes (Phase 1)
14. STAB-024 (CC-7), STAB-025 (Phase 2)
15. STAB-019-full, STAB-020, STAB-011, STAB-012 (Phase 2)
16. STAB-022, STAB-023 WAL/checkpoint/backup (Phase 2)
17. STAB-017 wake fallback from existing fields (Phase 2)
18. STAB-031, STAB-016, STAB-028, STAB-030 (Phase 3)
19. STAB-018 upload magic validation, STAB-032 hardening, STAB-034, STAB-035 (Phase 4)

Phase 1 and Phase 2 can partially parallelize after CC-0, CC-1, CC-3, CC-6,
and CC-9 land. CC-4 must wait for CC-6 so shutdown has durable audio job state;
STAB-008 background warmup must wait for CC-4.

---

## Out-of-Scope For V1.1

- Full Android-side service/WebView shell (STAB-001 option c).
- Offline ASR / wake spotter (mentioned in STAB-017 stretch; size cost too
  high for first pass).
- Multi-tenant pairing (single user assumption holds for V1.1).
- Distributed tracing / OpenTelemetry (incident table is enough for now).
