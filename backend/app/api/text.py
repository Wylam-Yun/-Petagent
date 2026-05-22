from __future__ import annotations

import logging
from datetime import datetime
from functools import partial
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.providers.errors import ProviderError
from app.runtime.concurrency import ServerBusyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/text")

DEFAULT_MAX_TEXT_CHARS = 2000


class TextChatRequest(BaseModel):
    text: str
    thinking_mode: bool = False


def _max_text_chars(request: Request) -> int:
    config = request.app.state.settings.app_config.get("text_chat", {})
    try:
        return int(config.get("max_text_chars", DEFAULT_MAX_TEXT_CHARS))
    except (TypeError, ValueError):
        return DEFAULT_MAX_TEXT_CHARS


@router.post("/chat")
async def post_text_chat(payload: TextChatRequest, request: Request):
    if getattr(request.app.state, "shutdown_in_progress", False):
        raise HTTPException(
            status_code=503,
            detail={"error": "Server is shutting down", "reason": "shutting_down"},
        )
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text message is empty")
    if len(text) > _max_text_chars(request):
        raise HTTPException(status_code=413, detail="Text message is too long")
    started = datetime.utcnow()
    request.app.state.tick_service.apply_if_due()
    try:
        executor = request.app.state.agent_work_executor
        fn = partial(request.app.state.text_pipeline.handle, text, thinking_mode=payload.thinking_mode)
        result = await executor.submit(fn)
    except ServerBusyError:
        raise HTTPException(
            status_code=503,
            detail={"error": "Server is busy, please try again", "error_class": "server_busy"},
        )
    except ProviderError as exc:
        logger.warning("text_chat provider error: %s", exc.to_dict())
        body: Dict[str, Any] = {
            "reply": "Momo 有点累了，稍后再试试吧~",
            "mood": "tired",
            "face_type": "tired",
            "animation": "slowBlink",
            "vibration": "none",
            "pet_state": request.app.state.state_store.get_state(),
            "runtime": {},
            "error_class": exc.error_class,
        }
        return body
    body = result.response.dict()
    body["user_text"] = result.user_text
    body["error_class"] = None
    route_info = result.route_info.dict()
    route_info["timings_ms"].setdefault(
        "api_total",
        int((datetime.utcnow() - started).total_seconds() * 1000),
    )
    body["text_route"] = route_info
    if result.activation is not None:
        body["activation"] = result.activation
    return body
