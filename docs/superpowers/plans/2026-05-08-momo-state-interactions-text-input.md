# Momo State Interactions And Text Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM-driven state affect, richer pet/emotional interaction buttons, and text chat with default TTS while preserving the existing voice, memory, context, and summary runtime.

**Architecture:** Keep the existing `RuntimeDispatcher -> ContextManager -> PetBrain -> Guard -> State/EventLog/Memory/TTS` path as the single runtime path. Extend `PetAction` with `state_affect`, route text chat through a new lightweight `TextPipeline`, and keep all button events on `/api/pet/event` so voice, text, and buttons share context and memory. Use `mimo-v2.5` for fast interactions by passing `fast_brain` explicitly, with Guard limiting state deltas and sanitizing affect metadata.

**Tech Stack:** FastAPI, Pydantic, SQLite, React, Vite, Vitest, pytest, MiMo LLM/TTS providers.

---

## Scope And Source Spec

Implement the approved design spec:

- `docs/superpowers/specs/2026-05-08-momo-state-interactions-text-input-design.md`

Do not add new skills, background wake, camera, browser automation, or a complex养成 subsystem in this phase.

## File Structure

Create:

- `backend/app/runtime/text_pipeline.py` — text route selection, activation detection, dispatcher calls, and route metadata.
- `backend/app/api/text.py` — `POST /api/text/chat`.
- `backend/tests/test_state_affect.py` — `PetAction` and Guard behavior for `state_affect`.
- `backend/tests/test_text_chat.py` — text API contract and route selection.
- `backend/tests/test_extended_interactions.py` — new button event contracts and state limits.
- `frontend/src/components/TextInputBar.tsx` — single-line text input and send button.
- `frontend/src/components/TextInputBar.test.tsx` — text input behavior tests.

Modify:

- `backend/app/runtime/actions.py` — add `StateAffect` model and field on `PetAction`.
- `backend/app/pet/guard.py` — validate `state_affect`, event-aware `state_delta` limits.
- `backend/app/pet/prompt_builder.py` — update output schema and prompt guidance.
- `backend/app/runtime/events.py` — add `text_message` and new interaction event types.
- `backend/app/pet/rules.py` — add lightweight base deltas for new interaction events.
- `backend/app/runtime/context_store.py` — migrate `raw_event_log` with `state_affect_json`.
- `backend/app/runtime/dispatcher.py` — pass event type to Guard, record `state_affect_json`.
- `backend/app/main.py` — instantiate `TextPipeline`, expose app state, include text router.
- `frontend/src/pet/types.ts` — add new event types, `state_affect`, and text response types.
- `frontend/src/pet/api.ts` — add `sendTextChat`, event descriptions for new buttons.
- `frontend/src/components/TouchArea.tsx` — main and more interaction buttons.
- `frontend/src/App.tsx` — integrate text input, thinking mode, more buttons, response handling.
- `frontend/src/styles.css` — text input and expanded interaction layout.
- `frontend/src/pet/api.test.ts` — verify text chat helper.
- `frontend/src/components/TouchArea.test.tsx` — verify new button events.

## Task 1: Add `state_affect` Contract And Guard

**Files:**

- Modify: `backend/app/runtime/actions.py`
- Modify: `backend/app/pet/guard.py`
- Modify: `backend/app/pet/prompt_builder.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Test: `backend/tests/test_state_affect.py`
- Test: `backend/tests/test_pet_guard.py`
- Test: `backend/tests/test_runtime_actions.py`

- [ ] **Step 1: Write failing tests for `StateAffect` model**

Create `backend/tests/test_state_affect.py`:

```python
from app.pet.guard import guard_action
from app.runtime.actions import PetAction, PetResponse, StateAffect


def test_pet_action_accepts_state_affect():
    action = PetAction(
        reply="嘿嘿，被夸到了。",
        mood="happy",
        face_type="happy",
        animation="bounce",
        vibration="light",
        state_affect=StateAffect(
            interaction_tone="affectionate",
            pet_effort="low",
            emotional_effect="encouraged",
            reason="用户夸了 Momo。",
        ),
    )

    assert action.state_affect.interaction_tone == "affectionate"
    assert action.state_affect.pet_effort == "low"
    assert action.state_affect.emotional_effect == "encouraged"


def test_guard_sanitizes_invalid_state_affect():
    action = guard_action(
        {
            "reply": "Momo 有点懵。",
            "mood": "idle",
            "state_affect": {
                "interaction_tone": "bad-tone",
                "pet_effort": "huge",
                "emotional_effect": "chaos",
                "reason": "x" * 260,
            },
        }
    )

    assert action.state_affect.interaction_tone == "neutral"
    assert action.state_affect.pet_effort == "none"
    assert action.state_affect.emotional_effect == "uncertain"
    assert len(action.state_affect.reason) <= 120


def test_guard_keeps_valid_state_affect():
    action = guard_action(
        {
            "reply": "Momo 被你鼓励到啦。",
            "mood": "happy",
            "state_affect": {
                "interaction_tone": "encouraging",
                "pet_effort": "low",
                "emotional_effect": "encouraged",
                "reason": "用户鼓励了 Momo。",
            },
        }
    )

    assert action.state_affect.interaction_tone == "encouraging"
    assert action.state_affect.pet_effort == "low"
    assert action.state_affect.emotional_effect == "encouraged"


def test_pet_response_can_expose_state_affect():
    response = PetResponse(
        reply="嘿嘿。",
        mood="happy",
        face_type="happy",
        animation="bounce",
        vibration="light",
        pet_state={"name": "Momo"},
        runtime={"event_id": "evt-test", "skills_used": []},
        state_affect={
            "interaction_tone": "affectionate",
            "pet_effort": "low",
            "emotional_effect": "happy",
            "reason": "用户摸了摸 Momo。",
        },
    )

    assert response.state_affect["interaction_tone"] == "affectionate"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest tests/test_state_affect.py -q
```

Expected: FAIL because `StateAffect` and `PetAction.state_affect` do not exist.

- [ ] **Step 3: Add `StateAffect` model**

Modify `backend/app/runtime/actions.py`:

```python
ALLOWED_INTERACTION_TONES = {
    "affectionate",
    "playful",
    "comforting",
    "encouraging",
    "demanding",
    "tiring",
    "quiet",
    "caregiving",
    "neutral",
}

ALLOWED_PET_EFFORTS = {"none", "low", "medium", "high"}

ALLOWED_EMOTIONAL_EFFECTS = {
    "happy",
    "comforted",
    "encouraged",
    "pressured",
    "annoyed",
    "sleepy",
    "calm",
    "lonely_relieved",
    "uncertain",
}


class StateAffect(BaseModel):
    interaction_tone: str = "neutral"
    pet_effort: str = "none"
    emotional_effect: str = "uncertain"
    reason: str = ""
