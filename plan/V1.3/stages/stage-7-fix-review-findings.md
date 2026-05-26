# Stage 7: Fix Review Findings Plan

**Date:** 2026-05-26
**Mode:** planning only. Do not modify implementation code until this plan is reviewed.
**Goal:** Close the V1.3 review gaps found after Stages 1-6, with tests written or changed before implementation in each task.

## Execution Protocol

This stage follows the same disciplined protocol as earlier V1.3 stages:

1. Treat this document as the reviewed stage plan after main-agent review.
2. Implement tasks in order unless a test dependency forces a narrower swap.
3. For every task, write/update tests first and confirm the intended failure before implementation.
4. After each task, run the task's minimal tests and leave the worktree in a coherent state.
5. After Tasks 1-6, run the final local verification and Nubia verification.
6. Record final results in a new Stage 7 completion document:
   `plan/V1.3/stages/stage-7-fix-review-findings-completion.md`.
7. Do not overwrite Stage 6 completion records. If Stage 6 documentation is inaccurate, mention that in Stage 7 completion instead of rewriting history.
8. Commit and push only after the main agent reviews the completed implementation and verification output.

## Background

Stage 1-6 completed most V1.3 work, but follow-up review and Nubia smoke testing found several contract gaps. The highest risk issues are those that can freeze the old Nubia runtime, silently call providers from default pet interactions, or inject forbidden context into Thinking Mode prompts.

Current observed state before this plan:

- Local git status was clean before writing this plan.
- `VoiceButton` is still press-and-hold and `App.tsx` disables the mic during `busy`, `speaking`, `waiting_voice`, and `thinking`.
- `App.tsx` has `audioRunRef` but no owned `Audio` ref, so current playback cannot be stopped.
- Thinking Mode still uses `PetBrain.generate_action()` -> `build_pet_messages()`, which serializes `current_time`, `device_state`, `output_schema`, legacy `memory_cards`, and other full-context fields.
- `TouchArea` still calls `handlePetEvent()` for all More interactions, and `handlePetEvent()` always posts `/api/pet/event`.
- Audio jobs expose `error_class`, but frontend terminal polling throws away the job object, playback errors are generic, and retry failure clears `lastAudioJobId`.
- `NotebookManager._parse_file()` caps the first 200 parseable lines, not the latest 200. Notebook writes use UTC timestamps and have no strict content length cap.
- `MemoryCardManager.rebuild()` only protects canonical files when V1.3 lines are present. Empty, comment-only, or malformed canonical files can still be overwritten by SQLite projection. `clear()` also writes legacy card headers.
- Nightly cleanup has once-per-day gating but no strict local midnight window; a daytime first tick can call the slow provider. Its timer cannot interrupt a synchronous provider call.
- Stage 6 recorded build hash `0e28d3c`, while the reviewed HEAD was `c55ba5d`; final Nubia verification must deploy and record the current commit.
- Nubia live issue: `/api/health` once returned `ok:true`, then `/api/pet/state`, `/api/audio/jobs/nonexistent`, and `/api/health` timed out while process and port 8000 were still alive. Treat this as a possible service hang until diagnosed.

## Risk Order

1. Runtime hang/provider overuse and voice interruptibility on Nubia.
2. Prompt contract violations and legacy memory source-of-truth corruption.
3. Audio error/retry UX losing recovery state.
4. Local deterministic interaction boundary.
5. Notebook ordering/timestamp/size correctness.
6. Final device verification and deployment traceability.

## Task 1: Voice Tap-To-Record And Interruptible Playback

**Findings covered:** 1.

### Target

Make voice interaction tap-based, interruptible, and recoverable:

- idle tap starts recording;
- listening tap stops and uploads;
- cancel discards the active recording;
- waiting_voice and speaking mic tap supersedes old run and starts a new recording;
- speaking tap stops the current `Audio` immediately;
- uploading/thinking tap can cancel or supersede local handling even if backend cancellation is unavailable;
- uploading/thinking cancel increments the local run id and ignores the pending response; it does not retry the same POST silently;
- mic is not disabled merely because playback or audio wait is active.

