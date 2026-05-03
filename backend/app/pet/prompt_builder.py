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
