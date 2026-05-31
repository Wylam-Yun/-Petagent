# PetAgent V1.6：豆豆颜表情与空闲气泡体验 Spec

**日期：** 2026-05-31  
**项目路径：** `/Users/wylam/Documents/workspace/Petagent`  
**目标设备：** Nubia Android 手机，Termux 后端，本机 WebView/浏览器前端。

## 目标

V1.6 要解决两个用户能直接感受到的问题：

1. 豆豆对话时没有稳定的颜表情反馈，看起来不像是在根据语境反应。
2. 豆豆空闲时缺少桌宠生命感，不像一只住在手机里的调皮小猫。

V1.6 不重做语音链路、记忆链路或 LLM provider。它只定义：

- 成功对话时，LLM 如何输出表情字段；
- 前端如何展示表情和气泡；
- 空闲时什么时候触发 LLM 生成桌宠气泡；
- 系统能给豆豆什么“灵感”，以及哪些内容绝不能由规则写死。

## 产品原则

1. **豆豆是桌宠，不是助手外壳。** 它是住在手机里的调皮小猫桌宠，会陪用户聊天，也会有自己的小动作。
2. **表情由语境决定。** 对话成功时，模型必须根据用户语境选择颜表情，而不是前端固定套 mood。
3. **台词由模型生成。** 空闲气泡不能规则拼句子，也不能从固定模板池里抽一句。规则只给场景和建议，最终台词由 LLM 生成。
4. **只用第一人称。** 豆豆台词里主语必须用“我”，不要自称“豆豆”。UI 标题仍然可以显示“豆豆”。
5. **失败就失败。** ASR/LLM/TTS 失败不能伪装成正常回复；空闲 LLM 失败就安静。
6. **不突然出声。** 空闲气泡只显示文字、表情和动作，不合成 TTS，不主动播放声音。
7. **灵动但不打扰。** 豆豆可以调皮，但要低频、短句、轻量，不制造通知骚扰。

## 非目标

- 不新增用户可见的“表情模式”或“空闲模式”开关。
- 不让模型自由生成任意 kaomoji 字符串。
- 不让颜表情进入 TTS 文本。
- 不把空闲气泡写入长期记忆。
- 不因为空闲气泡失败而显示本地兜底台词。
- 不恢复 Thinking Mode 或 Recall Mode UI。
- 不把空闲气泡设计成主动语音通知。

## 当前问题

### 对话表情不是稳定契约

当前 persona 明确要求“不要输出 kaomoji”，统一对话 schema 主要是：

```json
{
  "reply": "...",
  "mood": "...",
  "action": "..."
}
```

前端已有 `faces.ts` 的颜表情表，但只是根据 `face_type/mood` 做默认映射。模型没有显式选择表情，所以用户很难感到“豆豆在根据我刚才的话做表情”。

### 桌宠空闲生命感不足

当前 proactive/idle 机制偏规则化。空闲台词如果由规则 provider 或前端固定文案生成，会很快显得机械。用户想要的是：豆豆空闲时像一只有自己生活的小猫，但具体说什么仍由模型生成。

### 主语风格不自然

豆豆如果每句话都说“豆豆怎样、豆豆怎样”，会像模板台词。V1.6 要把台词风格改成第一人称：“我刚刚没有偷懒。”而不是“豆豆刚刚没有偷懒。”

## 豆豆身份设定

豆豆是住在手机里的调皮小猫桌宠。

它可以：

- 正常回答用户问题；
- 陪用户聊天、安慰、鼓励；
- 开心、害羞、委屈、困、疑惑、小生气；
- 偷懒、偷看用户、偷吃零食、嘴硬；
- 在用户不说话时做轻量小动作。

它不应该：

- 像客服或通用 AI 助手一样机械；
- 像恋人一样越界；
- 在用户严肃或低落时强行卖萌；
- 用调皮台词掩盖技术失败；
- 高频打扰用户。

## 对话输出契约

所有成功的前景对话，包括文字对话和 ASR 成功后的语音对话，都应该使用统一输出契约。

表情选择规则应写进 system prompt 和 response schema。模型每轮根据以下输入选择 `expression_key`：

