# Momo Experience Speedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Momo 当前的体验问题：回复有截断感、声音播放偶发卡住、互动动作不够丰富、`energy/sleepiness` 语义重叠、文本输入入口需要完善、默认对话耗时过长。

**Architecture:** 保持现有 FastAPI runtime + React/PWA 前端结构，不重写 Stage 3.5-3.7 的上下文与记忆系统。先把当前线性的 dispatcher 流程提升成可观测的 `AgentRun` orchestration：每轮有 `run_id`、route policy、context profile、plan、tool calls、observations、final action、commit 和 tracing。再把慢链路拆成“行为响应先返回、TTS 后台生成、前端音频状态机兜底”，并让快路径使用由 MemoryManager 生成的轻量 memory card 投影，降低 prompt 成本。所有语音、文字、触摸和主动事件仍然统一进入 runtime dispatcher，不另建聊天专线。

**Tech Stack:** FastAPI、SQLite、React + Vite、现有 ASR/LLM/TTS provider 配置、Termux/Nubia runtime。

---

## Current Project Context

当前项目已经具备这些基础能力：

- 后端已有 `/api/pet/event`、`/api/voice/chat`、`/api/text/chat`、`/api/context/*`、`/api/memory/*` 等 runtime API。
- Stage 3.5-3.7 已加入 episode、raw event log、context manager、memory candidate、curator、summary、daily digest、maintenance 等机制。
- 前端已有 Momo 主页面、语音按钮、思考模式、状态栏、触摸互动区域，并且已有 `TextInputBar` 相关代码，需要确认体验是否接入完整，而不是重复造一个输入框。
- 互动按钮已有部分扩展，但需要按养宠/陪伴两类补齐事件、后端白名单、prompt 和状态联动。
- 当前 runtime 已经不是纯状态机，但 dispatcher 仍偏线性脚本。体验修复阶段要避免继续堆 if/else，把新增能力落到 `AgentRun / RoutePolicy / PolicyGuard / ToolObservation / InteractionCatalog` 这些可扩展边界上。
- 当前项目不应该新开分支，除非用户再次明确要求。实施前先确认工作区状态，避免把“计划阶段”的临时代码混进实现提交。

## Non-Goals

- 不改公网/VPS/远程连接方案。
- 不做后台常驻麦克风唤醒。
- 不替换现有 Stage 3.5-3.7 的 SQLite 记忆系统。
- 不把完整 reply 直接从前端展示成聊天应用。
- 不新增“查看完整文字回复”文本卡片。Momo 默认始终是声音桌宠；完整文本只进入日志、debug 接口和开发工具，不进入普通用户界面。
- 不把真实 API key 写进代码、计划、测试输出或 git diff。

## Product Decisions

### Voice-First Interaction

Momo 是“会开口的小桌宠”，不是普通文字聊天窗口。

默认体验：

```text
用户语音 / 文字 / 按钮
-> 前端立刻变脸和动画
-> 后端返回 PetResponse + audio_job_id
-> TTS 后台生成音频
-> 前端等音频 ready
-> 播放声音
-> 可选显示极短气泡
```

完整 `reply` 仍保存到 raw event log、debug API 和后端日志，但默认 UI 不提前展示完整文本。即使 TTS 失败，普通 UI 也不展示完整文本卡片，只显示短提示并提供重试声音；开发调试入口可以查看完整 reply。

### Agent Run Loop

体验优化不能只是在 dispatcher 上继续追加固定步骤。每次用户输入、触摸按钮、主动事件或文字输入，都应被建模为一个 `AgentRun`：

```text
input event
-> create AgentRun(run_id, event_id, episode_id)
-> route policy decides context_profile/provider/tool policy
-> context assembler builds budgeted context
-> planner decides tool calls or direct action
-> executor runs bounded tools
-> observer records tool observations
-> PetBrain generates final action
-> PolicyGuard validates plan/action/state/memory/audio
-> commit state/event/memory/audio job
-> frontend executes action
-> audio playback reports observation
-> maintenance updates summaries/cards
```

每个 run 至少保存：

```text
run_id
event_id
episode_id
route
context_profile
provider
planned_tools
tool_observations
final_action
audio_job_id
timings_ms
status
```

这让 Momo 更接近主流 agent runtime：可路由、可观测、可恢复、可扩展，而不是不可检查的一次性函数调用。

### Fast Path vs Slow Path

默认快路径目标是“快、自然、能陪伴”：

```text
当前事件
当前 pet_state
最近 2-4 轮事件
user_preferences memory card
momo_memories memory card
```

思考模式慢路径目标是“能回忆、能用 skill、能认真推理”：

```text
当前事件
当前 pet_state
episode summary
daily summary
important quote
database memory search
skill result
```

