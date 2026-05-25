# PetAgent V1.3: Fast Reply And Card Memory Spec

**Date:** 2026-05-25
**Project path:** `/Users/wylam/Documents/workspace/Petagent`
**Runtime target:** Nubia Android + Termux, FastAPI backend on
`127.0.0.1:8000`, React/Vite frontend served by backend.

## Goal

V1.3 makes 豆豆 feel faster, more alive, and less like a heavy assistant. The
default path should prioritize user experience: immediate visible reaction,
short spoken reply, minimal context, and predictable memory. Slow, complete
reasoning remains available through Thinking Mode, but it must not be the
default experience.

This spec also absorbs the V1.2 review findings in
`plan/V1.3/v1.2-review-issues.md`. If that issue record conflicts with this
spec, this spec wins because it reflects the later product decision:

- no dynamic memory retrieval;
- no weather/tool path in V1.3;
- card-only memory from `user.md` and `memory.md`;
- fast reply first, complete reasoning only in Thinking Mode.

## Product Principles

1. **User experience first.** A technically complete reply is not better if it
   makes 豆豆 feel frozen.
2. **Reaction before intelligence.** User input should trigger sprite and bubble
   feedback within 100ms.
3. **Fast path by default.** Most daily talk, greetings, and lightweight
   companion interactions use Fast Reply Mode.
4. **Thinking Mode is explicit.** It exists for complete context and deeper
   replies, not for ordinary pet companionship.
5. **Memory is a visible notebook.** 豆豆 remembers through `user.md` and
   `memory.md`, not hidden dynamic search.
6. **Slow work must not block current UX.** Memory writing, nightly cleanup, and
   retries happen behind the current response whenever possible.

## Non-Goals

- No OpenAI/Gemini Realtime or new speech-to-speech provider integration.
- No new external tools, weather lookup, device fact answering, or broad tool
  mode in V1.3.
- No database retrieval of historical memories into prompts.
- No broad art-system redesign in this spec. V1.3 does include the first
  required layout/interaction cleanup because the current surface hurts the pet
  experience, but new art direction can be designed separately.
- No direct model file edits. Models may propose memory operations; backend
  applies them safely.

## Pre-Implementation Compatibility Review

This section records the V1.3 spec/code review from 2026-05-25. It is
normative: implementation should resolve these conflicts before claiming V1.3 is
done.

### Nubia Runtime Constraints

Current target device observed by ADB:

- model: `NX531J`;
- Android: `6.0.1`, SDK `23`;
- memory: about 3.7 GB total, no swap, about 1.8 GB available during review.

Design implications:

- prefer fewer provider calls over clever fallback chains;
- avoid repeated non-idempotent POST retries;
- avoid startup or midnight maintenance that can lock SQLite long enough to
  wedge uvicorn;
- keep frontend JavaScript and layout work modest for the old WebView/browser;
- treat "process alive but port 8000 not listening" as unhealthy, not healthy.

### Route Policy Must Be Replaced

Current `backend/app/runtime/route_policy.py` still has legacy behavior:

- `thinking_mode=True` maps to `long_task` and `allow_tools=True`;
- weather/device keywords map to a `tool` profile;
- code/analysis keywords automatically switch to slow mode and allow tools.

V1.3 route policy must instead be:

| Input | Route | Context profile | Tools | Notes |
| --- | --- | --- | --- | --- |
| default text/voice | `fast_reply` | `fast_reply` | no | short companion reply |
| thinking toggle on | `thinking` | `thinking` | no | slower, more card context |
| complex keywords while fast | `fast_reply` | `fast_reply` | no | suggest Thinking Mode if needed |
| weather/device/tool keywords | `fast_reply` | `fast_reply` | no | do not call tools in V1.3 |
| proactive | `fast_reply` | `proactive` | no | tiny card-only context |
| local tap/ambient | `local_reaction` | none | no | no LLM/TTS |

Implementation must update the old tests that assert `tool`, `long_task`, or
`allow_tools=True` for these paths. Keeping those tests unchanged will fight the
V1.3 product decision.

### Prompt And Context Must Be Split

Current `ContextManager.build()` and `build_pet_messages()` are incompatible
with the V1.3 fast/thinking boundary because they can serialize:

- `current_time`;
- `device_state`;
- `skill_results`;
- `temporal_recall_events`;
- `episode_summaries`;
- `daily_digest`;
- `relevant_memories`;
- `important_quotes`;
- the full `OUTPUT_SCHEMA_HINT`.

V1.3 must add separate prompt builders and prompt payload serializers:

- `build_fast_reply_messages(...)`;
- `build_thinking_messages(...)`;
- `build_memory_judgment_messages(...)`;
- `build_nightly_memory_cleanup_messages(...)`.

For `fast_reply` and `thinking`, forbidden fields must be absent from the
serialized prompt payload, not merely empty. Nightly cleanup is the only V1.3
path allowed to give current local date/time to the model.

### Card Notebook Source Of Truth

Current `MemoryCardManager` treats markdown cards as a SQLite projection/cache
and may rebuild `user.md` / `memory.md` from SQLite. V1.3 changes the source of
truth for prompt memory: the canonical notebook files are:

```text
backend/data/memory_cards/user.md
backend/data/memory_cards/memory.md
```

Required migration boundary:

- Do not let legacy `MemoryCardManager.rebuild()` overwrite canonical V1.3
  notebook files.