- system prompt 里的豆豆身份、语气和表情白名单；
- 当前用户输入或当前空闲事件；
- 最近 5 轮真实对话；
- `memory.md` 中当前 10 条长期记忆；
- 当前 `pet_state`，例如 energy、sleepiness、loneliness；
- 当前事件类型，例如 text、voice、button、ambient bubble；
- 输出 schema 中对 `expression_key`、`action`、`voice_style` 的枚举约束。

其中 system prompt 和 response schema 决定“能选什么、怎么选”；当前事件和最近对话决定“这次该选什么”；memory 只辅助理解用户偏好和长期关系，不能替代当前语境。

### LLM 输出字段

推荐目标结构：

```json
{
  "reply": "今天是星期日呀，我没有记错。",
  "mood": "happy",
  "expression_key": "idle_wink",
  "action": "happy",
  "voice_style": "happy"
}
```

字段含义：

| 字段 | 用途 | 是否进入 TTS |
| --- | --- | --- |
| `reply` | 给用户看的正式回复，也是语音回复文本 | 是 |
| `mood` | 状态、颜色、动画兜底 | 否 |
| `expression_key` | 前端显示的颜表情 key | 否 |
| `action` | 桌宠动作 key | 否 |
| `voice_style` | TTS 风格 | 否，作为 TTS 参数使用 |

规则：

- `reply` 里不能包含颜表情。
- `reply` 必须使用第一人称，不要自称“豆豆”。
- `mood` 必须来自白名单；缺失或非法时 fallback 到 `idle`。
- `expression_key` 必须来自白名单。
- `action` 必须来自动作白名单。
- 如果 `expression_key` 不合法，后端按 `mood` fallback。
- 如果 `expression_key` 和 `mood` 都不合法，最终 fallback 到 `idle_soft`。
- 如果 LLM 没有返回有效 `reply`，本轮失败，不生成假回复。

## 颜表情白名单

第一版定义以下 `expression_key`：

| key | 颜表情 | 主要语境 |
| --- | --- | --- |
| `idle_soft` | `(・ω・)` | 默认、普通陪伴 |
| `idle_wink` | `(｡•̀ᴗ-)✧` | 轻松、自信、小得意 |
| `happy` | `(^▽^)` | 开心、正向回应 |
| `happy_big` | `(≧▽≦)` | 很开心、被夸、亲近 |
| `excited` | `٩(ˊᗜˋ*)و` | 兴奋、鼓励、任务完成 |
| `shy` | `(//▽//)` | 被夸、被摸、害羞 |
| `clingy` | `(*ﾉωﾉ)` | 撒娇、想贴近用户 |
| `thinking` | `(・・?)` | 思考、没完全确定 |
| `confused` | `(。ヘ°)` | 疑惑、信息不足 |
| `concerned` | `(´・ω・)` | 担心、安慰用户 |
| `sad` | `(｡•́︿•̀｡)` | 用户难过、豆豆低落 |
| `crying` | `(╥﹏╥)` | 明显难过，低频使用 |
| `sleepy` | `(-_-) zzz` | 困、夜晚、休息 |
| `tired` | `(￣o￣)` | 累、省电、懒懒的 |
| `annoyed` | `(｀へ´)` | 被连续戳、小生气 |
| `wronged` | `(｡•́︿•̀｡)` | 委屈、装可怜 |
| `proud` | `(๑•̀ㅂ•́)و✧` | 做成事、小骄傲 |
| `playful` | `(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧` | 调皮、开玩笑、逗用户 |
| `lonely` | `(._.)` | 很久没互动、想被陪 |
| `calm` | `( ˘ω˘ )` | 安静陪伴、温柔收尾 |

如果某个颜表情在 Nubia 屏幕上显示过宽或不稳定，允许只修改映射值，不改变 `expression_key`。

### Mood 到表情 fallback

当模型没有给出合法 `expression_key` 时，按以下规则兜底：

| mood | fallback expression_key |
| --- | --- |
| `idle` | `idle_soft` |
| `happy` | `happy` |
| `sad` | `sad` |
| `sleepy` | `sleepy` |
| `angry` | `annoyed` |
| `shy` | `shy` |
| `thinking` | `thinking` |
| `concerned` | `concerned` |
| `excited` | `excited` |
| `lonely` | `lonely` |
| unknown | `idle_soft` |

## 对话场景表情规则

这些规则用于 prompt 约束和测试，不是规则生成回复。

