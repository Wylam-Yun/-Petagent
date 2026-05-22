from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Dict

from app.pet.brain import PetBrain
from app.providers.audio_omni import (
    AudioUnderstanding,
    FALLBACK_AUDIO_UNDERSTANDING,
)
from app.runtime.dispatcher import RuntimeDispatcher
from app.runtime.activation import classify_activation as _classify_activation
from app.runtime.voice_types import ASRTranscript, VoicePipelineResult, VoiceRouteInfo


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
        asr_min_confidence: float = 0.0,
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
        self.asr_min_confidence = asr_min_confidence
        self.fast_brain_provider_name = fast_brain_provider_name
        self.slow_brain_provider_name = slow_brain_provider_name
        self.activation_manager = activation_manager
        self.provider_gate = provider_gate

    def handle(
        self,
        audio_path: Path,
        content_type: str,
        *,
        requested_route: str = "auto",
        thinking_mode: bool = False,
    ) -> VoicePipelineResult:
        requested = requested_route if requested_route in {"auto", "fast", "slow"} else "auto"
        if thinking_mode or requested == "slow":
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
            selected="fast",
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
        except Exception:
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
            fallback_reason = "asr_timeout" if transcript.error_code == "asr_timeout" else "asr_provider_error"
        elif not text:
            fallback_reason = fallback_reason or "asr_empty"
        elif transcript.confidence < self.asr_min_confidence:
            fallback_reason = "asr_low_confidence"

        if fallback_reason:
            if self.slow_fallback_enabled:
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
                        timings_ms=merged,
                    ),
                    fallback_reason=fallback_reason,
                )
                return result
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
        try:
            understanding = self._understand_with_gate(audio_path, content_type)
        except Exception:
            understanding = FALLBACK_AUDIO_UNDERSTANDING
        timings["audio_understanding"] = _now_ms(started)

        # Step 2: Check if audio understanding gave usable text
        has_usable_text = bool(understanding.user_text.strip()) and understanding.confidence >= 0.3

        transcript = None
        if has_usable_text:
            emotion_source = "audio_understanding"
            # Optionally run ASR as transcript assist (non-blocking)
            asr_start = perf_counter()
            try:
                transcript = self._transcribe_with_gate(audio_path, content_type)
            except Exception:
                pass
            timings["asr_assist"] = _now_ms(asr_start)
        else:
            # Audio understanding failed or returned empty — fall back to ASR
            asr_start = perf_counter()
            try:
                transcript = self._transcribe_with_gate(audio_path, content_type)
            except Exception:
                transcript = ASRTranscript(
                    text="",
                    confidence=0.0,
                    provider=self._asr_name(),
                    error_code="asr_provider_exception",
                    error_message="ASR provider raised an exception",
                )
            timings["asr"] = _now_ms(asr_start)

            if transcript.text.strip() and transcript.confidence >= self.asr_min_confidence:
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
        if activation_event is not None:
            wake_source = "text" if understanding.user_text.strip() else "audio_understanding"
            activation_event.setdefault("payload", {})["thinking_mode"] = thinking_mode
            response = self.dispatcher.handle_event(activation_event, brain=self.slow_brain)
            activation_info = self._build_activation_info(activation_event["type"])
        else:
            response = self.dispatcher.handle_event(
                {
                    "type": "voice_message",
                    "source": "voice_slow",
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
                selected="slow",
                thinking_mode=thinking_mode,
                asr_provider=getattr(transcript, "provider", "") if transcript else "",
                brain_provider=self.slow_brain_provider_name,
                fallback_reason="" if has_usable_text else "audio_understanding_insufficient",
                emotion_source=emotion_source,
                wake_source=wake_source,
                timings_ms=timings,
            ),
            fallback_reason=None if has_usable_text else "audio_understanding_insufficient",
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
        try:
            understanding = self._understand_with_gate(audio_path, content_type)
        except Exception:
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
                    "source": "voice_slow",
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
                selected="slow",
                thinking_mode=thinking_mode,
                asr_provider="",
                brain_provider=self.slow_brain_provider_name,
                fallback_reason=fallback_reason,
                emotion_source="fallback",
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

    def _transcribe_with_gate(self, audio_path: Path, content_type: str) -> ASRTranscript:
        acquired = False
        if self.provider_gate is not None:
            self.provider_gate.acquire("asr")
            acquired = True
        try:
            return self.asr_provider.transcribe(audio_path, content_type)
        finally:
            if acquired and self.provider_gate is not None:
                self.provider_gate.release("asr")

    def _understand_with_gate(self, audio_path: Path, content_type: str) -> AudioUnderstanding:
        acquired = False
        if self.provider_gate is not None:
            self.provider_gate.acquire("audio_understanding")
            acquired = True
        try:
            return self.audio_provider.understand(audio_path, content_type)
        finally:
            if acquired and self.provider_gate is not None:
                self.provider_gate.release("audio_understanding")
