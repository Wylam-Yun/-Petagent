from __future__ import annotations

import json
import logging
import threading
from difflib import SequenceMatcher
from datetime import datetime
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from time import perf_counter

from app.pet.brain import PetBrain
from app.pet.guard import guard_action, guard_fast_reply_action
from app.pet.rules import apply_event_rules, apply_state_delta, clamp_state
from app.pet.state import PetStateStore
from app.providers.tts_mimo import MockTTSProvider
from app.runtime.actions import ALLOWED_BEHAVIOR_ACTIONS, FastReplyAction, PetResponse
from app.runtime.agent_run import AgentRun
from app.runtime.context import build_runtime_context
from app.runtime.context_manager import ContextManager
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.events import normalize_event
from app.runtime.registry import SkillRegistry
from app.runtime.concurrency import ProviderBusyError, ProviderGate
from app.runtime.route_policy import decide_route
from app.runtime.memory_triggers import detect_memory_triggers

logger = logging.getLogger(__name__)

FAST_DUPLICATE_RECOVERY_REPLIES = (
    "收到，豆豆顺着你这句继续聊。",
    "知道啦，豆豆这次不沿用上一句。",
    "嗯，豆豆接着你的意思往下说。",
    "好，豆豆换个角度陪你继续。",
    "明白，豆豆给你一个新的回应。",
)

PROVIDER_FALLBACK_REPLIES = (
    "豆豆在这儿，刚才反应慢了一下，但这句收到了。",
    "刚才豆豆脑袋转慢了点，这次直接接住你的意思。",
    "豆豆慢半拍了，但没有走开，这句先记住。",
    "这轮豆豆有点短路，先把你的话稳稳接住。",
    "豆豆刚刚反应慢了点，但这次不会让你重说。",
)

ASR_FAILURE_COPY_MARKERS = (
    "没听清",
    "没接准",
    "声音有点糊",
    "声音糊",
    "没识别完整",
    "识别不完整",
    "听偏了",
    "没接稳",
    "没接住",
    "再说一遍",
    "再讲一次",
    "再来一次",
    "换个说法再来",
    "不敢乱猜",
    "听到一点点",
    "竖起耳朵在听",
    "竖起耳朵听",
    "竖着耳朵",
    "耳朵竖",
    "耳朵都竖",
    "你说啥",
    "假装没听见",
    "没听见",
    "再提示一下",
    "再提示",
    "继续说嘛",
    "主人慢慢说",
    "主人再说",
)

FAST_REPLY_REPEAT_SIMILARITY = 0.72

_PROFILE_TO_GATE = {
    "fast_llm": "llm_fast",
    "slow_llm": "llm_slow",
}


def _profile_to_gate_type(provider_profile: str) -> str:
    return _PROFILE_TO_GATE.get(provider_profile, "llm_slow")


def _normalize_reply_for_repeat(reply: str) -> str:
    return "".join(
        char
        for char in str(reply or "")
        if char not in " \t\r\n，。,.！？!?～~…"
    )


