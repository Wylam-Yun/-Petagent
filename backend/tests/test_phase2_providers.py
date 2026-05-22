"""Tests for STAB-019/012/011: Provider errors, timeouts, circuit breaker."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.config import ProviderConfig
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


class _DummySettings:
    """Minimal settings for provider tests."""
    api_key = ""
    llm = ProviderConfig(name="test_llm", model="test", base_url="", api_key_env="LLM_API_KEY", timeout_seconds=5)
    tts = ProviderConfig(name="test_tts", model="test", base_url="", api_key_env="TTS_API_KEY", timeout_seconds=5)

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k == "llm" and isinstance(v, str):
                self.llm = ProviderConfig(name="test_llm", model="test", api_key=v, base_url="http://test.local/v1", api_key_env="LLM_API_KEY", timeout_seconds=5)
            elif k == "tts" and isinstance(v, str):
                self.tts = ProviderConfig(name="test_tts", model="test", api_key=v, base_url="http://test.local/v1", api_key_env="TTS_API_KEY", timeout_seconds=5)
            else:
                setattr(self, k, v)


# --- wrap_provider_error tests ---


def test_wrap_timeout():
    exc = requests.Timeout("read timed out")
    result = wrap_provider_error(exc, provider="test")
    assert isinstance(result, ProviderTimeoutError)
    assert result.provider == "test"


def test_wrap_connection_error():
    exc = requests.ConnectionError("Connection refused")
    result = wrap_provider_error(exc, provider="test")
    assert isinstance(result, ProviderNetworkError)


def test_wrap_http_401():
    resp = MagicMock()
    resp.status_code = 401
    exc = requests.HTTPError(response=resp)
    result = wrap_provider_error(exc, provider="test")
    assert isinstance(result, ProviderAuthError)
    assert result.status == 401


def test_wrap_http_429():
    resp = MagicMock()
    resp.status_code = 429
    exc = requests.HTTPError(response=resp)
    result = wrap_provider_error(exc, provider="test")
    assert isinstance(result, ProviderQuotaError)


def test_wrap_http_500():
    resp = MagicMock()
    resp.status_code = 500
    exc = requests.HTTPError(response=resp)
    result = wrap_provider_error(exc, provider="test")
    assert isinstance(result, ProviderUnavailableError)


def test_wrap_json_decode_error():
    exc = json.JSONDecodeError("Expecting value", "", 0)
    result = wrap_provider_error(exc, provider="test")
    assert isinstance(result, ProviderBadResponseError)


def test_wrap_key_error():
    exc = KeyError("missing_key")
    result = wrap_provider_error(exc, provider="test")
    assert isinstance(result, ProviderBadResponseError)


def test_wrap_already_provider_error():
    original = ProviderTimeoutError(provider="test")
    result = wrap_provider_error(original)
    assert result is original


def test_wrap_unknown_exception():
    exc = RuntimeError("something weird")
    result = wrap_provider_error(exc, provider="test")
    assert isinstance(result, ProviderError)
    assert result.provider == "test"


# --- LLM provider structured errors ---


def test_llm_provider_raises_auth_error_on_missing_key():
    from app.providers.llm_mimo import MiMoLLMProvider

    settings = _DummySettings(api_key="")
    provider = MiMoLLMProvider(settings)
    with pytest.raises(ProviderAuthError):
        provider.complete_json([{"role": "user", "content": "hi"}])


def test_llm_provider_raises_timeout_on_request_timeout():
    from app.providers.llm_mimo import MiMoLLMProvider

    settings = _DummySettings(llm="test-key")
    provider = MiMoLLMProvider(settings)

    with patch("app.providers.llm_mimo.requests.post") as mock_post:
        mock_post.side_effect = requests.Timeout("read timed out")
        with pytest.raises(ProviderTimeoutError) as exc_info:
            provider.complete_json([{"role": "user", "content": "hi"}])
        assert exc_info.value.provider == provider.name


def test_llm_provider_raises_auth_on_401():
    from app.providers.llm_mimo import MiMoLLMProvider

    settings = _DummySettings(llm="bad-key")
    provider = MiMoLLMProvider(settings)

    resp = MagicMock()
    resp.status_code = 401
    resp.raise_for_status.side_effect = requests.HTTPError(response=resp)

    with patch("app.providers.llm_mimo.requests.post") as mock_post:
        mock_post.return_value = resp
        with pytest.raises(ProviderAuthError):
            provider.complete_json([{"role": "user", "content": "hi"}])


def test_fallback_llm_records_primary_error():
    from app.providers.llm_mimo import FallbackLLMProvider, MockLLMProvider

    primary = MagicMock()
    primary.name = "primary"
    primary.complete_json.side_effect = ProviderTimeoutError(provider="primary")

    fallback = MockLLMProvider("fallback")
    provider = FallbackLLMProvider(primary, fallback)

    result = provider.complete_json([{"role": "user", "content": "hi"}])
    assert "reply" in result
    assert isinstance(provider.last_primary_error, ProviderTimeoutError)


def test_fallback_llm_clears_error_on_success():
    from app.providers.llm_mimo import FallbackLLMProvider, MockLLMProvider

    primary = MockLLMProvider("primary")
    fallback = MockLLMProvider("fallback")
    provider = FallbackLLMProvider(primary, fallback)
    provider.last_primary_error = ProviderTimeoutError(provider="stale")

    result = provider.complete_json([{"role": "user", "content": "hi"}])
    assert "reply" in result
    assert provider.last_primary_error is None


# --- TTS provider structured errors ---


def test_tts_provider_raises_auth_on_missing_key():
    from app.providers.tts_mimo import MiMoTTSProvider

    settings = _DummySettings(api_key="", tts=ProviderConfig(name="tts", model="test", api_key="", base_url="", api_key_env="TTS_API_KEY", timeout_seconds=5))
    provider = MiMoTTSProvider(settings)
    with pytest.raises(ProviderAuthError):
        provider.synthesize("hello")


def test_tts_provider_raises_timeout():
    from app.providers.tts_mimo import MiMoTTSProvider

    settings = _DummySettings(tts="test-key")
    provider = MiMoTTSProvider(settings)

    with patch("app.providers.tts_mimo.requests.post") as mock_post:
        mock_post.side_effect = requests.Timeout("read timed out")
        with pytest.raises(ProviderTimeoutError):
            provider.synthesize("hello")


def test_fallback_tts_records_primary_error():
    from app.providers.tts_mimo import FallbackTTSProvider

    primary = MagicMock()
    primary.name = "primary"
    primary.synthesize.side_effect = ProviderTimeoutError(provider="primary")

    fallback = MagicMock()
    fallback.synthesize.return_value = "/static/audio/fallback.wav"

    provider = FallbackTTSProvider(primary, fallback)
    result = provider.synthesize("hello")
    assert result == "/static/audio/fallback.wav"
    assert isinstance(provider.last_primary_error, ProviderTimeoutError)


def test_fallback_tts_clears_error_on_success():
    from app.providers.tts_mimo import FallbackTTSProvider

    primary = MagicMock()
    primary.synthesize.return_value = "/static/audio/primary.wav"

    fallback = MagicMock()
    provider = FallbackTTSProvider(primary, fallback)
    provider.last_primary_error = ProviderTimeoutError(provider="stale")

    result = provider.synthesize("hello")
    assert result == "/static/audio/primary.wav"
    assert provider.last_primary_error is None
