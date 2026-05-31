# V1.7 Context Memory Voice Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` or an equivalent step-by-step implementation loop. Steps use checkbox (`- [x]`) syntax for tracking. Do not skip the Nubia validation section.

**Goal:** 按 V1.7 spec 修复豆豆上下文自我强化、长期记忆 summary 误清空、pet_state 状态不闭环、reset 不彻底、ASR timeout 不重试的问题，并在 Nubia 真机网页语音链路上验证。

**Architecture:** 保留当前统一前台链路：text 和 ASR 成功 voice 都走 `unified` + `fast_llm`。普通对话每轮输入当前用户消息、最近 5 轮成功对话、最多 10 条长期记忆、降噪后的 pet_state；LLM 输出最新回复、表情、动作、语音风格和只含 `energy/intimacy` 的状态增量。memory summary 后台异步执行，输出完整替换后的 0-10 条长期记忆，并保护非空旧记忆不被空列表覆盖。

**Tech Stack:** FastAPI backend, SQLite runtime state, React/Vite frontend, pytest, vitest, Termux on Nubia through `adb forward` + `ssh nubia-adb`.

---

## Current Project Facts

- Repo: `/Users/wylam/Documents/workspace/Petagent`
- Spec: `plan/V1.7/context-memory-voice-stability-spec.md`
- Current Nubia status from the 2026-05-31 review pass:
  - `adb devices -l` returned one online Nubia: `9debb82b device ... model:NX531J`.
  - `adb forward --list` was initially empty, then forwards were restored:
    - `9debb82b tcp:18000 tcp:8000`
    - `9debb82b tcp:18022 tcp:8022`
  - `ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'` is healthy:
    - user is Termux `u0_a137`
    - groups include Android `inet`
    - `context: ok`
    - backend process is running
  - HTTP checks through `tcp:18000` currently work:
    - `/api/health` returns ok with running backend build hash `eb0d021`
    - `/build-info.json` returns frontend build info with git sha `de94b22`
  - Termux currently has `python`/`python3` and `~/Petagent/.venv/bin/python`, but no `sqlite3` CLI. Nubia validation SQL commands must use Python SQLite one-liners unless `sqlite3` is installed later.
- Deployment rule from V1.6 still applies:
  - HTTP verification: `adb forward tcp:18000 tcp:8000`
  - Termux restart/deploy control: `adb forward tcp:18022 tcp:8022` + `ssh nubia-adb`
  - Do not start backend through `adb shell su` as root; Android socket permission requires Termux `inet` group.

## Key Files

- `backend/app/pet/prompt_builder.py`
  Builds unified foreground prompt and memory summary prompt.
- `backend/app/runtime/context_manager.py`
  Selects recent 5 successful dialogue turns and `memory.md` lines for unified route.
- `backend/app/runtime/context_store.py`
  Contains `EventLogStore.recent_dialogue_turns()` and `SuccessfulTurnStore`.
- `backend/app/pet/guard.py`
  Validates LLM output. `guard_fast_reply_action()` currently ignores `state_delta`.
- `backend/app/runtime/actions.py`
  Defines `FastReplyAction` and `PetResponse`.
- `backend/app/runtime/dispatcher.py`
  Runs unified LLM, applies state, records event, queues TTS and memory summary.
- `backend/app/runtime/memory_judgment.py`
  Background memory summary queue.
- `backend/app/runtime/notebook.py`
  Canonical `memory.md` read/write.
- `backend/app/api/memory.py`
  `/api/runtime/reset`.
- `backend/app/providers/asr_http.py`
  Configurable HTTP ASR provider retry and timeout behavior.
- `config/models.yaml`
  ASR timeout/retry/model configuration.
- `config/pet_persona.yaml`
  Base persona wording; must keep first-person visible replies and avoid encouraging self-naming.
- `frontend/src/App.tsx`
  Reset flow, expression application, ambient local state.
- `frontend/src/pet/ambient.ts`
  Ambient localStorage helpers.

## Implementation Assumptions

1. `state_delta.energy` and `state_delta.intimacy` are deltas, not absolute values.
2. V1.7 accepts only small integer deltas in `[-5, 5]`; values outside this range are ignored, not clamped.
3. `sleepiness` remains in database and UI for compatibility, but it is not included in unified LLM prompt and is ignored if LLM outputs it.
4. Reset clears user-facing state and memory but keeps debug/audit data: `agent_run`, `audio_job`, uploads, `voice_debug.jsonl`.
5. Pure local button interactions do not count toward the 10-turn memory summary. Model-backed button interactions count only if they produce successful LLM text.
6. Existing deterministic event rules may still update non-LLM state fields for button/system events. The V1.7 restriction is specifically that LLM output can update only `energy` and `intimacy`.

---

## Task 1: Backend Prompt Payload And Schema

**Files:**
- Modify: `backend/app/pet/prompt_builder.py`
- Modify: `config/pet_persona.yaml`
- Test: `backend/tests/test_v17_context_memory_state.py`
- Update likely existing tests: `backend/tests/test_fast_reply_contract.py`, `backend/tests/test_v15_unified_context.py`

- [x] **Step 1: Add tests for unified payload field names**

Create `backend/tests/test_v17_context_memory_state.py` with tests that build `build_unified_foreground_messages()` and assert:

