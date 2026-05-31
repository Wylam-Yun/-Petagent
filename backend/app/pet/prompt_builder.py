from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.runtime.context import RuntimeContext
from app.runtime.events import PetEvent
from app.runtime.expressions import EXPRESSION_KEYS, activity_recommendation
from app.runtime.interaction_catalog import button_event_ids, get_interaction


BUTTON_EVENTS = set(button_event_ids())
BEHAVIOR_ACTION_SCHEMA = (
    "idle/waiting/review/waving/jumping/failed/running/running-left/running-right/"
    "lazy_idle/nap/sneak_eat/watch_tv/self_groom/wander/greet/happy/tease/"
    "pretend_busy/listen/think/speak/remember/comfort/confused/deny/excited"
)


def _selected_notebook_lines(selected: Any, max_items: int) -> List[str]:
    """Read V1.4 single-notebook selections with V1.3 tuple compatibility."""
    if isinstance(selected, list):
        return [str(item) for item in selected[:max_items] if item]
    if isinstance(selected, tuple) and len(selected) == 2:
        lines: List[str] = []
        for part in selected:
            if isinstance(part, list):
                lines.extend(str(item) for item in part if item)
            elif part:
                lines.append(str(part))
        return lines[:max_items]
    return []


OUTPUT_SCHEMA_HINT = {
    "reply": "自然简短的回复；需要解释或完成任务时可以适度展开；必须使用第一人称“我”；不输出 kaomoji；不要自称豆豆",
    "mood": "idle/happy/sad/sleepy/angry/shy/thinking/concerned/excited/lonely",
    "face_type": "同 mood 枚举",
    "expression_key": "/".join(sorted(EXPRESSION_KEYS)),
    "animation": "breathing/bounce/droop/slowBlink/shake/wiggle/blink/tilt/jump/small",
    "voice_style": "soft/normal/happy/sleepy/shy",
    "vibration": "none/light/medium",
    "intent": "这次行为意图",
    "autonomy_notes": "简短说明豆豆为什么这样反应",
    "behavior_intent": "可选：soft_comfort/clingy_happy/clingy_wronged_happy/lazy_busy/quiet_sleepy/playful_proud/confused_wronged/neutral_companion",
    "behavior_plan": [
        {"action": BEHAVIOR_ACTION_SCHEMA, "slot": "before_speech/speech/after_speech/idle_after", "duration_ms": 600-2500}
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
    cog = dict(context.cognition_context) if context.cognition_context else {}
    # V1.3 thinking mode: inject bounded card items if available
    selected = cog.get("selected_card_items")
    if selected:
        cog["notebook_memory"] = _selected_notebook_lines(selected, 20)
    payload = serialize_for_prompt(
        event=event,
        pet_state=context.pet_state,
        cognition_context=cog or None,
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
    "reply": "自然简短的回复，不超过 80 字；必须使用第一人称“我”；不要输出颜表情；不要自称豆豆",
    "mood": "idle/happy/sad/sleepy/angry/shy/thinking/concerned/excited/lonely",
    "expression_key": "/".join(sorted(EXPRESSION_KEYS)),
    "action": BEHAVIOR_ACTION_SCHEMA,
    "voice_style": "soft/normal/happy/sleepy/shy",
    "state_delta": {
        "energy": "可选，小整数 delta，范围 -5 到 5；过大或非数字会被忽略",
        "intimacy": "可选，小整数 delta，范围 -5 到 5；过大或非数字会被忽略",
    },
}

UNIFIED_REPLY_CONTRACT = {
    "must_answer_current_user_message_first": True,
    "recent_context_is_not_style_template": True,
    "long_term_memory_only_when_relevant": True,
    "invalid_if_reply_uses_context_or_memory_as_refusal_reason": True,
    "invalid_if_reply_repeats_recent_pet_phrase_pattern": True,
    "on_invalid_output_backend_fails_this_turn_without_fallback": True,
}


def _level(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    if number < 34:
        return "low"
    if number < 67:
        return "medium"
    return "high"


def _foreground_pet_state(context: RuntimeContext) -> Dict[str, Any]:
    energy = context.pet_state.get("energy", 50)
    intimacy = context.pet_state.get("intimacy", 0)
    return {
        "mood": context.pet_state.get("mood", "idle"),
        "energy": energy,
        "energy_level": _level(energy),
        "intimacy": intimacy,
        "intimacy_level": _level(intimacy),
    }


def _unified_current_time(cognition: Dict[str, Any]) -> Dict[str, Any]:
    current = cognition.get("current_time")
    if not isinstance(current, dict):
        return {}
    local = str(current.get("local") or "")
    utc = str(current.get("utc") or "")
    timezone_name = str(current.get("timezone") or "")
    result: Dict[str, Any] = {}
    if local:
        result["local"] = local
        try:
            local_dt = datetime.fromisoformat(local)
            result["local_date"] = local_dt.date().isoformat()
            result["local_time"] = local_dt.strftime("%H:%M")
            result["weekday"] = [
                "星期一",
                "星期二",
                "星期三",
                "星期四",
                "星期五",
                "星期六",
                "星期日",
            ][local_dt.weekday()]
        except ValueError:
            pass
    if utc:
        result["utc"] = utc
    if timezone_name:
        result["timezone"] = timezone_name
    return result


def build_unified_foreground_messages(
    settings: Settings,
    event: PetEvent,
    context: RuntimeContext,
    *,
    include_current_time: bool = True,
) -> List[Dict[str, str]]:
    system_prompt = settings.persona_config.get("system_prompt", "")
    system_prompt += (
        "\n\nV1.5 统一对话规则："
        "\n1. 直接回复用户，不输出思考过程。"
        "\n2. 文本和 ASR 成功后的语音都使用同一上下文。"
        "\n3. 不要提示用户打开思考模式或回忆模式。"
        "\n4. 严格输出 JSON，reply 必须是给用户看的自然回复。"
        "\n\nV1.6 表情规则："
        "\n1. 根据当前用户语境选择 expression_key。"
        "\n2. reply 里不要输出颜表情，颜表情只能通过 expression_key 表示。"
        "\n3. 台词主语必须用“我”，不要自称“豆豆”。"
        "\n\nV1.7 上下文使用规则："
        "\n1. current_user_message 是本轮最高优先级输入，必须先回应它。"
        "\n2. recent_conversation_context 是最近上下文，只用于理解连续对话，不是措辞模板。"
        "\n3. long_term_memory 是长期记忆和背景事实，只在相关时使用，不要每轮主动复述。"
        "\n4. 不要把自己上一轮的口头表达、玩笑、情绪当成长期事实。"
        "\n5. pet_state 是当前状态参考，不能压过本轮用户意图；mood 不代表必须延续上一轮情绪。"
        "\n6. energy 低可以影响语气，但不能成为拒绝正常回答的理由。"
        "\n7. 每轮都要根据当前用户输入重新选择 expression_key 和 action。"
        "\n8. 回复主语必须用“我”，不要自称豆豆。"
        "\n9. 如果 current_user_message 是问题、事实询问、总结请求或解释请求，reply 必须先给出直接答案，再保留一点桌宠语气。"
        "\n10. 不能把 recent_conversation_context、long_term_memory 或 pet_state 当作拒绝回答当前问题的理由。"
        "\n11. 如果 recent_conversation_context 里连续出现相似句式、相似借口或相同梗，本轮必须换一种表达，并避免继续使用这些重复模式。"
        "\n12. 只有当前用户明确问到长期偏好、记忆、用户习惯或相关话题时，才主动提 long_term_memory。"
        "\n13. 如果用户询问今天日期、星期或当前时间，必须以 current_time 为准，不要猜。"
    )
    cognition = context.cognition_context or {}
    payload = {
        "current_user_message": str(event.payload.get("user_text") or event.payload.get("text") or ""),
        "recent_conversation_context": list(cognition.get("recent_exact_events") or [])[-5:],
        "long_term_memory": _selected_notebook_lines(
            cognition.get("selected_card_items"),
            10,
        ),
        "pet_state": _foreground_pet_state(context),
        "reply_contract": UNIFIED_REPLY_CONTRACT,
        "response_schema": FAST_REPLY_SCHEMA,
    }
    if include_current_time:
        payload["current_time"] = _unified_current_time(cognition)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def build_unified_retry_messages(
    messages: List[Dict[str, str]],
    *,
    rejected_reply: str,
    reason: str,
) -> List[Dict[str, str]]:
    retry_messages = list(messages)
    retry_messages.append(
        {
            "role": "assistant",
            "content": json.dumps({"reply": rejected_reply}, ensure_ascii=False),
        }
    )
    retry_messages.append(
        {
            "role": "user",
            "content": json.dumps(
                {
                    "retry_reason": reason,
                    "required_fix": (
                        "上一条 reply 违反 V1.7：没有优先回答 current_user_message，"
                        "或把 recent_conversation_context/long_term_memory/pet_state 当成拒答理由。"
                        "请重新输出完整 JSON；必须先直接回答当前用户消息，避免复用上一条的借口或句式。"
                    ),
                    "failure_policy": "如果再次违反，后端会把本轮作为失败处理，不会写入历史。",
                },
                ensure_ascii=False,
            ),
        }
    )
    return retry_messages


def build_fast_reply_messages(
    settings: Settings, event: PetEvent, context: RuntimeContext
) -> List[Dict[str, str]]:
    return build_unified_foreground_messages(settings, event, context)


def build_ambient_bubble_messages(
    settings: Settings,
    *,
    scene: str,
    idle_step: int,
    idle_minutes: int,
    suggested_activity: str,
    pet_state: Dict[str, Any],
    recent_dialogue: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    system_prompt = settings.persona_config.get("system_prompt", "")
    system_prompt += (
        "\n\nV1.6 空闲气泡规则："
        "\n1. 你是住在手机里的调皮小猫桌宠，但台词必须只用第一人称“我”。"
        "\n2. 只能输出 JSON。"
        "\n3. bubble 最多 20 个中文字符左右，只能一句。"
        "\n4. 不要自称豆豆，不要输出颜表情，不要主动开启复杂话题。"
        "\n5. 规则给你的 suggested_activity 是灵感，台词不能照抄模板。"
        "\n6. expression_key 必须从 recommended_expression_keys 中选择。"
        "\n7. action 必须从 recommended_actions 中选择。"
        "\n8. 失败或不确定时宁可短一点，不要解释内部规则。"
    )
    rec = activity_recommendation(suggested_activity)
    payload = {
        "event_type": "ambient_bubble",
        "scene": scene,
        "idle_step": idle_step,
        "idle_minutes": idle_minutes,
        "suggested_activity": suggested_activity,
        "activity_hint": {
            "activity_class": rec.activity_class,
            "recommended_expression_keys": rec.expression_keys,
            "recommended_actions": rec.actions,
        },
        "tone": "调皮、轻、不要打扰",
        "constraints": {
            "max_chars": 20,
            "first_person_only": True,
            "no_tts": True,
            "do_not_start_complex_topic": True,
            "no_kaomoji_in_bubble": True,
        },
        "pet_state": pet_state,
        "recent_dialogue": recent_dialogue,
        "response_schema": {
            "bubble": "一句短气泡，必须包含“我”，不能包含豆豆或颜表情",
            "expression_key": "必须是 recommended_expression_keys 之一",
            "action": "必须是 recommended_actions 之一",
        },
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


THINKING_RESPONSE_SCHEMA = {
    "reply": "完整但简洁的自然回复；必须使用第一人称“我”；不输出思考过程；不要输出颜表情；不要自称豆豆",
    "mood": "idle/happy/sad/sleepy/angry/shy/thinking/concerned/excited/lonely",
    "face_type": "同 mood 枚举",
    "expression_key": "/".join(sorted(EXPRESSION_KEYS)),
    "animation": "breathing/bounce/droop/slowBlink/shake/wiggle/blink/tilt/jump/small",
    "voice_style": "soft/normal/happy/sleepy/shy",
    "vibration": "none/light/medium",
    "behavior_intent": "soft_comfort/clingy_happy/clingy_wronged_happy/lazy_busy/quiet_sleepy/playful_proud/confused_wronged/neutral_companion",
    "behavior_plan": [
        {"action": BEHAVIOR_ACTION_SCHEMA, "slot": "before_speech/speech/after_speech/idle_after", "duration_ms": 600}
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
}


def build_thinking_messages(
    settings: Settings, event: PetEvent, context: RuntimeContext
) -> List[Dict[str, str]]:
    return build_unified_foreground_messages(
        settings,
        event,
        context,
        include_current_time=False,
    )


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


MEMORY_JUDGMENT_SCHEMA = {
    "should_write": "true/false — 是否值得记到小本本",
    "target": "memory.md",
    "category": "identity/preference/relationship/project/temporary",
    "content": "要记住的内容，简洁一句话",
    "reason": "为什么值得记",
}


MEMORY_SUMMARY_SCHEMA = {
    "memories": [
        {"category": "identity/preference/relationship/project/temporary", "content": "保留下来的记忆一句话"}
    ],
}


def build_memory_judgment_messages(
    user_text: str, trigger_categories: list
) -> list:
    """Build prompt for background memory judgment."""
    system_prompt = (
        "你是豆豆的记忆判断器。判断用户的这句话是否值得记到小本本里。\n"
        "规则：\n"
        "1. 只记有长期价值的信息（身份、偏好、关系、项目）。\n"
        "2. 不记临时情绪、闲聊、重复信息。\n"
        "3. content 要简洁，一句话概括核心信息。\n"
        "4. target 固定使用 memory.md，不要写 user.md。\n"
        "5. 只输出 JSON，不要解释。"
    )
    payload = {
        "user_text": user_text,
        "trigger_categories": trigger_categories,
        "output_schema": MEMORY_JUDGMENT_SCHEMA,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def build_memory_summary_messages(
    user_text: str,
    pet_reply: str,
    route: str,
    memory_content: str,
    trigger_categories: list,
    recent_conversation_context: Optional[List[Dict[str, Any]]] = None,
    selected_memory: Optional[list] = None,
) -> list:
    """Build prompt for after-turn notebook summarization."""
    system_prompt = (
        "你是豆豆的小本本后台整理器。当前回复已经给用户了，你只整理 memory.md。\n"
        "用户体验规则：\n"
        "1. 只记录会让豆豆以后更懂主人的信息。\n"
        "2. 明确说“记住/别忘了/写进小本本”的内容优先判断。\n"
        "3. 不记录普通寒暄、短暂情绪、重复信息、密钥、口令、token 或大段原话。\n"
        "4. 输出是完整替换后的长期记忆列表，不是本轮新增列表，0 到 10 条，不输出时间戳。\n"
        "5. current_turn.current_user_message 是最高优先级证据。\n"
        "6. recent_conversation_context 只辅助判断最近上下文。\n"
        "7. long_term_memory_file 是已有长期记忆基线。\n"
        "8. 如果 long_term_memory_file 里已有有效记忆，默认原样保留旧记忆，只在当前证据明确要求时更新、合并或移除。\n"
        "9. 不能因为本轮没有新增长期信息就输出空列表。\n"
        "10. 只有 long_term_memory_file 本来没有有效记忆，且 current_turn 与 recent_conversation_context 都没有长期价值信息时，才允许输出 {\"memories\":[]}。\n"
        "11. 相似事实必须合并成一条，每条 memory 必须表达不同事实。\n"
        "12. memory.md 只维护用户相关长期事实，例如用户身份、偏好、关系、长期项目或用户明确要求我记住的约定。\n"
        "13. 不要保存自己的口头癖、玩笑、临时情绪，也不要把“正在记小本本”这类回复写成用户长期事实。\n"
        "14. 不要保留或新增关于我/豆豆/模型/系统/后端/ASR/LLM/前端的自我审计、答错题、识别错误、超时、测试结果或运行问题；这些属于日志，不是用户长期记忆。\n"
        "15. 如果 long_term_memory_file 里已有这类无效运行审计记忆，输出完整替换列表时应移除它们，同时保留其他有效用户记忆。"
    )
    payload = {
        "current_turn": {
            "current_user_message": user_text,
            "current_pet_reply": pet_reply,
            "route": route,
            "trigger_categories": trigger_categories,
        },
        "recent_conversation_context": list(recent_conversation_context or [])[-5:],
        "long_term_memory_file": memory_content or "（空）",
        "output_schema": MEMORY_SUMMARY_SCHEMA,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


NIGHTLY_CLEANUP_SCHEMA = {
    "add": [
        {"target": "memory.md", "category": "identity/preference/relationship/project/temporary", "content": "新内容"}
    ],
    "update": [
        {"target": "memory.md", "old": "原始行全文（含 - [timestamp][category]）", "new_category": "新分类", "new_content": "新内容"}
    ],
    "delete": [
        {"target": "memory.md", "old": "原始行全文（含 - [timestamp][category]）", "reason": "删除原因"}
    ],
}


def build_nightly_cleanup_messages(
    memory_content: str,
    event_lines: list,
    current_time: str,
) -> list:
    """Build prompt for nightly memory cleanup."""
    system_prompt = (
        "你是豆豆的小本本整理器。每晚整理一次唯一记忆文件 memory.md。\n"
        "老化规则：\n"
        "1. identity（身份）：保留，除非有更新的明确修正。\n"
        "2. preference（偏好）：长期保留，合并重复。\n"
        "3. relationship（关系）：保留重要项，合并相似项。\n"
        "4. project（项目）：3 天后将相关原始记忆总结为一行。\n"
        "5. temporary（临时）：3 天后删除，除非已升级为 project/relationship/preference。\n"
        "操作规则：\n"
        "- add: 添加新记忆。\n"
        "- update: 替换旧行。old 必须是完整行（含 - [timestamp][category]）。\n"
        "- delete: 删除旧行。old 必须是完整行。不能删除 identity 类。\n"
        "- target 固定使用 memory.md，不要输出 user.md。\n"
        "- 只输出 JSON，不要解释。\n"
        "- 如果不需要任何操作，输出 {\"add\":[], \"update\":[], \"delete\":[]}"
    )
    events_text = "\n".join(event_lines[:50]) if event_lines else "（今天没有对话）"
    payload = {
        "current_time": current_time,
        "memory_md": memory_content or "（空）",
        "today_conversation": events_text,
        "output_schema": NIGHTLY_CLEANUP_SCHEMA,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
