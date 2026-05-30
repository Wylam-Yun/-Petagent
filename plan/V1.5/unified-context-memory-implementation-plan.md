# V1.5 Unified Context And Stable Memory Implementation Plan

> **For agentic workers:** Use one fresh implementation agent per task with review checkpoints, or use the `executing-plans` skill for inline execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement V1.5's single foreground conversation pipeline, durable five-turn context, 10-line MiMo-only memory maintenance, explicit failure semantics, and Nubia verification.

**Architecture:** Keep the existing FastAPI/React architecture, but collapse foreground chat to one unified prompt contract. Add focused runtime helpers for durable dialogue selection, foreground reply validation, successful-turn trigger state, memory rewrite validation, and bounded provider retries. Keep compatibility fields accepted at API boundaries while ignoring them before route/prompt selection.

**Tech Stack:** FastAPI, SQLite via the existing locked connection wrapper, pytest, React/Vite, Vitest, Termux/Nubia deployment scripts.

---

## File Structure

### Backend Runtime

- Modify `backend/app/runtime/context_store.py`
  - Add durable recent-dialogue query across episodes.
  - Stop direct raw history deletion for V1.5.
  - Add a persistent successful-turn trigger store.

- Modify `backend/app/runtime/context_manager.py`
  - Build unified foreground context using durable history and all memory lines.
  - Remove foreground dependency on recall profile and current episode recent events.

- Modify `backend/app/pet/prompt_builder.py`
  - Add one unified foreground prompt builder.
  - Redirect foreground fast/thinking/generic callers to the unified builder or remove their foreground use.

- Modify `backend/app/pet/guard.py`
  - Split sanitization from fallback creation.
  - Return validation failure for invalid JSON, missing reply, empty reply, or reply stripped to empty.

- Modify `backend/app/runtime/dispatcher.py`
  - Ignore client thinking/route fields before routing.
  - Treat provider failure, provider busy, invalid output, and missing reply as terminal before commit.
  - Record successful turns once and trigger memory summary only by keyword or 10-turn counter.
  - Add required runtime diagnostics.
  - Stop calling the raw history deletion path.

- Modify `backend/app/runtime/text_pipeline.py`
  - Accept `thinking_mode` for compatibility but always pass false/ignored semantics downstream.

- Modify `backend/app/runtime/voice_pipeline.py`
  - Ignore `thinking_mode` and `requested_route`.
  - Make ASR success the only foreground voice entry point.
  - Remove audio-understanding fallback from foreground chat.

- Modify `backend/app/runtime/voice_types.py`
  - Keep fields compatible, but route info should report unified handling and ignored legacy fields where useful.

- Modify `backend/app/runtime/notebook.py`
  - Add all-memory-lines selection capped at 10.
  - Add atomic overwrite for validated memory lines.
  - Enforce at-most-10 invariant across append, migration, cleanup, and rewrite paths.

- Modify `backend/app/runtime/memory_judgment.py`
  - Change turn-summary processing to produce a full replacement memory set, or validate operations so final file never exceeds 10 lines.
  - Mark unconfigured MiMo jobs skipped and transient failures failed after bounded provider retries.

- Modify `backend/app/runtime/maintenance.py`
  - Process memory jobs only when queued by keyword or 10-turn trigger.
  - Disable or isolate maintenance paths that can write prompt-facing memory through non-MiMo providers.

- Modify `backend/app/main.py`
  - Build a MiMo-only memory provider; do not fall back to `settings.llm`.
  - Wire successful-turn trigger store.

- Modify `backend/app/api/text.py`
  - Keep request schema compatible, but ignore `thinking_mode`.
  - Return structured LLM failure responses.

- Modify `backend/app/api/voice.py`
  - Keep old form fields compatible, but ignore `thinking_mode` and `route`.
  - Return structured LLM failure responses after ASR success if LLM output fails.

- Modify `backend/app/api/context.py`
  - Remove side effects from `/api/context/refresh` or make it compatibility-only.

### Backend Providers

- Create `backend/app/providers/retry.py`
  - Provide a small bounded retry helper shared by ASR, LLM, TTS, and memory summarizer calls.
  - Total attempts must not exceed 3.
  - Auth/config errors are not retried.

- Modify `backend/app/providers/asr_http.py`
  - Count primary model, fallback models, and transient retries under the same 3-attempt budget.

- Modify `backend/app/providers/llm_mimo.py`
  - Add bounded retry to `MiMoLLMProvider.complete_json`.
  - Ensure `FallbackLLMProvider` counts fallback calls under the same logical budget or is not used for memory.

- Modify `backend/app/providers/tts_mimo.py`
  - Add bounded retry to both speech API styles.

### Frontend

- Modify `frontend/src/App.tsx`
  - Remove `VoiceModeToggle`, `thinkingMode` state, and "换个话题" UI.
  - Stop passing thinking options to text and voice calls.

- Modify `frontend/src/pet/api.ts`
  - Stop appending `thinking_mode` in new frontend requests.
  - Keep types permissive enough for old responses/tests.
  - Remove `refreshContext` usage; keep exported function only if tests or old code still require it.

- Modify `frontend/src/pet/types.ts`
  - Remove new-code reliance on `thinking_mode` route fields while preserving compatibility shapes if needed.

- Remove or retire `frontend/src/components/VoiceModeToggle.tsx` and `frontend/src/components/VoiceModeToggle.test.tsx`.

### Tests

