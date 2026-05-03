from __future__ import annotations

import json
import math
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


VOICE_DEBUG_LOG = "voice_debug.jsonl"


def append_voice_debug(data_dir: Path, event: str, payload: Dict[str, Any]) -> None:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "event": event,
        **_safe_payload(payload),
    }
    with (log_dir / VOICE_DEBUG_LOG).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def probe_audio_file(path: Path, content_type: str) -> Dict[str, Any]:
    if "wav" in content_type or path.suffix.lower() == ".wav":
        return _probe_wav(path)
    return {"format": _format_from_content_type(content_type), "size_bytes": path.stat().st_size}


def truncate_text(value: str, limit: int = 2000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def _probe_wav(path: Path) -> Dict[str, Any]:
    try:
        with wave.open(str(path), "rb") as handle:
            frame_count = handle.getnframes()
            sample_rate = handle.getframerate()
            sample_width = handle.getsampwidth()
            channel_count = handle.getnchannels()
            frames = handle.readframes(frame_count)
    except Exception as error:
        return {
            "format": "wav",
            "probe_error": error.__class__.__name__,
            "size_bytes": path.stat().st_size,
        }

    max_amplitude = 0
    rms = 0.0
    if sample_width == 2 and frame_count:
        samples = [
            int.from_bytes(frames[index : index + 2], "little", signed=True)
            for index in range(0, len(frames) - 1, 2)
        ]
        max_amplitude = max((abs(sample) for sample in samples), default=0)
        if samples:
            rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))

    return {
        "format": "wav",
        "size_bytes": path.stat().st_size,
        "sample_rate": sample_rate,
        "channels": channel_count,
        "sample_width": sample_width,
        "frame_count": frame_count,
        "duration_seconds": round(frame_count / sample_rate, 3) if sample_rate else 0,
        "max_amplitude": max_amplitude,
        "rms_amplitude": round(rms, 2),
    }


def _format_from_content_type(content_type: str) -> str:
    if "webm" in content_type:
        return "webm"
    if "mpeg" in content_type or "mp3" in content_type:
        return "mp3"
    if "mp4" in content_type or "m4a" in content_type:
        return "mp4"
    if "wav" in content_type:
        return "wav"
    return content_type or "unknown"


def _safe_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: _safe_value(value)
        for key, value in payload.items()
        if key.lower() not in {"api_key", "authorization", "audio_base64", "data"}
    }


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return truncate_text(value)
    if isinstance(value, dict):
        return _safe_payload(value)
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:20]]
    return value
