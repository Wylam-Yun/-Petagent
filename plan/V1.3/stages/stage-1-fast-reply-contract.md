# Stage 1: Fast Reply Contract (v2 — post pre-review)

**Date:** 2026-05-26
**Goal:** Establish the backend contract for Fast Reply Mode — new route values, new prompt builder, new guard path, disable heavy voice fallback, update all affected tests. No frontend UX changes.

## Scope

Backend contract layer only. Frontend UX (layout, voice tap-to-record, desktop pet surface) is Stage 4+.

### 1. Route Policy Update

**File:** `backend/app/runtime/route_policy.py`

Changes to `decide_route()`:
- Rename `RouteDecision.route` values: `"fast"` → `"fast_reply"`, `"slow"` → `"thinking"`
- **Keep `RouteDecision.brain` values as `"fast"` / `"slow"` unchanged** — brain values select which LLM provider to use and are consumed by text_pipeline/voice_pipeline; renaming them adds risk with no benefit in Stage 1
- Map `thinking_mode=True` → route `"thinking"`, context_profile `"thinking"`, brain `"slow"`, `allow_tools=False`
- Map proactive events → route `"fast_reply"`, context_profile `"proactive"`, brain `"fast"`
- Map default text/voice → route `"fast_reply"`, context_profile `"fast_reply"`, brain `"fast"`
- Map **tool keywords** (天气, 电量, etc.) → `fast_reply` / `fast_reply` / `fast` / **no tools** (V1.3 disables tools)
- Map **long-task keywords** (代码, 编程, etc.) → `fast_reply` / `fast_reply` / `fast` / **no tools** (suggest Thinking Mode in prompt instead)
- Keep recall keywords → `fast_reply` / `fast_reply` / `fast`
- Keep button events → `fast_reply` / `fast_reply` / `fast`

New context profiles:
- `fast_reply` (replaces `fast_companion`)
- `thinking` (replaces `long_task`)
- `proactive` (unchanged)
- Old names `tool`, `long_task`, `fast_companion` become dead code — removed from new code paths but kept as aliases in context_manager for backward compat with existing tests during transition

**Deferred to later stages:**
- `local_reaction` route (Stage 4 — UX Recovery Fixes)

### 2. Context Manager Profile Update

**File:** `backend/app/runtime/context_manager.py`

Add `fast_reply` and `thinking` to the profile branching (lines 39-69):

| Profile | recent_turns | memory_items | daily_digest | episode_summaries | important_quotes | temporal_recall |
|---|---|---|---|---|---|---|
| `fast_reply` | 1 | 0 (memory cards) | False | False | False | False |
| `thinking` | 6 | 0 (memory cards) | False | False | False | False |
| `proactive` | 2 | 0 (memory cards) | False | False | False | False |

Key changes for V1.3:
- `fast_reply`: only 1 recent turn (spec: "latest 1 user/pet turn"), no scored memories, no retrieval
- `thinking`: 6 recent turns, no scored memories, no retrieval (card-only; Stage 2 wires real cards)
- Both profiles use memory cards path (memory_card_manager) when available, else empty
- `temporal_recall_events` must NOT be populated for any V1.3 profile (disable `_wants_temporal_recall` call for fast_reply and thinking profiles)
- Keep old profile names (`fast_companion`, `tool`, `long_task`) as aliases mapping to the same behavior, so existing tests don't break immediately

### 3. Prompt Builder Updates

**File:** `backend/app/pet/prompt_builder.py`

**3a. Update `build_pet_messages()` profile matching (lines 148-162):**
- Add `fast_reply` branch: same instruction as `fast_companion` ("用1-2句简短自然的话回复")
- Add `thinking` branch: same instruction as `long_task` but with card-only note ("用完整但简洁的话回复，参考小本本里的记忆")
- Keep old profile names as aliases

