from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Dict, Optional

from app.pet.brain import PetBrain
from app.runtime.dispatcher import RuntimeDispatcher
from app.runtime.activation import classify_activation as _classify_activation
from app.runtime.route_policy import decide_route


def _now_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


@dataclass(frozen=True)
class TextRouteInfo:
    selected: str
    thinking_mode: bool
    brain_provider: str
    route_reason: str = ""
    timings_ms: Dict[str, int] = field(default_factory=dict)

    def dict(self) -> Dict[str, Any]:
        return {
            "selected": self.selected,
            "thinking_mode": self.thinking_mode,
            "brain_provider": self.brain_provider,
            "route_reason": self.route_reason,
            "timings_ms": dict(self.timings_ms),
        }


@dataclass(frozen=True)
class TextPipelineResult:
    user_text: str
    response: Any
    route_info: TextRouteInfo
    activation: Optional[Dict[str, Any]] = None


class TextPipeline:
    def __init__(
        self,
        *,
        dispatcher: RuntimeDispatcher,
        fast_brain: PetBrain,
        slow_brain: PetBrain,
        fast_brain_provider_name: str = "fast_llm",
        slow_brain_provider_name: str = "slow_llm",
        activation_manager: Any = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.fast_brain = fast_brain
        self.slow_brain = slow_brain
        self.fast_brain_provider_name = fast_brain_provider_name
        self.slow_brain_provider_name = slow_brain_provider_name
        self.activation_manager = activation_manager

    def handle(self, text: str, *, thinking_mode: bool = False) -> TextPipelineResult:
        user_text = text.strip()
        started = perf_counter()
        decision = decide_route(
            event_type="text_message",
            event_source="text",
            user_text=user_text,
            thinking_mode=thinking_mode,
        )
        brain = self.slow_brain if decision.brain == "slow" else self.fast_brain
        selected = decision.route
        provider_name = (
            self.slow_brain_provider_name if decision.brain == "slow" else self.fast_brain_provider_name
        )
        activation_event = _classify_activation(user_text, self.activation_manager)
        activation_info = None
        if activation_event is not None:
            source = "text_slow" if selected == "slow" else "text_fast"
            activation_event["source"] = source
            activation_event.setdefault("payload", {})["thinking_mode"] = thinking_mode
            response = self.dispatcher.handle_event(activation_event, brain=brain)
            activation_info = self._build_activation_info(activation_event["type"])
        else:
            response = self.dispatcher.handle_event(
                {
                    "type": "text_message",
                    "source": "text_slow" if selected == "slow" else "text_fast",
                    "payload": {"user_text": user_text, "thinking_mode": thinking_mode},
                },
                brain=brain,
            )
        return TextPipelineResult(
            user_text=user_text,
            response=response,
            route_info=TextRouteInfo(
                selected=selected,
                thinking_mode=thinking_mode,
                brain_provider=provider_name,
                route_reason=decision.reason,
                timings_ms={"total": _now_ms(started)},
            ),
            activation=activation_info,
        )

    def _build_activation_info(self, event_type: str) -> Dict[str, Any]:
        if self.activation_manager is None:
            return {"type": event_type, "active": False, "session_id": None}
        state = self.activation_manager.state
        return {
            "type": "wake" if event_type == "wake_phrase" else "exit",
            "active": state.active,
            "session_id": state.session_id,
        }
