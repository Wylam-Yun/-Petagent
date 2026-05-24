from __future__ import annotations

import binascii
import io
import json
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Union

import requests

from app.config import Settings
from app.providers.errors import (
    ProviderAuthError,
    ProviderBadResponseError,
    ProviderError,
    ProviderNetworkError,
    ProviderQuotaError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    wrap_provider_error,
)


def _timeout_tuple(scalar: int, connect: int = 5) -> tuple:
    """Convert a scalar timeout to (connect_timeout, read_timeout) tuple."""
    return (connect, max(scalar - connect, connect))


ALLOWED_EMOTIONS = {
    "calm",
    "tired",
    "happy",
    "sad",
    "angry",
    "anxious",
    "uncertain",
}


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


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.S)
    if fenced:
        return fenced.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        return stripped[start : end + 1]
    return stripped


def parse_audio_understanding(raw: Union[str, Dict[str, Any]]) -> AudioUnderstanding:
    if isinstance(raw, str):
        try:
            data = json.loads(_extract_json_text(raw))
        except (TypeError, ValueError):
            return FALLBACK_AUDIO_UNDERSTANDING
    elif isinstance(raw, dict):
        data = dict(raw)
    else:
        return FALLBACK_AUDIO_UNDERSTANDING

    emotion = str(data.get("detected_emotion") or "uncertain").strip()
    if emotion not in ALLOWED_EMOTIONS:
        emotion = "uncertain"

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return AudioUnderstanding(
        user_text=str(data.get("user_text") or "").strip(),
        detected_emotion=emotion,
        tone_notes=str(data.get("tone_notes") or "").strip(),
        non_verbal=str(data.get("non_verbal") or "").strip(),
        confidence=confidence,
    )


def _audio_format_from_content_type(content_type: str) -> str:
    if "wav" in content_type:
        return "wav"
    if "mpeg" in content_type or "mp3" in content_type:
        return "mp3"
    if "mp4" in content_type or "m4a" in content_type:
        return "mp4"
    return "webm"


def build_audio_prompt() -> str:
    return (
        "你正在帮助一个叫豆豆的手机桌宠理解用户的语音。"
        "请从音频中提取用户大概说了什么、当前情绪、语气特点、"
        "是否有叹气/笑声/沉默/环境噪音等非语言声音。"
        "只输出 JSON："
        '{"user_text":"...","detected_emotion":"calm/tired/happy/sad/angry/anxious/uncertain",'
        '"tone_notes":"...","non_verbal":"...","confidence":0.0}'
    )


def encode_audio_base64_chunked(audio_path: Path, chunk_size: int = 48 * 1024) -> str:
    """Base64 encode audio without reading the raw file into memory at once."""
    output = io.StringIO()
    carry = b""
    with audio_path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            data = carry + chunk
            safe_len = len(data) - (len(data) % 3)
            if safe_len:
                output.write(
                    binascii.b2a_base64(data[:safe_len], newline=False).decode("ascii")
                )
            carry = data[safe_len:]
    if carry:
        output.write(
            binascii.b2a_base64(carry, newline=False).decode("ascii")
        )
    return output.getvalue()


class MockAudioUnderstandingProvider:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def understand(self, audio_path: Path, content_type: str) -> AudioUnderstanding:
        if self.fail or not audio_path.exists():
            return FALLBACK_AUDIO_UNDERSTANDING
        return AudioUnderstanding(
            user_text="我回来啦",
            detected_emotion="happy",
            tone_notes="mock 语音听起来比较轻快",
            non_verbal="",
            confidence=0.9,
        )


class MiMoAudioUnderstandingProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider_config = settings.audio_understanding
        self.api_key = self.provider_config.api_key

    def _headers(self, api_key: str) -> Dict[str, str]:
        headers: Dict[str, str] = {"content-type": "application/json"}
        scheme = str(self.provider_config.extra.get("auth_scheme") or "api-key").lower()
        if scheme == "bearer":
            headers["Authorization"] = "Bearer %s" % api_key
            return headers
        if scheme == "custom":
            header = str(self.provider_config.extra.get("api_key_header") or "Authorization")
            prefix = str(self.provider_config.extra.get("api_key_prefix") or "")
            headers[header] = ("%s %s" % (prefix, api_key)).strip()
            return headers
        header = str(self.provider_config.extra.get("api_key_header") or "api-key")
        headers[header] = api_key
        return headers

    def understand(self, audio_path: Path, content_type: str) -> AudioUnderstanding:
        if not audio_path.exists():
            return FALLBACK_AUDIO_UNDERSTANDING
        if is_probably_empty_audio(audio_path, content_type):
            return FALLBACK_AUDIO_UNDERSTANDING
        if not self.api_key:
            raise ProviderAuthError(
                provider=self.provider_config.name,
                code="missing_api_key",
                message="%s is not configured" % self.provider_config.api_key_env,
            )
        if not self.provider_config.base_url:
            raise ProviderError(
                provider=self.provider_config.name,
                code="not_configured",
                message="audio understanding base_url is not configured",
            )

        start = perf_counter()
        try:
            audio_data = encode_audio_base64_chunked(audio_path)
            response = requests.post(
                self.provider_config.base_url.rstrip("/")
                + "/chat/completions",
                headers=self._headers(self.api_key),
                json={
                    "model": self.provider_config.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": build_audio_prompt()},
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": audio_data,
                                        "format": _audio_format_from_content_type(
                                            content_type
                                        ),
                                    },
                                },
                            ],
                        }
                    ],
                    "temperature": 0.2,
                },
                timeout=_timeout_tuple(self.provider_config.timeout_seconds),
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = parse_audio_understanding(content)
            if parsed == FALLBACK_AUDIO_UNDERSTANDING:
                raise ProviderBadResponseError(
                    provider=self.provider_config.name,
                    message="audio understanding response did not contain valid JSON",
                )
            return parsed
        except requests.Timeout as exc:
            latency_ms = int((perf_counter() - start) * 1000)
            raise ProviderTimeoutError(
                provider=self.provider_config.name,
                latency_ms=latency_ms,
                message=str(exc)[:200],
            ) from exc
        except requests.ConnectionError as exc:
            latency_ms = int((perf_counter() - start) * 1000)
            raise ProviderNetworkError(
                provider=self.provider_config.name,
                latency_ms=latency_ms,
                message=str(exc)[:200],
            ) from exc
        except requests.HTTPError as exc:
            latency_ms = int((perf_counter() - start) * 1000)
            resp = getattr(exc, "response", None)
            status = getattr(resp, "status_code", None)
            if status in (401, 403):
                raise ProviderAuthError(
                    provider=self.provider_config.name,
                    status=status,
                    latency_ms=latency_ms,
                    message=str(exc)[:200],
                ) from exc
            if status == 429:
                raise ProviderQuotaError(
                    provider=self.provider_config.name,
                    status=status,
                    latency_ms=latency_ms,
                    message=str(exc)[:200],
                ) from exc
            if status is not None and status >= 500:
                raise ProviderUnavailableError(
                    provider=self.provider_config.name,
                    status=status,
                    latency_ms=latency_ms,
                    message=str(exc)[:200],
                ) from exc
            raise wrap_provider_error(
                exc, provider=self.provider_config.name, latency_ms=latency_ms,
            ) from exc
        except (json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
            latency_ms = int((perf_counter() - start) * 1000)
            raise ProviderBadResponseError(
                provider=self.provider_config.name,
                latency_ms=latency_ms,
                message=str(exc)[:200],
            ) from exc


def is_probably_empty_audio(audio_path: Path, content_type: str) -> bool:
    if "wav" not in content_type and audio_path.suffix.lower() != ".wav":
        return audio_path.stat().st_size < 512
    try:
        with wave.open(str(audio_path), "rb") as handle:
            frame_count = handle.getnframes()
            sample_rate = handle.getframerate()
            sample_width = handle.getsampwidth()
            # Sample up to 16 windows of 4096 frames instead of reading all frames
            window_size = 4096
            max_windows = 16
            total_frames_to_read = min(frame_count, window_size * max_windows)
            frames = handle.readframes(total_frames_to_read)
    except Exception:
        return False

    if frame_count < max(1, int(sample_rate * 0.25)):
        return True
    if sample_width != 2:
        return False

    # Check sampled frames for amplitude
    max_amplitude = 0
    chunk_size = 2  # 16-bit samples = 2 bytes
    for index in range(0, len(frames) - 1, chunk_size * 64):  # Sample every 64th frame
        sample = int.from_bytes(frames[index : index + chunk_size], "little", signed=True)
        max_amplitude = max(max_amplitude, abs(sample))
        if max_amplitude > 96:
            return False
    return True
