from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ASRTranscript:
    text: str
    confidence: float = 0.0
    provider: str = "unknown"

    def dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": max(0.0, min(1.0, float(self.confidence))),
            "provider": self.provider,
        }


@dataclass(frozen=True)
class VoiceRouteInfo:
    requested: str
    selected: str
    thinking_mode: bool
    asr_provider: str = ""
    brain_provider: str = ""
    fallback_reason: str = ""
    timings_ms: Dict[str, int] = field(default_factory=dict)

    def dict(self) -> Dict[str, Any]:
        return {
            "requested": self.requested,
            "selected": self.selected,
            "thinking_mode": self.thinking_mode,
            "asr_provider": self.asr_provider,
            "brain_provider": self.brain_provider,
            "fallback_reason": self.fallback_reason,
            "timings_ms": dict(self.timings_ms),
        }


@dataclass(frozen=True)
class VoicePipelineResult:
    user_text: str
    audio_understanding: Any
    response: Any
    route_info: VoiceRouteInfo
    fallback_reason: Optional[str] = None
