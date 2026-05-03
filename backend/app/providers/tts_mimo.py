from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import requests

from app.config import Settings


VOICE_PROMPT = (
    "你是 Momo，一只住在旧手机里的可爱表情包小宠物。"
    "声音要软、近、轻快、自然，像小宠物在开心回应主人。"
    "不要像客服，不要像播音员，不要过度甜腻。"
)


def build_tts_payload(
    *, voice_prompt: str, spoken_text: str, model: str, voice: str, audio_format: str
) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": voice_prompt},
            {"role": "assistant", "content": spoken_text},
        ],
        "audio": {"format": audio_format, "voice": voice},
    }


def extract_audio_bytes(response_json: Dict[str, Any]) -> bytes:
    audio_data = response_json["choices"][0]["message"]["audio"]["data"]
    return base64.b64decode(audio_data)


class MockTTSProvider:
    def __init__(self, audio_dir: Path, fail: bool = False) -> None:
        self.audio_dir = audio_dir
        self.fail = fail

    def synthesize(self, text: str, voice_style: str = "soft") -> Optional[str]:
        if self.fail:
            return None
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        filename = "mock-%s.wav" % uuid4().hex
        path = self.audio_dir / filename
        path.write_bytes(b"RIFF$\x00\x00\x00WAVEfmt " + text.encode("utf-8")[:32])
        return "/static/audio/" + filename


class MiMoTTSProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def synthesize(self, text: str, voice_style: str = "soft") -> Optional[str]:
        if not self.settings.api_key or not self.settings.tts.base_url:
            return None

        payload = build_tts_payload(
            voice_prompt=VOICE_PROMPT,
            spoken_text=text,
            model=self.settings.tts.model,
            voice=self.settings.tts.voice or "冰糖",
            audio_format=self.settings.tts.audio_format or "wav",
        )
        try:
            response = requests.post(
                self.settings.tts.base_url.rstrip("/") + "/chat/completions",
                headers={
                    "api-key": self.settings.api_key,
                    "content-type": "application/json",
                },
                json=payload,
                timeout=self.settings.tts.timeout_seconds,
            )
            response.raise_for_status()
            audio_bytes = extract_audio_bytes(response.json())
        except Exception:
            return None

        self.settings.audio_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        filename = "reply-%s-%s.%s" % (
            stamp,
            uuid4().hex[:8],
            self.settings.tts.audio_format or "wav",
        )
        path = self.settings.audio_dir / filename
        path.write_bytes(audio_bytes)
        return "/static/audio/" + filename