```

Add the field to `PetAction`:

```python
class PetAction(BaseModel):
    schema_version: str = "0.1"
    reply: str
    mood: str = "idle"
    face_type: str = "idle"
    animation: str = "breathing"
    voice_style: str = "soft"
    vibration: str = "none"
    intent: str = "stage1_response"
    autonomy_notes: str = ""
    state_delta: Dict[str, int] = Field(default_factory=dict)
    state_affect: StateAffect = Field(default_factory=StateAffect)
    memory_update: MemoryUpdate = Field(default_factory=MemoryUpdate)
```

Add the response field to `PetResponse`:

```python
class PetResponse(BaseModel):
    schema_version: str = "0.1"
    reply: str
    mood: str
    face_type: str
    animation: str
    vibration: str
    pet_state: Dict[str, Any]
    runtime: Dict[str, Any]
    voice_url: Optional[str] = None
    state_affect: Optional[Dict[str, Any]] = None
```

- [ ] **Step 4: Add Guard sanitization**

Modify imports in `backend/app/pet/guard.py`:

```python
from app.runtime.actions import (
    ALLOWED_ANIMATIONS,
    ALLOWED_EMOTIONAL_EFFECTS,
    ALLOWED_INTERACTION_TONES,
    ALLOWED_MOODS,
    ALLOWED_PET_EFFORTS,
    ALLOWED_VIBRATIONS,
    ALLOWED_VOICE_STYLES,
    MOOD_ANIMATION_MAP,
    PetAction,
    StateAffect,
)
```

Add helper:

```python
def _guard_state_affect(raw: Any) -> StateAffect:
    data = raw if isinstance(raw, dict) else {}
    tone = str(data.get("interaction_tone") or "neutral")
    effort = str(data.get("pet_effort") or "none")
    effect = str(data.get("emotional_effect") or "uncertain")
    reason = str(data.get("reason") or "").strip()
    if tone not in ALLOWED_INTERACTION_TONES:
        tone = "neutral"
    if effort not in ALLOWED_PET_EFFORTS:
        effort = "none"
    if effect not in ALLOWED_EMOTIONAL_EFFECTS:
        effect = "uncertain"
    if len(reason) > 120:
        reason = reason[:119] + "…"
    return StateAffect(
        interaction_tone=tone,
        pet_effort=effort,
        emotional_effect=effect,
        reason=reason,
    )
```

Pass the guarded value into `PetAction`:

```python
return PetAction(
    reply=reply,
    mood=mood,
    face_type=face_type,
    animation=animation,
    voice_style=voice_style,
    vibration=vibration,
    intent=str(data.get("intent", "stage1_response")),
    autonomy_notes=str(data.get("autonomy_notes", "")),
    state_delta=_clamp_delta(data.get("state_delta") or {}),
    state_affect=_guard_state_affect(data.get("state_affect") or {}),
    memory_update=data.get("memory_update") or {"should_save": False, "content": ""},
)
```

- [ ] **Step 5: Update prompt output schema**

Modify `backend/app/pet/prompt_builder.py` `OUTPUT_SCHEMA_HINT`:

```python
"state_affect": {
    "interaction_tone": "affectionate/playful/comforting/encouraging/demanding/tiring/quiet/caregiving/neutral",
    "pet_effort": "none/low/medium/high",
    "emotional_effect": "happy/comforted/encouraged/pressured/annoyed/sleepy/calm/lonely_relieved/uncertain",
    "reason": "一句话说明为什么这样影响 Momo 状态",
},
```

Append prompt guidance in `build_pet_messages()`:

```python
system_prompt += (
    "\n\n状态联动规则：\n"
    "1. 你必须根据本轮互动和上下文输出 state_affect。\n"
    "2. state_delta 要保守，不要让数值暴涨暴跌。\n"
    "3. 用户让你连续做任务时，energy 可以下降，sleepiness 可以小幅上升。\n"
    "4. 用户夸你、摸你、抱你或陪你时，intimacy 可以上升，loneliness 可以下降。\n"
    "5. 按钮事件也必须结合最近上下文，不要只根据按钮名机械回复。\n"
)
```

- [ ] **Step 6: Run focused tests**

Before running tests, expose the affect metadata in `backend/app/runtime/dispatcher.py` when returning `PetResponse`:

```python
return PetResponse(
    reply=action.reply,
    mood=action.mood,
    face_type=action.face_type,
    animation=action.animation,
    vibration=action.vibration,
    voice_url=voice_url,
    pet_state=saved_state,
    runtime={
        "event_id": event.id,
        "skills_used": [item.get("skill_id") for item in skill_results],
        "episode_id": episode_id,
    },
    state_affect=action.state_affect.dict(),
)
```

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest tests/test_state_affect.py tests/test_pet_guard.py tests/test_runtime_actions.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add backend/app/runtime/actions.py backend/app/pet/guard.py backend/app/pet/prompt_builder.py backend/app/runtime/dispatcher.py backend/tests/test_state_affect.py backend/tests/test_pet_guard.py backend/tests/test_runtime_actions.py
git commit -m "feat: add Momo state affect contract"
```

## Task 2: Add Event-Aware State Delta Limits And Extended Events

**Files:**

- Modify: `backend/app/pet/guard.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Modify: `backend/app/runtime/events.py`
- Modify: `backend/app/pet/rules.py`
- Test: `backend/tests/test_extended_interactions.py`
- Test: `backend/tests/test_pet_guard.py`
- Test: `backend/tests/test_runtime_events.py`

- [ ] **Step 1: Write failing event and Guard tests**

Create `backend/tests/test_extended_interactions.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app
from app.pet.guard import guard_action
from app.runtime.events import normalize_event


def test_new_interaction_events_are_supported():
    for event_type in [
        "stay_with_me",
        "pet_pat",
        "praise_momo",
        "feed_momo",
        "comfort_me",
        "encourage_me",
        "listen_to_me",
        "tuck_in",
        "clean_face",
        "quiet_company",
        "take_a_break",
    ]:
        event = normalize_event({"event": event_type, "payload": {"description": event_type}})
        assert event.type == event_type


def test_guard_uses_feed_limit_for_hunger():
    action = guard_action(
        {
            "reply": "开饭啦。",
            "mood": "happy",
            "state_delta": {"hunger": -99},
        },
        event_type="feed_momo",
    )

    assert action.state_delta["hunger"] == -8


def test_guard_uses_clean_face_limit_for_cleanliness():
    action = guard_action(
        {
            "reply": "脸脸干净啦。",
            "mood": "shy",
            "state_delta": {"cleanliness": 99},
        },
        event_type="clean_face",
    )

    assert action.state_delta["cleanliness"] == 8


