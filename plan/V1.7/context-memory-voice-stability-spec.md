# V1.7 上下文、记忆、状态与语音稳定性改造 Spec

## 目标

这次改造解决当前豆豆进入“生气 + 小本本 + 玩手机”循环的问题，同时修复语音 ASR 偶发超时和重置不彻底的问题。

核心目标：

1. 每轮对话仍保持稳定、低成本、统一链路。
2. 最近对话、长期记忆、pet_state 不再互相强化成固定口头癖。
3. 记忆总结按用户要求在后台触发，维护最多 10 条不重复长期记忆。
4. 失败就明确失败，不用 fallback 假装正常。
5. Nubia 上必须验证实际语音、上下文、记忆、重置行为。

## 当前问题

### 1. 最近 5 轮对话造成自我强化

当前 prompt 会输入最近 5 条成功对话。最近记录里模型连续输出：

- 正在记你玩手机
- 小本本快写满了
- 主人又来烦我
- 没空管今天星期几
- 没空管语音识别

这些回复下一轮又作为 `recent_dialogue` 输入模型，导致模型继续模仿上一轮口头癖。

### 2. memory.md 内容过窄且被过度使用

当前 `memory.md` 只有两条相似记忆：

- 用户喜欢玩手机。
- 用户希望豆豆记住他喜欢玩手机。

模型把这两条当成每轮都要提的事实，导致“玩手机”过度出现在回复中。

### 3. pet_state 输入输出不平衡

当前统一 prompt 输入：

```json
{
  "mood": "angry",
  "energy": 10,
  "intimacy": 80
}
```

但 fast/unified 输出 schema 只允许输出：

```json
{
  "reply": "...",
  "mood": "...",
  "expression_key": "...",
  "action": "...",
  "voice_style": "..."
}
```

也就是说模型会被低能量、生气、高亲密度影响，但不能显式修正 `energy/intimacy`。状态容易锁死。

V1.7 不再把困意作为模型上下文字段，也不让模型输出困意变化。桌宠状态闭环只保留：

- `energy`
- `intimacy`

### 4. 记忆总结没有按最新设计输入完整上下文

当前后台 memory summary 输入只有：

- 当前 turn
- selected_memory
- 当前 memory.md

没有输入最近 5 轮成功对话。它也没有足够强的“语义合并、互不重复”约束，因此会产生相似记忆。

### 5. recall 模式残留但实际不生效

代码里有 `profile == "recall"` 和“回忆模式” prompt 分支，但当前 route policy 对回忆关键词仍返回 `unified`。实际没有专门 recall prompt，也不会额外拉历史。

### 6. reset 需要确认清空所有上下文和记忆

前端已有“重新认识”按钮，后端 `/api/runtime/reset` 已清理多数 runtime 数据。但还需要确认并补齐：

- `successful_turn_state`
- `successful_turn_event`
- canonical `memory.md`
- memory summary queue
- agent/audio 调试残留是否需要保留或归档

用户期望这个按钮能清掉所有上下文和记忆，让豆豆重新开始。

### 7. ASR 偶发 timeout

Nubia 日志显示录音文件已成功上传，大小正常，但后端调用 ASR HTTP 返回 `asr_timeout`，约 2 秒级失败。问题不是麦克风上传链路，而是 ASR HTTP 请求超时/网络抖动。

## 非目标

本次不做以下内容：

1. 不增加 deterministic 语义去重。记忆去重主要靠 summary prompt 和格式校验完成。
2. 不增加前端 thinking mode 按钮。
3. 不做 ASR/LLM/TTS 假成功 fallback。
4. 不用硬词表禁止豆豆说某些词，例如不写“禁止说小本本/禁止说玩手机”。约束要写成通用原则。
5. 不把所有历史对话每轮都塞进普通对话 prompt。

## 改造方案

### A. 统一对话 prompt 改造

文件：

- `backend/app/pet/prompt_builder.py`
- `config/pet_persona.yaml`

改法：

1. 保留统一链路：文本和 ASR 成功语音都走 `unified`。
2. system prompt 增加通用上下文使用规则：
   - 长期记忆只在和当前问题相关时使用。
   - 最近对话用于理解上下文，不是必须模仿上一轮措辞。
   - 不要把自己的上一轮口头表达当成长期事实。
   - 每轮应根据用户当前输入重新选择 `mood/expression_key/action`。
   - `pet_state.mood` 是当前状态参考，不代表必须延续同一种情绪。
   - 低能量可以影响语气，但不能让豆豆拒绝正常回答。
3. 这些规则必须是通用原则，不绑定具体词。

验收：

- 连续问“你在干嘛 / 今天星期几 / 你为什么超时”时，不能连续复读同一个梗。
- 如果用户问事实性问题，豆豆应回答问题，再带一点桌宠语气。
- 模型仍输出 `expression_key`，前端使用最新输出。

