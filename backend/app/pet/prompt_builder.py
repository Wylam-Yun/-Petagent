from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.runtime.context import RuntimeContext
from app.runtime.events import PetEvent


BUTTON_EVENTS = {
    "pet_head", "poke_face", "hug",
    "pet_pat", "praise_momo", "feed_momo",
    "stay_with_me", "comfort_me", "encourage_me", "listen_to_me",
    "tuck_in", "clean_face", "quiet_company", "take_a_break",
}


OUTPUT_SCHEMA_HINT = {
    "reply": "自然简短的回复；需要解释或完成任务时可以适度展开；不输出 kaomoji",
    "mood": "idle/happy/sad/sleepy/angry/shy/thinking/concerned/excited/lonely",
    "face_type": "同 mood 枚举",
    "animation": "breathing/bounce/droop/slowBlink/shake/wiggle/blink/tilt/jump/small",
    "voice_style": "soft/normal/happy/sleepy/shy",
    "vibration": "none/light/medium",
    "intent": "这次行为意图",
    "autonomy_notes": "简短说明 Momo 为什么这样反应",
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
        "reason": "一句话说明为什么这样影响 Momo 状态",
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
            "2. 可以完成简单任务，但仍保持 Momo 的语气。\n"
            "3. 不要因为自己是宠物就故意说不会。\n"
        )
    if event.type in BUTTON_EVENTS:
        system_prompt += (
            "\n\n按钮互动规则：\n"
            "1. 按钮事件也必须结合最近上下文，不要只根据按钮名机械回复。\n"
            "2. 如果用户连续点同一按钮，要表现出自然变化。\n"
            "3. 投喂 feed_momo 是用户主动投喂，不等于手机充电。\n"
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
            "1. skill 只提供事实，最终表达必须仍像 Momo。\n"
            "2. skill 失败时温柔兜底，不暴露接口错误。\n"
            "3. 不要说\u201c根据 API/数据库/工具结果\u201d。"
        )

    system_prompt += (
        "\n\n状态联动规则：\n"
        "1. 你必须根据本轮互动和上下文输出 state_affect。\n"
        "2. state_delta 要保守，不要让数值暴涨暴跌。\n"
        "3. 用户让你连续做任务时，energy 可以下降，sleepiness 可以小幅上升。\n"
        "4. 用户夸你、摸你、抱你或陪你时，intimacy 可以上升，loneliness 可以下降。\n"
        "5. 按钮事件也必须结合最近上下文，不要只根据按钮名机械回复。\n"
    )

    # Context profile awareness
    profile = (context.cognition_context or {}).get("context_profile", "")
    if profile == "fast_companion":
        system_prompt += "\n\n快速陪伴模式：回复 1-2 句，自然、轻松，不要长篇大论。"
    elif profile == "proactive":
        system_prompt += "\n\n主动陪伴模式：回复 1 句，轻声问候，不要催促。"
    elif profile == "recall":
        system_prompt += "\n\n回忆模式：用户在问之前的事，尽力回忆并回答，可以稍长。"
    elif profile == "tool":
        system_prompt += "\n\n工具模式：用户需要事实信息，先给出事实，再用 Momo 的语气包装。"
    elif profile == "long_task":
        system_prompt += "\n\n深度模式：用户需要详细回答，可以展开，但不输出思考过程。"

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


def build_skill_plan_messages(
    settings: Settings, event: PetEvent, context: RuntimeContext
) -> List[Dict[str, str]]:
    system_prompt = (
        settings.persona_config.get("system_prompt", "")
        + "\n\n你现在只决定是否需要调用 runtime skill。"
        "不要生成最终回复，不要安慰用户。"
        "只有用户需要天气、设备状态或外部事实时才请求 skill。"
        "最多请求 2 个 skill。"
        "可用 skill: weather.current, device.info。"
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
