# PetAgent V1.4: Living Doudou, Action Expansion, And Single Notebook Spec

**Date:** 2026-05-29
**Project path:** `/Users/wylam/Documents/workspace/Petagent`
**Runtime target:** Nubia Android phone, Termux FastAPI backend on
`127.0.0.1:8000`, React/Vite frontend served by backend WebView.

## Goal

V1.4 makes 豆豆 feel like a living desktop pet, not just a chat bubble with a
sprite. Fast conversations must visibly move 豆豆, idle time should show 豆豆
living its own small life, and quick memory should feel present without making
the default path slow.

V1.4 also changes the memory product model from split files to one visible
notebook, and introduces after-turn background memory summarization. The user
experience rule is strict: visible response and voice playback must not wait for
memory work.

All new V1.4 issues and generated asset experiments live under:

```text
plan/V1.4/
```

Do not mix V1.4 issues into V1.3 docs unless a stage explicitly needs a
backward-compatibility note.

## Product Principles

1. **豆豆 is alive before 豆豆 is useful.** A fast reply should show a pet
   reaction, not only text and loading state.
2. **豆豆 has a personality.** It is playful, slightly mischievous, and lazy,
   but not unreliable when the user needs warmth.
3. **Comfort overrides attitude.** If the user is sad, anxious, tired, or asks
   for comfort, 豆豆 must immediately become attentive and warm.
4. **Fast mode should not feel dumb.** It may be short, but it should use enough
   notebook memory to feel personal.
5. **Slow work is background work.** Memory summarization, asset generation,
   and cleanup must not block text response, TTS enqueue, audio polling, or
   frontend interaction.
6. **Nubia is the real target.** Local tests are not enough. Completion requires
   deployment and live API verification on the connected Nubia phone.

## Non-Goals

- Do not add weather/tools back into V1.4.
- Do not integrate realtime speech-to-speech APIs.
- Do not let MiMo participate in fast reply, ASR, TTS, tool use, or foreground
  chat response generation. MiMo is only for background memory summarization.
- Do not use generated image experiments as production assets until their cell
  size, transparency, identity consistency, and Nubia performance are verified.
- Do not hard-code API keys in source, spec, tests, scripts, or committed files.

## Current Project Context

### Frontend

Key files:

- `frontend/src/pet/doudouSprites.ts`
- `frontend/src/components/DoudouSprite.tsx`
- `frontend/src/pet/behaviorDirector.ts`
- `frontend/src/pet/doudouBehaviorPlan.ts`
- `frontend/src/App.tsx`
- `frontend/src/pet/types.ts`

Current sprite atlas:

- `1536x1872`;
- `8` columns x `9` rows;
- `192x208` cell;
- existing actions:
  - `idle`
  - `waiting`
  - `review`
  - `waving`
  - `jumping`
  - `failed`
  - `running`
  - `running-left`
  - `running-right`

Current issue: Fast Reply can return `action`, and
`BehaviorDirector.onBackendResponse()` prioritizes it, but `App.applyPetResponse()`
immediately enters `waiting_voice` when an audio job exists. `waiting_voice` and
`speaking` then force phase actions such as `review`, so the fast action is not
visible long enough for the user to perceive it.

### Backend

Key files:

- `backend/app/runtime/dispatcher.py`
- `backend/app/runtime/actions.py`
- `backend/app/runtime/context_manager.py`
- `backend/app/runtime/notebook.py`
- `backend/app/runtime/memory_judgment.py`
- `backend/app/runtime/nightly_cleanup.py`
- `backend/app/pet/prompt_builder.py`
- `backend/app/pet/guard.py`
- `config/app.yaml`
- `config/models.yaml`

V1.3 already introduced:

- `fast_reply` route;
- `FastReplyAction`;
- fast response `action`;
- `NotebookManager` for `user.md` and `memory.md`;
- memory trigger queue;
- nightly cleanup;
- thinking mode without tools/retrieval.

V1.4 builds on this, but changes the notebook product model and action
vocabulary.

## Doudou Character Definition

