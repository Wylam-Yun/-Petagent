# PetAgent Interaction TTS Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all visible interaction buttons call the existing LLM/TTS path, add a user-facing TTS switch for Xiaomi/Mimo BingTang, and document the real Termux persistence boundary.

**Architecture:** Keep the single existing `/api/pet/event`, `/api/text/chat`, and `/api/voice/chat` flows. Add a runtime-selectable TTS provider wrapper around the existing SiliconFlow primary and Mimo fallback providers, exposed through loopback-only runtime endpoints and a small frontend control.

**Tech Stack:** FastAPI, React/Vite, existing provider abstractions, Termux runtime scripts, Android WebView shell.

---

### Task 1: Make Visible Interaction Buttons Model-Backed

**Files:**
- Modify: `backend/app/runtime/interaction_catalog.py`
- Modify: `frontend/src/App.tsx`
- Modify: `backend/tests/test_interaction_catalog.py`
- Modify: `frontend/src/App.test.tsx`

- [ ] Set user-facing catalog interactions to `requires_model=True`.
- [ ] Remove the frontend early return that keeps default interactions local-only.
- [ ] Update tests so default visible interactions post `/api/pet/event`.

### Task 2: Add Runtime TTS Selection

**Files:**
- Modify: `backend/app/providers/tts_mimo.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/runtime.py`
- Modify: `backend/tests/test_provider_mock.py`
- Modify: `backend/tests/test_api_contracts.py`

- [ ] Add a thread-safe selector provider with modes `siliconflow` and `mimo`.
- [ ] Keep automatic fallback to the other configured provider on provider failure.
- [ ] Expose loopback-only `GET/POST /api/runtime/tts-config`.
- [ ] Persist `PETAGENT_TTS_MODE` into `.env`.

### Task 3: Add Frontend TTS Switch

**Files:**
- Modify: `frontend/src/pet/types.ts`
- Modify: `frontend/src/pet/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/pet/api.test.ts`
- Modify: `frontend/src/App.test.tsx`

- [ ] Add API helpers for the TTS config endpoint.
- [ ] Add a compact button near existing secondary actions: `TTS: 冰糖` or `TTS: Claire`.
- [ ] Switch modes without exposing API keys.

### Task 4: Stability and Provider Reality Checks

**Files:**
- Modify: `docs/operations.md`
- Modify: `scripts/status.sh`

- [ ] Document APK auto-recovery behavior and the Nubia NeoSafe force-stop limitation.
- [ ] Make status output call out Termux stopped/vendor-force-stop risk without treating it as proof that a live SSH/backend is down.
- [ ] Confirm Mimo ASR is not wired unless the real supported request shape is known.

### Task 5: Verification

- [ ] Run focused backend tests for runtime config, interaction catalog, providers, and voice contracts.
- [ ] Run focused frontend tests for App and API helpers.
- [ ] Check git status and forbidden artifacts.
