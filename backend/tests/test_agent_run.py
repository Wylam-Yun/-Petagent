from __future__ import annotations

from app.main import create_app
from app.runtime.agent_run import AgentObservation, AgentRun, AgentRunRegistry
from app.runtime.context_manager import ContextManager
from app.runtime.events import PetEvent
from starlette.testclient import TestClient


def test_agent_run_has_required_fields():
    run = AgentRun()
    assert run.run_id.startswith("run-")
    assert run.event_id == ""
    assert run.episode_id == ""
    assert run.route == ""
    assert run.context_profile == ""
    assert run.provider == ""
    assert isinstance(run.requested_tools, list)
    assert isinstance(run.tool_observations, list)
    assert run.final_action is None
    assert run.audio_job_id is None
    assert isinstance(run.timings_ms, dict)
    assert run.status == "started"
    assert run.error is None
    assert isinstance(run.observations, list)
    assert run.created_at
    assert run.updated_at


def test_agent_run_status_transitions():
    run = AgentRun()
    assert run.status == "started"
    run.set_status("planning")
    assert run.status == "planning"
    run.set_status("action_generated")
    assert run.status == "action_generated"
    run.set_status("completed")
    assert run.status == "completed"


def test_agent_run_failed_status():
    run = AgentRun()
    run.set_status("failed")
    run.error = "LLM provider timeout"
    assert run.status == "failed"
    assert run.error == "LLM provider timeout"


def test_agent_run_records_observations():
    run = AgentRun()
    run.record("context_built", {"profile": "fast_companion", "budget_used": 1200})
    run.record("audio_enqueued", {"job_id": "aud-123"})
    assert len(run.observations) == 2
    assert run.observations[0].kind == "context_built"
    assert run.observations[0].detail["profile"] == "fast_companion"
    assert run.observations[1].kind == "audio_enqueued"


def test_agent_run_registry_create_and_get():
    registry = AgentRunRegistry()
    run = registry.create(event_id="evt-abc", episode_id="ep-123")
    assert run.event_id == "evt-abc"
    assert run.episode_id == "ep-123"
    found = registry.get(run.run_id)
    assert found is run


def test_agent_run_registry_bounded_eviction():
    registry = AgentRunRegistry(max_runs=3)
    ids = []
    for i in range(5):
        run = registry.create(event_id=f"evt-{i}")
        ids.append(run.run_id)
    # First two should be evicted
    assert registry.get(ids[0]) is None
    assert registry.get(ids[1]) is None
    # Last three should still exist
    assert registry.get(ids[2]) is not None
    assert registry.get(ids[3]) is not None
    assert registry.get(ids[4]) is not None


def test_agent_run_registry_recent():
    registry = AgentRunRegistry()
    for i in range(5):
        registry.create(event_id=f"evt-{i}")
    recent = registry.recent(limit=3)
    assert len(recent) == 3
    # Most recent first
    assert recent[0]["event_id"] == "evt-4"
    assert recent[1]["event_id"] == "evt-3"
    assert recent[2]["event_id"] == "evt-2"


def test_agent_run_to_dict_sanitized():
    run = AgentRun()
    run.event_id = "evt-abc"
    run.route = "fast"
    run.context_profile = "fast_companion"
    run.record("context_built", {"profile": "fast_companion"})
    d = run.to_dict()
    assert d["run_id"] == run.run_id
    assert d["event_id"] == "evt-abc"
    assert d["route"] == "fast"
    assert d["context_profile"] == "fast_companion"
    assert d["observation_count"] == 1
    # to_dict should not include raw observations list
    assert "observations" not in d


# --- Integration tests ---


def test_text_chat_creates_agent_run():
    app = create_app(testing=True)
    client = TestClient(app)
    response = client.post("/api/text/chat", json={"text": "你好呀"})
    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["run_id"]
    assert body["runtime"]["context_profile"]
    registry = app.state.agent_run_registry
    runs = registry.recent(limit=1)
    assert len(runs) == 1
    assert runs[0]["run_id"] == body["runtime"]["run_id"]
    assert runs[0]["status"] == "completed"


def test_button_event_fast_companion_profile():
    app = create_app(testing=True)
    client = TestClient(app)
    response = client.post("/api/pet/event", json={"event": "hug", "payload": {}})
    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["context_profile"] == "unified"


def test_recall_question_profile():
    app = create_app(testing=True)
    client = TestClient(app)
    response = client.post("/api/text/chat", json={"text": "昨天我们聊了啥"})
    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["context_profile"] == "unified"


def test_weather_question_profile():
    app = create_app(testing=True)
    client = TestClient(app)
    response = client.post("/api/text/chat", json={"text": "今天适合出门吗"})
    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["context_profile"] == "unified"


def test_thinking_mode_slow_route():
    app = create_app(testing=True)
    client = TestClient(app)
    response = client.post("/api/text/chat", json={"text": "你好", "thinking_mode": True})
    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["context_profile"] == "unified"
    assert body["text_route"]["selected"] == "unified"


def test_context_profile_none_preserves_default():
    from app.db import create_state_store
    from app.config import load_settings
    settings = load_settings()
    state_store = create_state_store(settings, testing=True)
    from app.runtime.context_store import EpisodeStore, EventLogStore
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    cm = ContextManager({"max_context_chars": 4500})
    episode, _ = episodes.get_or_create_current()
    event = PetEvent(type="voice_message", source="voice_fast", payload={"user_text": "你好"})
    ctx_default = cm.build(event=event, pet_state={}, episode=episode, event_log_store=event_log)
    ctx_none = cm.build(event=event, pet_state={}, episode=episode, event_log_store=event_log, context_profile=None)
    assert ctx_default["context_profile"] == "default"
    assert ctx_none["context_profile"] == "default"
    assert ctx_default["recent_exact_events"] == ctx_none["recent_exact_events"]
    assert ctx_default["relevant_memories"] == ctx_none["relevant_memories"]


def test_fast_companion_excludes_heavy_context():
    from app.db import create_state_store
    from app.config import load_settings
    settings = load_settings()
    state_store = create_state_store(settings, testing=True)
    from app.runtime.context_store import EpisodeStore, EventLogStore
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    cm = ContextManager({"max_context_chars": 4500})
    episode, _ = episodes.get_or_create_current()
    event = PetEvent(type="text_message", source="text_fast", payload={"user_text": "你好"})
    ctx = cm.build(
        event=event, pet_state={}, episode=episode,
        event_log_store=event_log, context_profile="fast_companion",
    )
    assert ctx["context_profile"] == "fast_companion"
    assert ctx["daily_digest"] is None
    assert ctx["episode_summaries"] == []
    assert ctx["important_quotes"] == []


def test_debug_runs_endpoint():
    app = create_app(testing=True)
    client = TestClient(app)
    # Create a run first
    client.post("/api/text/chat", json={"text": "你好"})
    response = client.get(
        "/api/context/runs",
        headers={"Authorization": f"Bearer {app.state.internal_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert len(body["runs"]) >= 1
    assert body["runs"][0]["run_id"]
