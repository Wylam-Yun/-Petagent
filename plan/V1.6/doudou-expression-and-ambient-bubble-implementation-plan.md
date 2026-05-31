# Doudou Expression And Ambient Bubble Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` or equivalent task-by-task execution. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 实现 V1.6 豆豆颜表情契约和 LLM 生成空闲气泡，让对话表情由语境驱动，空闲小剧场低频、可观测、不可规则生成台词。

**Architecture:** 对话链路在现有 V1.5 unified foreground path 上扩展 `expression_key`，保持 `reply` 是唯一 TTS 文本。空闲气泡拆成前端本地 idle controller 和后端 ambient bubble service：前端负责页面可见、输入/录音/TTS 播放、TTS 结束后的退避计时；后端负责每日计数、activity 去重、LLM 生成、输出校验和 debug 状态。Ambient API 使用两阶段协议：`trigger` 只生成 pending 事件，前端真正展示后调用 `confirm`，只有 confirm 成功才计入每日次数和 backoff。

**Tech Stack:** FastAPI, SQLite-backed runtime stores, Pydantic models, React/Vite, Vitest, pytest, Nubia Android Termux deployment.

---

## File Structure

### Backend

- Create `backend/app/runtime/expressions.py`
  - Single source for `expression_key` whitelist, kaomoji map, mood fallback, ambient activity recommendations and activity classes.
- Create `backend/app/runtime/ambient_bubble.py`
  - Ambient request/response models, SQLite pending/log store, activity selector, output guard, debug snapshot builder.
- Modify `backend/app/runtime/actions.py`
  - Add `expression_key` to `FastReplyAction` and `PetResponse`.
- Modify `backend/app/pet/guard.py`
  - Validate `mood`, `expression_key`, `action`, `voice_style`, and first-person text rules for foreground and ambient outputs.
- Modify `backend/app/pet/prompt_builder.py`
  - Add expression schema to unified foreground prompt.
  - Add ambient bubble prompt builder.
- Modify `backend/app/pet/brain.py`
  - Add `generate_ambient_bubble()`.
- Modify `backend/app/runtime/dispatcher.py`
  - Include `expression_key` in foreground responses.
  - Record actual submitted TTS text for debug.
- Modify `backend/app/api/pet.py`
  - Add `/api/pet/ambient/check`, `/api/pet/ambient/trigger`, `/api/pet/ambient/confirm`, and `/api/pet/ambient/cancel`.
  - Keep legacy `/api/pet/proactive` endpoints for debugging compatibility, but remove all user-facing frontend polling after migration.
- Modify `backend/app/api/debug.py`
  - Add token-protected `/api/debug/idle-state`.
- Modify `backend/app/main.py`
  - Instantiate and expose `ambient_bubble_service` or equivalent state.
- Test files:
  - Create `backend/tests/test_v16_expression_contract.py`
  - Create `backend/tests/test_v16_ambient_policy.py`
  - Create `backend/tests/test_v16_ambient_api.py`
  - Create `backend/tests/test_v16_idle_debug.py`
  - Update existing V1.5/fast-reply tests that assert old schema.

### Frontend

- Create `frontend/src/pet/ambient.ts`
  - Local idle controller: eligibility, backoff timing, localStorage persistence, request payload building.
- Modify `frontend/src/pet/faces.ts`
  - Add `expressionMap`, `expressionForKey()`, and mood fallback.
- Modify `frontend/src/pet/types.ts`
  - Add `ExpressionKey`, `expression_key` fields, ambient response types, debug fields.
- Modify `frontend/src/pet/api.ts`
  - Add `getAmbientCheck()`, `triggerAmbientBubble()`, `confirmAmbientBubble()`, and `cancelAmbientBubble()`.
- Modify `frontend/src/App.tsx`
  - Use `expression_key` for face display.
  - Replace current proactive polling with ambient idle polling.
  - Track user input, recording, waiting, TTS playback and post-TTS idle anchor.
  - Apply ambient/dialogue `action` to the visible Doudou sprite/action state.
- Modify `frontend/src/components/TextInputBar.tsx`
  - Expose `onActiveChange` from focus, blur, value changes and IME composition.
- Use existing `frontend/src/components/DoudouSprite.tsx`
  - Render action-based sprite state; do not call rule-generated `BehaviorDirector.onAmbientTick()` for V1.6 ambient bubbles.
- Modify `frontend/src/components/PetFace.tsx`
  - Accept expression key or rendered expression.
- Test files:
  - Update `frontend/src/pet/faces.test.ts`
  - Create `frontend/src/pet/ambient.test.ts`
  - Update `frontend/src/pet/api.test.ts`
  - Update `frontend/src/App.test.tsx`

---

## Task 1: Add Shared Expression Catalog

**Files:**
- Create: `backend/app/runtime/expressions.py`
- Test: `backend/tests/test_v16_expression_contract.py`
- Modify later: `frontend/src/pet/faces.ts`

- [x] **Step 1: Write backend catalog tests**

Add tests:

```python
from app.runtime.expressions import (
    EXPRESSION_MAP,
    EXPRESSION_KEYS,
    expression_for_mood,
    activity_recommendation,
)


def test_expression_catalog_contains_v16_keys():
    assert "idle_soft" in EXPRESSION_KEYS
    assert "playful" in EXPRESSION_KEYS
    assert "wronged" in EXPRESSION_KEYS
    assert EXPRESSION_MAP["idle_soft"] == "(・ω・)"


def test_expression_for_mood_fallbacks():
    assert expression_for_mood("happy") == "happy"
    assert expression_for_mood("angry") == "annoyed"
    assert expression_for_mood("bad-mood") == "idle_soft"
    assert expression_for_mood(None) == "idle_soft"


def test_activity_recommendations_have_valid_expression_and_action():
    rec = activity_recommendation("sneak_snack")
    assert rec.activity == "sneak_snack"
    assert "playful" in rec.expression_keys
    assert "sneak_eat" in rec.actions
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_v16_expression_contract.py -q
```

Expected: import failure because `app.runtime.expressions` does not exist.

- [x] **Step 3: Implement catalog**

Create `backend/app/runtime/expressions.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set


EXPRESSION_MAP: Dict[str, str] = {
    "idle_soft": "(・ω・)",
    "idle_wink": "(｡•̀ᴗ-)✧",
    "happy": "(^▽^)",
    "happy_big": "(≧▽≦)",
    "excited": "٩(ˊᗜˋ*)و",
    "shy": "(//▽//)",
    "clingy": "(*ﾉωﾉ)",
    "thinking": "(・・?)",
    "confused": "(。ヘ°)",
    "concerned": "(´・ω・)",
    "sad": "(｡•́︿•̀｡)",
    "crying": "(╥﹏╥)",
    "sleepy": "(-_-) zzz",
    "tired": "(￣o￣)",
    "annoyed": "(｀へ´)",
    "wronged": "(｡•́︿•̀｡)",
    "proud": "(๑•̀ㅂ•́)و✧",
    "playful": "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧",
    "lonely": "(._.)",
    "calm": "( ˘ω˘ )",
}

EXPRESSION_KEYS: Set[str] = set(EXPRESSION_MAP)

MOOD_EXPRESSION_FALLBACK: Dict[str, str] = {
    "idle": "idle_soft",
    "happy": "happy",
    "sad": "sad",
    "sleepy": "sleepy",
    "angry": "annoyed",
    "shy": "shy",
    "thinking": "thinking",
    "concerned": "concerned",
    "excited": "excited",
    "lonely": "lonely",
}


@dataclass(frozen=True)
class ActivityRecommendation:
    activity: str
    activity_class: str
    expression_keys: List[str]
    actions: List[str]
    strong_once_daily: bool = False


ACTIVITY_RECOMMENDATIONS: Dict[str, ActivityRecommendation] = {
    "stay_near": ActivityRecommendation("stay_near", "near", ["idle_soft", "calm", "clingy"], ["idle", "greet"]),
    "pretend_busy": ActivityRecommendation("pretend_busy", "mischief", ["idle_wink", "proud", "playful"], ["pretend_busy", "remember"], True),
    "patrol": ActivityRecommendation("patrol", "active", ["proud", "idle_wink", "happy"], ["wander", "running"]),
    "self_groom": ActivityRecommendation("self_groom", "care", ["calm", "happy", "shy"], ["self_groom"]),
    "sneak_snack": ActivityRecommendation("sneak_snack", "mischief", ["playful", "shy", "wronged"], ["sneak_eat"], True),
    "lazy_save_power": ActivityRecommendation("lazy_save_power", "lazy", ["tired", "sleepy", "idle_wink"], ["lazy_idle", "nap"]),
    "peek_user": ActivityRecommendation("peek_user", "near", ["clingy", "idle_wink", "lonely"], ["listen", "greet"]),
    "claim_corner": ActivityRecommendation("claim_corner", "mischief", ["playful", "proud", "annoyed"], ["tease", "happy"], True),
    "watch_tiny_show": ActivityRecommendation("watch_tiny_show", "mischief", ["playful", "thinking", "idle_wink"], ["watch_tv", "pretend_busy"], True),
    "quiet_guard": ActivityRecommendation("quiet_guard", "quiet", ["calm", "idle_soft", "concerned"], ["idle", "listen"]),
    "sleepy_curl": ActivityRecommendation("sleepy_curl", "sleepy", ["sleepy", "tired", "calm"], ["nap", "lazy_idle"]),
}


def expression_for_mood(mood: Optional[str]) -> str:
    return MOOD_EXPRESSION_FALLBACK.get(str(mood or ""), "idle_soft")


def normalize_expression_key(value: object, mood: object = None) -> str:
    if isinstance(value, str) and value in EXPRESSION_KEYS:
        return value
    return expression_for_mood(str(mood) if isinstance(mood, str) else None)


def activity_recommendation(activity: str) -> ActivityRecommendation:
    return ACTIVITY_RECOMMENDATIONS[activity]
```