- Existing SQLite memory tables may remain for logs, old tests, or maintenance,
  but they are not prompt memory sources in V1.3.
- If old files such as `user_preferences/card.md` or `momo_memories/card.md`
  contain useful data and canonical files are empty, perform a one-time import
  into the new line format.
- After migration, appending and nightly cleanup operate on the canonical files
  directly through a locked file manager.

This is a source-of-truth migration, not just a formatting change.

### Fast Reply Schema Adapter

Current backend models and guard logic accept `behavior_intent` and
`behavior_plan`, but not a direct fast `action`. If V1.3 keeps the minimal fast
schema:

```json
{"reply": "...", "mood": "happy", "action": "waving"}
```

then implementation must add one of these adapters:

1. add a backend `FastReplyAction` model and expose `action` on the API response;
2. or map `action` into an existing whitelisted `behavior_intent` before the
   response reaches the frontend.

The chosen adapter must whitelist sprite actions, preserve fallback behavior
when `action` is missing, and add frontend `PetResponse` typing for `action`,
`behavior_intent`, and `behavior_plan`.

### Fast Voice Must Stay Fast

Current voice config has `slow_fallback_enabled: true`, so a failed/empty/low
confidence ASR result can trigger audio-understanding plus slow brain. That is
too heavy for the default Nubia experience.

V1.3 default voice path:

- tap-to-record records audio;
- ASR runs once;
- if ASR succeeds, route text to `fast_reply`;
- if ASR fails or confidence is too low, show a local "没听清" recovery and do
  not call audio-understanding or slow brain;
- only explicit Thinking Mode may use the heavier audio-understanding route.

Fast voice provider budget should be: ASR + one fast LLM + short TTS. No hidden
second ASR, audio-understanding, tools, or retrieval.

### Non-Idempotent POST Retry Policy

The current frontend request helper retries all JSON requests. For V1.3,
automatic retries must not duplicate provider work:

- `GET /api/audio/jobs/{id}` may keep polling/retrying;
- non-idempotent POSTs such as `/api/text/chat`, `/api/voice/chat`, and
  `/api/pet/event` must not auto-resubmit after timeout unless they carry an
  idempotency key and the backend deduplicates it;
- if a chat POST times out, the UI should keep the current run visible and offer
  explicit retry/cancel instead of silently creating another LLM/TTS run.

### Voice State Machine Must Be Explicit

Tap-to-record is not a small label change. V1.3 must define these states:

- `idle`: mic tap starts recording;
- `listening`: mic tap stops and sends, cancel discards;
- `uploading` / `thinking`: cancel only ignores the pending response unless the
  backend supports cancellation;
- `waiting_voice`: mic tap cancels/ignores pending playback for the current run
  before starting a new recording;
- `speaking`: mic tap stops the current audio element immediately, marks the old
  run superseded locally, then starts recording;
- `audio_error`: retry uses the audio retry endpoint; mic tap starts a new
  recording.

The frontend needs an owned audio controller/ref so playback can be stopped.
Disabling the mic during `speaking` or `waiting_voice` violates the V1.3
interruptibility requirement.

### Audio Retry And Error Class Are Required

V1.3 must not leave audio retry as a poll of the same failed job. Backend must
return a safe `error_class` for audio jobs and implement:

```text
POST /api/audio/jobs/{job_id}/retry
```

Retry creates a new job only for terminal `failed` or `expired` jobs with stored
text/style metadata. Frontend retry polls the new job id. Raw provider errors
must stay out of user-facing copy.

### Memory Write UX Semantics

Because fast memory writes happen in the background, copy must distinguish:

- requested: user asked 豆豆 to remember; background judgment queued;
- saved: notebook file was actually updated;
- skipped: duplicate, unsafe, too vague, or not worth saving;
- failed: provider/file failure, logged but not shown as a scary pet error.

During the current fast reply, prefer wording like "我先记到小本本里" rather than
claiming the write is already durable. A small later bubble such as "小本本更新啦"
is allowed if the job finishes soon, but current speech must not wait for it.

### Local Interaction Boundary

Ordinary sprite tap is local-only. More/TouchArea interactions should also be
local deterministic in the first V1.3 pass unless an interaction is explicitly
marked `requires_model=true`. Any backend sync for local interaction uses a
lightweight reaction endpoint that cannot call LLM or enqueue TTS.

The old `/api/pet/event` path can remain as a legacy/backend path, but the
default visible pet surface must not depend on it for petting, praise, feed, or
play interactions.

## Modes

### Fast Reply Mode

Fast Reply Mode is the default for:

- greetings: "早上好", "晚安", "在吗";
- simple companion talk;
- lightweight emotional support;
- ordinary text or voice messages without complex-task keywords;
- touch-derived local interactions.

Fast Reply Mode optimizes for:

- visible sprite reaction within 100ms;
- short reply;
- one sprite action or one simple behavior intent;
- minimal prompt;
- short TTS text;
- no dynamic retrieval;
- no tools;
- no complete state/memory schema in the model output.

Fast Reply Mode must still use a small amount of memory so 豆豆 does not feel
empty. First version context:

| Context item | Included | Budget |
| --- | --- | --- |
| current user input | yes | full input, trimmed by API limits |
| recent dialogue | yes | latest 1 user/pet turn |
| light pet state | yes | `mood`, `energy`, `intimacy`, `sleepiness` |
| `user.md` | yes | 1 selected item, preference/identity priority |
| `memory.md` | yes | 1 selected item, relationship/project priority |
| current time | no | not included |
| device state | no | not included |
| event summaries | no | disabled |
| daily digest | no | disabled |
| temporal recall | no | disabled |
| scored memories | no | disabled |
| important quotes | no | disabled |
| skill results | no | disabled |