| 用户场景 | 豆豆表现 | 推荐表情 |
| --- | --- | --- |
| 普通问问题 | 直接答，不绕 | `idle_wink`, `thinking`, `proud` |
| 用户低落 | 软一点、陪伴，不说教 | `concerned`, `calm`, `sad` |
| 用户想安静 | 少说，甚至一句就够 | `calm`, `sleepy`, `idle_soft` |
| 用户夸豆豆 | 害羞、开心、撒娇 | `shy`, `happy_big`, `clingy` |
| 用户责怪听不清 | 承认问题，不用撒娇掩盖 | `wronged`, `confused`, `concerned` |
| 用户逗它/欺负它 | 小生气、委屈，但不攻击 | `annoyed`, `wronged` |
| 用户开玩笑 | 嘴硬、装忙、调皮 | `playful`, `proud`, `idle_wink` |
| 用户认真求助 | 清楚帮忙，少卖萌 | `thinking`, `proud` |
| 严重安全/健康风险 | 认真、稳，不调皮 | `concerned` |
| 亲密但越界 | 保持小猫桌宠边界 | `shy`, `clingy`, `calm` |
| 用户说别烦我 | 退后、少说 | `calm`, `wronged`, `sleepy` |
| 很久没互动后回来 | 有一点想念或嘴硬 | `lonely`, `clingy`, `happy` |

## 空闲气泡总原则

空闲气泡是豆豆在用户不说话时的桌宠表现。

它必须满足：

- 由 LLM 生成具体台词；
- 只显示一条短气泡；
- 不合成 TTS；
- 不写入长期记忆；
- 不打断当前对话、录音、输入或播放；
- 失败就安静；
- 台词全部使用第一人称“我”。

## 空闲触发节奏

从一轮对话真正结束后开始计时。

触发退避序列：

```text
5min -> 10min -> 20min -> 40min -> 90min -> 90min...
```

含义：

1. 对话结束 5 分钟后，可以触发第一次空闲气泡。
2. 如果用户没有互动，再过 10 分钟触发第二次。
3. 再过 20 分钟触发第三次。
4. 再过 40 分钟触发第四次。
5. 之后最多每 90 分钟触发一次。

任何有效用户互动都会重置 idle 计数，下次重新从 5 分钟开始。

第一次 5 分钟触发时就允许出现调皮小剧场，不需要先输出“我还在”这类确认存在的固定风格。

## 什么叫对话结束

| 场景 | 结束时间 |
| --- | --- |
| 文字对话成功 | 后端返回有效回复，前端显示后 |
| 语音对话成功且有 TTS | TTS 播放结束后 |
| 语音对话成功但无 TTS | 前端显示有效回复后 |
| ASR 失败 | 错误显示后进入 idle，但不算成功对话 |
| LLM 失败 | 错误显示后进入 idle，但不算成功对话 |
| TTS 失败 | 文本回复已成功，错误状态结束后 |
| 按钮互动成功 | 前端完成显示后 |

ASR/LLM/TTS 失败后不设置特殊空闲冷却期，按正常 idle 规则处理。但失败本身不能被调皮台词伪装成成功回复。

## 空闲触发前提

只有同时满足以下条件，前端才允许检查或触发空闲气泡：

- 页面可见；
- 浏览器/WebView 在前台；
- 手机处于亮屏可交互状态；
- 豆豆 UI phase 是 `idle`；
- `busy === false`；
- 用户没有正在输入；
- 没有正在录音；
- 没有等待 LLM 回复；
- 没有等待 TTS job；
- 没有播放 TTS；
- 没有用户正在听音频；
- 最近一次 heartbeat 正常。

后端也需要二次校验前端心跳。如果前端心跳过期，不调用 LLM 生成空闲气泡。

## 空闲限频与去重

### 每日总量

按设备本地日期统计，豆豆每天最多主动冒泡 10 次。日期边界以设备本地日期为准，不以 UTC 日期为准。

达到上限后，当天不再触发空闲气泡。用户主动对话不受影响。

### suggested_activity 去重

同一个 `suggested_activity` 每天最多出现 2 次。

对于强记忆点小剧场，建议每天最多 1 次：

- `sneak_snack`
- `watch_tiny_show`
- `claim_corner`
- `pretend_busy`

连续两次空闲气泡不能使用同类活动。比如刚刚是偷吃，下一次不能还是偷吃；刚刚是装忙，下一次不能还是装忙。