```python
import json

from app.config import load_settings
from app.pet.prompt_builder import build_unified_foreground_messages
from app.runtime.context import build_runtime_context
from app.runtime.events import normalize_event


def _payload_for_state(pet_state):
    settings = load_settings()
    event = normalize_event({
        "type": "text_message",
        "source": "text",
        "payload": {"user_text": "今天星期几"},
    })
    context = build_runtime_context(
        event,
        pet_state,
        cognition_context={
            "context_profile": "unified",
            "recent_exact_events": [{"user": "你在干嘛", "pet": "我在玩", "created_at": "2026-05-31T10:00:00"}],
            "selected_card_items": ["- [2026-05-31 10:00][preference] 用户喜欢咖啡。"],
        },
    )
    messages = build_unified_foreground_messages(settings, event, context)
    return messages, json.loads(messages[1]["content"])


def test_unified_prompt_uses_v17_payload_sections():
    messages, payload = _payload_for_state({
        "mood": "angry",
        "energy": 10,
        "intimacy": 80,
        "sleepiness": 86,
    })

    assert "current_user_message" in payload
    assert "recent_conversation_context" in payload
    assert "long_term_memory" in payload
    assert "pet_state" in payload
    assert "response_schema" in payload
    assert "user_input" not in payload
    assert "recent_dialogue" not in payload
    assert "sleepiness" not in payload["pet_state"]

    system = messages[0]["content"]
    assert "最近上下文" in system
    assert "长期记忆" in system
    assert "不是措辞模板" in system
    assert "只在相关时使用" in system
    assert "不要自称" in system
    assert "回复主语" in system or "台词主语" in system


def test_unified_pet_state_has_levels_and_no_sleepiness():
    _, payload = _payload_for_state({
        "mood": "angry",
        "energy": 10,
        "intimacy": 80,
        "sleepiness": 86,
    })

    assert payload["pet_state"] == {
        "mood": "angry",
        "energy": 10,
        "energy_level": "low",
        "intimacy": 80,
        "intimacy_level": "high",
    }


def test_no_friendly_fallback_constants_remain():
    from app.pet import guard

    assert not hasattr(guard, "FALLBACK_ACTION")
    assert not hasattr(guard, "FAST_REPLY_FALLBACK")
```

- [x] **Step 2: Implement pet_state level helper**

In `backend/app/pet/prompt_builder.py`, replace `_foreground_pet_state()` with a V1.7 version:

```python
def _level(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    if number < 34:
        return "low"
    if number < 67:
        return "medium"
    return "high"


def _foreground_pet_state(context: RuntimeContext) -> Dict[str, Any]:
    energy = context.pet_state.get("energy", 50)
    intimacy = context.pet_state.get("intimacy", 0)
    return {
        "mood": context.pet_state.get("mood", "idle"),
        "energy": energy,
        "energy_level": _level(energy),
        "intimacy": intimacy,
        "intimacy_level": _level(intimacy),
    }
```

- [x] **Step 2.5: Remove unused friendly fallback reply constants**

In `backend/app/pet/guard.py`, delete `FALLBACK_ACTION` and `FAST_REPLY_FALLBACK` if they are unused. If a local import unexpectedly still depends on them, change their reply strings to first-person text without `豆豆`, but do not wire them into failure handling. V1.7 failure handling remains explicit failure with empty reply.

- [x] **Step 3: Update unified output schema**

Change `FAST_REPLY_SCHEMA` in `backend/app/pet/prompt_builder.py` so it includes only allowed state delta:

```python
"state_delta": {
    "energy": "可选，小整数 delta，范围 -5 到 5；过大或非数字会被忽略",
    "intimacy": "可选，小整数 delta，范围 -5 到 5；过大或非数字会被忽略",
}
```

Do not include `sleepiness`, `hunger`, `cleanliness`, or `loneliness` in the unified schema.

- [x] **Step 4: Rename unified user payload fields**

In `build_unified_foreground_messages()`, build:

```python
payload = {
    "current_user_message": str(event.payload.get("user_text") or event.payload.get("text") or ""),
    "recent_conversation_context": list(cognition.get("recent_exact_events") or [])[-5:],
    "long_term_memory": _selected_notebook_lines(cognition.get("selected_card_items"), 10),
    "pet_state": _foreground_pet_state(context),
    "response_schema": FAST_REPLY_SCHEMA,
}
```

- [x] **Step 5: Strengthen unified system prompt without hard-banning words**

Add rules to the V1.5/V1.6 unified system prompt:

```text
V1.7 上下文使用规则：
1. current_user_message 是本轮最高优先级输入，必须先回应它。
2. recent_conversation_context 只用于理解连续上下文，不是措辞模板。
3. long_term_memory 是长期背景事实，只在和当前问题相关时使用，不要每轮主动复述。
4. 不要把自己上一轮的口头表达、玩笑、情绪当成长期事实。
5. pet_state 是当前状态参考，不能压过本轮用户意图；mood 不代表必须延续上一轮情绪。
6. energy 低可以影响语气，但不能成为拒绝正常回答的理由。
7. 每轮都要根据当前用户输入重新选择 expression_key 和 action。
```

Also update `config/pet_persona.yaml` so the base persona does not encourage visible self-naming. It may still define the pet's name for identity, but the speaking rules must explicitly say: replies use only first-person `我` as the subject and must not self-reference as `豆豆`.

- [x] **Step 6: Run prompt tests**

Run:

```bash
cd backend
../.venv/bin/python -m pytest tests/test_v17_context_memory_state.py tests/test_fast_reply_contract.py tests/test_v15_unified_context.py -q
```

Expected: new tests pass, existing tests updated for field rename and no `sleepiness`.

---

## Task 2: Unified State Delta Output And Commit

**Files:**
- Modify: `backend/app/runtime/actions.py`
- Modify: `backend/app/pet/guard.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Test: `backend/tests/test_v17_context_memory_state.py`

- [x] **Step 1: Extend `FastReplyAction`**

In `backend/app/runtime/actions.py`:

```python
class FastReplyAction(BaseModel):
    reply: str
    mood: Optional[str] = None
    expression_key: str = "idle_soft"
    action: Optional[str] = None
    voice_style: str = "soft"
    state_delta: Dict[str, int] = Field(default_factory=dict)
```

- [x] **Step 2: Add state delta guard for fast reply**

In `backend/app/pet/guard.py`, add:

```python
FAST_STATE_DELTA_KEYS = {"energy", "intimacy"}
FAST_STATE_DELTA_LIMIT = 5


