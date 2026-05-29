from __future__ import annotations

import logging
import threading
from pathlib import Path
from time import perf_counter
from typing import Any, Dict

from app.pet.brain import PetBrain
from app.providers.audio_omni import (
    AudioUnderstanding,
    FALLBACK_AUDIO_UNDERSTANDING,
)
from app.providers.errors import ProviderError
from app.runtime.actions import PetResponse
from app.runtime.dispatcher import RuntimeDispatcher
from app.runtime.activation import classify_activation as _classify_activation
from app.runtime.voice_types import ASRTranscript, VoicePipelineResult, VoiceRouteInfo

logger = logging.getLogger(__name__)

FAST_ASR_RECOVERY_REPLIES = (
    "没听清，再说一次嘛~",
    "刚刚那句声音有点糊，主人再说一遍？",
    "豆豆听到一点点，但不敢乱猜，再讲一次嘛。",
    "这句没识别完整，主人说长一点好不好？",
    "豆豆刚刚没接准，换个说法再来一次？",
)


def _now_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


class VoicePipeline:
    def __init__(
        self,
        *,
        dispatcher: RuntimeDispatcher,
        fast_brain: PetBrain,
        slow_brain: PetBrain,
        asr_provider: Any,
        audio_provider: Any,
        slow_fallback_enabled: bool = True,
        fast_brain_provider_name: str = "fast_llm",
        slow_brain_provider_name: str = "slow_llm",
        activation_manager: Any = None,
        provider_gate: Any = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.fast_brain = fast_brain
        self.slow_brain = slow_brain
        self.asr_provider = asr_provider
        self.audio_provider = audio_provider
        self.slow_fallback_enabled = slow_fallback_enabled
        self.fast_brain_provider_name = fast_brain_provider_name
        self.slow_brain_provider_name = slow_brain_provider_name
        self.activation_manager = activation_manager
        self.provider_gate = provider_gate
        self._fast_asr_recovery_index = 0
        self._fast_asr_recovery_lock = threading.Lock()

    def handle(
        self,
        audio_path: Path,
        content_type: str,
        *,
        requested_route: str = "auto",
        thinking_mode: bool = False,
    ) -> VoicePipelineResult:
        requested = requested_route if requested_route in {"auto", "fast_reply", "thinking"} else "auto"
        if thinking_mode or requested == "thinking":
            return self._run_audio_understanding_route(
                audio_path,
                content_type,
                requested=requested,
                thinking_mode=thinking_mode,
            )
        return self._run_asr_route(
            audio_path,
            content_type,
            requested=requested,
            selected="fast_reply",
            thinking_mode=thinking_mode,
            brain=self.fast_brain,
            brain_provider_name=self.fast_brain_provider_name,
        )

    def _run_asr_route(
        self,
        audio_path: Path,
        content_type: str,
        *,
        requested: str,
        selected: str,
        thinking_mode: bool,
        brain: PetBrain,
        brain_provider_name: str,
    ) -> VoicePipelineResult:
        timings: Dict[str, int] = {}
        started = perf_counter()
        fallback_reason = ""
        emotion_source = "asr"
        try:
            transcript = self._transcribe_with_gate(audio_path, content_type)
        except Exception as exc:
            logger.info(
                "voice_asr_exception provider=%s error_type=%s",
                self._asr_name(),
                type(exc).__name__,
            )
            transcript = ASRTranscript(
                text="",
                confidence=0.0,
                provider=self._asr_name(),
                error_code="asr_provider_exception",
                error_message="ASR provider raised an exception",
            )
            fallback_reason = "asr_error"
        timings["asr"] = _now_ms(started)

        text = transcript.text.strip()
        if transcript.error_code:
            if transcript.error_code == "asr_timeout":
                fallback_reason = "asr_timeout"
            else:
                fallback_reason = "asr_provider_error"
        elif not text:
            fallback_reason = fallback_reason or "asr_empty"

        logger.info(
            "voice_asr_result selected=%s provider=%s text_len=%d confidence=%.3f "
            "fallback_reason=%s elapsed_ms=%d",
            selected,
            transcript.provider,
            len(text),
            transcript.confidence,
            fallback_reason or "none",
            timings["asr"],
        )

        if fallback_reason:
            if thinking_mode and self.slow_fallback_enabled:
                result = self._run_audio_fallback(
                    audio_path,
                    content_type,
                    requested=requested,
                    thinking_mode=thinking_mode,
                    fallback_reason=fallback_reason,
                )
                merged = dict(result.route_info.timings_ms)
                merged.setdefault("asr", timings["asr"])
                result = VoicePipelineResult(
                    user_text=result.user_text,
                    audio_understanding=result.audio_understanding,
                    response=result.response,
                    route_info=VoiceRouteInfo(
                        requested=result.route_info.requested,
                        selected=result.route_info.selected,
                        thinking_mode=result.route_info.thinking_mode,
                        asr_provider=transcript.provider,
                        asr_error_code=transcript.error_code,
                        asr_error_message=transcript.error_message,
                        brain_provider=result.route_info.brain_provider,
                        fallback_reason=fallback_reason,
                        emotion_source=result.route_info.emotion_source,
                        wake_source=result.route_info.wake_source,
                        provider_failure=result.route_info.provider_failure,
                        timings_ms=merged,
                    ),
                    fallback_reason=fallback_reason,
                )
                return result
            elif not thinking_mode:
                # Fast reply: ASR failed, return local recovery instead of heavy fallback
                timings["total"] = _now_ms(started)
                recovery_reply = self._next_fast_asr_recovery_reply()
                fallback_response = PetResponse(
                    reply=recovery_reply,
                    mood="idle",
                    face_type="idle",
                    animation="breathing",
                    vibration="none",
                    pet_state={},
                    runtime={"error_class": "asr_failed"},
                    route="fast_reply",
                )
                return VoicePipelineResult(
                    user_text="",
                    audio_understanding=FALLBACK_AUDIO_UNDERSTANDING,
                    response=fallback_response,
                    route_info=VoiceRouteInfo(
                        requested=requested,
                        selected="fast_reply",
                        thinking_mode=False,
                        asr_provider=transcript.provider,
                        asr_error_code=transcript.error_code,
                        asr_error_message=transcript.error_message,
                        brain_provider=self.fast_brain_provider_name,
                        fallback_reason=fallback_reason,
                        emotion_source="none",
                        asr_failed_hint="没听清",
                        timings_ms=timings,
                    ),
                    fallback_reason=fallback_reason,
                )
            understanding = FALLBACK_AUDIO_UNDERSTANDING
        else:
            understanding = AudioUnderstanding(
                user_text=text,
                detected_emotion="uncertain",
                tone_notes="fast ASR route only",
                non_verbal="",
                confidence=transcript.confidence,
            )

        brain_started = perf_counter()

        # Check for wake/exit phrase before dispatching as voice_message
        activation_event = _classify_activation(understanding.user_text, self.activation_manager)
        activation_info = None
        wake_source = ""
        if activation_event is not None:
            wake_source = "text" if understanding.user_text.strip() else "audio_understanding"
            activation_event.setdefault("payload", {})["thinking_mode"] = thinking_mode
            response = self.dispatcher.handle_event(activation_event, brain=brain)
            activation_info = self._build_activation_info(activation_event["type"])
        else:
            response = self.dispatcher.handle_event(
                {
                    "type": "voice_message",
                    "source": "voice_%s" % selected,
                    "payload": {
                        "user_text": understanding.user_text,
                        "audio_understanding": understanding.dict(),
                        "thinking_mode": thinking_mode,
                    },
                },
                brain=brain,
            )
        timings["brain_tts"] = _now_ms(brain_started)
        timings["total"] = _now_ms(started)
        return VoicePipelineResult(
            user_text=understanding.user_text,
            audio_understanding=understanding,
            response=response,
            route_info=VoiceRouteInfo(
                requested=requested,
                selected=selected,
                thinking_mode=thinking_mode,
                asr_provider=transcript.provider,
                asr_error_code=transcript.error_code,
                asr_error_message=transcript.error_message,
                brain_provider=brain_provider_name,
                fallback_reason=fallback_reason,
                emotion_source=emotion_source,
                wake_source=wake_source,
                timings_ms=timings,
            ),
            fallback_reason=fallback_reason or None,
            activation=activation_info,
        )

    def _run_audio_understanding_route(
        self,
        audio_path: Path,
        content_type: str,
        *,
        requested: str,
        thinking_mode: bool,
    ) -> VoicePipelineResult:
        timings: Dict[str, int] = {}
        started = perf_counter()
        emotion_source = "fallback"

        # Step 1: Try audio understanding first
        provider_failure = None
        try:
            understanding = self._understand_with_gate(audio_path, content_type)
        except ProviderError as exc:
            provider_failure = exc.to_dict()
            understanding = FALLBACK_AUDIO_UNDERSTANDING
            logger.info(
                "voice_audio_understanding_provider_error provider_failure=%s",
                provider_failure.get("error_class"),
            )
        except Exception as exc:
            logger.info("voice_audio_understanding_exception error_type=%s", type(exc).__name__)
            understanding = FALLBACK_AUDIO_UNDERSTANDING
        timings["audio_understanding"] = _now_ms(started)

        # Step 2: Check if audio understanding gave usable text
        has_usable_text = bool(understanding.user_text.strip())

        transcript = None
        if has_usable_text:
            emotion_source = "audio_understanding"
            # Optionally run ASR as transcript assist (non-blocking)
            asr_start = perf_counter()
            try:
                transcript = self._transcribe_with_gate(audio_path, content_type)
            except Exception as exc:
                logger.info("voice_asr_assist_exception error_type=%s", type(exc).__name__)
            timings["asr_assist"] = _now_ms(asr_start)
        else:
            # Audio understanding failed or returned empty — fall back to ASR
            asr_start = perf_counter()
            try:
                transcript = self._transcribe_with_gate(audio_path, content_type)
            except Exception as exc:
                logger.info("voice_asr_fallback_exception error_type=%s", type(exc).__name__)
                transcript = ASRTranscript(
                    text="",
                    confidence=0.0,
                    provider=self._asr_name(),
                    error_code="asr_provider_exception",
                    error_message="ASR provider raised an exception",
                )
            timings["asr"] = _now_ms(asr_start)

            if transcript.text.strip():
                # ASR succeeded — use it, but note emotion came from ASR
                understanding = AudioUnderstanding(
                    user_text=transcript.text.strip(),
                    detected_emotion="uncertain",
                    tone_notes="ASR fallback, no audio understanding",
                    non_verbal="",
                    confidence=transcript.confidence,
                )
                emotion_source = "asr"
            else:
                # Both failed — use fallback understanding
                emotion_source = "fallback"

        brain_started = perf_counter()

        # Check for wake/exit phrase
        activation_event = _classify_activation(understanding.user_text, self.activation_manager)
        activation_info = None
        wake_source = ""
        final_has_text = bool(understanding.user_text.strip())
        if not final_has_text:
            timings["total"] = _now_ms(started)
            fallback_reason = "audio_understanding_insufficient"
            if transcript is not None and transcript.error_code:
                fallback_reason = (
                    "asr_timeout" if transcript.error_code == "asr_timeout" else "asr_provider_error"
                )
            recovery_reply = self._next_fast_asr_recovery_reply()
            response = PetResponse(
                reply=recovery_reply,
                mood="idle",
                face_type="idle",
                animation="breathing",
                vibration="none",
                pet_state={},
                runtime={"error_class": "asr_failed"},
                route="thinking",
                action="confused",
            )
            return VoicePipelineResult(
                user_text="",
                audio_understanding=understanding,
                response=response,
                route_info=VoiceRouteInfo(
                    requested=requested,
                    selected="thinking",
                    thinking_mode=thinking_mode,
                    asr_provider=getattr(transcript, "provider", "") if transcript else "",
                    asr_error_code=getattr(transcript, "error_code", "") if transcript else "",
                    asr_error_message=getattr(transcript, "error_message", "") if transcript else "",
                    brain_provider=self.slow_brain_provider_name,
                    fallback_reason=fallback_reason,
                    emotion_source=emotion_source,
                    provider_failure=provider_failure,
                    asr_failed_hint="没听清",
                    timings_ms=timings,
                ),
                fallback_reason=fallback_reason,
            )
        if activation_event is not None:
            wake_source = "text" if understanding.user_text.strip() else "audio_understanding"
            activation_event.setdefault("payload", {})["thinking_mode"] = thinking_mode
            response = self.dispatcher.handle_event(activation_event, brain=self.slow_brain)
            activation_info = self._build_activation_info(activation_event["type"])
        else:
            response = self.dispatcher.handle_event(
                {
                    "type": "voice_message",
                    "source": "voice_thinking",
                    "payload": {
                        "user_text": understanding.user_text,
                        "audio_understanding": understanding.dict(),
                        "thinking_mode": thinking_mode,
                    },
                },
                brain=self.slow_brain,
            )
        timings["brain_tts"] = _now_ms(brain_started)
        timings["total"] = _now_ms(started)
        return VoicePipelineResult(
            user_text=understanding.user_text,
            audio_understanding=understanding,
            response=response,
            route_info=VoiceRouteInfo(
                requested=requested,
                selected="thinking",
                thinking_mode=thinking_mode,
                asr_provider=getattr(transcript, "provider", "") if transcript else "",
                brain_provider=self.slow_brain_provider_name,
                fallback_reason="" if final_has_text else "audio_understanding_insufficient",
                emotion_source=emotion_source,
                wake_source=wake_source,
                provider_failure=provider_failure,
                timings_ms=timings,
            ),
            fallback_reason=None if final_has_text else "audio_understanding_insufficient",
            activation=activation_info,
        )

    def _run_audio_fallback(
        self,
        audio_path: Path,
        content_type: str,
        *,
        requested: str,
        thinking_mode: bool,
        fallback_reason: str,
    ) -> VoicePipelineResult:
        timings: Dict[str, int] = {}
        started = perf_counter()
        provider_failure = None
        try:
            understanding = self._understand_with_gate(audio_path, content_type)
        except ProviderError as exc:
            understanding = FALLBACK_AUDIO_UNDERSTANDING
            provider_failure = exc.to_dict()
            fallback_reason = fallback_reason or "audio_understanding_error"
            logger.info(
                "voice_audio_fallback_provider_error provider_failure=%s",
                provider_failure.get("error_class"),
            )
        except Exception as exc:
            logger.info("voice_audio_fallback_exception error_type=%s", type(exc).__name__)
            understanding = FALLBACK_AUDIO_UNDERSTANDING
            fallback_reason = fallback_reason or "audio_understanding_error"
        timings["audio_understanding"] = _now_ms(started)

        brain_started = perf_counter()

        # Check for wake/exit phrase before dispatching as voice_message
        activation_event = _classify_activation(understanding.user_text, self.activation_manager)
        activation_info = None
        if activation_event is not None:
            activation_event.setdefault("payload", {})["thinking_mode"] = thinking_mode
            response = self.dispatcher.handle_event(activation_event, brain=self.slow_brain)
            activation_info = self._build_activation_info(activation_event["type"])
        else:
            response = self.dispatcher.handle_event(
                {
                    "type": "voice_message",
                    "source": "voice_thinking",
                    "payload": {
                        "user_text": understanding.user_text,
                        "audio_understanding": understanding.dict(),
                        "thinking_mode": thinking_mode,
                    },
                },
                brain=self.slow_brain,
            )
        timings["brain_tts"] = _now_ms(brain_started)
        timings["total"] = _now_ms(started)
        return VoicePipelineResult(
            user_text=understanding.user_text,
            audio_understanding=understanding,
            response=response,
            route_info=VoiceRouteInfo(
                requested=requested,
                selected="thinking",
                thinking_mode=thinking_mode,
                asr_provider="",
                brain_provider=self.slow_brain_provider_name,
                fallback_reason=fallback_reason,
                emotion_source="fallback",
                provider_failure=provider_failure,
                timings_ms=timings,
            ),
            fallback_reason=fallback_reason or None,
            activation=activation_info,
        )

    def _build_activation_info(self, event_type: str) -> Dict[str, Any]:
        """Build activation info dict from the activation manager state."""
        if self.activation_manager is None:
            return {"type": event_type, "active": False}
        state = self.activation_manager.state
        return {
            "type": event_type,
            "active": state.active,
            "session_id": state.session_id,
        }

    def _asr_name(self) -> str:
        return str(getattr(self.asr_provider, "name", "unknown_asr"))

    def _next_fast_asr_recovery_reply(self) -> str:
        with self._fast_asr_recovery_lock:
            reply = FAST_ASR_RECOVERY_REPLIES[
                self._fast_asr_recovery_index % len(FAST_ASR_RECOVERY_REPLIES)
            ]
            self._fast_asr_recovery_index += 1
            return reply

    def _transcribe_with_gate(self, audio_path: Path, content_type: str) -> ASRTranscript:
        acquired = False
        if self.provider_gate is not None:
            self.provider_gate.acquire("asr", blocking=True, timeout_s=30)
            acquired = True
        try:
            return self.asr_provider.transcribe(audio_path, content_type)
        finally:
            if acquired and self.provider_gate is not None:
                self.provider_gate.release("asr")

    def _understand_with_gate(self, audio_path: Path, content_type: str) -> AudioUnderstanding:
        acquired = False
        if self.provider_gate is not None:
            self.provider_gate.acquire("audio_understanding", blocking=True, timeout_s=60)
            acquired = True
        try:
            return self.audio_provider.understand(audio_path, content_type)
        finally:
            if acquired and self.provider_gate is not None:
                self.provider_gate.release("audio_understanding")