两条路径共用同一套 runtime dispatcher、guard、state rules、event log，只是 context budget 和 provider routing 不同。

新增 `context_profile`：

```text
fast_companion  普通陪伴、按钮互动、简单闲聊
recall          用户问昨天/之前/刚刚说过什么
tool            天气、设备状态、外部事实、skill 调用
long_task       代码、解释、复杂任务
proactive       主动陪伴
```

新增 `route_policy`：

```text
普通陪伴 -> fast_companion
回忆类问题 -> recall
天气/设备/外部事实 -> tool
复杂任务 -> long_task
用户打开思考模式 -> slow provider + 对应 context_profile
主动事件 -> proactive
```

`ContextManager` 不应全局瘦身，而应按 `context_profile` 选择预算。

### Natural Reply Length

回复不再“强行极短”。目标是：

- 普通陪伴：1-4 句。
- 复杂问题：允许完整回答，最多 500 字。
- 不输出思考过程。
- 不机械客服腔。
- 不每句话都撒娇。
- 能写代码/解释问题，但仍保留 Momo 的语气。

### State Semantics

`energy` 和 `sleepiness` 都保留，但语义必须分开：

```text
energy = 白天活力、陪玩能力、被频繁使唤后的疲劳
sleepiness = 作息困意、夜间想睡、被哄睡后的困倦
```

例子：

- 用户频繁要求 Momo 做任务：`energy` 降。
- 用户夸夸、投喂、充电：`energy` 升。
- 夜间、哄睡、长时间闲置：`sleepiness` 升。
- 早晨、充电、陪玩成功：`sleepiness` 降。

## File Map

### Backend

- Create: `backend/app/runtime/agent_run.py`  
  定义 `AgentRun`、`AgentStep`、`AgentObservation`、`RunStatus`，为每轮交互提供可追踪的运行对象。

- Create: `backend/app/runtime/route_policy.py`  
  根据事件、思考模式、回忆需求、工具需求、复杂度和主动事件，输出 `context_profile`、provider 策略和 tool 策略。

- Create: `backend/app/runtime/policy_guard.py`  
  统一输入、计划、工具调用、记忆写入、状态变化、输出和音频副作用的 guard/tripwire。

- Create: `backend/app/runtime/interaction_catalog.py`  
  中心化定义互动事件：event id、用户文案、分组、默认动画、状态语义、alias 和迁移规则。

- Modify: `backend/app/runtime/dispatcher.py`  
  下沉为 agent run orchestration：创建 run、调用 route policy、组装 context、规划/执行 tool、提交状态和 observation；统一返回 `audio_job_id`，不在主响应链路里等待 TTS。

- Create: `backend/app/runtime/audio_jobs.py`  
  管理 TTS job：`pending / ready / failed / expired / cancelled / superseded`，后台生成音频，提供查询状态；必须有 bounded queue、并发上限和 latest-only/supersede 语义。

- Create: `backend/app/api/audio.py`  
  暴露 `GET /api/audio/jobs/{job_id}`。

- Modify: `backend/app/runtime/actions.py`  
  `PetResponse` 增加 `audio_job_id`，保留 `voice_url` 兼容旧逻辑。

- Modify: `backend/app/api/text.py`、`backend/app/api/voice.py`、`backend/app/api/pet.py`、`backend/app/api/activation.py`  
  返回 audio job 字段；不要让 TTS 失败导致 HTTP 500。

- Create: `backend/app/runtime/memory_cards.py`  
  管理快路径轻量记忆卡：用户偏好卡、Momo 记忆卡。card 是 MemoryManager 的只读投影/缓存，不是第二套权威记忆源。

- Modify: `backend/app/runtime/context_manager.py`  
  根据 `context_profile` 选择 context budget：快路径只选轻量卡和最近事件；recall/tool/slow 保留数据库记忆、摘要、重要原话和 skill result。

- Modify: `backend/app/pet/prompt_builder.py`  
  调整回复风格、禁止思考过程、区分快慢路径上下文。

- Modify: `backend/app/pet/guard.py`  
  `reply` 最大长度放宽到 500 字；继续过滤非法 JSON、非法枚举、过大 state delta 和思考过程。

- Modify: `backend/app/pet/rules.py`  
  新增互动事件规则与 `energy/sleepiness` 语义分离。

- Modify: `backend/app/runtime/events.py`  
  补齐新增事件白名单。

- Modify: `backend/app/runtime/registry.py`  
  从硬编码 skill prompt 走向 manifest-driven tool catalog；tool 调用经过 schema validation、permission guard 和 observation 记录。

- Modify: `backend/app/config.py`、`config/app.yaml`  
  增加 audio job、memory card、reply policy、interaction state tuning 配置。

### Frontend

