# V2.0 100-Round Voice Field Test Notes

## Issues Found

### Issue 1: ASR Proxy Not Running (Critical)
- **Round:** Pre-test (affects all rounds)
- **Symptom:** All voice uploads fail with `asr_request_error: ASR HTTP request failed`
- **Evidence:**
  - `voice_debug.jsonl` shows `error_class: "asr_request_error"` with 674ms response time
  - Proxy at `127.0.0.1:7897` is configured in `.env` but not running
  - Port 7897 not listening (`ss -tlnp | grep 7897` returns nothing)
  - No proxy binary found on device (no clash/v2ray/xray/mihomo)
  - Direct curl to SiliconFlow API works (200 OK)
  - Python requests with `proxies={}` works (200 OK)
  - Python requests with `proxies={"https": "http://127.0.0.1:7897"}` fails with `ProxyError`
- **Root Cause:** Proxy service (likely clash or similar) was previously running on port 7897 but is no longer active. No proxy binary installed in Termux.
- **Recovery:** Disabled proxy env vars in `.env` (PETAGENT_ASR_PROXY_URL, SILICONFLOW_PROXY_URL, PETAGENT_PROXY_URL, ASR_PROXY_URL all set to empty). Backend restarted.
- **Impact:** ASR was completely broken until proxy disabled. All voice interactions would fail.
- **Recommendation:** Either reinstall/start the proxy service, or remove proxy config if direct connection is preferred.

### Issue 2: Backend Process Unstable
- **Round:** Pre-test
- **Symptom:** Backend process dies periodically, requiring restart via `scripts/start.sh`
- **Evidence:**
  - `scripts/status.sh` shows `process: not running` multiple times
  - SSH connection drops when backend is down
  - Recovery requires `adb shell am start -n com.termux/.app.TermuxActivity` + wait + restart
- **Root Cause:** Unknown - possibly Termux killing background processes, or backend crashing
- **Impact:** Test interruptions, requires manual recovery
- **Recommendation:** Investigate backend crash logs, check Termux battery optimization settings

### Issue 3: Recording Duration Excessive
- **Round:** 001
- **Symptom:** Recording duration 30.976s despite ~8s utterance
- **Evidence:**
  - `voice_debug.jsonl` shows `duration_s: 30.976`
  - Frontend MAX_RECORDING_MS=15000 should limit recording
  - Recording continues after `say` finishes
- **Root Cause:** Recording starts on first tap and continues until second tap. The wait between say finish and second tap adds extra time. Also, the microphone picks up ambient noise/silence.
- **Impact:** Longer recordings = larger files, slower ASR, potential timeout issues
- **Recommendation:** Optimize tap timing, consider adding silence detection

### Issue 4: ASR Quality Degraded
- **Round:** 001
- **Symptom:** ASR returns garbled text "嗯嗯嗯张开眼界的嗯30场84000方茶" instead of actual utterance
- **Evidence:**
  - User spoke "豆豆早上好，今天我们做一百轮语音测试，先从简单问候开始。"
  - ASR returned completely different text
  - Audio captured from Mac speaker via phone microphone
- **Root Cause:** Audio quality degradation from speaker-to-microphone path. Mac `say` command audio may not be loud enough or phone mic may have noise.
- **Impact:** ASR accuracy significantly reduced, but backend still processes (treats as success)
- **Recommendation:** This is expected for the test setup (Mac speaker -> phone mic). Real user speech would have better quality.

### Issue 5: SSH Connection Drops
- **Round:** Multiple
- **Symptom:** SSH to nubia-adb fails with "Connection closed by 127.0.0.1 port 18022"
- **Evidence:**
  - Multiple SSH failures during pre-test
  - Requires bringing Termux to foreground (`am start -n com.termux/.app.TermuxActivity`) + waiting 8-10 seconds
  - ADB forwards need to be re-established
- **Root Cause:** Termux SSH server may be killed when app is in background, or ADB forward tunnel drops
- **Impact:** Disrupts monitoring and evidence collection
- **Recommendation:** Keep Termux in foreground during testing, or use more robust SSH keepalive

## Test Setup Notes
- Voice button coordinates: X=540, Y=1250 (verified via screenshot)
- Screen resolution: 1080x1920
- `say` command on Mac produces audio through speakers
- Phone microphone captures audio from Mac speakers
- Recording starts on first tap, ends on second tap
- Backend health checked via `curl http://127.0.0.1:18000/api/health`
- Voice debug log at `backend/data/logs/voice_debug.jsonl`
