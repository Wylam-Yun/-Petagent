# PetAgent V1.5: Unified Context And Stable Memory Spec

**Date:** 2026-05-30
**Project path:** `/Users/wylam/Documents/workspace/Petagent`
**Runtime target:** Nubia Android phone, Termux FastAPI backend on
`127.0.0.1:8000`, React/Vite frontend served by backend WebView.

## Goal

V1.5 simplifies 豆豆's conversation and memory system for stability.

The user-facing product should no longer expose Thinking Mode, Recall Mode, or
other mode switches. Every successful chat turn should use the same context
shape:

```text
system prompt
+ current user input
+ latest 5 real dialogue turns
+ all 10 long-term memory lines from memory.md
+ current pet_state
+ output schema
```

Memory maintenance becomes low-frequency background work. It is triggered by
memory keywords or every 10 successful turns, and it only uses MiMo. If MiMo is
unavailable, memory writing is skipped or recorded as failed; it must never fall
back to SiliconFlow.

## Product Principles

1. **Stability first.** A failed helper path should fail quietly in the
   background, not destabilize the current reply.
2. **No user-facing modes.** 豆豆 should decide internally how much model work is
   needed. The frontend must not ask the user to choose Thinking Mode.
3. **One prompt shape.** Fast, slow, text, and voice-success replies use the same
   context contract so behavior is predictable.
4. **Local history is durable.** The backend keeps all successful history
   locally. It may archive or compact old records, but it must not silently
   delete history.
5. **Memory is small and curated.** `memory.md` is the only prompt-facing
   long-term memory file and contains at most 10 lines.
6. **ASR failure is terminal for that request.** ASR failure does not call LLM,
   does not call TTS, does not write dialogue history, and does not trigger
   memory summary.
7. **Invalid LLM output is terminal for that request.** If the LLM provider does
   not return a valid foreground reply, the backend must surface a structured
   failure instead of inventing a normal-looking fallback reply.

## Non-Goals

- Do not add a separate Recall Mode.
- Do not put all raw historical dialogue into every normal prompt.
- Do not make memory summarization synchronous with the current reply.
- Do not use SiliconFlow for memory summarization.
- Do not remove the `thinking_mode` API field immediately; keep it accepted for
  compatibility, but ignore it.
- Do not let frontend business APIs automatically retry POST chat requests.
  Provider retries happen inside the backend.

## Current Problems

### Frontend Mode Exposure

The frontend currently exposes `VoiceModeToggle` and sends `thinking_mode` with
text and voice requests. This makes users manage backend routing manually and
keeps old Thinking Mode assumptions visible in the UI.

### Fragmented Context Paths

The backend currently has `fast_reply`, `thinking`, and recall-like code paths.
Fast reply only injects the latest 1 turn into the prompt, while thinking uses a
different prompt shape. Recall keywords are detected in route policy, but the
true recall context is not actually activated consistently.

### Fallback Replies Hide Failures

The current guard layer can turn missing or invalid LLM output into a normal
reply such as "嗯嗯，豆豆在这儿。". This makes users believe the software is
working when the LLM actually failed or returned an unusable payload. V1.5 must
delete this user-visible fallback behavior for foreground chat.

### Session And Episode Confusion

The current `episode` rollover can close an episode after idle time. That is not
the desired product behavior. The user expects the same long-running local
session until manual reset.

### Memory Is Too Eager And Too Implicit

The current after-turn memory queue can be populated every successful user turn.
V1.5 should only trigger memory work when there is a reason:

- a memory keyword was detected;
- or 10 successful turns have accumulated since the last memory summary.

## Target Conversation Pipeline

### Text

```text
frontend text input
-> /api/text/chat
-> backend accepts thinking_mode but ignores it
-> dispatcher builds unified context
-> LLM generates text reply
-> response is returned and visible
-> raw_event_log records the successful turn
-> successful-turn counter increments
-> memory summary may be enqueued in the background
-> TTS job may run after text success
```

Text success counts as a successful turn once the backend has generated a valid
reply and the response body can be returned. TTS failure does not undo the
successful turn.

### Voice

```text
frontend records audio
-> /api/voice/chat
-> ASR provider call with backend retry policy
-> if ASR fails: return ok:false with error_class and stop
-> if ASR succeeds: use transcript as current user input
-> dispatcher builds unified context
-> LLM generates text reply
-> response is returned and visible
-> raw_event_log records the successful voice turn
-> successful-turn counter increments
-> memory summary may be enqueued in the background
-> TTS job may run after text success
```