Fast Reply output schema should be minimal:

```json
{
  "reply": "早呀，豆豆醒着呢。",
  "mood": "happy",
  "action": "waving"
}
```

Allowed output fields:

- `reply`: required, short, natural, normally <= 80 Chinese characters.
- `mood`: optional, one of existing mood enum.
- `action`: optional, one Doudou sprite action.
- `behavior_intent`: optional, only if cheaper to reuse existing fallback logic.
- `voice_style`: optional, default `soft`.

Fast Reply must not ask the model for:

- `state_delta`;
- `state_affect`;
- `memory_update`;
- `behavior_plan`;
- `autonomy_notes`;
- `skill_requests`;
- arbitrary timing, CSS, frame, or asset instructions.

Backend supplies safe defaults and deterministic rules for missing fields.

### Thinking Mode

Thinking Mode is for complete answers and deeper memory usage. It is selected
when the user explicitly enables the thinking toggle. Fast Reply may suggest
Thinking Mode for complex requests, but first version should not force-switch
without user intent.

Thinking Mode loads more card context, but it still must not use dynamic memory
retrieval.

Thinking Mode context:

| Context item | Included | Budget |
| --- | --- | --- |
| current user input | yes | full input, trimmed by API limits |
| recent dialogue | yes | latest 6 user/pet turns |
| full pet state | yes | existing pet state fields |
| `user.md` | yes | up to 8 selected items |
| `memory.md` | yes | up to 12 selected items |
| current time | no | not included |
| device state | no | not included |
| event summaries | no | disabled |
| daily digest | no | disabled |
| temporal recall | no | disabled |
| scored memories | no | disabled |
| important quotes | no | disabled |
| tools | no | disabled in V1.3 |

Thinking Mode may use the existing full response schema:

```json
{
  "reply": "...",
  "mood": "...",
  "face_type": "...",
  "animation": "...",
  "voice_style": "...",
  "vibration": "...",
  "behavior_intent": "...",
  "behavior_plan": [
    {
      "action": "review",
      "slot": "before_speech",
      "duration_ms": 900
    }
  ],
  "state_delta": {},
  "state_affect": {},
  "memory_update": {
    "should_save": false,
    "content": ""
  }
}
```

Thinking Mode is allowed to be slower, but it must not become automatically
verbose. If the user only needs comfort, it should still answer briefly.

### Local Reaction Mode

Local Reaction Mode covers direct sprite taps, repeated taps, over-poke, ambient
life, voice start, and local errors.

Local reactions:

- must never call LLM;
- must never enqueue TTS;
- must not set global `busy=true`;
- may update local bubble/sprite immediately;
- may optionally sync deterministic state/log through a lightweight backend
  endpoint.

Ordinary sprite tap must not call `/api/pet/event`.

## Fast Reply UX

The frontend should make Fast Reply feel alive even when the backend is still
working:

1. On text submit or voice release, immediately set sprite to `review` or
   `waiting`.
2. Show a short local bubble such as "豆豆听到啦。" or "豆豆想一句短短的。".
3. When the fast response arrives, show model reply and action.
4. Start TTS job as soon as the reply is available.
5. While TTS is pending, use `review` and quiet progressive copy.
6. When audio plays, keep `review` or the response action if safe.
7. After audio ends, run a short `after_speech` action if present or settle to
   idle.

Fast Reply should not say "我没有上下文" or expose implementation limits. If it
cannot answer safely, it should preserve character:

- "这个豆豆要认真翻一下小本本。"
- "打开思考模式，我帮你好好想。"
- "这件事我得慢慢看，别急。"

## Fast Reply Boundaries

Fast Reply should not hard-answer:

- code generation or debugging;
- long analysis;
- detailed explanations;
- "你还记得昨天/上次吗" when the answer is not in card memory;
- high-stakes advice;
- large writing tasks.

For these, it should either:

- answer briefly if possible; or
- suggest Thinking Mode without pretending to search hidden history.

No weather or external fact path is required in V1.3 because the user does not
intend to use 豆豆 for weather/tool lookup.

## Card-Only Memory

### Memory Sources

Prompt memory sources are only:

```text
backend/data/memory_cards/user.md
backend/data/memory_cards/memory.md
```

The existing internal key `momo_memories` may remain for compatibility, but the
user-facing concept is `memory.md`.

`momo_memories_path` and `momo_memories` are compatibility aliases only. New
code should refer to the canonical file as `memory.md` at the notebook boundary.

The following prompt sources should be removed or disabled for V1.3:

- `memory_manager.scored_memories(...)`;
- `memory_manager.important_quotes(...)`;
- `event_log_store.recall_events(...)`;
- `episode_summary_store.recent(...)`;
- `daily_summary_store.recent(...)`;
- dynamic retrieval fields such as `relevant_memories`,
  `temporal_recall_events`, `episode_summaries`, `daily_digest`,
  `important_quotes`.

Background storage can remain if needed for logs and nightly cleanup, but it
must not be loaded into model prompts.

Removal boundary:

- V1.3 implementation may keep old SQLite stores and summary tables for
  migration, debugging, and cleanup jobs.
