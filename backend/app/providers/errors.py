from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Base class for structured provider failures."""

    error_class = "provider_error"

    def __init__(
        self,
        *,
        provider: str = "",
        code: str = "",
        status: int | None = None,
        latency_ms: int | None = None,
        message: str = "",
    ) -> None:
        self.provider = provider
        self.code = code
        self.status = status
        self.latency_ms = latency_ms
        self.message = message
        super().__init__(message or self.error_class)

    def to_dict(self) -> dict:
        return {
            "error_class": self.error_class,
            "provider": self.provider,
            "code": self.code,
            "status": self.status,
            "latency_ms": self.latency_ms,
        }


class ProviderAuthError(ProviderError):
    """401/403 from provider."""

    error_class = "provider_auth_failed"


class ProviderTimeoutError(ProviderError):
    """Connect or read timeout."""

    error_class = "provider_timeout"


class ProviderUnavailableError(ProviderError):
    """5xx from provider."""

    error_class = "provider_unavailable"


class ProviderQuotaError(ProviderError):
    """429 or quota exceeded."""

    error_class = "provider_quota"


class ProviderBadResponseError(ProviderError):
    """Malformed JSON or schema mismatch."""

    error_class = "provider_bad_response"


class ProviderNetworkError(ProviderError):
    """DNS failure, connection refused, etc."""

    error_class = "provider_network_error"


def wrap_provider_error(
    exc: Exception,
    *,
    provider: str = "",
    latency_ms: int | None = None,
) -> ProviderError:
    """Wrap a requests/JSON exception into a structured ProviderError.

    Call at provider boundaries so callers never see raw requests exceptions.
    """
    if isinstance(exc, ProviderError):
        return exc

    if isinstance(exc, requests.Timeout):
        return ProviderTimeoutError(
            provider=provider, latency_ms=latency_ms, message=str(exc)[:200],
        )

    if isinstance(exc, requests.ConnectionError):
        return ProviderNetworkError(
            provider=provider, latency_ms=latency_ms, message=str(exc)[:200],
        )

    if isinstance(exc, requests.HTTPError):
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
        if status in (401, 403):
            return ProviderAuthError(
                provider=provider, status=status, latency_ms=latency_ms,
                message=str(exc)[:200],
            )
        if status == 429:
            return ProviderQuotaError(
                provider=provider, status=status, latency_ms=latency_ms,
                message=str(exc)[:200],
            )
        if status is not None and status >= 500:
            return ProviderUnavailableError(
                provider=provider, status=status, latency_ms=latency_ms,
                message=str(exc)[:200],
            )
        return ProviderBadResponseError(
            provider=provider, status=status, latency_ms=latency_ms,
            message=str(exc)[:200],
        )

    if isinstance(exc, (json.JSONDecodeError, KeyError, IndexError, ValueError)):
        return ProviderBadResponseError(
            provider=provider, latency_ms=latency_ms, message=str(exc)[:200],
        )

    # Unknown exception — wrap as generic provider error
    return ProviderError(
        provider=provider, latency_ms=latency_ms, message=str(exc)[:200],
    )


# Avoid circular import — json is needed for JSONDecodeError
import json  # noqa: E402
