from __future__ import annotations

import json
import math
import subprocess
import wave
from array import array
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


DEFAULT_MAX_LINES = 200


def audio_probe(path: Path, content_type: str) -> Dict[str, Any]:
    probe: Dict[str, Any] = {
        "content_type": content_type,
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }
    if not path.exists():
        probe["error"] = "audio_missing"
        return probe

    if content_type == "audio/wav" or path.suffix.lower() == ".wav":
        probe.update(_wav_probe(path))
    else:
        probe.update(_ffprobe_probe(path))
    return probe


def write_voice_debug(
    log_path: Path,
    *,
    audio_path: Path,
    content_type: str,
    route_info: Dict[str, Any],
    user_text: str,
    error_class: Optional[str],
    ok: bool,
    max_lines: int = DEFAULT_MAX_LINES,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "event": "voice_chat",
        "ok": ok,
        "filename": audio_path.name,
        "audio_probe": audio_probe(audio_path, content_type),
        "user_text": user_text,
        "error_class": error_class,
        "voice_route": route_info,
    }
    lines = _tail_lines(log_path, max_lines - 1)
    lines.append(json.dumps(entry, ensure_ascii=False, sort_keys=True))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _wav_probe(path: Path) -> Dict[str, Any]:
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frames = handle.getnframes()
            raw = handle.readframes(frames)
    except Exception as exc:
        return {"format": "wav", "probe_error": type(exc).__name__}

    samples = array("h")
    try:
        samples.frombytes(raw)
    except Exception as exc:
        return {"format": "wav", "probe_error": type(exc).__name__}
    if channels > 1:
        samples = samples[::channels]

    duration = frames / sample_rate if sample_rate else 0.0
    rms = math.sqrt(sum(value * value for value in samples) / len(samples)) if samples else 0.0
    max_amp = max((abs(value) for value in samples), default=0)
    leading_silence_s = _leading_silence(samples, sample_rate)
    return {
        "format": "wav",
        "duration_s": round(duration, 3),
        "sample_rate": sample_rate,
        "channels": channels,
        "sample_width": sample_width,
        "rms": round(rms, 1),
        "max_amp": max_amp,
        "leading_silence_s": round(leading_silence_s, 3),
    }


def _ffprobe_probe(path: Path) -> Dict[str, Any]:
    body: Dict[str, Any] = {"format": path.suffix.lower().lstrip(".") or "unknown"}
    try:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stderr=subprocess.DEVNULL,
            timeout=3,
            text=True,
        ).strip()
        if output:
            body["duration_s"] = round(float(output), 3)
    except Exception:
        pass
    return body


def _leading_silence(samples: Iterable[int], sample_rate: int, threshold: int = 200) -> float:
    if not sample_rate:
        return 0.0
    count = 0
    for value in samples:
        if abs(value) >= threshold:
            break
        count += 1
    return count / sample_rate


def _tail_lines(path: Path, max_lines: int) -> list[str]:
    if max_lines <= 0 or not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return lines[-max_lines:]
