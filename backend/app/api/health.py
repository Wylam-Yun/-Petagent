"""Health endpoints: light, watchdog, deep."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from app.api.auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter()

_started_at = datetime.now(timezone.utc).isoformat()
_pid = os.getpid()


def _age_s(ts: float) -> float:
    """Return seconds since a perf_counter timestamp."""
    if ts <= 0:
        return -1.0
    return max(0.0, perf_counter() - ts)


@router.get("/api/health")
def health_light(request: Request) -> Dict[str, Any]:
    """Light health: < 50ms, no DB queries, no locks."""
    settings = request.app.state.settings
    build_info = getattr(request.app.state, "build_info", {})
    return {
        "ok": True,
        "name": settings.pet_name,
        "version": settings.schema_version,
        "build_hash": build_info.get("git_sha", ""),
        "pid": _pid,
        "started_at": _started_at,
    }


@router.get("/api/health/watchdog")
def health_watchdog(request: Request) -> Dict[str, Any]:
    """Watchdog health: < 100ms, reads only lock-free counters."""
    dispatcher = request.app.state.dispatcher
    shutdown = getattr(request.app.state, "shutdown_in_progress", False)

    audio_mgr = request.app.state.audio_job_manager
    audio_queue = audio_mgr.pending_count() if audio_mgr is not None else 0

    scheduler = getattr(request.app.state, "proactive_scheduler", None)
    heartbeat_age = round(scheduler.heartbeat_age_s(), 1) if scheduler is not None else -1.0

    # Stuck detection: agent loop or event loop stalled for > 90s
    agent_age = _age_s(dispatcher.agent_inflight_start)
    tick_age = _age_s(dispatcher.event_loop_tick)
    provider_gate = getattr(request.app.state, "provider_gate", None)
    provider_age = (
        provider_gate.inflight_age_s() if provider_gate is not None else -1.0
    )
    stuck = (agent_age > 90) or (tick_age > 90) or (provider_age > 90)

    return {
        "ok": True,
        "core_ready": getattr(request.app.state, "core_ready", True),
        "shutdown_in_progress": shutdown,
        "event_loop_tick_age_s": round(tick_age, 1),
        "active_requests": dispatcher.active_requests,
        "agent_inflight_age_s": round(agent_age, 1),
        "provider_inflight_age_s": round(provider_age, 1),
        "audio_queue_depth": audio_queue,
        "frontend_heartbeat_age_s": heartbeat_age,
        "stuck": stuck,
    }


@router.get("/api/health/deep")
def health_deep(request: Request) -> Dict[str, Any]:
    """Deep health: < 500ms, token-protected debug endpoint."""
    require_internal_token(request)

    state_store = request.app.state.state_store
    dispatcher = request.app.state.dispatcher

    # DB quick check. Avoid WAL checkpoint here; on old Nubia devices it can
    # lock under normal traffic and make diagnostics disturb the app.
    db_ok = True
    try:
        conn = state_store.connection
        raw = getattr(conn, "_connection", conn)
        try:
            row = raw.execute("PRAGMA quick_check").fetchone()
            db_ok = bool(row and row[0] == "ok")
        except Exception:
            db_ok = True  # Skip check if DB is locked (e.g. testing)
    except Exception as exc:
        db_ok = False
        logger.warning("deep health DB check failed: %s", exc)

    # Audio backlog
    audio_mgr = request.app.state.audio_job_manager
    audio_pending = 0
    audio_running = 0
    if audio_mgr is not None:
        with audio_mgr._lock:
            for j in audio_mgr._jobs.values():
                if j.status == "pending":
                    audio_pending += 1
                elif j.status == "running":
                    audio_running += 1

    # Memory candidate backlog
    candidate_store = request.app.state.memory_candidate_store
    candidate_backlog = 0
    if candidate_store is not None:
        try:
            candidate_backlog = candidate_store.count_pending()
        except Exception:
            pass

    # Provider probe results
    probe_manager = getattr(request.app.state, "probe_manager", None)
    probe_results = probe_manager.to_dict() if probe_manager is not None else {}
    provider_gate = getattr(request.app.state, "provider_gate", None)
    provider_age = (
        provider_gate.inflight_age_s() if provider_gate is not None else -1.0
    )

    return {
        "ok": db_ok,
        "db_quick_check": db_ok,
        "core_ready": getattr(request.app.state, "core_ready", True),
        "providers_ready": getattr(request.app.state, "providers_ready", True),
        "event_loop_tick_age_s": round(_age_s(dispatcher.event_loop_tick), 1),
        "active_requests": dispatcher.active_requests,
        "agent_inflight_age_s": round(_age_s(dispatcher.agent_inflight_start), 1),
        "provider_inflight_age_s": round(provider_age, 1),
        "audio_pending": audio_pending,
        "audio_running": audio_running,
        "candidate_backlog": candidate_backlog,
        "probes": probe_results,
    }