### Files

- `frontend/src/App.tsx`
- `frontend/src/components/VoiceButton.tsx`
- `frontend/src/pet/audio.ts` if the recording session type needs a clearer cancel contract
- `frontend/src/components/VoiceButton.test.tsx`
- `frontend/src/App.test.tsx`

### Tests First

1. Replace long-press VoiceButton expectations with tap-to-record:
   - first click/touch starts recording and emits `listening`;
   - second click/touch stops, uploads once, and emits `thinking` then `waiting_voice` or `idle`;
   - cancel button/action calls recording `cancel()` and returns `idle`.
2. Add VoiceButton tests for `speaking` and `waiting_voice` props:
   - button remains enabled when `disabled=false`;
   - click invokes a supplied interrupt/supersede callback before starting recording.
3. Add App tests with mock `Audio`:
   - when playback is active, tapping mic calls `pause()` or equivalent stop on the current audio object and starts a new recording;
   - the old audio `onended` must not reset UI after it was superseded;
   - `busy` text submission remains blocked, but mic interrupt stays available during `speaking` and `waiting_voice`.

### Implementation Scope

- Replace mouse/touch down/up recording semantics in `VoiceButton` with click/tap state transitions.
- Add an explicit cancel control or cancel gesture while `listening`. The visible control can be a small icon button next to the mic; it must be keyboard accessible and covered by tests.
- In `App.tsx`, add an owned `HTMLAudioElement | null` ref. `playVoice()` or its caller must store the audio object, stop/pause it on interrupt, clear event handlers, and increment `audioRunRef`.
- Split voice disabled logic:
  - text input and More buttons may stay disabled while busy;
  - mic must be enabled for `idle`, `listening`, `waiting_voice`, `speaking`, `audio_error`;
  - mic may be disabled only for explicit upload/thinking phases where allowing a new upload would duplicate POSTs, unless local supersede logic is implemented for that phase.
- Make `handleVoicePhase()` and `playResponseAudio()` use the same supersede primitive so stale poll/playback completions cannot overwrite the current run.

### Minimal Test Command

```bash
npm --prefix frontend test -- VoiceButton App
```

### Done Criteria

- No `long press` behavior or text remains in `VoiceButton`; labels describe tap state, e.g. "点一下说话" / "点一下发送".
- Mic is available during `speaking` and `waiting_voice` when not otherwise hard-disabled by permissions.
- Current audio can be stopped immediately from `App.tsx`.
- Stale audio polling/playback completions do not reset phase, bubble, or sprite.
- Upload/thinking cancel does not auto-submit a duplicate request; any old backend result is ignored locally.
- Tests fail before the implementation and pass after it.

### Rollback / Compatibility

This is frontend-only. If tap-to-record causes device-specific recorder problems, rollback is limited to `VoiceButton.tsx` plus App audio-controller wiring. Keep `createVoiceRecordingSession()` unchanged unless tests prove the session contract must change.

## Task 2: Thinking Prompt Contract And Legacy Memory Isolation

**Findings covered:** 2 and part of 6.

### Target

Thinking Mode must use a dedicated V1.3 prompt builder with only allowed fields, card-only notebook memory, and no tools/weather/device facts. Legacy `memory_cards` fallback must not enter fast or thinking prompt payloads.

### Files

- `backend/app/pet/brain.py`
- `backend/app/pet/prompt_builder.py`
- `backend/app/runtime/context_manager.py`
- `backend/app/runtime/dispatcher.py`
- `backend/tests/test_fast_reply_contract.py`
- `backend/tests/test_memory_cards.py`
- new or updated backend prompt contract tests, preferably `backend/tests/test_thinking_prompt_contract.py`

### Tests First

