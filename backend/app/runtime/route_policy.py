from __future__ import annotations

from dataclasses import dataclass

from app.runtime.interaction_catalog import button_event_ids


@dataclass(frozen=True)
class RouteDecision:
    route: str
    context_profile: str
    provider_profile: str
    allow_tools: bool
    max_tool_calls: int
    reason: str


TOOL_KEYWORDS = {"天气", "出门", "下雨", "温度", "冷不冷", "热不热", "电量", "充电"}
RECALL_KEYWORDS = {
    "昨天", "前天", "刚刚", "之前", "上次", "回顾",
    "聊了啥", "聊了什么", "说了啥", "说了什么", "记得", "想起来", "记得吗",
}
LONG_TASK_KEYWORDS = {
    "代码", "编程", "写一个", "解释一下", "详细", "分析",
    "帮我写", "教程", "原理", "算法",
}

PROACTIVE_EVENT_TYPES = {
    "morning", "night", "long_idle", "battery_low",
    "charging_started", "charging_stopped", "sleepy_time", "user_return",
}
BUTTON_EVENT_TYPES = set(button_event_ids())


def decide_route(
    event_type: str,
    event_source: str,
    user_text: str,
    thinking_mode: bool = False,
) -> RouteDecision:
    if thinking_mode:
        return RouteDecision(
            route="slow",
            context_profile="long_task",
            provider_profile="slow_llm",
            allow_tools=True,
            max_tool_calls=2,
            reason="thinking_mode enabled",
        )

    if event_source == "proactive" or event_type in PROACTIVE_EVENT_TYPES:
        return RouteDecision(
            route="fast",
            context_profile="proactive",
            provider_profile="fast_llm",
            allow_tools=False,
            max_tool_calls=0,
            reason="proactive event",
        )

    if event_type in BUTTON_EVENT_TYPES:
        return RouteDecision(
            route="fast",
            context_profile="fast_companion",
            provider_profile="fast_llm",
            allow_tools=False,
            max_tool_calls=0,
            reason="button interaction",
        )

    if user_text and any(kw in user_text for kw in RECALL_KEYWORDS):
        return RouteDecision(
            route="fast",
            context_profile="fast_companion",
            provider_profile="fast_llm",
            allow_tools=False,
            max_tool_calls=0,
            reason="recall keyword in fast mode, using memory cards",
        )

    if user_text and any(kw in user_text for kw in TOOL_KEYWORDS):
        return RouteDecision(
            route="fast",
            context_profile="tool",
            provider_profile="fast_llm",
            allow_tools=True,
            max_tool_calls=2,
            reason="external fact request",
        )

    if user_text and any(kw in user_text for kw in LONG_TASK_KEYWORDS):
        return RouteDecision(
            route="slow",
            context_profile="long_task",
            provider_profile="slow_llm",
            allow_tools=True,
            max_tool_calls=2,
            reason="complex task detected",
        )

    return RouteDecision(
        route="fast",
        context_profile="fast_companion",
        provider_profile="fast_llm",
        allow_tools=False,
        max_tool_calls=0,
        reason="default companionship",
    )