- [x] **Step 4: Run catalog tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_v16_expression_contract.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/runtime/expressions.py backend/tests/test_v16_expression_contract.py
git commit -m "feat: add doudou expression catalog"
```

---

## Task 2: Extend Foreground Reply Contract

**Files:**
- Modify: `backend/app/runtime/actions.py`
- Modify: `backend/app/pet/guard.py`
- Modify: `backend/app/pet/prompt_builder.py`
- Modify: `backend/app/pet/brain.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Tests: `backend/tests/test_v16_expression_contract.py`, `backend/tests/test_fast_reply_contract.py`

- [x] **Step 1: Add failing guard tests**

Append tests:

```python
from app.pet.guard import guard_fast_reply_action


def test_fast_reply_accepts_expression_key():
    action = guard_fast_reply_action({
        "reply": "我来看看。",
        "mood": "thinking",
        "expression_key": "thinking",
        "action": "think",
        "voice_style": "soft",
    })
    assert action.expression_key == "thinking"
    assert action.mood == "thinking"


def test_fast_reply_invalid_expression_falls_back_to_mood():
    action = guard_fast_reply_action({
        "reply": "我在。",
        "mood": "angry",
        "expression_key": "not-real",
    })
    assert action.expression_key == "annoyed"
    assert action.mood == "angry"


def test_fast_reply_invalid_expression_and_mood_defaults_idle_soft():
    action = guard_fast_reply_action({
        "reply": "我在。",
        "mood": "furious",
        "expression_key": "not-real",
    })
    assert action.mood == "idle"
    assert action.expression_key == "idle_soft"


def test_fast_reply_sanitizes_self_name_to_first_person():
    action = guard_fast_reply_action({
        "reply": "豆豆来看看。",
        "mood": "happy",
        "expression_key": "happy",
    })
    assert "豆豆" not in action.reply
    assert action.reply == "我来看看。"


def test_fast_reply_rejects_kaomoji_in_tts_reply():
    try:
        guard_fast_reply_action({
            "reply": "我来啦(^▽^)",
            "mood": "happy",
            "expression_key": "happy",
        })
    except Exception as exc:
        assert getattr(exc, "error_class", "") == "llm_invalid_output"
    else:
        raise AssertionError("kaomoji in reply must not reach TTS text")
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_v16_expression_contract.py tests/test_fast_reply_contract.py -q
```

Expected: failures because `FastReplyAction.expression_key` does not exist.

- [x] **Step 3: Update models**

In `backend/app/runtime/actions.py`:

```python
class FastReplyAction(BaseModel):
    reply: str
    mood: Optional[str] = None
    expression_key: str = "idle_soft"
    action: Optional[str] = None
    voice_style: str = "soft"


class PetResponse(BaseModel):
    schema_version: str = "0.1"
    reply: str
    mood: str
    face_type: str
    expression_key: str = "idle_soft"
    animation: str
    vibration: str
    pet_state: Dict[str, Any]
    runtime: Dict[str, Any]
    voice_url: Optional[str] = None
    audio_job_id: Optional[str] = None
    state_affect: Optional[Dict[str, Any]] = None
    behavior_intent: Optional[str] = None
    behavior_plan: Optional[list] = None
    action: Optional[str] = None
    route: Optional[str] = None
    memory_ack_hint: Optional[str] = None
```

- [x] **Step 4: Update fast reply guard**

In `backend/app/pet/guard.py`, import `normalize_expression_key` and update `guard_fast_reply_action()`:

```python
from app.runtime.expressions import normalize_expression_key

KAOMOJI_MARKERS = ("(^", "(｡", "(・", "(//", "٩(", "(╥", "(-_", "(￣", "(｀", "(๑", "(ﾉ", "(._", "( ˘")


def _sanitize_first_person(reply: str) -> str:
    return str(reply or "").replace("豆豆", "我")


def _contains_kaomoji(reply: str) -> bool:
    return any(marker in reply for marker in KAOMOJI_MARKERS)
```

Then after mood validation and before return:

```python
mood = data.get("mood")
if mood not in ALLOWED_MOODS:
    mood = "idle"

expression_key = normalize_expression_key(data.get("expression_key"), mood)

reply = _strip_reasoning(str(data.get("reply", "")).strip())
reply = _sanitize_prompt_leak(reply)
reply = _sanitize_pet_name(reply)
reply = _sanitize_first_person(reply)
if not reply:
    raise InvalidActionError("llm_invalid_output", "LLM reply is empty after sanitization")
if _contains_kaomoji(reply):
    raise InvalidActionError("llm_invalid_output", "LLM reply contains kaomoji")
reply = _trim_reply(reply, max_reply_chars)

return FastReplyAction(
    reply=reply,
    mood=mood,
    expression_key=expression_key,
    action=action,
    voice_style=voice_style,
)
```

- [x] **Step 5: Update unified prompt schema**

In `backend/app/pet/prompt_builder.py`, add expression list to `FAST_REPLY_SCHEMA`:

```python
from app.runtime.expressions import EXPRESSION_KEYS, ACTIVITY_RECOMMENDATIONS

FAST_REPLY_SCHEMA = {
    "reply": "自然简短的回复，不超过 80 字；必须使用第一人称“我”；不要输出颜表情；不要自称豆豆",
    "mood": "idle/happy/sad/sleepy/angry/shy/thinking/concerned/excited/lonely",
    "expression_key": "/".join(sorted(EXPRESSION_KEYS)),
    "action": BEHAVIOR_ACTION_SCHEMA,
    "voice_style": "soft/normal/happy/sleepy/shy",
}
```

Also add a short system prompt block:

```python
system_prompt += (
    "\n\nV1.6 表情规则："
    "\n1. 根据当前用户语境选择 expression_key。"
    "\n2. reply 里不要输出颜表情，颜表情只能通过 expression_key 表示。"
    "\n3. 台词主语必须用“我”，不要自称“豆豆”。"
)
```

- [x] **Step 6: Include expression in dispatcher responses**

In `backend/app/runtime/dispatcher.py`, add `expression_key` to `run.final_action` and `PetResponse` creation:

```python
run.final_action = {
    "reply": fast_action.reply[:200],
    "mood": fast_action.mood or "idle",
    "expression_key": fast_action.expression_key,
    "action": fast_action.action or "",
    "voice_style": fast_action.voice_style,
}
```

And in fast response:

```python
expression_key=fast_action.expression_key,
```

For non-fast `PetAction`, use:

```python
expression_key=normalize_expression_key(getattr(action, "expression_key", None), action.mood),
```

If the non-fast path is now unreachable for foreground, keep this as compatibility only.

- [x] **Step 7: Record submitted TTS text for debug**

In `RuntimeDispatcher.__init__`:

```python
self.last_submitted_tts_text = ""
self.last_submitted_tts_event_id = ""
self.last_submitted_tts_at = ""
```

Before enqueueing TTS:

```python
self.last_submitted_tts_text = tts_text
self.last_submitted_tts_event_id = event.id
self.last_submitted_tts_at = datetime.utcnow().isoformat()
```

This value must always be the final sanitized `reply`, never `expression_key`, kaomoji text, or raw LLM JSON. Tests should assert `last_submitted_tts_text == response["reply"]` and `last_submitted_tts_event_id` matches the current event, so stale debug values cannot mask a regression.

- [x] **Step 8: Run backend contract tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_v16_expression_contract.py tests/test_fast_reply_contract.py tests/test_text_chat.py tests/test_voice_pipeline.py -q
```

Expected: PASS.

- [x] **Step 9: Commit**

```bash
git add backend/app/runtime/actions.py backend/app/pet/guard.py backend/app/pet/prompt_builder.py backend/app/runtime/dispatcher.py backend/tests/test_v16_expression_contract.py backend/tests/test_fast_reply_contract.py
git commit -m "feat: add expression key to foreground replies"
```

---

## Task 3: Add Backend Ambient Bubble Service

**Files:**
- Create: `backend/app/runtime/ambient_bubble.py`
- Modify: `backend/app/pet/prompt_builder.py`
- Modify: `backend/app/pet/brain.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_v16_ambient_policy.py`

- [x] **Step 1: Write policy and guard tests**

Create `backend/tests/test_v16_ambient_policy.py`:

```python
from datetime import datetime, timedelta

from app.pet.state import PetStateStore
from app.runtime.ambient_bubble import AmbientBubbleService, guard_ambient_bubble_output


def make_service(tmp_path):
    state_store = PetStateStore(tmp_path / "state.db")
    return AmbientBubbleService(state_store.connection)


def test_guard_accepts_valid_llm_output():
    result = guard_ambient_bubble_output({
        "bubble": "我刚刚没有偷懒。",
        "expression_key": "idle_wink",
        "action": "lazy_idle",
    })
    assert result.bubble == "我刚刚没有偷懒。"
    assert result.expression_key == "idle_wink"
    assert result.action == "lazy_idle"


def test_guard_rejects_empty_or_not_first_person():
    assert guard_ambient_bubble_output({"bubble": ""}) is None
    assert guard_ambient_bubble_output({"bubble": "刚刚没有偷懒。"}) is None
    assert guard_ambient_bubble_output({"bubble": "豆豆没有偷懒。"}) is None


def test_guard_rejects_too_long_without_truncating():
    result = guard_ambient_bubble_output({"bubble": "我" + "很" * 30})
    assert result is None