- Modify existing tests that currently assert old thinking behavior:
  - `backend/tests/test_text_chat.py`
  - `backend/tests/test_voice_pipeline.py`
  - `backend/tests/test_route_policy.py`
  - `backend/tests/test_fast_reply_contract.py`
  - `backend/tests/test_thinking_prompt_contract.py`
  - `backend/tests/test_phase1_dispatcher.py`
  - `backend/tests/test_agent_run.py`
  - `backend/tests/test_stage3_runtime_integration.py`
  - `backend/tests/test_skill_execution.py`
  - `backend/tests/test_dispatcher_pet_effort.py`
  - `backend/tests/test_pet_guard.py`
  - `backend/tests/test_provider_mock.py`
  - frontend tests under `frontend/src/App.test.tsx`, `frontend/src/pet/api.test.ts`, and `frontend/src/components/VoiceButton.test.tsx`.

- Add focused V1.5 tests:
  - `backend/tests/test_v15_unified_context.py`
  - `backend/tests/test_v15_successful_turns.py`
  - `backend/tests/test_v15_memory_invariant.py`
  - `backend/tests/test_v15_provider_retry.py`
  - `backend/tests/test_v15_failure_contract.py`

---

## Task 1: Push-Free Baseline And Failing V1.5 Contract Tests

**Files:**
- Create: `backend/tests/test_v15_failure_contract.py`
- Create: `backend/tests/test_v15_unified_context.py`
- Create: `backend/tests/test_v15_successful_turns.py`
- Create: `backend/tests/test_v15_memory_invariant.py`
- Create: `backend/tests/test_v15_provider_retry.py`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/pet/api.test.ts`

- [ ] **Step 1: Confirm clean baseline**

Run:

```bash
git status --short
```

Expected: no output.

- [ ] **Step 2: Add failing backend tests for explicit LLM failure**

Create `backend/tests/test_v15_failure_contract.py` with tests that assert:

```python
from fastapi.testclient import TestClient

from app.main import create_app


class RaisingProvider:
    name = "raising_provider"

    def complete_json(self, messages):
        raise RuntimeError("provider down")


class InvalidJsonProvider:
    name = "invalid_json_provider"

    def complete_json(self, messages):
        return "{broken json"


def _client_with_provider(provider):
    app = create_app(testing=True)
    app.state.text_pipeline.fast_brain.provider = provider
    app.state.dispatcher.brain.provider = provider
    return TestClient(app)


def test_text_llm_provider_exception_is_explicit_failure_without_history():
    client = _client_with_provider(RaisingProvider())
    response = client.post("/api/text/chat", json={"text": "你好"})
    body = response.json()
    assert response.status_code == 200
    assert body["error_class"] in {"llm_provider_error", "llm_invalid_output"}
    assert body["reply"] == ""
    assert client.app.state.event_log_store.count() == 0


def test_text_invalid_llm_output_is_not_friendly_fallback():
    client = _client_with_provider(InvalidJsonProvider())
    response = client.post("/api/text/chat", json={"text": "你好"})
    body = response.json()
    assert response.status_code == 200
    assert body["error_class"] == "llm_invalid_output"
    assert "豆豆在这儿" not in body.get("reply", "")
    assert client.app.state.event_log_store.count() == 0
```

- [ ] **Step 3: Add failing backend tests for ignored thinking and route fields**

Append to `backend/tests/test_v15_failure_contract.py`:

```python
class CapturingProvider:
    name = "capturing_provider"

    def __init__(self):
        self.messages = []

    def complete_json(self, messages):
        self.messages.append(messages)
        return {"reply": "收到啦", "mood": "happy", "action": "happy"}


def test_text_thinking_mode_is_accepted_but_ignored():
    provider = CapturingProvider()
    client = _client_with_provider(provider)
    response = client.post(
        "/api/text/chat",
        json={"text": "认真想一下", "thinking_mode": True},
    )
    body = response.json()
    assert body["error_class"] is None
    assert body["runtime"]["context_profile"] == "unified"
    assert body["text_route"]["thinking_mode"] is False


def test_voice_legacy_route_thinking_is_ignored_on_asr_failure(tmp_path):
    app = create_app(testing=True)

    class EmptyASR:
        name = "empty_asr"

        def transcribe(self, audio_path, content_type):
            from app.runtime.voice_types import ASRTranscript
            return ASRTranscript(text="", confidence=0.0, provider=self.name, error_code="asr_empty")

    app.state.voice_pipeline.asr_provider = EmptyASR()
    client = TestClient(app)
    audio = b"RIFF\x24\x00\x00\x00WAVEfmt "
    response = client.post(
        "/api/voice/chat",
        files={"file": ("voice.wav", audio, "audio/wav")},
        data={"thinking_mode": "true", "route": "thinking"},
    )
    body = response.json()
    assert body["ok"] is False
    assert body["error_class"] == "asr_empty"
    assert client.app.state.event_log_store.count() == 0
```

- [ ] **Step 4: Add failing backend tests for unified context selection**

Create `backend/tests/test_v15_unified_context.py`:

```python
from app.runtime.context_store import EventLogStore
from app.pet.state import StateStore


def _record(store, event_id, episode_id, event_type, user_text, pet_reply, source="test"):
    store.record(
        event_id=event_id,
        episode_id=episode_id,
        event_type=event_type,
        source=source,
        user_text=user_text,
        pet_reply=pet_reply,
    )