- Modify: `frontend/src/pet/types.ts`  
  增加 `waiting_voice`、`audio_error` phase，补齐 `audio_job_id` 和新增互动事件类型。

- Modify: `frontend/src/pet/api.ts`  
  增加 `getAudioJob(jobId)`；确认 `sendTextChat`、`uploadVoice`、`sendPetEvent` 都能接收 `audio_job_id`。

- Modify: `frontend/src/App.tsx`  
  统一处理语音、文字、互动按钮返回：先动画，后等 audio job，播放失败自动恢复。

- Modify: `frontend/src/components/VoiceButton.tsx`  
  上传完成后进入 `waiting_voice`，不要直接假设一定能 `speaking`。

- Modify: `frontend/src/components/TextInputBar.tsx`  
  保留输入框，但调整为声音优先体验；发送后不提前展示完整 reply。

- Modify: `frontend/src/components/TouchArea.tsx`  
  补齐互动按钮分组和本地乐观动画映射。

- Modify: `frontend/src/components/StatusBar.tsx`  
  调整 `energy/sleepiness` 展示文案，避免用户以为两个值重复。

- Modify: `frontend/src/styles.css`  
  新增等待声音、音频错误、按钮分组、文本输入状态样式。

### Tests

- Create/Modify: `backend/tests/test_audio_jobs.py`
- Create/Modify: `backend/tests/test_memory_cards.py`
- Create/Modify: `backend/tests/test_text_chat.py`
- Create/Modify: `backend/tests/test_voice_contract.py`
- Create/Modify: `backend/tests/test_api_contracts.py`
- Create/Modify: `backend/tests/test_pet_events.py`
- Create/Modify: `frontend/src/pet/api.test.ts`
- Create/Modify: `frontend/src/components/VoiceButton.test.tsx`
- Create/Modify: `frontend/src/components/TextInputBar.test.tsx`
- Create/Modify: `frontend/src/App.test.tsx`

## Task 0: Preflight And Workspace Guard

**Files:**

- Read: `git status --short --branch`
- Read: `plan/2026-05-14-momo-experience-speedup.md`

- [ ] **Step 1: Confirm user intent**

  Confirm whether this is still a planning-only pass or an implementation pass. If planning-only, do not modify backend/frontend code.

- [ ] **Step 2: Check working tree**

  Run:

  ```bash
  cd /Users/wylam/Documents/workspace/Petagent
  git status --short --branch
  ```

  Expected for implementation: either clean, or only known changes from the current implementation session.

- [ ] **Step 3: Protect secrets**

  Before any commit or sync, run:

  ```bash
  cd /Users/wylam/Documents/workspace/Petagent
  git diff -- . ':(exclude).env' | rg -n "sk-|tp-|nvapi-|github_pat_|ghp_|MIMO_API_KEY=.+|NVIDIA_API_KEY=.+" || true
  ```

  Expected: no real token output.

## Stage Gate: Subagent Review After Every Stage

每个实现阶段结束后都必须做一次独立 review，不能直接进入下一阶段。

适用阶段：

```text
Task 1  AgentRun / RoutePolicy / Observability
Task A  Async TTS / Audio State Machine
Task B  Lightweight Memory Cards / Fast Path
Task C  Text Input / Interaction Expansion
Task D  State Semantics / Dialogue Linkage
Task D2 PolicyGuard / Tool Runtime Hardening
Task E  Performance / Nubia E2E Gate
```

每个阶段完成后执行：

1. Run the stage-specific backend/frontend tests.
2. Run the relevant integration or manual check.
3. Open a subagent review focused on:
   - whether the implementation matches this plan;
   - whether it regresses Stage 1/2/2.5/3/3.5/3.6/3.7 behavior;
   - whether the agent loop remains extensible rather than becoming a fixed if/else state machine;
   - whether Nubia runtime constraints are respected;
   - whether secrets, runtime data, audio files, `.env`, and `backend/data` stay out of git.
4. Treat review findings as blockers for the current stage.
5. Fix the findings.
6. Re-run affected tests.
7. Only then mark the stage complete and move to the next stage.

Suggested subagent prompt template:

```text
Review the completed implementation for <stage name> in /Users/wylam/Documents/workspace/Petagent.
Compare the code against /Users/wylam/Documents/workspace/Petagent/plan/2026-05-14-momo-experience-speedup.md.
Focus on behavioral bugs, regression risk, Nubia/Termux compatibility, frontend runtime states, provider timeout/fallback behavior, agent-loop extensibility, and missing tests.
Return findings ordered by severity with exact file/line references when possible.
```

## Task 1: AgentRun, RoutePolicy And Observability Foundation

**Goal:** 先把体验修复挂到一个可演化的 agent loop 上，避免继续把 dispatcher 写成固定脚本。

**Files:**

