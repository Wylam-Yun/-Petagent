"""Public client configuration endpoint (STAB-016).

Returns frontend-safe config values. No provider keys, proxy, DB, or incident data.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/runtime")


@router.get("/client-config")
def client_config(request: Request) -> Dict[str, Any]:
    """Public config for frontend. Safe to expose to any client."""
    settings = request.app.state.settings

    # Audio wait timeout: primary TTS timeout + fallback TTS timeout + buffer
    tts_timeout = int(settings.app_config.get("tts", {}).get("timeout_seconds", 30))
    fallback_timeout = tts_timeout  # fallback uses same timeout
    audio_wait_ms = (tts_timeout + fallback_timeout + 10) * 1000  # +10s buffer

    # Progressive copy thresholds (ms → message)
    audio_progressive = {
        "0": "Momo 准备声音…",
        "5000": "Momo 有点慢，再等一下…",
        "30000": "声音可能要再等一会儿…",
    }

    return {
        "audio_wait_ms": audio_wait_ms,
        "audio_progressive": audio_progressive,
        "pet_name": settings.pet_name,
    }