def test_recent_dialogue_crosses_episodes_and_filters_non_dialogue(tmp_path):
    state = StateStore(tmp_path / "state.db")
    store = EventLogStore(state.connection)
    _record(store, "p1", "ep-a", "proactive", "", "早呀")
    _record(store, "b1", "ep-a", "feed_momo", "", "好吃")
    _record(store, "t1", "ep-a", "text_message", "一", "答一")
    _record(store, "v1", "ep-a", "voice_message", "二", "答二")
    _record(store, "w1", "ep-b", "wake_phrase", "豆豆", "在")
    _record(store, "t2", "ep-b", "text_message", "三", "答三")
    _record(store, "v2", "ep-b", "voice_message", "", "")
    _record(store, "t3", "ep-c", "text_message", "四", "答四")
    _record(store, "t4", "ep-c", "text_message", "五", "答五")
    _record(store, "t5", "ep-c", "text_message", "六", "答六")

    rows = store.recent_dialogue_turns(limit=5)
    assert [row["user"] for row in rows] == ["二", "三", "四", "五", "六"]
    assert [row["pet"] for row in rows] == ["答二", "答三", "答四", "答五", "答六"]
```

- [ ] **Step 5: Add failing backend tests for turn counter and memory triggers**

Create `backend/tests/test_v15_successful_turns.py`:

```python
from app.pet.state import StateStore
from app.runtime.context_store import SuccessfulTurnStore


def test_successful_turn_counter_persists_and_triggers_every_ten(tmp_path):
    state = StateStore(tmp_path / "state.db")
    store = SuccessfulTurnStore(state.connection)
    triggered = []
    for idx in range(1, 21):
        result = store.record_successful_turn(f"event-{idx}", keyword_trigger=False)
        if result.should_enqueue_memory:
            triggered.append(idx)
    assert triggered == [10, 20]

    reloaded = SuccessfulTurnStore(state.connection)
    assert reloaded.snapshot()["successful_turn_count_total"] == 20
    assert reloaded.record_successful_turn("event-20", keyword_trigger=False).incremented is False


def test_keyword_trigger_enqueues_without_waiting_for_tenth_turn(tmp_path):
    state = StateStore(tmp_path / "state.db")
    store = SuccessfulTurnStore(state.connection)
    result = store.record_successful_turn("event-1", keyword_trigger=True)
    assert result.incremented is True
    assert result.should_enqueue_memory is True
```

- [ ] **Step 6: Add failing backend tests for 10-line memory invariant**

Create `backend/tests/test_v15_memory_invariant.py`:

```python
from app.runtime.notebook import NotebookManager


def test_memory_overwrite_rejects_more_than_ten_lines(tmp_path):
    user = tmp_path / "user.md"
    memory = tmp_path / "memory.md"
    memory.write_text("- [2026-05-30 10:00][identity] 旧记忆\n", encoding="utf-8")
    notebook = NotebookManager(user, memory)
    lines = [
        {"category": "preference", "content": f"记忆{i}"}
        for i in range(11)
    ]
    assert notebook.overwrite_memory_lines(lines) is False
    assert "旧记忆" in memory.read_text(encoding="utf-8")


def test_memory_overwrite_accepts_ten_valid_lines(tmp_path):
    notebook = NotebookManager(tmp_path / "user.md", tmp_path / "memory.md")
    lines = [
        {"category": "preference", "content": f"记忆{i}"}
        for i in range(10)
    ]
    assert notebook.overwrite_memory_lines(lines) is True
    content = (tmp_path / "memory.md").read_text(encoding="utf-8")
    assert content.count("[preference]") == 10
```

- [ ] **Step 7: Add failing backend tests for provider retry budget**

Create `backend/tests/test_v15_provider_retry.py`:

```python
import pytest

from app.providers.errors import ProviderTimeoutError, ProviderAuthError
from app.providers.retry import retry_provider_call


def test_provider_retry_succeeds_within_three_attempts():
    attempts = {"count": 0}

    def op():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ProviderTimeoutError(provider="x")
        return "ok"

    assert retry_provider_call(op, provider="x") == "ok"
    assert attempts["count"] == 3


def test_provider_retry_does_not_retry_auth_error():
    attempts = {"count": 0}

    def op():
        attempts["count"] += 1
        raise ProviderAuthError(provider="x", message="bad key")

    with pytest.raises(ProviderAuthError):
        retry_provider_call(op, provider="x")
    assert attempts["count"] == 1
```

- [ ] **Step 8: Add failing frontend tests**

Update `frontend/src/App.test.tsx` to assert:

```tsx
it("does not render thinking mode or topic refresh controls", async () => {
  render(<App />);
  expect(screen.queryByText(/思考/)).not.toBeInTheDocument();
  expect(screen.queryByText("换个话题")).not.toBeInTheDocument();
});
```

Update `frontend/src/pet/api.test.ts` to assert new text/voice requests do not include `thinking_mode`:

```ts
expect(body.has("thinking_mode")).toBe(false);
expect(JSON.parse(fetchBody as string)).not.toHaveProperty("thinking_mode");
```

- [ ] **Step 9: Run targeted tests and confirm they fail**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest -q \
  tests/test_v15_failure_contract.py \
  tests/test_v15_unified_context.py \
  tests/test_v15_successful_turns.py \
  tests/test_v15_memory_invariant.py \
  tests/test_v15_provider_retry.py
cd ../frontend && npm test -- --run src/App.test.tsx src/pet/api.test.ts
```

Expected: failures for missing `recent_dialogue_turns`, `SuccessfulTurnStore`, `overwrite_memory_lines`, `retry_provider_call`, and old frontend controls/request fields.

- [ ] **Step 10: Commit failing V1.5 contract tests**

```bash
git add backend/tests/test_v15_*.py frontend/src/App.test.tsx frontend/src/pet/api.test.ts
git commit -m "test: add V1.5 unified context contracts"
```

---

## Task 2: Explicit Foreground Failure Semantics