ASR failure includes empty transcript, low confidence, timeout, provider error,
or provider exception. ASR failure does not count as a successful turn.

### Button Interactions

Button interactions can still produce model-backed replies. If a button
interaction successfully outputs a reply, it counts as a successful turn for the
10-turn memory summary trigger.

Button interactions do not enter the latest 5 real dialogue turns used for
normal chat context. They can still be stored in local history for observability
and future analysis.

## Unified Prompt Contract

Every foreground successful user chat uses:

```text
messages = [
  {"role": "system", "content": system_prompt},
  {"role": "user", "content": json_payload}
]
```

`system_prompt` comes from `config/pet_persona.yaml` and remains the top-level
persona and behavior contract.

`json_payload` contains:

```json
{
  "user_input": "current text or ASR transcript",
  "recent_dialogue": [
    {"user": "...", "pet": "...", "created_at": "..."}
  ],
  "long_term_memory": [
    "- [timestamp][category] memory content"
  ],
  "pet_state": {
    "mood": "idle",
    "energy": 72,
    "intimacy": 40,
    "sleepiness": 15
  },
  "response_schema": {}
}
```

### Recent Dialogue Rules

The latest 5 turns are selected from local history using these filters:

- include `text_message` turns with a successful pet reply;
- include `voice_message` turns only when ASR succeeded and a pet reply exists;
- exclude ASR failures;
- exclude wake and exit phrases;
- exclude proactive events;
- exclude pure frontend/UI state events;
- exclude button interactions from the prompt context, even though button
  successes count toward the 10-turn memory trigger.

### Long-Term Memory Rules

`memory.md` is the only prompt-facing memory source. It contains at most 10
memory lines. Every foreground prompt includes all current lines from
`memory.md`; there is no dynamic selection step.

If `memory.md` has fewer than 10 lines, include all existing lines. If it has
more than 10 because of migration or manual edits, the backend should clamp
prompt injection to 10 and the next memory maintenance pass should rewrite it
to at most 10.

## Internal Model Selection

The frontend no longer exposes Thinking Mode. The backend may still choose
between fast and slow LLM providers internally, but this must not change the
prompt contract.

Initial stable policy:

- default foreground chat uses the configured fast LLM provider;
- complex input may use the slow LLM provider internally;
- provider choice is recorded in runtime diagnostics;
- user-visible response shape stays the same.

`thinking_mode` remains accepted by `/api/text/chat` and `/api/voice/chat` for
old clients, but it is ignored.

## Session And Local History

The product session is long-running. It ends only when the user manually resets
豆豆 with "重新认识" or an equivalent reset action.

Implementation may keep internal `episode_id` for compatibility with existing
tables, but idle-time episode rollover must not affect the latest 5 dialogue
selection or the user's visible session continuity.

### History Durability

Successful turns are stored in local SQLite history. V1.5 must not silently
delete history to keep row counts low.

Allowed storage management:

- archive old rows to a local file or archive table;
- compact old rows into durable summaries while preserving that compaction
  happened;
- expose retention/archival actions explicitly in code and tests.

Disallowed storage management:

- deleting old raw history with no archive or trace;
- losing successful turn counters on restart;
- clearing history except during explicit runtime reset.

## Memory File Contract

Canonical file:

```text
backend/data/memory_cards/memory.md
```

`user.md` can exist for migration compatibility, but it is not prompt-facing.

### Line Format

The existing V1.4 line format remains acceptable:

```text
- [YYYY-MM-DD HH:MM][category] content
```

Allowed categories:

```text
identity, preference, relationship, project, temporary
```

### Size Limit

`memory.md` contains at most 10 lines. The memory summarizer rewrites the file
as a curated 10-line notebook, not an append-only log.

### Priority Rule

When the summarizer decides what to keep:

1. Current conversation evidence has the highest priority.
2. Existing `memory.md` items are second priority.
3. Older local history is lower priority and should only be used when it helps
   preserve important stable facts.

The model should preserve durable identity, preferences, relationship facts,
and active projects. It should remove stale temporary facts, duplicates, and
low-value chatter.

## Memory Summary Triggering

Memory summarization is background-only.

Triggers:

1. Memory keyword hit in user text.
2. Every 10 successful turns.

