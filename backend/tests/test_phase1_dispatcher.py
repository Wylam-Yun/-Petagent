"""Tests for STAB-005+010: Dispatcher split + ProviderGate."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

from app.pet.state import PetStateStore
from app.runtime.concurrency import ProviderBusyError, ProviderGate


# --- CAS tests ---


def test_state_version_column_exists():
    """PetStateStore should have a version column."""
    store = PetStateStore(None, pet_name="Test")
    state = store.get_state()
    assert "version" in state
    assert state["version"] >= 0


def test_save_state_increments_version():
    """save_state should increment the version."""
    store = PetStateStore(None, pet_name="Test")
    state1 = store.get_state()
    v1 = state1["version"]

    state1["mood"] = "happy"
    state2 = store.save_state(state1)
    v2 = state2["version"]

    assert v2 == v1 + 1


def test_save_state_cas_success():
    """save_state_cas should succeed when version matches."""
    store = PetStateStore(None, pet_name="Test")
    state = store.get_state()
    expected_version = state["version"]

    state["mood"] = "excited"
    result = store.save_state_cas(state, expected_version)
    assert result is not None
    assert result["mood"] == "excited"
    assert result["version"] == expected_version + 1


def test_save_state_cas_failure():
    """save_state_cas should fail when version doesn't match."""
    store = PetStateStore(None, pet_name="Test")
    state = store.get_state()

    # Concurrent write changes version
    state["mood"] = "happy"
    store.save_state(state)

    # Now try CAS with old version
    state["mood"] = "sad"
    result = store.save_state_cas(state, state["version"] - 1)
    assert result is None  # CAS failed


def test_dispatcher_handle_event_concurrent():
    """Concurrent events should not lose state updates."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    # Send multiple events
    for _ in range(5):
        resp = client.post("/api/pet/event", json={"type": "pet_head", "source": "runtime"})
        assert resp.status_code == 200

    # State should be consistent
    state = app.state.state_store.get_state()
    assert "version" in state
    assert state["version"] >= 5


# --- ProviderGate tests ---


def test_provider_gate_acquire_release():
    """ProviderGate should track slots correctly."""
    gate = ProviderGate({"llm_fast": 2})
    gate.acquire("llm_fast")
    assert gate.get_usage()["llm_fast"]["current"] == 1
    assert gate.inflight_age_s("llm_fast") >= 0
    assert gate.inflight_age_s() >= 0
    gate.release("llm_fast")
    assert gate.get_usage()["llm_fast"]["current"] == 0
    assert gate.inflight_age_s("llm_fast") < 0
    assert gate.inflight_age_s() < 0


def test_provider_gate_raises_when_full():
    """ProviderGate should raise ProviderBusyError when at capacity."""
    gate = ProviderGate({"llm_fast": 1})
    gate.acquire("llm_fast")

    try:
        gate.acquire("llm_fast")
        assert False, "Should have raised"
    except ProviderBusyError:
        pass

    gate.release("llm_fast")


def test_provider_gate_failed_acquire_does_not_reset_active_age():
    """A rejected acquire must not release or hide the active provider slot."""
    gate = ProviderGate({"llm_fast": 1})
    gate.acquire("llm_fast")
    age_before = gate.inflight_age_s("llm_fast")

    try:
        gate.acquire("llm_fast")
        assert False, "Should have raised"
    except ProviderBusyError:
        pass

    usage = gate.get_usage()["llm_fast"]
    assert usage["current"] == 1
    assert gate.inflight_age_s("llm_fast") >= age_before
    gate.release("llm_fast")


def test_provider_gate_default_limits():
    """ProviderGate should have sensible defaults."""
    gate = ProviderGate()
    usage = gate.get_usage()
    assert "llm_fast" in usage
    assert "llm_slow" in usage
    assert "asr" in usage
    assert "tts" in usage
    assert "audio_understanding" in usage


def test_provider_gate_unknown_type():
    """Unknown provider types should default to limit 1."""
    gate = ProviderGate()
    gate.acquire("unknown_type")
    try:
        gate.acquire("unknown_type")
        assert False, "Should have raised"
    except ProviderBusyError:
        pass
    gate.release("unknown_type")


def test_dispatcher_uses_provider_gate_for_llm():
    """Dispatcher should acquire/release provider gate around LLM call."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    dispatcher = app.state.dispatcher

    # Replace provider_gate with a mock to track calls
    mock_gate = MagicMock()
    dispatcher.provider_gate = mock_gate

    client = TestClient(app)
    resp = client.post("/api/pet/event", json={"type": "pet_head", "source": "runtime"})
    assert resp.status_code == 200

    # fast_llm profile maps to llm_fast gate type
    mock_gate.acquire.assert_called_once_with("llm_fast")
    mock_gate.release.assert_called_once_with("llm_fast")


def test_dispatcher_provider_gate_slow_profile():
    """Dispatcher should use llm_slow gate for thinking_mode events."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    dispatcher = app.state.dispatcher

    mock_gate = MagicMock()
    dispatcher.provider_gate = mock_gate

    client = TestClient(app)
    resp = client.post("/api/pet/event", json={
        "type": "text_message",
        "source": "runtime",
        "payload": {"user_text": "帮我写一个算法", "thinking_mode": True},
    })
    assert resp.status_code == 200

    mock_gate.acquire.assert_called_once_with("llm_slow")
    mock_gate.release.assert_called_once_with("llm_slow")
