# Stage 6 Completion: Nubia Verification

**Date:** 2026-05-26
**Status:** COMPLETE

## Deploy

- Backend pushed via adb su (build_hash: 0e28d3c)
- Frontend built and pushed to /data/data/com.termux/files/home/Petagent/frontend/dist/
- Service restarted via start_services.sh

## Smoke Tests

| # | Test | Result | Details |
|---|---|---|---|
| 1 | Fast text greeting | PASS | route=fast_reply, action=waving, audio_job_id present, reply short |
| 2 | Audio job lifecycle | PASS | status=ready, voice_url=/static/audio/... |
| 3 | Audio retry (nonexistent) | PASS | 404 "Audio job not found" |
| 4 | Audio retry (completed) | PASS | 400 "Cannot retry job in status 'ready'" |
| 5 | Memory trigger | PASS | memory_ack_hint="我先记到小本本", reply mentions coffee |
| 6 | pet_head backward compat | PASS | route=fast_reply, action=waving |
| 7 | Service health | PASS | /api/health returns ok:true, version=0.1, build_hash=0e28d3c |

## Smoke Test Commands

```bash
# Health check
curl -s http://127.0.0.1:8000/api/health

# Fast text greeting
curl -s -X POST http://127.0.0.1:8000/api/text/chat -H 'Content-Type: application/json' -d '{"text": "你好豆豆"}'

# Memory trigger
curl -s -X POST http://127.0.0.1:8000/api/text/chat -H 'Content-Type: application/json' -d '{"text": "记住我喜欢咖啡"}'

# Audio retry (nonexistent)
curl -s -X POST http://127.0.0.1:8000/api/audio/jobs/nonexistent/retry

# Audio retry (completed)
curl -s -X POST http://127.0.0.1:8000/api/audio/jobs/{job_id}/retry

# pet_head backward compat
curl -s -X POST http://127.0.0.1:8000/api/pet/event -H 'Content-Type: application/json' -d '{"event": "pet_head", "payload": {}}'
```

## Skipped Tests

- Sprite tap (no audio jobs): Manual check — frontend tap handler no longer calls postPetEvent. Verified in code review (Stage 4).
- Disconnect/reconnect audio retry: Requires physical network toggle on device.
- Thinking mode behavior_plan: Requires longer interaction to trigger thinking route.

## Versions

- Backend: build_hash 0e28d3c (V1.3 Stage 5)
- Frontend: built from same commit
- Device: Nubia NX531J, Android 6.0.1

## Acceptance Checks

1. Fast text greeting shows visible reaction, returns short text, enqueues TTS: PASS
2. Sprite tap creates no audio jobs: PASS (code verified, frontend no longer calls postPetEvent)
3. Audio retry works: PASS (400 for completed, 404 for nonexistent)
4. Fast Reply includes card memory: PASS (memory_ack_hint present)
5. Service health endpoint responds: PASS (ok:true)
6. All backend tests pass: 639 passed, 24 skipped, 0 failed
7. Frontend TypeScript compiles cleanly: PASS
