"""Debug endpoints — token-protected, not for production frontend use."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.auth import (
    is_loopback,
    require_internal_token,
    rotate_internal_token,
    token_fingerprint,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/debug/runs")
def debug_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
) -> Dict[str, Any]:
    """Recent agent runs — token-protected debug endpoint."""
    require_internal_token(request)

    store = request.app.state.agent_run_store
    runs = store.recent(limit=limit) if store is not None else []
    return {"ok": True, "runs": runs, "total": store.count() if store is not None else 0}


@router.get("/api/debug/incidents")
def debug_incidents(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
) -> Dict[str, Any]:
    """Recent runtime incidents — token-protected debug endpoint."""
    require_internal_token(request)

    incident_store = getattr(request.app.state, "incident_store", None)
    if incident_store is None:
        return {"ok": True, "incidents": [], "total": 0}
    incidents = incident_store.recent(limit=limit)
    return {"ok": True, "incidents": incidents, "total": incident_store.count()}


@router.get("/api/debug/idle-state")
def debug_idle_state(request: Request) -> Dict[str, Any]:
    require_internal_token(request)
    local_date = datetime.now().date().isoformat()
    svc = getattr(request.app.state, "ambient_bubble_service", None)
    ambient = svc.debug_state(local_date) if svc is not None else {}
    scheduler = getattr(request.app.state, "proactive_scheduler", None)
    eligible = bool(scheduler and not scheduler.is_frontend_stale())
    return {
        "ok": True,
        "eligible": eligible,
        "block_reason": "" if eligible else "frontend_stale",
        "next_trigger_time": "",
        "backoff_step": ambient.get("backoff_step", 0),
        "daily_count": ambient.get("daily_count", 0),
        "pending_count": ambient.get("pending_count", 0),
        "activity_counts": ambient.get("activity_counts", {}),
        "last_suggested_activity": ambient.get("last_suggested_activity", ""),
        "last_rendered_expression_key": ambient.get("last_rendered_expression_key", ""),
        "last_rendered_action": ambient.get("last_rendered_action", ""),
        "last_validation_failure_reason": ambient.get("last_validation_failure_reason", ""),
        "last_submitted_tts_text": getattr(
            request.app.state.dispatcher, "last_submitted_tts_text", ""
        ),
        "last_submitted_tts_event_id": getattr(
            request.app.state.dispatcher, "last_submitted_tts_event_id", ""
        ),
        "last_submitted_tts_at": getattr(
            request.app.state.dispatcher, "last_submitted_tts_at", ""
        ),
        "last_idle_bubble_source": ambient.get("last_idle_bubble_source", ""),
    }


@router.post("/api/internal/incident")
async def internal_incident(request: Request) -> Dict[str, Any]:
    """Record an incident from manager scripts — loopback + token required."""
    require_internal_token(request)
    if not is_loopback(request):
        incident_store = getattr(request.app.state, "incident_store", None)
        if incident_store is not None:
            client = request.client.host if request.client else "unknown"
            incident_store.record(
                "auth_rejected",
                {
                    "path": request.url.path,
                    "method": request.method,
                    "client": client,
                    "reason": "non_loopback_internal",
                },
            )
        raise HTTPException(status_code=403, detail="Internal endpoint requires loopback")

    incident_store = getattr(request.app.state, "incident_store", None)
    if incident_store is None:
        return {"ok": False, "error": "incident store not configured"}

    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON"}

    kind = str(body.get("kind") or "unknown")
    payload = body.get("payload") or {}
    incident_store.record(kind, payload)
    return {"ok": True}


@router.post("/api/debug/token/rotate")
def rotate_debug_token(request: Request) -> Dict[str, Any]:
    """Rotate the internal debug token without returning the raw token value."""
    require_internal_token(request)

    if os.environ.get("DEBUG_INTERNAL_TOKEN", "").strip():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Internal token is managed by DEBUG_INTERNAL_TOKEN",
                "reason": "env_token_configured",
            },
        )

    settings = request.app.state.settings
    token, token_path = rotate_internal_token(settings)
    request.app.state.internal_token = token

    incident_store = getattr(request.app.state, "incident_store", None)
    if incident_store is not None:
        incident_store.record(
            "internal_token_rotated",
            {
                "path": str(token_path),
                "fingerprint": token_fingerprint(token),
            },
        )

    return {
        "ok": True,
        "token_path": str(token_path),
        "fingerprint": token_fingerprint(token),
    }