- The prompt path must not call dynamic retrieval functions.
- Tests that currently require dynamic retrieval in `long_task`/Thinking prompts
  must be rewritten to require card-only prompts.
- Public memory APIs can remain if they are debug/maintenance tools, but they
  must not influence Fast Reply or Thinking prompts.

### Memory File Format

Use a simple line-oriented format:

```md
- [2026-05-25 20:42][preference] 主人希望豆豆快速回应优先。
- [2026-05-25 21:10][project] 主人正在调 PetAgent V1.3 的快速档。
- [2026-05-25 22:05][relationship] 豆豆和主人约好先少加载上下文。
```

Required fields:

- system timestamp in local timezone;
- category;
- one short sentence.

The model must not output timestamps. Backend adds timestamps at write time.

Allowed categories:

- `identity`: name, birthday, stable identity facts;
- `preference`: likes, dislikes, communication preferences, pet behavior
  preferences;
- `relationship`: important agreements or shared moments with 豆豆;
- `project`: active longer-running work;
- `temporary`: short-lived facts that should expire easily.

### Fast Memory Selection

Fast Reply reads:

- latest or highest-priority `identity/preference` item from `user.md`;
- latest or highest-priority `relationship/project` item from `memory.md`;
- optionally one fresh `temporary` item only if it is within 3 days and directly
  useful.

Selection should not require a model call. Use deterministic rules:

1. parse lines;
2. group by category;
3. prefer `identity/preference` for `user.md`;
4. prefer `relationship/project` for `memory.md`;
5. prefer newer items within the chosen category;
6. ignore malformed lines.

If the notebook grows large, selection must still read cheaply on Nubia:

- cap parsed lines to the latest 200 per file for Fast Reply;
- cap selected prompt text to 400 Chinese characters total;
- do not scan SQLite, embeddings, or summary tables;
- malformed lines are ignored but preserved on disk.

### Thinking Memory Selection

Thinking Mode reads:

- up to 8 selected items from `user.md`;
- up to 12 selected items from `memory.md`;
- priority order: `identity`, `preference`, `relationship`, `project`,
  then fresh `temporary`.

This should also be deterministic and should not call LLM.

## Memory Writes During Fast Reply

Fast Reply must be able to update memory without blocking the user response.

### Trigger Rules

After user text is received, scan the raw user input for hard trigger phrases.
Trigger phrases do not guarantee a write; they only enqueue a background
judgment job.

Initial trigger phrases:

Explicit memory:

- 记住
- 你要记得
- 帮我记
- 别忘了
- 以后记得
- 以后你要知道
- 这个很重要
- 记到小本本
- 写进小本本

Preferences:

- 我喜欢
- 我不喜欢
- 我讨厌
- 我害怕
- 我习惯
- 我希望你
- 我更喜欢
- 我不想要
- 以后不要
- 以后可以

Identity and stable facts:

- 我叫
- 我的名字
- 我是
- 我的生日
- 我住在
- 我的工作
- 我的学校
- 我的猫
- 我的家人
- 我的朋友

Relationship/project:

- 今天我们
- 刚刚我们
- 以后我们
- 这是我们的
- 你陪我
- 我们约好
- 这次要记住

### Background Memory Judgment

If triggers match, enqueue a background memory judgment. The current reply must
not wait for it.

Queue limits for Nubia:

- at most one memory judgment job running at a time;
- at most 5 pending memory jobs;
- drop duplicate pending jobs for the same normalized user input;
- do not start a memory judgment if provider backpressure is active;
- each job should use a short timeout and a small output budget;
- if the queue is full, log and skip rather than slowing the current reply.

The memory judgment prompt should be small and output only:

```json
{
  "should_write": true,
  "target": "user.md",
  "category": "preference",
  "content": "主人希望豆豆快速回应优先，不要为了完整上下文变慢。"
}
```

Allowed fields:

- `should_write`: boolean;
- `target`: `user.md` or `memory.md`;
- `category`: one allowed category;
- `content`: one short sentence, no timestamp;
- `reason`: optional, for logs only.

Backend validates:

- target whitelist;
- category whitelist;
- max content length;
- no prompt/internal fields;
- no raw secrets;
- no timestamp supplied by model.

Backend then writes:

```md
- [YYYY-MM-DD HH:mm][category] content
```

### Write UX

If the user explicitly asks to remember something, the current fast reply may
say:

- "嗯，豆豆记到小本本。"
- "这个我会记住。"

For implicit preference triggers like "我喜欢咖啡", write silently unless the
reply naturally mentions it.

Write failures must not interrupt the current response.

### What Must Not Be Written

- passwords, tokens, secret keys;
- phone numbers, identity numbers, addresses unless the user explicitly asks
  豆豆 to remember and the app policy allows it;
- one-off transient physical state, such as "我现在有点饿";
- permanent negative labels, such as "用户是焦虑的人";
- high-stakes medical/legal/financial conclusions;
- raw long chat excerpts;
- duplicate memory lines.

Negative or emotional memory should be framed as time-bound:

- allowed: "主人今天说有点焦虑，喜欢豆豆轻轻陪着。"
- not allowed: "主人是焦虑的人。"

## Nightly Memory Cleanup

At local midnight, 豆豆 should "整理小本本". This is allowed to be slow because
the user is not waiting.

### Inputs

Nightly cleanup may read:

- today's conversation/event log;
- current `user.md`;
- current `memory.md`;
- current local date/time;
- timestamps already present in memory lines.

This is the only V1.3 memory path that gives current time to the model.