1. Add `test_thinking_prompt_excludes_forbidden_fields`:
   - build a context containing `current_time`, `device_state`, `skill_results`, `temporal_recall_events`, `episode_summaries`, `daily_digest`, `relevant_memories`, `important_quotes`, full `memory_cards`, and `selected_card_items`;
   - assert `build_thinking_messages()` output includes only allowed fields.
2. Add `test_brain_generate_thinking_uses_thinking_builder`:
   - patch provider to capture messages for a `thinking_mode=True` event through dispatcher;
   - assert no full `OUTPUT_SCHEMA_HINT`, no device state, no current time, no legacy cards.
3. Tighten fast reply prompt test:
   - if `selected_card_items` is absent and legacy `memory_cards` exists, fast reply `memory_hints` must be empty instead of falling back to legacy card projection.
4. Add context test:
   - for `fast_reply` and `thinking`, `context["memory_cards"]` is `None` or absent when `notebook_manager` exists; `selected_card_items` is the only prompt memory source.

### Allowed Thinking Payload

`build_thinking_messages()` may serialize:

- `user_input`;
- `recent_dialogue`, latest 6 user/pet turns;
- `pet_state`: `mood`, `energy`, `intimacy`, `sleepiness`;
- `notebook_user`: up to 8 selected `user.md` items;
- `notebook_memory`: up to 12 selected `memory.md` items;
- `response_schema`: only Thinking response fields needed for user-visible reply/state/behavior:
  `reply`, `mood`, `face_type`, `animation`, `vibration`, `state_delta`,
  `state_affect`, `behavior_intent`, and `behavior_plan`. Do not include
  `memory_update`, skill/tool schemas, device schemas, or retrieval schemas in
  V1.3 Thinking prompts.

Forbidden fields must be absent, not empty:

- `current_time`;
- `device_state`;
- `skill_results`;
- weather/device/tool facts;
- `temporal_recall_events`;
- `episode_summaries`;
- `daily_digest`;
- `relevant_memories`;
- `important_quotes`;
- legacy `memory_cards`;
- full `OUTPUT_SCHEMA_HINT` constant if it includes disabled tool/memory paths.

### Implementation Scope

- Add `build_thinking_messages(settings, event, context)`.
- Add `PetBrain.generate_thinking_action()` and call it for `decision.route == "thinking"` instead of `generate_action()`.
- Keep `build_pet_messages()` available for old/default tests or non-V1.3 paths, but do not use it from the V1.3 thinking route.
- In `build_fast_reply_messages()`, remove fallback from `memory_cards`; only consume `selected_card_items`.
- In `ContextManager.build()`, avoid loading `memory_card_manager.read_card()` for V1.3 `fast_reply` / `thinking` profiles when `notebook_manager` exists. If notebook selection fails, return empty selected items rather than falling back to SQLite projection.

### Minimal Test Command

```bash
pytest backend/tests/test_fast_reply_contract.py backend/tests/test_memory_cards.py backend/tests/test_thinking_prompt_contract.py
```

### Done Criteria

- Thinking route provider messages are produced by `build_thinking_messages()`.
- Fast and Thinking prompt JSON contain notebook-selected memory only.
- No device/time/tool/retrieval/digest/summary fields are serialized into V1.3 fast or thinking prompts.
- No `memory_update` instruction is serialized into V1.3 fast or thinking prompts; memory is handled by triggers and nightly cleanup.
- Existing thinking `PetResponse` behavior still validates through `guard_action()`.

### Rollback / Compatibility

Keep `build_pet_messages()` and old context profiles intact for tests or legacy debug routes. The rollback path is changing only the thinking branch back to `generate_action()`, but that would knowingly restore the review finding and must not ship.

## Task 3: Canonical Notebook Protection And Notebook Semantics

**Findings covered:** 5 and 6.

### Target

Protect `backend/data/memory_cards/user.md` and `memory.md` as the canonical source of truth, and make NotebookManager parse/write behavior match V1.3:

- parse latest 200 parseable lines, not first 200;
- write local Asia/Shanghai timestamps;
- enforce content length bounds;
- do not let SQLite card projection overwrite canonical files, even when files are empty, comment-only, or malformed;
- `clear()` must not rewrite canonical files in legacy projection format.

### Files

- `backend/app/runtime/notebook.py`
- `backend/app/runtime/memory_cards.py`
- `backend/app/main.py`
- `backend/tests/test_notebook.py`
- `backend/tests/test_memory_cards.py`
- `backend/tests/test_nightly_cleanup.py` if cleanup timestamp behavior is shared

### Tests First

1. Notebook latest priority:
   - create 250 valid lines;
   - assert parse result contains lines 51-250 and excludes lines 1-50;
   - assert ranking still chooses higher category first, then newer line number.
2. Notebook local timestamp:
   - freeze or monkeypatch time at a known UTC time;
   - append a line and assert timestamp is UTC+8 local time.
3. Notebook length cap:
   - append content longer than the configured maximum;
   - assert it is rejected or deterministically truncated according to the chosen rule.
   - Chosen rule: reject content over 120 CJK chars or 240 non-CJK characters, because silent truncation can corrupt user memory meaning.
4. Canonical protection:
   - `MemoryCardManager.rebuild("manual_debug")` must skip writing canonical paths when `protect_canonical=True`, even if the files are missing, empty, comment-only, or malformed.
   - `MemoryCardManager.clear()` must not write legacy headers to canonical `user.md` / `memory.md`; it may leave files untouched or create empty files with a V1.3 guard comment.
5. Startup behavior:
   - when canonical files are empty and SQLite has memories, startup must import through `NotebookManager.migrate_if_needed()` or leave files empty; it must not call `MemoryCardManager.rebuild()` onto canonical files.

### Implementation Scope

- Add explicit canonical protection flag to `MemoryCardManager`, defaulting to true when paths end with `memory_cards/user.md` and `memory_cards/memory.md`, or when config says `protect_canonical_notebook=true`.
- Make `_rebuild_locked()` return skipped stats for protected canonical files before reading SQLite.
- Make `clear()` canonical-safe.
- Move one-time legacy import responsibility to `NotebookManager.migrate_if_needed()` only.
- Change `_parse_file()` to walk lines from bottom to top until 200 parseable entries are collected, then return them in file order.
- Use local time helper in `NotebookManager` for append, import, migration, cleanup updates/adds, and backups where user-visible notebook timestamps are written. Backup filenames can remain UTC if desired, but document it in tests if kept.
- Add strict content validation to `append_line()` and cleanup add/update application.

### Minimal Test Command

```bash
pytest backend/tests/test_notebook.py backend/tests/test_memory_cards.py backend/tests/test_nightly_cleanup.py
```

### Done Criteria

- Canonical notebook files cannot be overwritten by SQLite projection rebuild or runtime reset clear.
- Latest 200 parseable notebook entries are used.
- Notebook lines written by backend use configured local time.
- Oversized memory content is rejected consistently in append and cleanup paths.
- Tests cover empty, comment-only, malformed, and valid V1.3 canonical files.

### Rollback / Compatibility

Old subdirectory projection files such as `user_preferences/card.md` and `momo_memories/card.md` may remain readable for import. Do not delete them in this task. If any legacy feature still needs projections, configure it to write only to non-canonical paths.

## Task 4: Audio Error Classes, Terminal Jobs, And Retry State

**Findings covered:** 4.

### Target

Audio terminal jobs and playback failures must surface classified UX copy and preserve retryability where possible:

- polling must retain `AudioJob.error_class`;
- `failed_runtime_restart` and `failed_shutdown` are terminal statuses in frontend polling;
- playback failures use playback-specific copy;
- retry failure does not clear the retryable old job id unless a new retry job is terminal and non-retryable;
- backend persisted restart/shutdown rows include `error_class="infrastructure"`.

### Files