**Files:**
- Modify: `backend/app/pet/guard.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Modify: `backend/app/api/text.py`
- Modify: `backend/app/api/voice.py`
- Test: `backend/tests/test_v15_failure_contract.py`
- Update old tests: `backend/tests/test_pet_guard.py`, `backend/tests/test_fast_reply_contract.py`, `backend/tests/test_provider_mock.py`

- [ ] **Step 1: Add validation result types in guard**

In `backend/app/pet/guard.py`, add:

```python
class InvalidActionError(ValueError):
    def __init__(self, error_class: str = "llm_invalid_output", message: str = "") -> None:
        super().__init__(message or error_class)
        self.error_class = error_class
```

Change `_parse_action` so invalid JSON and unsupported raw values raise `InvalidActionError` instead of returning `FALLBACK_ACTION`.

- [ ] **Step 2: Remove synthetic fallback success**

Update `guard_action` and `guard_fast_reply_action`:

```python
data = _parse_action(raw)
if not str(data.get("reply") or "").strip():
    raise InvalidActionError("llm_invalid_output", "LLM reply is empty")
```

After `_strip_reasoning` and `_sanitize_prompt_leak`, if the reply is empty or equals a synthetic fallback-only value because the model output had no user-visible reply, raise `InvalidActionError`.

Keep enum repair behavior for mood/action/voice_style.

- [ ] **Step 3: Stop dispatcher before commit on provider failure**

In `backend/app/runtime/dispatcher.py`, replace the current `raw_action = None` continuation with an explicit failure response path. The failure path must:

- set `run.status = failed`;
- not call `guard_action` or `guard_fast_reply_action`;
- not save state;
- not record `raw_event_log`;
- not enqueue audio;
- not enqueue memory;
- return a `PetResponse` with `reply=""`, current `pet_state`, and `runtime.error_class`.

- [ ] **Step 4: Stop dispatcher before commit on invalid guard output**

Wrap guard calls:

```python
try:
    fast_action = guard_fast_reply_action(raw_action)
except InvalidActionError as exc:
    return self._failure_response(...)
```

Use `llm_invalid_output` for invalid JSON, missing reply, empty reply, or fully stripped reply.

- [ ] **Step 5: Normalize API bodies**

In `/api/text/chat` and `/api/voice/chat`, propagate `runtime.error_class` to top-level `error_class`, set `ok:false` for voice failures, and avoid `audio_job_id`.

- [ ] **Step 6: Update old guard tests**

Change tests that currently expect fallback replies:

- `test_guard_uses_fallback_for_invalid_json`
- `test_guard_uses_fallback_when_reply_is_only_reasoning`
- `test_fast_reply_guard_fallback_on_empty`
- `test_fast_reply_guard_fallbacks_on_reasoning_only`
- `test_provider_mock` broken JSON case

They should now assert `InvalidActionError`.

- [ ] **Step 7: Run failure tests**

```bash
cd backend && ../.venv/bin/python -m pytest -q \
  tests/test_v15_failure_contract.py \
  tests/test_pet_guard.py \
  tests/test_fast_reply_contract.py \
  tests/test_provider_mock.py
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/pet/guard.py backend/app/runtime/dispatcher.py backend/app/api/text.py backend/app/api/voice.py backend/tests/test_v15_failure_contract.py backend/tests/test_pet_guard.py backend/tests/test_fast_reply_contract.py backend/tests/test_provider_mock.py
git commit -m "fix: fail explicitly on invalid foreground LLM output"
```

---

## Task 3: Ignore Thinking And Legacy Voice Route Fields

**Files:**
- Modify: `backend/app/runtime/route_policy.py`
- Modify: `backend/app/runtime/text_pipeline.py`
- Modify: `backend/app/runtime/voice_pipeline.py`
- Modify: `backend/app/api/text.py`
- Modify: `backend/app/api/voice.py`
- Test: `backend/tests/test_v15_failure_contract.py`
- Update old tests: `backend/tests/test_text_chat.py`, `backend/tests/test_voice_pipeline.py`, `backend/tests/test_route_policy.py`, `backend/tests/test_agent_run.py`, `backend/tests/test_phase1_dispatcher.py`, `backend/tests/test_stage3_runtime_integration.py`, `backend/tests/test_skill_execution.py`, `backend/tests/test_thinking_prompt_contract.py`

- [ ] **Step 1: Make route policy unified**

Change `decide_route` so `thinking_mode` no longer returns `thinking`. Route decision can still include provider hints, but `context_profile` must be `"unified"` for foreground chat.

- [ ] **Step 2: Force text thinking false at pipeline boundary**

In `TextPipeline.handle`, keep the parameter but set:

```python
effective_thinking_mode = False
```

Use that for route decisions, event payloads, and `TextRouteInfo.thinking_mode`.

- [ ] **Step 3: Force voice route to ASR path**

In `VoicePipeline.handle`, ignore `requested_route` and `thinking_mode`:

```python
requested = "auto"
effective_thinking_mode = False
return self._run_asr_route(...)
```

Do not call `_run_audio_understanding_route` from foreground chat.

- [ ] **Step 4: Preserve compatibility in API schemas**

Keep `thinking_mode` and `route` accepted by FastAPI request parsing, but pass ignored values downstream or ignore them before calling the pipeline.

- [ ] **Step 5: Update route and thinking tests**

Change old tests to assert:

- text `thinking_mode=True` returns `text_route.thinking_mode is False`;
- voice `thinking_mode=true` returns `voice_route.thinking_mode is False`;
- no test expects audio-understanding fallback for foreground voice;
- no test expects `context_profile="thinking"`.

- [ ] **Step 6: Run targeted tests**

```bash
cd backend && ../.venv/bin/python -m pytest -q \
  tests/test_v15_failure_contract.py \
  tests/test_text_chat.py \
  tests/test_voice_pipeline.py \
  tests/test_route_policy.py \
  tests/test_agent_run.py \
  tests/test_phase1_dispatcher.py \
  tests/test_stage3_runtime_integration.py \
  tests/test_skill_execution.py \
  tests/test_thinking_prompt_contract.py