Nubia safety limits:

- run at most once per local day;
- skip if FastAPI health is degraded or provider backpressure is active;
- never run during an active voice/text response;
- read today's conversation log with a bounded limit, for example latest 200
  rows or 20 KB serialized text, whichever comes first;
- do not run SQLite WAL checkpoint in the same critical section as notebook
  cleanup;
- stop the cleanup attempt after a short timeout and retry on the next
  maintenance window;
- cleanup must not make the server appear alive while port `8000` is not
  listening.

### Output

The model proposes operations only:

```json
{
  "add": [
    {
      "target": "memory.md",
      "category": "project",
      "content": "主人最近在调豆豆的快速回复，希望体验优先。"
    }
  ],
  "update": [
    {
      "target": "memory.md",
      "old": "[2026-05-25 20:42][project] ...",
      "new_category": "project",
      "new_content": "主人在推进 PetAgent V1.3，重点是快速档和小本本记忆。"
    }
  ],
  "delete": [
    {
      "target": "memory.md",
      "old": "[2026-05-22 09:00][temporary] ...",
      "reason": "temporary item expired"
    }
  ]
}
```

Backend applies operations safely. The model never writes files directly.

### Aging Rules

Hard rules:

- `identity`: keep unless contradicted by a newer explicit correction.
- `preference`: keep long term, merge duplicates.
- `relationship`: keep important items, merge repeated similar items.
- `project`: after 3 days, summarize related raw memories into one concise
  line.
- `temporary`: delete after 3 days unless promoted to `project`,
  `relationship`, or `preference`.

The "3 days" rule applies to temporary/project detail, not to stable identity or
preference.

### File Safety

Memory file writes must use:

- a single process-local write lock;
- read latest file before applying changes;
- write to temporary file;
- atomic rename;
- backup of previous file before nightly cleanup;
- validation after write.

Instant memory writes and nightly cleanup must not edit memory files
concurrently.

If validation after write fails, restore the backup and keep serving the last
valid notebook content from memory or disk. Do not block Fast Reply because a
cleanup write failed.

## V1.2 Review Fixes Included In V1.3

### Fix A: Fast Tap Boundary

Replace sprite tap backend sync with one of:

1. no backend sync for ordinary taps; or
2. a new lightweight reaction endpoint.

Chosen V1.3 direction: add a lightweight endpoint only if state/log sync is
needed. It must not call LLM and must not enqueue TTS. Until that endpoint
exists, ordinary sprite taps should remain local only.

### Fix B: Behavior Action Execution

V1.3 Fast Reply output can be a single `action`. Thinking Mode can still use
`behavior_plan`.

Frontend must:

- type behavior fields in `PetResponse`;
- remove `Record<string, unknown>` casts;
- execute single-action Fast Reply immediately;
- execute Thinking Mode `behavior_plan` slots at real phase boundaries:
  `before_speech`, `speech`, `after_speech`, `idle_after`;
- preserve protected phases: `listening`, `waiting_voice`, `speaking`.

### Fix C: Audio Retry

Failed audio jobs must be retryable after network recovery.

Add:

- `POST /api/audio/jobs/{job_id}/retry`;
- retry only for terminal failed/expired jobs;
- new job uses old text and voice style;
- frontend retry button polls the new job id.

Old behavior of rechecking the same failed job is insufficient.

### Fix D: Audio Error Classification

Do not show only "声音刚刚没出来" for every audio failure.

Frontend should map safe error classes to user copy:

- network/provider connection: "网络刚刚没连上，豆豆发不出声音。";
- timeout: "声音生成太慢了，等一下再试。";
- auth/quota/config: "发声服务配置可能有问题。";
- playback failure: "声音生成了，但浏览器没播出来。";
- unknown: generic fallback.

Backend may add `error_class` to audio job responses to avoid parsing raw
strings in the frontend.

### Fix E: Type Contract

Frontend response types must include:

- `behavior_intent`;
- `behavior_plan`;
- fast reply `action` if exposed directly by backend;
- audio job `error_class` if added.

### Fix F: V1.2 Stage Documentation

`plan/V1.2/stages/stage-5-hardening-completion.md` is currently untracked.
Before final V1.3 completion, either commit it or intentionally remove it.

## API/Backend Shape

### Route Policy

Update route policy:

- default text/voice route: `fast_reply`;
- thinking toggle route: `thinking`;
- remove or disable tool route for V1.3;
- complex keywords should produce a fast suggestion to use Thinking Mode rather
  than automatically loading tools or retrieval.

Do not keep legacy route names like `tool` and `long_task` as active V1.3 prompt
profiles unless they are internally mapped to `fast_reply` or `thinking` with
tools disabled.

### Prompt Builders

Introduce separate prompt builders:

- `build_fast_reply_messages(...)`;
- `build_thinking_messages(...)`;
- `build_memory_judgment_messages(...)`;
- `build_nightly_memory_cleanup_messages(...)`.

Do not use the full `OUTPUT_SCHEMA_HINT` for Fast Reply.

Prompt payload requirements:

- Fast Reply payload contains only current input, latest 1 turn, light pet
  state, selected card items, and minimal response schema.
- Thinking payload contains current input, latest 6 turns, pet state, selected
  card items, and the full or near-full response schema.
- Neither Fast Reply nor Thinking payload includes current time, device state,
  skill results, retrieved memories, summaries, daily digest, or quotes.