def test_extended_button_event_returns_contextual_response():
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/pet/event",
        json={
            "event": "praise_momo",
            "payload": {
                "description": "用户夸夸 Momo",
                "interaction_group": "pet_care",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"]
    assert "state_affect" in body
    assert body["runtime"]["episode_id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest tests/test_extended_interactions.py -q
```

Expected: FAIL because event types and `event_type` Guard parameter are missing.

- [ ] **Step 3: Add new allowed events**

Modify `backend/app/runtime/events.py` `ALLOWED_EVENTS`:

```python
ALLOWED_EVENTS = {
    "pet_head",
    "poke_face",
    "hug",
    "pet_pat",
    "praise_momo",
    "feed_momo",
    "stay_with_me",
    "comfort_me",
    "encourage_me",
    "listen_to_me",
    "tuck_in",
    "clean_face",
    "quiet_company",
    "take_a_break",
    "debug_happy",
    "debug_sleepy",
    "debug_angry",
    "voice_message",
    "text_message",
    "wake_phrase",
    "exit_phrase",
    "context_refresh",
    "morning",
    "night",
    "long_idle",
    "battery_low",
    "charging_started",
    "charging_stopped",
    "sleepy_time",
    "user_return",
}
```

- [ ] **Step 4: Add base event deltas**

Modify `backend/app/pet/rules.py` `EVENT_DELTAS`:

```python
"pet_pat": {
    "mood": "happy",
    "energy": 1,
    "intimacy": 1,
    "hunger": 0,
    "cleanliness": 0,
    "loneliness": -3,
    "sleepiness": 0,
},
"praise_momo": {
    "mood": "happy",
    "energy": 1,
    "intimacy": 1,
    "hunger": 0,
    "cleanliness": 0,
    "loneliness": -2,
    "sleepiness": 0,
},
"feed_momo": {
    "mood": "happy",
    "energy": 1,
    "intimacy": 1,
    "hunger": -4,
    "cleanliness": 0,
    "loneliness": -1,
    "sleepiness": 0,
},
"stay_with_me": {"mood": "concerned", "intimacy": 1, "loneliness": -4},
"comfort_me": {"mood": "concerned", "intimacy": 1, "loneliness": -3},
"encourage_me": {"mood": "happy", "energy": 1, "intimacy": 1, "loneliness": -2},
"listen_to_me": {"mood": "concerned", "intimacy": 1, "loneliness": -2},
"tuck_in": {"mood": "sleepy", "sleepiness": 3, "energy": -1, "loneliness": -1},
"clean_face": {"mood": "shy", "cleanliness": 5, "intimacy": 1},
"quiet_company": {"mood": "idle", "loneliness": -2},
"take_a_break": {"mood": "sleepy", "sleepiness": 2, "energy": 1},
"text_message": {"intimacy": 1, "loneliness": -3},
```

Use `"idle"` for `quiet_company` because `calm` is not an allowed mood.

- [ ] **Step 5: Make Guard event-aware**

Modify `backend/app/pet/guard.py`:

```python
DEFAULT_STATE_DELTA_LIMITS = {
    "energy": (-5, 5),
    "intimacy": (-1, 2),
    "hunger": (-3, 3),
    "cleanliness": (-2, 2),
    "loneliness": (-6, 3),
    "sleepiness": (-3, 5),
}

EVENT_STATE_DELTA_LIMITS = {
    "feed_momo": {"hunger": (-8, 2), "energy": (-3, 5)},
    "charging_started": {"hunger": (-8, 2), "energy": (-3, 8)},
    "clean_face": {"cleanliness": (-2, 8)},
}
```

Replace `_clamp_delta`:

```python
def _limits_for_event(event_type: str = "") -> Dict[str, tuple]:
    limits = dict(DEFAULT_STATE_DELTA_LIMITS)
    for key, value in EVENT_STATE_DELTA_LIMITS.get(event_type, {}).items():
        limits[key] = value
    return limits


def _clamp_delta(delta: Dict[str, Any], event_type: str = "") -> Dict[str, int]:
    guarded: Dict[str, int] = {}
    limits_by_key = _limits_for_event(event_type)
    for key, limits in limits_by_key.items():
        value = delta.get(key, 0)
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = 0
        low, high = limits
        guarded[key] = max(low, min(high, number))
    return guarded
```

Update `guard_action` signature and call:

```python
def guard_action(
    raw: Any,
    max_reply_chars: int = DEFAULT_MAX_REPLY_CHARS,
    event_type: str = "",
) -> PetAction:
    data = _parse_action(raw)
    if not data.get("reply"):
        data = dict(FALLBACK_ACTION)
    return PetAction(
        reply=_trim_reply(str(data.get("reply", FALLBACK_ACTION["reply"])).strip(), max_reply_chars),
        mood="idle",
        face_type="idle",
        animation="breathing",
        voice_style="soft",
        vibration="none",
        state_delta=_clamp_delta(data.get("state_delta") or {}, event_type),
        state_affect=_guard_state_affect(data.get("state_affect") or {}),
        memory_update=data.get("memory_update") or {"should_save": False, "content": ""},
    )
```

- [ ] **Step 6: Pass event type from dispatcher to Guard**

Modify `backend/app/runtime/dispatcher.py`:

```python
action = guard_action(
    raw_action,
    max_reply_chars=self._max_reply_chars(active_brain),
    event_type=event.type,
)
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest tests/test_extended_interactions.py tests/test_pet_guard.py tests/test_runtime_events.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add backend/app/runtime/events.py backend/app/pet/rules.py backend/app/pet/guard.py backend/app/runtime/dispatcher.py backend/tests/test_extended_interactions.py backend/tests/test_pet_guard.py backend/tests/test_runtime_events.py
git commit -m "feat: add contextual interaction events"
```

## Task 3: Persist `state_affect` In Raw Event Log

**Files:**

- Modify: `backend/app/runtime/context_store.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Test: `backend/tests/test_stage35_event_log.py`
- Test: `backend/tests/test_state_affect.py`

- [ ] **Step 1: Write failing event log test**

Append to `backend/tests/test_state_affect.py`:

```python
from app.db import create_state_store
from app.config import load_settings
from app.runtime.context_store import EventLogStore


def test_event_log_records_state_affect_json(tmp_path, monkeypatch):
    monkeypatch.setenv("PETAGENT_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    state_store = create_state_store(settings, testing=True)
    store = EventLogStore(state_store.connection)

    store.record(
        event_id="evt-affect",
        episode_id="ep-affect",
        event_type="praise_momo",
        source="runtime",
        user_text="夸夸",
        pet_reply="嘿嘿。",
        state_before={"energy": 70},
        state_after={"energy": 71},
        mood_after="happy",
        state_affect={
            "interaction_tone": "affectionate",
            "pet_effort": "low",
            "emotional_effect": "encouraged",
            "reason": "用户夸了 Momo。",
        },
    )

    rows = store.recent_events("ep-affect", limit=1)
    assert rows[0]["state_affect"]["interaction_tone"] == "affectionate"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest tests/test_state_affect.py::test_event_log_records_state_affect_json -q
```

Expected: FAIL because `record()` does not accept `state_affect`.

- [ ] **Step 3: Migrate `raw_event_log` schema**

Modify `backend/app/runtime/context_store.py` `EventLogStore.initialize()` after table creation:

```python
self._ensure_state_affect_column()
```

Add method:

```python
def _ensure_state_affect_column(self) -> None:
    with self.connection.locked():
        rows = self.connection.execute("PRAGMA table_info(raw_event_log)").fetchall()
        columns = {row["name"] for row in rows}
        if "state_affect_json" not in columns:
            self.connection.execute("ALTER TABLE raw_event_log ADD COLUMN state_affect_json TEXT")
            self.connection.commit()
```

- [ ] **Step 4: Record and read `state_affect`**

Modify `EventLogStore.record()` signature:

```python
state_affect: Optional[Dict[str, Any]] = None,
```

Add `state_affect_json` to INSERT columns and values:

```python
state_affect_json
```

```python
json.dumps(state_affect, ensure_ascii=False) if state_affect else None
```

Modify `recent_events()` row mapping to include:

```python
"state_affect": json.loads(row["state_affect_json"]) if row["state_affect_json"] else None,
```

Modify `recent_events_for_episode()` or any second event reader in the same file with the same mapping.

- [ ] **Step 5: Pass `state_affect` from dispatcher**

Modify `backend/app/runtime/dispatcher.py` in `event_log_store.record()`:

```python
state_affect=action.state_affect.dict(),
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest tests/test_state_affect.py tests/test_stage35_event_log.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add backend/app/runtime/context_store.py backend/app/runtime/dispatcher.py backend/tests/test_state_affect.py backend/tests/test_stage35_event_log.py
git commit -m "feat: persist Momo state affect"
```

## Task 4: Add Text Pipeline And `/api/text/chat`

**Files:**

- Create: `backend/app/runtime/text_pipeline.py`
- Create: `backend/app/api/text.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/runtime/events.py`
- Test: `backend/tests/test_text_chat.py`
- Test: `backend/tests/test_api_contracts.py`

- [ ] **Step 1: Write failing text chat tests**

Create `backend/tests/test_text_chat.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_text_chat_uses_fast_route_by_default():
    client = TestClient(create_app(testing=True))

    response = client.post("/api/text/chat", json={"text": "我今天有点累"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_text"] == "我今天有点累"
    assert body["text_route"]["selected"] == "fast"
    assert body["text_route"]["thinking_mode"] is False
    assert body["text_route"]["brain_provider"] == "mock_fast_llm"
    assert body["voice_url"]
    assert body["runtime"]["event_id"]


def test_text_chat_uses_slow_route_when_thinking_mode_is_enabled():
    client = TestClient(create_app(testing=True))

    response = client.post(
        "/api/text/chat",
        json={"text": "帮我认真想想这个问题", "thinking_mode": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text_route"]["selected"] == "slow"
    assert body["text_route"]["thinking_mode"] is True
    assert body["text_route"]["brain_provider"] == "mock_slow_llm"


def test_text_chat_rejects_empty_text():
    client = TestClient(create_app(testing=True))

    response = client.post("/api/text/chat", json={"text": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "Text message is empty"


def test_text_chat_handles_wake_and_exit_phrases():
    client = TestClient(create_app(testing=True))

    wake = client.post("/api/text/chat", json={"text": "嗨 momo"})
    exit_response = client.post("/api/text/chat", json={"text": "momo休息吧"})

    assert wake.status_code == 200
    assert wake.json()["activation"]["type"] == "wake"
    assert wake.json()["activation"]["active"] is True
    assert exit_response.status_code == 200
    assert exit_response.json()["activation"]["type"] == "exit"
    assert exit_response.json()["activation"]["active"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest tests/test_text_chat.py -q
```

Expected: FAIL because `/api/text/chat` does not exist.

- [ ] **Step 3: Add text route types**

Create `backend/app/runtime/text_pipeline.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Dict, Optional

from app.pet.brain import PetBrain
from app.runtime.dispatcher import RuntimeDispatcher
from app.runtime.voice_pipeline import _classify_activation


def _now_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


@dataclass(frozen=True)
class TextRouteInfo:
    selected: str
    thinking_mode: bool
    brain_provider: str
    timings_ms: Dict[str, int] = field(default_factory=dict)

    def dict(self) -> Dict[str, Any]:
        return {
            "selected": self.selected,
            "thinking_mode": self.thinking_mode,
            "brain_provider": self.brain_provider,
            "timings_ms": dict(self.timings_ms),
        }


@dataclass(frozen=True)
class TextPipelineResult:
    user_text: str
    response: Any
    route_info: TextRouteInfo
    activation: Optional[Dict[str, Any]] = None


class TextPipeline:
    def __init__(
        self,
        *,
        dispatcher: RuntimeDispatcher,
        fast_brain: PetBrain,
        slow_brain: PetBrain,
        fast_brain_provider_name: str = "fast_llm",
        slow_brain_provider_name: str = "slow_llm",
        activation_manager: Any = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.fast_brain = fast_brain
        self.slow_brain = slow_brain
        self.fast_brain_provider_name = fast_brain_provider_name
        self.slow_brain_provider_name = slow_brain_provider_name
        self.activation_manager = activation_manager

    def handle(self, text: str, *, thinking_mode: bool = False) -> TextPipelineResult:
        user_text = text.strip()
        brain = self.slow_brain if thinking_mode else self.fast_brain
        selected = "slow" if thinking_mode else "fast"
        provider_name = (
            self.slow_brain_provider_name if thinking_mode else self.fast_brain_provider_name
        )
        started = perf_counter()
        activation_event = _classify_activation(user_text, self.activation_manager)
        activation_info = None
        if activation_event is not None:
            source = "text_slow" if thinking_mode else "text_fast"
            activation_event["source"] = source
            response = self.dispatcher.handle_event(activation_event, brain=brain)
            activation_info = self._build_activation_info(activation_event["type"])
        else:
            response = self.dispatcher.handle_event(
                {
                    "type": "text_message",
                    "source": "text_slow" if thinking_mode else "text_fast",
                    "payload": {"user_text": user_text},
                },
                brain=brain,
            )
        return TextPipelineResult(
            user_text=user_text,
            response=response,
            route_info=TextRouteInfo(
                selected=selected,
                thinking_mode=thinking_mode,
                brain_provider=provider_name,
                timings_ms={"total": _now_ms(started)},
            ),
            activation=activation_info,
        )

    def _build_activation_info(self, event_type: str) -> Dict[str, Any]:
        if self.activation_manager is None:
            return {"type": event_type, "active": False, "session_id": None}
        state = self.activation_manager.state
        return {
            "type": "wake" if event_type == "wake_phrase" else "exit",
            "active": state.active,
            "session_id": state.session_id,
        }
```

- [ ] **Step 4: Add API router**

Create `backend/app/api/text.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/text")


class TextChatRequest(BaseModel):
    text: str
    thinking_mode: bool = False


@router.post("/chat")
async def post_text_chat(payload: TextChatRequest, request: Request):
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text message is empty")
    started = datetime.utcnow()
    request.app.state.tick_service.apply_if_due()
    result = await run_in_threadpool(
        request.app.state.text_pipeline.handle,
        text,
        thinking_mode=payload.thinking_mode,
    )
    body: Dict[str, Any] = result.response.dict()
    body["user_text"] = result.user_text
    route_info = result.route_info.dict()
    route_info["timings_ms"].setdefault(
        "api_total",
        int((datetime.utcnow() - started).total_seconds() * 1000),
    )
    body["text_route"] = route_info
    if result.activation is not None:
        body["activation"] = result.activation
    return body
```

- [ ] **Step 5: Wire text pipeline in `main.py`**

Modify imports in `backend/app/main.py`:

```python
from app.api import text as text_api
from app.runtime.text_pipeline import TextPipeline
```

Instantiate after `voice_pipeline`:

```python
text_pipeline = TextPipeline(
    dispatcher=dispatcher,
    fast_brain=fast_brain,
    slow_brain=brain,
    fast_brain_provider_name=str(getattr(fast_llm_provider, "name", "fast_llm")),
    slow_brain_provider_name=str(getattr(slow_llm_provider, "name", "slow_llm")),
    activation_manager=activation_manager,
)
```

Set app state:

```python
app.state.text_pipeline = text_pipeline
```

Include router:

```python
app.include_router(text_api.router)
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest tests/test_text_chat.py tests/test_api_contracts.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add backend/app/runtime/text_pipeline.py backend/app/api/text.py backend/app/main.py backend/app/runtime/events.py backend/tests/test_text_chat.py backend/tests/test_api_contracts.py
git commit -m "feat: add Momo text chat pipeline"
```

## Task 5: Update Prompt For Text, Buttons, And State Affect

**Files:**

- Modify: `backend/app/pet/prompt_builder.py`
- Modify: `config/pet_persona.yaml`
- Test: `backend/tests/test_stage35_context.py`
- Test: `backend/tests/test_text_chat.py`

- [ ] **Step 1: Write failing prompt test**

Append to `backend/tests/test_text_chat.py`:

```python
from app.config import load_settings
from app.pet.prompt_builder import build_pet_messages
from app.runtime.context import build_runtime_context
from app.runtime.events import normalize_event


def test_text_prompt_mentions_state_affect_and_contextual_buttons():
    settings = load_settings()
    event = normalize_event(
        {
            "event": "praise_momo",
            "payload": {"description": "用户夸夸 Momo", "interaction_group": "pet_care"},
        }
    )
    context = build_runtime_context(
        event,
        {"name": "Momo", "mood": "happy", "energy": 70},
        cognition_context={"recent_exact_events": [{"user": "刚刚写了代码"}]},
    )

    messages = build_pet_messages(settings, event, context)
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert "state_affect" in user
    assert "按钮事件也必须结合最近上下文" in system
    assert "不要只根据按钮名机械回复" in system
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest tests/test_text_chat.py::test_text_prompt_mentions_state_affect_and_contextual_buttons -q
```

Expected: FAIL if prompt guidance or schema is missing.

- [ ] **Step 3: Add event-specific prompt guidance**

Modify `backend/app/pet/prompt_builder.py` after voice event rules:

```python
if event.type == "text_message":
    system_prompt += (
        "\n\n文字事件规则：\n"
        "1. 用户是在打字和你聊天，默认也要自然回应。\n"
        "2. 可以完成简单任务，但仍保持 Momo 的语气。\n"
        "3. 不要因为自己是宠物就故意说不会。\n"
    )
```

Add button event set near top:

```python
BUTTON_EVENTS = {
    "pet_head",
    "poke_face",
    "hug",
    "pet_pat",
    "praise_momo",
    "feed_momo",
    "stay_with_me",
    "comfort_me",
    "encourage_me",
    "listen_to_me",
    "tuck_in",
    "clean_face",
    "quiet_company",
    "take_a_break",
}
```

Append button guidance:

```python
if event.type in BUTTON_EVENTS:
    system_prompt += (
        "\n\n按钮互动规则：\n"
        "1. 按钮事件也必须结合最近上下文，不要只根据按钮名机械回复。\n"
        "2. 如果用户连续点同一按钮，要表现出自然变化。\n"
        "3. 投喂 feed_momo 是用户主动投喂，不等于手机充电。\n"
    )
```

- [ ] **Step 4: Update persona config**

Modify `config/pet_persona.yaml` rules section with one extra rule:

```yaml
  13. 当用户通过按钮、语音或文字互动时，你都要结合最近上下文、状态和记忆来回应。
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest tests/test_text_chat.py tests/test_stage35_context.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add backend/app/pet/prompt_builder.py config/pet_persona.yaml backend/tests/test_text_chat.py backend/tests/test_stage35_context.py
git commit -m "feat: guide Momo text and button prompts"
```

## Task 6: Frontend API And Text Input Component

**Files:**

- Modify: `frontend/src/pet/types.ts`
- Modify: `frontend/src/pet/api.ts`
- Create: `frontend/src/components/TextInputBar.tsx`
- Create: `frontend/src/components/TextInputBar.test.tsx`
- Modify: `frontend/src/pet/api.test.ts`

- [ ] **Step 1: Write failing API helper test**

Modify the existing import in `frontend/src/pet/api.test.ts` so it includes `sendTextChat`, then append the test block below:

```typescript
describe("sendTextChat", () => {
  test("sends text and thinking mode as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ reply: "好呀。" })
    });
    vi.stubGlobal("fetch", fetchMock);

    await sendTextChat("帮我写两数之和", { thinkingMode: true });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/text/chat");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({
      text: "帮我写两数之和",
      thinking_mode: true
    });
  });
});
```

- [ ] **Step 2: Write failing TextInputBar tests**

Create `frontend/src/components/TextInputBar.test.tsx`:

```typescript
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { TextInputBar } from "./TextInputBar";

describe("TextInputBar", () => {
  test("does not submit empty text", () => {
    const onSubmit = vi.fn();
    render(<TextInputBar disabled={false} onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  test("submits trimmed text and clears input on success", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<TextInputBar disabled={false} onSubmit={onSubmit} />);

    const input = screen.getByPlaceholderText("输入一句话……");
    fireEvent.change(input, { target: { value: "  我今天有点累  " } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(onSubmit).toHaveBeenCalledWith("我今天有点累");
  });

  test("enter submits text", () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<TextInputBar disabled={false} onSubmit={onSubmit} />);

    const input = screen.getByPlaceholderText("输入一句话……");
    fireEvent.change(input, { target: { value: "夸夸 Momo" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onSubmit).toHaveBeenCalledWith("夸夸 Momo");
  });
});
```

- [ ] **Step 3: Run frontend tests to verify they fail**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- TextInputBar api --run
```

Expected: FAIL because `sendTextChat` and `TextInputBar` do not exist.

- [ ] **Step 4: Add frontend types**

Modify `frontend/src/pet/types.ts`:

```typescript
export type StateAffect = {
  interaction_tone: string;
  pet_effort: string;
  emotional_effect: string;
  reason: string;
};
```

Add response-compatible field to `PetResponse`:

```typescript
state_affect?: StateAffect;
```

Extend `PetEventType`:

```typescript
  | "pet_pat"
  | "praise_momo"
  | "feed_momo"
  | "stay_with_me"
  | "comfort_me"
  | "encourage_me"
  | "listen_to_me"
  | "tuck_in"
  | "clean_face"
  | "quiet_company"
  | "take_a_break";
```

Add text types:

```typescript
export type TextChatResponse = PetResponse & {
  user_text: string;
  text_route: {
    selected: "fast" | "slow";
    thinking_mode: boolean;
    brain_provider: string;
    timings_ms: Record<string, number>;
  };
  activation?: {
    type: "wake" | "exit";
    active: boolean;
    session_id: string | null;
  };
};
```

- [ ] **Step 5: Add API helper**

Modify `frontend/src/pet/api.ts` imports:

```typescript
TextChatResponse,
```

Add:

```typescript
export type SendTextOptions = {
  thinkingMode?: boolean;
};

export function sendTextChat(
  text: string,
  options: SendTextOptions = {}
): Promise<TextChatResponse> {
  return requestJson<TextChatResponse>("/api/text/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      text,
      thinking_mode: options.thinkingMode === true
    })
  });
}
```

- [ ] **Step 6: Create TextInputBar component**

Create `frontend/src/components/TextInputBar.tsx`:

```tsx
import { SendHorizontal } from "lucide-react";
import { useState } from "react";