- Create: `backend/app/runtime/agent_run.py`
- Create: `backend/app/runtime/route_policy.py`
- Create: `backend/app/runtime/policy_guard.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Modify: `backend/app/runtime/context_manager.py`
- Modify: `backend/app/pet/prompt_builder.py`
- Test: `backend/tests/test_agent_run.py`
- Test: `backend/tests/test_route_policy.py`
- Test: `backend/tests/test_policy_guard.py`

- [ ] **Step 1.1: Define AgentRun contract**

  `AgentRun` must track:

  ```text
  run_id
  event_id
  episode_id
  route
  context_profile
  provider
  requested_tools
  tool_observations
  final_action
  audio_job_id
  timings_ms
  status
  error
  created_at
  updated_at
  ```

  `status` values:

  ```text
  started
  planning
  tools_running
  action_generated
  committed
  audio_pending
  completed
  failed
  superseded
  ```

- [ ] **Step 1.2: Define RoutePolicy**

  Route policy output:

  ```json
  {
    "route": "fast | slow",
    "context_profile": "fast_companion | recall | tool | long_task | proactive",
    "provider_profile": "fast_llm | slow_llm",
    "allow_tools": true,
    "max_tool_calls": 2,
    "reason": "short reason"
  }
  ```

  Rules:

  - Thinking mode forces `slow`.
  - Weather/device/external fact requests select `tool`.
  - “昨天/之前/刚刚/记得吗” selects `recall`.
  - Code/explanation/long task selects `long_task`.
  - Touch buttons and normal companionship select `fast_companion`.
  - Proactive events select `proactive`.

- [ ] **Step 1.3: Wire context_profile into ContextManager**

  `ContextManager.build(...)` must accept `context_profile`.

  Budget expectations:

  ```text
  fast_companion: recent 2-4 events + memory cards + pet_state
  recall: recent events + temporal recall + summaries + important quotes
  tool: recent events + skill results + minimal memory
  long_task: recent events + relevant memories + device state when useful
  proactive: current time + device state + pet_state + low-cost memory card
  ```

  Do not globally remove summaries/memories. Only omit them when profile is `fast_companion` or `proactive`.

- [ ] **Step 1.4: Add observation/tracing**

  Each run should record sanitized observations:

  ```text
  context_built
  skill_planned
  skill_finished
  action_guarded
  state_committed
  audio_enqueued
  audio_ready
  audio_failed
  audio_played
  ```

  Debug API may expose recent runs, but must desensitize user text and provider errors.

- [ ] **Step 1.5: Verify**

  Required tests:

  - Normal button event chooses `fast_companion`.
  - “昨天我说了什么” chooses `recall`.
  - “今天适合出门吗” chooses `tool`.
  - Thinking mode chooses slow provider.
  - ContextManager receives and respects profile.
  - AgentRun contains `run_id`, `event_id`, `episode_id`, `context_profile`, `timings_ms`.

## Task A: Async TTS And Audio State Machine

**Goal:** 主行为响应不再等待 TTS；声音失败不会卡在“Momo 在说”。

**Files:**

- Create: `backend/app/runtime/audio_jobs.py`
- Create: `backend/app/api/audio.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Modify: `backend/app/runtime/actions.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/pet/types.ts`
- Modify: `frontend/src/pet/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/VoiceButton.tsx`
- Test: `backend/tests/test_audio_jobs.py`
- Test: `frontend/src/components/VoiceButton.test.tsx`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step A1: Define backend audio job contract**

  Response from normal interaction APIs should include:

  ```json
  {
    "run_id": "run_xxx",
    "event_id": "evt_xxx",
    "reply": "完整回复只用于日志和调试",
    "voice_url": null,
    "audio_job_id": "aud_xxx",
    "mood": "happy",
    "face_type": "happy",
    "animation": "bounce"
  }
  ```

  `GET /api/audio/jobs/{job_id}` should return:

  ```json
  {
    "job_id": "aud_xxx",
    "run_id": "run_xxx",
    "event_id": "evt_xxx",
    "status": "pending | ready | failed | expired",
    "voice_url": "/static/audio/reply-xxx.wav",
    "error": null,
    "provider": "siliconflow_tts",
    "timings_ms": {"queued": 0, "tts": 2200},
    "created_at": "2026-05-14T00:00:00Z",
    "updated_at": "2026-05-14T00:00:01Z"
  }
  ```

- [ ] **Step A2: Write failing backend tests**

  Required test cases:

  - `/api/text/chat` returns quickly with `run_id`, `audio_job_id` and `voice_url: null`.
  - Polling the job eventually returns `ready` with a `voice_url`.
  - TTS failure returns job status `failed`, not HTTP 500.
  - Proactive low-cost events do not create audio jobs when `synthesize_voice=false`.
  - Newer response supersedes older pending audio job in the same session when latest-only mode is enabled.

