from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.voice_debug import append_voice_debug, probe_audio_file

router = APIRouter(prefix="/api/voice")

ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/wav", "audio/mpeg", "audio/mp4"}
MAX_AUDIO_BYTES = 8 * 1024 * 1024


def _extension_for_content_type(content_type: str) -> str:
    if content_type == "audio/wav":
        return "wav"
    if content_type == "audio/mpeg":
        return "mp3"
    if content_type == "audio/mp4":
        return "mp4"
    return "webm"


async def _save_upload(upload_dir: Path, file: UploadFile) -> Path:
    content_type = file.content_type or ""
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio content type: %s" % (content_type or "unknown"),
        )
    data = await file.read()
    if len(data) > MAX_AUDIO_BYTES:
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
async def post_voice_chat(request: Request, file: UploadFile = File(...)):
    settings = request.app.state.settings
    path = await _save_upload(settings.upload_dir, file)
    append_voice_debug(
        settings.data_dir,
        "upload_received",
        {
            "filename": path.name,
            "content_type": file.content_type or "",
            "size_bytes": path.stat().st_size,
            "audio_probe": probe_audio_file(path, file.content_type or ""),
        },
    )
    understanding = request.app.state.audio_provider.understand(
        path, file.content_type or ""
    )
    payload = {
        "user_text": understanding.user_text,
        "audio_understanding": understanding.dict(),
    }
    response = request.app.state.dispatcher.handle_event(
        {"type": "voice_message", "source": "voice", "payload": payload}
    )
    body: Dict[str, Any] = response.dict()
    body["user_text"] = understanding.user_text
    body["audio_understanding"] = understanding.dict()
    return body