### 失败计数

空闲气泡只有在 LLM 返回有效输出、后端校验通过，并且前端仍然处于可展示状态时，才计入每日总次数、activity 次数和退避 step。

以下情况都不计数，也不推进退避 step：

- LLM 请求失败；
- LLM 请求超时；
- LLM 返回非 JSON；
- LLM 返回 schema 不合法；
- `bubble` 内容校验失败；
- 没有可用 `suggested_activity`；
- 后端触发后，前端在展示前进入输入、录音、等待或播放状态；
- 前端明确取消本次空闲展示。

## 空闲活动建议

系统可以给 LLM 一个 `suggested_activity` 作为灵感，但不能根据这个 activity 规则生成台词。

第一版活动建议：

| suggested_activity | 含义 | 推荐 expression_key | 推荐 action |
| --- | --- | --- | --- |
| `stay_near` | 靠近用户，轻轻待着 | `idle_soft`, `calm`, `clingy` | `idle`, `greet` |
| `pretend_busy` | 嘴硬地假装在忙、翻小本本 | `idle_wink`, `proud`, `playful` | `pretend_busy`, `remember` |
| `patrol` | 在手机里巡逻、看家 | `proud`, `idle_wink`, `happy` | `wander`, `running` |
| `self_groom` | 整理毛毛、洗脸 | `calm`, `happy`, `shy` | `self_groom` |
| `sneak_snack` | 偷吃零食、小鱼干心虚感 | `playful`, `shy`, `wronged` | `sneak_eat` |
| `lazy_save_power` | 偷懒、省电、趴一会儿 | `tired`, `sleepy`, `idle_wink` | `lazy_idle`, `nap` |
| `peek_user` | 偷看用户有没有回来 | `clingy`, `idle_wink`, `lonely` | `listen`, `greet` |
| `claim_corner` | 占住一个屏幕角落、小小捣乱 | `playful`, `proud`, `annoyed` | `tease`, `happy` |
| `watch_tiny_show` | 看手机里的小剧场、看到关键地方 | `playful`, `thinking`, `idle_wink` | `watch_tv`, `pretend_busy` |
| `quiet_guard` | 安静看家、陪着用户 | `calm`, `idle_soft`, `concerned` | `idle`, `listen` |
| `sleepy_curl` | 困了，蜷起来休息 | `sleepy`, `tired`, `calm` | `nap`, `lazy_idle` |

这些是给模型的灵感，不是固定剧本。模型可以在推荐表情和动作中选择，也可以在白名单内选择更符合当前语境的其他 `expression_key` 或 `action`。系统不能根据这张表直接生成台词。

## 空闲 LLM 请求契约

触发空闲气泡时，后端给 LLM 的 payload 应该类似：

```json
{
  "event_type": "ambient_bubble",
  "scene": "post_conversation_idle",
  "idle_step": 1,
  "idle_minutes": 5,
  "suggested_activity": "sneak_snack",
  "tone": "调皮、轻、不要打扰",
  "constraints": {
    "max_chars": 20,
    "first_person_only": true,
    "no_tts": true,
    "do_not_start_complex_topic": true
  },
  "pet_state": {
    "energy": 42,
    "sleepiness": 50,
    "loneliness": 30
  },
  "recent_dialogue": []
}
```

LLM 输出：

```json
{
  "bubble": "刚刚那个不是我藏的。",
  "expression_key": "playful",
  "action": "sneak_eat"
}
```

约束：

- `bubble` 最多 20 个中文字符左右。
- `bubble` 只能一句。
- `bubble` 必须使用“我”，不能自称“豆豆”。
- 不主动开启复杂话题。
- 不假装知道系统没有记录的事。
- 不输出颜表情到 `bubble`。
- 不输出思考过程。
- 不输出内部字段名。

## 空闲场景类型

第一版保留这些 scene：

| scene | 触发语境 |
| --- | --- |
| `post_conversation_idle` | 成功对话结束后进入空闲 |
| `page_return` | 用户离开页面后又回来 |
| `night_quiet` | 夜晚或睡前时间 |
| `battery_low` | 电量低 |
| `charging_started` | 开始充电 |
| `long_idle_return` | 很久没有互动后用户回来 |

`post_conversation_idle` 是主路径。其他 scene 也必须服从每日总量、activity 去重、页面可见和 not busy 条件。

