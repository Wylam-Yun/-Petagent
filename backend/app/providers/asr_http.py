from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import requests

from app.config import ProviderConfig
from app.runtime.voice_types import ASRTranscript


def parse_transcript_json(body: Dict[str, Any]) -> Tuple[str, float]:
    for key in ("text", "transcript", "transcription"):
        text = str(body.get(key) or "").strip()
        if text:
            return text, _confidence(body.get("confidence", 1.0))

    for segment in body.get("segments", []) or []:
        text = str(segment.get("text") or "").strip()
        if text:
            return text, _confidence(segment.get("confidence", body.get("confidence", 1.0)))

    for result in body.get("results", []) or []:
        for alternative in result.get("alternatives", []) or []:
            text = str(
                alternative.get("transcript")
                or alternative.get("text")
                or alternative.get("transcription")
                or ""
            ).strip()
            if text:
                return text, _confidence(alternative.get("confidence", body.get("confidence", 1.0)))

    return "", 0.0


def _confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(1.0, value))


class HttpASRProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.name = config.name or "http_asr"

    def transcribe(self, audio_path: Path, content_type: str) -> ASRTranscript:
        if not audio_path.exists() or not self.config.base_url:
            return ASRTranscript(text="", confidence=0.0, provider=self.name)

        try:
            with audio_path.open("rb") as handle:
                response = requests.post(
                    self._url(),
                    headers=self._headers(),
                    data=self._data(),
                    files={
                        "file": (
                            audio_path.name,
                            handle,
                            content_type or "application/octet-stream",
                        )
                    },
                    proxies=self._proxies(),
                    timeout=self.config.timeout_seconds,
                )
            response.raise_for_status()
            text, confidence = parse_transcript_json(response.json())
            return ASRTranscript(text=text, confidence=confidence, provider=self.name)
        except Exception:
            return ASRTranscript(text="", confidence=0.0, provider=self.name)

    def _url(self) -> str:
        endpoint = str(self.config.extra.get("endpoint") or "/v1/audio/transcriptions")
        return self.config.base_url.rstrip("/") + "/" + endpoint.lstrip("/")

    def _headers(self) -> Dict[str, str]:
        if not self.config.api_key:
            return {}
        scheme = str(self.config.extra.get("auth_scheme") or "bearer").lower()
        if scheme == "api-key":
            return {"api-key": self.config.api_key}
        return {"Authorization": "Bearer %s" % self.config.api_key}

    def _data(self) -> Dict[str, str]:
        data = {
            "model": self.config.model,
            "language": str(self.config.extra.get("language_code") or "zh-CN"),
        }
        for key in ("response_format", "temperature", "prompt"):
            value = self.config.extra.get(key)
            if value is not None and value != "":
                data[key] = str(value)
        return data

    def _proxies(self) -> Dict[str, str]:
        proxy_url = str(self.config.extra.get("proxy_url") or "").strip()
        if not proxy_url:
            return {}
        return {"http": proxy_url, "https": proxy_url}