### B. pet_state 输入与输出改造

文件：

- `backend/app/pet/prompt_builder.py`
- `backend/app/runtime/dispatcher.py`

确定方案：

1. 普通对话只输入 `mood/energy/intimacy`。
2. 在 prompt 中说明这些是“参考状态”，不是回复指令。
3. 对 `energy/intimacy` 增加低/中/高分层，避免模型只看到裸数字后过度放大状态影响。例如：

```json
"pet_state": {
  "mood": "angry",
  "energy": 10,
  "energy_level": "low",
  "intimacy": 80,
  "intimacy_level": "high"
}
```

4. 普通对话仍保留原始数值，方便模型理解，但不能把它当作固定输出方向。
5. 不再向模型输入 `sleepiness`，也不要求模型输出 `sleepiness`。

输出 schema 增加状态变化：

```json
{
  "reply": "我回来了，刚才在装作很忙。",
  "mood": "playful",
  "expression_key": "smug",
  "action": "pretend_busy",
  "voice_style": "normal",
  "state_delta": {
    "energy": -2,
    "intimacy": 1
  }
}
```

落库规则：

1. 只有 LLM 成功输出文本时才应用 `state_delta`。
2. `state_delta.energy` 和 `state_delta.intimacy` 都是小整数 delta，不是最终绝对值。
3. 后端把结果 clamp 到 0-100。
4. 缺失字段按 0 处理。
5. 非数字、过大值、非法字段忽略，不影响本轮回复。
6. 不支持 `sleepiness` 输出；即使模型输出也忽略。

验收：

- 即使 `mood=angry`，用户正常问问题时也可以输出 `idle/happy/concerned/playful` 等其他表情。
- `energy=10` 不应导致豆豆连续拒答或装忙。
- 成功对话后 `energy/intimacy` 会按模型输出的小幅 delta 更新。
- 模型输出 `sleepiness` 时后端忽略。

### C. 最近 5 轮上下文处理

文件：

- `backend/app/runtime/context_store.py`
- `backend/app/runtime/context_manager.py`
- `backend/app/pet/prompt_builder.py`

改法：

1. 仍取最近 5 条成功对话。
2. 只取：
   - `text_message`
   - ASR 成功后的 `voice_message`
3. ASR 失败不进入最近对话。
4. prompt 输入结构必须清楚分区，不能把上下文、记忆、用户最新一句混在同一段自然语言里。
5. 普通对话 payload 使用明确字段名：

```json
{
  "current_user_message": "用户这一轮刚刚说的话",
  "recent_conversation_context": [
    {"user": "上一轮用户说的话", "pet": "上一轮我回复的话", "created_at": "..."}
  ],
  "long_term_memory": [
    "- [2026-05-31 15:36][preference] 用户喜欢玩手机。"
  ],
  "pet_state": {
    "mood": "angry",
    "energy": 10,
    "energy_level": "low",
    "intimacy": 80,
    "intimacy_level": "high"
  },
  "response_schema": {}
}
```

6. system prompt 要明确解释这些字段的用途：
   - `current_user_message` 是本轮要优先回应的最新输入。
   - `recent_conversation_context` 是最近上下文，只用于理解连续对话，不是措辞模板。
   - `long_term_memory` 是长期背景事实，只在相关时使用。
   - `pet_state` 是当前状态参考，不能压过本轮用户意图。
7. 可选：对每条 recent conversation 增加轻量字段：

```json
{
  "user": "...",
  "pet": "...",
  "note": "历史回复仅供理解，不要求复用措辞"
}
```

验收：

- 最近 5 轮里即使包含相似回复，新一轮也不会机械复读。
- 回忆类问题仍能看到最近 5 轮。

### D. 长期记忆 memory.md 使用规则

文件：

- `backend/app/pet/prompt_builder.py`
- `backend/app/runtime/notebook.py`

改法：

1. 每轮对话读取当前 `memory.md`，最多 10 条，全部进入 `long_term_memory`。
2. prompt 明确：
   - `long_term_memory` 是背景事实。
   - 只有和当前输入相关时才引用。
   - 不要每轮主动复述记忆内容。
   - 同一事实不要在回复中反复强调。

不做：

- 不做 deterministic 语义去重。
- 不做智能选择，只要 memory.md 最多 10 条就全进。

验收：

- `memory.md` 里有“用户喜欢玩手机”，但用户问星期几时不应强行提玩手机。

### E. 记忆总结触发时机

记忆总结只有两个触发时刻：

1. **关键词触发**
   用户文本命中记忆相关关键词：
   - 记住 / 你要记得 / 帮我记 / 别忘了 / 写进小本本
   - 我喜欢 / 我不喜欢 / 我希望你 / 我更喜欢
   - 我叫 / 我的名字 / 我是
   - 今天我们 / 刚刚我们 / 以后我们

