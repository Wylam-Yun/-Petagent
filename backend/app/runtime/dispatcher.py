from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from app.pet.brain import PetBrain
from app.pet.guard import guard_action
from app.pet.rules import apply_event_rules, apply_state_delta
from app.pet.state import PetStateStore
from app.providers.tts_mimo import MockTTSProvider
from app.runtime.actions import PetResponse
from app.runtime.context import build_runtime_context
from app.runtime.events import normalize_event
from app.runtime.registry import SkillRegistry


class RuntimeDispatcher:
    def __init__(
        self,
        state_store: PetStateStore,
        brain: PetBrain,
        tts_provider: MockTTSProvider,
        registry: SkillRegistry,
    ) -> None:
        self.state_store = state_store
        self.brain = brain
        self.tts_provider = tts_provider
        self.registry = registry

    def handle_event(
        self, raw_event: Dict[str, Any], brain: PetBrain = None
    ) -> PetResponse:
        event = normalize_event(raw_event)
        current_state = self.state_store.get_state()
        ruled_state = apply_event_rules(current_state, event.type)
        context = build_runtime_context(event, ruled_state)
        active_brain = brain or self.brain

        try:
            raw_action = active_brain.generate_action(event, context)
        except Exception:
            raw_action = None
        action = guard_action(raw_action)

        final_state = apply_state_delta(ruled_state, action.state_delta)
        final_state["mood"] = action.mood
        final_state["mode"] = "idle"
        final_state["last_interaction_at"] = datetime.utcnow().isoformat()
        saved_state = self.state_store.save_state(final_state)

        voice_url = None
        try:
            voice_url = self.tts_provider.synthesize(action.reply, action.voice_style)
        except Exception:
            voice_url = None

        return PetResponse(
            reply=action.reply,
            mood=action.mood,
            face_type=action.face_type,
            animation=action.animation,
            vibration=action.vibration,
            voice_url=voice_url,
            pet_state=saved_state,
            runtime={"event_id": event.id, "skills_used": []},
        )
