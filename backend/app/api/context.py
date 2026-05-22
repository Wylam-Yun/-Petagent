from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Request

from app.api.auth import require_internal_token
from app.runtime.context_store import desensitize_text

router = APIRouter()


@router.post("/api/context/refresh")
def context_refresh(request: Request) -> Dict[str, Any]:
    """换话题：关闭当前 episode，创建新 episode，记录 context_refresh 事件."""
    dispatcher = request.app.state.dispatcher

    # Use dispatcher's event lock to serialize with voice/touch events
    with dispatcher._event_lock:
        episode_manager = request.app.state.episode_manager
        event_log_store = request.app.state.event_log_store
        summary_job_store = request.app.state.summary_job_store

        # Close old episode and create new one
        new_episode, closed_episode_id = episode_manager.refresh_topic()

        # Enqueue summary job for the closed episode
        if closed_episode_id and summary_job_store is not None:
            summary_job_store.enqueue(closed_episode_id)

        # Record context_refresh event in the event log and update episode count
        if event_log_store is not None:
            from app.runtime.events import PetEvent

            refresh_event = PetEvent(type="context_refresh", source="ui")
            event_log_store.record(
                event_id=refresh_event.id,
                episode_id=new_episode["episode_id"],
                event_type="context_refresh",
                source="ui",
                user_text="",
                pet_reply="",
            )
            episode_manager.update_event_count(new_episode["episode_id"])

    return {
        "ok": True,
        "episode": new_episode,
        "reply": "好呀，我们换个轻一点的话题。",
    }


@router.get("/api/context/runs")
def context_runs(request: Request, limit: int = 10) -> Dict[str, Any]:
    """Debug: recent agent runs with sanitized observations."""
    require_internal_token(request)
    registry = getattr(request.app.state, "agent_run_registry", None)
    if registry is None:
        return {"ok": False, "reason": "agent_run_registry not configured"}
    runs = registry.recent(limit=min(limit, 50))
    return {"ok": True, "runs": runs}


@router.get("/api/context/debug")
def context_debug(request: Request) -> Dict[str, Any]:
    """调试当前 episode、最近事件数、上下文预算."""
    require_internal_token(request)
    episode_manager = request.app.state.episode_manager
    event_log_store = request.app.state.event_log_store
    settings = request.app.state.settings

    cc_config = settings.app_config.get("cognition_context", {})
    debug_enabled = cc_config.get("debug_enabled", False)

    # Current episode (peek only, don't create)
    current_episode = episode_manager.peek_current()

    # Event count
    event_count = event_log_store.count() if event_log_store else 0

    result: Dict[str, Any] = {
        "ok": True,
        "current_episode": current_episode,
        "total_events": event_count,
        "debug_enabled": debug_enabled,
    }

    if debug_enabled:
        # Return detailed info with desensitized text
        ep_id = current_episode.get("episode_id") if current_episode else None
        recent = event_log_store.recent_events(
            episode_id=ep_id,
            limit=10,
        ) if event_log_store and ep_id else []
        desensitized_events = []
        for evt in recent:
            desensitized_events.append({
                "event_type": evt.get("event_type", ""),
                "created_at": evt.get("created_at_utc", ""),
                "user_text": desensitize_text(evt.get("user_text") or ""),
                "pet_reply": desensitize_text(evt.get("pet_reply") or ""),
            })
        result["recent_events"] = desensitized_events
        result["context_config"] = cc_config

    return result
