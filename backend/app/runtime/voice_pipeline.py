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
from app.runtime.voice_types import ASRTranscript, VoicePipelineResult, VoiceRouteInfo


def _classify_activation(text, activation_manager):
    """Check if text matches wake/exit phrases. Returns event dict or None."""
    if not text or activation_manager is None:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    if activation_manager.phrase_matches(stripped, activation_manager.exit_phrases()):
        activation_manager.exit(stripped, confidence=1.0)
        return {"type": "exit_phrase", "source": "voice", "payload": {"user_text": stripped}}
    if activation_manager.phrase_matches(stripped, activation_manager.wake_phrases()):
        activation_manager.wake(stripped, confidence=1.0, source="voice")
        return {"type": "wake_phrase", "source": "voice", "payload": {"user_text": stripped}}
    return None


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
            return self._run_slow(
                audio_path,
                content_type,
                requested=requested,
                thinking_mode=thinking_mode,
                fallback_reason="",
            )
        return self._run_fast(
            audio_path,
            content_type,
            requested=requested,
            thinking_mode=thinking_mode,
        )

    def _run_fast(
        self,
        audio_path: Path,
        content_type: str,
        *,
        requested: str,
        thinking_mode: bool,
    ) -> VoicePipelineResult:
        timings: Dict[str, int] = {}
        started = perf_counter()
        fallback_reason = ""
        try:
            transcript = self.asr_provider.transcribe(audio_path, content_type)
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
            fallback_reason = "asr_provider_error"
        elif not text:
            fallback_reason = fallback_reason or "asr_empty"
        elif transcript.confidence < self.asr_min_confidence:
            fallback_reason = "asr_low_confidence"

        if fallback_reason:
            if self.slow_fallback_enabled:
                result = self._run_slow(
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
        if activation_event is not None:
            response = self.dispatcher.handle_event(activation_event, brain=self.fast_brain)
            activation_info = self._build_activation_info(activation_event["type"])
        else:
            response = self.dispatcher.handle_event(
                {
                    "type": "voice_message",
                    "source": "voice_fast",
                    "payload": {
                        "user_text": understanding.user_text,
                        "audio_understanding": understanding.dict(),
                    },
                },
                brain=self.fast_brain,
            )
        timings["brain_tts"] = _now_ms(brain_started)
        timings["total"] = _now_ms(started)
        return VoicePipelineResult(
            user_text=understanding.user_text,
            audio_understanding=understanding,
            response=response,
            route_info=VoiceRouteInfo(
                requested=requested,
                selected="fast",
                thinking_mode=thinking_mode,
                asr_provider=transcript.provider,
                asr_error_code=transcript.error_code,
                asr_error_message=transcript.error_message,
                brain_provider=self.fast_brain_provider_name,
                fallback_reason=fallback_reason,
                timings_ms=timings,
            ),
            fallback_reason=fallback_reason or None,
            activation=activation_info,
        )

    def _run_slow(
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
            understanding = self.audio_provider.understand(audio_path, content_type)
        except Exception:
            understanding = FALLBACK_AUDIO_UNDERSTANDING
            fallback_reason = fallback_reason or "audio_understanding_error"
        timings["audio_understanding"] = _now_ms(started)

        brain_started = perf_counter()

        # Check for wake/exit phrase before dispatching as voice_message
        activation_event = _classify_activation(understanding.user_text, self.activation_manager)
        activation_info = None
        if activation_event is not None:
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
