from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any, Dict, List, Optional, Protocol

import requests

from app.config import ProviderConfig, Settings
from app.providers.circuit import ProviderCircuit
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
from app.providers.retry import retry_provider_call


def _timeout_tuple(scalar: int, connect: int = 5) -> tuple:
    """Convert a scalar timeout to (connect_timeout, read_timeout) tuple."""
    return (connect, max(scalar - connect, connect))


class LLMProvider(Protocol):
    def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        ...


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


class MockLLMProvider:
    def __init__(self, name: str = "mock_llm") -> None:
        self.name = name

    def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        return {
            "reply": "嘿嘿，豆豆在呢。",
            "mood": "happy",
            "face_type": "happy",
            "animation": "bounce",
            "voice_style": "happy",
            "vibration": "light",
            "intent": "affection_response",
            "autonomy_notes": "mock provider response",
            "state_delta": {
                "energy": 0,
                "intimacy": 0,
                "hunger": 0,
                "loneliness": -1,
                "sleepiness": 0,
            },
            "memory_update": {"should_save": False, "content": ""},
        }


class FallbackLLMProvider:
    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
        circuit: Optional[ProviderCircuit] = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = "%s_with_%s_fallback" % (
            getattr(primary, "name", "primary"),
            getattr(fallback, "name", "fallback"),
        )
        self.last_primary_error: Optional[ProviderError] = None
        self._circuit = circuit

    def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        # Skip primary if circuit is open
        if self._circuit is not None and self._circuit.is_open:
            return self.fallback.complete_json(messages)

        try:
            result = self.primary.complete_json(messages)
            self.last_primary_error = None
            if self._circuit is not None:
                self._circuit.record_success()
            return result
        except ProviderError as exc:
            self.last_primary_error = exc
            if self._circuit is not None:
                self._circuit.record_failure()
            return self.fallback.complete_json(messages)
        except Exception as exc:
            self.last_primary_error = wrap_provider_error(
                exc, provider=getattr(self.primary, "name", "primary"),
            )
            if self._circuit is not None:
                self._circuit.record_failure()
            return self.fallback.complete_json(messages)


class MiMoLLMProvider:
    def __init__(
        self, settings: Settings, provider_config: ProviderConfig = None
    ) -> None:
        self.settings = settings
        self.provider_config = provider_config or settings.llm
        self.name = self.provider_config.name

    def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        api_key = self.provider_config.api_key or self.settings.api_key
        if not api_key:
            raise ProviderAuthError(
                provider=self.name,
                message="%s is not configured" % self.provider_config.api_key_env,
            )
        if not self.provider_config.base_url:
            raise ProviderError(
                provider=self.name,
                code="not_configured",
                message="MIMO_BASE_URL is not configured",
            )

        payload = {
            "model": self.provider_config.model,
            "messages": messages,
            "temperature": self.provider_config.extra.get("temperature", 0.8),
        }
        for key in (
            "chat_template_kwargs",
            "max_tokens",
            "top_p",
            "response_format",
        ):
            if key in self.provider_config.extra:
                payload[key] = self.provider_config.extra[key]

        def operation() -> Dict[str, Any]:
            response = requests.post(
                self.provider_config.base_url.rstrip("/") + "/chat/completions",
                headers=self._headers(api_key),
                json=payload,
                proxies=self._proxies(),
                timeout=_timeout_tuple(self.provider_config.timeout_seconds),
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, dict):
                return content
            return json.loads(_extract_json_text(str(content)))

        def wrapped_operation() -> Dict[str, Any]:
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
                raise ProviderNetworkError(
                    provider=self.name, latency_ms=latency_ms, message=str(exc)[:200],
                ) from exc
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
            except (json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
                latency_ms = int((perf_counter() - start) * 1000)
                raise ProviderBadResponseError(
                    provider=self.name, latency_ms=latency_ms, message=str(exc)[:200],
                ) from exc

        return retry_provider_call(wrapped_operation, provider=self.name)

    def _headers(self, api_key: str) -> Dict[str, str]:
        headers = {"content-type": "application/json"}
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

    def _proxies(self) -> Dict[str, str]:
        proxy_url = str(self.provider_config.extra.get("proxy_url") or "").strip()
        if not proxy_url:
            return {}
        return {"http": proxy_url, "https": proxy_url}