def test_daily_limit_and_activity_limits(tmp_path):
    svc = make_service(tmp_path)
    day = "2026-05-31"
    for i in range(10):
        event_id = f"evt-{i}"
        assert svc.create_pending(
            local_date=day,
            event_id=event_id,
            activity="quiet_guard",
            activity_class="quiet",
            bubble="我在安静看家。",
            expression_key="calm",
            action="idle",
        ) is True
        assert svc.confirm_pending(event_id) is True
    assert svc.can_emit(day)["eligible"] is False
    assert svc.can_emit(day)["block_reason"] == "daily_limit"


def test_pending_does_not_advance_counters_until_confirmed(tmp_path):
    svc = make_service(tmp_path)
    day = "2026-05-31"
    before = svc.debug_state(day)
    assert svc.create_pending(
        local_date=day,
        event_id="evt-pending",
        activity="sneak_snack",
        activity_class="mischief",
        bubble="我没有偷吃。",
        expression_key="playful",
        action="sneak_eat",
    ) is True
    middle = svc.debug_state(day)
    assert middle["daily_count"] == before["daily_count"]
    assert middle["backoff_step"] == before["backoff_step"]
    assert middle["pending_count"] == 1
    assert svc.confirm_pending("evt-pending") is True
    after = svc.debug_state(day)
    assert after["daily_count"] == before["daily_count"] + 1
    assert after["backoff_step"] == before["backoff_step"] + 1
    assert after["last_rendered_expression_key"] == "playful"


def test_failure_and_cancel_do_not_advance_counters(tmp_path):
    svc = make_service(tmp_path)
    day = "2026-05-31"
    before = svc.debug_state(day)
    svc.record_failure("validation_failed")
    after = svc.debug_state(day)
    assert after["daily_count"] == before["daily_count"]
    assert after["backoff_step"] == before["backoff_step"]
    svc.create_pending(
        local_date=day,
        event_id="evt-cancelled",
        activity="lazy_save_power",
        activity_class="lazy",
        bubble="我在省电。",
        expression_key="tired",
        action="lazy_idle",
    )
    assert svc.cancel_pending("evt-cancelled") is True
    cancelled = svc.debug_state(day)
    assert cancelled["daily_count"] == before["daily_count"]
    assert cancelled["backoff_step"] == before["backoff_step"]
```

- [x] **Step 2: Run tests and verify failure**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_v16_ambient_policy.py -q
```

Expected: import failure because ambient service does not exist.

- [x] **Step 3: Implement ambient models, guard, store**

Create `backend/app/runtime/ambient_bubble.py` with these public surfaces:

```python
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.runtime.actions import ALLOWED_BEHAVIOR_ACTIONS
from app.runtime.expressions import ACTIVITY_RECOMMENDATIONS, EXPRESSION_KEYS, normalize_expression_key

MAX_BUBBLE_CHARS = 20
DAILY_LIMIT = 10
DEFAULT_BACKOFF_MS = [5 * 60_000, 10 * 60_000, 20 * 60_000, 40 * 60_000, 90 * 60_000]


@dataclass(frozen=True)
class AmbientBubbleAction:
    bubble: str
    expression_key: str
    action: str
    source: str = "llm_generated"


def guard_ambient_bubble_output(raw: Any) -> Optional[AmbientBubbleAction]:
    if not isinstance(raw, dict):
        return None
    bubble = str(raw.get("bubble") or "").strip()
    if not bubble or len(bubble) > MAX_BUBBLE_CHARS:
        return None
    if "豆豆" in bubble:
        return None
    if "我" not in bubble:
        return None
    expression_key = normalize_expression_key(raw.get("expression_key"), "idle")
    action = str(raw.get("action") or "idle")
    if action not in ALLOWED_BEHAVIOR_ACTIONS:
        action = "idle"
    return AmbientBubbleAction(bubble=bubble, expression_key=expression_key, action=action)


class AmbientBubbleService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.last_validation_failure_reason = ""
        self._generation_lock = threading.Lock()
        self._generation_inflight = False
        self.initialize()

    def initialize(self) -> None:
        with self.connection.locked():
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ambient_bubble_pending (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_date TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    suggested_activity TEXT NOT NULL,
                    activity_class TEXT NOT NULL,
                    bubble TEXT NOT NULL,
                    expression_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ambient_bubble_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_date TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    suggested_activity TEXT NOT NULL,
                    activity_class TEXT NOT NULL,
                    bubble TEXT NOT NULL,
                    expression_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self.connection.commit()

    def expire_pending(self) -> int:
        now = datetime.utcnow().isoformat()
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                UPDATE ambient_bubble_pending
                SET status = 'expired'
                WHERE status = 'pending' AND expires_at < ?
                """,
                (now,),
            )
            self.connection.commit()
        return cursor.rowcount

    def can_emit(self, local_date: str) -> Dict[str, Any]:
        self.expire_pending()
        state = self.debug_state(local_date)
        if state["daily_count"] >= DAILY_LIMIT:
            return {"eligible": False, "block_reason": "daily_limit"}
        if state["pending_count"] > 0:
            return {"eligible": False, "block_reason": "pending_exists"}
        return {"eligible": True, "block_reason": ""}

    def begin_generation(self, local_date: str) -> Dict[str, Any]:
        with self._generation_lock:
            if self._generation_inflight:
                return {"eligible": False, "block_reason": "ambient_inflight"}
            allowed = self.can_emit(local_date)
            if not allowed["eligible"]:
                return allowed
            self._generation_inflight = True
            return {"eligible": True, "block_reason": ""}

    def end_generation(self) -> None:
        with self._generation_lock:
            self._generation_inflight = False

    def select_activity(self, local_date: str) -> Optional[str]:
        state = self.debug_state(local_date)
        last_class = state.get("last_activity_class") or ""
        for name, rec in ACTIVITY_RECOMMENDATIONS.items():
            if rec.activity_class == last_class:
                continue
            count = state["activity_counts"].get(name, 0)
            limit = 1 if rec.strong_once_daily else 2
            if count < limit:
                return name
        self.last_validation_failure_reason = "no_available_activity"
        return None

    def create_pending(
        self,
        *,
        local_date: str,
        event_id: str,
        activity: str,
        activity_class: str,
        bubble: str,
        expression_key: str,
        action: str,
    ) -> bool:
        if not self.can_emit(local_date)["eligible"]:
            return False
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=2)
        with self.connection.locked():
            self.connection.execute(
                """
                INSERT INTO ambient_bubble_pending
                    (local_date, event_id, suggested_activity, activity_class, bubble,
                     expression_key, action, source, status, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    local_date,
                    event_id,
                    activity,
                    activity_class,
                    bubble,
                    expression_key,
                    action,
                    "llm_generated",
                    expires_at.isoformat(),
                    now.isoformat(),
                ),
            )
            self.connection.commit()
        return True

    def confirm_pending(self, event_id: str) -> bool:
        self.expire_pending()
        with self.connection.locked():
            row = self.connection.execute(
                """
                SELECT local_date, event_id, suggested_activity, activity_class,
                       bubble, expression_key, action, source
                FROM ambient_bubble_pending
                WHERE event_id = ? AND status = 'pending'
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                return False
            if self.debug_state(row["local_date"])["daily_count"] >= DAILY_LIMIT:
                return False
            self.connection.execute(
                """
                INSERT INTO ambient_bubble_log
                    (local_date, event_id, suggested_activity, activity_class,
                     bubble, expression_key, action, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["local_date"],
                    row["event_id"],
                    row["suggested_activity"],
                    row["activity_class"],
                    row["bubble"],
                    row["expression_key"],
                    row["action"],
                    row["source"],
                    datetime.utcnow().isoformat(),
                ),
            )
            self.connection.execute(
                "UPDATE ambient_bubble_pending SET status = 'confirmed' WHERE event_id = ?",
                (event_id,),
            )
            self.connection.commit()
        return True

    def cancel_pending(self, event_id: str) -> bool:
        with self.connection.locked():
            cursor = self.connection.execute(
                """
                UPDATE ambient_bubble_pending
                SET status = 'cancelled'
                WHERE event_id = ? AND status = 'pending'
                """,
                (event_id,),
            )
            self.connection.commit()
        return cursor.rowcount > 0

    def record_failure(self, reason: str) -> None:
        self.last_validation_failure_reason = str(reason or "unknown")

    def debug_state(self, local_date: str) -> Dict[str, Any]:
        with self.connection.locked():
            rows = self.connection.execute(
                """
                SELECT suggested_activity, activity_class, expression_key, action
                FROM ambient_bubble_log
                WHERE local_date = ?
                ORDER BY id ASC
                """,
                (local_date,),
            ).fetchall()
            pending_row = self.connection.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM ambient_bubble_pending
                WHERE local_date = ? AND status = 'pending' AND expires_at >= ?
                """,
                (local_date, datetime.utcnow().isoformat()),
            ).fetchone()
        activity_counts: Dict[str, int] = {}
        for row in rows:
            activity = row["suggested_activity"]
            activity_counts[activity] = activity_counts.get(activity, 0) + 1
        last = rows[-1] if rows else None
        return {
            "daily_count": len(rows),
            "pending_count": pending_row["cnt"] if pending_row else 0,
            "activity_counts": activity_counts,
            "last_suggested_activity": last["suggested_activity"] if last else "",
            "last_activity_class": last["activity_class"] if last else "",
            "last_rendered_expression_key": last["expression_key"] if last else "",
            "last_rendered_action": last["action"] if last else "",
            "backoff_step": len(rows),
            "last_validation_failure_reason": self.last_validation_failure_reason,
        }
```

- [x] **Step 4: Add ambient prompt builder**

In `backend/app/pet/prompt_builder.py`:

```python
def build_ambient_bubble_messages(
    settings: Settings,
    *,
    scene: str,
    idle_step: int,
    idle_minutes: int,
    suggested_activity: str,
    pet_state: Dict[str, Any],
    recent_dialogue: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    system_prompt = settings.persona_config.get("system_prompt", "")
    system_prompt += (
        "\n\nV1.6 空闲气泡规则："
        "\n1. 你是住在手机里的调皮小猫桌宠，但台词必须只用第一人称“我”。"
        "\n2. 只能输出 JSON。"
        "\n3. bubble 最多 20 个中文字符左右，只能一句。"
        "\n4. 不要自称豆豆，不要输出颜表情，不要主动开启复杂话题。"
        "\n5. 规则给你的 suggested_activity 只是灵感，不能照抄模板。"
    )
    payload = {
        "event_type": "ambient_bubble",
        "scene": scene,
        "idle_step": idle_step,
        "idle_minutes": idle_minutes,
        "suggested_activity": suggested_activity,
        "constraints": {
            "max_chars": 20,
            "first_person_only": True,
            "no_tts": True,
            "do_not_start_complex_topic": True,
        },
        "pet_state": pet_state,
        "recent_dialogue": recent_dialogue,
        "response_schema": {
            "bubble": "一句短气泡，必须包含“我”，不能包含豆豆或颜表情",
            "expression_key": "/".join(sorted(EXPRESSION_KEYS)),
            "action": BEHAVIOR_ACTION_SCHEMA,
        },
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
```

- [x] **Step 5: Add PetBrain method**

In `backend/app/pet/brain.py`:

```python
from app.pet.prompt_builder import build_ambient_bubble_messages


def generate_ambient_bubble(self, *, scene: str, idle_step: int, idle_minutes: int,
                            suggested_activity: str, pet_state: Dict[str, Any],
                            recent_dialogue: list) -> Dict[str, Any]:
    messages = build_ambient_bubble_messages(
        self.settings,
        scene=scene,
        idle_step=idle_step,
        idle_minutes=idle_minutes,
        suggested_activity=suggested_activity,
        pet_state=pet_state,
        recent_dialogue=recent_dialogue,
    )
    return self.provider.complete_json(messages)
```

- [x] **Step 6: Wire service in app startup**

In `backend/app/main.py`, import the service near the other runtime imports:

```python
from app.runtime.ambient_bubble import AmbientBubbleService
```

Inside `create_app()`, create the service after `state_store` exists and before `app = FastAPI(...)`:

```python
ambient_bubble_service = AmbientBubbleService(state_store.connection)
```

Do **not** assign `app.state` at this point because `app` is not created until later in the current file. Add the state assignment inside the existing `app.state.*` block after `app = FastAPI(...)`, near `app.state.proactive_scheduler = proactive_scheduler`:

```python
app.state.ambient_bubble_service = ambient_bubble_service
```

- [x] **Step 7: Run policy tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_v16_ambient_policy.py -q
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add backend/app/runtime/ambient_bubble.py backend/app/pet/prompt_builder.py backend/app/pet/brain.py backend/app/main.py backend/tests/test_v16_ambient_policy.py
git commit -m "feat: add ambient bubble backend policy"
```

---

## Task 4: Add Ambient Bubble API And Debug Endpoint

**Files:**
- Modify: `backend/app/api/pet.py`
- Modify: `backend/app/api/debug.py`
- Test: `backend/tests/test_v16_ambient_api.py`
- Test: `backend/tests/test_v16_idle_debug.py`

- [x] **Step 1: Write API tests**

Create `backend/tests/test_v16_ambient_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_ambient_check_blocks_stale_frontend():
    app = create_app(testing=True)
    client = TestClient(app)
    response = client.post("/api/pet/ambient/check", json={
        "local_date": "2026-05-31",
        "idle_step": 0,
        "idle_elapsed_ms": 5 * 60_000,
        "client_state": {"visible": True, "foreground": True, "screen_on": True, "idle": True, "busy": False},
    })
    body = response.json()
    assert body["eligible"] is False
    assert body["block_reason"] in {"frontend_stale", "heartbeat_stale"}


def test_ambient_trigger_generates_without_tts_or_history():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})

    provider = app.state.dispatcher.brain.provider
    provider.complete_json = lambda messages: {
        "bubble": "我刚刚没有偷懒。",
        "expression_key": "idle_wink",
        "action": "lazy_idle",
    }

    before_events = app.state.event_log_store.count()
    response = client.post("/api/pet/ambient/trigger", json={
        "local_date": "2026-05-31",
        "scene": "post_conversation_idle",
        "idle_step": 0,
        "idle_elapsed_ms": 5 * 60_000,
        "client_state": {"visible": True, "foreground": True, "screen_on": True, "idle": True, "busy": False},
    })
    body = response.json()
    assert body["active"] is True
    assert body["event_id"].startswith("ambient-")
    assert body["bubble"] == "我刚刚没有偷懒。"
    assert body["expression_key"] == "idle_wink"
    assert body["audio_job_id"] is None
    assert body["voice_url"] is None
    assert app.state.ambient_bubble_service.debug_state("2026-05-31")["daily_count"] == 0
    assert app.state.event_log_store.count() == before_events

    confirm = client.post("/api/pet/ambient/confirm", json={"event_id": body["event_id"]})
    assert confirm.status_code == 200
    assert confirm.json()["ok"] is True
    assert app.state.ambient_bubble_service.debug_state("2026-05-31")["daily_count"] == 1


def test_ambient_cancel_does_not_count():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})
    app.state.dispatcher.brain.provider.complete_json = lambda messages: {
        "bubble": "我在省电。",
        "expression_key": "tired",
        "action": "lazy_idle",
    }
    response = client.post("/api/pet/ambient/trigger", json={
        "local_date": "2026-05-31",
        "scene": "post_conversation_idle",
        "idle_step": 0,
        "idle_elapsed_ms": 5 * 60_000,
        "client_state": {"visible": True, "foreground": True, "screen_on": True, "idle": True, "busy": False},
    })
    event_id = response.json()["event_id"]
    cancelled = client.post("/api/pet/ambient/cancel", json={"event_id": event_id})
    assert cancelled.json()["ok"] is True
    assert app.state.ambient_bubble_service.debug_state("2026-05-31")["daily_count"] == 0


def test_ambient_provider_busy_returns_explicit_block_reason():
    app = create_app(testing=True)
    client = TestClient(app)
    client.post("/api/frontend/heartbeat", json={"user_agent": "test"})
    app.state.provider_gate.acquire("llm_fast")
    app.state.provider_gate.acquire("llm_fast")
    try:
        response = client.post("/api/pet/ambient/trigger", json={
            "local_date": "2026-05-31",
            "scene": "post_conversation_idle",
            "idle_step": 0,
            "idle_elapsed_ms": 5 * 60_000,
            "client_state": {"visible": True, "foreground": True, "screen_on": True, "idle": True, "busy": False},
        })
    finally:
        app.state.provider_gate.release("llm_fast")
        app.state.provider_gate.release("llm_fast")
    assert response.json()["active"] is False
    assert response.json()["block_reason"] == "provider_busy"
```

Create `backend/tests/test_v16_idle_debug.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_idle_debug_requires_token():
    app = create_app(testing=True)
    client = TestClient(app)
    response = client.get("/api/debug/idle-state")
    assert response.status_code == 403


def test_idle_debug_contains_required_fields_with_token():
    app = create_app(testing=True)
    client = TestClient(app)
    token = app.state.internal_token
    response = client.get("/api/debug/idle-state", headers={"x-internal-token": token})
    body = response.json()
    assert body["ok"] is True
    for key in [
        "eligible", "block_reason", "next_trigger_time", "backoff_step",
        "daily_count", "activity_counts", "last_suggested_activity",
        "last_rendered_expression_key", "last_validation_failure_reason",
        "last_submitted_tts_text", "last_submitted_tts_event_id",
        "last_submitted_tts_at", "last_idle_bubble_source",
    ]:
        assert key in body


def test_legacy_proactive_no_longer_generates_user_visible_text():
    app = create_app(testing=True)
    client = TestClient(app)
    check = client.get("/api/pet/proactive")
    assert check.status_code == 200
    assert check.json() == {"active": False, "legacy_disabled": True}
    trigger = client.post("/api/pet/proactive/trigger")
    assert trigger.status_code == 410
```

- [x] **Step 2: Run API tests and verify failure**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_v16_ambient_api.py tests/test_v16_idle_debug.py -q
```

Expected: 404 failures because endpoints do not exist.

- [x] **Step 3: Add request models and eligibility helpers**

In `backend/app/api/pet.py`:

```python
from pydantic import BaseModel, Field
from datetime import datetime
from functools import partial
from uuid import uuid4

from app.runtime.concurrency import ProviderBusyError, ServerBusyError
from app.runtime.expressions import ACTIVITY_RECOMMENDATIONS
from app.runtime.ambient_bubble import guard_ambient_bubble_output, DEFAULT_BACKOFF_MS


class AmbientClientState(BaseModel):
    visible: bool = False
    foreground: bool = False
    screen_on: bool = False
    idle: bool = False
    busy: bool = True
    input_active: bool = False
    recording: bool = False
    waiting_llm: bool = False
    waiting_tts: bool = False
    playing_tts: bool = False


class AmbientRequest(BaseModel):
    local_date: str
    scene: str = "post_conversation_idle"
    idle_step: int = Field(default=0, ge=0)
    idle_elapsed_ms: int = Field(default=0, ge=0)
    client_state: AmbientClientState


class AmbientEventRequest(BaseModel):
    event_id: str
```

Add:

```python
def _ambient_block_reason(request: Request, payload: AmbientRequest) -> str:
    scheduler = getattr(request.app.state, "proactive_scheduler", None)
    if scheduler and scheduler.is_frontend_stale():
        return "frontend_stale"
    state = payload.client_state
    if not state.visible:
        return "page_hidden"
    if not state.foreground:
        return "not_foreground"
    if not state.screen_on:
        return "screen_off"
    if not state.idle or state.busy:
        return "busy"
    if state.input_active:
        return "input_active"
    if state.recording:
        return "recording"
    if state.waiting_llm or state.waiting_tts or state.playing_tts:
        return "waiting_or_playing"
    delay = DEFAULT_BACKOFF_MS[min(payload.idle_step, len(DEFAULT_BACKOFF_MS) - 1)]
    if payload.idle_elapsed_ms < delay:
        return "too_early"
    return ""
```

- [x] **Step 4: Add check endpoint**

In `backend/app/api/pet.py`:

```python
@router.post("/ambient/check")
def post_ambient_check(payload: AmbientRequest, request: Request):
    block = _ambient_block_reason(request, payload)
    svc = request.app.state.ambient_bubble_service
    server = svc.can_emit(payload.local_date)
    if block:
        return {"eligible": False, "block_reason": block}
    if not server["eligible"]:
        return server
    return {"eligible": True, "block_reason": "", "next_activity": svc.select_activity(payload.local_date)}
```

- [x] **Step 5: Add trigger, confirm and cancel endpoints**

In `backend/app/api/pet.py`:

```python
def _generate_ambient_payload(payload: AmbientRequest, request: Request, activity: str) -> dict:
    rec = ACTIVITY_RECOMMENDATIONS[activity]
    pet_state = request.app.state.state_store.get_state()
    recent_dialogue = request.app.state.event_log_store.recent_dialogue_turns(limit=5)
    gate = request.app.state.provider_gate
    gate.acquire("llm_fast")
    try:
        return request.app.state.dispatcher.brain.generate_ambient_bubble(
            scene=payload.scene,
            idle_step=payload.idle_step,
            idle_minutes=int(payload.idle_elapsed_ms / 60000),
            suggested_activity=activity,
            pet_state=pet_state,
            recent_dialogue=recent_dialogue,
        )
    finally:
        gate.release("llm_fast")


@router.post("/ambient/trigger")
async def post_ambient_trigger(payload: AmbientRequest, request: Request):
    block = _ambient_block_reason(request, payload)
    svc = request.app.state.ambient_bubble_service
    if block:
        return {"active": False, "block_reason": block}
    can_emit = svc.begin_generation(payload.local_date)
    if not can_emit["eligible"]:
        return {"active": False, "block_reason": can_emit["block_reason"]}
    try:
        activity = svc.select_activity(payload.local_date)
        if not activity:
            svc.record_failure("no_available_activity")
            return {"active": False, "block_reason": "no_available_activity"}
        rec = ACTIVITY_RECOMMENDATIONS[activity]
        executor = request.app.state.agent_work_executor
        raw = await executor.submit(partial(_generate_ambient_payload, payload, request, activity), timeout_s=45)
        action = guard_ambient_bubble_output(raw)
        if action is None:
            svc.record_failure("validation_failed")
            return {"active": False, "block_reason": "validation_failed"}

        event_id = "ambient-%s-%s" % (
            datetime.utcnow().strftime("%Y%m%d%H%M%S%f"),
            uuid4().hex[:8],
        )
        created = svc.create_pending(
            local_date=payload.local_date,
            event_id=event_id,
            activity=activity,
            activity_class=rec.activity_class,
            bubble=action.bubble,
            expression_key=action.expression_key,
            action=action.action,
        )
        if not created:
            return {"active": False, "block_reason": "pending_or_limit_changed"}
        return {
            "active": True,
            "event_id": event_id,
            "bubble": action.bubble,
            "expression_key": action.expression_key,
            "action": action.action,
            "audio_job_id": None,
            "voice_url": None,
            "runtime": {
                "source": action.source,
                "suggested_activity": activity,
                "activity_class": rec.activity_class,
            },
        }
    except ServerBusyError:
        svc.record_failure("server_busy")
        return {"active": False, "block_reason": "server_busy"}
    except ProviderBusyError:
        svc.record_failure("provider_busy")
        return {"active": False, "block_reason": "provider_busy"}
    except Exception:
        svc.record_failure("llm_provider_error")
        return {"active": False, "block_reason": "llm_provider_error"}
    finally:
        svc.end_generation()


@router.post("/ambient/confirm")
def post_ambient_confirm(payload: AmbientEventRequest, request: Request):
    ok = request.app.state.ambient_bubble_service.confirm_pending(payload.event_id)
    return {"ok": ok}


@router.post("/ambient/cancel")
def post_ambient_cancel(payload: AmbientEventRequest, request: Request):
    ok = request.app.state.ambient_bubble_service.cancel_pending(payload.event_id)
    return {"ok": ok}
```

- [x] **Step 6: Disable legacy proactive user-facing output**

In `backend/app/api/pet.py`, keep the endpoints only as compatibility stubs so old frontends fail clearly instead of seeing rule-generated copy from `ProactiveRuleProvider`:

```python
from fastapi import HTTPException


@router.get("/proactive")
def get_pet_proactive(request: Request):
    return {"active": False, "legacy_disabled": True}


@router.post("/proactive/trigger")
def trigger_pet_proactive(request: Request, mode: str = ""):
    raise HTTPException(
        status_code=410,
        detail={
            "error": "Legacy proactive endpoint disabled; use /api/pet/ambient/*",
            "error_class": "legacy_proactive_disabled",
        },
    )
```

`ProactiveScheduler` can remain for heartbeat/watchdog freshness checks, but `ProactiveRuleProvider` must not be reachable from user-facing frontend code after this task.

- [x] **Step 7: Add debug endpoint**

In `backend/app/api/debug.py`:

```python
@router.get("/api/debug/idle-state")
def debug_idle_state(request: Request) -> Dict[str, Any]:
    require_internal_token(request)
    local_date = datetime.now().date().isoformat()
    svc = getattr(request.app.state, "ambient_bubble_service", None)
    ambient = svc.debug_state(local_date) if svc is not None else {}
    scheduler = getattr(request.app.state, "proactive_scheduler", None)
    eligible = bool(scheduler and not scheduler.is_frontend_stale())
    return {
        "ok": True,
        "eligible": eligible,
        "block_reason": "" if eligible else "frontend_stale",
        "next_trigger_time": "",
        "backoff_step": ambient.get("backoff_step", 0),
        "daily_count": ambient.get("daily_count", 0),
        "pending_count": ambient.get("pending_count", 0),
        "activity_counts": ambient.get("activity_counts", {}),
        "last_suggested_activity": ambient.get("last_suggested_activity", ""),
        "last_rendered_expression_key": ambient.get("last_rendered_expression_key", ""),
        "last_rendered_action": ambient.get("last_rendered_action", ""),
        "last_validation_failure_reason": ambient.get("last_validation_failure_reason", ""),
        "last_submitted_tts_text": getattr(request.app.state.dispatcher, "last_submitted_tts_text", ""),
        "last_submitted_tts_event_id": getattr(request.app.state.dispatcher, "last_submitted_tts_event_id", ""),
        "last_submitted_tts_at": getattr(request.app.state.dispatcher, "last_submitted_tts_at", ""),
        "last_idle_bubble_source": "llm_generated" if ambient.get("daily_count", 0) else "",
    }
```

- [x] **Step 8: Run API tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_v16_ambient_api.py tests/test_v16_idle_debug.py tests/test_phase1_proactive.py -q
```

Expected: PASS after updating `tests/test_phase1_proactive.py` to assert the legacy disabled behavior instead of rule-generated proactive copy.

- [x] **Step 9: Commit**

```bash
git add backend/app/api/pet.py backend/app/api/debug.py backend/tests/test_v16_ambient_api.py backend/tests/test_v16_idle_debug.py backend/tests/test_phase1_proactive.py
git commit -m "feat: add ambient bubble api and debug state"
```

---

## Task 5: Add Frontend Expression Rendering And Sprite Action

**Files:**
- Modify: `frontend/src/pet/faces.ts`
- Modify: `frontend/src/pet/types.ts`
- Modify: `frontend/src/components/PetFace.tsx`
- Use: `frontend/src/components/DoudouSprite.tsx`
- Use: `frontend/src/pet/doudouSprites.ts`
- Modify: `frontend/src/pet/behaviorDirector.ts`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/pet/faces.test.ts`
- Test: `frontend/src/App.test.tsx`

- [x] **Step 1: Add frontend expression tests**

Update `frontend/src/pet/faces.test.ts`:

```ts
import { expressionForKey, faceForType } from "./faces";

test("expressionForKey returns configured expression", () => {
  expect(expressionForKey("playful")).toBe("(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧");
});

test("expressionForKey falls back through mood", () => {
  expect(expressionForKey("unknown", "angry")).toBe("(｀へ´)");
  expect(expressionForKey("unknown")).toBe("(・ω・)");
});

test("faceForType keeps old mood behavior", () => {
  expect(faceForType("happy")).toBe("(^▽^)");
});
```

- [x] **Step 2: Run test and verify failure**

Run:

```bash
cd frontend && npm test -- --run src/pet/faces.test.ts
```

Expected: failure because `expressionForKey` does not exist.

- [x] **Step 3: Update frontend types**

In `frontend/src/pet/types.ts`:

```ts
export type ExpressionKey =
  | "idle_soft"
  | "idle_wink"
  | "happy"
  | "happy_big"
  | "excited"
  | "shy"
  | "clingy"
  | "thinking"
  | "confused"
  | "concerned"
  | "sad"
  | "crying"
  | "sleepy"
  | "tired"
  | "annoyed"
  | "wronged"
  | "proud"
  | "playful"
  | "lonely"
  | "calm";
```

Add to `PetResponse`:

```ts
expression_key?: ExpressionKey;
action?: string;
```