- [ ] **Step A3: Implement backend audio job manager**

  Requirements:

  - In-memory job registry is acceptable for this stage, but job metadata must include `run_id` and `event_id`.
  - Job TTL defaults to 15 minutes.
  - TTS runs through `ThreadPoolExecutor(max_workers=1 or 2)`, not unlimited daemon threads.
  - Registry has a maximum job count and removes expired jobs.
  - Per session has a pending job limit.
  - Default policy is latest-only: a newer response marks older unplayed jobs as `superseded`.
  - Provider exceptions are caught and stored as sanitized `error`.
  - No API key, base64 audio, or raw provider response appears in the job response.
  - Audio job completion/failure writes an `audio_ready` or `audio_failed` observation back to the associated `AgentRun`.

- [ ] **Step A4: Wire dispatcher**

  `RuntimeDispatcher.handle_event(..., synthesize_voice=True)` should enqueue a job instead of calling TTS synchronously.

  Compatibility rule:

  - Keep `voice_url` field for old callers.
  - New normal path returns `voice_url: null` plus `audio_job_id`.
  - `audio_job_id` is bound to the same `run_id/event_id/episode_id` as the action.
  - If `audio_job_manager` is missing in tests, fallback to old sync behavior only when explicitly needed.

- [ ] **Step A5: Implement frontend state machine**

  Frontend phases:

  ```text
  idle
  listening
  thinking
  waiting_voice
  speaking
  audio_error
  error
  ```

  Rules:

  - After user action, immediately animate locally.
  - After backend response with `audio_job_id`, enter `waiting_voice`.
  - Poll every 400-700ms, max 15s.
  - On `ready`, play audio and enter `speaking`.
  - On `failed`, `expired`, fetch error, `audio.play()` rejection, or timeout, enter `audio_error` then return to `idle`.
  - Do not show complete reply in the normal bubble.
  - Do not show a full text card after audio failure. Show a short failure prompt and allow voice retry.
  - Playback completion should report `audio_played` observation if the backend endpoint exists; if not, frontend must still recover to `idle`.

- [ ] **Step A6: Verify**

  Run:

  ```bash
  cd /Users/wylam/Documents/workspace/Petagent/backend
  ../.venv/bin/python -m pytest tests/test_audio_jobs.py tests/test_text_chat.py tests/test_voice_contract.py -q
  ```

  Run:

  ```bash
  cd /Users/wylam/Documents/workspace/Petagent/frontend
  npm test -- --run src/components/VoiceButton.test.tsx src/App.test.tsx
  npm run build
  ```

## Task B: Lightweight Memory Cards For Fast Path

**Goal:** 快路径不再每轮都塞重型摘要和数据库检索，减少 prompt 成本；memory cards 必须是现有 MemoryManager 的投影缓存，不是第二套长期记忆系统。

**Files:**

- Create: `backend/app/runtime/memory_cards.py`
- Modify: `backend/app/runtime/context_manager.py`
- Modify: `backend/app/runtime/memory_curator.py`
- Modify: `backend/app/api/memory.py`
- Modify: `backend/app/config.py`
- Modify: `config/app.yaml`
- Test: `backend/tests/test_memory_cards.py`
- Test: `backend/tests/test_stage36_context.py`
- Test: `backend/tests/test_stage37_daily_context.py`

- [ ] **Step B1: Define storage**

  Runtime-created files:

  ```text
  backend/data/memory_cards/user_preferences/card.md
  backend/data/memory_cards/momo_memories/card.md
  ```

  These files live under ignored `backend/data/`, so they must not be committed.

  Card line format should include provenance:

  ```text
  - 喜欢短回复 <!-- source:memory:42 type:user_preference updated:2026-05-14 ttl:stable -->
  ```

- [ ] **Step B2: Define card limits**

  Config:

  ```yaml
  memory_cards:
    enabled: true
    max_card_cjk_chars: 200
    max_item_cjk_chars: 20
    max_items_per_card: 10
    user_preferences_path: backend/data/memory_cards/user_preferences/card.md
    momo_memories_path: backend/data/memory_cards/momo_memories/card.md
  ```

  Runtime rules:

  - Cards are generated by maintenance/curator from SQLite memories.
  - Dispatcher must not write card files directly.
  - Reject or compress items over 20 Chinese characters.
  - Keep at most 10 lines per card.
  - Keep each card under 200 Chinese characters.
  - Deduplicate near-identical items.
  - Do not store tokens, passwords, API keys, private credentials, or sensitive guesses.
  - Rebuild cards after memory merge, reset, decay cleanup or curator save.