```

Expected: pass after test updates.

- [ ] **Step 7: Commit**

```bash
git add backend/app/runtime/route_policy.py backend/app/runtime/text_pipeline.py backend/app/runtime/voice_pipeline.py backend/app/api/text.py backend/app/api/voice.py backend/tests
git commit -m "fix: ignore legacy thinking and voice route controls"
```

---

## Task 4: Durable Recent Dialogue And Unified Prompt

**Files:**
- Modify: `backend/app/runtime/context_store.py`
- Modify: `backend/app/runtime/context_manager.py`
- Modify: `backend/app/pet/prompt_builder.py`
- Modify: `backend/app/pet/brain.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Test: `backend/tests/test_v15_unified_context.py`
- Update old tests: `backend/tests/test_fast_reply_contract.py`, `backend/tests/test_thinking_prompt_contract.py`, `backend/tests/test_memory_cards.py`, `backend/tests/test_stage35_context.py`, `backend/tests/test_stage36_context.py`, `backend/tests/test_recall_context_and_summary_jobs.py`

- [ ] **Step 1: Add durable recent dialogue query**

In `EventLogStore`, add:

```python
def recent_dialogue_turns(self, limit: int = 5) -> List[Dict[str, Any]]:
    rows = self.connection.execute(
        """
        SELECT event_id, event_type, source, user_text, pet_reply, created_at_utc
        FROM raw_event_log
        WHERE event_type IN ('text_message', 'voice_message')
          AND user_text IS NOT NULL AND TRIM(user_text) != ''
          AND pet_reply IS NOT NULL AND TRIM(pet_reply) != ''
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    result = [{"user": row["user_text"], "pet": row["pet_reply"], "created_at": row["created_at_utc"]} for row in rows]
    result.reverse()
    return result
```

- [ ] **Step 2: Add all memory lines selector**

In `NotebookManager`, add:

```python
def prompt_memory_lines(self, limit: int = 10) -> List[str]:
    return [entry.raw for entry in self.parse_memory()[:limit]]
```

If product wants content without metadata, use `entry.content`, but keep the plan consistent with tests.

- [ ] **Step 3: Build unified context**

In `ContextManager.build`, when profile is foreground chat, set:

```python
context["context_profile"] = "unified"
context["recent_exact_events"] = event_log_store.recent_dialogue_turns(limit=5)
context["selected_card_items"] = notebook_manager.prompt_memory_lines(limit=10)
context["memory_cards"] = None
context["temporal_recall_events"] = []
```

Remove recall-only loading from foreground.

- [ ] **Step 4: Add unified prompt builder**

In `prompt_builder.py`, add:

```python
def build_unified_foreground_messages(settings, event, context):
    system_prompt = settings.persona_config.get("system_prompt", "")
    cognition = context.cognition_context or {}
    payload = {
        "user_input": str(event.payload.get("user_text") or event.payload.get("text") or ""),
        "recent_dialogue": cognition.get("recent_exact_events", [])[-5:],
        "long_term_memory": cognition.get("selected_card_items", [])[:10],
        "pet_state": {
            "mood": context.pet_state.get("mood", "idle"),
            "energy": context.pet_state.get("energy", 50),
            "intimacy": context.pet_state.get("intimacy", 0),
            "sleepiness": context.pet_state.get("sleepiness", 0),
        },
        "response_schema": FAST_REPLY_SCHEMA,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
```

Redirect foreground brain generation to this builder.

- [ ] **Step 5: Add required runtime diagnostics**

In dispatcher response runtime, set:

```python
response.runtime["context_profile"] = "unified"
response.runtime["recent_dialogue_count"] = len(cognition_context.get("recent_exact_events") or [])
response.runtime["memory_line_count"] = len(cognition_context.get("selected_card_items") or [])
response.runtime["provider"] = run.provider
```

- [ ] **Step 6: Update old context/prompt tests**

Old thinking prompt tests should either be removed or changed to assert unified prompt payload. Fast reply contract tests should expect latest 5 and `long_term_memory`.

- [ ] **Step 7: Run targeted tests**

```bash
cd backend && ../.venv/bin/python -m pytest -q \
  tests/test_v15_unified_context.py \
  tests/test_fast_reply_contract.py \
  tests/test_thinking_prompt_contract.py \
  tests/test_memory_cards.py \
  tests/test_stage35_context.py \
  tests/test_stage36_context.py \
  tests/test_recall_context_and_summary_jobs.py
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/runtime/context_store.py backend/app/runtime/context_manager.py backend/app/pet/prompt_builder.py backend/app/pet/brain.py backend/app/runtime/dispatcher.py backend/tests
git commit -m "feat: use unified durable dialogue context"
```

---

## Task 5: Successful Turn Counter And Memory Trigger Gating

**Files:**
- Modify: `backend/app/runtime/context_store.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Modify: `backend/app/runtime/memory_judgment.py`
- Modify: `backend/app/runtime/maintenance.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_v15_successful_turns.py`
- Update old tests: `backend/tests/test_fast_reply_contract.py`, `backend/tests/test_memory_judgment.py`, `backend/tests/test_stage36_maintenance.py`

- [ ] **Step 1: Add result dataclass**

In `context_store.py`, add:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class SuccessfulTurnResult:
    incremented: bool
    should_enqueue_memory: bool
    total: int
    since_memory_summary: int
```