- [x] **Step 4: Update face map**

In `frontend/src/pet/faces.ts`:

```ts
import type { ExpressionKey, Mood } from "./types";

export const expressionMap: Record<ExpressionKey, string> = {
  idle_soft: "(・ω・)",
  idle_wink: "(｡•̀ᴗ-)✧",
  happy: "(^▽^)",
  happy_big: "(≧▽≦)",
  excited: "٩(ˊᗜˋ*)و",
  shy: "(//▽//)",
  clingy: "(*ﾉωﾉ)",
  thinking: "(・・?)",
  confused: "(。ヘ°)",
  concerned: "(´・ω・)",
  sad: "(｡•́︿•̀｡)",
  crying: "(╥﹏╥)",
  sleepy: "(-_-) zzz",
  tired: "(￣o￣)",
  annoyed: "(｀へ´)",
  wronged: "(｡•́︿•̀｡)",
  proud: "(๑•̀ㅂ•́)و✧",
  playful: "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧",
  lonely: "(._.)",
  calm: "( ˘ω˘ )",
};

const moodExpressionFallback: Record<string, ExpressionKey> = {
  idle: "idle_soft",
  happy: "happy",
  sad: "sad",
  sleepy: "sleepy",
  tired: "tired",
  angry: "annoyed",
  shy: "shy",
  thinking: "thinking",
  concerned: "concerned",
  excited: "excited",
  lonely: "lonely",
};

export function expressionForKey(key?: string | null, mood?: Mood | string | null): string {
  if (key && key in expressionMap) return expressionMap[key as ExpressionKey];
  const fallback = moodExpressionFallback[String(mood || "idle")] ?? "idle_soft";
  return expressionMap[fallback];
}
```

- [x] **Step 5: Update PetFace**

In `frontend/src/components/PetFace.tsx`:

```tsx
import { expressionForKey } from "../pet/faces";
import type { AnimationName, ExpressionKey, Mood } from "../pet/types";

type PetFaceProps = {
  faceType: Mood;
  animation: AnimationName;
  expressionKey?: ExpressionKey | string | null;
};

export function PetFace({ faceType, animation, expressionKey }: PetFaceProps) {
  return (
    <div
      aria-label="豆豆表情"
      className={`pet-face animation-${animation}`}
      data-face-type={faceType}
      data-expression-key={expressionKey ?? ""}
    >
      {expressionForKey(expressionKey, faceType)}
    </div>
  );
}
```

- [x] **Step 6: Update App state and response application**

In `frontend/src/App.tsx`, import `DoudouSprite`, `isValidDoudouAction`, and `DoudouAction`, then add:

```ts
const [spriteAction, setSpriteAction] = useState<DoudouAction>("idle");
const [expressionKey, setExpressionKey] = useState<string>("idle_soft");
```

In `applyPetResponse()`:

```ts
setExpressionKey(response.expression_key ?? response.face_type ?? response.mood);
setSpriteAction(isValidDoudouAction(response.action ?? "") ? response.action as DoudouAction : "idle");
```

In initial state load:

```ts
setExpressionKey(state.mood);
setSpriteAction("idle");
```

In phase changes where the current App only changes `faceType`/`animation`, also update `spriteAction` with the existing phase mapping:

```ts
setSpriteAction(BehaviorDirector.phaseToAction(nextPhase));
```

Do not call `BehaviorDirector.onAmbientTick()` for V1.6 ambient bubbles. That existing method contains rule-generated idle text and self-references, so it must not drive user-facing ambient copy after this migration.

In render, keep `PetFace` for the kaomoji contract and add the sprite as the visible action carrier:

```tsx
<DoudouSprite action={spriteAction} />
<PetFace faceType={faceType} animation={animation} expressionKey={expressionKey} />
```

- [x] **Step 7: Update App test fixture**

In `frontend/src/App.test.tsx`, add `expression_key` to successful responses:

```ts
expression_key: "thinking",
```

Add assertion:

```ts
expect(screen.getByLabelText("豆豆表情")).toHaveAttribute("data-expression-key", "thinking");
expect(screen.getByLabelText("豆豆")).toHaveAttribute("data-action", "think");
```

- [x] **Step 8: Run frontend expression tests**

Run:

```bash
cd frontend && npm test -- --run src/pet/faces.test.ts src/components/PetFace.test.tsx src/App.test.tsx
```

Expected: PASS.

- [x] **Step 9: Commit**

```bash
git add frontend/src/pet/faces.ts frontend/src/pet/types.ts frontend/src/components/PetFace.tsx frontend/src/pet/faces.test.ts frontend/src/components/PetFace.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: render doudou expression keys"
```

---

## Task 6: Replace Frontend Proactive Polling With Ambient Idle Controller

**Files:**
- Create: `frontend/src/pet/ambient.ts`
- Modify: `frontend/src/pet/api.ts`
- Modify: `frontend/src/pet/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/TextInputBar.tsx`
- Use: `frontend/src/components/DoudouSprite.tsx`
- Test: `frontend/src/pet/ambient.test.ts`
- Test: `frontend/src/pet/api.test.ts`
- Test: `frontend/src/App.test.tsx`

- [x] **Step 1: Write ambient controller tests**

Create `frontend/src/pet/ambient.test.ts`:

```ts
import { describe, expect, test } from "vitest";

import {
  ambientDelayMs,
  buildAmbientClientState,
  getLocalDateString,
  loadAmbientState,
  saveAmbientState,
  shouldRequestAmbient,
} from "./ambient";

test("ambient delay follows V1.6 backoff", () => {
  expect(ambientDelayMs(0)).toBe(5 * 60_000);
  expect(ambientDelayMs(1)).toBe(10 * 60_000);
  expect(ambientDelayMs(2)).toBe(20 * 60_000);
  expect(ambientDelayMs(3)).toBe(40 * 60_000);
  expect(ambientDelayMs(4)).toBe(90 * 60_000);
  expect(ambientDelayMs(9)).toBe(90 * 60_000);
});

test("shouldRequestAmbient blocks non-idle states", () => {
  expect(shouldRequestAmbient({
    now: 1000,
    idleAnchorAt: 0,
    idleStep: 0,
    visible: true,
    foreground: true,
    screenOn: true,
    phase: "idle",
    busy: false,
    inputActive: false,
    recording: false,
    waitingLlm: false,
    waitingTts: false,
    playingTts: false,
  })).toBe(false);

  expect(shouldRequestAmbient({
    now: 5 * 60_000,
    idleAnchorAt: 0,
    idleStep: 0,
    visible: true,
    foreground: true,
    screenOn: true,
    phase: "idle",
    busy: false,
    inputActive: false,
    recording: false,
    waitingLlm: false,
    waitingTts: false,
    playingTts: false,
  })).toBe(true);
});

test("client state maps UI blockers", () => {
  const state = buildAmbientClientState({
    visible: false,
    foreground: true,
    screenOn: true,
    phase: "speaking",
    busy: true,
    inputActive: true,
    recording: false,
    waitingLlm: false,
    waitingTts: false,
    playingTts: true,
  });
  expect(state.visible).toBe(false);
  expect(state.busy).toBe(true);
  expect(state.playing_tts).toBe(true);
});

test("getLocalDateString uses device local date instead of UTC", () => {
  const date = new Date(2026, 4, 31, 0, 30, 0);
  expect(getLocalDateString(date)).toBe("2026-05-31");
});

test("ambient state persists idle step and local date", () => {
  const storage = new Map<string, string>();
  const fakeStorage = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  } as Storage;
  saveAmbientState(fakeStorage, { idleAnchorAt: 1000, idleStep: 2, localDate: "2026-05-31" });
  expect(loadAmbientState(fakeStorage, "2026-05-31")).toEqual({
    idleAnchorAt: 1000,
    idleStep: 2,
    localDate: "2026-05-31",
  });
  expect(loadAmbientState(fakeStorage, "2026-06-01")?.idleStep).toBe(0);
});
```

- [x] **Step 2: Run test and verify failure**

Run:

```bash
cd frontend && npm test -- --run src/pet/ambient.test.ts
```

Expected: import failure because `ambient.ts` does not exist.

- [x] **Step 3: Implement ambient helpers**

Create `frontend/src/pet/ambient.ts`:

```ts
import type { PetUIPhase } from "./types";

const DELAYS = [5, 10, 20, 40, 90].map((minutes) => minutes * 60_000);
const AMBIENT_STORAGE_KEY = "petagent:v16:ambient-state";

export type AmbientPersistedState = {
  idleAnchorAt: number;
  idleStep: number;
  localDate: string;
};

export function ambientDelayMs(step: number): number {
  return DELAYS[Math.min(Math.max(0, step), DELAYS.length - 1)];
}

export function getLocalDateString(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function loadAmbientState(storage: Storage, localDate = getLocalDateString()): AmbientPersistedState | null {
  try {
    const raw = storage.getItem(AMBIENT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AmbientPersistedState>;
    if (parsed.localDate !== localDate) {
      return { idleAnchorAt: Date.now(), idleStep: 0, localDate };
    }
    if (!Number.isFinite(parsed.idleAnchorAt) || !Number.isFinite(parsed.idleStep)) return null;
    return {
      idleAnchorAt: Number(parsed.idleAnchorAt),
      idleStep: Math.max(0, Number(parsed.idleStep)),
      localDate,
    };
  } catch {
    return null;
  }
}

export function saveAmbientState(storage: Storage, state: AmbientPersistedState): void {
  try {
    storage.setItem(AMBIENT_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // localStorage can fail in private mode; ambient bubbles can still run in memory.
  }
}

export type AmbientEligibilityInput = {
  now: number;
  idleAnchorAt: number;
  idleStep: number;
  visible: boolean;
  foreground: boolean;
  screenOn: boolean;
  phase: PetUIPhase;
  busy: boolean;
  inputActive: boolean;
  recording: boolean;
  waitingLlm: boolean;
  waitingTts: boolean;
  playingTts: boolean;
};

export function shouldRequestAmbient(input: AmbientEligibilityInput): boolean {
  if (!input.visible || !input.foreground || !input.screenOn) return false;
  if (input.phase !== "idle" || input.busy) return false;
  if (input.inputActive || input.recording || input.waitingLlm || input.waitingTts || input.playingTts) return false;
  return input.now - input.idleAnchorAt >= ambientDelayMs(input.idleStep);
}

export function buildAmbientClientState(input: Omit<AmbientEligibilityInput, "now" | "idleAnchorAt" | "idleStep">) {
  return {
    visible: input.visible,
    foreground: input.foreground,
    screen_on: input.screenOn,
    idle: input.phase === "idle",
    busy: input.busy,
    input_active: input.inputActive,
    recording: input.recording,
    waiting_llm: input.waitingLlm,
    waiting_tts: input.waitingTts,
    playing_tts: input.playingTts,
  };
}
```

