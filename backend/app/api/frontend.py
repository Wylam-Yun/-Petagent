"""Frontend heartbeat endpoint."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/frontend")


class HeartbeatRequest(BaseModel):
    user_agent: str = ""


@router.post("/heartbeat")
async def post_heartbeat(payload: HeartbeatRequest, request: Request) -> Dict[str, Any]:
    """Record frontend heartbeat. Called every 30s by the browser."""
    user_agent_hash = hashlib.md5(payload.user_agent.encode()).hexdigest()[:8] if payload.user_agent else ""

    scheduler = getattr(request.app.state, "proactive_scheduler", None)
    if scheduler is not None:
        scheduler.record_heartbeat(user_agent_hash)

    return {
        "ok": True,
        "received_at": datetime.utcnow().isoformat(),
    }