### Successful Turn Definition

Counts as 1 successful turn:

- text request with a valid pet text reply;
- ASR-success voice request with a valid pet text reply;
- model-backed button interaction with a valid pet text reply;
- TTS failure after a valid text reply.

Does not count:

- ASR failure;
- empty text request rejected before model call;
- LLM failure;
- invalid LLM JSON or missing/empty reply;
- guard-produced synthetic fallback replies;
- server busy response;
- wake phrase only;
- exit phrase only;
- proactive event;
- local-only visual state change.

### Persistent Counter

The successful-turn counter must be persisted in SQLite. The implementation
should be restart-safe and idempotent.

Recommended persisted fields:

```text
successful_turn_count_total
successful_turn_count_since_memory_summary
last_successful_turn_event_id
last_memory_summary_event_id
last_memory_summary_at
```

The exact schema can differ, but tests must prove:

- restart does not reset the count;
- one successful event increments once;
- repeated processing of the same event does not increment twice;
- a 10-turn trigger does not enqueue duplicate summary jobs.

### Keyword Triggering

Keyword detection is deterministic string matching. It is only a trigger; it
does not force a memory write.

The MiMo summarizer can still return "no change" if the input is not worth
remembering.

Keyword sets should include explicit memory phrases such as:

```text
记住, 你要记得, 帮我记, 别忘了, 以后记得, 记到小本本, 写进小本本
```

Preference and identity keywords can remain, but broad phrases such as "我是"
must be treated carefully. They may trigger the background summarizer, but the
backend must rely on MiMo plus validation to avoid writing junk.

## Memory Summarizer Provider

Memory summarization only uses MiMo:

```text
MIMO_BASE_URL
MIMO_API_KEY
MIMO_MEMORY_MODEL or default mimo-v2.5
```

It must not fall back to SiliconFlow.

If MiMo is unavailable:

- current reply remains successful;
- no memory file change is applied;
- the failure is logged;
- an unconfigured MiMo provider marks the memory job as skipped;
- a transient MiMo provider failure retries through the bounded provider retry
  policy, then marks the memory job failed;
- the system must not repeatedly retry the same failed job forever.

## Provider Retry Policy

Provider calls, not frontend business API calls, may retry up to 3 attempts.

Applies to:

- ASR provider calls;
- foreground LLM provider calls;
- TTS provider calls;
- MiMo memory summarizer calls.

Rules:

- retries are bounded;
- retry delay is short and preferably exponential with jitter;
- auth/configuration errors should not be retried repeatedly;
- a user's single request must remain one logical request;
- retries must not create duplicate history rows or duplicate memory jobs.

## Frontend Changes

Remove the visible Thinking Mode control from the main UI.

Remove the "换个话题" control from the main UI. V1.5 has one continuous local
session, so the new frontend should not expose a topic-refresh action.

Frontend request compatibility:

- new frontend does not send `thinking_mode` intentionally;
- old cached frontend may still send it;
- backend ignores it and returns normal unified responses.

Voice failure UI remains explicit:

- show a clear error bubble from `error_class`;
- do not show a fake pet reply;
- do not wait for TTS after ASR failure.

## Backend Component Changes

### Route Policy

Remove user-visible route semantics for thinking and recall.

The route policy can still label internal provider choice, but prompt context
selection should not branch into separate user-facing modes.

### Context Manager

Context manager should provide a unified foreground context:

- latest 5 qualifying dialogue turns from durable local history;
- all current `memory.md` lines up to 10;
- current time only if needed by existing prompt rules;
- pet state from the dispatcher snapshot.

The current recall-only temporal history path should not be used as a special
mode in V1.5.

### Prompt Builder

Prompt builder should have one foreground chat prompt shape for text and
ASR-success voice. It should preserve the system prompt and output schema.

### Guard And Reply Validation

The guard layer should validate and sanitize model output, not invent a reply.

Allowed guard behavior:

- parse a dict response;
- parse a JSON string response;
- trim overlong replies;
- strip leaked reasoning or internal prompt fields from an otherwise valid
  reply;
- normalize invalid enum fields such as mood, action, voice style, animation,
  or vibration.

Disallowed guard behavior:

- replacing missing provider output with a friendly fallback reply;
- replacing invalid JSON with a friendly fallback reply;
- replacing a missing or empty reply with a friendly fallback reply;
- treating a fully synthetic fallback reply as a successful turn.