- [x] **Step 4: Add API types and functions**

In `frontend/src/pet/types.ts`:

```ts
export type AmbientClientState = {
  visible: boolean;
  foreground: boolean;
  screen_on: boolean;
  idle: boolean;
  busy: boolean;
  input_active: boolean;
  recording: boolean;
  waiting_llm: boolean;
  waiting_tts: boolean;
  playing_tts: boolean;
};

export type AmbientCheckRequest = {
  local_date: string;
  scene: string;
  idle_step: number;
  idle_elapsed_ms: number;
  client_state: AmbientClientState;
};

export type AmbientCheckResponse = {
  eligible: boolean;
  block_reason: string;
  next_activity?: string | null;
};

export type AmbientBubbleResponse = {
  active: boolean;
  event_id?: string;
  bubble?: string;
  expression_key?: ExpressionKey;
  action?: string;
  block_reason?: string;
  audio_job_id?: null;
  voice_url?: null;
  runtime?: Record<string, unknown>;
};

export type AmbientEventRequest = {
  event_id: string;
};
```

In `frontend/src/pet/api.ts`:

```ts
export function getAmbientCheck(payload: AmbientCheckRequest): Promise<AmbientCheckResponse> {
  return requestJson<AmbientCheckResponse>("/api/pet/ambient/check", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function triggerAmbientBubble(payload: AmbientCheckRequest): Promise<AmbientBubbleResponse> {
  return requestJson<AmbientBubbleResponse>("/api/pet/ambient/trigger", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function confirmAmbientBubble(payload: AmbientEventRequest): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>("/api/pet/ambient/confirm", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function cancelAmbientBubble(payload: AmbientEventRequest): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>("/api/pet/ambient/cancel", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
}
```

- [x] **Step 5: Replace App proactive polling**

In `frontend/src/App.tsx`:

Remove current `getProactiveCheck()` / `triggerProactiveEvent()` polling imports and effect.

Add state:

```ts
const [inputActive, setInputActive] = useState(false);
const [recordingActive, setRecordingActive] = useState(false);
const initialAmbient = loadAmbientState(window.localStorage, getLocalDateString());
const [idleAnchorAt, setIdleAnchorAt] = useState(initialAmbient?.idleAnchorAt ?? Date.now());
const [idleStep, setIdleStep] = useState(initialAmbient?.idleStep ?? 0);
const ambientInFlightRef = useRef(false);
const pendingAmbientEventRef = useRef<string | null>(null);
```

Add one helper and use it for successful dialogue, ASR/LLM/TTS failures after the error is visible, audio interrupt/cancel, and successful button interactions:

```ts
function markIdleAnchor(resetStep = true) {
  const now = Date.now();
  const localDate = getLocalDateString();
  setIdleAnchorAt(now);
  if (resetStep) setIdleStep(0);
  saveAmbientState(window.localStorage, {
    idleAnchorAt: now,
    idleStep: resetStep ? 0 : idleStep,
    localDate,
  });
}
```

When an ambient bubble displays successfully, persist the advanced step:

```ts
function advanceAmbientStep() {
  const now = Date.now();
  const nextStep = idleStep + 1;
  const localDate = getLocalDateString();
  setIdleAnchorAt(now);
  setIdleStep(nextStep);
  saveAmbientState(window.localStorage, { idleAnchorAt: now, idleStep: nextStep, localDate });
}
```

Add ambient effect:

```ts
useEffect(() => {
  if (!isOnline) return;
  const timer = window.setInterval(() => {
    if (ambientInFlightRef.current) return;
    const now = Date.now();
    const visible = document.visibilityState === "visible";
    const clientState = buildAmbientClientState({
      visible,
      foreground: visible,
      screenOn: visible,
      phase,
      busy,
      inputActive,
      recording: recordingActive,
      waitingLlm: phase === "thinking",
      waitingTts: phase === "waiting_voice",
      playingTts: phase === "speaking",
    });
    if (!shouldRequestAmbient({
      now,
      idleAnchorAt,
      idleStep,
      visible,
      foreground: visible,
      screenOn: visible,
      phase,
      busy,
      inputActive,
      recording: recordingActive,
      waitingLlm: phase === "thinking",
      waitingTts: phase === "waiting_voice",
      playingTts: phase === "speaking",
    })) return;
    ambientInFlightRef.current = true;
    const payload = {
      local_date: getLocalDateString(),
      scene: "post_conversation_idle",
      idle_step: idleStep,
      idle_elapsed_ms: now - idleAnchorAt,
      client_state: clientState,
    };
    void getAmbientCheck(payload)
      .then((check) => {
        if (!check.eligible) return null;
        return triggerAmbientBubble(payload);
      })
      .then((ambient) => {
        if (!ambient?.active || !ambient.bubble) return;
        if (phaseRef.current !== "idle") {
          if (ambient.event_id) void cancelAmbientBubble({ event_id: ambient.event_id }).catch(() => undefined);
          return;
        }
        setBubbleText(ambient.bubble);
        setExpressionKey(ambient.expression_key ?? "idle_soft");
        if (ambient.action && isValidDoudouAction(ambient.action)) {
          setSpriteAction(ambient.action);
        }
        if (ambient.event_id) {
          pendingAmbientEventRef.current = ambient.event_id;
          void confirmAmbientBubble({ event_id: ambient.event_id }).catch(() => undefined);
        }
        advanceAmbientStep();
      })
      .catch(() => undefined)
      .finally(() => {
        ambientInFlightRef.current = false;
      });
  }, 30_000);
  return () => window.clearInterval(timer);
}, [isOnline, phase, busy, inputActive, recordingActive, idleAnchorAt, idleStep]);
```

If any user interaction starts while `pendingAmbientEventRef.current` is set and confirm has not been sent yet, call `cancelAmbientBubble({ event_id })` and clear the ref.

Extend `TextInputBar` with optional `onActiveChange`. Call it on focus, blur, `onChange`, composition start/end, submit start, and after successful clear:

```tsx
type TextInputBarProps = {
  disabled: boolean;
  onSubmit: (text: string) => Promise<boolean | void> | boolean | void;
  onActiveChange?: (active: boolean) => void;
};
```

For the input handlers:

```tsx
onFocus={() => onActiveChange?.(true)}
onBlur={() => onActiveChange?.(!!value.trim())}
onCompositionStart={() => onActiveChange?.(true)}
onCompositionEnd={() => onActiveChange?.(!!value.trim())}
onChange={(event) => {
  const next = event.target.value;
  setValue(next);
  onActiveChange?.(document.activeElement === event.currentTarget || !!next.trim());
}}
```

- [x] **Step 6: Ensure user interaction resets idle**

In text submit start, voice phase `listening`, voice upload `thinking`, successful button interaction, reset button, and any tap/touch interaction:

```ts
markIdleAnchor(true);
```

In `handleVoicePhase()`:

```ts
setRecordingActive(nextPhase === "listening" || nextPhase === "thinking");
if (nextPhase === "idle" || nextPhase === "error" || nextPhase === "audio_error") {
  markIdleAnchor(true);
}
```

When `playResponseAudio()` finishes successfully, call `markIdleAnchor(true)` after phase becomes `idle`. When audio fails and the error bubble is shown, set a short timeout such as 1500ms that returns phase to `idle` and then calls `markIdleAnchor(true)`; this prevents `audio_error` from permanently blocking ambient eligibility.

- [x] **Step 7: Run frontend tests**

Run:

```bash
cd frontend && npm test -- --run src/pet/ambient.test.ts src/pet/api.test.ts src/App.test.tsx
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add frontend/src/pet/ambient.ts frontend/src/pet/api.ts frontend/src/pet/types.ts frontend/src/App.tsx frontend/src/components/TextInputBar.tsx frontend/src/pet/ambient.test.ts frontend/src/pet/api.test.ts frontend/src/App.test.tsx
git commit -m "feat: add ambient idle bubble frontend"
```

---

## Task 7: Full Regression And Nubia Verification

**Files:**
- Modify: `plan/V1.6/doudou-expression-and-ambient-bubble-verification.md`

- [x] **Step 1: Run backend targeted tests**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest \
  tests/test_v16_expression_contract.py \
  tests/test_v16_ambient_policy.py \
  tests/test_v16_ambient_api.py \
  tests/test_v16_idle_debug.py \
  tests/test_fast_reply_contract.py \
  tests/test_text_chat.py \
  tests/test_voice_pipeline.py \
  -q