def _sanitize_fast_state_delta(raw: Any) -> Dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    guarded: Dict[str, int] = {}
    for key in FAST_STATE_DELTA_KEYS:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if abs(number) > FAST_STATE_DELTA_LIMIT:
            continue
        guarded[key] = number
    return guarded
```

Then return it from `guard_fast_reply_action()`:

```python
state_delta=_sanitize_fast_state_delta(data.get("state_delta") or {}),
```

- [x] **Step 3: Add guard tests**

Add tests:

```python
from app.pet.guard import guard_fast_reply_action


def test_fast_reply_guard_accepts_only_energy_intimacy_state_delta():
    action = guard_fast_reply_action({
        "reply": "我在。",
        "mood": "happy",
        "state_delta": {
            "energy": -2,
            "intimacy": 1,
            "sleepiness": 99,
            "hunger": 99,
        },
    })

    assert action.state_delta == {"energy": -2, "intimacy": 1}


def test_fast_reply_guard_ignores_oversized_state_delta():
    action = guard_fast_reply_action({
        "reply": "我在。",
        "state_delta": {"energy": -100, "intimacy": 100},
    })

    assert action.state_delta == {}
```

- [x] **Step 4: Apply state delta in unified dispatcher path**

In `backend/app/runtime/dispatcher.py`, in the `is_fast_reply` branch after `final_state = dict(ruled_state)`:

```python
final_state = apply_state_delta(final_state, fast_action.state_delta)
```

Keep this after deterministic event rules and before mood/mode/last_interaction_at assignment.

Also add `state_delta` to `run.final_action` for debug:

```python
"state_delta": dict(fast_action.state_delta),
```

In the CAS retry branch for `is_fast_reply`, recompute the same way:

```python
final_state = dict(ruled_state)
if fast_action:
    final_state = apply_state_delta(final_state, fast_action.state_delta)
    if fast_action.mood:
        final_state["mood"] = fast_action.mood
```

- [x] **Step 5: Add dispatcher state tests**

Add tests:

```python
from app.main import create_app


def test_unified_applies_energy_and_intimacy_state_delta():
    app = create_app(testing=True)
    app.state.state_store.save_state({
        **app.state.state_store.get_state(),
        "energy": 50,
        "intimacy": 40,
        "mood": "idle",
    })
    app.state.dispatcher.brain.provider.complete_json = lambda messages: {
        "reply": "我听到啦。",
        "mood": "happy",
        "expression_key": "happy",
        "action": "speak",
        "voice_style": "normal",
        "state_delta": {"energy": -2, "intimacy": 1, "sleepiness": 99},
    }

    response = app.state.dispatcher.handle_event({
        "type": "text_message",
        "source": "runtime",
        "payload": {"user_text": "你好"},
    }, synthesize_voice=False)

    assert response.pet_state["energy"] == 48
    assert response.pet_state["intimacy"] == 42  # text_message rule +1, LLM delta +1
    assert response.pet_state["sleepiness"] == 15
    runs = app.state.agent_run_store.recent(limit=1)
    assert runs[0]["final_action"]["state_delta"] == {"energy": -2, "intimacy": 1}
```

- [x] **Step 6: Run state tests**

Run:

```bash
cd backend
../.venv/bin/python -m pytest tests/test_v17_context_memory_state.py tests/test_fast_reply_contract.py tests/test_dispatcher_pet_effort.py -q
```

Expected: unified route applies only allowed `energy/intimacy` delta and ignores `sleepiness`.

---

## Task 3: Memory Summary Context And Empty-List Protection

**Files:**
- Modify: `backend/app/runtime/dispatcher.py`
- Modify: `backend/app/runtime/memory_judgment.py`
- Modify: `backend/app/pet/prompt_builder.py`
- Modify if needed: `backend/app/runtime/notebook.py`
- Test: `backend/tests/test_memory_judgment.py`
- Test: `backend/tests/test_v17_context_memory_state.py`

- [x] **Step 1: Gate successful-turn counting to V1.7 eligible LLM replies**

In `RuntimeDispatcher._handle_event_split()`, only call `successful_turn_store.record_successful_turn()` for event types that V1.7 says can count:

```python
eligible_successful_turn = event.type in {"text_message", "voice_message"} or (
    event.type in BUTTON_EVENTS and bool(reply_text)
)
```

Then wrap successful-turn recording and memory summary enqueueing with `eligible_successful_turn`. ASR failures already return before dispatcher, so they must not count. LLM failures return `_failure_response()` before post-commit, so they must not count. Wake/exit/proactive/system events must not advance the 10-turn memory summary counter.

Add a regression test:

```python
def test_successful_turn_counter_counts_only_v17_eligible_events():
    app = create_app(testing=True)
    provider = app.state.dispatcher.brain.provider
    provider.complete_json = lambda messages: {
        "reply": "我在。",
        "mood": "happy",
        "expression_key": "happy",
        "action": "speak",
        "voice_style": "normal",
    }

    app.state.dispatcher.handle_event({"type": "morning", "source": "proactive", "payload": {}}, synthesize_voice=False)
    assert app.state.successful_turn_store.snapshot()["successful_turn_count_total"] == 0

    app.state.dispatcher.handle_event({
        "type": "text_message",
        "source": "runtime",
        "payload": {"user_text": "你好"},
    }, synthesize_voice=False)
    assert app.state.successful_turn_store.snapshot()["successful_turn_count_total"] == 1
```

- [x] **Step 2: Extend memory summary enqueue signature**

In `MemoryJudgmentQueue.enqueue_turn_summary()`, add parameter:

```python
recent_conversation_context: Optional[List[Dict[str, Any]]] = None,
```

Store it in the job:

```python
"recent_conversation_context": list(recent_conversation_context or [])[-5:],
```

- [x] **Step 3: Pass previous recent context without duplicating current turn**

In `RuntimeDispatcher._handle_event_split()`, before `enqueue_turn_summary()`, build:

```python
recent_context = []
if cognition_context:
    raw_recent = cognition_context.get("recent_exact_events") or []
    if isinstance(raw_recent, list):
        recent_context = list(raw_recent)[-5:]
