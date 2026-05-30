import pytest

from app.providers.errors import ProviderAuthError, ProviderTimeoutError
from app.providers.retry import retry_provider_call


def test_provider_retry_succeeds_within_three_attempts():
    attempts = {"count": 0}

    def op():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ProviderTimeoutError(provider="x")
        return "ok"

    assert retry_provider_call(op, provider="x", base_delay_seconds=0) == "ok"
    assert attempts["count"] == 3


def test_provider_retry_does_not_retry_auth_error():
    attempts = {"count": 0}

    def op():
        attempts["count"] += 1
        raise ProviderAuthError(provider="x", message="bad key")

    with pytest.raises(ProviderAuthError):
        retry_provider_call(op, provider="x", base_delay_seconds=0)
    assert attempts["count"] == 1
