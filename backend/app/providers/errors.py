from __future__ import annotations


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