- [ ] **Step 2: Add `SuccessfulTurnStore`**

Create a SQLite-backed store with table:

```sql
CREATE TABLE IF NOT EXISTS successful_turn_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS successful_turn_event (
  event_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);
```

Implement:

```python
record_successful_turn(event_id: str, keyword_trigger: bool) -> SuccessfulTurnResult
mark_memory_summary_enqueued(event_id: str) -> None
snapshot() -> Dict[str, int]
clear_all() -> None
```

Only increment once per event id. `should_enqueue_memory` is true on keyword trigger or when since count reaches 10. Reset since count after enqueue.

- [ ] **Step 3: Wire store in app startup**

In `main.py`, instantiate `SuccessfulTurnStore(state_store.connection)` and attach it to app state and dispatcher.

- [ ] **Step 4: Gate memory queue in dispatcher**

After a successful commit, call `record_successful_turn`. Enqueue memory summary only if:

```python
turn_result.should_enqueue_memory is True
```

Pass the current user text, reply, current `memory.md` lines, and trigger reason to `MemoryJudgmentQueue`.

- [ ] **Step 5: Make memory queue persistent outcome-aware**

If keeping in-memory queue, the trigger decision must be persistent and idempotent in `SuccessfulTurnStore`. If the queue is full, explicit keyword jobs can evict non-priority jobs; failed MiMo jobs must not retry forever.

- [ ] **Step 6: Update tests that expect every-turn memory enqueue**

Change existing tests to assert no memory job for normal turns 1-9, one job on turn 10, and immediate job on explicit keyword.

- [ ] **Step 7: Run targeted tests**

```bash
cd backend && ../.venv/bin/python -m pytest -q \
  tests/test_v15_successful_turns.py \
  tests/test_fast_reply_contract.py \
  tests/test_memory_judgment.py \
  tests/test_stage36_maintenance.py
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/runtime/context_store.py backend/app/runtime/dispatcher.py backend/app/runtime/memory_judgment.py backend/app/runtime/maintenance.py backend/app/main.py backend/tests
git commit -m "feat: gate memory summaries by persistent turn triggers"
```

---

## Task 6: 10-Line Memory Invariant And MiMo-Only Memory Maintenance

**Files:**
- Modify: `backend/app/runtime/notebook.py`
- Modify: `backend/app/runtime/memory_judgment.py`
- Modify: `backend/app/runtime/nightly_cleanup.py`
- Modify: `backend/app/runtime/memory_curator.py`
- Modify: `backend/app/runtime/maintenance.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/pet/prompt_builder.py`
- Test: `backend/tests/test_v15_memory_invariant.py`
- Update old tests: `backend/tests/test_notebook.py`, `backend/tests/test_memory_cards.py`, `backend/tests/test_memory_judgment.py`, `backend/tests/test_nightly_cleanup.py`, `backend/tests/test_stage36_curator.py`

- [ ] **Step 1: Add `overwrite_memory_lines`**

In `NotebookManager`, implement:

```python
def overwrite_memory_lines(self, items: List[Dict[str, str]]) -> bool:
    if len(items) > 10:
        return False
    lines = [_V14_MARKER]
    for item in items:
        category = str(item.get("category") or "")
        content = str(item.get("content") or "").strip()
        if category not in _CATEGORY_WHITELIST or not content:
            return False
        if _is_too_long(content) or _is_sensitive(content) or _CONTENT_TIMESTAMP_RE.match(content):
            return False
        lines.append(f"- [{_local_timestamp()}][{category}] {content}")
    with self._lock:
        self._memory_path.parent.mkdir(parents=True, exist_ok=True)
        backup = self._backup_file(self._memory_path)
        return self._write_text_atomic(self._memory_path, "\n".join(lines) + "\n")
```

- [ ] **Step 2: Make append compatibility preserve <=10**

Update `append_line` so it refuses to append if canonical memory already has 10 valid entries. Do not silently drop existing entries in append mode.

- [ ] **Step 3: Clamp migration with backup**

During migration/import, if more than 10 entries are found, keep the top 10 according to existing ranking, create a backup, and write only 10.

- [ ] **Step 4: Change memory summarizer output contract**

Update `build_memory_summary_messages` so the requested schema is a full replacement list:

```json
{"memories": [{"category": "identity", "content": "..." }]}
```

Limit: 0-10 items. Current conversation is highest priority.

- [ ] **Step 5: Apply summary as overwrite**

In `MemoryJudgmentQueue._process_turn_summary`, validate `memories` and call `notebook_manager.overwrite_memory_lines`. Remove add/update/delete application for V1.5 foreground memory summary, or keep legacy only for non-foreground disabled paths.

- [ ] **Step 6: Enforce MiMo-only provider**

In `main.py`, change `_select_memory_summarizer_provider`:

```python
config = settings.memory_summarizer
if testing:
    return MockLLMProvider("mock_memory_summarizer")
if config is None or not config.api_key or not config.base_url:
    return DisabledMemoryProvider("mimo_memory_not_configured")
return MiMoLLMProvider(settings, config)
```

Do not pass `settings.llm` as fallback.

- [ ] **Step 7: Disable or MiMo-isolate legacy memory-writing paths**

Ensure `MemoryCurator`, nightly cleanup, episode/daily summary, and memory card rebuild paths cannot write prompt-facing `memory.md` via SiliconFlow. Either route them to MiMo-only provider or disable their prompt-facing writes for V1.5.