豆豆 is a playful desktop cat that lives in the phone.

Daily behavior:

- 豆豆 likes to slack off when the user is away.
- It may secretly eat snacks, nap, watch TV, groom itself, or wander around.
- It may act slightly guilty or annoyed when interrupted.
- It should not feel like a customer-service assistant waiting silently.

Relationship behavior:

- 豆豆 is familiar with the user.
- It may tease, act proud, pretend to be busy, or make small excuses.
- It can refuse lightly when over-poked or interrupted, but not harshly.

Comfort behavior:

- If the user expresses sadness, fatigue, anxiety, stress, loneliness, or asks
  for comfort, 豆豆 must drop the lazy/teasing persona.
- It should switch to `listen` or `comfort`, reply warmly, and avoid sarcasm,
  laziness jokes, guilt-tripping, or refusal.

Fast mode behavior:

- Fast mode means "豆豆先马上回应你", not "豆豆变笨".
- The answer may be short, but the action must carry emotional feedback.

## Action Vocabulary

### Existing Compatibility Actions

Keep existing actions until the new atlas and mappings are fully deployed:

```text
idle, waiting, review, waving, jumping, failed, running, running-left, running-right
```

These may remain as fallbacks and legacy aliases.

### V1.4 Product Actions

V1.4 introduces product-level action names. They may initially map to legacy
sprite rows while new art is generated.

| Action | Meaning | Primary use |
| --- | --- | --- |
| `idle` | calm breathing | default |
| `lazy_idle` | lazy lounging | user away, light idle |
| `nap` | dozing / sleeping | long idle, night, low energy |
| `sneak_eat` | secretly eating | long idle autonomous behavior |
| `watch_tv` | watching something | long idle autonomous behavior |
| `self_groom` | grooming | autonomous calm behavior |
| `wander` | small walkabout | autonomous life behavior |
| `greet` | greeting | "早上好", "在吗", wake |
| `happy` | pleased | praise, agreement, light joy |
| `tease` | playful / mischievous | jokes, guilty excuses |
| `pretend_busy` | pretending to work | interrupted TV/laziness |
| `listen` | attentive listening | recording, emotional talk |
| `think` | quick thought | short wait |
| `speak` | talking | audio playback |
| `remember` | notebook write | explicit memory request |
| `comfort` | warm support | sadness, fatigue, anxiety |
| `confused` | unsure / did not hear | ASR or comprehension failure |
| `deny` | small refusal | overpoke, interrupted nap |
| `excited` | high positive energy | good news |

### First Production Batch

First implementation should expose these product actions even if some are
mapped to existing sprite rows:

```text
idle
lazy_idle
nap
sneak_eat
watch_tv
greet
happy
tease
listen
speak
remember
comfort
confused
```

Do not block V1.4 implementation on final art for every action. Product actions
can be introduced as semantic names first, with a fallback map to existing rows.

### Action Safety Rules

- `comfort` and `listen` override `lazy_idle`, `tease`, `deny`, `sneak_eat`,
  and `watch_tv` when user distress is detected.
- `remember` only appears for explicit memory triggers such as "记住",
  "别忘了", "写进小本本", or equivalent.
- `deny` is never used for user distress or genuine help requests.
- `speak` is the default visual during audio playback if no stronger
  behavior-plan slot is active.
- `confused` is used for ASR low confidence, failed parsing, or "没听清".

## Fast Reply Action Rendering

### Problem

Fast Reply already returns `action`, but the frontend often overwrites it with
phase actions when TTS is enqueued. The user sees `review` or static waiting
instead of a meaningful reaction.

### Required Behavior

When a Fast Reply response arrives:

1. show the reply bubble immediately;
2. apply the fast `action` immediately;
3. if audio is queued, preserve the action for a minimum visible duration unless
   the action is incompatible with the phase;
4. switch to `speak` when playback starts, unless a behavior slot provides a
   more specific action;
5. return to idle/autonomous behavior after playback ends.

Recommended minimum visible duration:

```text
600ms
```