recent_context = recent_context[-5:]
```

Pass it:

```python
recent_conversation_context=recent_context,
```

Do not append the current turn to `recent_conversation_context`. The summary payload has a dedicated `current_turn` section; duplicating the same turn in the recent list makes the contract ambiguous and can bias the summarizer toward over-weighting the latest line.

- [x] **Step 4: Rewrite memory summary prompt structure**

Change `build_memory_summary_messages()` signature to accept:

```python
recent_conversation_context: Optional[List[Dict[str, Any]]] = None,
```

Use payload:

```python
payload = {
    "current_turn": {
        "current_user_message": user_text,
        "current_pet_reply": pet_reply,
        "route": route,
        "trigger_categories": trigger_categories,
    },
    "recent_conversation_context": list(recent_conversation_context or [])[-5:],
    "long_term_memory_file": memory_content or "（空）",
    "output_schema": MEMORY_SUMMARY_SCHEMA,
}
```

System prompt must say:

```text
输出是完整替换后的长期记忆列表，不是本轮新增列表。
如果 long_term_memory_file 里已有有效记忆，默认原样保留旧记忆，只在当前证据明确要求时更新、合并或移除。
不能因为本轮没有新增长期信息就输出空列表。
只有 long_term_memory_file 本来没有有效记忆，且 current_turn 与 recent_conversation_context 都没有长期价值信息时，才允许输出 {"memories": []}。
```

Remove `selected_memory` from the new summary prompt payload. It is no longer sufficient evidence because V1.7 requires the full current `memory.md` text. The `enqueue_turn_summary()` signature may keep `selected_memory` temporarily for compatibility during the patch, but `_process_turn_summary()` must not pass it into `build_memory_summary_messages()`.

- [x] **Step 5: Protect non-empty memory from empty summary**

In `_process_turn_summary()`, after `memories = self._validate_memories(result)`:

```python
existing_entries = []
if self._notebook_manager is not None:
    existing_entries = self._notebook_manager.parse_memory()
if existing_entries and memories == []:
    return {"should_write": False, "memories": [], "error": "empty_summary_would_clear_existing_memory"}
```

Then only call `overwrite_memory_lines(memories)` if this guard did not fire.

- [x] **Step 6: Keep backend validation format-only**

Do not add deterministic semantic dedup. `_validate_memories()` should continue to check only:

- result is dict
- `memories` is list
- length <= 10
- each item is dict
- category in whitelist
- content non-empty

Existing `NotebookManager.overwrite_memory_lines()` still handles timestamp/sensitive/length protection.

- [x] **Step 7: Add memory tests**

Add tests:

```python
def test_turn_summary_prompt_includes_current_and_recent_context():
    provider = MockProvider(result={
        "memories": [{"category": "preference", "content": "用户喜欢短回复"}],
    })
    tmp = Path(mkdtemp())
    notebook = NotebookManager(tmp / "user.md", tmp / "memory.md")
    q = MemoryJudgmentQueue(provider=provider, notebook_manager=notebook)

    q.enqueue_turn_summary(
        user_text="我喜欢短回复",
        pet_reply="我记住啦",
        route="unified",
        recent_conversation_context=[
            {"user": "上一句", "pet": "上一答", "created_at": "2026-05-31T10:00:00"},
        ],
        trigger_categories=["preference"],
    )
    q.process_one()
    payload = json.loads(provider.last_messages[1]["content"])

    assert payload["current_turn"]["current_user_message"] == "我喜欢短回复"
    assert payload["recent_conversation_context"][-1]["user"] == "上一句"
    assert all(item.get("user") != "我喜欢短回复" for item in payload["recent_conversation_context"])
    assert "long_term_memory_file" in payload
    assert "selected_memory" not in payload


def test_empty_summary_does_not_clear_existing_memory():
    provider = MockProvider(result={"memories": []})
    tmp = Path(mkdtemp())
    notebook = NotebookManager(tmp / "user.md", tmp / "memory.md")
    assert notebook.overwrite_memory_lines([
        {"category": "preference", "content": "用户喜欢咖啡。"}
    ])
    q = MemoryJudgmentQueue(provider=provider, notebook_manager=notebook)

    q.enqueue_turn_summary("今天星期几", "星期日", "unified")
    result = q.process_one()

    assert result["should_write"] is False
    assert "用户喜欢咖啡" in notebook.read_raw("memory.md")
```

- [x] **Step 8: Run memory tests**

Run:

```bash
cd backend
../.venv/bin/python -m pytest tests/test_memory_judgment.py tests/test_v15_successful_turns.py tests/test_v17_context_memory_state.py -q
```

Expected: summary payload contains current turn + recent context, and empty output cannot clear non-empty `memory.md`.

---

## Task 4: Reset Completeness Without Deleting Debug Data

**Files:**
- Modify: `backend/app/runtime/memory_judgment.py`
- Modify: `backend/app/api/memory.py`
- Modify: `frontend/src/pet/ambient.ts`
- Modify: `frontend/src/App.tsx`
- Test: backend reset test file, likely `backend/tests/test_api_contracts.py` or new `backend/tests/test_v17_reset.py`
- Test: `frontend/src/pet/ambient.test.ts`
- Test: `frontend/src/pet/api.test.ts`
- Test: `frontend/src/App.test.tsx`

- [x] **Step 1: Add queue clear method**

In `MemoryJudgmentQueue`:

```python
def clear(self) -> None:
    with self._lock:
        self._pending.clear()
        self._seen.clear()
```

- [x] **Step 2: Clear successful turn counters and summary queue in reset**

In `/api/runtime/reset`, add:

```python
successful_turn_store = getattr(request.app.state, "successful_turn_store", None)
memory_judgment_queue = getattr(request.app.state, "memory_judgment_queue", None)
notebook_manager = getattr(request.app.state, "notebook_manager", None)