## 禁止规则生成台词

系统不能写这种逻辑：

```text
if suggested_activity == "sneak_snack":
  bubble = "我没有偷吃，是它自己过来的。"
```

系统允许做的事：

- 判断是否触发；
- 选择 `suggested_activity`；
- 提供状态和最近上下文；
- 限制输出长度；
- 校验 `expression_key` 和 `action`；
- 记录限频；
- LLM 失败时安静退出。

系统不允许做的事：

- 固定生成气泡文本；
- 根据 activity 拼接模板句；
- LLM 失败后用本地台词兜底；
- 强制豆豆说某一句话；
- 让空闲气泡进入 TTS；
- 把空闲气泡写入长期记忆。

## 前端展示规则

### 对话回复

成功对话：

- 气泡显示 `reply`；
- 豆豆脸显示 `expression_key` 映射出的颜表情；
- 动作使用 `action`；
- TTS 只读 `reply`。

失败对话：

- 显示明确错误；
- 不显示假回复；
- 不触发 TTS；
- 不记录为成功对话。

### 空闲气泡

空闲气泡：

- 气泡显示 `bubble`；
- 豆豆脸显示 `expression_key`；
- 动作使用 `action`；
- 不调用 TTS；
- 显示时间要短，不能长期遮挡用户；
- 用户一旦开始输入、录音或对话，空闲气泡应让位。

## 后端校验规则

### 对话输出校验

- `reply` 为空：失败。
- `reply` 含颜表情：应清理或判为无效，具体实现时决定。
- `reply` 自称“豆豆”：应清理、重试或判为风格错误，具体实现时决定。
- `mood` 缺失或非白名单：fallback 到 `idle`。
- `expression_key` 非白名单：按 `mood` fallback。
- `expression_key` 与 `mood` 都非法：fallback 到 `idle_soft`。
- `action` 非白名单：fallback 到 `idle` 或 mood 对应动作。
- `voice_style` 非白名单：fallback 到 `soft`。

### 空闲输出校验

- `bubble` 为空：不显示。
- `bubble` 超长：不显示，不截断。
- `bubble` 含颜表情：不显示或清理。
- `bubble` 自称“豆豆”：不显示或重试一次。
- `bubble` 不使用第一人称“我”：不显示或重试一次。
- `expression_key` 非白名单：fallback 到 `idle_soft`。
- `action` 非白名单：fallback 到 `idle`。

空闲输出失败不能显示本地台词兜底。

空闲输出失败不能计入每日总次数、activity 次数或退避 step。

## 记忆与历史

对话成功仍按 V1.5 的成功轮次规则记录历史和触发记忆总结。

空闲气泡默认不算成功对话轮次，不触发记忆总结，不写入 `memory.md`。

如果用户对空闲气泡做出回应，那么用户的回应是新的真实对话输入，后续按正常对话链路处理。

## 测试设计

### 后端单元测试

- 对话输出 schema 快照包含 `reply`、`mood`、`expression_key`、`action`、`voice_style` 以及对应 enum。
- 合法 `expression_key` 能通过 guard。
- 非法 `expression_key` 按 `mood` fallback。
- `expression_key` 和 `mood` 都非法时 fallback 到 `idle_soft`。
- `mood` 缺失、非法、类型错误时 fallback 到 `idle`。
- `action` 缺失、非法、类型错误时 fallback 到 `idle` 或约定动作。
- `voice_style` 缺失、非法、类型错误时 fallback 到 `soft`。
- `reply` 不进入颜表情。
- `reply` 只进入 TTS 文本，`expression_key` 不进入 TTS。
- TTS 使用最终清洗后的 `reply`，不是原始 LLM 文本。
- LLM 请求失败、超时、非 JSON、schema 错误、校验失败时不会生成假回复。
- Prompt payload 包含当前输入、最近 5 轮真实对话、当前 10 条 `memory.md`、`pet_state`、表情白名单和 response schema。
- Prompt payload 在空 memory、超长输入、特殊字符和 JSON 注入文本下仍保持结构正确。
- 空闲 bubble 输出为空时不显示、不兜底。
- 空闲 bubble 含“豆豆”时按风格错误处理。
- 空闲 bubble 不含第一人称“我”时按风格错误处理。
- 空闲 bubble 超长时不展示、不截断。