- [ ] **Step 8: Run targeted tests**

```bash
cd backend && ../.venv/bin/python -m pytest -q \
  tests/test_v15_memory_invariant.py \
  tests/test_notebook.py \
  tests/test_memory_cards.py \
  tests/test_memory_judgment.py \
  tests/test_nightly_cleanup.py \
  tests/test_stage36_curator.py
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/runtime/notebook.py backend/app/runtime/memory_judgment.py backend/app/runtime/nightly_cleanup.py backend/app/runtime/memory_curator.py backend/app/runtime/maintenance.py backend/app/main.py backend/app/pet/prompt_builder.py backend/tests
git commit -m "feat: enforce ten-line MiMo-only memory"
```

---

## Task 7: Bounded Provider Retry

**Files:**
- Create: `backend/app/providers/retry.py`
- Modify: `backend/app/providers/asr_http.py`
- Modify: `backend/app/providers/llm_mimo.py`
- Modify: `backend/app/providers/tts_mimo.py`
- Test: `backend/tests/test_v15_provider_retry.py`
- Update old tests: `backend/tests/test_asr_http_provider.py`, `backend/tests/test_phase2_providers.py`, `backend/tests/test_audio_retry.py`

- [ ] **Step 1: Create retry helper**

Create `backend/app/providers/retry.py`:

```python
from __future__ import annotations

from time import sleep
from typing import Callable, TypeVar

from app.providers.errors import ProviderAuthError

T = TypeVar("T")


def is_retryable_provider_error(exc: Exception) -> bool:
    if isinstance(exc, ProviderAuthError):
        return False
    return True


def retry_provider_call(
    operation: Callable[[], T],
    *,
    provider: str,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.1,
) -> T:
    attempts = max(1, min(3, int(max_attempts)))
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            if not is_retryable_provider_error(exc) or attempt >= attempts - 1:
                raise
            sleep(min(1.0, base_delay_seconds * (attempt + 1)))
    raise last_exc  # type: ignore[misc]
```

- [ ] **Step 2: Apply retry to LLM**

Wrap the HTTP request body inside `MiMoLLMProvider.complete_json` with `retry_provider_call`. Do not retry invalid output parsing if the HTTP call succeeded but the model returned unusable content; that is `llm_invalid_output` handled by guard/dispatcher.

- [ ] **Step 3: Apply retry to TTS**

Wrap both `_synthesize_openai_speech` and chat-completions TTS HTTP operations. Auth/config errors remain non-retryable.

- [ ] **Step 4: Apply total attempt cap to ASR**

Change `ASRHTTPProvider._max_attempts` to:

```python
return max(1, min(3, max(retries + 1, len(models))))
```

Ensure fallback model attempts consume the same 3-attempt budget.

- [ ] **Step 5: Run provider retry tests**

```bash
cd backend && ../.venv/bin/python -m pytest -q \
  tests/test_v15_provider_retry.py \
  tests/test_asr_http_provider.py \
  tests/test_phase2_providers.py \
  tests/test_audio_retry.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers/retry.py backend/app/providers/asr_http.py backend/app/providers/llm_mimo.py backend/app/providers/tts_mimo.py backend/tests
git commit -m "feat: bound provider retries to three attempts"
```

---

## Task 8: Frontend Remove Thinking And Topic Refresh

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pet/api.ts`
- Modify: `frontend/src/pet/types.ts`
- Delete: `frontend/src/components/VoiceModeToggle.tsx`
- Delete: `frontend/src/components/VoiceModeToggle.test.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/pet/api.test.ts`
- Modify: `frontend/src/components/VoiceButton.test.tsx`

- [ ] **Step 1: Remove UI imports and state**

In `App.tsx`, remove:

- `VoiceModeToggle` import and render;
- `thinkingMode` state;
- `refreshContext` import and handler;
- "换个话题" button.

- [ ] **Step 2: Stop sending thinking options**

Call:

```ts
sendTextChat(text)
```

and:

```tsx
<VoiceButton ... />
```

without passing `thinkingMode`.

- [ ] **Step 3: Update API helpers**

In `frontend/src/pet/api.ts`, remove `formData.append("thinking_mode", ...)` from `uploadVoice`. Remove `thinking_mode` from `sendTextChat` request body for new calls.

Keep compatibility types only where old test fixtures require them.

- [ ] **Step 4: Delete VoiceModeToggle component and tests**

Remove files:

```bash
rm frontend/src/components/VoiceModeToggle.tsx frontend/src/components/VoiceModeToggle.test.tsx
```

- [ ] **Step 5: Update frontend tests**

Update tests to assert no thinking mode control, no topic refresh control, and no `thinking_mode` in new request bodies.

- [ ] **Step 6: Run frontend tests**

```bash
cd frontend && npm test -- --run
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pet/api.ts frontend/src/pet/types.ts frontend/src/App.test.tsx frontend/src/pet/api.test.ts frontend/src/components/VoiceButton.test.tsx
git rm frontend/src/components/VoiceModeToggle.tsx frontend/src/components/VoiceModeToggle.test.tsx
git commit -m "feat: remove user-facing thinking and topic refresh controls"
```

---

## Task 9: Context Refresh Compatibility And History Durability

**Files:**
- Modify: `backend/app/api/context.py`
- Modify: `backend/app/runtime/context_store.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Test: `backend/tests/test_v15_unified_context.py`
- Update old tests: `backend/tests/test_stage35_event_log.py`, `backend/tests/test_stage35_episode.py`, `backend/tests/test_recall_context_and_summary_jobs.py`

