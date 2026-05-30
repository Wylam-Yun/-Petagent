# V1.5 Unified Context And Stable Memory Verification

**Date:** 2026-05-30
**Branch:** `main`
**Target:** Nubia Termux runtime at `127.0.0.1:8000`

## Local Regression

- Backend: `cd backend && ../.venv/bin/python -m pytest -q`
  - Result: `704 passed, 24 skipped`
- Frontend: `cd frontend && npm test -- --run`
  - Result: `16 passed`, `143 passed`
- Whitespace check: `git diff --check`
  - Result: passed

## Nubia Deployment

- Command: `BUILD_FRONTEND=1 ./scripts/deploy_nubia.sh`
  - Result: frontend built and archive deployed.
- Service start: SSH/Termux context with `scripts/start.sh`
  - Result: runtime ready on `0.0.0.0:8000`.
- Health:
  - `GET /api/health`: `ok:true`
  - Final redeploy health was checked after commit.
  - `HEAD /`: `HTTP/1.1 200 OK`

## Nubia Live Checks

### Text Success And Ignored Thinking Mode

Request included legacy `thinking_mode:true`.

Observed response:

- `error_class:null`
- `route:"unified"`
- `runtime.context_profile:"unified"`
- `runtime.recent_dialogue_count:5`
- `runtime.memory_line_count:7`
- `text_route.thinking_mode:false`

### Voice ASR Success And Ignored Legacy Route

Request included legacy form fields `thinking_mode=true` and `route=thinking`.

Observed response:

- `ok:true`
- `user_text` non-empty
- `voice_route.requested:"auto"`
- `voice_route.selected:"unified"`
- `voice_route.thinking_mode:false`
- `voice_route.emotion_source:"asr"`
- `runtime.context_profile:"unified"`
- `runtime.recent_dialogue_count:5`
- `runtime.memory_line_count:7`

### Voice ASR Failure Is Terminal

Input: generated 1-second silent WAV.

Observed response:

- `ok:false`
- `error_class:"asr_empty"`
- `reply:""`
- `audio_job_id:null`
- `voice_route.selected:"unified"`
- `voice_route.thinking_mode:false`
- `voice_route.emotion_source:"none"`

Database counts before and after the ASR failure were unchanged:

- `raw_event_count:13`
- `audio_job_count:12`
- `successful_turn_count_total:4`
- `successful_turn_count_since_memory_summary:4`
- `last_successful_turn_event_id` unchanged

### 10 Successful Turn Memory Trigger

After six additional successful text turns:

- `successful_turn_count_total:10`
- `successful_turn_count_since_memory_summary:0`
- `last_memory_summary_event_id` set to the 10th successful event
- `memory.md` remained at `7` prompt-facing memory lines

Runtime logs showed no SiliconFlow memory-writing fallback. Memory summarization
provider selection remains MiMo-only in application startup.

## Notes

- The automatic nightly prompt-facing memory cleanup runner is disabled by
  default in V1.5. It remains available only through explicit `force=True`
  maintenance/debug calls, so normal `memory.md` updates are triggered only by
  keyword hits or every 10 successful turns.