- `backend/app/runtime/audio_job_store.py`
- `backend/app/runtime/audio_jobs.py`
- `backend/app/api/audio.py`
- `frontend/src/App.tsx`
- `frontend/src/pet/types.ts`
- `frontend/src/pet/errorMessages.ts`
- `frontend/src/pet/api.ts`
- `backend/tests/test_audio_retry.py`
- `frontend/src/App.test.tsx`
- `frontend/src/pet/api.test.ts`

### Tests First

1. Backend persisted infrastructure class:
   - create a pending job saved in `AudioJobStore`;
   - call `mark_restart_failed()` and `mark_shutdown_failed()`;
   - assert rows have `error_class="infrastructure"`.
2. Backend retry visibility:
   - `GET /api/audio/jobs/{id}` returns `failed_runtime_restart` and `failed_shutdown` with `error_class`;
   - `POST /retry` accepts both if text/style metadata exists.
3. Frontend polling:
   - `waitForReadyAudio()` or its refactored equivalent treats `failed_runtime_restart` and `failed_shutdown` as terminal and returns/throws an object preserving `error_class`.
4. Frontend copy:
   - `network`, `timeout`, `auth_config`, `infrastructure`, `playback`, and `unknown` map to explicit messages.
5. Retry state:
   - if `postAudioRetry(lastAudioJobId)` fails due to transient network/server error, `lastAudioJobId` remains set and retry button remains visible.
   - if retry creates a new job and that new job fails with an error class, the UI shows classified copy and stores the new job id if retryable.

### Implementation Scope

- Update `AudioJobStore.mark_restart_failed()` and `mark_shutdown_failed()` SQL to set `error_class='infrastructure'`.
- Add `failed_runtime_restart` and `failed_shutdown` to frontend terminal status handling.
- Introduce a small frontend `AudioJobError` object or equivalent so polling failures carry `status`, `job_id`, and `error_class`.
- Add `playback` error class for browser audio play/onerror failures. Do not overload provider failure classes.
- Change `playResponseAudio()` catch block to use classified copy instead of generic "声音刚刚没出来。".
- Change `handleRetryAudio()` so a failed retry request does not clear `lastAudioJobId`. Clear only after successful playback or an explicit user action that abandons retry.
- Keep raw provider error strings out of bubble copy.

### Minimal Test Command

```bash
pytest backend/tests/test_audio_retry.py
npm --prefix frontend test -- App api
```

### Done Criteria

- Every terminal audio status expected by backend is represented in frontend types and handled in polling.
- User-facing copy is selected by safe `error_class`, including browser playback failure.
- Retry preserves a usable job id after transient retry failure.
- Persisted restart/shutdown rows have infrastructure error class after process recovery.

### Rollback / Compatibility

The retry API shape stays `{"new_job_id": "..."}`. Existing ready/pending job behavior must not change. Browser playback failure is frontend-only and should not create backend jobs.

## Task 5: Local Deterministic More/TouchArea Interactions

**Findings covered:** 3.

### Target

Default More/TouchArea interactions must be local deterministic and must not call LLM/TTS. Only interactions explicitly marked `requires_model=true` may POST to `/api/pet/event`.

### Files

- `frontend/src/App.tsx`
- `frontend/src/components/TouchArea.tsx`
- `frontend/src/pet/types.ts`
- `frontend/src/pet/behaviorDirector.ts` if local interaction mapping belongs there
- `backend/app/runtime/interaction_catalog.py`
- `backend/app/api/interactions.py`
- `frontend/src/components/TouchArea.test.tsx`
- `frontend/src/App.test.tsx`
- `backend/tests/test_interaction_catalog.py`
- optional backend lightweight endpoint only if state sync is required: `backend/app/api/pet.py`

### Tests First

1. Catalog contract:
   - every interaction returned by `/api/interactions` includes `requires_model: false` unless deliberately opted in.
