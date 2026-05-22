"""Debug endpoints — token-protected, not for production frontend use."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request

from app.api.auth import require_internal_token

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


@router.post("/api/internal/incident")
async def internal_incident(request: Request) -> Dict[str, Any]:
    """Record an incident from manager scripts — loopback + token required."""
    require_internal_token(request)

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
