from __future__ import annotations

import logging
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.providers.errors import ProviderError
from app.runtime.concurrency import ServerBusyError
from app.runtime.voice_debug import write_voice_debug

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice")

DEFAULT_AUDIO_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/mpeg",
    "audio/ogg",
    "audio/mp4",
}
DEFAULT_MAX_AUDIO_BYTES = 8 * 1024 * 1024


def _base_content_type(content_type: str) -> str:
    return str(content_type or "").split(";", 1)[0].strip().lower()


def _extension_for_content_type(content_type: str) -> str:
    content_type = _base_content_type(content_type)
    if content_type == "audio/wav":
        return "wav"
    if content_type == "audio/mpeg":
        return "mp3"
    if content_type == "audio/ogg":
        return "ogg"
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


def _invalid_audio(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": message, "error_class": "invalid_audio"},
    )


def _is_voice_failure(body: Dict[str, Any]) -> bool:
    runtime = body.get("runtime") if isinstance(body.get("runtime"), dict) else {}
    error_class = body.get("error_class") or runtime.get("error_class")
    return bool(error_class)


def _validate_magic_bytes(path: Path, content_type: str) -> None:
    """Validate magic bytes for known audio types. Raises HTTPException on mismatch."""
    required = {
        "audio/wav": 12,
        "audio/mpeg": 3,
        "audio/ogg": 4,
        "audio/webm": 4,
    }.get(content_type)
    if required is None:
        return
    try:
        with path.open("rb") as f:
            header = f.read(required)
        if len(header) < required:
            raise _invalid_audio("File too small to be a valid audio file")
        if content_type == "audio/wav":
            if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
                raise _invalid_audio("Invalid WAV file header")
        elif content_type == "audio/mpeg":
            has_id3 = header[:3] == b"ID3"
            has_frame_sync = len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
            if not (has_id3 or has_frame_sync):
                raise _invalid_audio("Invalid MP3 file header")
        elif content_type == "audio/ogg":
            if header[:4] != b"OggS":
                raise _invalid_audio("Invalid OGG file header")
        elif content_type == "audio/webm":
            if header[:4] != b"\x1a\x45\xdf\xa3":
                raise _invalid_audio("Invalid WebM file header")
    except HTTPException:
        raise
    except OSError:
        pass  # If we can't read, let the provider handle it


async def _save_upload(settings, upload_dir: Path, file: UploadFile) -> Path:
    content_type = _base_content_type(file.content_type or "")
    if content_type not in allowed_audio_types(settings):
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio content type: %s" % (content_type or "unknown"),
        )
    upload_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = "voice-%s-%s.%s" % (
        stamp,
        uuid4().hex[:8],
        _extension_for_content_type(content_type),
    )
    path = upload_dir / filename
    limit = max_audio_bytes(settings)
    total = 0
    with path.open("wb") as out:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                out.close()
                path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Audio file is too large")
            out.write(chunk)
    try:
        _validate_magic_bytes(path, content_type)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    return path


@router.post("/chat")
async def post_voice_chat(
    request: Request,
    file: UploadFile = File(...),
    thinking_mode: str = Form("false"),
    route: str = Form("auto"),
):
    if getattr(request.app.state, "shutdown_in_progress", False):
        raise HTTPException(
            status_code=503,
            detail={"error": "Server is shutting down", "reason": "shutting_down"},
        )
    settings = request.app.state.settings
    content_type = _base_content_type(file.content_type or "")
    started = datetime.utcnow()
    path = await _save_upload(settings, settings.upload_dir, file)
    upload_save_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    request.app.state.tick_service.apply_if_due()
    try:
        executor = request.app.state.agent_work_executor
        fn = partial(
            request.app.state.voice_pipeline.handle,
            path,
            content_type,
            requested_route=route,
            thinking_mode=_as_bool(thinking_mode),
        )
        result = await executor.submit(fn)
    except ServerBusyError:
        raise HTTPException(
            status_code=503,
            detail={"error": "Server is busy, please try again", "error_class": "server_busy"},
        )
    except ProviderError as exc:
        logger.warning("voice_chat provider error: %s", exc.to_dict())
        body: Dict[str, Any] = {
            "ok": False,
            "reply": "豆豆有点累了，稍后再试试吧~",
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
    runtime = body.get("runtime") if isinstance(body.get("runtime"), dict) else {}
    error_class = runtime.get("error_class") or None
    failed = _is_voice_failure({"error_class": error_class, "runtime": runtime})
    body["ok"] = not failed
    body["user_text"] = result.user_text
    body["error_class"] = error_class
    if failed:
        body["pet_state"] = request.app.state.state_store.get_state()
    body["audio_understanding"] = result.audio_understanding.dict()
    route_info = result.route_info.dict()
    route_info["timings_ms"] = dict(route_info.get("timings_ms", {}))
    route_info["timings_ms"].setdefault("upload_save", upload_save_ms)
    body["voice_route"] = route_info
    try:
        write_voice_debug(
            settings.data_dir / "logs" / "voice_debug.jsonl",
            audio_path=path,
            content_type=content_type,
            route_info=route_info,
            user_text=result.user_text,
            error_class=error_class,
            ok=not failed,
        )
    except Exception:
        logger.debug("voice debug logging failed", exc_info=True)
    if result.activation is not None:
        body["activation"] = result.activation
    return body