- [ ] **Step 1: Make context refresh compatibility-only**

Change `/api/context/refresh` so it returns:

```json
{"ok": true, "reply": "豆豆继续听你说。"}
```

It must not call `episode_manager.refresh_topic`, must not enqueue summary jobs, and must not record `context_refresh` into `raw_event_log`.

- [ ] **Step 2: Stop dispatcher raw cleanup delete path**

Remove or disable:

```python
self.event_log_store.cleanup_if_needed(...)
```

from foreground dispatcher success path.

- [ ] **Step 3: Preserve old cleanup function only as explicit archive-dependent API**

Either mark `cleanup_if_needed` deprecated and unused, or change it to no-op unless an archive implementation is provided.

- [ ] **Step 4: Update tests that expect deletion**

Old tests in `test_stage35_event_log.py` should assert that cleanup does not silently delete rows, or should move deletion assertions to an explicit archival feature if implemented.

- [ ] **Step 5: Run targeted tests**

```bash
cd backend && ../.venv/bin/python -m pytest -q \
  tests/test_v15_unified_context.py \
  tests/test_stage35_event_log.py \
  tests/test_stage35_episode.py \
  tests/test_recall_context_and_summary_jobs.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/context.py backend/app/runtime/context_store.py backend/app/runtime/dispatcher.py backend/tests
git commit -m "fix: preserve durable history and neutralize topic refresh"
```

---

## Task 10: Full Regression And Nubia Verification

**Files:**
- Modify as needed: `plan/V1.5/unified-context-memory-implementation-plan.md`
- No production changes unless verification finds a defect.

- [ ] **Step 1: Run full backend suite**

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

Expected: all tests pass. Record final summary in the completion notes.

- [ ] **Step 2: Run full frontend suite**

```bash
cd frontend && npm test -- --run
```

Expected: all tests pass.

- [ ] **Step 3: Build frontend and deploy to Nubia**

```bash
cd /Users/wylam/Documents/workspace/Petagent
BUILD_FRONTEND=1 ./scripts/deploy_nubia.sh
```

Expected: deploy completes without error.

- [ ] **Step 4: Start service from Termux/SSH context**

```bash
adb forward tcp:18022 tcp:8022
ssh -i ~/.ssh/nubia_ed25519 -p 18022 localhost 'cd ~/Petagent && scripts/start.sh'
```

Expected: backend starts in Termux context with inet group.

- [ ] **Step 5: Verify health and frontend**

```bash
adb shell 'curl -sS --connect-timeout 2 --max-time 10 http://127.0.0.1:8000/api/health'
adb shell 'curl -sS --connect-timeout 2 --max-time 10 -I http://127.0.0.1:8000/'
```

Expected: health `ok:true`, frontend `HTTP/1.1 200 OK`.

- [ ] **Step 6: Verify text success on Nubia**

Send a text chat from the web UI. Confirm:

- reply appears;
- `runtime.context_profile` is `unified`;
- `recent_dialogue_count` is present;
- successful-turn counter increments.

- [ ] **Step 7: Verify voice ASR success on Nubia**

Record a clear phrase such as:

```text
123456789 豆豆今天星期几
```

Confirm:

- `ok:true`;
- `user_text` is non-empty;
- reply appears;
- history row is written;
- successful-turn counter increments.

- [ ] **Step 8: Verify ASR failure on Nubia**

Submit silence or force an ASR-empty fixture if available. Confirm:

- `ok:false`;
- explicit `error_class`;
- no TTS job;
- no history row;
- no successful-turn counter increment;
- no memory summary enqueue.

- [ ] **Step 9: Verify 10-turn memory trigger on Nubia**

Complete 10 successful text/button/voice-success turns. Confirm one memory summary attempt is logged. Confirm `memory.md` remains at 10 lines or fewer.

- [ ] **Step 10: Verify MiMo unavailable does not call SiliconFlow**

Temporarily run with missing/invalid MiMo memory config in a controlled test. Confirm:

- foreground chat still works;
- memory job is skipped or failed;
- logs show no SiliconFlow call for memory writing;
- no prompt-facing memory file change is applied.

- [ ] **Step 11: Commit completion notes**

Create or update a V1.5 completion note with command summaries and Nubia evidence:

```bash
git add plan/V1.5
git commit -m "docs: record V1.5 verification results"
```

---

## Final Review Checklist

- [ ] Frontend has no Thinking Mode control.
- [ ] Frontend has no "换个话题" control.
- [ ] Backend accepts but ignores `thinking_mode`.
- [ ] Backend accepts but ignores voice `route`.
- [ ] Voice foreground chat only proceeds after ASR transcript success.
- [ ] ASR failure is explicit and terminal.
- [ ] LLM provider failure is explicit and terminal.
- [ ] Invalid LLM output is explicit and terminal.
- [ ] Successful foreground prompt shape is unified.
- [ ] Runtime diagnostics expose `context_profile`, `recent_dialogue_count`, `memory_line_count`, and `provider`.
- [ ] Recent dialogue comes from durable history across episodes.
- [ ] Button successes count for memory trigger but do not enter recent dialogue.
- [ ] Successful-turn counter persists and is idempotent.
- [ ] Memory summary triggers only on keyword or 10-turn boundaries.
- [ ] `memory.md` has at most 10 valid memory lines.
- [ ] Memory-writing maintenance is MiMo-only or disabled.
- [ ] Provider retries are bounded to 3 total attempts.
- [ ] Raw history is not silently deleted.
- [ ] Backend tests pass.
- [ ] Frontend tests pass.
- [ ] Nubia deployment and live checks pass.
