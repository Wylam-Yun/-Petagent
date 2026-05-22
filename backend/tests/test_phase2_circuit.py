"""Tests for STAB-011: Provider circuit breaker."""
from __future__ import annotations

import time

from app.providers.circuit import ProviderCircuit


def test_circuit_starts_closed():
    c = ProviderCircuit("test")
    assert c.is_open is False


def test_circuit_opens_after_threshold():
    c = ProviderCircuit("test", threshold=3, window_seconds=60, cooldown_seconds=60)
    for _ in range(3):
        c.record_failure()
    assert c.is_open is True


def test_circuit_stays_closed_below_threshold():
    c = ProviderCircuit("test", threshold=5, window_seconds=60)
    for _ in range(4):
        c.record_failure()
    assert c.is_open is False


def test_circuit_closes_after_cooldown():
    c = ProviderCircuit("test", threshold=2, window_seconds=60, cooldown_seconds=0.1)
    c.record_failure()
    c.record_failure()
    assert c.is_open is True

    time.sleep(0.15)
    assert c.is_open is False


def test_circuit_closes_on_success():
    c = ProviderCircuit("test", threshold=2, window_seconds=60)
    c.record_failure()
    c.record_failure()
    assert c.is_open is True

    c.record_success()
    assert c.is_open is False


def test_circuit_reset():
    c = ProviderCircuit("test", threshold=1)
    c.record_failure()
    assert c.is_open is True

    c.reset()
    assert c.is_open is False


def test_circuit_window_expiry():
    c = ProviderCircuit("test", threshold=2, window_seconds=0.1)
    c.record_failure()
    time.sleep(0.15)
    # First failure expired from window, only 1 in window
    assert c.is_open is False
    c.record_failure()
    # Still only 1 in window (first expired)
    assert c.is_open is False


# --- Integration with FallbackLLMProvider ---


def test_fallback_llm_skips_primary_when_circuit_open():
    from unittest.mock import MagicMock

    from app.providers.circuit import ProviderCircuit
    from app.providers.errors import ProviderTimeoutError
    from app.providers.llm_mimo import FallbackLLMProvider, MockLLMProvider

    primary = MagicMock()
    primary.name = "primary"
    primary.complete_json.side_effect = ProviderTimeoutError(provider="primary")

    fallback = MockLLMProvider("fallback")
    circuit = ProviderCircuit("primary", threshold=1)
    provider = FallbackLLMProvider(primary, fallback, circuit=circuit)

    # First call: primary fails, circuit opens
    result = provider.complete_json([{"role": "user", "content": "hi"}])
    assert "reply" in result
    assert circuit.is_open is True

    # Second call: primary should be skipped (circuit open)
    primary.complete_json.reset_mock()
    result = provider.complete_json([{"role": "user", "content": "hi"}])
    assert "reply" in result
    primary.complete_json.assert_not_called()