- [ ] **Step B3: Update context manager**

  Fast path context includes:

  ```json
  {
    "context_profile": "fast_companion",
    "recent_exact_events": "2-4 turns",
    "memory_cards": {
      "user_preferences": ["喜欢短回复"],
      "momo_memories": ["昨天聊过项目累"]
    }
  }
  ```

  Slow/recall/tool path context keeps:

  ```text
  episode summaries
  daily digest
  important quotes
  scored SQLite memories
  skill results
  ```

- [ ] **Step B4: Update reset behavior**

  `/api/runtime/reset` clears both card files in addition to SQLite memory, summaries, candidates, event logs and pet state.

- [ ] **Step B4.5: Add card rebuild behavior**

  Maintenance should expose:

  ```text
  rebuild_memory_cards(reason)
  ```

  Required reasons:

  ```text
  curator_saved
  memory_merged
  memory_expired
  runtime_reset
  manual_debug
  ```

- [ ] **Step B5: Verify**

  Required tests:

  - “记住我喜欢短回复” enters user preference card.
  - “我刚刚喝了水” does not enter either card.
  - Card over 200 Chinese characters is trimmed.
  - Single item over 20 Chinese characters is compressed or rejected.
  - Card item contains source memory id.
  - Dispatcher never writes card file directly.
  - Rebuild after reset produces empty card files.
  - Fast path prompt does not include daily summary unless route explicitly requests slow/recall.
  - Slow path still includes database summaries and memory search.

## Task C: Text Input And Interaction Expansion

**Goal:** 补齐文字入口，扩展养宠动作，并保证按钮也结合上下文调用 LLM。

**Files:**

- Create: `backend/app/runtime/interaction_catalog.py`
- Create/Modify: `backend/app/api/interactions.py`
- Modify: `frontend/src/components/TextInputBar.tsx`
- Modify: `frontend/src/components/TouchArea.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pet/types.ts`
- Modify: `backend/app/runtime/events.py`
- Modify: `backend/app/pet/rules.py`
- Modify: `backend/app/pet/prompt_builder.py`
- Test: `frontend/src/components/TextInputBar.test.tsx`
- Test: `frontend/src/App.test.tsx`
- Test: `backend/tests/test_text_chat.py`
- Test: `backend/tests/test_pet_events.py`

- [ ] **Step C1: Audit existing frontend**

  Confirm whether `TextInputBar` is already rendered and wired in `frontend/src/App.tsx`. If it exists, only adjust behavior; do not create a duplicate input box.

- [ ] **Step C2: Define interaction events**

  First define a canonical interaction catalog. Do not scatter event labels, groups, animations and rule meanings across frontend and backend.

  Catalog fields:

  ```json
  {
    "event_id": "feed_momo",
    "aliases": ["feed"],
    "label": "投喂",
    "group": "养宠",
    "default_mood": "happy",
    "default_animation": "bounce",
    "state_semantics": {"energy": "up", "hunger": "down"},
    "prompt_semantics": "用户在投喂 Momo，不等于手机充电"
  }
  ```

  Required canonical events:

  ```text
  feed_momo
  pet_pat
  praise_momo
  comfort_me
  stay_with_me
  listen_to_me
  tuck_in
  clean_face
  encourage_me
  quiet_company
  take_a_break
  ```

  Avoid introducing duplicate events like `comfort_momo` when `comfort_me` already exists. If a better name is needed, add alias/migration explicitly.

  Product grouping:

  ```text
  养宠：投喂、拍一拍、擦脸、哄睡
  陪伴：夸夸、安慰我、陪我一下、听我吐槽、给我打气、安静待着、陪我休息
  ```

- [ ] **Step C3: Define optimistic animation map**

  Frontend local feedback should happen before network returns:

  ```text
  feed_momo -> happy + bounce
  pet_pat -> shy + wiggle
  praise_momo -> excited + jump
  comfort_momo -> concerned + tilt
  stay_with_me -> idle/happy + breathing
  listen_to_me -> thinking + tilt
  tuck_in -> sleepy + slowBlink
  clean_face -> happy + wiggle
  encourage_me -> happy + bounce
  quiet_company -> idle + breathing
  take_a_break -> sleepy/idle + breathing
  ```

- [ ] **Step C4: Make button events context-aware**

  Prompt must say: button events are not fixed canned lines. Momo should combine:

  - Current pet state.
  - Recent episode context.
  - Memory cards.
  - User’s latest mood.
  - The button’s semantic meaning.

- [ ] **Step C5: Verify**

  Required tests:

  - Text input uses `/api/text/chat`.
  - Text input respects thinking mode.
  - Text input receives `audio_job_id` and follows audio state machine.
  - `/api/interactions` or equivalent catalog endpoint returns canonical metadata.
  - Each new button dispatches a valid event.
  - Existing aliases do not create duplicate semantic events.
  - Network failure restores UI to `idle` or `error`, never permanently disables controls.
  - New events are written into raw event log.