def _reply_similarity(left: str, right: str) -> float:
    left_norm = _normalize_reply_for_repeat(left)
    right_norm = _normalize_reply_for_repeat(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _is_duplicate_fast_reply(reply: str, cognition_context: Optional[Dict[str, Any]]) -> bool:
    normalized = _normalize_reply_for_repeat(reply)
    if not normalized or not cognition_context:
        return False
    recent_events = (
        cognition_context.get("recent_reply_history")
        or cognition_context.get("recent_exact_events")
        or []
    )
    for event in recent_events[-5:]:
        if not isinstance(event, dict):
            continue
        recent_reply = str(event.get("pet") or "")
        if _reply_similarity(reply, recent_reply) >= FAST_REPLY_REPEAT_SIMILARITY:
            return True
    return False


def _is_duplicate_reply(reply: str, cognition_context: Optional[Dict[str, Any]]) -> bool:
    return _is_duplicate_fast_reply(reply, cognition_context)


def _recent_reply_norms(cognition_context: Optional[Dict[str, Any]]) -> List[str]:
    if not cognition_context:
        return []
    recent_events = (
        cognition_context.get("recent_reply_history")
        or cognition_context.get("recent_exact_events")
        or []
    )
    return [
        _normalize_reply_for_repeat(str(event.get("pet") or ""))
        for event in recent_events[-5:]
        if isinstance(event, dict)
    ]


def _generic_recovery_replies() -> tuple[str, ...]:
    return (
        "收到，豆豆继续陪你聊。",
        "嗯，豆豆接着你的意思往下说。",
        "好，豆豆换个角度陪你继续。",
    )


def _select_generic_recovery_reply(
    cognition_context: Optional[Dict[str, Any]],
) -> str:
    recent = _recent_reply_norms(cognition_context)
    for reply in _generic_recovery_replies():
        if _normalize_reply_for_repeat(reply) not in recent:
            return reply
    return _generic_recovery_replies()[0]


def _select_duplicate_recovery_reply(
    cognition_context: Optional[Dict[str, Any]],
) -> str:
    recent = _recent_reply_norms(cognition_context)
    for reply in _generic_recovery_replies() + FAST_DUPLICATE_RECOVERY_REPLIES:
        if _normalize_reply_for_repeat(reply) not in recent:
            return reply
    return _generic_recovery_replies()[0]


def _select_distinct_reply(
    replies: tuple[str, ...],
    cognition_context: Optional[Dict[str, Any]],
) -> str:
    recent = _recent_reply_norms(cognition_context)
    for reply in replies:
        if _normalize_reply_for_repeat(reply) not in recent:
            return reply
    return replies[0]


def _event_user_text(event: Any) -> str:
    payload = getattr(event, "payload", {}) or {}
    return str(payload.get("user_text") or payload.get("text") or "")


def _select_successful_voice_repair_reply(
    cognition_context: Optional[Dict[str, Any]],
) -> str:
    return _select_generic_recovery_reply(cognition_context)


def _dedupe_fast_reply(
    fast_action: FastReplyAction,
    cognition_context: Optional[Dict[str, Any]],
) -> FastReplyAction:
    if not _is_duplicate_fast_reply(fast_action.reply, cognition_context):
        return fast_action
    return FastReplyAction(
        reply=_select_duplicate_recovery_reply(cognition_context),
        mood=fast_action.mood or "happy",
        action=fast_action.action or "speak",
        voice_style=fast_action.voice_style,
    )


def _is_successful_voice_event(event: Any) -> bool:
    if getattr(event, "type", "") != "voice_message":
        return False
    return bool(_event_user_text(event).strip())


def _contains_asr_failure_copy(reply: str) -> bool:
    text = str(reply or "")
    return any(marker in text for marker in ASR_FAILURE_COPY_MARKERS)


def _repair_successful_voice_reply(
    reply: str,
    cognition_context: Optional[Dict[str, Any]],
) -> str:
    if not _contains_asr_failure_copy(reply):
        return reply
    return _select_successful_voice_repair_reply(cognition_context)


def _first_behavior_action(action: Any, mood: str) -> str:
    if action and action.behavior_plan:
        for step in action.behavior_plan:
            if isinstance(step, dict):
                candidate = str(step.get("action") or "")
                if candidate in ALLOWED_BEHAVIOR_ACTIONS:
                    return candidate
    if mood == "happy":
        return "happy"
    if mood == "sleepy":
        return "nap"
    if mood in {"sad", "lonely", "concerned"}:
        return "comfort"
    if mood == "thinking":
        return "think"
    if mood == "excited":
        return "excited"
    if mood == "angry":
        return "deny"
    if mood == "shy":
        return "self_groom"
    return "speak"


def _provider_fallback_action(raw_action: Any, cognition_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if raw_action is not None:
        return raw_action
    reply = _select_distinct_reply(PROVIDER_FALLBACK_REPLIES, cognition_context)
    return {
        "reply": reply,
        "mood": "concerned",
        "face_type": "concerned",
        "animation": "tilt",
        "voice_style": "soft",
        "vibration": "none",
        "intent": "provider_fallback",
        "autonomy_notes": "provider unavailable or invalid output",
        "state_delta": {},
        "state_affect": {
            "interaction_tone": "comforting",
            "pet_effort": "none",
            "emotional_effect": "uncertain",
            "reason": "provider fallback",
        },
        "memory_update": {"should_save": False, "content": ""},
        "behavior_intent": "neutral_companion",
        "behavior_plan": [
            {"action": "confused", "slot": "before_speech", "duration_ms": 900},
            {"action": "speak", "slot": "speech", "duration_ms": 1400},
        ],
    }


def _dedupe_context_from_recent_events(
    cognition_context: Optional[Dict[str, Any]],
    event_log_store: Any,
    episode_id: str,
) -> Optional[Dict[str, Any]]:
    if event_log_store is None or not episode_id:
        return cognition_context
    try:
        raw_events = event_log_store.recent_events(episode_id=episode_id, limit=5)
    except Exception:
        return cognition_context
    recent_exact_events = []
    for event in raw_events:
        entry: Dict[str, Any] = {}
        if event.get("user_text"):
            entry["user"] = event["user_text"]
        if event.get("pet_reply"):
            entry["pet"] = event["pet_reply"]
        if entry:
            recent_exact_events.append(entry)
    recent_exact_events.reverse()
    if not recent_exact_events:
        return cognition_context
    merged = dict(cognition_context or {})
    merged["recent_exact_events"] = recent_exact_events
    return merged

class RuntimeDispatcher:
    def __init__(
        self,
        state_store: PetStateStore,
        brain: PetBrain,
        tts_provider: MockTTSProvider,
        registry: SkillRegistry,
        interaction_log=None,
        device_store=None,
        tick_service=None,
        episode_manager: EpisodeStore = None,
        event_log_store: EventLogStore = None,
        context_manager: ContextManager = None,
        memory_candidate_store=None,
        summary_job_store=None,
        maintenance_service=None,
        memory_manager=None,
        episode_summary_store=None,
        daily_summary_store=None,
        audio_job_manager=None,
        agent_run_registry=None,
        memory_card_manager=None,
        policy_guard=None,
        maintenance_worker=None,
        provider_gate=None,
        incident_store=None,
        memory_judgment_queue=None,
        notebook_manager=None,
    ) -> None:
        self.state_store = state_store
        self.brain = brain
        self.tts_provider = tts_provider
        self.registry = registry
        self.interaction_log = interaction_log
        self.device_store = device_store
        self.tick_service = tick_service
        self.episode_manager = episode_manager
        self.event_log_store = event_log_store
        self.context_manager = context_manager
        self.memory_candidate_store = memory_candidate_store
        self.summary_job_store = summary_job_store
        self.maintenance_service = maintenance_service
        self.memory_manager = memory_manager
        self.episode_summary_store = episode_summary_store
        self.daily_summary_store = daily_summary_store
        self.audio_job_manager = audio_job_manager
        self.agent_run_registry = agent_run_registry
        self.memory_card_manager = memory_card_manager
        self.policy_guard = policy_guard
        self.maintenance_worker = maintenance_worker
        self.provider_gate = provider_gate
        self.incident_store = incident_store
        self.memory_judgment_queue = memory_judgment_queue
        self.notebook_manager = notebook_manager
        self._event_lock = threading.RLock()
        # Health counters (lock-free, read by /api/health/watchdog)
        self.event_loop_tick: float = perf_counter()
        self.agent_inflight_start: float = 0.0
        self.active_requests: int = 0

    def handle_event(
        self,
        raw_event: Dict[str, Any],
        brain: PetBrain = None,
        synthesize_voice: bool = True,
    ) -> PetResponse:
        self.event_loop_tick = perf_counter()
        self.active_requests += 1
        try:
            self.agent_inflight_start = perf_counter()
            try:
                response = self._handle_event_split(raw_event, brain, synthesize_voice)
            finally:
                self.agent_inflight_start = 0.0

            # Maintenance tick runs OUTSIDE the event lock — never blocks response
            self._try_maintenance_tick()

            return response
        finally:
            self.active_requests = max(0, self.active_requests - 1)

    def _handle_event_split(
        self,
        raw_event: Dict[str, Any],
        brain: PetBrain = None,
        synthesize_voice: bool = True,
    ) -> PetResponse:
        """Three-phase event handling: snapshot → slow work → commit.

        Phase 1 (locked): Read state + version, apply tick, get episode, reserve IDs
        Phase 2 (unlocked): LLM call, tool execution, context building — uses immutable snapshot
        Phase 3 (locked): CAS save state, record event, enqueue audio
        """
        pipeline_start = perf_counter()
        event = normalize_event(raw_event)
        active_brain = brain or self.brain

        # --- AgentRun lifecycle begins ---
        run: AgentRun = None
        decision = None
        if self.agent_run_registry is not None:
            run = self.agent_run_registry.create(event_id=event.id)

        # ===== PHASE 1: LOCKED SNAPSHOT =====
        with self._event_lock:
            thinking_mode = bool(event.payload.get("thinking_mode", False))
            user_text = str(event.payload.get("user_text") or event.payload.get("text") or "")
            decision = decide_route(
                event_type=event.type,
                event_source=event.source,
                user_text=user_text,
                thinking_mode=thinking_mode,
            )
            if run:
                run.route = decision.route
                run.context_profile = decision.context_profile
                run.provider = decision.provider_profile
                run.sanitized_user_text = user_text[:500]
                run.set_status("planning")

            # Apply tick
            if self.tick_service is not None:
                self.tick_service.apply_if_due()

            # Read current state + version (immutable snapshot)
            current_state = self.state_store.get_state()
            state_before = dict(current_state)
            expected_version = current_state.get("version", 0)

            # Apply deterministic event rules
            ruled_state = apply_event_rules(current_state, event.type)

            # Get/create current episode
            episode = None
            closed_episode_id = None
            if self.episode_manager is not None:
                idle_min = self.context_manager.idle_episode_minutes if self.context_manager else 45
                episode, closed_episode_id = self.episode_manager.get_or_create_current(
                    idle_minutes=idle_min
                )
                if closed_episode_id and self.summary_job_store is not None:
                    self.summary_job_store.enqueue(closed_episode_id)

            episode_id = episode.get("episode_id", "") if episode else ""

        # ===== PHASE 2: SLOW WORK OUTSIDE LOCK =====

        # Build cognition context
        cognition_context = None
        if self.context_manager is not None:
            cognition_context = self.context_manager.build(
                event=event,
                pet_state=ruled_state,
                episode=episode,
                event_log_store=self.event_log_store,
                device_state=self._device_state(),
                skill_results=[],
                memory_manager=self.memory_manager,
                episode_summary_store=self.episode_summary_store,
                daily_summary_store=self.daily_summary_store,
                context_profile=decision.context_profile if decision else None,
                memory_card_manager=self.memory_card_manager,
                notebook_manager=self.notebook_manager,
            )
            if run:
                run.record("context_built", {
                    "profile": decision.context_profile if decision else "",
                    "budget_used": cognition_context.get("context_budget", {}).get("used_chars", 0),
                })

        # Build planning context
        planning_context = build_runtime_context(
            event,
            ruled_state,
            device_state=self._device_state(),
            cognition_context=cognition_context,
        )

        # Run skills (gated by route policy)
        if decision is None or decision.allow_tools:
            tool_start = perf_counter()
            skill_results = self._run_requested_skills(event, active_brain, planning_context)
            if run:
                run.timings_ms["tool"] = int((perf_counter() - tool_start) * 1000)
        else:
            skill_results = []
            if run:
                run.timings_ms["tool"] = 0

        # Record tool observations
        if run:
            for sr in skill_results:
                run.record("tool_observation", {
                    "skill_id": sr.get("skill_id", ""),
                    "ok": sr.get("ok", False),
                    "content": str(sr.get("content", ""))[:200],
                    "error": sr.get("error"),
                })
            run.requested_tools = [sr.get("skill_id", "") for sr in skill_results]
            run.tool_observations = [
                {
                    "skill_id": sr.get("skill_id", ""),
                    "ok": sr.get("ok", False),
                    "content": str(sr.get("content", ""))[:200],
                    "error": sr.get("error"),
                }
                for sr in skill_results
            ]

        # Rebuild context with skill results
        if self.context_manager is not None and cognition_context is not None:
            cognition_context = self.context_manager.build(
                event=event,
                pet_state=ruled_state,
                episode=episode,
                event_log_store=self.event_log_store,
                device_state=self._device_state(),
                skill_results=skill_results,
                memory_manager=self.memory_manager,
                episode_summary_store=self.episode_summary_store,
                daily_summary_store=self.daily_summary_store,
                context_profile=decision.context_profile if decision else None,
                memory_card_manager=self.memory_card_manager,
                notebook_manager=self.notebook_manager,
            )
        if run and skill_results:
            run.record("skill_finished", {"count": len(skill_results)})
        context = build_runtime_context(
            event,
            ruled_state,
            device_state=self._device_state(),
            skill_results=skill_results,
            cognition_context=cognition_context,
        )

        # Generate action (LLM call — the slowest part, gated by provider concurrency)
        is_fast_reply = decision and decision.route == "fast_reply"
        provider_type = _profile_to_gate_type(decision.provider_profile if decision else "slow_llm")
        llm_start = perf_counter()
        raw_action = None
        gate_acquired = False
        try:
            if self.provider_gate is not None:
                self.provider_gate.acquire(provider_type, blocking=True, timeout_s=25)
                gate_acquired = True
            try:
                if is_fast_reply:
                    raw_action = active_brain.generate_fast_reply_action(event, context)
                elif decision and decision.route == "thinking":
                    raw_action = active_brain.generate_thinking_action(event, context)
                else:
                    raw_action = active_brain.generate_action(event, context)
            except Exception:
                raw_action = None
        except ProviderBusyError:
            logger.warning("Provider %s busy, returning fallback", provider_type)
            raw_action = None
        finally:
            if gate_acquired and self.provider_gate is not None:
                try:
                    self.provider_gate.release(provider_type)
                except Exception:
                    pass
        if run:
            run.timings_ms["llm"] = int((perf_counter() - llm_start) * 1000)
        if run and raw_action is None:
            run.set_status("failed")
            if self.incident_store is not None:
                try:
                    self.incident_store.record("provider_error", {
                        "provider": provider_type,
                        "stage": "llm",
                        "event_type": event.type,
                    })
                except Exception:
                    pass
            run.error = "LLM provider exception"
        if run and run.status not in {"failed", "superseded"}:
            run.set_status("action_generated")

        fast_action = None
        if raw_action is None:
            raw_action = _provider_fallback_action(raw_action, cognition_context)

        if is_fast_reply:
            fast_action = guard_fast_reply_action(raw_action)
            if _is_successful_voice_event(event):
                fast_action.reply = _repair_successful_voice_reply(
                    fast_action.reply,
                    cognition_context,
                )
            fast_action = _dedupe_fast_reply(
                fast_action,
                _dedupe_context_from_recent_events(
                    cognition_context,
                    self.event_log_store,
                    episode_id,
                ),
            )
            if run:
                run.final_action = {
                    "reply": fast_action.reply[:200],
                    "mood": fast_action.mood or "idle",
                    "action": fast_action.action or "",
                    "voice_style": fast_action.voice_style,
                }
                run.sanitized_response_text = fast_action.reply[:500]
            # Minimal state update: mood + last_interaction_at only
            final_state = dict(ruled_state)
            if fast_action.mood:
                final_state["mood"] = fast_action.mood
            final_state["mode"] = "idle"
            final_state["last_interaction_at"] = datetime.utcnow().isoformat()
        else:
            action = guard_action(
                raw_action,
                max_reply_chars=self._max_reply_chars(active_brain),
                event_type=event.type,
            )
            if _is_successful_voice_event(event):
                action.reply = _repair_successful_voice_reply(
                    action.reply,
                    cognition_context,
                )
                dedupe_context = _dedupe_context_from_recent_events(
                    cognition_context,
                    self.event_log_store,
                    episode_id,
                )
                if _is_duplicate_reply(action.reply, dedupe_context):
                    action.reply = _select_duplicate_recovery_reply(
                        dedupe_context,
                    )
            if run:
                run.final_action = {
                    "reply": action.reply[:200],
                    "mood": action.mood,
                    "face_type": action.face_type,
                    "animation": action.animation,
                    "voice_style": action.voice_style,
                }
                run.sanitized_response_text = action.reply[:500]
            # Compute state delta (deterministic, can be recomputed on CAS retry)
            sanitized_delta = {k: v for k, v in action.state_delta.items() if k != "energy"}
            if "energy" in action.state_delta:
                logger.debug("Stripped energy from LLM state_delta (effort handles energy)")
            final_state = apply_state_delta(ruled_state, sanitized_delta)
            pre_llm_energy = int(ruled_state.get("energy", 0))
            effort = action.state_affect.pet_effort
            if effort == "medium":
                final_state["energy"] = min(
                    int(final_state.get("energy", 0)) - 2,
                    pre_llm_energy - 2,
                )
            elif effort == "high":
                final_state["energy"] = min(
                    int(final_state.get("energy", 0)) - 5,
                    pre_llm_energy - 4,
                )
                final_state["sleepiness"] = int(final_state.get("sleepiness", 0)) + 1
            final_state = clamp_state(final_state)
            final_state["mood"] = action.mood
            final_state["mode"] = "idle"
            final_state["last_interaction_at"] = datetime.utcnow().isoformat()

        # ===== PHASE 3: LOCKED COMMIT =====
        with self._event_lock:
            # CAS save state
            saved_state = self.state_store.save_state_cas(final_state, expected_version)
            if saved_state is None:
                # Version mismatch — re-read state and recompute deterministic deltas
                logger.info("CAS failed, retrying with fresh state")
                current_state = self.state_store.get_state()
                state_before = dict(current_state)
                ruled_state = apply_event_rules(current_state, event.type)
                if is_fast_reply:
                    final_state = dict(ruled_state)
                    if fast_action and fast_action.mood:
                        final_state["mood"] = fast_action.mood
                    final_state["mode"] = "idle"
                    final_state["last_interaction_at"] = datetime.utcnow().isoformat()
                else:
                    final_state = apply_state_delta(ruled_state, sanitized_delta)
                    if effort == "medium":
                        final_state["energy"] = min(
                            int(final_state.get("energy", 0)) - 2,
                            int(ruled_state.get("energy", 0)) - 2,
                        )
                    elif effort == "high":
                        final_state["energy"] = min(
                            int(final_state.get("energy", 0)) - 5,
                            int(ruled_state.get("energy", 0)) - 4,
                        )
                        final_state["sleepiness"] = int(final_state.get("sleepiness", 0)) + 1
                    final_state = clamp_state(final_state)
                    final_state["mood"] = action.mood
                    final_state["mode"] = "idle"
                    final_state["last_interaction_at"] = datetime.utcnow().isoformat()
                saved_state = self.state_store.save_state(final_state)

            # Record in event_log
            if self.event_log_store is not None and episode_id:
                if is_fast_reply:
                    self.event_log_store.record(
                        event_id=event.id,
                        episode_id=episode_id,
                        event_type=event.type,
                        source=event.source,
                        user_text=str(event.payload.get("user_text", "")),
                        pet_reply=fast_action.reply,
                        skill_results=None,
                        state_before=state_before,
                        state_after=saved_state,
                        mood_after=fast_action.mood or "idle",
                        state_affect=None,
                    )
                else:
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
                        state_affect=action.state_affect.dict(),
                    )
            if run and run.status not in {"failed", "superseded"}:
                run.set_status("committed")

            # Update episode event count
            if self.episode_manager is not None and episode_id:
                self.episode_manager.update_event_count(episode_id)

            # Close episode on exit_phrase
            closed_on_exit = None
            if event.type == "exit_phrase" and self.episode_manager is not None:
                closed_on_exit = self.episode_manager.close_current("exit_phrase")
                if closed_on_exit and self.summary_job_store is not None:
                    self.summary_job_store.enqueue(closed_on_exit)

            # TTS job
            voice_url = None
            audio_job_id = None
            if synthesize_voice:
                tts_text = fast_action.reply if is_fast_reply else action.reply
                tts_style = fast_action.voice_style if is_fast_reply else action.voice_style
                if self.audio_job_manager is not None:
                    audio_job_id = self.audio_job_manager.enqueue(
                        tts_text,
                        tts_style,
                        run_id=run.run_id if run else "",
                        event_id=event.id,
                        session_id=episode_id,
                    )
                    if run and audio_job_id:
                        run.audio_job_id = audio_job_id
                        run.record("audio_enqueued", {"job_id": audio_job_id})
                else:
                    try:
                        voice_url = self.tts_provider.synthesize(tts_text, tts_style)
                    except Exception:
                        voice_url = None

        # Post-commit work (outside lock)
        if not is_fast_reply:
            self._collect_memory_candidates(event, action, episode_id)

        reply_text = fast_action.reply if is_fast_reply else action.reply
        route = "fast_reply" if is_fast_reply else "thinking"

        # V1.4: after-turn memory summary is queued only. The summarizer LLM is
        # called later by maintenance, never before returning the response.
        memory_ack = None
        trigger_categories: List[str] = []
        if user_text:
            try:
                trigger_categories = detect_memory_triggers(user_text)
                if "explicit" in trigger_categories:
                    memory_ack = "我先记到小本本"
            except Exception:
                trigger_categories = []
        if user_text and self.memory_judgment_queue is not None:
            try:
                selected_memory = []
                if cognition_context:
                    raw_selected = cognition_context.get("selected_card_items") or []
                    if isinstance(raw_selected, list):
                        selected_memory = [str(item) for item in raw_selected[:10] if item]
                self.memory_judgment_queue.enqueue_turn_summary(
                    user_text=user_text,
                    pet_reply=reply_text,
                    route=route,
                    selected_memory=selected_memory,
                    trigger_categories=trigger_categories,
                )
            except Exception:
                pass

        if self.interaction_log is not None:
            if is_fast_reply:
                self.interaction_log.record(
                    event.type,
                    fast_action.reply,
                    fast_action.mood or "idle",
                    user_text=str(event.payload.get("user_text", "")),
                )
            else:
                self.interaction_log.record(
                    event.type,
                    action.reply,
                    action.mood,
                    user_text=str(event.payload.get("user_text", "")),
                )

        if self.event_log_store is not None:
            max_rows = self.context_manager.raw_max_rows if self.context_manager else 3000
            self.event_log_store.cleanup_if_needed(
                max_rows=max_rows,
                current_episode_id=episode_id or None,
            )

        # Finalize AgentRun
        if run:
            if run.status not in {"failed", "superseded"}:
                run.set_status("completed")
            run.timings_ms["total"] = int((perf_counter() - pipeline_start) * 1000)
            if episode_id:
                run.episode_id = episode_id
            # Persist to SQLite for postmortem
            if self.agent_run_registry is not None:
                self.agent_run_registry.persist_if_terminal(run)

        if is_fast_reply:
            from app.runtime.actions import MOOD_ANIMATION_MAP
            resp_mood = fast_action.mood or "idle"
            response = PetResponse(
                reply=fast_action.reply,
                mood=resp_mood,
                face_type=resp_mood,
                animation=MOOD_ANIMATION_MAP.get(resp_mood, "breathing"),
                vibration="none",
                voice_url=voice_url,
                pet_state=saved_state,
                runtime={
                    "event_id": event.id,
                    "skills_used": [],
                    "episode_id": episode_id,
                },
                audio_job_id=audio_job_id,
                state_affect=None,
                behavior_intent=None,
                behavior_plan=None,
                action=fast_action.action,
                route="fast_reply",
                memory_ack_hint=memory_ack,
            )
        else:
            response = PetResponse(
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
                audio_job_id=audio_job_id,
                state_affect=action.state_affect.dict(),
                behavior_intent=action.behavior_intent,
                behavior_plan=action.behavior_plan,
                action=_first_behavior_action(action, action.mood),
                route="thinking",
            )
        if run:
            response.runtime["run_id"] = run.run_id
            if decision:
                response.runtime["context_profile"] = decision.context_profile
                response.runtime["route_decision"] = decision.reason
            response.runtime["route"] = run.route
            response.runtime["provider"] = run.provider
            response.runtime["status"] = run.status
            response.runtime["timings_ms"] = dict(run.timings_ms)
        return response

    def _collect_memory_candidates(self, event, action, episode_id: str) -> None:
        """Route memory_update to candidate store. V1.3: explicit commands handled by trigger system."""
        # LLM suggestion — only via candidate store (no fallback)
        if self.memory_candidate_store is not None:
            if action.memory_update.should_save and action.memory_update.content:
                text = action.memory_update.content.strip()
                if self.policy_guard is not None:
                    text = self.policy_guard.filter_memory_candidate(text)
                if text:
                    self.memory_candidate_store.add(
                        source_event_id=event.id,
                        episode_id=episode_id,
                        candidate_text=text,
                        trigger_reason="llm_suggestion",
                    )

    def _max_reply_chars(self, brain: PetBrain) -> int:
        persona = getattr(getattr(brain, "settings", None), "persona_config", {}) or {}
        policy = persona.get("reply_policy") or {}
        try:
            return int(policy.get("max_chars", 500))
        except (TypeError, ValueError):
            return 500

    def _try_maintenance_tick(self) -> None:
        """Notify maintenance worker — never blocks the response."""
        if self.maintenance_worker is not None:
            self.maintenance_worker.notify()
        elif self.maintenance_service is not None:
            # Fallback: legacy per-event thread (should not happen after Task 8)
            t = threading.Thread(target=self._run_maintenance_tick, daemon=True)
            t.start()

    def _run_maintenance_tick(self) -> None:
        try:
            self.maintenance_service.tick()
        except Exception:
            logger.warning("Maintenance tick failed", exc_info=True)

    def _device_state(self) -> Dict[str, Any]:
        if self.device_store is None:
            return {}
        return self.device_store.get_state()

    def _run_requested_skills(
        self, event, brain: PetBrain, context
    ) -> List[Dict[str, Any]]:
        requests = self._planned_skill_requests(event, brain, context)
        max_calls = self.registry.max_calls_per_event()
        results: List[Dict[str, Any]] = []
        for skill_id, payload in requests[:max_calls]:
            if not self.registry.has_skill(skill_id):
                continue
            if self.policy_guard is not None:
                try:
                    payload = self.policy_guard.validate_skill_payload(
                        skill_id, payload, self.registry,
                    )
                except ValueError:
                    continue
            result = self.registry.run_skill(skill_id, payload)
            if self.policy_guard is not None:
                result = self.policy_guard.sanitize_skill_result(result)
            results.append(asdict(result))
        return results

    def _planned_skill_requests(self, event, brain: PetBrain, context) -> List[tuple]:
        if event.type not in {"voice_message", "text_message"}:
            return []
        if not self._looks_like_external_request(event):
            return []
        skill_catalog = ""
        if self.policy_guard is not None:
            skill_catalog = self.policy_guard.build_skill_catalog(self.registry)
        try:
            plan = brain.generate_skill_plan(event, context, skill_catalog=skill_catalog)
        except Exception:
            plan = {}
        raw_items = plan.get("skill_requests") or []
        if self.policy_guard is not None:
            requests = self.policy_guard.validate_skill_plan(raw_items, self.registry)
        else:
            requests = []
            for item in raw_items:
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