type TextInputBarProps = {
  disabled: boolean;
  onSubmit: (text: string) => Promise<void> | void;
};

export function TextInputBar({ disabled, onSubmit }: TextInputBarProps) {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const isDisabled = disabled || submitting;

  async function submit() {
    const text = value.trim();
    if (!text || isDisabled) return;
    setSubmitting(true);
    try {
      await onSubmit(text);
      setValue("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      className="text-input-bar"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <input
        aria-label="文字输入"
        disabled={isDisabled}
        placeholder="输入一句话……"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void submit();
          }
        }}
      />
      <button aria-label="发送" disabled={isDisabled || !value.trim()} type="submit">
        <SendHorizontal aria-hidden="true" />
        <span>发送</span>
      </button>
    </form>
  );
}
```

- [ ] **Step 7: Run focused frontend tests**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- TextInputBar api --run
```

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add frontend/src/pet/types.ts frontend/src/pet/api.ts frontend/src/pet/api.test.ts frontend/src/components/TextInputBar.tsx frontend/src/components/TextInputBar.test.tsx
git commit -m "feat: add Momo text input API"
```

## Task 7: Expand Interaction Buttons

**Files:**

- Modify: `frontend/src/components/TouchArea.tsx`
- Modify: `frontend/src/components/TouchArea.test.tsx`
- Modify: `frontend/src/pet/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing TouchArea tests**

