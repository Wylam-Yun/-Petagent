from __future__ import annotations

import base64
import json as _json
import threading
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional
from uuid import uuid4

import requests

from app.config import Settings
from app.providers.errors import (
    ProviderAuthError,
    ProviderBadResponseError,
    ProviderError,
    ProviderQuotaError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    wrap_provider_error,
)
from app.providers.retry import retry_provider_call

DIRECT_REQUEST_PROXIES = {"http": None, "https": None, "all": None}


def _timeout_tuple(scalar: int, connect: int = 5) -> tuple:
    """Convert a scalar timeout to (connect_timeout, read_timeout) tuple."""
    return (connect, max(scalar - connect, connect))


VOICE_PROMPT = (
    "你是豆豆，一只住在旧手机里的可爱精灵小猫。"
    "声音要软、近、轻快、自然，像小宠物在开心回应主人。"
    "不要像客服，不要像播音员，不要过度甜腻。"
)

SPEED_PROMPTS = {
    "slightly_slow": "语速稍慢一点，像温柔贴近地说话。",
    "normal": "语速自然。",
    "slightly_fast": "语速稍快一点，节奏轻快但吐字清楚。",
}

EMOTION_PROMPTS = {
    "warm": "整体情绪温暖。",
    "happy": "整体情绪开心。",
    "calm": "整体情绪平静。",
}

VOICE_STYLE_PROMPTS = {
    "happy": "这句可以更开心一点。",
    "sleepy": "这句可以更困倦、更轻一点。",
    "shy": "这句可以更害羞、更软一点。",
    "soft": "这句保持柔软亲近。",
    "normal": "这句保持自然。",
}


def build_voice_prompt(style: Dict[str, Any], voice_style: str = "soft") -> str:
    parts = [VOICE_PROMPT]
    speed = str((style or {}).get("speed") or "normal")
    emotion = str((style or {}).get("emotion") or "")
    if speed in SPEED_PROMPTS:
        parts.append(SPEED_PROMPTS[speed])
    if emotion in EMOTION_PROMPTS:
        parts.append(EMOTION_PROMPTS[emotion])
    if voice_style in VOICE_STYLE_PROMPTS:
        parts.append(VOICE_STYLE_PROMPTS[voice_style])
    return "".join(parts)


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

    def status(self) -> Dict[str, Any]:
        return {
            "configured": True,
            "model": "mock",
            "voice": "mock",
            "format": "wav",
        }


class FallbackTTSProvider:
    def __init__(self, primary, fallback, circuit=None) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = "fallback_tts"
        self.last_primary_error: Optional[ProviderError] = None
        self._circuit = circuit

    def synthesize(self, text: str, voice_style: str = "soft") -> Optional[str]:
        # Skip primary if circuit is open
        if self._circuit is not None and self._circuit.is_open:
            return self.fallback.synthesize(text, voice_style)

        try:
            voice_url = self.primary.synthesize(text, voice_style)
            if voice_url:
                self.last_primary_error = None
                if self._circuit is not None:
                    self._circuit.record_success()
                return voice_url
        except ProviderError as exc:
            self.last_primary_error = exc
            if self._circuit is not None:
                self._circuit.record_failure()
        except Exception as exc:
            self.last_primary_error = wrap_provider_error(
                exc, provider=getattr(self.primary, "name", "primary"),
            )
            if self._circuit is not None:
                self._circuit.record_failure()
        return self.fallback.synthesize(text, voice_style)


