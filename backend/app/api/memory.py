from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.api.auth import is_loopback, require_internal_token
from app.runtime.context_store import desensitize_text

router = APIRouter()

_RESET_CONFIRM_TEXT = "\u91cd\u65b0\u8ba4\u8bc6"  # 重新认识


@router.get("/api/memory/debug")
def memory_debug(request: Request) -> Dict[str, Any]:
    """Return desensitized memory debug info. Only when debug_enabled."""
    require_internal_token(request)
    settings = request.app.state.settings
    cc_config = settings.app_config.get("cognition_context", {})
    debug_enabled = cc_config.get("debug_enabled", False)

    if not debug_enabled:
        return {"ok": True, "debug_enabled": False}

    memory_manager = getattr(request.app.state, "memory_manager", None)
    candidate_store = getattr(request.app.state, "memory_candidate_store", None)
    episode_summary_store = getattr(request.app.state, "episode_summary_store", None)
    daily_summary_store = getattr(request.app.state, "daily_summary_store", None)

    result: Dict[str, Any] = {"ok": True, "debug_enabled": True}

    # Memories
    if memory_manager is not None:
        with memory_manager.connection.locked():
            rows = memory_manager.connection.execute(
                "SELECT id, type, content, importance, created_at, usage_count FROM memory ORDER BY id DESC LIMIT 20"
            ).fetchall()
        result["memories"] = [
            {
                "id": r["id"],
                "type": r["type"],
                "content": desensitize_text(r["content"], 100),
                "importance": r["importance"],
                "created_at": r["created_at"],
                "usage_count": r["usage_count"],
            }
            for r in rows
        ]
        result["memory_count"] = memory_manager.count()

    # Candidates
    if candidate_store is not None:
        pending = candidate_store.pending(limit=10)
        result["pending_candidates"] = [
            {
                "id": c["id"],
                "trigger_reason": c["trigger_reason"],
                "candidate_text": desensitize_text(c["candidate_text"], 80),
                "created_at": c["created_at"],
            }
            for c in pending
        ]
        result["pending_candidate_count"] = candidate_store.count_pending()

    # Episode summaries
    if episode_summary_store is not None:
        summaries = episode_summary_store.recent(limit=5)
        result["episode_summaries"] = [
            {
                "episode_id": s["episode_id"],
                "summary": desensitize_text(s["summary"], 100),
                "mood_notes": desensitize_text(s.get("mood_notes", ""), 50),
                "key_events": s.get("key_events", []),
            }
            for s in summaries
        ]

    # Daily summaries
    if daily_summary_store is not None:
        daily = daily_summary_store.recent(limit=3)
        result["daily_summaries"] = [
            {
                "local_date": d["local_date"],
                "summary": desensitize_text(d["summary"], 150),
                "key_events": d.get("key_events", []),
            }
            for d in daily
        ]

    # Memory cards
    memory_card_manager = getattr(request.app.state, "memory_card_manager", None)
    if memory_card_manager is not None:
        try:
            result["memory_cards"] = {
                "user_preferences": memory_card_manager.read_card("user_preferences"),
                "momo_memories": memory_card_manager.read_card("momo_memories"),
            }
        except Exception:
            pass

    return result


@router.post("/api/memory/curate")
def memory_curate(request: Request) -> Dict[str, Any]:
    """Manually trigger curator batch processing."""
    require_internal_token(request)
    curator = getattr(request.app.state, "memory_curator", None)
    candidate_store = getattr(request.app.state, "memory_candidate_store", None)
    if curator is None or candidate_store is None:
        raise HTTPException(status_code=503, detail="Curator not available")

    result = curator.curate_batch(candidate_store)

    # Rebuild cards if any memories were saved
    if result.get("saved", 0) > 0:
        memory_card_manager = getattr(request.app.state, "memory_card_manager", None)
        if memory_card_manager:
            try:
                memory_card_manager.rebuild("curator_saved")
            except Exception:
                pass

    return {"ok": True, **result}


