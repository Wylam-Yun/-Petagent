from __future__ import annotations

from typing import Any, Dict

from app.config import Settings
from app.pet.prompt_builder import (
    build_ambient_bubble_messages,
    build_fast_reply_messages,
    build_pet_messages,
    build_skill_plan_messages,
    build_thinking_messages,
    build_unified_foreground_messages,
)
from app.providers.llm_mimo import LLMProvider
from app.runtime.context import RuntimeContext
from app.runtime.events import PetEvent


class PetBrain:
    def __init__(self, settings: Settings, provider: LLMProvider) -> None:
        self.settings = settings
        self.provider = provider

    def generate_action(self, event: PetEvent, context: RuntimeContext) -> Dict[str, Any]:
        messages = build_pet_messages(self.settings, event, context)
        return self.provider.complete_json(messages)

    def generate_fast_reply_action(self, event: PetEvent, context: RuntimeContext) -> Dict[str, Any]:
        messages = build_unified_foreground_messages(self.settings, event, context)
        return self.provider.complete_json(messages)

    def generate_thinking_action(self, event: PetEvent, context: RuntimeContext) -> Dict[str, Any]:
        messages = build_unified_foreground_messages(self.settings, event, context)
        return self.provider.complete_json(messages)

    def generate_skill_plan(
        self, event: PetEvent, context: RuntimeContext,
        skill_catalog: str = "",
    ) -> Dict[str, Any]:
        messages = build_skill_plan_messages(
            self.settings, event, context, skill_catalog=skill_catalog,
        )
        return self.provider.complete_json(messages)

    def generate_ambient_bubble(
        self,
        *,
        scene: str,
        idle_step: int,
        idle_minutes: int,
        suggested_activity: str,
        pet_state: Dict[str, Any],
        recent_dialogue: list,
    ) -> Dict[str, Any]:
        messages = build_ambient_bubble_messages(
            self.settings,
            scene=scene,
            idle_step=idle_step,
            idle_minutes=idle_minutes,
            suggested_activity=suggested_activity,
            pet_state=pet_state,
            recent_dialogue=recent_dialogue,
        )
        return self.provider.complete_json(messages)