if successful_turn_store:
    successful_turn_store.clear_all()
if memory_judgment_queue:
    memory_judgment_queue.clear()
if notebook_manager:
    notebook_manager.overwrite_memory_lines([])
```

Keep existing deletes for `raw_event_log`, `episode`, `interaction_log`, old memory stores, and pet state reset. `NotebookManager.overwrite_memory_lines([])` must leave canonical `memory.md` with only the V1.4 marker and must rewrite `user.md` to the single-notebook stub.

Do not delete:

- `agent_run`
- `audio_job`
- uploaded files under `backend/data/uploads`
- `backend/data/logs/voice_debug.jsonl`
- `backend/static/audio`

Also fix the reset reply in `backend/app/api/memory.py`: it currently says `你好呀，我是豆豆。我们重新开始认识吧。`, which violates the V1.7 first-person rule. Change it to first person without self-naming, for example `你好呀，我在这里。我们重新开始认识吧。`.

- [x] **Step 3: Add backend reset test**

Create `backend/tests/test_v17_reset.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_runtime_reset_clears_user_context_but_keeps_debug_tables():
    app = create_app(testing=True)
    client = TestClient(app)
    token = app.state.internal_token

    app.state.notebook_manager.overwrite_memory_lines([
        {"category": "preference", "content": "用户喜欢咖啡。"}
    ])
    app.state.successful_turn_store.record_successful_turn("evt-1")
    assert app.state.memory_judgment_queue.enqueue_turn_summary("记住咖啡", "我记住啦", "unified")
    app.state.agent_run_store.save({
        "run_id": "run-reset-audit",
        "event_id": "evt-audit",
        "status": "completed",
        "final_action": {"reply": "审计保留"},
    })
    app.state.audio_job_store.save({
        "job_id": "job-reset-audit",
        "status": "failed",
        "text": "审计保留",
        "created_at": "2026-05-31T10:00:00",
        "updated_at": "2026-05-31T10:00:00",
    })

    response = client.post(
        "/api/runtime/reset",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm": "重新认识"},
    )

    assert response.status_code == 200
    assert "我是豆豆" not in response.json()["reply"]
    assert app.state.event_log_store.count() == 0
    assert app.state.successful_turn_store.snapshot()["successful_turn_count_total"] == 0
    assert app.state.memory_judgment_queue.pending_count() == 0
    assert "用户喜欢咖啡" not in app.state.notebook_manager.read_raw("memory.md")
    assert "<!-- v1.4_single_notebook -->" in app.state.notebook_manager.read_raw("memory.md")
    assert "canonical memory is memory.md" in app.state.notebook_manager.read_raw("user.md")
    assert app.state.agent_run_store.count() == 1
    assert app.state.audio_job_store.get("job-reset-audit") is not None
```

- [x] **Step 4: Add frontend ambient reset helper**

In `frontend/src/pet/ambient.ts`:

```ts
export function resetAmbientState(storage: Storage): void {
  try {
    storage.removeItem(AMBIENT_STORAGE_KEY);
  } catch {
    // Ambient bubbles are optional; private-mode storage failures should stay silent.
  }
}
```

In `frontend/src/App.tsx`, import and call it after reset succeeds:

```ts
resetAmbientState(window.localStorage);
```

Do not call `markIdleAnchor(true)` immediately after `resetAmbientState()`, because `markIdleAnchor()` writes a new ambient record back to localStorage. Instead, reset the in-memory refs/state without persisting:

```ts
const now = Date.now();
idleAnchorAtRef.current = now;
idleStepRef.current = 0;
setIdleAnchorAt(now);
setIdleStep(0);
```

On reset success also clear transient audio/UI state so old audio jobs cannot affect the new session:

```ts
audioRunRef.current += 1;
stopCurrentAudioPlayback();
setLastAudioJobId(null);
setPetPhase("idle");
setBusyState(false);
setRecordingActiveState(false);
setInputActiveState(false);
setActiveSession(null);
pendingAmbientEventRef.current = null;
ambientInFlightRef.current = false;
```

The `finally` block must not call `markIdleAnchor(true)` after a successful reset. If keeping a shared `finally`, guard the call so only failed reset attempts persist a new idle anchor.

- [x] **Step 5: Add frontend ambient reset test**

In `frontend/src/pet/ambient.test.ts`:

```ts
import { resetAmbientState } from "./ambient";

test("resetAmbientState clears persisted idle state", () => {
  const storage = new Map<string, string>();
  const fakeStorage = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
    length: 0,
    clear: () => storage.clear(),
    key: () => null,
  } as Storage;
  saveAmbientState(fakeStorage, { idleAnchorAt: 1000, idleStep: 2, localDate: "2026-05-31" });
  resetAmbientState(fakeStorage);
  expect(loadAmbientState(fakeStorage, "2026-05-31")).toBeNull();
});
```

- [x] **Step 6: Add frontend App reset regression test**

In `frontend/src/App.test.tsx`, add a regression test that clicks `重新认识`, confirms the dialog, and asserts:

- `window.localStorage.getItem("petagent:v16:ambient-state")` is `null` after reset success.
- the face is `idle_soft`/idle after reset.
- old audio retry UI is not visible after reset.
- the reset POST body remains `{"confirm":"重新认识"}` and does not contain `thinking_mode`.

Also keep the existing `frontend/src/pet/api.test.ts` assertions that `sendTextChat(..., { thinkingMode: true })` and `uploadVoice(..., { thinkingMode: true })` do not send `thinking_mode`. Do not add any frontend thinking-mode control.

- [x] **Step 7: Run reset tests**

Run:

```bash
cd backend
../.venv/bin/python -m pytest tests/test_v17_reset.py tests/test_api_contracts.py -q