- If old `RuntimeContext` still carries these fields, the V1.3 serializer must
  omit them.

### Context Manager

Replace dynamic retrieval-oriented context with card-only context selection.
The implementation may keep old classes temporarily, but prompt output must not
include retrieval fields in V1.3.

Suggested context profiles:

- `fast_reply`;
- `thinking`;
- `proactive`;
- `local_reaction`;

Fast/proactive profiles must be card-only and tiny.

The old dynamic context code can remain behind explicit debug/maintenance calls,
but `dispatcher.handle_event()` for user-visible text/voice must not call:

- `memory_manager.scored_memories`;
- `memory_manager.important_quotes`;
- `event_log_store.recall_events`;
- `episode_summary_store.recent`;
- `daily_summary_store.recent`.

### Memory Manager

Add or refactor a card memory manager that can:

- parse `user.md` and `memory.md`;
- select deterministic items for Fast Reply and Thinking Mode;
- append validated memory lines;
- perform locked atomic rewrite;
- run nightly cleanup operations.

The manager must own canonical notebook files directly. Legacy SQLite-backed
card rebuilds must not overwrite them after migration.

### Request Idempotency

Fast Reply must not create duplicate model/audio work because the old WebView
or fetch/XHR times out.

Preferred V1.3 behavior:

- add a client-generated `request_id` to text and voice submits;
- backend stores a short-lived response cache by `request_id` and returns the
  same run/audio job for duplicate submits;
- frontend does not auto-retry chat POSTs without `request_id`;
- audio polling remains retryable because it is a GET.

If request idempotency is deferred, disable automatic retries for chat/voice
POSTs in the first implementation stage.

## Frontend Behavior

V1.3 should move the UI closer to a small cat desktop pet, not a debug console
or generic chat app. Detailed visual polish can be iterated later, but the
first V1.3 frontend pass must fix the current layout and interaction problems.

### Desktop Pet Layout

Default first screen:

```text
[ Doudou sprite main stage ]
        short bubble

[ text input........................ ][send]
[ mic ][thinking toggle][more]

[ intimacy ][energy ][mood ]
```

Required changes:

- Remove the large central `豆豆` title from the main stage. 豆豆 should be
  visible as the sprite, not repeated as oversized text.
- Make the sprite the first visual focus and give it stable stage space.
- Keep bubbles short and close to the sprite. They should feel like pet
  reactions, not system logs.
- Move `亲密 / 活力 / 心情` below the main controls as low-priority status
  chips or a compact status strip.
- Keep the text input at the bottom and place the send button at the far right.
- Normalize button heights and widths where appropriate. The current mixed
  button sizing should be treated as a bug.
- Keep Thinking Mode as a small toggle/control, not a dominant primary action.
- Keep More/Interactions behind a compact button or bottom drawer.
- Do not show a large grid of interaction buttons on the default surface.

### Voice Interaction

The current long-press-to-record interaction is not reliable enough on the old
Android/WebView target. It can feel delayed, accidental, and hard to interrupt.

V1.3 should replace long press with tap-to-record:

1. Tap microphone once to start recording.
2. While recording, the mic button enters an obvious active state and copy
   changes to "说完点这里" or equivalent.
3. Tap the active mic again to stop recording and send.
4. Show a small cancel affordance while recording to discard the current audio.
5. If 豆豆 is currently speaking, tapping mic should stop current playback before
   starting a new recording.
6. Recording start sets sprite to `waiting`.
7. Recording stop/upload sets sprite to `review`.
8. Failed or cancelled recording returns to the previous safe state without a
   scary error.

The goal is not to add more controls. The goal is to make voice input
predictable and interruptible.

Detailed voice state rules:

- `idle`: mic tap starts a new recording immediately.
- `listening`: mic tap stops recording and uploads; cancel discards the blob.
- `thinking` or upload in progress: cancel only ignores the eventual frontend
  response unless backend cancellation exists.
- `waiting_voice`: mic tap invalidates the current audio run locally before
  recording.
- `speaking`: mic tap stops the current `Audio` element immediately before
  recording.
- `audio_error`: retry button retries TTS; mic tap starts a new utterance.

Fast voice should not use heavy fallback. If ASR fails in Fast Reply Mode, 豆豆
should show a local "没听清" recovery and let the user retry. Audio-understanding
fallback is reserved for explicit Thinking Mode.

### UI Boundaries

V1.3 frontend work should not become a broad visual redesign before the fast
reply architecture is implemented.

In scope:

- remove oversized title;
- make sprite stage dominant;
- normalize button sizing;
- move status chips lower;
- fix send button placement;
- convert voice to tap-to-record;
- keep More as a secondary drawer/control;
- ensure text does not overflow on Nubia screen sizes.

Out of scope for this spec:

- new illustrations or non-sprite pet assets;
- game-like inventory/level/collection systems;
- full chat transcript UI;
- marketing/landing-page style hero layout;
- external tool panels;
- complex animation editor/debug controls.

### Behavior Rules

Frontend behavior must follow:

- default UI uses Fast Reply;
- Thinking Mode is visible as an intentional slower mode;
- local sprite reaction happens immediately;
- Fast Reply uses one action/mood;
- Thinking Mode can show `review` longer and use richer behavior plan;
- failure copy should be specific enough to guide the user without exposing raw
  provider errors.

## Testing Requirements

### Backend Unit Tests