2. TouchArea emits the full interaction object, not just event id, so the caller can inspect `requires_model`.
3. App local interaction:
   - clicking `feed_momo`, `pet_pat`, `clean_face`, `tuck_in`, `praise_momo`, `comfort_me`, `stay_with_me`, `encourage_me`, `take_a_break`, and `play_with_momo` updates bubble/sprite locally and does not call `/api/pet/event`.
4. Explicit model interaction:
   - a test-only interaction with `requires_model: true` still calls `/api/pet/event`.

### Implementation Scope

- Extend `InteractionDefinition` with `requires_model?: boolean` and optional local fields if the backend catalog already has deterministic mood/animation labels.
- Make `handlePetEvent()` branch:
  - local default: apply deterministic mood/animation/bubble/action, no backend POST, no TTS, no global busy;
  - explicit model: existing POST path.
- Consider renaming local handler to `handleInteraction()` to avoid implying backend event.
- Keep `/api/pet/event` backward compatible for old clients and tests.
- Do not add a new backend sync endpoint in this task unless product needs persisted state for local care interactions. If state sync is needed later, use a lightweight endpoint that cannot call LLM or enqueue TTS.

### Minimal Test Command

```bash
pytest backend/tests/test_interaction_catalog.py backend/tests/test_stage4_ux.py
npm --prefix frontend test -- TouchArea App
```

### Done Criteria

- Default visible More interactions generate no `/api/pet/event`, no LLM call, and no audio job.
- `requires_model=true` remains an explicit opt-in path.
- Local reactions are immediate and deterministic.
- Backend `/api/pet/event` remains backward compatible.

### Rollback / Compatibility

If any interaction truly needs model text, set `requires_model=true` in the catalog and cover it with a test. Do not rely on missing `requires_model` to mean model-required.

## Task 6: Nightly Cleanup Window, Hang Diagnostics, And Final Nubia Verification

**Findings covered:** 7 and 8.

### Target

Avoid slow cleanup work during active daytime use, define the provider timeout limitation clearly, and perform a stronger Nubia smoke after fixes with the current deployed commit hash.

### Files

- `backend/app/runtime/nightly_cleanup.py`
- `backend/app/runtime/maintenance.py`
- `backend/app/runtime/maintenance_worker.py`
- `backend/app/api/health.py`
- `backend/tests/test_nightly_cleanup.py`
- `backend/tests/test_phase1_health.py` or new health tests
- `plan/V1.3/stages/stage-7-fix-review-findings-completion.md` after live verification, not in this planning task

### Tests First

1. Nightly cleanup window:
   - `should_run()` returns true only in a configured local window, chosen as `00:00 <= local time < 01:00`;
   - once-per-day still prevents duplicate runs inside the window;
   - `force=True` or direct test hook can bypass the window for tests/manual maintenance only.
2. Maintenance ordering:
   - a daytime first maintenance tick does not call `nightly_cleanup_runner.run()`.
3. Provider call timeout limitation:
   - document in tests or code comments that the existing `threading.Timer` can prevent post-provider apply but cannot kill a synchronous provider call already in progress.
   - acceptable V1.3 fix: never start this call outside the midnight window, and run it only in the maintenance worker thread, never request thread.
4. Health diagnostics:
   - add a lightweight health/watchdog test that reports `active_requests`, event loop tick age, provider inflight age, and audio queue without DB locks.

### Implementation Scope

- Add configurable cleanup window to `NightlyCleanupRunner`, default Asia/Shanghai 00:00-01:00.
- Add an injectable clock or `_get_local_now()` method so tests can freeze local time cleanly.
- Let `NightlyCleanupRunner.run(force=False)` pass the force flag through `should_run(force=force)`.
- Ensure `MaintenanceService.tick()` calls nightly cleanup only when `should_run()` is true inside the window.
- Keep provider call in the maintenance worker only. Do not attempt unsafe thread killing in V1.3.
- Strengthen health docs/tests around "process alive + port listening but requests timeout" diagnosis.

### Minimal Test Command

```bash
pytest backend/tests/test_nightly_cleanup.py backend/tests/test_phase1_health.py
```

