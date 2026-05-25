from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.runtime.context import RuntimeContext
from app.runtime.events import PetEvent
from app.runtime.interaction_catalog import button_event_ids, get_interaction


BUTTON_EVENTS = set(button_event_ids())


OUTPUT_SCHEMA_HINT = {
    "reply": "自然简短的回复；需要解释或完成任务时可以适度展开；不输出 kaomoji",
    "mood": "idle/happy/sad/sleepy/angry/shy/thinking/concerned/excited/lonely",
    "face_type": "同 mood 枚举",
    "animation": "breathing/bounce/droop/slowBlink/shake/wiggle/blink/tilt/jump/small",
    "voice_style": "soft/normal/happy/sleepy/shy",
    "vibration": "none/light/medium",
    "intent": "这次行为意图",
    "autonomy_notes": "简短说明豆豆为什么这样反应",
    "behavior_intent": "可选：soft_comfort/clingy_happy/clingy_wronged_happy/lazy_busy/quiet_sleepy/playful_proud/confused_wronged/neutral_companion",
    "behavior_plan": [
        {"action": "idle/waiting/review/waving/jumping/failed/running/running-left/running-right", "slot": "before_speech/speech/after_speech/idle_after", "duration_ms": 600-2500}
    ],
    "state_delta": {
        "energy": 0,
        "intimacy": 0,
        "hunger": 0,
        "cleanliness": 0,
        "loneliness": 0,
        "sleepiness": 0,
    },
    "state_affect": {
        "interaction_tone": "affectionate/playful/comforting/encouraging/demanding/tiring/quiet/caregiving/neutral",
        "pet_effort": "none/low/medium/high",
        "emotional_effect": "happy/comforted/encouraged/pressured/annoyed/sleepy/calm/lonely_relieved/uncertain",
        "reason": "一句话说明为什么这样影响豆豆状态",
    },
    "memory_update": {"should_save": False, "content": ""},
}

SKILL_PLAN_SCHEMA = {
    "skill_requests": [
        {"skill_id": "weather.current", "payload": {"location": "current"}}
    ],
    "reason": "简短说明为什么需要或不需要 skill",
}


