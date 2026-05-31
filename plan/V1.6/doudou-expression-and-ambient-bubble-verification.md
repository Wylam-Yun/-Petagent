# PetAgent V1.6 Verification

**Date:** 2026-05-31
**V1.6 code verification commit on Nubia:** 3428ade
**Nubia runtime process:** 21774
**Nubia access path:** `adb forward tcp:18000 tcp:8000`, `adb forward tcp:18022 tcp:8022`, `ssh nubia-adb`
**Deployment rule:** 后续部署统一使用 `adb forward tcp:18022 tcp:8022` + `ssh nubia-adb`，不依赖 Wi-Fi 直连 `ssh nubia`。

## Backend

- Targeted tests: pass
  - `tests/test_v16_expression_contract.py`
  - `tests/test_v16_ambient_policy.py`
  - `tests/test_v16_ambient_api.py`
  - `tests/test_v16_idle_debug.py`
  - `tests/test_fast_reply_contract.py`
  - `tests/test_text_chat.py`
  - `tests/test_voice_pipeline.py`
  - `tests/test_v15_failure_contract.py`
- Full tests: pass, `733 passed, 24 skipped`

## Frontend

- Targeted tests: pass, `46 passed`
- Full tests: pass, `149 passed`
- Production build: pass, `npm run build`

## Review Fixes

- Kaomoji guard is sourced from the expression catalog and rejects catalog faces such as `(´・ω・)` and `(≧▽≦)` before TTS.
- Ambient generation uses the fast brain while holding the `llm_fast` gate.
- Ambient validation rejects `expression_key` or `action` that does not match the selected `suggested_activity` recommendation, so mismatched LLM output fails instead of being normalized.
- Frontend confirms ambient pending events only after rechecking page visibility and idle state; hidden or interrupted displays are cancelled.
- Local ambient backoff advances only when `/api/pet/ambient/confirm` returns `ok: true`.
- Client config loading uses the same fetch/XHR transport fallback as other frontend API calls.

## Nubia

- ADB forward: pass
  - Device: `9debb82b NX531J`
  - Forward: `tcp:18000 -> tcp:8000`
- SSH/Termux restart: pass
  - `ssh nubia-adb 'cd ~/Petagent && scripts/stop.sh && scripts/start.sh'`
  - Termux context: `scripts/status.sh` returned `context: ok`
- Health: pass
  - `/api/health` returned `"ok": true`
  - `/api/health/watchdog` returned `"ok": true`, `stuck: false`
- Foreground expression: pass
  - `/api/text/chat` with `你是不是又偷懒了` returned whitelisted `expression_key: playful`
  - `reply` had no kaomoji and did not contain `豆豆`
- TTS excludes expression: pass
  - Audio job `aud-f14f14bd9c22` reached `ready`
  - `/api/debug/idle-state` showed `last_submitted_tts_text` equal to sanitized `reply`
  - `last_submitted_tts_text` did not include the expression key or kaomoji
- Ambient trigger: pass
  - `/api/pet/ambient/trigger` returned `active: true`
  - Returned `bubble: 我困得眼皮打架了……`
  - Returned `expression_key: sleepy`, `action: lazy_idle`
  - Returned `audio_job_id: null`, `voice_url: null`
  - Runtime source was `llm_generated`
- Ambient confirm/cancel: pass
  - Confirming `ambient-20260531054630078877-07fc5f8d` returned `ok: true`
  - Debug state advanced to `daily_count: 1`, `backoff_step: 1`
- Backoff: pass
  - `idle_step: 1`, `idle_elapsed_ms: 599999` returned `too_early`
  - `idle_step: 1`, `idle_elapsed_ms: 600000` returned eligible
- Blockers: pass
  - `input_active`, `recording`, `waiting_llm`, `waiting_tts`, `playing_tts`, `busy`, `screen_off`, and `page_hidden` all returned explicit block reasons
- Activity limits and daily cap: pass
  - Temporary SQLite test rows on future local dates verified `daily_limit`
  - Temporary SQLite test rows verified activity selection skipped already-limited and same-class entries
  - Temporary rows were deleted after verification
- Debug idle state: pass
  - Missing token returned `403`
  - Token-protected endpoint returned `daily_count`, `activity_counts`, `last_submitted_tts_text`, `last_rendered_expression_key`, and `last_idle_bubble_source`

## Notes

- Nubia code verification `/api/health` returned `build_hash: 3428ade`, `pid: 21774`, and `ok: true`.
- Final Nubia `/api/health/watchdog` returned `ok: true`, `stuck: false`.
- Final Nubia runtime guard check returned `mismatch_rejected True` for a `stay_near` activity paired with `sneak_eat`, proving the deployed code rejects activity/action mismatches instead of normalizing them.
