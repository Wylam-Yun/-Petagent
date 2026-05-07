from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.runtime.context import RuntimeContext
from app.runtime.events import PetEvent


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
        "loneliness": 0,
        "sleepiness": 0,
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