### 空闲调度测试

- 对话结束后 5 分钟才允许第一次触发。
- 对话结束后 4 分 59 秒不触发，5 分 00 秒才允许触发。
- 语音回复有 TTS 时，5 分钟从 TTS 播放结束开始计算；TTS 播放期间即使超过 5 分钟也不触发。
- 后续触发间隔为 10、20、40、90、90 分钟。
- 用户互动后 idle step 重置。
- 页面不可见时不触发。
- busy、录音、等待 LLM、等待 TTS、播放 TTS 时不触发。
- 空闲触发到期的同一刻，如果用户开始输入、录音或发送消息，空闲气泡不显示，也不占用次数。
- 每日最多 10 次。
- 同一 `suggested_activity` 每日最多 2 次。
- 强记忆点小剧场每日最多 1 次。
- 连续两次不能同类 activity。
- 每日总次数、activity 次数、强记忆 activity 次数按设备本地日期跨天重置。
- 页面刷新、切后台再回来、后端进程重启后，退避 step、每日次数和 activity 次数按持久化策略恢复。
- LLM 失败、校验失败、没有可选 activity、前端展示前取消时，不计入每日次数、activity 次数或退避 step。

### 空闲生成测试

- 后端传给 LLM 的空闲 payload 只包含 scene、idle_step、idle_minutes、suggested_activity、tone、constraints、pet_state、recent_dialogue 和必要 schema。
- 本地代码不存在根据 `suggested_activity` 生成固定 bubble 的分支。
- LLM 请求失败、超时、非 JSON、schema 错误、内容校验失败时，不显示默认文案、模板文案或历史缓存文案。
- 空闲 bubble 不进入 TTS。
- 空闲 bubble 不写入 `memory.md`。
- 空闲 bubble 不计入成功对话轮次。
- 成功空闲 bubble 的来源应可标记为 `llm_generated`。

### 前端测试

- 对话回复显示 `reply` 和 `expression_key`。
- TTS 播放只使用 `reply`。
- 空闲气泡不调用 TTS。
- 用户输入中不触发空闲气泡。
- 页面不可见不触发空闲气泡。
- 锁屏、后台、WebView 不在前台或 screen-on 状态不可用时不触发空闲气泡。
- 空闲气泡显示期间用户开始交互，气泡让位。
- 前端能够暴露当前渲染的 `expression_key`，供自动化和 Nubia 真机检查。

### 调试与可观测性测试

实现时需要提供调试状态，供自动化和 Nubia 真机验证读取：

- 当前是否 eligible；
- 当前 block reason；
- next trigger time；
- 当前 backoff step；
- 当日主动冒泡总数；
- 当日各 activity 次数；
- 当日强记忆 activity 次数；
- last suggested_activity；
- last rendered expression_key；
- last validation failure reason；
- last submitted TTS text；
- last idle bubble source，例如 `llm_generated`。

### Nubia 真机验证

必须在 Nubia 上验证：

- 对话成功后表情能随 `expression_key` 改变。
- TTS 不读颜表情。
- 对话结束 5 分钟后可以触发一次 LLM 空闲气泡。
- 后续退避节奏至少用调试时间缩放验证。
- 页面切后台不触发。
- 锁屏、息屏、WebView 不在前台时不触发。
- 录音、等待回复、播放语音时不触发。
- 一天 10 次上限可通过调试日期或计数注入验证。
- activity 去重、强记忆 activity 限频和连续同类禁止可通过调试接口验证。
- 真机上可以看到当前渲染的 `expression_key` 和实际提交给 TTS 的文本。

## 验收标准

V1.6 完成时，必须满足：

- 成功对话响应包含合法 `expression_key`。
- 前端使用 `expression_key` 显示颜表情。
- `reply` 不包含颜表情，TTS 只读 `reply`。
- 豆豆台词使用第一人称，不自称“豆豆”。
- 空闲气泡由 LLM 生成，不由规则生成。
- 空闲气泡首次触发为对话结束 5 分钟后。
- 后续触发按 10/20/40/90 退避。
- 页面不可见、busy、输入、录音、等待和播放时不触发。
- 每日主动冒泡最多 10 次。
- 同类 activity 不连续，同一 activity 每日限频。
- 空闲 LLM 失败时安静，不显示本地兜底台词。