This duration should not delay text display or backend polling. It may delay
the visual phase transition only. If audio becomes ready sooner, playback can
start while the action remains visible, then switch to `speak`.

### Phase Mapping

Replace broad `review` fallback with phase-aware product actions:

| UI phase | Default product action |
| --- | --- |
| `idle` | `idle` or current autonomous action |
| `listening` | `listen` |
| `thinking` | `think` |
| `waiting_voice` | keep fast action until min duration, then `think` |
| `speaking` | `speak` |
| `audio_error` | `confused` |
| `error` | `confused` |

## Autonomous Idle Life

### Goal

When the user ignores 豆豆 for a long time, 豆豆 should visibly do its own small
life activities.

### Idle Activities

| Activity | Product action | User-facing reaction when interrupted |
| --- | --- | --- |
| lazy lounging | `lazy_idle` | "我刚刚在看家。" |
| nap | `nap` | sleepy/confused greeting |
| sneak eating | `sneak_eat` | guilty/teasing denial |
| watch TV | `watch_tv` | pretend-busy / mildly interrupted |
| grooming | `self_groom` | normal calm response |
| wandering | `wander` | happy return |

### Timing

Keep Nubia modest:

- existing ambient tick can remain at 5 seconds;
- first autonomous activity should not start immediately after user input;
- suggested idle threshold: 60-180 seconds for visible life activity;
- longer idle threshold: 5-15 minutes for stronger states such as `nap`,
  `sneak_eat`, or `watch_tv`;
- randomize activity choice, but keep deterministic guardrails for tests.

### Runtime State

Frontend or backend may track lightweight volatile state:

```text
last_idle_activity = lazy_idle | nap | sneak_eat | watch_tv | self_groom | wander
last_idle_activity_at
```

This is not long-term memory. It should not be written into `memory.md` unless
the user explicitly discusses it and the memory summarizer decides it matters.

### Interruption Rules

When the user returns:

- if prior activity was `nap`, first reaction may be sleepy/confused;
- if prior activity was `sneak_eat`, first reaction may be guilty/teasing;
- if prior activity was `watch_tv`, first reaction may be pretend-busy;
- if prior activity was `wander`, first reaction may be happy/greet;
- if user distress is detected, ignore idle activity and use `listen/comfort`.

## Memory Model

### Direction

V1.4 moves toward one canonical user-facing notebook:

```text
backend/data/memory_cards/memory.md
```

`user.md` should be deprecated as a prompt source. Implementation may keep
compatibility support for one release, but new prompt selection and memory
summarization should treat `memory.md` as canonical.

### Categories

The single file uses categories to replace the old file split:

```text
identity
preference
relationship
project
temporary
```

Line format remains:

```md
- [YYYY-MM-DD HH:mm][category] content
```

The backend writes timestamps. Models must not write timestamps.

### Migration

On first V1.4 startup or migration command:

1. parse existing `user.md`;
2. parse existing `memory.md`;
3. merge into canonical `memory.md`;
4. preserve existing lines where possible;
5. deduplicate exact and near-exact content;
6. backup old files before rewrite;
7. leave `user.md` either as a compatibility stub or archived backup.

No legacy SQLite memory projection may overwrite canonical `memory.md`.

### Fast Prompt Memory Selection

Fast Reply should load up to 10 short memory lines from canonical `memory.md`.

Suggested budget:

- up to 2 `identity`;
- up to 3 `preference`;
- up to 3 `relationship/project`;
- up to 2 fresh `temporary`;
- total prompt memory budget: 600-800 Chinese characters.

Fast mode must still not load:

- current time;
- device state;
- dynamic retrieval;
- SQLite scored memories;
- event summaries;
- daily digest;
- tools.

### Thinking Memory Selection

Thinking Mode remains explicit. It may load more notebook lines, but still only
from canonical `memory.md`.

Suggested budget:

- up to 20 lines;
- priority: `identity`, `preference`, `relationship`, `project`, fresh
  `temporary`;
- total budget should remain bounded for Nubia performance.

## After-Turn Memory Summarization