@router.post("/api/memory/summarize")
def memory_summarize(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    """Manually trigger summary generation."""
    require_internal_token(request)
    mode = body.get("mode", "episode")
    summary_manager = getattr(request.app.state, "summary_manager", None)
    if summary_manager is None:
        raise HTTPException(status_code=503, detail="SummaryManager not available")

    if mode == "episode":
        event_log_store = request.app.state.event_log_store
        episode_manager = request.app.state.episode_manager
        episode = episode_manager.peek_current() if episode_manager else None
        episode_id = episode.get("episode_id") if episode else None
        if not episode_id:
            raise HTTPException(status_code=400, detail="No active episode")
        result = summary_manager.generate_episode_summary(
            episode_id=episode_id,
            event_log_store=event_log_store,
            episode_store=episode_manager,
        )
        return {"ok": True, "mode": "episode", "result": result}

    if mode == "daily":
        from datetime import datetime, timedelta, timezone

        tz = timezone(timedelta(hours=8))
        local_date = datetime.now(tz).strftime("%Y-%m-%d")
        result = summary_manager.generate_daily_summary(local_date)
        return {"ok": True, "mode": "daily", "result": result}

    raise HTTPException(status_code=400, detail="Invalid mode: %s" % mode)


@router.post("/api/runtime/reset")
def runtime_reset(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
    """Reset all runtime data. Requires { "confirm": "重新认识" }."""
    confirm = body.get("confirm", "")
    if not is_loopback(request):
        require_internal_token(request)
    if confirm != _RESET_CONFIRM_TEXT:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required. Send { \"confirm\": \"%s\" }" % _RESET_CONFIRM_TEXT,
        )

    settings = request.app.state.settings
    state_store = request.app.state.state_store

    # Clear all tables
    memory_manager = getattr(request.app.state, "memory_manager", None)
    candidate_store = getattr(request.app.state, "memory_candidate_store", None)
    summary_job_store = getattr(request.app.state, "summary_job_store", None)
    episode_summary_store = getattr(request.app.state, "episode_summary_store", None)
    daily_summary_store = getattr(request.app.state, "daily_summary_store", None)
    maintenance_state = getattr(request.app.state, "maintenance_state", None)
    event_log_store = request.app.state.event_log_store
    episode_manager = request.app.state.episode_manager
    interaction_log = getattr(request.app.state, "interaction_log", None)
    activation_manager = getattr(request.app.state, "activation_manager", None)
    successful_turn_store = getattr(request.app.state, "successful_turn_store", None)
    memory_judgment_queue = getattr(request.app.state, "memory_judgment_queue", None)
    notebook_manager = getattr(request.app.state, "notebook_manager", None)

    if memory_manager:
        memory_manager.clear_all()
    if candidate_store:
        candidate_store.clear_all()
    if summary_job_store:
        summary_job_store.clear_all()
    if episode_summary_store:
        episode_summary_store.clear_all()
    if daily_summary_store:
        daily_summary_store.clear_all()
    if maintenance_state:
        maintenance_state.clear_all()
    if successful_turn_store:
        successful_turn_store.clear_all()
    if memory_judgment_queue:
        memory_judgment_queue.clear()

    # Clear memory cards
    memory_card_manager = getattr(request.app.state, "memory_card_manager", None)
    if memory_card_manager:
        try:
            memory_card_manager.clear()
        except Exception:
            pass
    if notebook_manager:
        notebook_manager.overwrite_memory_lines([])

    if event_log_store:
        with event_log_store.connection.locked():
            event_log_store.connection.execute("DELETE FROM raw_event_log")
            event_log_store.connection.commit()
    if episode_manager:
        with episode_manager.connection.locked():
            episode_manager.connection.execute("DELETE FROM episode")
            episode_manager.connection.commit()
    if interaction_log:
        with interaction_log.connection.locked():
            interaction_log.connection.execute("DELETE FROM interaction_log")
            interaction_log.connection.commit()

    # Close activation session
    if activation_manager:
        try:
            activation_manager.exit("reset", confidence=1.0)
        except Exception:
            pass

    # Reset pet_state to initial values
    initial_state = settings.app_config.get("state", {}).get("initial", {})
    if initial_state:
        state_store.save_state(initial_state)
    tick_service = getattr(request.app.state, "tick_service", None)
    if tick_service:
        try:
            tick_service.set_last_tick(datetime.utcnow())
        except Exception:
            pass

    new_state = state_store.get_state()
    return {
        "ok": True,
        "pet_state": new_state,
        "reply": "\u4f60\u597d\u5440\uff0c\u6211\u5728\u8fd9\u91cc\u3002\u6211\u4eec\u91cd\u65b0\u5f00\u59cb\u8ba4\u8bc6\u5427\u3002",  # 你好呀，我在这里。我们重新开始认识吧。
    }