## Task D: State Semantics And Dialogue Linkage

**Goal:** 让状态影响 Momo 的表现，也让对话和互动真实改变状态。

**Files:**

- Modify: `backend/app/pet/rules.py`
- Modify: `backend/app/pet/guard.py`
- Modify: `backend/app/runtime/policy_guard.py`
- Modify: `backend/app/pet/prompt_builder.py`
- Modify: `config/pet_persona.yaml`
- Modify: `frontend/src/components/StatusBar.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `backend/tests/test_pet_rules.py`
- Test: `backend/tests/test_pet_guard.py`
- Test: `backend/tests/test_stage35_event_log.py`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step D1: Update state language**

  UI labels should make the distinction obvious:

  ```text
  energy -> 活力
  sleepiness -> 困意
  intimacy -> 亲密
  loneliness -> 想陪
  ```

- [ ] **Step D2: Add event rule deltas**

  Suggested bounded defaults:

  ```text
  feed_momo: energy +8, hunger -10, sleepiness -2
  pet_pat: intimacy +2, loneliness -4
  praise_momo: energy +4, intimacy +2
  comfort_momo: loneliness -6, intimacy +1
  play_with_momo: energy -5, loneliness -5, intimacy +2
  tuck_in: sleepiness +10, energy +2
  clean_face: cleanliness +10, mood happy
  encourage_me: energy -2, intimacy +1
  take_a_break: sleepiness +3, loneliness -3
  pet_effort=medium: energy -2
  pet_effort=high: energy -4 to -6, sleepiness +1
  ```

  Guard still clamps all numeric state values to `0-100`.

- [ ] **Step D3: Let LLM suggest state affect**

  LLM may suggest `state_delta` and `state_affect`, but guard enforces:

  ```text
  energy: -8 to +8 per turn
  sleepiness: -8 to +10 per turn
  intimacy: -3 to +3 per turn
  loneliness: -10 to +4 per turn
  hunger: -10 to +8 per turn
  cleanliness: -8 to +10 per turn
  ```

  Do not implement `complex_text_or_voice_task` as a fake event. Complex task fatigue comes from `state_affect.pet_effort`:

  ```text
  none   -> no fatigue
  low    -> no or tiny change
  medium -> small energy drop
  high   -> larger energy drop, tiny sleepiness rise
  ```

  This keeps state linkage tied to agent action semantics instead of brittle keyword rules.

- [ ] **Step D4: Make state influence expression**

  Prompt and frontend should reflect:

  - Low energy: smaller animation, less eager to do long tasks.
  - High sleepiness: softer voice style, sleepy face, fewer active invitations.
  - High intimacy: more familiar language.
  - High loneliness: wants company, but proactive remains rate-limited.

- [ ] **Step D5: Verify**

  Required tests:

  - Repeated task requests lower `energy`.
  - `feed_momo` and `praise_momo` raise `energy`.
  - Night/tuck-in raises `sleepiness`.
  - Morning/charging lowers `sleepiness`.
  - Raw event log stores `state_before` and `state_after`.
  - Raw event log stores `state_affect`.
  - High-effort answer lowers energy even when event type is just `text_message`.
  - Values never exceed `0-100`.

## Task D2: PolicyGuard And Tool Runtime Hardening

**Goal:** 把 guard 从“只校验 LLM JSON”扩展成覆盖 agent loop 的统一 policy 层。

**Files:**

- Create/Modify: `backend/app/runtime/policy_guard.py`
- Modify: `backend/app/runtime/registry.py`
- Modify: `backend/app/pet/guard.py`
- Modify: `backend/app/runtime/dispatcher.py`
- Modify: `backend/app/pet/prompt_builder.py`
- Test: `backend/tests/test_policy_guard.py`
- Test: `backend/tests/test_skill_registry.py`

- [ ] **Step D2.1: Define policy checkpoints**

  PolicyGuard checkpoints:

  ```text
  input_event
  route_decision
  tool_plan
  tool_result
  memory_candidate
  state_delta
  final_action
  audio_job
  proactive_event
  ```

- [ ] **Step D2.2: Make tools manifest-driven**

  Tool catalog must come from skill manifests and `config/skills.yaml`, not hardcoded prompt strings.

  Planner sees:

  ```json
  {
    "skill_id": "weather.current",
    "description": "获取当前天气",
    "input_schema": {"location": "string"},
    "permissions": ["network"],
    "timeout_ms": 3000
  }
  ```

  Dispatcher must validate tool id, payload schema, permission and max calls before execution.

- [ ] **Step D2.3: Record tool observations**

  Each skill call produces an observation:

  ```json
  {
    "type": "tool_observation",
    "skill_id": "weather.current",
    "ok": true,
    "latency_ms": 820,
    "content": "多云，22 度",
    "error": null
  }
  ```

  Final PetBrain should consume observations, not raw provider errors.

- [ ] **Step D2.4: Verify**

  Required tests:

  - Unknown skill is rejected before execution.
  - Skill payload fails schema validation when malformed.
  - Skill timeout becomes sanitized observation.
  - Memory candidate with secret-like text is rejected.
  - Proactive event respects rate policy.
  - Tool list in prompt comes from registry, not hardcoded text.

## Task E: Performance And Nubia E2E Gate

**Goal:** 确认体验真的更快、更稳，不再卡在 speaking。

**Files:**

- Modify if needed: `scripts/start.sh`
- Modify if needed: `scripts/status.sh`
- Modify if needed: `scripts/clean_cache.sh`
- Read: `backend/data/logs/runtime.log`

- [ ] **Step E1: Backend test gate**

  Run:

  ```bash
  cd /Users/wylam/Documents/workspace/Petagent/backend
  ../.venv/bin/python -m pytest -q
  ```

  Expected: all backend tests pass.

- [ ] **Step E2: Frontend test gate**

  Run:

  ```bash
  cd /Users/wylam/Documents/workspace/Petagent/frontend
  npm test -- --run
  npm run build
  ```

  Expected: tests and build pass.

- [ ] **Step E3: Secret scan**

  Run:

  ```bash
  cd /Users/wylam/Documents/workspace/Petagent
  git diff --cached | rg -n "sk-|tp-|nvapi-|github_pat_|ghp_|MIMO_API_KEY=.+|NVIDIA_API_KEY=.+" || true
  ```

  Expected: no real secrets.

  Also block accidental staging of runtime files:

  ```bash
  cd /Users/wylam/Documents/workspace/Petagent
  git diff --cached --name-only | rg '(^|/)\.env$|backend/data|runtime\.log|backend/static/audio' && exit 1 || true
  ```

  Optional stronger gate:

  ```bash
  gitleaks protect --staged
  ```

- [ ] **Step E4: Safe sync to Nubia**

  Do not use raw `scp -r Petagent/*`. Use a safe sync that excludes:

  ```text
  .env
  .git/
  .venv/
  frontend/node_modules/
  backend/data/
  backend/static/audio/
  ```

  Do not overwrite Nubia’s `backend/data/pet.db` or runtime `.env`.

- [ ] **Step E5: Nubia manual test**

  Test in Via browser on Nubia:

  - Open current frontend URL.
  - Tap 10 interaction buttons in a row.
  - Send 5 text messages.
  - Send 5 voice messages.
  - Force one TTS provider failure or timeout if possible.
  - Confirm every run returns to `idle`.
  - Confirm no “Momo 在说” permanent stuck state.

- [ ] **Step E6: Performance targets**

  Record observed timings:

  ```text
  Main response: target 1-3s
  Audio ready: target 3-8s normal network
  UI first feedback: target <300ms
  Error recovery: target <15s
  ```

  Each response/debug run should expose sanitized metrics:

  ```text
  run_id
  event_id
  route
  context_profile
  provider
  asr_ms
  llm_ms
  tool_ms
  tts_ms
  audio_queue_ms
  total_ms
  status
  ```

## Rollback Plan

If async TTS causes instability:

1. Keep `audio_job_id` field but configure sync TTS fallback off for fast path.
2. Frontend should treat missing `audio_job_id` and missing `voice_url` as `audio_error -> idle`, not crash.
3. Re-enable old `voice_url` path only as compatibility mode.
4. Do not add full text card as fallback; only short prompt, retry voice and debug-only full reply.

If memory cards pollute behavior:

1. Set `memory_cards.enabled=false` in `config/app.yaml`.
2. Continue using SQLite memory and summaries in slow path.
3. Keep reset API clearing cards so test data can be wiped.

## Definition Of Done

- Plan file exists at `/Users/wylam/Documents/workspace/Petagent/plan/2026-05-14-momo-experience-speedup.md`.
- Async audio job contract is documented before implementation.
- AgentRun, RoutePolicy, PolicyGuard and interaction catalog are documented before implementation.
- Fast path memory card boundaries are explicit.
- Memory cards are documented as MemoryManager projections, not a second source of truth.
- Audio jobs are bounded, cancellable/supersedable, and tied to `run_id/event_id`.
- Route policy decides `fast_companion/recall/tool/long_task/proactive` instead of relying only on thinking mode.
- Text input and interaction expansion are treated as one frontend/runtime feature, not scattered patches.
- `energy` and `sleepiness` have separate meanings in UI, prompt, rules and tests.
- Tests cover route policy, audio failure, TTS timeout, text input, interaction catalog, memory cards, state deltas, tool guard and Nubia E2E.
- No secrets appear in repo, plan or logs.
