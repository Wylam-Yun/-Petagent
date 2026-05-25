"""V1.1 live integration tests against a real PetAgent server.

Run from Mac:
    PETAGENT_TEST_URL=http://192.168.10.239:8000 \
    PETAGENT_INTERNAL_TOKEN_FILE=/path/to/token \
    ../.venv/bin/python -m pytest tests/test_live_nubia.py -q

Run on Nubia:
    cd ~/Petagent/backend
    PETAGENT_TEST_URL=http://127.0.0.1:8000 \
    PETAGENT_INTERNAL_TOKEN_FILE=../backend/secrets/internal_token \
    ../.venv/bin/python -m pytest tests/test_live_nubia.py -q
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import pytest

BASE = os.environ.get("PETAGENT_TEST_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE,
    reason="PETAGENT_TEST_URL not set; skipping live integration tests",
)


def _token() -> str:
    raw = os.environ.get("PETAGENT_INTERNAL_TOKEN", "").strip()
    if raw:
        return raw
    token_file = os.environ.get("PETAGENT_INTERNAL_TOKEN_FILE", "").strip()
    if token_file:
        try:
            return Path(token_file).read_text().strip()
        except OSError:
            return ""
    return ""


def _headers(require_token: bool = False) -> Dict[str, str]:
    token = _token()
    if require_token and not token:
        pytest.skip("PETAGENT_INTERNAL_TOKEN or PETAGENT_INTERNAL_TOKEN_FILE is required")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _url(path: str) -> str:
    return BASE + path


def _get(path: str, *, token: bool = False, timeout: float = 30) -> Dict[str, Any]:
    response = httpx.get(_url(path), headers=_headers(token), timeout=timeout)
    response.raise_for_status()
    return response.json()


def _post(
    path: str,
    *,
    json: Optional[Dict[str, Any]] = None,
    token: bool = False,
    timeout: float = 60,
) -> Dict[str, Any]:
    response = httpx.post(
        _url(path),
        json=json or {},
        headers=_headers(token),
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _status(method: str, path: str, *, json: Optional[Dict[str, Any]] = None) -> int:
    if method == "GET":
        response = httpx.get(_url(path), timeout=15)
    else:
        response = httpx.post(_url(path), json=json, timeout=15)
    return response.status_code


def test_01_health_light():
    data = _get("/api/health", timeout=5)
    assert data["ok"] is True
    assert data["name"] == "豆豆"
    assert "build_hash" in data


def test_02_health_watchdog():
    data = _get("/api/health/watchdog", timeout=5)
    assert data["ok"] is True
    assert "event_loop_tick_age_s" in data
    assert "agent_inflight_age_s" in data
    assert "provider_inflight_age_s" in data
    assert "frontend_heartbeat_age_s" in data
    assert "audio_queue_depth" in data


def test_03_client_config_public_and_safe():
    data = _get("/api/runtime/client-config", timeout=5)
    assert data["audio_wait_ms"] >= 30000
    assert isinstance(data["audio_progressive"], dict)
    forbidden = {"api_key", "tts_api_key", "proxy_url", "db_path", "internal_token"}
    assert forbidden.isdisjoint(data.keys())


def test_04_frontend_heartbeat_updates_watchdog():
    before = _get("/api/health/watchdog", timeout=5)["frontend_heartbeat_age_s"]
    posted = _post(
        "/api/frontend/heartbeat",
        json={"user_agent": "live-v1.1-test"},
        timeout=5,
    )
    assert posted["ok"] is True
    after = _get("/api/health/watchdog", timeout=5)["frontend_heartbeat_age_s"]
    assert after >= 0
    if before >= 0:
        assert after <= before + 1


def test_05_pet_state_and_interactions_public():
    state = _get("/api/pet/state", timeout=5)
    assert {"mood", "energy", "intimacy"}.issubset(state.keys())
    interactions = _get("/api/interactions", timeout=5)
    assert isinstance(interactions, list)
    assert any(item["event_id"] == "pet_head" for item in interactions)


def test_06_text_chat_and_audio_job_surface():
    data = _post("/api/text/chat", json={"text": "你好呀 Momo"}, timeout=90)
    assert data.get("reply")
    assert "runtime" in data
    assert "text_route" in data
    job_id = data.get("audio_job_id")
    if not job_id:
        return
    deadline = time.time() + 90
    job = None
    while time.time() < deadline:
        job = _get(f"/api/audio/jobs/{job_id}", timeout=10)
        if job["status"] in {"ready", "failed", "expired", "superseded"}:
            break
        time.sleep(1)
    assert job is not None
    assert "timings_ms" in job


def test_07_pet_event_dispatcher_response():
    data = _post("/api/pet/event", json={"event": "pet_head"}, timeout=90)
    assert data.get("reply")
    assert "runtime" in data
    assert "pet_state" in data


def test_08_debug_runs_and_incidents_with_token():
    runs = _get("/api/debug/runs?limit=5", token=True, timeout=10)
    assert runs["ok"] is True
    assert isinstance(runs["runs"], list)
    incidents = _get("/api/debug/incidents?limit=5", token=True, timeout=10)
    assert incidents["ok"] is True
    assert isinstance(incidents["incidents"], list)


def test_09_deep_health_with_token():
    data = _get("/api/health/deep", token=True, timeout=15)
    assert "db_quick_check" in data
    assert "wal_bytes" in data
    assert "provider_inflight_age_s" in data
    assert "probes" in data


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/health/deep", None),
        ("GET", "/api/debug/runs", None),
        ("GET", "/api/debug/incidents", None),
        ("POST", "/api/internal/incident", {"kind": "live_no_token_check"}),
        ("GET", "/api/context/debug", None),
        ("GET", "/api/context/runs", None),
        ("GET", "/api/memory/debug", None),
        ("POST", "/api/memory/curate", {}),
        ("POST", "/api/memory/summarize", {"mode": "episode"}),
        ("POST", "/api/runtime/reset", {"confirm": "wrong"}),
        ("GET", "/api/runtime/skills", None),
        ("POST", "/api/skills/device.info/run", {}),
    ],
)
def test_10_protected_endpoints_reject_missing_token(method: str, path: str, payload):
    assert _status(method, path, json=payload) == 403