- Fast Reply prompt excludes retrieval fields and full schema.
- Thinking prompt uses card memory only.
- Dynamic retrieval functions are not called in Fast/Thinking prompt paths.
- Route policy maps Thinking Mode to `thinking` with `allow_tools=false`.
- Tool/weather/code keywords do not enable tools in V1.3 Fast Reply.
- Legacy `long_task` prompt tests are updated or removed.
- Memory trigger rules enqueue background job without blocking response.
- Memory judgment validates target/category/content and adds system timestamp.
- Memory judgment queue enforces pending/running limits.
- Nightly cleanup applies add/update/delete safely.
- Nightly cleanup skips under active response, provider backpressure, or
  unhealthy runtime.
- Memory file writes are locked and atomic.
- Audio retry creates a new job from failed job metadata.
- Audio job responses include safe `error_class`.
- Chat/voice POST retries are idempotent or disabled.
- Lightweight tap endpoint, if implemented, does not call LLM/TTS.

### Frontend Unit Tests

- Sprite tap does not call `/api/pet/event`.
- More/TouchArea local interactions do not call `/api/pet/event` unless marked
  `requires_model=true`.
- Fast Reply response with `action` updates sprite.
- Thinking behavior plan advances through slots.
- Audio retry uses new retry endpoint for failed jobs.
- Audio error class maps to correct user copy.
- Mic tap starts recording; second tap sends; cancel discards.
- Mic tap during `speaking` stops current audio and starts recording.
- Mic is not disabled during `speaking` or `waiting_voice`.
- Chat/voice submit does not silently duplicate POSTs on timeout.
- Protected phases are not interrupted by ambient/tap/plans.

Old tests that assert long-press voice labels or auto tool/long_task routing
must be rewritten to the new behavior.

### Nubia Smoke Tests

- Fast text greeting returns quickly and enqueues short TTS.
- Fast voice greeting feels responsive.
- Fast voice ASR failure does not trigger slow audio-understanding fallback.
- Repeated sprite tapping creates no audio jobs.
- Disconnect Wi-Fi, trigger TTS failure, reconnect, retry audio successfully.
- Fast Reply still includes limited card memory.
- Thinking Mode loads more card memory but no retrieval fields.
- During/after nightly cleanup, `127.0.0.1:8000` remains reachable.
- Service manager treats process-alive/port-down as unhealthy and recovers.

## Success Metrics

User experience targets:

- local sprite reaction: < 100ms;
- Fast Reply LLM response target: < 2s, ideal < 1.5s;
- Fast Reply text length: normally <= 80 Chinese characters;
- Fast TTS target: < 4s for short replies;
- no generic "no context" wording in normal UX;
- no hidden LLM/TTS work from ordinary sprite taps;
- user can understand why Thinking Mode is slower.

Engineering targets:

- no dynamic memory retrieval in prompt paths;
- card memory reads are deterministic and cheap;
- background memory writes never block current reply;
- background memory queue is bounded;
- audio retry works after network recovery;
- non-idempotent request retries do not duplicate LLM/TTS work;
- type contracts cover behavior/action fields;
- test suite covers mode boundaries.

## Suggested Implementation Stages

V1.3 has 6 implementation stages. Each stage is a separate commit boundary and
must include its own stage plan, pre-implementation review, implementation,
tests, completion review, fixes if needed, and stage completion record.

### Stage Execution Protocol

Every stage must follow this protocol:

1. **Write the stage plan first.**
   - Save it under `plan/V1.3/stages/stage-N-<short-name>.md`.
   - The plan must list exact files expected to change, API/type contracts,
     tests to add/update, Nubia constraints, and acceptance checks.
   - The plan must include rollback/compatibility notes for any changed route,
     prompt, memory, audio, or frontend state behavior.

2. **Run a pre-implementation subagent review.**
   - Open a subagent to review the stage plan against this V1.3 spec, the
     current codebase, Nubia constraints, and existing tests.
   - The review must specifically look for incompatibilities, unreasonable
     scope, missing boundary cases, and tests that will conflict with the plan.
   - The review result must be `PASS` or `FIX`.
   - Save notes under
     `plan/V1.3/stages/stage-N-<short-name>-pre-review.md`.
   - If the result is `FIX`, update the stage plan and repeat review until it
     passes or the issue is explicitly recorded as deferred.

3. **Implement only the reviewed stage scope.**
   - Do not pull work from later stages unless the reviewed plan is updated and
     re-reviewed.
   - Do not leave unrelated refactors in the stage commit.
   - Preserve compatibility aliases called out in this spec unless the stage plan
     explicitly removes them.

4. **Run the stage's acceptance plan.**
   - Run the exact backend/frontend/unit/live tests listed for that stage.
   - If a Nubia live check is required and the device is unavailable, record the
     deferral and the exact smoke command/check that must be run later.
   - Save important outputs or summaries in the completion document.

5. **Run a completion subagent review.**
   - Open a subagent to review the implemented diff against the stage plan, this
     spec, project code patterns, tests, and Nubia constraints.
   - The review must return `PASS` or `FIX`.
   - Save notes under
     `plan/V1.3/stages/stage-N-<short-name>-completion-review.md`.
   - If the review returns `FIX`, repair the issue, rerun relevant tests, and
     repeat completion review until it passes or an explicit deferral is
     recorded.

6. **Write the stage completion record.**
   - Save it under `plan/V1.3/stages/stage-N-<short-name>-completion.md`.
   - Include files changed, behavior changed, tests run, skipped checks,
     remaining risks, and Nubia verification status.

