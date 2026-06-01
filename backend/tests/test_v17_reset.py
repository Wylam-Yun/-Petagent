from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app


def test_runtime_reset_clears_user_context_but_keeps_debug_tables():
    app = create_app(testing=True)
    client = TestClient(app)
    token = app.state.internal_token

    app.state.notebook_manager.overwrite_memory_lines([
        {"category": "preference", "content": "用户喜欢咖啡。"}
    ])
    app.state.successful_turn_store.record_successful_turn("evt-1")
    assert app.state.memory_judgment_queue.enqueue_turn_summary("记住咖啡", "我记住啦", "unified")
    app.state.agent_run_store.save({
        "run_id": "run-reset-audit",
        "event_id": "evt-audit",
        "status": "completed",
        "final_action": {"reply": "审计保留"},
    })
    app.state.audio_job_store.save({
        "job_id": "job-reset-audit",
        "status": "failed",
        "text": "审计保留",
        "created_at": "2026-05-31T10:00:00",
        "updated_at": "2026-05-31T10:00:00",
    })

    response = client.post(
        "/api/runtime/reset",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm": "重新认识"},
    )

    assert response.status_code == 200
    assert "我是豆豆" not in response.json()["reply"]
    assert app.state.event_log_store.count() == 0
    assert app.state.successful_turn_store.snapshot()["successful_turn_count_total"] == 0
    assert app.state.memory_judgment_queue.pending_count() == 0
    assert "用户喜欢咖啡" not in app.state.notebook_manager.read_raw("memory.md")
    assert "<!-- v1.4_single_notebook -->" in app.state.notebook_manager.read_raw("memory.md")
    assert "canonical memory is memory.md" in app.state.notebook_manager.read_raw("user.md")
    assert app.state.agent_run_store.count() == 1
    assert app.state.audio_job_store.get("job-reset-audit") is not None


def test_runtime_reset_resets_tick_clock_so_initial_state_is_stable():
    app = create_app(testing=True)
    client = TestClient(app)
    token = app.state.internal_token

    stale_tick = datetime.utcnow() - timedelta(hours=12)
    app.state.tick_service.set_last_tick(stale_tick)

    response = client.post(
        "/api/runtime/reset",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm": "重新认识"},
    )

    assert response.status_code == 200
    reset_state = response.json()["pet_state"]

    next_state = app.state.tick_service.apply_if_due()

    assert next_state["energy"] == reset_state["energy"]
    assert next_state["hunger"] == reset_state["hunger"]
    assert next_state["loneliness"] == reset_state["loneliness"]
    assert next_state["sleepiness"] == reset_state["sleepiness"]
