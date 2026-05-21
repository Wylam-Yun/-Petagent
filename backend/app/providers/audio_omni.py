from __future__ import annotations

import base64
import json
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Union

import requests

from app.config import Settings


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
        "你正在帮助一个叫 Momo 的手机桌宠理解用户的语音。"
        "请从音频中提取用户大概说了什么、当前情绪、语气特点、"
        "是否有叹气/笑声/沉默/环境噪音等非语言声音。"
        "只输出 JSON："
        '{"user_text":"...","detected_emotion":"calm/tired/happy/sad/angry/anxious/uncertain",'
        '"tone_notes":"...","non_verbal":"...","confidence":0.0}'
    )


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
        self.api_key = self.provider_config.api_key or settings.api_key

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
        if not self.api_key or not self.provider_config.base_url:
            return FALLBACK_AUDIO_UNDERSTANDING

        try:
            audio_data = base64.b64encode(audio_path.read_bytes()).decode("ascii")
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
                timeout=self.provider_config.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            return parse_audio_understanding(content)
        except Exception:
            return FALLBACK_AUDIO_UNDERSTANDING


def is_probably_empty_audio(audio_path: Path, content_type: str) -> bool:
    if "wav" not in content_type and audio_path.suffix.lower() != ".wav":
        return audio_path.stat().st_size < 512
    try:
        with wave.open(str(audio_path), "rb") as handle:
            frame_count = handle.getnframes()
            sample_rate = handle.getframerate()
            sample_width = handle.getsampwidth()
            frames = handle.readframes(frame_count)
    except Exception:
        return False

    if frame_count < max(1, int(sample_rate * 0.25)):
        return True
    if sample_width != 2:
        return False
    max_amplitude = 0
    for index in range(0, len(frames) - 1, 2):
        sample = int.from_bytes(frames[index : index + 2], "little", signed=True)
        max_amplitude = max(max_amplitude, abs(sample))
        if max_amplitude > 96:
            return False
    return True
