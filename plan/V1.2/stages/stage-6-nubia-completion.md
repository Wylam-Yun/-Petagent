# Stage 6 Completion: Nubia Live Verification And Deployment

## Summary
Stage 6 is complete. V1.2 deployed and verified on the Nubia phone. All live checks pass. Two post-verification fixes applied (HTML title, live test assertion).

## Deployment
- Method: adb push via /sdcard/ staging, then `run-as com.termux cp -r`
- Backend: uvicorn running on port 8000 (PID 9790)
- Frontend: dist with legacy polyfills served by FastAPI static mount
- Build hash: `c884cf4` (then `1c3a10a` after title fix)

## Live Verification Results

| Check | Status | Details |
|-------|--------|---------|
| Health API | PASS | name=豆豆, version, pid, started_at |
| Client Config | PASS | pet_name=豆豆, progressive copy correct |
| Pet State | PASS | schema 0.1, reasonable values |
| Pet Event | PASS | reply, mood happy, intimacy 42 |
| Text Chat | PASS | reply mentions 豆豆 |
| Frontend HTML | PASS | title=豆豆, legacy polyfills |
| Spritesheet | PASS | HTTP 200, referenced in bundle |
| Live Tests | 18/20 PASS | 1 fixed (name assertion), 2 skipped (no token) |
| E6 Metrics | PASS | all 5 timing tests pass |

## Post-Verification Fixes
1. `frontend/index.html` title: "Momo" → "豆豆"
2. `test_live_nubia.py` line 91: assertion "Momo" → "豆豆"
3. Frontend dist redeployed to phone with fix

## Known Non-Blocking Issues
- `behavior_intent`/`behavior_plan` are null in responses (LLM not generating these fields yet; fallback chain works correctly)
- Backend startup fragility: SQLite WAL checkpoint failure can cause uvicorn to hang; service manager recovers after ~120s

## V1.2 Final Commit Log
- `c5b2df9` — Stage 1: Sprite foundation
- `e2ce7b6` — Stage 2: Behavior director
- `85e65f8` — Stage 3: UI integration
- `94473ec` — Stage 4: Naming + persona + guard
- `c884cf4` — Stage 5: Hardening (Momo→豆豆 complete)
- `1c3a10a` — Stage 6: Live verification fixes
