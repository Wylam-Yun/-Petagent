from __future__ import annotations

import json
import threading
from datetime import datetime
from dataclasses import asdict
from typing import Any, Dict, List

from app.pet.brain import PetBrain
from app.pet.guard import guard_action
from app.pet.rules import apply_event_rules, apply_state_delta
from app.pet.state import PetStateStore
from app.providers.tts_mimo import MockTTSProvider
from app.runtime.actions import PetResponse
from app.runtime.context import build_runtime_context
from app.runtime.context_manager import ContextManager
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.events import normalize_event
from app.runtime.registry import SkillRegistry


class RuntimeDispatcher:
    def __init__(
        self,
        state_store: PetStateStore,
        brain: PetBrain,
        tts_provider: MockTTSProvider,
        registry: SkillRegistry,
        memory_store=None,
        interaction_log=None,
        device_store=None,
        tick_service=None,
        episode_manager: EpisodeStore = None,
        event_log_store: EventLogStore = None,
        context_manager: ContextManager = None,
    ) -> None:
        self.state_store = state_store
        self.brain = brain
        self.tts_provider = tts_provider
        self.registry = registry
        self.memory_store = memory_store
        self.interaction_log = interaction_log
        self.device_store = device_store
        self.tick_service = tick_service
        self.episode_manager = episode_manager
        self.event_log_store = event_log_store
        self.context_manager = context_manager
        self._event_lock = threading.RLock()

    def handle_event(
        self,
        raw_event: Dict[str, Any],
        brain: PetBrain = None,
        synthesize_voice: bool = True,
    ) -> PetResponse:
        with self._event_lock:
            return self._handle_event_inner(raw_event, brain, synthesize_voice)

    def _handle_event_inner(
        self,
        raw_event: Dict[str, Any],
        brain: PetBrain = None,
        synthesize_voice: bool = True,
    ) -> PetResponse:
        event = normalize_event(raw_event)

        # 1. Apply tick
        if self.tick_service is not None:
            self.tick_service.apply_if_due()

        # 2. Get current state and capture before snapshot
        current_state = self.state_store.get_state()
        state_before = dict(current_state)

        # 3. Apply event rules
        ruled_state = apply_event_rules(current_state, event.type)
        active_brain = brain or self.brain

        # 4. Get/create current episode
        episode = None
        if self.episode_manager is not None:
            idle_min = self.context_manager.idle_episode_minutes if self.context_manager else 45
            episode = self.episode_manager.get_or_create_current(idle_minutes=idle_min)

        # 5. Build cognition context via ContextManager
        cognition_context = None
        if self.context_manager is not None:
            cognition_context = self.context_manager.build(
                event=event,
                pet_state=ruled_state,
                episode=episode,
                event_log_store=self.event_log_store,
                memory_store=self.memory_store,
                device_state=self._device_state(),
                skill_results=[],
            )

        # 6. Build planning context (backward compat + cognition_context)
        planning_context = build_runtime_context(
            event,
            ruled_state,
            recent_memory=self._recent_memory(),
            recent_dialogue=self._recent_dialogue(),
            device_state=self._device_state(),
            cognition_context=cognition_context,
        )

        # 7. Run skills
        skill_results = self._run_requested_skills(event, active_brain, planning_context)

        # 8. Rebuild context with skill results
        if self.context_manager is not None and cognition_context is not None:
            cognition_context = self.context_manager.build(
                event=event,
                pet_state=ruled_state,
                episode=episode,
                event_log_store=self.event_log_store,
                memory_store=self.memory_store,
                device_state=self._device_state(),
                skill_results=skill_results,
            )
        context = build_runtime_context(
            event,
            ruled_state,
            recent_memory=self._recent_memory(),
            recent_dialogue=self._recent_dialogue(),
            device_state=self._device_state(),
            skill_results=skill_results,
            cognition_context=cognition_context,
        )

        # 9. Generate action
        try:
            raw_action = active_brain.generate_action(event, context)
        except Exception:
            raw_action = None
        action = guard_action(raw_action)

        # 10. Apply state delta and save
        final_state = apply_state_delta(ruled_state, action.state_delta)
        final_state["mood"] = action.mood
        final_state["mode"] = "idle"
        final_state["last_interaction_at"] = datetime.utcnow().isoformat()
        saved_state = self.state_store.save_state(final_state)

        # 11. Record in event_log (before TTS so it's never blocked)
        episode_id = episode.get("episode_id", "") if episode else ""
        if self.event_log_store is not None and episode_id:
            self.event_log_store.record(
                event_id=event.id,
                episode_id=episode_id,
                event_type=event.type,
                source=event.source,
                user_text=str(event.payload.get("user_text", "")),
                pet_reply=action.reply,
                skill_results=skill_results or None,
                state_before=state_before,
                state_after=saved_state,
                mood_after=action.mood,
            )

        # 12. Update episode event count
        if self.episode_manager is not None and episode_id:
            self.episode_manager.update_event_count(episode_id)

        # 13. Close episode on exit_phrase (after event is logged)
        if event.type == "exit_phrase" and self.episode_manager is not None:
            self.episode_manager.close_current("exit_phrase")

        # 14. TTS (failure doesn't block)
        voice_url = None
        if synthesize_voice:
            try:
                voice_url = self.tts_provider.synthesize(action.reply, action.voice_style)
            except Exception:
                voice_url = None

        # 15. Save memory (backward compat)
        if self.memory_store is not None:
            self.memory_store.save_from_update(action.memory_update)

        # 16. Log to interaction_log (backward compat)
        if self.interaction_log is not None:
            self.interaction_log.record(
                event.type,
                action.reply,
                action.mood,
                user_text=str(event.payload.get("user_text", "")),
            )

        # 17. Cleanup event log if needed
        if self.event_log_store is not None:
            max_rows = self.context_manager.raw_max_rows if self.context_manager else 3000
            self.event_log_store.cleanup_if_needed(
                max_rows=max_rows,
                current_episode_id=episode_id or None,
            )

        return PetResponse(
            reply=action.reply,
            mood=action.mood,
            face_type=action.face_type,
            animation=action.animation,
            vibration=action.vibration,
            voice_url=voice_url,
            pet_state=saved_state,
            runtime={
                "event_id": event.id,
                "skills_used": [item.get("skill_id") for item in skill_results],
                "episode_id": episode_id,
            },
        )

    def _recent_memory(self) -> List[str]:
        if self.memory_store is None:
            return []
        return self.memory_store.recent_memory(limit=6)

    def _recent_dialogue(self) -> List[Dict[str, str]]:
        if self.interaction_log is None:
            return []
        return self.interaction_log.recent_dialogue(limit=3)

    def _device_state(self) -> Dict[str, Any]:
        if self.device_store is None:
            return {}
        return self.device_store.get_state()

    def _run_requested_skills(
        self, event, brain: PetBrain, context
    ) -> List[Dict[str, Any]]:
        requests = self._planned_skill_requests(event, brain, context)
        results: List[Dict[str, Any]] = []
        for skill_id, payload in requests[:2]:
            if not self.registry.has_skill(skill_id):
                continue
            result = self.registry.run_skill(skill_id, payload)
            results.append(asdict(result))
        return results

    def _planned_skill_requests(self, event, brain: PetBrain, context) -> List[tuple]:
        if event.type != "voice_message":
            return []
        if not self._looks_like_external_request(event):
            return []
        try:
            plan = brain.generate_skill_plan(event, context)
        except Exception:
            plan = {}
        requests: List[tuple] = []
        for item in plan.get("skill_requests") or []:
            if not isinstance(item, dict):
                continue
            skill_id = str(item.get("skill_id") or "")
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            if skill_id:
                requests.append((skill_id, payload))
        return requests or self._infer_skill_requests(event)

    def _infer_skill_requests(self, event) -> List[tuple]:
        text = str(event.payload.get("user_text") or event.payload.get("text") or "")
        if any(word in text for word in ["天气", "出门", "下雨", "温度", "冷不冷", "热不热"]):
            return [("weather.current", {"location": "current"})]
        return []

    def _looks_like_external_request(self, event) -> bool:
        text = str(event.payload.get("user_text") or event.payload.get("text") or "")
        return any(
            word in text
            for word in ["天气", "出门", "下雨", "温度", "冷不冷", "热不热", "电量", "充电"]
        )