### Provider Boundary

MiMo is used only for background memory summarization.

Allowed:

- after-turn memory summarization;
- nightly memory cleanup if already using MiMo-compatible slow provider and
  gated by maintenance.

Forbidden:

- Fast Reply generation;
- Thinking chat response generation;
- ASR;
- TTS;
- frontend action selection;
- tools;
- foreground API calls that block current user response.

### Provider Config

Use environment variables, not hard-coded secrets:

```text
MIMO_BASE_URL=https://api.xiaomimimo.com/v1
MIMO_API_KEY=...
MIMO_MEMORY_MODEL=mimo-v2.5
```

Existing `config/models.yaml` may already define MiMo fallback providers. V1.4
should add or reuse a dedicated memory-summarizer provider profile so that
changing memory summarization does not affect ASR/TTS/chat.

### Trigger Policy

V1.4 changes from trigger-only memory judgment to after-turn summarization:

- every completed text or voice conversation turn may enqueue a memory summary
  job;
- explicit memory triggers should be prioritized;
- queue must be bounded;
- duplicate recent user inputs should be deduplicated;
- summarization must run outside dispatcher locks and notebook locks;
- current reply and TTS enqueue must complete before summarization starts.

### Summary Input

Inputs to the summarizer:

- latest user text;
- latest 豆豆 reply;
- route (`fast_reply` or `thinking`);
- optional current selected memory hints;
- current canonical `memory.md` content, bounded;
- trigger metadata if present.

Do not include:

- API keys;
- raw provider errors;
- full database dumps;
- current device state;
- current time for normal after-turn summarization.

### Summary Output

The model proposes operations, not file text:

```json
{
  "add": [
    {
      "category": "preference",
      "content": "主人希望豆豆快速回应，但不要显得变笨。"
    }
  ],
  "update": [
    {
      "old": "- [2026-05-29 10:00][project] 主人在调豆豆。",
      "new_category": "project",
      "new_content": "主人在调 PetAgent V1.4，重点是动作、记忆和体验。"
    }
  ],
  "delete": [
    {
      "old": "- [2026-05-26 10:00][temporary] 主人今天有点忙。",
      "reason": "temporary expired or no longer useful"
    }
  ]
}
```

Backend validates:

- category whitelist;
- content length;
- no timestamp in model-provided content;
- no secrets/tokens/passwords;
- no long raw chat excerpts;
- no permanent negative labels;
- no identity deletion unless contradicted by newer explicit correction;
- dedupe before append.

### Disk Size And Prompt Size

The file may contain more than 10 total lines, but fast prompt selection loads
at most 10. Nightly cleanup can compact older items.

If user prefers strict 10-line disk file later, define that as a separate
policy. V1.4 first implementation should avoid destructive over-compaction.

## Image Generation And Asset Pipeline

### Current Experiment

Generated files and notes:

```text
plan/V1.4/generated/happy-generation-notes.md
plan/V1.4/generated/happy_chatgpt_web_actual.png
plan/V1.4/generated/happy_chatgpt_web_strip_1152x208.png
plan/V1.4/generated/happy_test_strip_local.png
```

Findings:

- ChatGPT web can generate a six-frame happy contact sheet when given a
  single-frame reference.
- `opencli chatgpt image` may return before the actual page image is ready.
  Correct workflow is to wait for the generated `<img>` and fetch its `src`.
- White background is poor for transparent extraction because 豆豆 is white.
- A pure chroma background is better for generated sprite rows.

### GPT Image Endpoint Probe

The user-provided OpenAI-compatible base URL model list contains:

```text
gpt-image-1
gpt-image-1.5
gpt-image-2
```

This was verified through `/v1/models`. No image generation call was made during
the probe. Single-model `/v1/models/{id}` returned 404, which may only mean the
proxy does not implement that detail endpoint.

### Asset Acceptance Criteria

Generated action art is not production-ready until:

- each frame is `192x208` or can be losslessly/predictably packed into that
  cell;