If the provider returns no action, invalid JSON, or a payload with no usable
reply after sanitization, the foreground request fails with a structured
`error_class` such as `llm_invalid_output` or `llm_provider_error`. It does not
write `raw_event_log`, does not increment the successful-turn counter, does not
enqueue TTS, and does not trigger memory summary.

### Dispatcher

Dispatcher should:

- record successful turns once;
- increment persistent successful-turn counters;
- enqueue memory summary only on keyword trigger or 10-turn trigger;
- avoid memory enqueue on ASR failures or LLM failures;
- keep TTS failure independent from text-turn success.

### Notebook Manager

Notebook manager should support atomic overwrite of `memory.md` with a validated
list of at most 10 lines.

Validation should reject:

- invalid category;
- empty content;
- sensitive content;
- lines that exceed existing length limits;
- more than 10 output lines.

### Context Refresh API

The new frontend does not call `/api/context/refresh`.

For compatibility, the backend may keep the endpoint temporarily, but V1.5
requires that it does not close episodes, does not enqueue summaries, does not
write prompt-facing history, and does not affect latest-5 dialogue selection.
If no old client depends on it, the endpoint can be removed.

## API Compatibility

### `/api/text/chat`

Request may include:

```json
{"text": "...", "thinking_mode": true}
```

The backend ignores `thinking_mode`.

### `/api/voice/chat`

Request may include form field:

```text
thinking_mode=true
```

The backend ignores `thinking_mode`.

### Response Runtime Diagnostics

Responses may include internal diagnostics such as:

```json
{
  "runtime": {
    "provider": "siliconflow_fast",
    "context_profile": "unified",
    "recent_dialogue_count": 5,
    "memory_line_count": 10
  }
}
```

Diagnostic names can vary, but tests should assert the observable contract, not
private implementation details.

## Test Design

V1.5 must include focused tests for behavior, contracts, and Nubia runtime.

### Backend Unit Tests

#### Route And Compatibility

- `thinking_mode=True` on text request does not select old thinking prompt.
- `thinking_mode=True` on voice request does not select audio-understanding
  fallback route.
- recall keywords do not select a separate recall mode.
- internal provider selection can choose fast or slow provider without changing
  prompt payload shape.

#### Context Selection

- context includes exactly the latest 5 qualifying `text_message` and
  ASR-success `voice_message` turns.
- ASR failure events are absent from recent dialogue.
- wake and exit phrase events are absent from recent dialogue.
- proactive events are absent from recent dialogue.
- button interactions are absent from recent dialogue.
- button interaction success still counts for the 10-turn memory trigger.
- context selection crosses old episode boundaries and is not limited by a
  45-minute idle rollover.
- prompt includes all current `memory.md` lines when there are 0, 3, or 10
  lines.
- prompt clamps memory injection to 10 lines if a manual file edit creates more
  than 10 lines.
- system prompt is always present as the first message.

#### Successful Turn Counter

- text success increments the persistent counter once.
- ASR-success voice reply increments the counter once.
- button success increments the counter once.
- TTS failure after text success still increments the counter once.
- ASR failure does not increment the counter.
- LLM failure does not increment the counter.
- invalid LLM JSON, missing reply, empty reply, or guard-produced synthetic
  fallback replies do not increment the counter.
- duplicate processing of the same event id does not double increment.
- counter state survives app restart or store reinitialization.
- the 10th successful turn enqueues one memory summary job.
- the 20th successful turn enqueues a second memory summary job.
- repeated maintenance ticks do not enqueue duplicate summary jobs for the same
  trigger point.

#### Memory Triggering

- explicit keyword such as "记住" enqueues background summary.
- preference keyword can enqueue background summary.
- keyword trigger does not block the foreground response.
- non-keyword turns only enqueue on the 10-turn boundary.
- ASR failure with a keyword-like empty transcript does not enqueue summary.
- MiMo returning no changes leaves `memory.md` unchanged.

#### Memory File Rewrite

- summarizer output with 10 valid memories atomically rewrites `memory.md`.
- summarizer output with fewer than 10 valid memories rewrites to that smaller
  set.
- summarizer output with more than 10 lines is rejected; the previous file
  remains intact.
- invalid categories are rejected.
- empty or sensitive content is rejected.
- failed rewrite leaves the previous file intact.
- concurrent summary attempts do not corrupt the file.

#### Provider Retry

