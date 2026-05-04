from __future__ import annotations

import importlib
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.config import ProviderConfig
from app.runtime.voice_types import ASRTranscript


class ASRInputError(ValueError):
    pass


@dataclass(frozen=True)
class WavASRSpec:
    sample_rate: int
    channels: int
    sample_width: int
    pcm_bytes: bytes


def inspect_wav_for_asr(audio_path: Path) -> WavASRSpec:
    try:
        with wave.open(str(audio_path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            pcm_bytes = handle.readframes(handle.getnframes())
    except wave.Error as exc:
        raise ASRInputError("input must be a readable WAV file") from exc

    if channels != 1:
        raise ASRInputError("NVIDIA Parakeet ASR expects mono WAV input")
    if sample_width != 2:
        raise ASRInputError("NVIDIA Parakeet ASR expects 16-bit PCM WAV input")
    if not pcm_bytes:
        raise ASRInputError("WAV input has no PCM frames")

    return WavASRSpec(
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
        pcm_bytes=pcm_bytes,
    )


def _load_riva_module() -> Optional[Any]:
    try:
        client_module = importlib.import_module("riva.client")

        class RivaModule:
            client = client_module

        return RivaModule
    except Exception:
        return None


class NvidiaParakeetASRProvider:
    def __init__(
        self, config: ProviderConfig, riva_module: Optional[Any] = None
    ) -> None:
        self.config = config
        self.riva = riva_module if riva_module is not None else _load_riva_module()
        self.name = config.name or "nvidia_parakeet"

    def transcribe(self, audio_path: Path, content_type: str) -> ASRTranscript:
        if "wav" not in content_type and audio_path.suffix.lower() != ".wav":
            return ASRTranscript(text="", confidence=0.0, provider=self.name)
        if not self.config.api_key or not self.config.base_url or self.riva is None:
            return ASRTranscript(text="", confidence=0.0, provider=self.name)

        try:
            spec = inspect_wav_for_asr(audio_path)
            response = self._recognize(spec)
            return self._parse_response(response)
        except Exception:
            return ASRTranscript(text="", confidence=0.0, provider=self.name)

    def _recognize(self, spec: WavASRSpec) -> Any:
        client = self.riva.client
        metadata = [
            ["authorization", "Bearer %s" % self.config.api_key],
        ]
        function_id = self.config.extra.get("function_id")
        if function_id:
            metadata.append(["function-id", str(function_id)])

        auth = client.Auth(
            uri=self.config.base_url,
            use_ssl=True,
            metadata_args=metadata,
        )
        service = client.ASRService(auth)
        recognition_config = client.RecognitionConfig(
            encoding=client.AudioEncoding.LINEAR_PCM,
            language_code=str(self.config.extra.get("language_code") or "zh-CN"),
            max_alternatives=1,
            enable_automatic_punctuation=True,
            audio_channel_count=1,
            sample_rate_hertz=spec.sample_rate,
        )
        return service.offline_recognize(spec.pcm_bytes, recognition_config)

    def _parse_response(self, response: Any) -> ASRTranscript:
        for result in getattr(response, "results", []) or []:
            alternatives = getattr(result, "alternatives", []) or []
            if not alternatives:
                continue
            best = alternatives[0]
            text = str(getattr(best, "transcript", "") or "").strip()
            if text:
                confidence = float(getattr(best, "confidence", 0.0) or 0.0)
                return ASRTranscript(
                    text=text,
                    confidence=max(0.0, min(1.0, confidence)),
                    provider=self.name,
                )
        return ASRTranscript(text="", confidence=0.0, provider=self.name)
