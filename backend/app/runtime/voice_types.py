from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AudioUnderstanding:
    user_text: str
    detected_emotion: str
    tone_notes: str
    non_verbal: str
    confidence: float

    def dict(self) -> Dict[str, Any]:
        return {
            "user_text": self.user_text,
            "detected_emotion": self.detected_emotion,
            "tone_notes": self.tone_notes,
            "non_verbal": self.non_verbal,
            "confidence": self.confidence,
        }


FALLBACK_AUDIO_UNDERSTANDING = AudioUnderstanding(
    user_text="",
    detected_emotion="uncertain",
    tone_notes="没有稳定识别到语音",
    non_verbal="",
    confidence=0.0,
)


@dataclass(frozen=True)
class ASRTranscript:
    text: str
    confidence: float = 0.0
    provider: str = "unknown"
    error_code: str = ""
    error_message: str = ""

    def dict(self) -> Dict[str, Any]:
        body = {
            "text": self.text,
            "confidence": max(0.0, min(1.0, float(self.confidence))),
            "provider": self.provider,
        }
        if self.error_code:
            body["error_code"] = self.error_code
        if self.error_message:
            body["error_message"] = self.error_message
        return body


@dataclass(frozen=True)
class VoiceRouteInfo:
    requested: str
    selected: str
    thinking_mode: bool
    asr_provider: str = ""
    asr_error_code: str = ""
    asr_error_message: str = ""
    brain_provider: str = ""
    fallback_reason: str = ""
    emotion_source: str = ""
    wake_source: str = ""
    asr_failed_hint: Optional[str] = None
    timings_ms: Dict[str, int] = field(default_factory=dict)

    def dict(self) -> Dict[str, Any]:
        body = {
            "requested": self.requested,
            "selected": self.selected,
            "thinking_mode": self.thinking_mode,
            "asr_provider": self.asr_provider,
            "asr_error_code": self.asr_error_code,
            "asr_error_message": self.asr_error_message,
            "brain_provider": self.brain_provider,
            "fallback_reason": self.fallback_reason,
            "emotion_source": self.emotion_source,
            "wake_source": self.wake_source,
            "timings_ms": dict(self.timings_ms),
        }
        if self.asr_failed_hint:
            body["asr_failed_hint"] = self.asr_failed_hint
        return body


@dataclass(frozen=True)
class VoicePipelineResult:
    user_text: str
    audio_understanding: Any
    response: Any
    route_info: VoiceRouteInfo
    fallback_reason: Optional[str] = None
    activation: Optional[Dict[str, Any]] = None