class SelectableTTSProvider:
    """Runtime-switchable TTS provider with automatic secondary fallback."""

    VALID_MODES = ("siliconflow", "mimo", "weilin")
    MODE_LABELS = {
        "siliconflow": "硅基 Claire",
        "mimo": "小米冰糖",
        "weilin": "Weilin",
    }

    def __init__(self, providers: Dict[str, Any], mode: str = "siliconflow") -> None:
        self.providers = {
            key: value
            for key, value in providers.items()
            if key in self.VALID_MODES and value is not None
        }
        self.name = "selectable_tts"
        self.last_primary_error: Optional[ProviderError] = None
        self._lock = threading.RLock()
        self._mode = self._normalize_mode(mode)

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    def set_mode(self, mode: str) -> str:
        next_mode = self._normalize_mode(mode)
        with self._lock:
            if next_mode not in self.providers:
                raise ValueError("TTS mode is not configured: %s" % next_mode)
            self._mode = next_mode
            return self._mode

    def available_modes(self) -> list[str]:
        return [mode for mode in self.VALID_MODES if mode in self.providers]

    def active_provider_name(self) -> str:
        provider = self.providers.get(self.mode)
        return str(getattr(provider, "name", self.mode))

    def status(self) -> Dict[str, Any]:
        mode = self.mode
        active = self.providers.get(mode)
        options = []
        for candidate_mode in self.VALID_MODES:
            provider = self.providers.get(candidate_mode)
            if provider is None:
                continue
            provider_status = (
                provider.status() if hasattr(provider, "status") else {"configured": True}
            )
            options.append(
                {
                    "mode": candidate_mode,
                    "label": self.MODE_LABELS.get(candidate_mode, candidate_mode),
                    "configured": bool(provider_status.get("configured", True)),
                    "model": provider_status.get("model", ""),
                    "voice": provider_status.get("voice", ""),
                    "format": provider_status.get("format", ""),
                }
            )
        return {
            "ok": True,
            "mode": mode,
            "active_provider": self.active_provider_name(),
            "options": options,
            "last_primary_error": (
                self.last_primary_error.error_class
                if self.last_primary_error is not None
                else None
            ),
            "configured": bool(active is not None),
        }

    def synthesize(self, text: str, voice_style: str = "soft") -> Optional[str]:
        with self._lock:
            mode = self._mode
            providers = dict(self.providers)
        order = [mode] + [candidate for candidate in self.VALID_MODES if candidate != mode]
        last_error: Optional[ProviderError] = None
        for candidate_mode in order:
            provider = providers.get(candidate_mode)
            if provider is None:
                continue
            try:
                voice_url = provider.synthesize(text, voice_style)
                if voice_url:
                    if candidate_mode == mode:
                        self.last_primary_error = None
                    return voice_url
            except ProviderError as exc:
                last_error = exc
                if candidate_mode == mode:
                    self.last_primary_error = exc
            except Exception as exc:
                last_error = wrap_provider_error(
                    exc, provider=getattr(provider, "name", candidate_mode),
                )
                if candidate_mode == mode:
                    self.last_primary_error = last_error
        if last_error is not None:
            raise last_error
        return None

    def _normalize_mode(self, mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in self.VALID_MODES:
            normalized = "siliconflow"
        if normalized in self.providers:
            return normalized
        if self.providers:
            return next(iter(self.providers))
        raise ValueError("No TTS providers configured")


class MiMoTTSProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.name = settings.tts.name or "mimo_tts"

    def status(self) -> Dict[str, Any]:
        voice = self.settings.tts.voice or ""
        voice_is_file = bool(self.settings.tts.extra.get("voice_is_file"))
        sample_path = self._voice_sample_path() if voice_is_file else None
        return {
            "configured": bool(
                (self.settings.tts.api_key or self.settings.api_key)
                and self.settings.tts.base_url
                and (not voice_is_file or (sample_path is not None and sample_path.exists()))
            ),
            "model": self.settings.tts.model,
            "voice": sample_path.name if sample_path is not None else voice,
            "format": self.settings.tts.audio_format or "",
        }

    def synthesize(self, text: str, voice_style: str = "soft") -> Optional[str]:
        api_key = self.settings.tts.api_key or self.settings.api_key
        if not api_key or not self.settings.tts.base_url:
            raise ProviderAuthError(
                provider=self.name,
                message="TTS API key or base URL not configured",
            )
        if str(self.settings.tts.extra.get("api_style") or "").lower() == "openai_speech":
            return self._synthesize_openai_speech(text, voice_style, api_key)

        payload = build_tts_payload(
            voice_prompt=build_voice_prompt(self.settings.tts.style or {}, voice_style),
            spoken_text=text,
            model=self.settings.tts.model,
            voice=self._voice_value(),
            audio_format=self.settings.tts.audio_format or "wav",
        )
        def operation() -> bytes:
            response = requests.post(
                self.settings.tts.base_url.rstrip("/") + "/chat/completions",
                headers=self._headers(api_key),
                json=payload,
                proxies=DIRECT_REQUEST_PROXIES,
                timeout=_timeout_tuple(self.settings.tts.timeout_seconds),
            )
            response.raise_for_status()
            return extract_audio_bytes(response.json())

        def wrapped_operation() -> bytes:
            start = perf_counter()
            try:
                return operation()
            except requests.Timeout as exc:
                latency_ms = int((perf_counter() - start) * 1000)
                raise ProviderTimeoutError(
                    provider=self.name, latency_ms=latency_ms, message=str(exc)[:200],
                ) from exc
            except requests.ConnectionError as exc:
                latency_ms = int((perf_counter() - start) * 1000)
                raise wrap_provider_error(exc, provider=self.name, latency_ms=latency_ms) from exc
            except requests.HTTPError as exc:
                latency_ms = int((perf_counter() - start) * 1000)
                resp = getattr(exc, "response", None)
                status = getattr(resp, "status_code", None)
                if status in (401, 403):
                    raise ProviderAuthError(
                        provider=self.name, status=status, latency_ms=latency_ms,
                        message=str(exc)[:200],
                    ) from exc
                if status == 429:
                    raise ProviderQuotaError(
                        provider=self.name, status=status, latency_ms=latency_ms,
                        message=str(exc)[:200],
                    ) from exc
                if status is not None and status >= 500:
                    raise ProviderUnavailableError(
                        provider=self.name, status=status, latency_ms=latency_ms,
                        message=str(exc)[:200],
                    ) from exc
                raise wrap_provider_error(exc, provider=self.name, latency_ms=latency_ms) from exc
            except (_json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
                latency_ms = int((perf_counter() - start) * 1000)
                raise ProviderBadResponseError(
                    provider=self.name, latency_ms=latency_ms, message=str(exc)[:200],
                ) from exc

        audio_bytes = retry_provider_call(wrapped_operation, provider=self.name)
        return self._write_audio(audio_bytes)

    def _synthesize_openai_speech(
        self, text: str, voice_style: str, api_key: str
    ) -> Optional[str]:
        endpoint = str(self.settings.tts.extra.get("endpoint") or "/audio/speech")
        payload = {
            "model": self.settings.tts.model,
            "input": self._speech_input(text, voice_style),
            "voice": self.settings.tts.voice,
            "response_format": self.settings.tts.audio_format or "mp3",
        }
        speed = self.settings.tts.extra.get("speed")
        if speed is not None:
            payload["speed"] = speed
        def operation() -> bytes:
            response = requests.post(
                self.settings.tts.base_url.rstrip("/") + "/" + endpoint.lstrip("/"),
                headers=self._headers(api_key),
                json=payload,
                proxies=DIRECT_REQUEST_PROXIES,
                timeout=_timeout_tuple(self.settings.tts.timeout_seconds),
            )
            response.raise_for_status()
            return response.content

        def wrapped_operation() -> bytes:
            start = perf_counter()
            try:
                return operation()
            except requests.Timeout as exc:
                latency_ms = int((perf_counter() - start) * 1000)
                raise ProviderTimeoutError(
                    provider=self.name, latency_ms=latency_ms, message=str(exc)[:200],
                ) from exc
            except requests.ConnectionError as exc:
                latency_ms = int((perf_counter() - start) * 1000)
                raise wrap_provider_error(exc, provider=self.name, latency_ms=latency_ms) from exc
            except requests.HTTPError as exc:
                latency_ms = int((perf_counter() - start) * 1000)
                raise wrap_provider_error(exc, provider=self.name, latency_ms=latency_ms) from exc
        audio_bytes = retry_provider_call(wrapped_operation, provider=self.name)
        return self._write_audio(audio_bytes)

    def _speech_input(self, text: str, voice_style: str) -> str:
        if not bool(self.settings.tts.extra.get("include_voice_prompt", True)):
            return text
        prompt = build_voice_prompt(self.settings.tts.style or {}, voice_style)
        return "%s<|endofprompt|>%s" % (prompt, text)

    def _voice_sample_path(self) -> Optional[Path]:
        raw = str(self.settings.tts.voice or "").strip()
        if not raw:
            return None
        path = Path(raw)
        if path.is_absolute():
            return path
        root = getattr(self.settings, "project_root", None)
        if root is not None:
            return Path(root) / path
        return path

    def _voice_value(self) -> str:
        if not bool(self.settings.tts.extra.get("voice_is_file")):
            return self.settings.tts.voice or "冰糖"

        path = self._voice_sample_path()
        if path is None or not path.exists():
            raise ProviderAuthError(
                provider=self.name,
                message="TTS voice clone sample is not configured",
            )
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            mime = "audio/mp3"
        elif suffix == ".wav":
            mime = "audio/wav"
        else:
            raise ProviderBadResponseError(
                provider=self.name,
                message="TTS voice clone sample must be mp3 or wav",
            )
        return "%s;base64,%s" % (
            "data:%s" % mime,
            base64.b64encode(path.read_bytes()).decode("ascii"),
        )

    def _headers(self, api_key: str) -> Dict[str, str]:
        headers = {"content-type": "application/json"}
        scheme = str(self.settings.tts.extra.get("auth_scheme") or "api-key").lower()
        if scheme == "bearer":
            headers["Authorization"] = "Bearer %s" % api_key
            return headers
        if scheme == "custom":
            header = str(self.settings.tts.extra.get("api_key_header") or "Authorization")
            prefix = str(self.settings.tts.extra.get("api_key_prefix") or "")
            headers[header] = ("%s %s" % (prefix, api_key)).strip()
            return headers
        header = str(self.settings.tts.extra.get("api_key_header") or "api-key")
        headers[header] = api_key
        return headers

    def _write_audio(self, audio_bytes: bytes) -> Optional[str]:
        if not audio_bytes:
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