2. **每 10 轮成功对话触发**
   成功输出文本算一轮：
   - text_message 成功回复算一轮
   - ASR 成功后的 voice_message 成功回复算一轮
   - 按钮互动如果触发 LLM 并产生正式文本回复，也算一轮

不算：

- ASR 失败
- LLM 失败
- 纯本地按钮互动
- TTS 失败但文本已成功输出时，文本成功仍算一轮

### F. 记忆总结 prompt 改造

文件：

- `backend/app/runtime/dispatcher.py`
- `backend/app/runtime/memory_judgment.py`
- `backend/app/pet/prompt_builder.py`

改法：

1. 触发 memory summary 时，后台 job 携带：
   - 用户最新一句：`current_user_message`
   - 豆豆本轮回复：`current_pet_reply`
   - 最近 5 条成功对话：`recent_conversation_context`
   - 当前 `memory.md` 全文
   - 路由和触发信息：`route`, `trigger_categories`
2. 记忆总结 payload 也必须分区清楚：

```json
{
  "current_turn": {
    "current_user_message": "用户这一轮刚刚说的话",
    "current_pet_reply": "我这一轮已经回复给用户的话",
    "route": "unified",
    "trigger_categories": ["preference"]
  },
  "recent_conversation_context": [
    {"user": "最近用户说过的话", "pet": "最近我回复过的话", "created_at": "..."}
  ],
  "long_term_memory_file": "当前 memory.md 全文",
  "output_schema": {
    "memories": [
      {"category": "identity/preference/relationship/project/temporary", "content": "保留下来的记忆一句话"}
    ]
  }
}
```

3. summary prompt 要求输出完整替换后的 0-10 条 memories。
4. prompt 明确：
   - `current_turn.current_user_message` 是最高优先级证据。
   - `recent_conversation_context` 只辅助判断最近上下文。
   - `long_term_memory_file` 是已有长期记忆基线。
   - 输出是“完整替换后的长期记忆列表”，不是“本轮新增记忆列表”。
   - 如果 `long_term_memory_file` 里已有有效记忆，默认应原样保留旧记忆，并只在当前证据明确要求时更新、合并或移除。
   - 不能因为本轮没有新增长期信息就输出空列表。
   - 只有当 `long_term_memory_file` 本来没有有效记忆，且当前轮和最近上下文也没有长期价值信息时，才允许输出空列表。
   - 相似事实必须合并成一条。
   - 每条 memory 必须表达不同事实。
   - 不要保存豆豆自己的口头癖、玩笑、临时情绪。
   - 不要把“豆豆正在记小本本”这类回复内容写成用户长期事实。
5. 输出格式仍为：

```json
{
  "memories": [
    {"category": "preference", "content": "用户喜欢玩手机，并希望我记住这一点。"}
  ]
}
```

6. 后端只做格式校验：
   - `memories` 必须是 list
   - 最多 10 条
   - category 合法
   - content 非空
   - content 不含敏感信息
   - content 不以时间戳开头
   - 如果当前 `memory.md` 已有有效记忆，而模型输出 `memories: []`，视为异常 summary，不覆盖旧 `memory.md`

不做：

- 不做 deterministic 语义去重。

验收：

- 当前两条相似记忆应被总结成一条。
- 如果用户没有提供长期价值信息，但 `memory.md` 已有旧记忆，应保留旧记忆，不能输出空列表覆盖。
- 一次总结后 `memory.md` 最多 10 条。

### G. Reset 改造

文件：

- `frontend/src/App.tsx`
- `frontend/src/pet/api.ts`
- `backend/app/api/memory.py`

现状：

- 前端已有 `重新认识` 按钮。
- 后端 `/api/runtime/reset` 已清大部分 runtime 数据。

需要确认并补齐：

1. 清空 canonical `memory.md`，保留 marker。
2. 清空 `user.md` stub。
3. 清空 `raw_event_log`。
4. 清空 `episode`。
5. 清空 `interaction_log`。
6. 清空 `successful_turn_state` 和 `successful_turn_event`。
7. 清空 memory summary queue 内存队列。
8. pet_state 回到初始值。
9. 前端 localStorage 的 ambient state 也重置。

前端文案：

- 按钮仍可叫“重新认识”。
- confirm 文案要明确“会清空记忆、上下文和状态”。

验收：

- 点击后 `memory.md` 为空 marker。
- 最近 5 轮对话为空。
- 成功 turn 计数归零。
- pet_state 回初始。
- 页面显示 idle 表情和重新开始文案。

### H. ASR timeout 稳定性

文件：

- `backend/app/providers/asr_http.py`
- `config/models.yaml`
- 相关测试

改法：

