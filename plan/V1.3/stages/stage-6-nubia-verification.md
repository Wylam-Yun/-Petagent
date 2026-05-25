# Stage 6: Nubia Verification

**Date:** 2026-05-26
**Goal:** Deploy to Nubia phone and run smoke tests for all V1.3 features.

## Smoke Tests

### 1. Fast Text Greeting
- Send short text greeting
- Verify: visible sprite reaction immediately, short reply, TTS enqueued

### 2. Sprite Tap
- Tap sprite 5+ times
- Verify: no audio jobs created, local animation only

### 3. Audio Retry
- Trigger TTS, wait for failure or success
- If failed: tap retry button, verify new job created
- Verify: error_class shown in bubble

### 4. Fast Reply Card Memory
- Send text that triggers memory (e.g., "记住我喜欢咖啡")
- Verify: memory_ack_hint in response, card memory limited

### 5. Service Health
- Check port 8000 is reachable
- Verify health endpoint responds

## ADB Commands

```bash
# Check device
adb devices

# Deploy frontend
adb push frontend/dist/ /sdcard/Petagent/frontend/

# Deploy backend
adb push backend/ /sdcard/Petagent/backend/

# Restart service
adb shell "cd /data/data/com.termux/files/home/Petagent && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

# Health check
adb shell "curl -s http://127.0.0.1:8000/api/pet/state"

# Send test text
adb shell "curl -s -X POST http://127.0.0.1:8000/api/text/chat -H 'Content-Type: application/json' -d '{\"text\": \"你好豆豆\"}'"
```

## Acceptance Checks

1. Fast text greeting shows visible reaction, returns short text, enqueues TTS
2. Sprite tap creates no audio jobs
3. Audio retry works after failure
4. Fast Reply includes card memory
5. Service health endpoint responds
6. All backend tests pass (639 passed)
7. Frontend TypeScript compiles cleanly
