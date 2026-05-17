"""Live integration tests against a real Petagent server on nubia.

These tests hit real APIs: LLM (MiMo), weather (wttr.in), device state, etc.
They verify each functional requirement end-to-end through the HTTP API.

Run with:
    PETAGENT_TEST_URL=http://192.168.x.x:8000 .venv/bin/pytest tests/test_live_nubia.py -v

Requires: the server must be started separately and PETAGENT_TEST_URL must be set.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx
import pytest

BASE = os.environ.get("PETAGENT_TEST_URL", "")

pytestmark = pytest.mark.skipif(
    not BASE,
    reason="PETAGENT_TEST_URL not set; skipping live integration tests",
)


def _url(path: str) -> str:
    return BASE + path


# ── helpers ──────────────────────────────────────────────────────────────────

def _get(path: str, **kwargs) -> dict:
    r = httpx.get(_url(path), timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def _post(path: str, json: dict = None, **kwargs) -> dict:
    r = httpx.post(_url(path), json=json or {}, timeout=60, **kwargs)
    r.raise_for_status()
    return r.json()


# ── 1. Health check ──────────────────────────────────────────────────────────

def test_01_health_check():
    """GET /api/health — runtime is alive and reports pet name."""
    data = _get("/api/health")
    assert data.get("ok") is True
    assert "name" in data


# ── 2. Pet state persistence ─────────────────────────────────────────────────

def test_02_pet_state_returns_valid_structure():
    """GET /api/pet/state — returns mood, energy, intimacy etc."""
    data = _get("/api/pet/state")
    assert "mood" in data
    assert "energy" in data
    assert "intimacy" in data
    assert isinstance(data["mood"], str)


# ── 3. Skill registry lists skills with input_schema ─────────────────────────

def test_03_skill_registry_lists_skills():
    """GET /api/skills — lists weather.current and device.info with input_schema."""
    data = _get("/api/skills")
    skills = data.get("skills", [])
    ids = [s["id"] for s in skills]
    assert "weather.current" in ids
    assert "device.info" in ids
    weather = next(s for s in skills if s["id"] == "weather.current")
    assert "input_schema" in weather


# ── 4. Weather skill — real wttr.in API call ─────────────────────────────────

def test_04_weather_skill_real_api():
    """POST /api/skills/weather.current/run — hits wttr.in and returns weather data."""
    data = _post("/api/skills/weather.current/run", json={"location": "Shanghai"})
    assert data.get("ok") is True
    content = data.get("content", "")
    assert len(content) > 0, "weather content should not be empty"
    # wttr.in returns weather info (may be in Chinese or English)
    content_lower = content.lower()
    assert any(kw in content_lower for kw in [
        "°", "度", "temp", "weather", "shanghai", "wind", "humid", "cloudy", "晴", "阴", "雨",
    ]), f"unexpected weather content: {content[:200]}"


# ── 5. Device info skill ─────────────────────────────────────────────────────

def test_05_device_info_skill():
    """POST /api/skills/device.info/run — returns device state."""
    data = _post("/api/skills/device.info/run", json={})
    assert data.get("ok") is True
    content = data.get("content", "")
    assert len(content) > 0


# ── 6. Interaction catalog — dynamic button list ─────────────────────────────

def test_06_interaction_catalog():
    """GET /api/interactions — returns interaction definitions with labels."""
    items = _get("/api/interactions")
    assert isinstance(items, list)
    assert len(items) >= 5, f"expected >=5 interactions, got {len(items)}"
    first = items[0]
    assert "event_id" in first
    assert "label" in first
    assert "default_mood" in first
    assert "default_animation" in first
    event_ids = [it["event_id"] for it in items]
    assert "pet_head" in event_ids
    assert "hug" in event_ids


# ── 7. Text chat — real LLM call ─────────────────────────────────────────────

def test_07_text_chat_real_llm():
    """POST /api/text/chat — real LLM generates reply with mood and animation."""
    data = _post("/api/text/chat", json={"text": "你好呀 Momo"})
    assert "reply" in data
    assert len(data["reply"]) > 0, "LLM reply should not be empty"
    assert "mood" in data
    assert isinstance(data["mood"], str)
    assert "face_type" in data
    assert "animation" in data


# ── 8. Pet event dispatch — full agent loop ──────────────────────────────────

def test_08_pet_event_full_loop():
    """POST /api/pet/event — dispatches pet_head event through full agent loop."""
    data = _post("/api/pet/event", json={"event": "pet_head"})
    assert "reply" in data
    assert len(data.get("reply", "")) > 0
    assert "mood" in data
    assert "animation" in data
    assert "pet_state" in data
    assert "runtime" in data


# ── 9. Proactive events ─────────────────────────────────────────────────────

def test_09_proactive_events():
    """GET /api/pet/proactive — proactive service responds (active or inactive)."""
    data = _get("/api/pet/proactive")
    assert isinstance(data, dict)
    assert "active" in data


# ── 10. Context debug — episode tracking ─────────────────────────────────────

def test_10_context_debug():
    """GET /api/context/debug — returns current episode info."""
    data = _get("/api/context/debug")
    assert data.get("ok") is True
    assert "current_episode" in data
    assert "total_events" in data


# ── 11. Memory debug ─────────────────────────────────────────────────────────

def test_11_memory_debug():
    """GET /api/memory/debug — returns memory system state."""
    data = _get("/api/memory/debug")
    assert data.get("ok") is True
    assert "debug_enabled" in data


# ── 12. Agent run tracking ───────────────────────────────────────────────────

def test_12_agent_run_tracking():
    """GET /api/context/runs — returns recent agent runs with observability."""
    data = _get("/api/context/runs")
    assert data.get("ok") is True
    runs = data.get("runs", [])
    assert isinstance(runs, list)
    if len(runs) > 0:
        run = runs[0]
        assert "run_id" in run
        assert "status" in run


# ── 13. Runtime skills endpoint ──────────────────────────────────────────────

def test_13_runtime_skills():
    """GET /api/runtime/skills — lists skills from runtime registry."""
    data = _get("/api/runtime/skills")
    skills = data.get("skills", [])
    assert len(skills) >= 2
    ids = [s["id"] for s in skills]
    assert "weather.current" in ids
    assert "device.info" in ids


# ── server management ────────────────────────────────────────────────────────

def _wait_for_server(url: str, timeout: int = 30) -> bool:
    """Wait until server is responsive."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url + "/api/health", timeout=3)
            if r.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.ReadTimeout):
            pass
        time.sleep(1)
    return False


if __name__ == "__main__":
    import pytest

    if len(sys.argv) > 1 and sys.argv[1] == "start":
        env = os.environ.copy()
        env.setdefault("PETAGENT_DATA_DIR", "/data/data/com.termux/files/home/petagent-data")
        proc = subprocess.Popen(
            [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9821"],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            env=env,
        )
        print(f"Server PID: {proc.pid}")
        if _wait_for_server(BASE):
            print("Server ready")
        else:
            print("Server failed to start")
            proc.kill()
            sys.exit(1)
        proc.wait()
    else:
        if not _wait_for_server(BASE, timeout=5):
            print(f"Server not reachable at {BASE}")
            sys.exit(1)
        sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