1. `asr_timeout` 纳入 transient retry。
2. 最多 3 次请求。
3. connect/read timeout 拆开配置，避免 2 秒连接超时过紧。
4. 仍然失败时返回 `asr_timeout`，不调用 LLM，不生成伪回复。

验收：

- 单次 ASR timeout 时会重试。
- 三次都 timeout 时返回结构化失败。
- 日志能看到最终失败原因。
- Nubia 连续录音测试至少 5 次，成功/失败原因清晰。

## 测试计划

### 单元测试

1. prompt_builder：
   - unified prompt 包含通用上下文使用规则。
   - `current_user_message`、`recent_conversation_context`、`long_term_memory`、`pet_state` 分区清楚。
   - `pet_state` 包含 `energy/intimacy` 原始数值和低/中/高分层，不包含 `usage_rule` 字段，不包含 `sleepiness`。
   - unified 输出 schema 包含 `state_delta.energy` 和 `state_delta.intimacy`，不包含 `sleepiness`。
   - memory 使用规则存在。

2. context：
   - 最近 5 轮只取成功 text/voice。
   - ASR 失败不进入 recent_dialogue。

3. memory summary：
   - job payload 带 current turn + recent_conversation_context + memory_md。
   - prompt 要求 0-10 条不重复。
   - validator 拒绝超过 10 条、非法 category、空 content。
   - 当前 `memory.md` 非空时，模型输出空列表不会覆盖旧记忆。

4. reset：
   - 清 raw_event_log。
   - 清 successful_turn_state/event。
   - 清 memory.md。
   - pet_state 回初始。

5. ASR：
   - `asr_timeout` 会重试。
   - 认证错误不重试。
   - 三次 timeout 后明确失败。

### Nubia 验证

1. 部署后检查：
   - `/build-info.json`
   - `/api/health`
   - 后端进程状态

2. 上下文验证：
   - 连续问 5 轮普通问题。
   - 检查 SQLite 最近 5 轮内容。
   - 确认不再连续复读同一梗。
   - 检查 `pet_state` 只把 `energy/intimacy` 输入给 LLM，并且成功回复后能小幅更新。

3. 记忆验证：
   - 说“我喜欢 X，你要记住”。
   - 等后台 summary 触发或手动触发 maintenance。
   - 检查 `memory.md` 输出 0-10 条，且相似事实合并。

4. reset 验证：
   - 点击前写入一条记忆并产生几轮对话。
   - 点击“重新认识”。
   - 查 `memory.md`、`raw_event_log`、`successful_turn_state`、pet_state。

5. 语音验证：
   - 页面点击麦克风录音。
   - 连续 5 次。
   - 检查 `voice_debug.jsonl`。
   - 成功时有 user_text；失败时必须是明确错误，不产生 LLM 回复。

## 实施顺序

1. prompt/context 防自我强化。
2. memory summary payload 和 prompt 改造。
3. reset 清理补齐。
4. ASR timeout retry。
5. 单元测试。
6. Nubia 部署和实机验证。

## 已确认边界结论

这些结论已经确认，实现时不能再自行改口径。

1. 记忆总结没有新长期信息时，怎么处理？
   - 结论：保留现有 `memory.md`。
   - 原因：summary 输入已经包含旧长期记忆，所以输出应该是“基于旧记忆的完整更新结果”，不是“本轮新增列表”。没有新增长期信息时，模型应原样保留旧记忆。
   - 空列表只允许一种情况：旧 `memory.md` 本来就没有有效记忆，且当前 turn 和最近上下文也没有长期价值信息。
   - 如果旧 `memory.md` 非空但模型输出 `memories: []`，后端视为异常 summary，不覆盖旧记忆。

2. `recent_conversation_context` 在记忆总结里是否包含当前 turn？
   - 结论：包含。
   - 具体结构：`current_turn` 单独放当前轮，同时 `recent_conversation_context` 也可以包含当前轮，保证最近上下文完整。

3. reset 是否清理调试/审计数据？
   - 结论：不清调试数据。
   - reset 只清前台体验会用到的记忆、上下文、episode、成功轮次、pet_state、前端 ambient state。
   - 保留：`agent_run`、`audio_job`、上传音频文件、`voice_debug.jsonl`。

4. V1.7 是否恢复状态更新闭环？
   - 结论：恢复，但只允许模型更新 `energy` 和 `intimacy`。
   - 不输入 `sleepiness`，不输出 `sleepiness`，后端即使收到也忽略。
   - 状态更新只在 LLM 成功输出文本后应用，失败轮次不更新。

5. 纯本地按钮互动是否计入“成功轮次”？
   - 结论：不计入记忆总结。
   - 只有经过 LLM 并产生正式文本回复的 text_message、ASR 成功 voice_message、模型按钮互动才计入 10 轮总结。
