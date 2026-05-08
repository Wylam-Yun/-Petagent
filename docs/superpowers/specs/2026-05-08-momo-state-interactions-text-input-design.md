# Momo 状态联动、互动扩展与文字输入设计

日期：2026-05-08

## 背景

Momo 目前已经有语音对话、上下文、记忆、摘要和基础状态系统。现阶段的主要短板是：

- `energy / intimacy / loneliness / sleepiness / hunger / cleanliness` 与对话内容的关系还不够自然。
- 互动按钮只有 `摸摸头 / 戳戳脸 / 抱一下`，养宠感和陪伴情绪入口偏少。
- 用户只能通过语音输入，不方便在浏览器里直接打字测试或安静聊天。

本阶段目标是把 Momo 从“能对话的宠物”推进到“状态会随互动自然变化、可养成互动更丰富、语音和文字都能陪伴”的形态。

## 设计决策

1. 状态联动采用 **LLM 为主，Guard 限制**。
   每轮语音、文字、互动按钮都让 `mimo-v2.5` 判断本次互动对 Momo 的影响，后端只负责限幅、校验和落库。

2. 状态联动不新增第二次模型调用。
   继续让现有 `PetBrain` 一次性输出回复、表情、动画、`state_delta` 和新增的 `state_affect`，避免手机端每轮再多等一次 LLM。

3. 所有互动按钮都调用 `mimo-v2.5`。
   按钮不走固定台词池；按钮只提供事件语义，Momo 的回复和状态变化必须结合上下文生成。

4. 按钮也必须使用 cognition context。
   按钮事件和语音/文字一样读取当前 episode、最近事件、episode summary、daily digest、长期记忆、设备状态和当前时间。

5. 文字输入默认播放 TTS。
   打字和说话都被视为与 Momo 对话，Momo 默认用声音回应。

6. 文字输入支持思考模式。
   默认走 `mimo-v2.5` 快路径；思考模式开启时走现有慢路径。

## 范围

本设计覆盖：

- `PetAction` 增加 `state_affect`。
- Guard 对 `state_affect` 和 `state_delta` 做校验与限幅。
- 扩展互动事件类型。
- 前端新增更多互动按钮。
- 后端新增文字对话入口。
- 前端新增文字输入框。
- 语音、文字、按钮共享上下文、记忆、状态联动和 TTS。

本设计不覆盖：

- 后台常驻唤醒。
- 新的天气/代码/浏览器等技能系统。
- 真正的多模态画面理解。
- 把状态系统改成复杂养成游戏数值系统。

## 状态联动

现有 `state_delta` 继续保留，但模型需要同时输出 `state_affect`，用于解释本轮状态变化。

示例：

```json
{
  "reply": "嘿嘿，被夸到了，Momo 又有劲一点啦。",
  "mood": "happy",
  "face_type": "happy",
  "animation": "bounce",
  "voice_style": "happy",
  "vibration": "light",
  "state_delta": {
    "energy": 1,
    "intimacy": 2,
    "hunger": 0,
    "cleanliness": 0,
    "loneliness": -3,
    "sleepiness": 0
  },
  "state_affect": {
    "interaction_tone": "affectionate",
    "pet_effort": "low",
    "emotional_effect": "encouraged",
    "reason": "用户在夸 Momo，Momo 感到被喜欢。"
  },
  "memory_update": {
    "should_save": false,
    "content": ""
  }
}
```

允许的 `interaction_tone`：

- `affectionate`
- `playful`
- `comforting`
- `encouraging`
- `demanding`
- `tiring`
- `quiet`
- `caregiving`
- `neutral`

允许的 `pet_effort`：

- `none`
- `low`
- `medium`
- `high`

允许的 `emotional_effect`：

- `happy`
- `comforted`
- `encouraged`
- `pressured`
- `annoyed`
- `sleepy`
- `calm`
- `lonely_relieved`
- `uncertain`

Guard 限幅建议：

- `energy`: `-5` 到 `+5`
- `intimacy`: `-1` 到 `+2`
- `loneliness`: `-6` 到 `+3`
- `sleepiness`: `-3` 到 `+5`
- `hunger`: 默认 `-3` 到 `+3`，`feed_momo` 和充电相关事件可到 `-8`
- `cleanliness`: 默认 `-2` 到 `+2`，`clean_face` 可到 `+8`

状态变化原则：

- 用户让 Momo 连续做任务，`energy` 应下降，`sleepiness` 可小幅上升。
- 用户夸奖、摸头、抱抱、拍拍，`intimacy` 应上升，`loneliness` 应下降。
- 用户深夜聊天，`sleepiness` 更容易上升。
- 用户表达疲惫、难过、烦躁时，Momo 更倾向 `concerned / comforting`，`intimacy` 可小涨。
- 用户连续戳脸或打扰休息，Momo 可以小生气，但数值不能剧烈惩罚。

## 互动按钮

互动按钮分为两类：养宠互动和陪伴情绪。两类按钮都走 `POST /api/pet/event`，都调用 `mimo-v2.5`，都结合上下文。

### 主按钮区

主按钮区保持轻量，适合常用操作：

- `pet_head`：摸摸头
- `hug`：抱一下
- `stay_with_me`：陪我一下

### 更多互动

更多互动可以折叠或放在次级区域：

- `pet_pat`：拍拍
- `praise_momo`：夸夸
- `feed_momo`：投喂
- `comfort_me`：安慰我
- `encourage_me`：鼓励我
- `listen_to_me`：听我吐槽
- `tuck_in`：哄睡
- `clean_face`：擦擦脸
- `quiet_company`：安静待着
- `take_a_break`：休息会儿

按钮事件 payload 示例：