Replace `frontend/src/components/TouchArea.test.tsx` with:

```typescript
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { TouchArea } from "./TouchArea";

describe("TouchArea", () => {
  test("emits primary interaction events", () => {
    const onPetEvent = vi.fn();
    render(<TouchArea disabled={false} onPetEvent={onPetEvent} />);

    fireEvent.click(screen.getByRole("button", { name: "摸摸头" }));
    fireEvent.click(screen.getByRole("button", { name: "抱一下" }));
    fireEvent.click(screen.getByRole("button", { name: "陪我一下" }));

    expect(onPetEvent).toHaveBeenCalledWith("pet_head");
    expect(onPetEvent).toHaveBeenCalledWith("hug");
    expect(onPetEvent).toHaveBeenCalledWith("stay_with_me");
  });

  test("emits more interaction events", () => {
    const onPetEvent = vi.fn();
    render(<TouchArea disabled={false} onPetEvent={onPetEvent} />);

    for (const name of ["拍拍", "夸夸", "投喂", "安慰我", "鼓励我", "听我吐槽", "哄睡", "擦擦脸", "安静待着", "休息会儿"]) {
      fireEvent.click(screen.getByRole("button", { name }));
    }

    expect(onPetEvent).toHaveBeenCalledWith("pet_pat");
    expect(onPetEvent).toHaveBeenCalledWith("praise_momo");
    expect(onPetEvent).toHaveBeenCalledWith("feed_momo");
    expect(onPetEvent).toHaveBeenCalledWith("comfort_me");
    expect(onPetEvent).toHaveBeenCalledWith("encourage_me");
    expect(onPetEvent).toHaveBeenCalledWith("listen_to_me");
    expect(onPetEvent).toHaveBeenCalledWith("tuck_in");
    expect(onPetEvent).toHaveBeenCalledWith("clean_face");
    expect(onPetEvent).toHaveBeenCalledWith("quiet_company");
    expect(onPetEvent).toHaveBeenCalledWith("take_a_break");
  });

  test("disables controls while busy", () => {
    render(<TouchArea disabled={true} onPetEvent={() => undefined} />);

    expect(screen.getByRole("button", { name: "投喂" })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- TouchArea --run
```