- background is transparent or cleanly removable;
- 豆豆 identity is consistent across frames;
- frame baseline and scale are stable;
- no text, watermark, props, or extra characters;
- WebP atlas remains small enough for Nubia;
- Playwright/browser screenshot confirms sprite is not blank.

## Claude Execution Protocol

### Intent

Claude can be used as an execution worker to reduce this session's token load.
The user has explicitly approved using Claude this way, but Claude should not
own planning, quality review, or final acceptance because its model quality may
be weaker.

### Command Pattern

For isolated tasks, prefer:

```bash
claude -p \
  --bare \
  --permission-mode bypassPermissions \
  --no-session-persistence \
  --output-format json \
  '<task>'
```

Do not apply artificial budget limits unless the user asks. For codebase tasks,
provide enough explicit context rather than relying on unknown implicit context.

### Context Policy

Use more context when it helps:

- project path;
- relevant spec path;
- relevant source files;
- test commands;
- target stage;
- ownership boundaries.

Use narrower context for isolated execution tasks:

- web checks;
- endpoint probes;
- small read-only investigations.

### Responsibility

Claude may execute assigned slices, but this agent remains responsible for:

- planning stages;
- reviewing all changes;
- running tests;
- fixing poor or incomplete Claude output;
- integrating patches;
- deploying to Nubia;
- running live API verification;
- committing and pushing only after verification passes.

If Claude execution is poor, incomplete, incompatible, or risky, this agent must
repair it locally rather than blindly accepting it.

### Stage Execution Protocol

For each implementation stage:

1. main agent writes or updates the stage plan;
2. main agent reviews the stage plan against project code and the V1.4 spec;
3. implementation proceeds, either locally or through Claude with explicit file
   ownership;
4. main agent reviews completion against the stage plan, code, and tests;
5. main agent fixes findings;
6. local tests run;
7. stage completion doc records changed files, tests, and open risks.

## Implementation Stages

### Stage 1: V1.4 Spec And Action Contract

Goal:

- finalize V1.4 spec;
- define product action enum and fallback mapping;
- update persona/action prompt constraints without changing runtime behavior
  beyond safe aliases.

Likely files:

- `config/pet_persona.yaml`
- `frontend/src/pet/doudouSprites.ts`
- `frontend/src/pet/doudouBehaviorPlan.ts`
- `backend/app/runtime/actions.py`
- `backend/app/pet/guard.py`
- tests for action whitelist and fallback.

Acceptance:

- product actions are documented and whitelisted;
- legacy actions still work;
- invalid actions are guarded to safe fallback;
- no frontend blank sprite if a new action lacks final art.

### Stage 2: Fast Action Rendering And Speaking Phase

Goal:

- make Fast Reply action visible;
- add `speak` phase behavior;
- avoid overwriting immediate fast action with `review`.

Likely files:

- `frontend/src/App.tsx`
- `frontend/src/pet/behaviorDirector.ts`
- `frontend/src/pet/types.ts`
- frontend tests.

Acceptance:

- fast response with `action=happy` visibly sets `happy`;
- audio job does not immediately erase fast action before minimum duration;
- `speaking` defaults to `speak`;
- `audio_error` defaults to `confused`;
- protected phase behavior remains interrupt-safe.

### Stage 3: Autonomous Idle Life

Goal:

- add idle activities such as `nap`, `sneak_eat`, and `watch_tv`;
- track volatile `last_idle_activity`;
- make return-from-idle reactions reflect the interrupted activity.

Likely files:

- `frontend/src/pet/behaviorDirector.ts`
- `frontend/src/App.tsx`
- optional small frontend helper for distress detection;
- frontend tests.

Acceptance:

- idle activities happen only after idle thresholds;
- no autonomous activity during listening, waiting_voice, speaking, or busy;
- user distress overrides idle personality;
- tests can use deterministic random injection or controlled time.

### Stage 4: Single Notebook Migration And Selection

Goal:

- make `memory.md` the canonical prompt notebook;
- merge `user.md` and `memory.md` safely;
- fast mode selects up to 10 lines.

Likely files:

- `backend/app/runtime/notebook.py`
- `backend/app/runtime/context_manager.py`
- `backend/app/pet/prompt_builder.py`
- `backend/app/main.py`
- `config/app.yaml`
- backend tests.

Acceptance:

- canonical prompt memory reads from `memory.md`;
- migration preserves and deduplicates old file content;
- fast prompt contains up to 10 selected lines within budget;
- thinking prompt uses bounded canonical notebook lines;
- legacy `MemoryCardManager.rebuild()` cannot overwrite canonical notebook.

### Stage 5: After-Turn MiMo Memory Summarization

Goal:

- enqueue background memory summarization after each completed conversation;
- use MiMo only for summarization;
- apply validated operations to `memory.md`.

Likely files:

- `backend/app/runtime/memory_judgment.py` or new
  `backend/app/runtime/memory_summary_queue.py`
- `backend/app/runtime/dispatcher.py`
- `backend/app/pet/prompt_builder.py`
- `backend/app/runtime/notebook.py`
- `backend/app/main.py`
- `config/models.yaml`
- backend tests.

Acceptance:

- current response and audio enqueue complete before summary job runs;
- queue is bounded and deduplicated;
- explicit memory triggers are prioritized;
- malformed model output is ignored safely;
- secrets and timestamps are rejected;
- MiMo config is isolated from chat/TTS/ASR providers;
- tests prove Fast Reply does not wait for summarization.

### Stage 6: Asset Pipeline Spike

Goal:

- define a repeatable asset generation path for new actions;
- generate or process `happy` as the first test asset;
- do not ship generated art unless quality passes.

Likely files:

- `plan/V1.4/generated/*`
- optional scripts under a non-runtime tooling path if needed;
- no production frontend asset replacement unless approved.

Acceptance:

- prompt template for action generation exists;
- generated result is saved and documented;
- if packed into sprite row, cell dimensions are verified;
- Playwright or local image inspection confirms nonblank frames;
- decision recorded: usable, needs redraw, or reject.

### Stage 7: Integration, Nubia Deployment, And Live API Verification

Goal:

- run full targeted local tests;
- deploy to Nubia;
- run real live API checks against the phone.

Required local checks:

```bash
npm --prefix frontend test -- --run
pytest backend/tests/test_fast_reply_contract.py \
  backend/tests/test_text_chat.py \
  backend/tests/test_voice_pipeline.py \
  backend/tests/test_notebook.py \
  backend/tests/test_nightly_cleanup.py \
  backend/tests/test_stage5_behavior.py
```

Adjust exact test list as implementation changes, but include action rendering,
memory selection, memory summarization, and voice/audio polling coverage.

Required Nubia flow:

1. deploy current project to Nubia;
2. restart Termux runtime cleanly;
3. verify `/api/health` reports the deployed commit hash;
4. run live text Fast Reply check;
5. run live memory trigger check;
6. poll audio job until `ready` or safe terminal state;
7. inspect response fields:
   - `route=fast_reply`;
   - meaningful `action`;
   - no leaked reasoning;
   - audio job does not block on SQLite;
   - memory summarization does not block response;
8. if voice upload path is available, run a live voice check;
9. record logs and results in V1.4 completion docs.

Completion requires Nubia live API success. Local-only passing tests are not
enough.

## Commit And Push Policy

After implementation:

- commit only after tests and Nubia live checks pass or after clearly
  documenting a user-approved exception;
- do not commit secrets or generated junk outputs that are not part of the
  intended record;
- push after commit if the user asked for end-to-end completion.

## Open Decisions Before Implementation

1. Whether to physically remove `user.md` in V1.4, or keep it as a compatibility
   stub for one release.
2. Whether first production action art should be generated via ChatGPT web,
   `gpt-image-2` API, or manual editing from the existing sprite.
3. Whether disk `memory.md` should eventually be capped to 10 lines, or only the
   fast prompt selection should be capped to 10 lines.
4. Whether autonomous idle state is purely frontend-local or partially persisted
   in backend runtime state.
