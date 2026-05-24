from __future__ import annotations

from typing import Any, Dict, List


PROACTIVE_ACTIONS = {
    "morning": {
        "reply": "早呀。豆豆醒了一点点。",
        "mood": "happy",
        "face_type": "happy",
        "animation": "bounce",
        "voice_style": "happy",
    },
    "night": {
        "reply": "有点晚啦，豆豆陪你慢慢收尾。",
        "mood": "sleepy",
        "face_type": "sleepy",
        "animation": "slowBlink",
        "voice_style": "sleepy",
    },
    "long_idle": {
        "reply": "豆豆刚刚有乖乖待着，没有乱吵你。",
        "mood": "lonely",
        "face_type": "lonely",
        "animation": "small",
        "voice_style": "soft",
    },
    "battery_low": {
        "reply": "电量有点低，豆豆要小小省电了。",
        "mood": "sleepy",
        "face_type": "sleepy",
        "animation": "slowBlink",
        "voice_style": "sleepy",
    },
    "charging_started": {
        "reply": "开饭啦，豆豆又能回血陪你了。",
        "mood": "happy",
        "face_type": "happy",
        "animation": "bounce",
        "voice_style": "happy",
    },
    "charging_stopped": {
        "reply": "吃饱啦，豆豆继续陪你。",
        "mood": "idle",
        "face_type": "idle",
        "animation": "breathing",
        "voice_style": "soft",
    },
    "sleepy_time": {
        "reply": "豆豆有点困困的，会安静一点。",
        "mood": "sleepy",
        "face_type": "sleepy",
        "animation": "slowBlink",
        "voice_style": "sleepy",
    },
}


class ProactiveRuleProvider:
    name = "proactive_rule"

    def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        content = messages[-1]["content"]
        event_type = "long_idle"
        for candidate in PROACTIVE_ACTIONS:
            if '"type": "%s"' % candidate in content:
                event_type = candidate
                break
        action = dict(PROACTIVE_ACTIONS.get(event_type, PROACTIVE_ACTIONS["long_idle"]))
        action.update(
            {
                "vibration": "none",
                "intent": "proactive_%s" % event_type,
                "autonomy_notes": "low-cost proactive foreground poll response",
                "state_delta": {
                    "energy": 0,
                    "intimacy": 0,
                    "hunger": 0,
                    "loneliness": -1,
                    "sleepiness": 0,
                },
                "memory_update": {"should_save": False, "content": ""},
            }
        )
        return action