Expected: FAIL because the new buttons do not exist.

- [ ] **Step 3: Expand event descriptions**

Modify `frontend/src/pet/api.ts` `eventDescription()`:

```typescript
    case "pet_pat":
      return "用户轻轻拍拍你，像是在鼓励你";
    case "praise_momo":
      return "用户夸夸了 Momo";
    case "feed_momo":
      return "用户投喂了 Momo";
    case "stay_with_me":
      return "用户希望你陪自己一下";
    case "comfort_me":
      return "用户希望你安慰自己";
    case "encourage_me":
      return "用户希望你鼓励自己";
    case "listen_to_me":
      return "用户希望你听自己吐槽";
    case "tuck_in":
      return "用户想哄你休息";
    case "clean_face":
      return "用户帮你擦擦脸";
    case "quiet_company":
      return "用户希望你安静陪着";
    case "take_a_break":
      return "用户希望你休息会儿";
```

Modify `postPetEvent()` payload:

```typescript
body: JSON.stringify({
  event,
  payload: {
    description: eventDescription(event),
    interaction_group: interactionGroup(event)
  }
})
```

Add helper:

```typescript
function interactionGroup(event: PetEventType): string {
  if (["pet_head", "poke_face", "hug", "pet_pat", "praise_momo", "feed_momo", "tuck_in", "clean_face"].includes(event)) {
    return "pet_care";
  }
  if (["stay_with_me", "comfort_me", "encourage_me", "listen_to_me", "quiet_company", "take_a_break"].includes(event)) {
    return "emotional_companion";
  }
  return "debug";
}
```

