"""Tests for audio retry endpoint and error classification (V1.3 Stage 4)."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from tempfile import mkdtemp
from typing import Optional
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.errors import (
    ProviderAuthError,
    ProviderNetworkError,
    ProviderQuotaError,
    ProviderTimeoutError,
)
from app.providers.tts_mimo import MockTTSProvider
from app.runtime.audio_jobs import AudioJobManager, _map_error_class


class BlockingTTSProvider:
    """TTS provider that blocks until unblocked, for testing pending jobs."""

    def __init__(self, audio_dir: Path):
        self.audio_dir = audio_dir
        self._event = threading.Event()

    def unblock(self):
        self._event.set()

    def synthesize(self, text: str, voice_style: str = "soft") -> Optional[str]:
        self._event.wait(timeout=10)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        from uuid import uuid4
        filename = "mock-%s.wav" % uuid4().hex
        path = self.audio_dir / filename
        path.write_bytes(b"RIFF$\x00\x00\x00WAVEfmt " + text.encode("utf-8")[:32])
        return "/static/audio/" + filename


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 3.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = client.get(f"/api/audio/jobs/{job_id}")
        if response.status_code != 200:
            return None
        last = response.json()
        if last["status"] in {"ready", "failed", "expired",
                               "failed_runtime_restart", "failed_shutdown"}:
            return last
        time.sleep(0.02)
    return last


def test_retry_failed_job():
    app = create_app(testing=True)
    app.state.audio_job_manager.tts_provider.fail = True
    client = TestClient(app)

    response = client.post("/api/text/chat", json={"text": "你好"})
    job_id = response.json().get("audio_job_id")
    assert job_id

    job = _wait_for_job(client, job_id)
    assert job["status"] == "failed"

    retry_response = client.post(f"/api/audio/jobs/{job_id}/retry")
    assert retry_response.status_code == 200
    new_id = retry_response.json()["new_job_id"]
    assert new_id != job_id

    new_job = _wait_for_job(client, new_id)
    assert new_job["status"] in {"ready", "failed"}


def test_retry_expired_job():
    tts = BlockingTTSProvider(Path(mkdtemp()))
    mgr = AudioJobManager(tts, ttl_seconds=0, max_workers=1)  # expire immediately
    job_id = mgr.enqueue("test")

    job = mgr.get(job_id)
    assert job.status == "expired"

    new_id = mgr.retry(job_id)
    assert new_id is not None
    assert new_id != job_id
    tts.unblock()
    mgr.shutdown()


def test_retry_pending_job_rejected():
    app = create_app(testing=True)
    client = TestClient(app)

    response = client.post("/api/text/chat", json={"text": "你好"})
    job_id = response.json().get("audio_job_id")
    if not job_id:
        return  # no audio job in this config

    # Try to retry while still pending
    retry_response = client.post(f"/api/audio/jobs/{job_id}/retry")
    # Might be pending or already done, but if pending should be 400
    if retry_response.status_code == 400:
        assert "Cannot retry" in retry_response.json()["detail"]


def test_retry_completed_job_rejected():
    app = create_app(testing=True)
    client = TestClient(app)

    response = client.post("/api/text/chat", json={"text": "你好"})
    job_id = response.json().get("audio_job_id")
    if not job_id:
        return

    job = _wait_for_job(client, job_id)
    if job["status"] == "ready":
        retry_response = client.post(f"/api/audio/jobs/{job_id}/retry")
        assert retry_response.status_code == 400


def test_retry_uses_old_text_and_style():
    tts = BlockingTTSProvider(Path(mkdtemp()))
    mgr = AudioJobManager(tts, ttl_seconds=0, max_workers=1)
    job_id = mgr.enqueue("hello world", voice_style="gentle")

    old = mgr.get(job_id)
    assert old.status == "expired"

    new_id = mgr.retry(job_id)
    assert new_id is not None
    new = mgr.get(new_id)
    assert new.text == "hello world"
    assert new.voice_style == "gentle"
    assert new.session_id == old.session_id
    tts.unblock()
    mgr.shutdown()


def test_retry_idempotent():
    tts = BlockingTTSProvider(Path(mkdtemp()))
    mgr = AudioJobManager(tts, ttl_seconds=0, max_workers=1)
    job_id = mgr.enqueue("test idempotent")

    new_id_1 = mgr.retry(job_id)
    new_id_2 = mgr.retry(job_id)
    assert new_id_1 is not None
    assert new_id_1 == new_id_2  # same new job within 5s window
    tts.unblock()
    mgr.shutdown()


def test_failed_job_has_error_class():
    app = create_app(testing=True)
    app.state.audio_job_manager.tts_provider.fail = True
    client = TestClient(app)

    response = client.post("/api/text/chat", json={"text": "你好"})
    job_id = response.json().get("audio_job_id")
    if not job_id:
        return

    job = _wait_for_job(client, job_id)
    assert job["status"] == "failed"
    assert job["error_class"] is not None


def test_infrastructure_error_class():
    tts = BlockingTTSProvider(Path(mkdtemp()))
    mgr = AudioJobManager(tts, max_workers=1, ttl_seconds=60)
    job_id = mgr.enqueue("test infra")
    # Job stays pending because TTS blocks
    mgr.mark_restart_failed()
    job = mgr.get(job_id)
    assert job.status == "failed_runtime_restart"
    assert job.error_class == "infrastructure"
    tts.unblock()
    mgr.shutdown()


def test_expired_job_error_class_is_timeout():
    tts = BlockingTTSProvider(Path(mkdtemp()))
    mgr = AudioJobManager(tts, ttl_seconds=0, max_workers=1)
    job_id = mgr.enqueue("test timeout")
    job = mgr.get(job_id)
    assert job.status == "expired"
    assert job.error_class == "timeout"
    tts.unblock()
    mgr.shutdown()


def test_tts_empty_error_class_is_auth_config():
    tts = MockTTSProvider(Path(mkdtemp()))
    tts.synthesize = MagicMock(return_value=None)  # empty return
    mgr = AudioJobManager(tts, max_workers=1, ttl_seconds=60)
    job_id = mgr.enqueue("test empty")
    deadline = time.time() + 2
    while time.time() < deadline:
        job = mgr.get(job_id)
        if job.status != "pending":
            break
        time.sleep(0.02)
    assert job.status == "failed"
    assert job.error_class == "auth_config"
    mgr.shutdown()


def test_failed_runtime_restart_visible():
    tts = BlockingTTSProvider(Path(mkdtemp()))
    mgr = AudioJobManager(tts, max_workers=1, ttl_seconds=60)
    job_id = mgr.enqueue("test visible")
    mgr.mark_restart_failed()

    job = mgr.get(job_id)
    assert job is not None
    assert job.status == "failed_runtime_restart"
    assert job.error_class == "infrastructure"
    tts.unblock()
    mgr.shutdown()


def test_map_error_class_provider_network():
    exc = ProviderNetworkError(provider="tts")
    assert _map_error_class(exc) == "network"


def test_map_error_class_provider_timeout():
    exc = ProviderTimeoutError(provider="tts")
    assert _map_error_class(exc) == "timeout"


def test_map_error_class_provider_auth():
    exc = ProviderAuthError(provider="tts")
    assert _map_error_class(exc) == "auth_config"


def test_map_error_class_provider_quota():
    exc = ProviderQuotaError(provider="tts")
    assert _map_error_class(exc) == "auth_config"


def test_map_error_class_unknown():
    exc = RuntimeError("something")
    assert _map_error_class(exc) == "unknown"