7. **Commit and push the stage.**
   - Commit only the stage changes and its plan/review/completion artifacts.
   - Push after the stage commit passes review.

Subagent reviews must not use `ccb`. Use the available subagent tooling in the
current session. Review prompts should include concrete file paths and ask the
subagent to inspect both the spec and relevant code.

### Stage 1: Fast Reply Contract

- Add minimal Fast Reply response model.
- Add `build_fast_reply_messages`.
- Add card-only fast context selection.
- Route default text/voice companion messages to Fast Reply.
- Keep old Thinking path intact for fallback.
- Disable or remap legacy `tool`/`long_task` route behavior for V1.3.
- Disable heavy voice fallback for Fast Reply Mode.

Acceptance plan:

- Backend tests prove default text/voice routes use `fast_reply`.
- Thinking toggle maps to `thinking` with `allow_tools=false`.
- Weather/device/code keywords do not enable tools or `long_task`.
- Fast Reply prompt payload excludes current time, device state, skill results,
  dynamic retrieval fields, and full output schema.
- Fast voice ASR failure returns a local recovery instead of slow
  audio-understanding fallback.
- Existing route/prompt tests that assert old tool/long_task behavior are
  updated or removed.

### Stage 2: Card-Only Memory

- Disable prompt-time dynamic retrieval.
- Add deterministic card parser/selector.
- Migrate canonical notebook files and prevent legacy rebuild overwrite.
- Add memory trigger rules.
- Add background memory judgment and atomic append.
- Add bounded memory judgment queue.

Acceptance plan:

- Fast Reply selects at most one relevant `user.md` item and one relevant
  `memory.md` item without an LLM call.
- Thinking Mode selects bounded card context only.
- Prompt paths do not call `scored_memories`, `important_quotes`,
  `recall_events`, `episode_summary_store.recent`, or
  `daily_summary_store.recent`.
- Canonical `user.md` and `memory.md` are not overwritten by legacy
  SQLite-backed card rebuilds.
- Memory trigger jobs are queued in the background, bounded, deduplicated, and
  non-blocking.
- Memory writes use backend timestamps, whitelist target/category, reject unsafe
  content, and write atomically.

### Stage 3: Nightly Memory Cleanup

- Add midnight scheduler or maintenance worker hook.
- Add cleanup prompt and operation validation.
- Add aging/merge/delete application.
- Add backups and tests.
- Add Nubia safety gates: active-response skip, provider-backpressure skip,
  bounded log reads, timeout, and no WAL checkpoint coupling.

Acceptance plan:

- Cleanup runs at most once per local day.
- Cleanup reads bounded conversation history plus `user.md` / `memory.md` only.
- Current local date/time is included only in the cleanup prompt, not in
  Fast/Thinking prompts.
- Cleanup skips during active responses, provider backpressure, or degraded
  runtime health.
- Add/update/delete operations are validated before applying.
- Backup/atomic rewrite/restore path is tested.
- Nubia smoke confirms `127.0.0.1:8000` remains reachable during/after cleanup.

### Stage 4: UX Recovery Fixes

- Remove sprite tap slow path.
- Convert More/TouchArea interactions to local deterministic behavior unless
  explicitly model-backed.
- Add audio retry endpoint.
- Add audio error classification.
- Complete frontend response types.
- Make chat/voice POST retry idempotent or disable automatic POST retries.

Acceptance plan:

- Sprite tap and default More interactions do not call `/api/pet/event` and do
  not create audio jobs.
- Any model-backed interaction is explicitly marked and tested.
- Failed/expired audio jobs retry through `POST /api/audio/jobs/{job_id}/retry`
  and return a new job id.
- Audio job responses expose safe `error_class`; frontend copy maps network,
  timeout, auth/quota/config, playback, and unknown failures.
- Frontend `PetResponse`/`AudioJob` types include behavior/action/error fields.
- Chat/voice POST retry policy cannot duplicate LLM/TTS work.

### Stage 5: Behavior Slot Execution

- Wire single Fast Reply action.
- Wire Thinking `behavior_plan` slots to phase boundaries.
- Add protected-phase tests.

Acceptance plan:

- Fast Reply `action` is whitelisted and updates the sprite immediately.
- Missing/invalid `action` falls back deterministically.
- Thinking `behavior_plan` advances through `before_speech`, `speech`,
  `after_speech`, and `idle_after` at real phase boundaries.
- Protected phases `listening`, `waiting_voice`, and `speaking` remain
  authoritative.
- Frontend no longer needs unsafe casts for behavior fields.

### Stage 6: Nubia Verification

- Deploy to Nubia.
- Run targeted fast reply, memory, tap, retry, and Thinking smoke tests.
- Verify service health detects port-down even if Python process is alive.
- Record results in `plan/V1.3/stages/`.

Acceptance plan:

- A fast text greeting shows visible reaction immediately, returns short text,
  and enqueues short TTS.
- A fast voice greeting uses ASR + Fast Reply and does not trigger heavy fallback
  on ASR failure.
- Repeated taps create no LLM/TTS/audio jobs.
- Disconnect network, trigger TTS failure, reconnect, retry audio, and confirm
  audio becomes ready.
- Fast Reply includes limited card memory; Thinking includes more card memory
  but no dynamic retrieval fields.
- Service manager or health checks classify process-alive/port-down as
  unhealthy and recover.
- Record exact adb commands, backend/frontend versions, skipped checks, and
  final pass/fail count.
