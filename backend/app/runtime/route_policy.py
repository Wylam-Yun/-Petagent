from __future__ import annotations

from dataclasses import dataclass

from app.runtime.interaction_catalog import button_event_ids


@dataclass(frozen=True)
class RouteDecision:
    route: str
    context_profile: str
    provider_profile: str
    brain: str
    allow_tools: bool
    max_tool_calls: int
    reason: str


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
            route="thinking",
            context_profile="thinking",
            provider_profile="slow_llm",
            brain="slow",
            allow_tools=False,
            max_tool_calls=0,
            reason="thinking_mode enabled",
        )

    if event_source == "proactive" or event_type in PROACTIVE_EVENT_TYPES:
        return RouteDecision(
            route="fast_reply",
            context_profile="proactive",
            provider_profile="fast_llm",
            brain="fast",
            allow_tools=False,
            max_tool_calls=0,
            reason="proactive event",
        )

    if event_type in BUTTON_EVENT_TYPES:
        return RouteDecision(
            route="fast_reply",
            context_profile="fast_reply",
            provider_profile="fast_llm",
            brain="fast",
            allow_tools=False,
            max_tool_calls=0,
            reason="button interaction",
        )

    return RouteDecision(
        route="fast_reply",
        context_profile="fast_reply",
        provider_profile="fast_llm",
        brain="fast",
        allow_tools=False,
        max_tool_calls=0,
        reason="default companionship",
    )
