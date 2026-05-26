# Stage 7 Fix Review Findings Completion

**Date:** 2026-05-26
**Status:** COMPLETE - Tasks 1-6 implemented, reviewed, locally verified, and prepared for final Nubia deployment verification.

## Scope Completed

### Task 1: Voice Tap-To-Record And Interruptible Playback

Completed:

- `VoiceButton` now uses tap-to-record:
  - tap idle starts recording;
  - tap listening stops and uploads;
  - cancel recording discards the active session;
  - tap during `waiting_voice`, `speaking`, or `audio_error` interrupts the current response and starts a new recording.
- `App.tsx` owns the active `Audio` object through a ref and can stop playback immediately.
- Stale audio polling/playback completion is guarded by `audioRunRef`.
- Text and More interactions remain protected while busy; voice can still interrupt user-visible audio phases.

### Task 2: Thinking Prompt Contract And Legacy Memory Isolation

Completed:

- Added `build_thinking_messages()` with a V1.3-only payload.
- Added `PetBrain.generate_thinking_action()`.
- Dispatcher now routes `decision.route == "thinking"` through the Thinking prompt builder.
- Fast Reply and Thinking no longer fall back to legacy `memory_cards` projection.
- `ContextManager` avoids loading legacy `memory_cards` for V1.3 `fast_reply` / `thinking` when `NotebookManager` is present.
- Thinking prompt schema excludes `memory_update`, tools, device schema, retrieval schema, current time, and device state.

### Task 3: Canonical Notebook Protection And Notebook Semantics

Completed:

- `NotebookManager._parse_file()` now uses the latest 200 parseable lines and returns them in file order.
- Notebook writes now use local UTC+8 timestamps for user-visible memory lines.
- `append_line()` and cleanup add/update paths reject oversized content.
- `MemoryCardManager.rebuild()` skips protected canonical notebook files before reading SQLite.
- `MemoryCardManager.clear()` no longer rewrites protected canonical notebooks with legacy `memory_cards:` headers.
- Runtime reset behavior preserves protected V1.3 canonical notebook files.

### Task 4: Audio Error Classes, Terminal Jobs, And Retry State

Completed:

- `AudioJobStore.mark_restart_failed()` and `mark_shutdown_failed()` now persist `error_class = "infrastructure"`.
- `AudioJobManager.mark_restart_failed()` and `mark_shutdown_failed()` keep in-memory jobs retryable and visible.
- Superseded in-memory jobs now also receive `error_class = "infrastructure"` for contract consistency.
- Frontend treats `failed_runtime_restart` and `failed_shutdown` as terminal audio statuses.
- `AudioJobError` carries `error_class`, status, and job id.
- Browser playback failures map to the `playback` UX class.
- Retry request failure keeps the retry button/job id unless the response was superseded.

### Task 5: Local Deterministic More Interactions

Completed:

- `InteractionDef` has `requires_model: bool = False`.
- `/api/interactions` returns `requires_model`.
- Frontend `InteractionDefinition` supports optional `requires_model`.
- `TouchArea` emits the full interaction object.
- `App.handlePetEvent()` updates mood, animation, and bubble locally for default interactions.
- Only explicit `requires_model === true` interactions POST `/api/pet/event`.

### Task 6: Nightly Cleanup Window And Nubia Guardrails

Completed:

- `NightlyCleanupRunner.should_run(force=False)` only runs inside local `00:00 <= time < 01:00`.
- `NightlyCleanupRunner.run(force=False)` honors the same window.
- `force=True` bypasses the time window for explicit manual/debug runs.
- `MaintenanceService.tick(force=...)` passes the force flag through.
- Tests freeze `_get_local_now()` and cover before-window, in-window, after-window, once-per-day, force, and app-state integration.

## Review Results

Subagent review result:

- Blocking implementation issues: none.
- Blocking sign-off issue: this completion document was stale and still said Tasks 4-6 were not executed. Fixed here.
- Low non-blocking issue: superseded in-memory audio jobs had an empty `error_class`. Fixed in `backend/app/runtime/audio_jobs.py` and covered in `backend/tests/test_audio_jobs.py`.

## Files Changed

- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `frontend/src/components/VoiceButton.tsx`
- `frontend/src/components/VoiceButton.test.tsx`
- `frontend/src/components/TouchArea.tsx`
- `frontend/src/components/TouchArea.test.tsx`
- `frontend/src/pet/api.test.ts`
- `frontend/src/pet/errorMessages.ts`
- `frontend/src/pet/types.ts`
- `backend/app/api/interactions.py`
- `backend/app/pet/brain.py`
- `backend/app/pet/prompt_builder.py`
- `backend/app/runtime/audio_job_store.py`
- `backend/app/runtime/audio_jobs.py`
- `backend/app/runtime/context_manager.py`
- `backend/app/runtime/dispatcher.py`
- `backend/app/runtime/interaction_catalog.py`
- `backend/app/runtime/maintenance.py`
- `backend/app/runtime/memory_cards.py`
- `backend/app/runtime/nightly_cleanup.py`
- `backend/app/runtime/notebook.py`
- `backend/tests/test_audio_jobs.py`
- `backend/tests/test_audio_retry.py`
- `backend/tests/test_fast_reply_contract.py`
- `backend/tests/test_interaction_catalog.py`
- `backend/tests/test_memory_cards.py`
- `backend/tests/test_nightly_cleanup.py`
- `backend/tests/test_notebook.py`
- `backend/tests/test_thinking_prompt_contract.py`
- `plan/V1.3/stages/stage-7-fix-review-findings.md`
- `plan/V1.3/stages/stage-7-fix-review-findings-completion.md`

## Local Verification

Focused audio verification:

```bash
pytest backend/tests/test_audio_jobs.py backend/tests/test_audio_retry.py -q
```

Result:

- `24 passed`

Full backend verification:

```bash
pytest backend/tests -q
```

Result:

- `652 passed, 24 skipped`

Full frontend verification:

```bash
npm --prefix frontend test -- --run
```

Result:

- `17 test files passed`
- `126 tests passed`

Frontend production build:

```bash
npm --prefix frontend run build
```

Result:

- build passed
- generated `frontend/dist/build-info.json`
- current pre-commit source build hash at build time: `c55ba5d`

## Nubia Verification Already Performed During This Stage

Device:

- `adb devices -l` detected `NX531J`.

Deployment:

- Project was copied to `/data/data/com.termux/files/home/Petagent`.
- Runtime data and secrets were preserved:
  - `.env`
  - `.venv`
  - `backend/data`
  - `backend/secrets`
- Frontend `dist` was copied to the device.

Pre-final-commit live checks passed:

- `python -m pytest backend/tests/test_live_nubia.py`
  - `21 passed`
- `/api/health`
  - `ok:true`
  - `name:"豆豆"`
  - build hash reported by that deployed build: `c55ba5d`
- `/api/health/watchdog`
  - `ok:true`
  - `stuck:false`
- `/api/pet/state`
  - 200 OK
- `/api/audio/jobs/nonexistent`
  - 404 JSON response
- `/api/interactions`
  - all default interactions returned `requires_model:false`
- `/`
  - HTML title `豆豆`
- sprite asset
  - `/assets/spritesheet-TBTZxMSe.webp` returned 200
- fast text smoke
  - input: `早上好豆豆`
  - route: `fast_reply`
  - tools: none
  - observed LLM latency: about `1204ms`
  - observed API latency: about `1256ms`
  - audio job became `ready`
  - observed TTS latency: about `1508ms`
- thinking text smoke
  - route: `thinking`
  - tools: none
  - observed LLM latency: about `24643ms`
  - observed API latency: about `24738ms`
  - behavior plan validated

## Nubia Operational Notes

- Stage 6 documentation recorded older deployed hashes (`0e28d3c` / `1c3a10a`). Stage 7 deployment and smoke checks used the newer Stage 7 code path.
- Do not start the runtime with plain `run-as com.termux ./scripts/start.sh`; that environment can miss Termux linker variables and may leave port 8000 listening while HTTP requests time out.
- A correct Termux runtime environment needs:
  - `HOME=/data/data/com.termux/files/home`
  - `PREFIX=/data/data/com.termux/files/usr`
  - `PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets:/system/bin:/system/xbin:/su/bin`
  - `LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib`
- During this stage, a bad root-owned runtime was killed, ownership was repaired, `runtime.pid` was corrected, and health/watchdog recovered.
- Final post-commit deployment should rebuild after commit so `/api/health.build_hash` matches the pushed commit.

## Remaining Risk

- There is still no true backend cancellation for an in-flight LLM/TTS provider call. The shipped UX cancellation is local supersede/ignore plus immediate audio stop. This is acceptable for V1.3 because it protects the user experience and avoids duplicate POSTs.
- Thinking Mode remains intentionally slower than Fast Reply.
- Nubia startup can still be sensitive to Termux environment and file ownership if launched through the wrong adb/run-as path.
