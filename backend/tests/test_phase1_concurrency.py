"""Tests for STAB-007: App-level concurrency gates."""
from __future__ import annotations

import asyncio
import time
import threading
from unittest.mock import MagicMock

import pytest

from app.runtime.concurrency import AgentWorkExecutor, ServerBusyError


def test_server_busy_error_has_error_class():
    err = ServerBusyError()
    assert err.error_class == "server_busy"


def test_text_chat_returns_503_when_saturated():
    """When executor queue is full, text chat should return 503."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    # Create a saturated executor by manipulating inflight counter
    original_executor = app.state.agent_work_executor
    original_executor._inflight = original_executor.max_workers + original_executor.max_queue

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/text/chat", json={"text": "hello"})
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error_class"] == "server_busy"

    # Restore
    original_executor._inflight = 0


def test_voice_chat_returns_503_when_saturated():
    """When executor queue is full, voice chat should return 503."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    original_executor = app.state.agent_work_executor
    original_executor._inflight = original_executor.max_workers + original_executor.max_queue

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/voice/chat",
        data={},
        files={"file": ("voice.wav", b"RIFF mock wav bytes", "audio/wav")},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["error_class"] == "server_busy"

    original_executor._inflight = 0


def test_health_not_gated_by_concurrency():
    """Health endpoints should work even when executor is saturated."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    original_executor = app.state.agent_work_executor
    original_executor._inflight = original_executor.max_workers + original_executor.max_queue

    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health/watchdog").status_code == 200

    original_executor._inflight = 0


def test_text_chat_works_normally():
    """Text chat should work when executor has capacity."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)
    resp = client.post("/api/text/chat", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json()["error_class"] is None


def test_executor_tracks_inflight():
    """Executor should track inflight count correctly."""
    executor = AgentWorkExecutor(max_workers=2, max_queue=2)
    assert executor._inflight == 0

    blocker = threading.Event()

    def blocking_fn():
        blocker.wait(timeout=5)
        return "done"

    loop = asyncio.new_event_loop()

    async def run_test():
        # Start a task
        task = asyncio.create_task(executor.submit(blocking_fn))
        await asyncio.sleep(0.05)  # Let it start
        assert executor._inflight == 1

        # Complete it
        blocker.set()
        result = await task
        assert result == "done"
        assert executor._inflight == 0

    loop.run_until_complete(run_test())
    loop.close()
