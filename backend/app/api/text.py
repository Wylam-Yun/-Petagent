from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

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
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text message is empty")
    if len(text) > _max_text_chars(request):
        raise HTTPException(status_code=413, detail="Text message is too long")
    started = datetime.utcnow()
    request.app.state.tick_service.apply_if_due()
    result = await run_in_threadpool(
        request.app.state.text_pipeline.handle,
        text,
        thinking_mode=payload.thinking_mode,
    )
    body: Dict[str, Any] = result.response.dict()
    body["user_text"] = result.user_text
    route_info = result.route_info.dict()
    route_info["timings_ms"].setdefault(
        "api_total",
        int((datetime.utcnow() - started).total_seconds() * 1000),
    )
    body["text_route"] = route_info
    if result.activation is not None:
        body["activation"] = result.activation
    return body