- transient ASR error retries up to 3 attempts and succeeds if a later attempt
  succeeds.
- transient foreground LLM error retries up to 3 attempts.
- transient TTS error retries up to 3 attempts.
- transient MiMo memory summarizer error retries up to 3 attempts.
- auth/configuration errors do not retry three expensive attempts.
- provider retry does not create duplicate event log rows.
- provider retry does not create duplicate memory jobs.
- memory summarizer without MiMo configuration does not call SiliconFlow.

#### History Durability

- successful raw history is retained after maintenance cleanup.
- cleanup no longer silently deletes raw history rows.
- if archival is implemented, archived rows remain recoverable or traceable.
- runtime reset explicitly clears history, state, counters, and `memory.md`.
- `/api/context/refresh`, if retained, does not close episodes, write
  prompt-facing history, enqueue summaries, or affect latest-5 context.

### Backend API Contract Tests

#### Text API

- `/api/text/chat` accepts old `thinking_mode` field and returns a normal
  response.
- response contains `user_text`, pet state, and no mode-specific frontend
  requirement.
- provider failure returns a structured error without incrementing successful
  turn count.
- invalid LLM output returns a structured error and does not show a friendly
  fallback reply.

#### Voice API

- `/api/voice/chat` accepts old `thinking_mode` form field and ignores it.
- ASR success returns `ok:true`, `user_text`, and normal pet response.
- ASR empty returns `ok:false`, `error_class:"asr_empty"`, no TTS job, no
  history write, no counter increment.
- ASR timeout/provider error returns explicit `error_class`.
- voice debug logging records ASR success/failure without changing the contract.

#### Memory API

- debug endpoint can show memory status without exposing secrets.
- manual reset clears the 10-line memory file through the existing reset
  contract.
- if a manual memory summary endpoint remains, it must require internal auth and
  must use MiMo-only provider policy.

### Frontend Tests

- `VoiceModeToggle` is no longer rendered in `App`.
- text submit no longer sends `thinking_mode` from new frontend code.
- voice upload no longer sends `thinking_mode` from new frontend code.
- the "换个话题" control is no longer rendered in `App`.
- old API type compatibility does not break tests that construct old responses.
- ASR failure response displays explicit error bubble and does not call
  `applyPetResponse`.
- ASR failure does not enter waiting voice or speaking phase.
- normal text and voice success still play TTS when an audio job is present.
- button interactions still work and show model-backed replies when required.

### Integration Tests

- full backend test suite passes locally.
- full frontend test suite passes locally.
- deploy to Nubia with frontend build.
- start service from Termux/SSH context, not adb/su context.
- verify `/api/health` on Nubia.
- verify served frontend opens on Nubia.
- send text chat and confirm response, history row, and turn counter increment.
- send voice chat with clear phrase and confirm ASR text, response, history row,
  and turn counter increment.
- send/produce ASR failure and confirm no history row, no counter increment, and
  explicit frontend error.
- complete 10 successful turns on Nubia and confirm one background memory
  summary attempt is logged.
- remove or invalidate MiMo config on a test run and confirm memory summary
  skips/fails without SiliconFlow call and without blocking chat.

## Acceptance Criteria

V1.5 is complete when:

- frontend no longer exposes Thinking Mode;
- frontend no longer exposes "换个话题";
- backend accepts but ignores `thinking_mode`;
- every foreground successful chat uses the unified prompt shape;
- invalid or missing LLM output fails explicitly instead of using a friendly
  fallback reply;
- latest dialogue context includes 5 qualifying turns when available;
- `memory.md` contains at most 10 prompt-facing memories and all are included in
  foreground prompts;
- no separate Recall Mode remains in routing behavior;
- local successful history is not silently deleted;
- memory summary is background-only and triggered only by keywords or every 10
  successful turns;
- memory summary uses MiMo only and never falls back to SiliconFlow;
- provider retries are bounded to 3 backend attempts;
- ASR failure remains explicit and terminal for that request;
- local tests and Nubia verification pass.

## Open Implementation Notes

- The exact SQLite table or key-value store for successful-turn counters can be
  chosen during implementation, as long as it is persistent and idempotent.
- Internal episode fields may remain for compatibility, but should not define
  product session boundaries.
- If history archival is implemented in V1.5, it needs its own small test set.
  If not implemented, cleanup must at least stop silently deleting successful
  raw history.