**3b. Add `build_fast_reply_messages(settings, event, context) -> List[Dict[str, str]]`:**
- System prompt: base persona from `pet_persona.yaml` + fast_reply-specific instruction (short reply, one action, character voice, no state/memory schema)
- User message payload — only these fields, all others forbidden:
  - `user_input`: full text from event
  - `recent_dialogue`: latest 1 user/pet turn from context
  - `pet_state`: `mood`, `energy`, `intimacy`, `sleepiness` only
  - `memory_hints`: placeholder empty list (Stage 2 wires real card selection)
  - `response_schema`: minimal `{"reply": "...", "mood": "...", "action": "..."}`
- Forbidden fields must be **absent** (not empty): current_time, device_state, skill_results, temporal_recall_events, episode_summaries, daily_digest, relevant_memories, important_quotes, state_delta, state_affect, memory_update, behavior_plan, full OUTPUT_SCHEMA_HINT

**Deferred:** `build_thinking_messages()`, `build_memory_judgment_messages()`, `build_nightly_memory_cleanup_messages()` — Stage 2+ uses existing `build_pet_messages()` for thinking route.

### 4. Fast Reply Response Model

**File:** `backend/app/runtime/actions.py`

Add `FastReplyAction` Pydantic model:
- `reply`: str (required)
- `mood`: Optional[str] = None
- `action`: Optional[str] = None (single sprite action from `ALLOWED_BEHAVIOR_ACTIONS`)
- `voice_style`: str = "soft" (spec: "voice_style: optional, default soft")

Add to `PetResponse`:
- `action`: Optional[str] = None (forwarded from FastReplyAction)
- `route`: Optional[str] = None (top-level: "fast_reply" or "thinking")

### 5. Fast Reply Guard

**File:** `backend/app/pet/guard.py`

Add `guard_fast_reply_action(raw: Any, max_reply_chars: int = 80) -> FastReplyAction`:
- Parse raw JSON (reuse `_parse_action` helper)
- If no `reply` field, use fast reply fallback: `{"reply": "嗯嗯，豆豆在这儿。", "mood": "happy", "action": "idle", "voice_style": "soft"}`
- `mood`: validate against `ALLOWED_MOODS`, fallback `"idle"`
- `action`: validate against `ALLOWED_BEHAVIOR_ACTIONS`, fallback `None`
- `voice_style`: validate against `ALLOWED_VOICE_STYLES`, fallback `"soft"`
- `reply`: strip reasoning (reuse `_strip_reasoning`), sanitize prompt leaks (reuse `_sanitize_prompt_leak`), fallback if empty, trim to `max_reply_chars` (80 chars for fast reply, not 500)
- Return `FastReplyAction` Pydantic model

### 6. Brain Fast Reply Method

**File:** `backend/app/pet/brain.py`

Add `generate_fast_reply_action(self, event: PetEvent, context: RuntimeContext) -> Dict[str, Any]`:
- Calls `build_fast_reply_messages(self.settings, event, context)` instead of `build_pet_messages`
- Passes messages to `self.provider.complete_json(messages)`
- Returns raw dict

Keep existing `generate_action()` unchanged for Thinking Mode path.

### 7. Dispatcher Fast Reply Path

**File:** `backend/app/runtime/dispatcher.py`

When `decision.route == "fast_reply"`:

**Phase 2 (unlocked):**
- Call `brain.generate_fast_reply_action(event, context)` instead of `brain.generate_action(event, context)`
- Call `guard_fast_reply_action(raw)` instead of `guard_action(raw)`
- Skip skill execution (already gated by `allow_tools=False`)
- Skip `state_delta` computation
- Skip `_collect_memory_candidates()`
- Use `FastReplyAction.voice_style` for TTS style

**Phase 3 (locked):**
- Still update `final_state["mood"]` from `FastReplyAction.mood` (if present)
- Still update `final_state["last_interaction_at"]` to current time
- Still CAS save state
- Still record in event_log_store (simplified entry)
- Skip `state_affect` on response (set to None)
- Skip `behavior_intent` / `behavior_plan` on response
- Set `response.action = fast_action.action`
- Set `response.route = "fast_reply"`

When `decision.route == "thinking"`:
- Use existing `generate_action()` and `guard_action()` paths
- Set `allow_tools = False` in the decision
- Set `response.route = "thinking"`

### 8. Text Pipeline Route Name Propagation

**File:** `backend/app/runtime/text_pipeline.py`