```

Expected: PASS.

- [x] **Step 2: Run backend full suite**

Run:

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

Expected: PASS or only known skipped tests.

- [x] **Step 3: Run frontend targeted tests**

Run:

```bash
cd frontend && npm test -- --run \
  src/pet/faces.test.ts \
  src/pet/ambient.test.ts \
  src/pet/api.test.ts \
  src/components/PetFace.test.tsx \
  src/App.test.tsx
```

Expected: PASS.

- [x] **Step 4: Run frontend full suite**

Run:

```bash
cd frontend && npm test -- --run
```

Expected: PASS.

- [x] **Step 5: Check formatting and diff safety**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors. Status should show only V1.6-related files.

- [x] **Step 6: Nubia connection precheck**

Current known device state on 2026-05-31: ADB is available, screen is awake, backend is reachable through `adb forward tcp:18000 tcp:8000`, and Wi-Fi SSH to `nubia:8022` may time out because Mac routing/VPN can capture the phone subnet. Treat ADB forward as the required HTTP verification path, and use `ssh nubia-adb` for Termux restarts while USB is connected.

Run from the Mac:

```bash
adb devices -l
adb shell dumpsys power | rg -n "mWakefulness|Display Power|state="
adb forward tcp:18000 tcp:8000
adb forward --list | rg "tcp:18000"
curl -sS --max-time 5 http://127.0.0.1:18000/api/health
curl -sS --max-time 5 http://127.0.0.1:18000/api/health/watchdog
```

Expected:

- `adb devices -l` shows `9debb82b NX531J device`.
- Power dump shows `mWakefulness=Awake` and display `state=ON`.
- Health returns `"ok":true`.
- Watchdog returns `"ok":true` and `stuck:false`.

- [x] **Step 7: Deploy to Nubia and restart only through real Termux context**

Deploy files with the existing ADB archive flow:

```bash
BUILD_FRONTEND=1 ./scripts/deploy_nubia.sh
```

Then restart through SSH over ADB forward. This is the standard deployment path for this project while USB is connected. It is still a real Termux SSH session (`u0_a137` with `inet` group), not `adb shell`:

```bash
adb forward tcp:18022 tcp:8022
ssh -o ConnectTimeout=5 nubia-adb 'cd ~/Petagent && scripts/start.sh'
```

If `ssh nubia-adb` times out after the forward is created, do **not** start the backend through `adb shell su` or as root. `scripts/start.sh` intentionally refuses root/adb network contexts because Android socket permission requires the real Termux app `inet` group. Mark deployment restart as `blocked_ssh_unavailable`, keep the existing running service if health remains good, and record that HTTP checks verify the currently running build only. Direct Wi-Fi SSH via `ssh nubia` is not a deployment prerequisite.

- [x] **Step 8: Verify Nubia health and build hash through ADB forward**

Run from host:

```bash
curl -sS --max-time 5 http://127.0.0.1:18000/api/health
curl -sS --max-time 5 http://127.0.0.1:18000/api/health/watchdog
```

Expected health shape:

```json
{"ok": true}
```

The response should include the current build hash if existing health output supports it. If build hash is not the just-deployed commit because SSH restart was unavailable, record the mismatch explicitly and do not mark deployed-build verification as pass.

- [x] **Step 9: Verify foreground expression contract on Nubia**

Send a text chat request:

```bash
curl -sS --max-time 60 -X POST http://127.0.0.1:18000/api/text/chat \
  -H 'content-type: application/json' \
  -d '{"text":"你是不是又偷懒了"}'
```

Expected:

- `reply` does not contain kaomoji.
- `reply` does not contain `豆豆`.
- `expression_key` is present and whitelisted.
- `audio_job_id` may be present, but TTS debug text equals `reply` when debug endpoint can be queried.

- [x] **Step 10: Verify ambient trigger with debug-scaled payload**

Send heartbeat, then trigger ambient:

```bash
LOCAL_DATE="$(date +%Y-%m-%d)"

curl -sS --max-time 5 -X POST http://127.0.0.1:18000/api/frontend/heartbeat \
  -H 'content-type: application/json' \
  -d '{"user_agent":"nubia-test"}'

curl -sS --max-time 60 -X POST http://127.0.0.1:18000/api/pet/ambient/trigger \
  -H 'content-type: application/json' \
  -d '{"local_date":"'"$LOCAL_DATE"'","scene":"post_conversation_idle","idle_step":0,"idle_elapsed_ms":300000,"client_state":{"visible":true,"foreground":true,"screen_on":true,"idle":true,"busy":false,"input_active":false,"recording":false,"waiting_llm":false,"waiting_tts":false,"playing_tts":false}}'
```

Expected:

- `active:true` or a clear `block_reason`.
- If active: response contains `event_id`.
- If active: `bubble` contains `我`, not `豆豆`.
- If active: no `audio_job_id`, no `voice_url`.
- If active: `runtime.source` is `llm_generated`.

- [x] **Step 11: Confirm or cancel ambient display during manual API verification**

If Step 10 returned `active:true`, confirm it only after manually deciding the returned bubble would have been displayed:

```bash
TRIGGER_RESPONSE='{"active":true,"event_id":"ambient-example"}'
EVENT_ID="$(python -c 'import json, sys; print(json.loads(sys.stdin.read()).get("event_id", ""))' <<< "$TRIGGER_RESPONSE")"
test -n "$EVENT_ID"
curl -sS --max-time 5 -X POST http://127.0.0.1:18000/api/pet/ambient/confirm \
  -H 'content-type: application/json' \
  -d '{"event_id":"'"$EVENT_ID"'"}'
```

If the UI state changed or the response was not displayed, cancel instead:

```bash
curl -sS --max-time 5 -X POST http://127.0.0.1:18000/api/pet/ambient/cancel \
  -H 'content-type: application/json' \
  -d '{"event_id":"'"$EVENT_ID"'"}'
```

- [x] **Step 12: Verify debug idle state**

Run with debug token only if it is known. On Nubia the token normally lives under `~/Petagent/backend/secrets/internal_token`, but if SSH/Termux is unavailable it may not be retrievable from the host. Do not assume `$DEBUG_TOKEN` is set.

```bash
curl -sS --max-time 5 http://127.0.0.1:18000/api/debug/idle-state \
  -H "x-internal-token: $DEBUG_TOKEN"
```

Expected without token:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18000/api/debug/idle-state
```

returns `403`.

Expected fields:

- `eligible`
- `block_reason`
- `backoff_step`
- `daily_count`
- `activity_counts`
- `last_suggested_activity`
- `last_rendered_expression_key`
- `last_validation_failure_reason`
- `last_submitted_tts_text`
- `last_submitted_tts_event_id`
- `last_submitted_tts_at`
- `last_idle_bubble_source`

- [x] **Step 13: Write verification notes**

Create `plan/V1.6/doudou-expression-and-ambient-bubble-verification.md` using the observed results from Steps 1-12. Set the shell variables first, then generate the file:

```bash
COMMIT="$(git rev-parse --short HEAD)"
BACKEND_TARGETED="pass"
BACKEND_FULL="pass"
FRONTEND_TARGETED="pass"
FRONTEND_FULL="pass"
NUBIA_HEALTH="pass"
NUBIA_ADB_FORWARD="pass"
NUBIA_SSH_RESTART="blocked_ssh_unavailable"
NUBIA_FOREGROUND_EXPRESSION="pass"
NUBIA_TTS_EXCLUDES_EXPRESSION="pass"
NUBIA_AMBIENT_TRIGGER="pass"
NUBIA_AMBIENT_CONFIRM="pass"
NUBIA_DEBUG_IDLE_STATE="pass"

cat > plan/V1.6/doudou-expression-and-ambient-bubble-verification.md <<EOF
# PetAgent V1.6 Verification

**Date:** 2026-05-31
**Commit:** ${COMMIT}

## Backend

- Targeted tests: ${BACKEND_TARGETED}
- Full tests: ${BACKEND_FULL}

## Frontend

- Targeted tests: ${FRONTEND_TARGETED}
- Full tests: ${FRONTEND_FULL}

## Nubia

- ADB forward: ${NUBIA_ADB_FORWARD}
- SSH/Termux restart: ${NUBIA_SSH_RESTART}
- Health: ${NUBIA_HEALTH}
- Foreground expression: ${NUBIA_FOREGROUND_EXPRESSION}
- TTS excludes expression: ${NUBIA_TTS_EXCLUDES_EXPRESSION}
- Ambient trigger: ${NUBIA_AMBIENT_TRIGGER}
- Ambient confirm/cancel: ${NUBIA_AMBIENT_CONFIRM}
- Debug idle state: ${NUBIA_DEBUG_IDLE_STATE}

## Notes

- ADB forward used host URL `http://127.0.0.1:18000`.
- Health response contained `"ok": true`.
- Foreground text response contained a whitelisted `expression_key`.
- Debug idle state exposed `daily_count`, `activity_counts`, `last_submitted_tts_text`, and `last_idle_bubble_source`.
EOF
```

If any verification item fails, set that variable to `fail` and add a concrete note under `## Notes` before committing.

- [x] **Step 14: Final commit**

```bash
git add plan/V1.6/doudou-expression-and-ambient-bubble-verification.md
git commit -m "test: verify V1.6 expression and ambient bubble"
```

---

## Self-Review Checklist

- [x] Spec coverage: expression key, prompt schema, TTS isolation, ambient LLM generation, no rule-generated text, backoff, limits, debug state and Nubia verification all have tasks.
- [x] No user-facing Thinking Mode or Recall Mode is introduced.
- [x] Ambient bubbles do not write memory, do not call TTS and do not count as successful dialogue turns.
- [x] Foreground TTS only uses final sanitized `reply`.
- [x] Frontend owns actual TTS-end idle timing; backend owns daily limits, activity selection and LLM output validation.
- [x] Existing V1.5 failure behavior remains: invalid LLM output fails instead of producing fake normal replies.