### Nubia Verification Procedure

Run only after Tasks 1-6 pass locally and the reviewed commit is deployed.

1. Record local commit:
   ```bash
   git rev-parse --short HEAD
   ```
2. Build frontend:
   ```bash
   npm --prefix frontend run build
   ```
3. Run backend focused suite:
   ```bash
   pytest backend/tests/test_fast_reply_contract.py backend/tests/test_memory_cards.py backend/tests/test_notebook.py backend/tests/test_nightly_cleanup.py backend/tests/test_audio_retry.py backend/tests/test_voice_pipeline.py backend/tests/test_interaction_catalog.py backend/tests/test_stage4_ux.py backend/tests/test_stage5_behavior.py
   ```
4. Run frontend focused suite:
   ```bash
   npm --prefix frontend test -- VoiceButton App TouchArea api
   ```
5. Run full local verification:
   ```bash
   pytest backend/tests
   npm --prefix frontend run build
   ```
6. Deploy to Nubia and record deployed hash in the completion document. The hash must match the current `HEAD`.
7. Nubia smoke checks:
   - `/api/health` responds under 2s and includes the deployed `build_hash`;
   - `/api/health/watchdog` responds under 2s and shows `stuck:false`;
   - `/api/pet/state` responds under 2s;
   - `/api/audio/jobs/nonexistent` returns 404 under 2s;
   - fast text greeting returns `route=fast_reply`, no tools, short reply, audio job id;
   - Thinking text returns `route=thinking`; captured or debug prompt evidence shows no current time/device/tool/retrieval fields;
   - fast voice ASR failure returns local "没听清" recovery without slow fallback;
   - TTS failure shows classified copy; reconnect/recover then retry creates a new audio job and can play;
   - mic tap during speaking stops current playback and starts a new recording;
   - More default interactions do not create audio jobs and do not POST `/api/pet/event`;
   - port-down/process-alive unhealthy case: if curl timeouts recur while process and port are alive, capture `logcat`, uvicorn stdout/stderr, `ss -ltnp`, `/api/health/watchdog` if reachable, and thread/process state before restart.

### Done Criteria

- Nightly cleanup cannot start slow provider work during daytime first tick.
- Timeout limitation is explicitly accepted and mitigated by scheduling; no plan claims synchronous provider calls can be killed mid-flight.
- Final Nubia completion records current deployed hash, exact commands, response snippets, and any timeout diagnostics.
- Stage 7 completion explicitly notes that the old Stage 6 completion deployed
  `0e28d3c`, while this verification deploys the current Stage 7 commit.

### Rollback / Compatibility

If midnight cleanup misses its 00:00-01:00 window because the device is asleep, it waits until the next night. Manual force remains available for maintenance/debug routes with internal-token protection if an endpoint already exists; do not add a public force endpoint.

## Final Full Verification

Run after all tasks:

```bash
pytest backend/tests
npm --prefix frontend run build
```

Expected result:

- backend full suite passes;
- frontend build passes (`tsc && vite build`);
- no new destructive commands, commits, or pushes during planning/execution review cycles unless explicitly requested by the main agent.

## Completion Requirements For Execution Agent

For each task:

- write or update tests first and confirm they fail for the intended reason;
- make the smallest implementation change that satisfies those tests;
- run the task's minimal test command;
- record changed files and test output in that task's completion note;
- do not combine unrelated task changes into one large patch;
- preserve user or unrelated worktree changes.

## Most Error-Prone Areas

1. **Voice supersede races:** old audio `onended`, polling loops, and upload promises can still update UI after a new run unless every path checks the current run id.
2. **Prompt leakage through context fallback:** removing forbidden fields in `build_thinking_messages()` is not enough if `ContextManager` still loads legacy `memory_cards` and the builder accidentally serializes them.
3. **Canonical memory overwrite:** startup, runtime reset, curator rebuild, memory expiration, and manual debug rebuild are separate paths; all must respect canonical notebook protection.