- [ ] **Step 4: Expand TouchArea**

Modify `frontend/src/components/TouchArea.tsx`:

```tsx
import {
  Baby,
  Bed,
  Coffee,
  HandHeart,
  HeartHandshake,
  MessageCircleHeart,
  Moon,
  Sparkles,
  SmilePlus,
  Soup,
  Stars,
  VolumeX,
} from "lucide-react";
```

Use data arrays:

```tsx
const primaryActions = [
  { event: "pet_head", label: "摸摸头", icon: HandHeart, primary: true },
  { event: "hug", label: "抱一下", icon: HeartHandshake },
  { event: "stay_with_me", label: "陪我一下", icon: MessageCircleHeart },
] as const;

const moreActions = [
  { event: "pet_pat", label: "拍拍", icon: Baby },
  { event: "praise_momo", label: "夸夸", icon: Stars },
  { event: "feed_momo", label: "投喂", icon: Soup },
  { event: "comfort_me", label: "安慰我", icon: Sparkles },
  { event: "encourage_me", label: "鼓励我", icon: Coffee },
  { event: "listen_to_me", label: "听我吐槽", icon: SmilePlus },
  { event: "tuck_in", label: "哄睡", icon: Bed },
  { event: "clean_face", label: "擦擦脸", icon: Sparkles },
  { event: "quiet_company", label: "安静待着", icon: VolumeX },
  { event: "take_a_break", label: "休息会儿", icon: Moon },
] as const;
```

Render:

```tsx
return (
  <div className="touch-area">
    <div className="touch-primary">
      {primaryActions.map(({ event, label, icon: Icon, primary }) => (
        <button
          aria-label={label}
          className={`touch-button ${primary ? "primary" : ""}`}
          disabled={disabled}
          key={event}
          type="button"
          onClick={() => onPetEvent(event)}
        >
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </div>
    <div className="touch-more" aria-label="更多互动">
      {moreActions.map(({ event, label, icon: Icon }) => (
        <button
          aria-label={label}
          className="touch-button compact"
          disabled={disabled}
          key={event}
          type="button"
          onClick={() => onPetEvent(event)}
        >
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </div>
  </div>
);
```

- [ ] **Step 5: Update optimistic previews**

Modify `frontend/src/App.tsx` `optimistic`:

```typescript
  pet_pat: { mood: "happy", animation: "bounce", text: "嗯！Momo 收到拍拍。" },
  praise_momo: { mood: "shy", animation: "wiggle", text: "诶嘿，被夸到了…" },
  feed_momo: { mood: "happy", animation: "bounce", text: "开饭啦。" },
  stay_with_me: { mood: "concerned", animation: "tilt", text: "Momo 靠近一点。" },
  comfort_me: { mood: "concerned", animation: "tilt", text: "Momo 在听。" },
  encourage_me: { mood: "happy", animation: "jump", text: "给你打气！" },
  listen_to_me: { mood: "concerned", animation: "blink", text: "慢慢说，Momo 听着。" },
  tuck_in: { mood: "sleepy", animation: "slowBlink", text: "要睡觉觉了吗…" },
  clean_face: { mood: "shy", animation: "wiggle", text: "脸脸被擦干净啦。" },
  quiet_company: { mood: "idle", animation: "breathing", text: "Momo 安静陪你。" },
  take_a_break: { mood: "sleepy", animation: "slowBlink", text: "那就休息一小会儿。" },
```

- [ ] **Step 6: Add styles**

Modify `frontend/src/styles.css`:

```css
.touch-area {
  display: grid;
  gap: 8px;
}

.touch-primary,
.touch-more {
  display: grid;
  gap: 8px;
}

.touch-primary {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.touch-more {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.touch-button.compact {
  min-height: 46px;
  padding: 8px 6px;
  font-size: 0.9rem;
}

@media (max-width: 640px) {
  .touch-primary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .touch-more {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .touch-button.compact {
    min-height: 44px;
  }
}
```

- [ ] **Step 7: Run focused frontend tests**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- TouchArea --run
```

Expected: PASS.

- [ ] **Step 8: Commit Task 7**

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add frontend/src/components/TouchArea.tsx frontend/src/components/TouchArea.test.tsx frontend/src/pet/api.ts frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: expand Momo interaction buttons"
```

## Task 8: Integrate Text Chat In App

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`
- Test: `frontend/src/components/TextInputBar.test.tsx`

- [ ] **Step 1: Write failing App integration test**

Append the helper and test below to `frontend/src/App.test.tsx`. Reuse the existing imports at the top of that file; add only `describe` and `expect` to the existing `vitest` import if they are missing.

```typescript
function mockFetchForText() {
  return vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/pet/state") {
      return {
        ok: true,
        json: async () => ({
          schema_version: "0.1",
          name: "Momo",
          mood: "idle",
          energy: 72,
          intimacy: 40,
          hunger: 30,
          cleanliness: 85,
          loneliness: 35,
          sleepiness: 15,
          mode: "idle"
        })
      };
    }
    if (url === "/api/text/chat") {
      return {
        ok: true,
        json: async () => ({
          reply: "可以呀，我陪你写一个小小版本。",
          mood: "thinking",
          face_type: "thinking",
          animation: "blink",
          vibration: "none",
          voice_url: null,
          user_text: "帮我写两数之和",
          text_route: {
            selected: "fast",
            thinking_mode: false,
            brain_provider: "mock_fast_llm",
            timings_ms: {}
          },
          pet_state: {
            name: "Momo",
            mood: "thinking",
            energy: 70,
            intimacy: 41,
            hunger: 30,
            cleanliness: 85,
            loneliness: 32,
            sleepiness: 15
          },
          runtime: { event_id: "evt-text", skills_used: [] }
        })
      };
    }
    return { ok: true, json: async () => ({ active: false }) };
  }) as unknown as typeof fetch;
}

