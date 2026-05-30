from __future__ import annotations

from time import sleep
from typing import Callable, TypeVar

from app.providers.errors import ProviderAuthError

T = TypeVar("T")


def is_retryable_provider_error(exc: Exception) -> bool:
    if isinstance(exc, ProviderAuthError):
        return False
    return True


def retry_provider_call(
    operation: Callable[[], T],
    *,
    provider: str,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.1,
) -> T:
    attempts = max(1, min(3, int(max_attempts)))
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            if not is_retryable_provider_error(exc) or attempt >= attempts - 1:
                raise
            delay = max(0.0, min(1.0, base_delay_seconds * (attempt + 1)))
            if delay:
                sleep(delay)
    raise last_exc  # type: ignore[misc]