def serialize_for_prompt(
    event: PetEvent,
    pet_state: Dict[str, Any],
    cognition_context: Optional[Dict[str, Any]] = None,
    skill_results: Optional[List[Dict[str, Any]]] = None,
    device_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a trimmed, deduplicated prompt payload.

    Only includes cognition_context (not old recent_dialogue/recent_memory).
    """
    payload: Dict[str, Any] = {
        "event": event.dict(),
        "pet_state": pet_state,
    }
    if cognition_context:
        payload["cognition_context"] = cognition_context
    if device_state:
        payload["device_state"] = device_state
    if skill_results:
        payload["skill_results"] = skill_results
    return payload


def build_pet_messages(
    settings: Settings, event: PetEvent, context: RuntimeContext
) -> List[Dict[str, str]]:
    system_prompt = settings.persona_config.get("system_prompt", "")
    reply_policy = settings.persona_config.get("reply_policy") or {}
    if event.type == "voice_message":
        system_prompt += (
            "\n\n语音事件规则：\n"
            "1. 优先回应用户情绪，而不是急着给建议。\n"
            "2. 如果用户疲惫、烦躁、低落，语气要温柔。\n"
            "3. 如果识别置信度低，不要假装完全听懂，可以说刚刚有点没听清。\n"
            "4. 不要复读用户整句话。\n"
            "5. 很多时候陪着就好，不要强行解决问题。"
        )
    if event.type == "text_message":
        system_prompt += (
            "\n\n文字事件规则：\n"
            "1. 用户是在打字和你聊天，默认也要自然回应。\n"
            "2. 可以完成简单任务，但仍保持豆豆的语气。\n"
            "3. 不要因为自己是宠物就故意说不会。\n"
        )
    if event.type in BUTTON_EVENTS:
        system_prompt += (
            "\n\n按钮互动规则：\n"
            "1. 按钮事件也必须结合最近上下文，不要只根据按钮名机械回复。\n"
            "2. 如果用户连续点同一按钮，要表现出自然变化。\n"
            "3. 投喂(feed_momo)是用户主动投喂，不等于手机充电。"
        )
        interaction = get_interaction(event.type)
        if interaction:
            semantics = ", ".join(
                f"{k}({v})" for k, v in interaction.state_semantics.items()
            ) or "无"
            system_prompt += (
                f"\n\n当前按钮语义：\n"
                f"- 互动名称：{interaction.label}\n"
                f"- 分组：{interaction.group}\n"
                f"- 状态含义：{semantics}\n"
                f"- LLM 描述：{interaction.description}\n"
            )
    if event.source == "proactive":
        system_prompt += (
            "\n\n主动陪伴规则：\n"
            "1. 主动回复要更短、更轻，不要像通知。\n"
            "2. 不要催促用户，不要连续抱怨没人理。\n"
            "3. 可以根据时间、电量和记忆轻轻表达状态。\n"
        )
    if context.skill_results:
        system_prompt += (
            "\n\nSkill 结果规则：\n"
            "1. skill 只提供事实，最终表达必须仍像豆豆。\n"
            "2. skill 失败时温柔兜底，不暴露接口错误。\n"
            "3. 不要说\u201c根据 API/数据库/工具结果\u201d。"
        )

    system_prompt += (
        "\n\n状态联动规则：\n"
        "1. 你必须根据本轮互动和上下文输出 state_affect。\n"
        "2. state_delta 要保守，不要让数值暴涨暴跌。\n"
        "3. energy = 白天活力/陪玩能力。用户让你连续做任务时 energy 降；投喂、夸奖、充电时 energy 升。\n"
        "4. sleepiness = 作息困意。夜间、哄睡、长时间闲置时升；早晨、充电、陪玩成功时降。\n"
        "5. 用户夸你、摸你、抱你或陪你时，intimacy 可以上升，loneliness 可以下降。\n"
        "6. 按钮事件也必须结合最近上下文，不要只根据按钮名机械回复。\n"
        "7. pet_effort 表示本轮你（豆豆）付出的精力：\n"
        "   - none: 闲聊、打招呼 → 无疲劳\n"
        "   - low: 简单回答、按钮互动 → 极小或无变化\n"
        "   - medium: 需要思考的回答 → energy 小幅下降\n"
        "   - high: 长任务、写代码、详细解释 → energy 明显下降，sleepiness 小幅上升\n"
    )

    # Context profile awareness
    profile = (context.cognition_context or {}).get("context_profile", "")
    if profile in ("fast_reply", "fast_companion", "tool"):
        system_prompt += (
            "\n\n快速陪伴模式：回复 1-2 句，自然、轻松，不要长篇大论。"
            "\n如果用户问回忆类问题且记忆卡片中没有足够信息，"
            "自然地说「这个我得认真翻一下记忆，打开思考模式我再帮你回忆」，不要编造。"
            "\n如果用户问复杂问题或需要详细分析，简短回答并建议打开思考模式。"
        )
    elif profile in ("thinking", "long_task"):
        system_prompt += "\n\n深度模式：用户需要详细回答，可以展开，但不输出思考过程。参考小本本里的记忆。"
    elif profile == "proactive":
        system_prompt += "\n\n主动陪伴模式：回复 1 句，轻声问候，不要催促。"
    elif profile == "recall":
        system_prompt += "\n\n回忆模式：用户在问之前的事，尽力回忆并回答，可以稍长。"

    # Use serializer instead of raw context.dict()
    payload = serialize_for_prompt(
        event=event,
        pet_state=context.pet_state,
        cognition_context=context.cognition_context if context.cognition_context else None,
        skill_results=context.skill_results or None,
        device_state=context.device_state or None,
    )
    if reply_policy:
        payload["response_policy"] = reply_policy
    payload["output_schema"] = OUTPUT_SCHEMA_HINT

    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]


FAST_REPLY_SCHEMA = {
    "reply": "自然简短的回复，不超过 80 字",
    "mood": "idle/happy/sad/sleepy/angry/shy/thinking/concerned/excited/lonely",
    "action": "idle/waiting/review/waving/jumping/failed/running/running-left/running-right",
}


def build_fast_reply_messages(
    settings: Settings, event: PetEvent, context: RuntimeContext
) -> List[Dict[str, str]]:
    """Build minimal prompt for fast reply mode. Only includes essential context."""
    system_prompt = settings.persona_config.get("system_prompt", "")

    system_prompt += (
        "\n\n快速回复模式："
        "\n1. 用 1-2 句简短自然的话回复，不超过 80 字。"
        "\n2. 输出一个 action 表示豆豆的动作/表情。"
        "\n3. 不要输出 state_delta、memory_update、behavior_plan 等字段。"
        "\n4. 不要输出思考过程。"
        "\n5. 保持豆豆的语气，温柔、可爱、自然。"
    )

    if event.type == "voice_message":
        system_prompt += (
            "\n6. 如果识别置信度低，可以说刚刚有点没听清。"
        )

    # Build minimal payload — only essential fields
    cognition = context.cognition_context or {}
    recent_events = cognition.get("recent_exact_events", [])[-1:]  # latest 1 turn only
    memory_cards = cognition.get("memory_cards") or {}

    # Select 1 item from each card file
    user_items = memory_cards.get("user_preferences", [])
    memory_items = memory_cards.get("momo_memories", [])
    memory_hints = []
    if user_items:
        memory_hints.append(user_items[-1])
    if memory_items:
        memory_hints.append(memory_items[-1])

    user_text = str(event.payload.get("user_text") or event.payload.get("text") or "")

    payload = {
        "user_input": user_text,
        "recent_dialogue": recent_events,
        "pet_state": {
            "mood": context.pet_state.get("mood", "idle"),
            "energy": context.pet_state.get("energy", 50),
            "intimacy": context.pet_state.get("intimacy", 0),
            "sleepiness": context.pet_state.get("sleepiness", 0),
        },
        "memory_hints": memory_hints,
        "response_schema": FAST_REPLY_SCHEMA,
    }

    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]


def build_skill_plan_messages(
    settings: Settings, event: PetEvent, context: RuntimeContext,
    skill_catalog: str = "",
) -> List[Dict[str, str]]:
    catalog = skill_catalog or "weather.current, device.info"
    system_prompt = (
        settings.persona_config.get("system_prompt", "")
        + "\n\n你现在只决定是否需要调用 runtime skill。"
        "不要生成最终回复，不要安慰用户。"
        "只有用户需要天气、设备状态或外部事实时才请求 skill。"
        "最多请求 2 个 skill。"
        f"可用 skill: {catalog}。"
        "必须只输出 JSON。"
    )

    # Use serializer instead of raw context.dict()
    payload = serialize_for_prompt(
        event=event,
        pet_state=context.pet_state,
        cognition_context=context.cognition_context if context.cognition_context else None,
        device_state=context.device_state or None,
    )
    payload["output_schema"] = SKILL_PLAN_SCHEMA

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