cd ../frontend
npm test -- --run src/pet/ambient.test.ts src/pet/api.test.ts src/App.test.tsx
```

Expected: reset clears user-facing memory/context/state and leaves debug stores untouched.

---

## Task 5: ASR Timeout Retry And Configurable Timeout Split

**Files:**
- Modify: `backend/app/providers/asr_http.py`
- Modify: `config/models.yaml`
- Test: `backend/tests/test_asr_http_provider.py`

- [x] **Step 1: Add timeout split helper**

Replace `_timeout_tuple()` with a helper that accepts optional explicit connect/read values:

```python
def _timeout_tuple(
    scalar: int,
    connect: Optional[int] = None,
    read: Optional[int] = None,
) -> tuple:
    scalar = max(1, int(scalar))
    if connect is not None or read is not None:
        connect_timeout = max(1, int(connect if connect is not None else min(2, scalar)))
        read_timeout = max(1, int(read if read is not None else max(scalar - connect_timeout, 1)))
        return (connect_timeout, read_timeout)
    connect_timeout = min(2, scalar)
    return (connect_timeout, max(scalar - connect_timeout, 1))
```

- [x] **Step 2: Read ASR timeout config**

In `_request_kwargs()`:

```python
connect_timeout = self.config.extra.get("connect_timeout_seconds")
read_timeout = self.config.extra.get("read_timeout_seconds")
common = {
    ...
    "timeout": _timeout_tuple(
        self.config.timeout_seconds,
        connect=connect_timeout,
        read=read_timeout,
    ),
}
```

- [x] **Step 3: Retry `asr_timeout`**

In `_should_retry()`:

```python
if error_code in {"asr_request_error", "asr_provider_error", "asr_empty", "asr_timeout"}:
    return True
```

Authentication/client HTTP 4xx must still not retry.

- [x] **Step 4: Update `config/models.yaml`**

Under `providers.asr`, set:

```yaml
timeout_seconds: 12
connect_timeout_seconds: 4
read_timeout_seconds: 12
transient_retries: 2
retry_backoff_seconds: 0.2
```

Keep current model order:

```yaml
model: TeleAI/TeleSpeechASR
fallback_models:
  - FunAudioLLM/SenseVoiceSmall
```

`config.ProviderConfig` keeps `timeout_seconds` as the top-level scalar and places all other provider keys in `config.extra`, so `connect_timeout_seconds`, `read_timeout_seconds`, `transient_retries`, and `retry_backoff_seconds` must be siblings under `providers.asr`, not nested under another key.

- [x] **Step 5: Update ASR tests**

Change `test_http_asr_does_not_retry_timeouts` into:

```python
def test_http_asr_retries_timeouts_then_succeeds(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    config = provider_config()
    config.extra["transient_retries"] = 2
    config.extra["retry_backoff_seconds"] = 0
    calls = []

    class SuccessResponse:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"text": "一二三四五六七八九"}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) < 3:
            raise requests.Timeout("read timed out")
        return SuccessResponse()

    monkeypatch.setattr("app.providers.asr_http.requests.post", fake_post)

    transcript = HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert len(calls) == 3
    assert transcript.text == "一二三四五六七八九"
    assert transcript.error_code == ""
```

Add timeout config test:

```python
def test_http_asr_uses_configured_connect_and_read_timeouts(tmp_path: Path, monkeypatch):
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"RIFF fake wav")
    config = provider_config()
    config.extra["connect_timeout_seconds"] = 4
    config.extra["read_timeout_seconds"] = 12
    captured = {}

    class Response:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"text": "你好"}

    monkeypatch.setattr("app.providers.asr_http.requests.post", lambda url, **kwargs: captured.update(kwargs) or Response())

    HttpASRProvider(config).transcribe(audio, "audio/wav")

    assert captured["timeout"] == (4, 12)
```

- [x] **Step 6: Run ASR tests**

Run:

```bash
cd backend
../.venv/bin/python -m pytest tests/test_asr_http_provider.py tests/test_voice_pipeline.py tests/test_voice_contract.py -q
```

Expected: timeout retries up to 3 attempts, 4xx does not retry, final timeout remains explicit failure.

---

## Task 6: Local Integration Test Pass

**Files:**
- No new files unless previous tasks require test updates.

- [x] **Step 1: Run targeted backend tests**

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest \
  tests/test_v17_context_memory_state.py \
  tests/test_v17_reset.py \
  tests/test_memory_judgment.py \
  tests/test_fast_reply_contract.py \
  tests/test_v15_unified_context.py \
  tests/test_v15_successful_turns.py \
  tests/test_v15_failure_contract.py \
  tests/test_asr_http_provider.py \
  tests/test_voice_pipeline.py \
  tests/test_voice_contract.py \
  tests/test_text_chat.py \
  -q
```

- [x] **Step 2: Run frontend tests and build**

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- --run
npm run build
```

- [x] **Step 3: Run backend full test if targeted pass is clean**

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest -q
```

Expected: no regression in prompt contract, voice failure contract, reset behavior, or ASR retry.

---

## Task 7: Nubia Deploy And Service Restart

**Files:**
- Runtime/deploy only.

- [x] **Step 1: Restore USB/ADB connection**

The 2026-05-31 review pass already restored the USB/ADB connection and both forwards. Still re-run before deployment because ADB forwards can disappear after reconnect:

```bash
adb devices -l
```

Expected: one Nubia device shown as `device`, not empty and not `unauthorized`.

If empty:

- Replug USB.
- Confirm phone USB debugging prompt.
- Run `adb kill-server && adb start-server`.
- Re-run `adb devices -l`.

- [x] **Step 2: Create required forwards**

```bash
adb forward tcp:18000 tcp:8000
adb forward tcp:18022 tcp:8022
adb forward --list
```

Expected:

- `tcp:18000 tcp:8000`
- `tcp:18022 tcp:8022`

- [x] **Step 3: Confirm real Termux SSH**

```bash
ssh -o ConnectTimeout=5 nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
```

Expected:

- `id` includes Termux user `u0_a137` and Android `inet` group.
- `scripts/status.sh` does not say `context: not Termux app network context`.

If SSH fails but ADB works:

- Do not start backend through `adb shell su`.
- Start/repair Termux sshd on the phone, then retry the forward + `ssh nubia-adb`.

- [x] **Step 4: Deploy**

```bash
cd /Users/wylam/Documents/workspace/Petagent
BUILD_FRONTEND=1 ./scripts/deploy_nubia.sh
```

Expected:

- Frontend build succeeds.
- Archive installs into `~/Petagent`.
- No runtime data directories are overwritten by deploy because script excludes `backend/data`, `backend/secrets`, uploads, and audio cache.

- [x] **Step 5: Restart service through SSH**

```bash
ssh -o ConnectTimeout=5 nubia-adb 'cd ~/Petagent && scripts/stop.sh && scripts/start.sh'
```

Then:

```bash
curl -fsS http://127.0.0.1:18000/api/health
curl -fsS http://127.0.0.1:18000/build-info.json
ssh -o ConnectTimeout=5 nubia-adb 'cd ~/Petagent && scripts/status.sh'
```

Expected:

- `/api/health` is OK.
- `/build-info.json` corresponds to the newly built frontend.
- `scripts/status.sh` shows process running and database quick_check ok.

---

## Task 8: Nubia Functional Validation

**Important:** Voice validation must use the phone frontend microphone button, not only curl or local file upload.

- [x] **Step 1: Capture pre-test state**

```bash
TOKEN="$(ssh nubia-adb 'cat ~/Petagent/backend/secrets/internal_token')"
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:18000/api/memory/debug
ssh nubia-adb "cd ~/Petagent && .venv/bin/python - <<'PY'
import json, sqlite3
con = sqlite3.connect('backend/data/pet.db')
con.row_factory = sqlite3.Row
rows = con.execute('select mood, energy, intimacy, sleepiness from pet_state').fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
PY"
```

Record:

- current `memory.md`
- `successful_turn_state`
- `pet_state`
- recent `raw_event_log`

- [x] **Step 2: Context anti-repetition test**

Use text API or the phone page to send 5 normal messages:

```bash
curl -sS http://127.0.0.1:18000/api/text/chat \
  -H 'content-type: application/json' \
  -d '{"text":"你在干嘛"}'
curl -sS http://127.0.0.1:18000/api/text/chat \
  -H 'content-type: application/json' \
  -d '{"text":"今天星期几"}'
curl -sS http://127.0.0.1:18000/api/text/chat \
  -H 'content-type: application/json' \
  -d '{"text":"你为什么刚刚会超时"}'
curl -sS http://127.0.0.1:18000/api/text/chat \
  -H 'content-type: application/json' \
  -d '{"text":"你现在心情怎么样"}'
curl -sS http://127.0.0.1:18000/api/text/chat \
  -H 'content-type: application/json' \
  -d '{"text":"帮我简单总结一下刚才聊了什么"}'
```

Then inspect:

```bash
ssh nubia-adb "cd ~/Petagent && .venv/bin/python - <<'PY'
import json, sqlite3
con = sqlite3.connect('backend/data/pet.db')
con.row_factory = sqlite3.Row
rows = con.execute('select event_type,user_text,pet_reply,mood_after,created_at_utc from raw_event_log order by id desc limit 8').fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
PY"
ssh nubia-adb "cd ~/Petagent && .venv/bin/python - <<'PY'
import json, sqlite3
con = sqlite3.connect('backend/data/pet.db')
con.row_factory = sqlite3.Row
rows = con.execute('select final_action_json from agent_run order by created_at desc limit 5').fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
PY"
```

Expected:

- Recent 5 turns are successful `text_message`/ASR-success `voice_message` only.
- Replies do not repeatedly lock into the same phrase pattern.
- `expression_key` in `agent_run.final_action_json` changes according to model output and is not always a question/annoyed placeholder.

- [x] **Step 3: State delta validation**

Run:

```bash
ssh nubia-adb "cd ~/Petagent && .venv/bin/python - <<'PY'
import json, sqlite3
con = sqlite3.connect('backend/data/pet.db')
con.row_factory = sqlite3.Row
rows = con.execute('select mood, energy, intimacy, sleepiness from pet_state').fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
PY"
```

Expected:

- `energy` and/or `intimacy` can change after successful LLM turns.
- `sleepiness` is not changed by LLM `state_delta`.
- Prompt/run payload does not include `sleepiness` as unified LLM context.

- [x] **Step 4: Memory summary validation**

Send:

```bash
curl -sS http://127.0.0.1:18000/api/text/chat \
  -H 'content-type: application/json' \
  -d '{"text":"我喜欢喝冰美式，你要记住"}'
```

The dispatcher notifies the in-process maintenance worker after the successful turn. Wait briefly and poll `memory.md`; do not start a second `create_app()` process to force maintenance, because the memory summary queue is in-memory and belongs to the already-running backend process.

```bash
for i in 1 2 3 4 5 6; do
  ssh nubia-adb 'cd ~/Petagent && sed -n "1,80p" backend/data/memory_cards/memory.md'
  sleep 5
done
```

If the memory has not updated after 30 seconds, inspect `backend/data/logs/runtime.log` for memory summary errors and keep waiting up to 5 minutes. Do not treat `scripts/status.sh` as a trigger; it only reports status.

Inspect canonical memory:

```bash
ssh nubia-adb 'cd ~/Petagent && sed -n "1,80p" backend/data/memory_cards/memory.md'
```

Expected:

- `memory.md` has at most 10 parseable memory lines.
- Similar facts are merged by the model prompt.
- If a summary output is empty while `memory.md` had valid old entries, old memory remains.

- [x] **Step 5: Reset validation**

From phone page, click `重新认识`.

Then inspect:

```bash
ssh nubia-adb 'cd ~/Petagent && sed -n "1,80p" backend/data/memory_cards/memory.md'
ssh nubia-adb "cd ~/Petagent && .venv/bin/python - <<'PY'
import json, sqlite3
con = sqlite3.connect('backend/data/pet.db')
con.row_factory = sqlite3.Row
queries = {
  'raw_count': 'select count(*) as raw_count from raw_event_log',
  'episode_count': 'select count(*) as ep_count from episode',
  'pet_state': 'select mood,energy,intimacy,sleepiness from pet_state',
}
for label, sql in queries.items():
    rows = [dict(r) for r in con.execute(sql).fetchall()]
    print(label, json.dumps(rows, ensure_ascii=False, indent=2))
PY"
ssh nubia-adb "cd ~/Petagent && .venv/bin/python - <<'PY'
import json, sqlite3
con = sqlite3.connect('backend/data/pet.db')
con.row_factory = sqlite3.Row
queries = {
  'turn_events': 'select count(*) as turn_events from successful_turn_event',
  'turn_state': 'select * from successful_turn_state',
  'audit_counts': 'select (select count(*) from agent_run) as agent_run_count, (select count(*) from audio_job) as audio_job_count',
}
for label, sql in queries.items():
    rows = [dict(r) for r in con.execute(sql).fetchall()]
    print(label, json.dumps(rows, ensure_ascii=False, indent=2))
PY"
```

Expected:

- `memory.md` contains marker/stub only and no old user facts.
- `raw_event_log`, `episode`, `interaction_log`, `successful_turn_event/state` are cleared.
- `pet_state` returns to initial values.
- Debug/audit tables and files still exist.

- [x] **Step 6: Real phone voice validation**

On the Nubia frontend page:

1. Tap the microphone button.
2. Record: `123456789 豆豆今天星期几`
3. Stop/send.
4. Repeat at least 5 times with short normal phrases.

Inspect:

```bash
ssh nubia-adb 'cd ~/Petagent && tail -n 20 backend/data/logs/voice_debug.jsonl'
ssh nubia-adb 'cd ~/Petagent && ls -lh backend/data/uploads | tail'
ssh nubia-adb "cd ~/Petagent && .venv/bin/python - <<'PY'
import json, sqlite3
con = sqlite3.connect('backend/data/pet.db')
con.row_factory = sqlite3.Row
rows = con.execute("select event_type,user_text,pet_reply,created_at_utc from raw_event_log where event_type='voice_message' order by id desc limit 8").fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
PY"
```

Expected:

- Uploaded audio files are normal size.
- ASR success has non-empty `user_text`.
- ASR timeout retries are reflected by longer ASR timings or final explicit `asr_timeout`.
- If ASR ultimately fails, no LLM reply is generated and no fake “听不清” success is recorded.
- Successful voice turns enter recent 5 context.

- [x] **Step 7: Expression validation on phone**

On the phone page:

1. Send a text message that produces a clear emotion.
2. Watch phase:
   - during thinking/listening: expression may become `thinking`.
   - after LLM response: expression must become latest `response.expression_key`.
   - during TTS playback and after audio finishes: expression must not fall back to a question mark unless latest LLM output was actually that expression.
3. Trigger an ambient bubble after idle timing if practical; confirm it also updates expression from latest ambient LLM output.

Inspect latest model output:

```bash
ssh nubia-adb "cd ~/Petagent && .venv/bin/python - <<'PY'
import json, sqlite3
con = sqlite3.connect('backend/data/pet.db')
con.row_factory = sqlite3.Row
rows = con.execute('select final_action_json from agent_run order by created_at desc limit 3').fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
PY"
```

Expected:

- Phone visible expression matches latest `expression_key` from `final_action_json`.

---

## Task 9: Commit And Push

- [x] **Step 1: Review diff**

```bash
cd /Users/wylam/Documents/workspace/Petagent
git status --short
git diff -- backend/app/pet/prompt_builder.py backend/app/runtime/dispatcher.py backend/app/runtime/memory_judgment.py backend/app/api/memory.py backend/app/providers/asr_http.py config/models.yaml frontend/src/App.tsx frontend/src/pet/ambient.ts
```

- [x] **Step 2: Ensure no generated/runtime artifacts are staged**

Do not stage:

- `frontend/dist`
- `backend/data`
- `backend/static/audio`
- `backend/secrets`
- uploaded audio files
- logs

- [x] **Step 3: Commit**

```bash
git add \
  plan/V1.7/context-memory-voice-stability-spec.md \
  plan/V1.7/context-memory-voice-stability-implementation-plan.md \
  backend/app/pet/prompt_builder.py \
  backend/app/runtime/actions.py \
  backend/app/pet/guard.py \
  backend/app/runtime/dispatcher.py \
  backend/app/runtime/memory_judgment.py \
  backend/app/api/memory.py \
  backend/app/providers/asr_http.py \
  config/models.yaml \
  config/pet_persona.yaml \
  frontend/src/App.tsx \
  frontend/src/pet/ambient.ts \
  backend/tests/test_v17_context_memory_state.py \
  backend/tests/test_v17_reset.py \
  backend/tests/test_memory_judgment.py \
  backend/tests/test_asr_http_provider.py \
  frontend/src/pet/ambient.test.ts

git commit -m "fix: stabilize v17 context memory and voice"
git push
```

Expected: commit includes spec/plan and implementation/tests only.

---

## Self-Review Checklist

- [x] Unified prompt uses `current_user_message`, `recent_conversation_context`, `long_term_memory`, `pet_state`.
- [x] Unified prompt does not include `sleepiness`.
- [x] Unified output schema includes `state_delta.energy/intimacy` only.
- [x] Fast reply guard rejects invalid/oversized state delta and ignores `sleepiness`.
- [x] Dispatcher applies fast `state_delta` only after successful LLM output.
- [x] Memory summary payload includes current turn and recent context.
- [x] Non-empty `memory.md` cannot be overwritten by empty summary.
- [x] Reset clears successful turn counters and memory queue.
- [x] Reset does not clear debug/audit data.
- [x] ASR timeout retries up to 3 attempts.
- [x] Nubia validation uses real phone frontend microphone recording.
