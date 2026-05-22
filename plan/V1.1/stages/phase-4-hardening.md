# Phase 4: Hardening Follow-through

**Depends on:** Phase 0, 1, 2, 3 (all complete)
**Target:** Nubia NX531J, Android 6.0.1, Termux, ~200MB RAM

## Tasks

### 1. STAB-018: Upload Validation Magic Bytes
**File:** `backend/app/api/voice.py`
- After content_type check, validate magic bytes for WAV files (RIFF header)
- Reject files that claim WAV but lack `RIFF....WAVE` header
- Keep validation minimal — only check first 12 bytes
- Add structured error response with `error_class: "invalid_audio"`

### 2. STAB-026: Memory Card Rebuild Locking
**File:** `backend/app/runtime/memory_cards.py`
- Add `threading.RLock` to `MemoryCardManager`
- Wrap `rebuild()` and `clear()` in the lock
- Read operations (`read_card`, `read_card_with_provenance`) remain lock-free (atomic replace guarantees consistent reads)
- Add concurrency test

### 3. STAB-032: Auth Hardening for Runtime Endpoints
**File:** `backend/app/api/runtime.py`
- `/api/runtime/health` is public (used by service manager) — leave as-is
- `/api/runtime/skills` exposes internal skill list — add `require_internal_token` dependency
- CORS is already hardened (explicit origins + loopback)

### 4. STAB-034: Proxy Supervision in Service Manager
**File:** `scripts/termux_service_manager.sh`
- Add `ensure_proxy()` function that checks port 7897 on each loop iteration
- Call `start_proxy_once` if proxy port is down (with backoff)
- Log proxy restart events

### 5. STAB-035: Runtime Log Rotation
**File:** `backend/app/runtime/maintenance_worker.py` or `backend/app/main.py`
- Add periodic runtime.log rotation in the maintenance worker
- Use same pattern as service manager: check size, rotate to `.old`, truncate
- Configurable max size (default 512KB for mobile)

## Verification
```bash
cd backend && ../.venv/bin/python -m pytest -q
cd frontend && npm test -- --run && npm run build
```
