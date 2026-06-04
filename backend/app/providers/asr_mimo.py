from __future__ import annotations

import base64
from pathlib import Path
from time import sleep
from typing import Any, Dict, Optional

import requests

from app.config import ProviderConfig
from app.runtime.voice_types import ASRTranscript

DIRECT_REQUEST_PROXIES = {"http": None, "https": None, "all": None}


def _timeout_tuple(scalar: int, connect: int = 4) -> tuple:
    return (connect, max(int(scalar or 1), connect))


def _base_content_type(value: str) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def _data_url_mime(content_type: str) -> str:
    content_type = _base_content_type(content_type)
    if content_type in {"audio/mpeg", "audio/mp3"}:
        return content_type
    if content_type == "audio/wav":
        return content_type
    return ""


def parse_mimo_asr_response(body: Dict[str, Any]) -> str:
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
            elif isinstance(item, str):
                stripped = item.strip()
                if stripped:
                    parts.append(stripped)
        return "".join(parts).strip()
    return ""


class MiMoASRProvider:
    """MiMo v2.5 ASR using OpenAI-compatible chat completions input_audio."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.name = config.name or "mimo_asr"

    def transcribe(self, audio_path: Path, content_type: str) -> ASRTranscript:
        if not audio_path.exists():
            return self._error("asr_audio_missing", "ASR input audio file is missing")
        if not self.config.api_key or not self.config.base_url:
            return self._error("asr_not_configured", "Mimo ASR is not configured")
        mime = _data_url_mime(content_type or audio_path.suffix)
        if not mime:
            return self._error(
                "asr_unsupported_audio",
                "Mimo ASR supports only wav and mp3 inputs",
            )

        attempts = self._max_attempts()
        last = self._error("asr_provider_error", "Mimo ASR provider failed")
        for attempt in range(attempts):
            last = self._transcribe_once(audio_path, mime)
            if not self._should_retry(last.error_code, attempt, attempts):
                return last
            sleep(self._retry_backoff_seconds(attempt))
        return last

    def _transcribe_once(self, audio_path: Path, mime: str) -> ASRTranscript:
        try:
            response = requests.post(
                self._url(),
                headers=self._headers(),
                json=self._payload(audio_path, mime),
                proxies=DIRECT_REQUEST_PROXIES,
                timeout=_timeout_tuple(self.config.timeout_seconds),
            )
            response.raise_for_status()
            text = parse_mimo_asr_response(response.json())
            if not text:
                return self._error("asr_empty", "Mimo ASR returned empty transcript")
            return ASRTranscript(text=text, confidence=1.0, provider=self.name)
        except requests.Timeout:
            return self._error("asr_timeout", "Mimo ASR request timed out")
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status:
                return self._error(
                    "asr_http_%s" % status,
                    "Mimo ASR request failed with status %s" % status,
                )
            return self._error("asr_http_error", "Mimo ASR request failed")
        except requests.RequestException:
            return self._error("asr_request_error", "Mimo ASR request failed")
        except ValueError:
            return self._error("asr_bad_response", "Mimo ASR response was not valid JSON")
        except Exception:
            return self._error("asr_provider_error", "Mimo ASR provider failed")

    def _payload(self, audio_path: Path, mime: str) -> Dict[str, Any]:
        encoded = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        payload: Dict[str, Any] = {
            "model": self.config.model or "mimo-v2.5-asr",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": "data:%s;base64,%s" % (mime, encoded)},
                        }
                    ],
                }
            ],
            "stream": False,
        }
        language = str(self.config.extra.get("language") or "auto").strip()
        if language:
            payload["asr_options"] = {"language": language}
        return payload

    def _url(self) -> str:
        endpoint = str(self.config.extra.get("endpoint") or "/chat/completions")
        return self.config.base_url.rstrip("/") + "/" + endpoint.lstrip("/")

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        scheme = str(self.config.extra.get("auth_scheme") or "api-key").lower()
        if scheme == "bearer":
            headers["Authorization"] = "Bearer %s" % self.config.api_key
        else:
            header = str(self.config.extra.get("api_key_header") or "api-key")
            headers[header] = str(self.config.api_key)
        return headers

    def _max_attempts(self) -> int:
        try:
            retries = int(self.config.extra.get("transient_retries", 0))
        except (TypeError, ValueError):
            retries = 0
        return max(1, min(3, retries + 1))

    def _retry_backoff_seconds(self, attempt: int) -> float:
        try:
            base = float(self.config.extra.get("retry_backoff_seconds", 0.25))
        except (TypeError, ValueError):
            base = 0.25
        return max(0.0, min(2.0, base * (attempt + 1)))

    def _should_retry(self, error_code: str, attempt: int, attempts: int) -> bool:
        if not error_code or attempt >= attempts - 1:
            return False
        if error_code in {"asr_request_error", "asr_provider_error", "asr_empty", "asr_timeout"}:
            return True
        if error_code.startswith("asr_http_"):
            try:
                status = int(error_code.rsplit("_", 1)[1])
            except (IndexError, ValueError):
                return False
            return 500 <= status <= 599
        return False

    def _error(self, code: str, message: str) -> ASRTranscript:
        return ASRTranscript(
            text="",
            confidence=0.0,
            provider=self.name,
            error_code=code,
            error_message=message,
        )


class FallbackASRProvider:
    def __init__(self, primary, fallback) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = "%s_with_%s_fallback" % (
            getattr(primary, "name", "primary"),
            getattr(fallback, "name", "fallback"),
        )
        self.last_primary_error_code = ""

    def transcribe(self, audio_path: Path, content_type: str) -> ASRTranscript:
        transcript = self.primary.transcribe(audio_path, content_type)
        if not self._should_fallback(transcript):
            self.last_primary_error_code = ""
            return transcript
        self.last_primary_error_code = transcript.error_code or "asr_empty"
        fallback_transcript = self.fallback.transcribe(audio_path, content_type)
        if fallback_transcript.text.strip() and not fallback_transcript.error_code:
            return fallback_transcript
        return transcript

    def _should_fallback(self, transcript: ASRTranscript) -> bool:
        code = transcript.error_code
        if not code and transcript.text.strip():
            return False
        if not code:
            return True
        if code in {
            "asr_empty",
            "asr_timeout",
            "asr_request_error",
            "asr_provider_error",
            "asr_bad_response",
        }:
            return True
        if code.startswith("asr_http_"):
            try:
                status = int(code.rsplit("_", 1)[1])
            except (IndexError, ValueError):
                return False
            return status >= 500
        return False
