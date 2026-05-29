# V1.4 Stage 8 Completion: Nubia Voice Stability

**Date:** 2026-05-29
**Scope:** urgent production stability fix after real Nubia voice no-reply

## Result

The no-reply symptom was traced to an HTTP half-alive runtime on the Nubia. The
process and port stayed alive, but health, client config, and audio polling
requests stopped returning. Recent persisted voice turns had actually completed,
and their audio jobs were ready, so the main failure was service availability
and frontend timeout behavior rather than a missing model response.

The fix removes the old online SQLite backup/WAL maintenance layer, makes the
Termux manager recover half-alive HTTP states, clears deleted remote code during
deploy, and gives voice uploads a realistic request budget.

## Root Cause

Evidence from the device:

- `/api/health` through adb forward timed out while the port was listening.
- Recent `agent_run`, `audio_job`, and `raw_event_log` rows showed completed
  voice turns and ready audio jobs.
- The stuck process held a zero-byte routine backup file under
  `backend/data/backups/`.
- Runtime logs included `sqlite3.OperationalError: database table is locked`.
- The service manager previously launched runtime with `PETAGENT_FOREGROUND=1`,
  so uvicorn replaced the manager loop and prevented watchdog recovery.

## Why SQLite Was Kept

`pet.db` is still active application state, not an obsolete memory database. It
stores current pet state, raw event log, agent-run records, audio jobs, device
state, activation state, incidents, and memory-related queues.

The removed code was the redundant online backup/WAL maintenance layer:

- `backend/app/runtime/backup.py`
- routine `DatabaseBackupManager` wiring;
- `daily_backup_if_due`;
- `wal_checkpoint_if_due`;
- `wal_truncate_idle`;
- deep-health `PRAGMA wal_checkpoint(PASSIVE)`.

This reduces lock contention and removes a recovery hazard on the old phone
without deleting the state database.

## Code Changes

- `backend/app/api/health.py`
  - deep health now avoids WAL checkpoint and no longer returns `wal_bytes`.
- `backend/app/main.py`
  - removed `DatabaseBackupManager` construction and injection.
- `backend/app/runtime/maintenance.py`
  - removed online backup and WAL checkpoint/truncate scheduling state.
- `backend/app/runtime/maintenance_worker.py`
  - removed periodic WAL/backup calls and shutdown WAL truncate.
- `scripts/termux_service_manager.sh`
  - starts runtime with `PETAGENT_FOREGROUND=0`;
  - restarts repeated HTTP half-alive states after `HTTP_FAIL_MAX=2`;
  - also handles the orphan-port case where the pid file is stale or missing.
- `scripts/deploy_nubia.sh`
  - clears remote code directories before unpacking so deleted modules disappear
    from the phone.
- `frontend/src/pet/api.ts`
  - voice upload timeout is now 30s for fast mode and 60s for thinking mode.
  - timeout still fires on old WebViews without `AbortController`.
- `frontend/src/components/VoiceButton.tsx`
  - timeout/abort copy now tells the user to retry instead of implying 豆豆 has
    no voice.

## Local Verification

Frontend focused tests:

```bash
npm --prefix frontend test -- --run \
  src/pet/api.test.ts \
  src/components/VoiceButton.test.tsx \
  src/App.test.tsx \
  src/pet/audio.test.ts
```

Result:

```text
4 files, 35 tests passed
```

Backend focused tests:

```bash
pytest backend/tests/test_phase1_startup.py \
  backend/tests/test_phase1_maintenance.py \
  backend/tests/test_phase4_hardening.py \
  backend/tests/test_phase1_health.py \
  backend/tests/test_voice_contract.py \
  backend/tests/test_voice_pipeline.py -q
```

Result:

```text
59 passed
```

Maintenance constructor/regression tests after deleting the dead connection
parameter:

```bash
pytest backend/tests/test_stage36_maintenance.py \
  backend/tests/test_stage37_daily_auto.py \
  backend/tests/test_stage37_cleanup.py \
  backend/tests/test_stage37_singleflight.py \
  backend/tests/test_memory_cards.py -q
```

Result:

```text
51 passed
```

Runtime reference check:

```text
No remaining runtime references to DatabaseBackupManager, backup_manager,
daily_backup_if_due, wal_checkpoint_if_due, wal_truncate_idle, wal_bytes, or
PRAGMA wal_checkpoint.
```

Historical V1.1 plan files still mention those terms as old design records only.

## Nubia Verification

Deployment:

```bash
BUILD_FRONTEND=1 ./scripts/deploy_nubia.sh
```

Device checks:

- remote `backend/app/runtime/backup.py` absent;
- remote runtime/config/scripts contain no active online backup/WAL checkpoint
  references;
- `/api/health` returned `ok=true`, `name=豆豆`;
- `/api/health/watchdog` returned `stuck=false`, `audio_queue_depth=0`;
- `/api/health/deep` returned quickly and no longer includes `wal_bytes`.

Real Nubia voice API chain:

```text
input audio: 早上好豆豆，今天你开心吗？
ASR text: 早上好豆豆，今天你开心吗？
reply: 早呀主人～今天超开心的！刚偷偷把小本本翻出来记了咖啡事，想给你整点惊喜呢～
action: happy
audio_job_id: aud-f65006b778f0
voice total: 5046ms
ASR: 2569ms
brain + TTS enqueue: 2477ms
audio job: ready
TTS job: 1060ms
voice_url: /static/audio/reply-20260529-123137-e218319e.mp3
```

Automated live suite:

```bash
PETAGENT_TEST_URL=http://127.0.0.1:18000 \
PETAGENT_INTERNAL_TOKEN=... \
pytest backend/tests/test_live_nubia.py -q --tb=short
```

Result:

```text
21 passed in 7.59s
```

## Residual Risks

- This verification used a real Nubia `/api/voice/chat` upload over adb forward,
  not automated physical tapping of the WebView microphone button. The full
  backend voice path and audio-job polling were exercised on-device.
- The runtime log still contains old pre-fix lock lines until log rotation.
  Post-fix checks should compare entries after the latest runtime start.
- If Termux itself kills background processes aggressively, the documented
  foreground runtime remains the most reliable manual live-test path; normal
  operation should use the Termux service startup path.

## Acceptance Criteria Audit

- Issue documented under V1.4: yes.
- Redundant online DB backup/WAL maintenance removed: yes.
- SQLite state database preserved intentionally: yes.
- Frontend request timeout aligned with real voice latency: yes.
- Deployment removes deleted remote code: yes.
- Local focused tests pass: yes.
- Nubia health/watchdog/deep health pass: yes.
- Nubia real voice API returns reply and ready audio: yes.
- Nubia live API suite passes: yes.