- `TextRouteInfo.selected`: report `"fast_reply"` or `"thinking"` (from `decision.route`)
- Source string: `"text_fast_reply"` when `decision.brain == "fast"`, `"text_thinking"` when `decision.brain == "slow"` (keep brain-based branching since brain values don't change)
- Update `decision.brain == "slow"` comparison → stays as-is (brain values unchanged)
- Update source string from `"text_fast"` → `"text_fast_reply"`, `"text_slow"` → `"text_thinking"`

### 9. Voice Pipeline Updates

**File:** `backend/app/runtime/voice_pipeline.py`

**9a. Route name propagation:**
- `VoiceRouteInfo.selected`: report `"fast_reply"` or `"thinking"` (from route)
- Update all `"fast"` → `"fast_reply"` and `"slow"` → `"thinking"` string literals:
  - Line 58: `requested_route` validation — accept `"thinking"` instead of `"slow"`
  - Line 70: `selected="fast"` → `selected="fast_reply"`
  - Lines 169, 282, 289: source `"voice_slow"` → `"voice_thinking"`
  - Lines 299, 367: `selected="slow"` → `selected="thinking"`

**9b. Disable heavy fallback for fast reply:**
- When `thinking_mode=False` and ASR fails or confidence < threshold:
  - Do NOT call `_run_audio_fallback()` or `audio_provider.understand()`
  - Return a result with `error_class = "asr_failed"` and `asr_failed_hint = "没听清"`
  - The result should still include `VoiceRouteInfo` with `selected="fast_reply"`
- When `thinking_mode=True`:
  - Keep existing slow fallback behavior unchanged

**File:** `backend/app/runtime/voice_types.py`

Add to `VoiceRouteInfo`:
- `asr_failed_hint: Optional[str] = None` — user-facing hint when fast voice ASR fails

### 10. Test Updates

**File:** `backend/tests/test_route_policy.py`

Rewrite all tests for new route/profile names:
- Default text → route="fast_reply", context_profile="fast_reply", brain="fast"
- Thinking mode → route="thinking", context_profile="thinking", brain="slow", allow_tools=False
- Tool keywords → route="fast_reply", allow_tools=False (was tool/allow_tools=True)
- Long-task keywords → route="fast_reply" (was slow/long_task)
- Proactive → route="fast_reply", context_profile="proactive"
- Button → route="fast_reply"

**File:** `backend/tests/test_text_chat.py`

- `test_text_message_routes_fast`: assert `text_route.selected == "fast_reply"`
- `test_text_message_can_trigger_skill_planner` (line 73-89): rewrite — tool keywords no longer enable skills; assert `skills_used` is empty or absent
- Fast route returns `text_route.selected == "fast_reply"`
- Thinking route returns `text_route.selected == "thinking"`

**File:** `backend/tests/test_voice_pipeline.py`

- Fast voice ASR failure no longer triggers slow fallback
- Thinking voice ASR failure still triggers slow fallback
- Update route name assertions

**File:** `backend/tests/test_agent_run.py`

- Lines 135, 144, 153, 162: update `context_profile` assertions from `"fast_companion"` → `"fast_reply"`, `"tool"` → `"fast_reply"`, `"long_task"` → `"thinking"`
- Line 163: update `text_route.selected == "slow"` → `"thinking"`

**File:** `backend/tests/test_memory_cards.py`

- Lines 163, 193, 451, 484, 524, 592, 632: update `context_profile` values to new names, or keep old names if context_manager aliases them (decide during implementation)

**File:** `backend/tests/test_interaction_catalog.py`

- Lines 116, 135: update `cognition_context={"context_profile": "fast_companion"}` → `"fast_reply"`

**File:** `backend/tests/test_phase2_agent_run.py`

- Line 25: update `"fast_companion"` → `"fast_reply"`

**File:** `backend/tests/test_fast_reply_contract.py` (new)

New tests:
- `test_fast_reply_prompt_excludes_forbidden_fields`: build fast reply prompt, verify no current_time, device_state, skill_results, retrieval fields, full schema
- `test_fast_reply_response_has_action`: mock LLM returning `{"reply": "早", "mood": "happy", "action": "waving"}`, verify `PetResponse.action == "waving"` and `PetResponse.route == "fast_reply"`
- `test_fast_reply_guard_sanitizes`: test guard strips reasoning, prompt leaks, enforces mood/action whitelists, trims to 80 chars
- `test_fast_reply_guard_fallback`: test guard returns safe fallback on empty/invalid LLM output
- `test_thinking_response_has_route`: verify thinking path returns `PetResponse.route == "thinking"` and `allow_tools=False`
- `test_fast_voice_asr_failure_no_slow_fallback`: verify fast voice ASR failure returns `error_class="asr_failed"` and does not call audio_understanding
- `test_fast_reply_skips_state_delta`: verify fast reply response has no state_affect
- `test_context_manager_fast_reply_profile`: verify fast_reply profile returns 1 recent turn, no daily_digest, no episode_summaries, no important_quotes, no temporal_recall

## Files Changed

| File | Change Type | Issue Addressed |
|---|---|---|
| `backend/app/runtime/route_policy.py` | Modify | #10 brain values kept |
| `backend/app/runtime/context_manager.py` | Modify | #5 new profiles |
| `backend/app/pet/prompt_builder.py` | Modify | #6 profile matching + new function |
| `backend/app/runtime/actions.py` | Modify | #4 voice_style on FastReplyAction |
| `backend/app/pet/guard.py` | Modify | #2 guard_fast_reply_action |
| `backend/app/pet/brain.py` | Modify | #1 generate_fast_reply_action |
| `backend/app/runtime/dispatcher.py` | Modify | #3, #12 fast reply branch |
| `backend/app/runtime/text_pipeline.py` | Modify | #9 source strings |
| `backend/app/runtime/voice_pipeline.py` | Modify | #8 route names + fallback |
| `backend/app/runtime/voice_types.py` | Modify | #11 asr_failed_hint |
| `backend/tests/test_route_policy.py` | Modify | route name updates |
| `backend/tests/test_text_chat.py` | Modify | #15 skill planner test |
| `backend/tests/test_voice_pipeline.py` | Modify | fallback test |
| `backend/tests/test_agent_run.py` | Modify | #7 profile names |
| `backend/tests/test_memory_cards.py` | Modify | #7 profile names |
| `backend/tests/test_interaction_catalog.py` | Modify | #7 profile names |
| `backend/tests/test_phase2_agent_run.py` | Modify | #7 profile names |
| `backend/tests/test_fast_reply_contract.py` | New | acceptance tests |

## Nubia Constraints

- No new provider calls introduced
- Fast reply path reduces prompt size → faster LLM response
- Disabling slow fallback for fast voice reduces audio_understanding provider calls
- No SQLite or WAL changes

## Rollback / Compatibility

- `RouteDecision.brain` values unchanged ("fast"/"slow") — text_pipeline and voice_pipeline brain selection unaffected
- Frontend reads `text_route.selected` / `voice_route.selected` — values change from "fast"→"fast_reply" and "slow"→"thinking" but frontend does not branch on these values currently
- Old context profile names kept as aliases in context_manager for test backward compat
- `PetResponse.runtime` dict still carries route info for debugging
- New `PetResponse.action` and `PetResponse.route` are Optional, backward compatible
- Old `PetAction` model unchanged for Thinking Mode path

## Acceptance Checks

1. `pytest backend/tests/test_route_policy.py -v` — all pass
2. `pytest backend/tests/test_text_chat.py -v` — all pass
3. `pytest backend/tests/test_fast_reply_contract.py -v` — all pass
4. `pytest backend/tests/test_voice_pipeline.py -v` — all pass
5. `pytest backend/tests/test_agent_run.py -v` — all pass
6. `pytest backend/tests/test_memory_cards.py -v` — all pass
7. `pytest backend/tests/test_interaction_catalog.py -v` — all pass
8. `pytest backend/tests/test_phase2_agent_run.py -v` — all pass
9. `cd frontend && npx tsc --noEmit` — no type errors
10. Grep for old route/profile names in active prompt paths to confirm dead code
