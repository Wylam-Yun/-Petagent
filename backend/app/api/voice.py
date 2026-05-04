from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/voice")

DEFAULT_AUDIO_TYPES = {"audio/webm", "audio/wav", "audio/mpeg", "audio/mp4"}
DEFAULT_MAX_AUDIO_BYTES = 8 * 1024 * 1024


def _extension_for_content_type(content_type: str) -> str:
    if content_type == "audio/wav":
        return "wav"
    if content_type == "audio/mpeg":
        return "mp3"
    if content_type == "audio/mp4":
        return "mp4"
    return "webm"


def allowed_audio_types(settings) -> set:
    raw = settings.voice_routing.get("allowed_audio_types") or list(DEFAULT_AUDIO_TYPES)
    return {str(item) for item in raw}


def max_audio_bytes(settings) -> int:
    return int(settings.voice_routing.get("max_audio_bytes", DEFAULT_MAX_AUDIO_BYTES))


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


async def _save_upload(settings, upload_dir: Path, file: UploadFile) -> Path:
    content_type = file.content_type or ""
    if content_type not in allowed_audio_types(settings):
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio content type: %s" % (content_type or "unknown"),
        )
    data = await file.read()
    if len(data) > max_audio_bytes(settings):
        raise HTTPException(status_code=413, detail="Audio file is too large")
    upload_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = "voice-%s-%s.%s" % (
        stamp,
        uuid4().hex[:8],
        _extension_for_content_type(content_type),
    )
    path = upload_dir / filename
    path.write_bytes(data)
    return path


@router.post("/chat")
async def post_voice_chat(
    request: Request,
    file: UploadFile = File(...),
    thinking_mode: str = Form("false"),
    route: str = Form("auto"),
):
    settings = request.app.state.settings
    started = datetime.utcnow()
    path = await _save_upload(settings, settings.upload_dir, file)
    upload_save_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    request.app.state.tick_service.apply_if_due()
    result = await run_in_threadpool(
        request.app.state.voice_pipeline.handle,
        path,
        file.content_type or "",
        requested_route=route,
        thinking_mode=_as_bool(thinking_mode),
    )
    body: Dict[str, Any] = result.response.dict()
    body["user_text"] = result.user_text
    body["audio_understanding"] = result.audio_understanding.dict()
    route_info = result.route_info.dict()
    route_info["timings_ms"] = dict(route_info.get("timings_ms", {}))
    route_info["timings_ms"].setdefault("upload_save", upload_save_ms)
    body["voice_route"] = route_info
    return body
