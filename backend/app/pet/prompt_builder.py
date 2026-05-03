from __future__ import annotations

import json
from typing import Any, Dict, List

from app.config import Settings
from app.runtime.context import RuntimeContext
from app.runtime.events import PetEvent


OUTPUT_SCHEMA_HINT = {
    "reply": "短回复，不输出 kaomoji",
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


def build_pet_messages(
    settings: Settings, event: PetEvent, context: RuntimeContext
) -> List[Dict[str, str]]:
    system_prompt = settings.persona_config.get("system_prompt", "")
    if event.type == "voice_message":
        system_prompt += (
            "\n\n语音事件规则：\n"
            "1. 优先回应用户情绪，而不是急着给建议。\n"
            "2. 如果用户疲惫、烦躁、低落，语气要温柔。\n"
            "3. 如果识别置信度低，不要假装完全听懂，可以说刚刚有点没听清。\n"
            "4. 不要复读用户整句话。\n"
            "5. 很多时候陪着就好，不要强行解决问题。"
        )
    user_payload = {
        "event": event.dict(),
        "runtime_context": context.dict(),
        "output_schema": OUTPUT_SCHEMA_HINT,
    }
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False),
        },
    ]
