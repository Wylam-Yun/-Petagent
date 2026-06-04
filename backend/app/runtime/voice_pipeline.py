from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Dict

from app.pet.brain import PetBrain
from app.runtime.actions import PetResponse
from app.runtime.dispatcher import RuntimeDispatcher
from app.runtime.activation import classify_activation as _classify_activation
from app.runtime.voice_types import (
    ASRTranscript,
    AudioUnderstanding,
    FALLBACK_AUDIO_UNDERSTANDING,
    VoicePipelineResult,
    VoiceRouteInfo,
)


def _now_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


def _asr_failure_code(transcript: ASRTranscript, fallback_reason: str) -> str:
    if transcript.error_code:
        return transcript.error_code
    return fallback_reason or "asr_failed"


class VoicePipeline:
    def __init__(
        self,
        *,
        dispatcher: RuntimeDispatcher,
        fast_brain: PetBrain,
        asr_provider: Any,
        asr_min_confidence: float = 0.0,
        fast_brain_provider_name: str = "fast_llm",
        activation_manager: Any = None,
        provider_gate: Any = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.fast_brain = fast_brain
        self.asr_provider = asr_provider
        self.asr_min_confidence = asr_min_confidence
        self.fast_brain_provider_name = fast_brain_provider_name
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
        requested = "auto"
        effective_thinking_mode = False
        return self._run_asr_route(
            audio_path,
            content_type,
            requested=requested,
            selected="unified",
            thinking_mode=effective_thinking_mode,
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
            if transcript.error_code == "asr_empty":
                fallback_reason = "asr_empty"
            elif transcript.error_code == "asr_timeout":
                fallback_reason = "asr_timeout"
            else:
                fallback_reason = "asr_provider_error"
        elif not text:
            fallback_reason = fallback_reason or "asr_empty"
        elif transcript.confidence < self.asr_min_confidence:
            fallback_reason = "asr_low_confidence"

        if fallback_reason:
            timings["total"] = _now_ms(started)
            error_code = _asr_failure_code(transcript, fallback_reason)
            failure_response = PetResponse(
                reply="",
                mood="idle",
                face_type="idle",
                animation="breathing",
                vibration="none",
                pet_state={},
                runtime={"error_class": error_code},
                route=selected,
            )
            return VoicePipelineResult(
                user_text="",
                audio_understanding=FALLBACK_AUDIO_UNDERSTANDING,
                response=failure_response,
                route_info=VoiceRouteInfo(
                    requested=requested,
                    selected=selected,
                    thinking_mode=thinking_mode,
                    asr_provider=transcript.provider,
                    asr_error_code=error_code,
                    asr_error_message=transcript.error_message,
                    brain_provider=brain_provider_name,
                    fallback_reason=fallback_reason,
                    emotion_source="none",
                    timings_ms=timings,
                ),
                fallback_reason=fallback_reason,
            )
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
            activation_event.setdefault("payload", {})["thinking_mode"] = False
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
                        "thinking_mode": False,
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