```json
{
  "event": "feed_momo",
  "payload": {
    "description": "用户投喂了 Momo",
    "interaction_group": "pet_care"
  }
}
```

`feed_momo` 只表示用户主动投喂，不和设备充电绑定。充电仍然是独立设备事件。

同一个按钮必须因上下文不同而有不同表现：

- Momo 刚说饿了时点投喂：更开心，`hunger` 明显下降。
- 刚聊到用户很累时点投喂：回复应更温柔，像“我吃一点就陪你”。
- 连续投喂多次：Momo 应表示已经饱了，`hunger` 不再大幅下降。

## 文字输入

前端新增文字输入框，支持用户直接打字和 Momo 对话。

建议布局：

```text
[输入一句话……                    ][发送]
[思考模式开关]
[按住说话]
[主互动按钮]
[更多互动]
```

发送流程：

```text
用户输入文字
↓
POST /api/text/chat
↓
后端转成 text_message 事件
↓
默认走 mimo-v2.5
↓
思考模式开启时走慢路径
↓
PetBrain 输出 reply / mood / animation / state_delta / state_affect
↓
Guard 校验
↓
写入事件日志、记忆候选和状态
↓
TTS 默认播放
↓
前端更新气泡、表情、动画和状态栏
```

文字请求示例：

```json
{
  "text": "帮我写一个两数之和吧",
  "thinking_mode": false
}
```

文字响应沿用 `PetResponse`，并额外返回：

```json
{
  "user_text": "帮我写一个两数之和吧",
  "text_route": {
    "selected": "fast",
    "thinking_mode": false,
    "brain_provider": "mimo_v25_fast",
    "timings_ms": {}
  }
}
```

文字输入也支持 wake/exit 词：

- `hi momo` / `嗨 momo` / `你好 momo`：唤醒前台 session。
- `momo休息吧` / `先这样` / `不用陪了`：退出当前陪伴。

## 后端接口

新增：

- `POST /api/text/chat`

继续使用：

- `POST /api/pet/event`
- `POST /api/voice/chat`
- `GET /api/pet/state`

`text_message` 需要加入 `ALLOWED_EVENTS`。现有 `voice_message` 保持不变。

所有入口最终都进入同一个 runtime：

```text
voice_message / text_message / button event
↓
RuntimeDispatcher
↓
ContextManager
↓
PetBrain
↓
Guard
↓
State / EventLog / MemoryCandidate / TTS
```

## 前端组件

新增组件：

- `TextInputBar.tsx`
  - 输入框
  - 发送按钮
  - Enter 发送
  - 第一版使用单行输入框，不支持多行换行；移动端主要通过发送按钮提交

调整组件：

- `TouchArea.tsx`
  - 支持主互动和更多互动。
  - 不写固定回复池，只做乐观状态反馈。

- `App.tsx`
  - 新增 `handleTextSubmit`。
  - 文字请求期间进入 `thinking`。
  - 返回后统一走 `applyPetResponse`。
  - 思考模式开关同时影响语音和文字。

前端失败兜底：

- 文本为空不发送。
- 正在请求时禁用发送，避免并发。
- 请求失败时显示温柔文案，不丢掉用户输入。
- TTS 播放失败不影响文字显示。

## Prompt 调整

系统提示需要补充：

- 按钮事件也要结合当前上下文，不要只根据按钮名机械回复。
- Momo 可以完成简单任务，但语气仍保持宠物感。
- 状态变化要解释在 `state_affect.reason` 中。
- 不要为了状态变化而夸大情绪。

输出 schema 增加 `state_affect`。

## 数据与日志

`raw_event_log` 继续记录：

- `event_type`
- `user_text`
- `pet_reply`
- `state_before_json`
- `state_after_json`
- `mood_after`

后续可扩展记录：

- `state_affect_json`

第一版需要迁移 `raw_event_log`，新增 `state_affect_json` 字段，方便以后分析“为什么状态这么变”。

## 测试计划

后端测试：

- `PetAction` 支持 `state_affect`。
- Guard 接受合法 `state_affect`，拒绝非法枚举。
- Guard 对 `state_delta` 按事件类型限幅。
- `text_message` 能走 dispatcher。
- `/api/text/chat` 默认走 fast brain。
- `/api/text/chat` 在 `thinking_mode=true` 时走慢路径。
- 文字输入也能触发 wake/exit。
- 按钮事件能拿到 cognition context。
- `feed_momo` 在连续多次时不会无限降低 hunger。

前端测试：

- 输入框空文本不发送。
- 输入框提交时调用 `/api/text/chat`。
- 思考模式开启时请求带 `thinking_mode=true`。
- 文字响应回来后更新气泡、表情、状态并播放 TTS。
- 更多互动按钮发送正确事件名。
- 请求失败时显示 fallback，输入内容不被误清空。

手机 E2E：

- 打字“帮我写两数之和”，Momo 能给出正常帮助，不说“不会”。
- 打字“我有点累”，Momo 温柔回应并播放 TTS。
- 点击投喂、夸夸、安慰我，回复都结合最近上下文。
- 连续让 Momo 做任务，`energy` 有下降趋势。
- 夸 Momo 后，`intimacy` 小幅上升。
- 深夜或睡前相关互动，`sleepiness` 有合理变化。

## 成功标准

- 用户可以用语音或文字自然和 Momo 对话。
- 所有按钮都能生成非固定、上下文相关的回应。
- Momo 的状态会随着对话和按钮互动产生可解释的变化。
- 状态变化不会一轮暴涨暴跌。
- TTS 默认在文字和语音回复中播放。
- 现有 Stage 1 到 Stage 3.7 的上下文、记忆、摘要和语音能力不回归。