describe("App text input", () => {
  test("sends typed text and applies response", async () => {
    const fetchMock = mockFetchForText();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("输入一句话……"), {
      target: { value: "帮我写两数之和" }
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      expect(screen.getByText("可以呀，我陪你写一个小小版本。")).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/text/chat",
      expect.objectContaining({ method: "POST" })
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- App --run
```

Expected: FAIL because `TextInputBar` is not integrated.

- [ ] **Step 3: Import text API and component**

Modify `frontend/src/App.tsx` imports:

```typescript
import { TextInputBar } from "./components/TextInputBar";
```

Add API import:

```typescript
sendTextChat,
```

Add type import:

```typescript
TextChatResponse,
```

- [ ] **Step 4: Add text response handler**

Add in `App.tsx`:

```typescript
async function handleTextResponse(response: TextChatResponse) {
  if (response.activation) {
    setActiveSession(response.activation.active ? response.activation.session_id : null);
    applyPetResponse(response);
    return;
  }
  applyPetResponse(response);
}
```

Add submit handler:

```typescript
async function handleTextSubmit(text: string) {
  if (busy) return;
  setBusy(true);
  setPhase("thinking");
  setFaceType("thinking");
  setAnimation("blink");
  setBubbleText(thinkingMode ? "Momo 多想一下。" : "马上回应你。");
  try {
    const response = await sendTextChat(text, { thinkingMode });
    await handleTextResponse(response);
  } catch {
    setFaceType("concerned");
    setAnimation("tilt");
    setBubbleText("Momo 刚刚没接稳，你那句话还可以再发一次。");
    throw new Error("text_chat_failed");
  } finally {
    setBusy(false);
  }
}
```

Use `throw new Error("text_chat_failed")` so `TextInputBar` keeps the text on failed submission.

- [ ] **Step 5: Render TextInputBar**

Place `TextInputBar` above `VoiceModeToggle` in the control deck:

```tsx
<TextInputBar disabled={busy} onSubmit={handleTextSubmit} />
```

- [ ] **Step 6: Add styles**

Modify `frontend/src/styles.css`:

```css
.text-input-bar {
  min-height: 54px;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}

.text-input-bar input {
  min-width: 0;
  border: 1px solid rgba(23, 32, 51, 0.12);
  border-radius: 8px;
  padding: 0 14px;
  background: rgba(255, 255, 255, 0.9);
  color: #172033;
  font: inherit;
}

.text-input-bar button {
  min-width: 92px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid rgba(67, 179, 174, 0.32);
  border-radius: 8px;
  background: #ffffff;
  color: #172033;
  cursor: pointer;
}

.text-input-bar button svg {
  width: 18px;
  height: 18px;
}

.text-input-bar button:disabled,
.text-input-bar input:disabled {
  cursor: wait;
  opacity: 0.62;
}
```

- [ ] **Step 7: Run focused frontend tests**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- App TextInputBar --run
```

Expected: PASS.

- [ ] **Step 8: Commit Task 8**

```bash
cd /Users/wylam/Documents/workspace/Petagent
git add frontend/src/App.tsx frontend/src/styles.css frontend/src/App.test.tsx frontend/src/components/TextInputBar.test.tsx
git commit -m "feat: integrate Momo text chat UI"
```

## Task 9: Runtime Regression, Build, And Phone Deployment

**Files:**

- Modify only files required by fixes discovered during verification.

- [ ] **Step 1: Run backend full test suite**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- --run
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Build frontend**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm run build
```

Expected: Vite build succeeds and updates `frontend/dist`.

- [ ] **Step 4: Check for formatting and secret leaks**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git diff --check
git diff --cached --name-only | xargs rg -n "(tp-[A-Za-z0-9_-]{20,}|nvapi-[A-Za-z0-9_-]{20,}|github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{20,}|MIMO_API_KEY=.+|ASR_API_KEY=.+|NVIDIA_API_KEY=.+)" -- 2>/dev/null || true
```

Expected: `git diff --check` exits 0 and secret scan prints no real secrets.

- [ ] **Step 5: Commit verification fixes**

If verification required fixes, commit them:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git status --short
git add -u
git commit -m "fix: stabilize Momo text and interaction runtime"
```

If there are no verification fixes, skip this step and record that no commit was needed.

- [ ] **Step 6: Deploy to Nubia**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
COPYFILE_DISABLE=1 tar \
  --exclude='./.git' \
  --exclude='./.env' \
  --exclude='./backend/.venv' \
  --exclude='./backend/data' \
  --exclude='./backend/static/audio' \
  --exclude='./frontend/node_modules' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  -czf - . | ssh -o BatchMode=yes nubia 'mkdir -p ~/Petagent && cd ~/Petagent && tar -xzf -'
```

Expected: files sync to `~/Petagent`. macOS tar extended header warnings may appear and do not fail the deploy.

- [ ] **Step 7: Restart Nubia runtime safely**

Run:

```bash
ssh -o BatchMode=yes nubia 'set -eu
if [ -f ~/Petagent/backend/data/runtime.pid ]; then kill $(cat ~/Petagent/backend/data/runtime.pid) 2>/dev/null || true; fi
pids=$(ps aux | awk '\''/python -m uvicorn app.main:app/ && !/awk/ {print $2}'\'')
if [ -n "$pids" ]; then kill $pids 2>/dev/null || true; fi
sleep 2
rm -f ~/Petagent/backend/data/runtime.pid
cd ~/Petagent && sh scripts/start.sh'
```

Expected: output includes `PetAgent runtime ready on 0.0.0.0:8000`.

- [ ] **Step 8: Smoke test Nubia APIs**

Run:

```bash
ssh -o BatchMode=yes nubia 'curl -s http://127.0.0.1:8000/api/health; echo'
curl -s http://172.20.10.2:8000/api/health
```

Expected:

```json
{"ok":true,"name":"Momo"}
```

- [ ] **Step 9: Real phone E2E**

Open:

```text
http://172.20.10.2:8000/
```

Perform these checks:

```text
1. Type “帮我写两数之和”.
   Expected: Momo gives a useful short solution, not “不会写”.

2. Type “我有点累”.
   Expected: Momo replies warmly and plays TTS.

3. Click 投喂.
   Expected: Momo references current context and hunger does not drop below 0.

4. Click 夸夸.
   Expected: intimacy rises slightly or mood becomes happy/shy.

5. Enable 思考模式, type a harder prompt.
   Expected: response text_route.selected is slow in backend response.
```

Use browser devtools and `raw_event_log` with this command:

```bash
ssh -o BatchMode=yes nubia 'cd ~/Petagent && python - <<'"'"'PY'"'"'
import sqlite3
conn = sqlite3.connect("backend/data/pet.db")
conn.row_factory = sqlite3.Row
for row in conn.execute("SELECT event_type,user_text,pet_reply,state_affect_json FROM raw_event_log ORDER BY created_at_utc DESC LIMIT 5"):
    print(dict(row))
PY'
```

Expected: recent rows include `text_message`, button event names, and non-empty `state_affect_json`.

- [ ] **Step 10: Final milestone commit and push**

Run:

```bash
cd /Users/wylam/Documents/workspace/Petagent
git status --short
git push origin main
```

Expected: `main -> main` push succeeds. If GitHub returns an HTTP2 framing error, retry:

```bash
git -c http.version=HTTP/1.1 push origin main
```

## Final Verification Checklist

- [ ] Backend full test suite passes.
- [ ] Frontend test suite passes.
- [ ] Frontend build succeeds.
- [ ] `/api/text/chat` works in fast and slow modes.
- [ ] `state_affect` appears in API responses and raw event log.
- [ ] All expanded buttons send supported event names.
- [ ] Text input defaults to TTS playback through normal `PetResponse.voice_url`.
- [ ] Buttons, text, and voice all go through `RuntimeDispatcher`.
- [ ] Nubia runtime starts and health endpoint responds.
- [ ] GitHub `origin/main` contains the final commits.
