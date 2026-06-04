from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.auth import is_loopback, require_internal_token

router = APIRouter(prefix="/api/runtime")


@router.get("/health")
def runtime_health(request: Request):
    settings = request.app.state.settings
    return {"ok": True, "runtime": settings.runtime_name, "pet": settings.pet_name}


@router.get("/skills")
def runtime_skills(request: Request):
    require_internal_token(request)
    return {"skills": request.app.state.registry.list_skills()}


class SiliconFlowConfigRequest(BaseModel):
    api_key: str
    base_url: str = ""


class TTSConfigRequest(BaseModel):
    mode: str


class RuntimeRestartRequest(BaseModel):
    confirm: str


def _require_local_management(request: Request) -> None:
    if is_loopback(request):
        return
    require_internal_token(request)
    raise HTTPException(status_code=403, detail="Provider config changes require loopback")


def _clean_base_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail={"error": "base_url must be an https URL", "error_class": "invalid_base_url"},
        )
    return raw


def _read_env_lines(path: Path) -> tuple[Dict[str, str], list[str]]:
    existing: Dict[str, str] = {}
    order = []
    if not path.exists():
        return existing, order
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.lstrip().startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        existing[key] = value
        order.append(key)
    return existing, order


def _write_env_values(path: Path, values: Dict[str, str]) -> None:
    existing, order = _read_env_lines(path)
    for key, value in values.items():
        existing[key] = value
        if key not in order:
            order.append(key)
    path.write_text(
        "".join("%s=%s\n" % (key, existing.get(key, "")) for key in order),
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _update_provider_config(config, *, api_key: str, base_url: str):
    if config is None:
        return None
    if str(getattr(config, "api_key_env", "")) != "SILICONFLOW_API_KEY":
        return config
    next_base_url = base_url or config.base_url
    return replace(config, api_key=api_key, base_url=next_base_url)


def _update_llm_provider(provider, *, api_key: str, base_url: str) -> None:
    if provider is None:
        return
    provider_config = getattr(provider, "provider_config", None)
    if provider_config is not None and str(provider_config.api_key_env) == "SILICONFLOW_API_KEY":
        provider.provider_config = _update_provider_config(
            provider_config,
            api_key=api_key,
            base_url=base_url,
        )
    _update_llm_provider(getattr(provider, "primary", None), api_key=api_key, base_url=base_url)
    _update_llm_provider(getattr(provider, "fallback", None), api_key=api_key, base_url=base_url)


def _update_asr_provider(provider, *, api_key: str, base_url: str) -> None:
    if provider is None:
        return
    config = getattr(provider, "config", None)
    if config is not None:
        provider.config = _update_provider_config(config, api_key=api_key, base_url=base_url)
    _update_asr_provider(getattr(provider, "primary", None), api_key=api_key, base_url=base_url)
    _update_asr_provider(getattr(provider, "fallback", None), api_key=api_key, base_url=base_url)


def _update_tts_provider(provider, settings, *, api_key: str) -> None:
    if provider is None:
        return
    providers = getattr(provider, "providers", None)
    if isinstance(providers, dict):
        for candidate in providers.values():
            _update_tts_provider(candidate, settings, api_key=api_key)
    for attr in ("primary", "fallback"):
        _update_tts_provider(getattr(provider, attr, None), settings, api_key=api_key)
    candidate_settings = getattr(provider, "settings", None)
    if (
        candidate_settings is not None
        and candidate_settings.tts.api_key_env == "SILICONFLOW_API_KEY"
    ):
        candidate_settings.tts = settings.tts
        candidate_settings.api_key = api_key


def _apply_provider_runtime_config(request: Request, *, api_key: str, base_url: str) -> None:
    settings = request.app.state.settings
    settings.llm = _update_provider_config(settings.llm, api_key=api_key, base_url=base_url)
    settings.llm_fast = _update_provider_config(settings.llm_fast, api_key=api_key, base_url=base_url)
    settings.tts = _update_provider_config(settings.tts, api_key=api_key, base_url=base_url)
    settings.asr = _update_provider_config(settings.asr, api_key=api_key, base_url=base_url)
    settings.api_key = api_key

    for provider in (
        getattr(getattr(request.app.state, "fast_brain", None), "provider", None),
        getattr(getattr(request.app.state.dispatcher, "brain", None), "provider", None),
    ):
        _update_llm_provider(provider, api_key=api_key, base_url=base_url)

    asr_provider = getattr(request.app.state, "asr_provider", None)
    _update_asr_provider(asr_provider, api_key=api_key, base_url=base_url)
    request.app.state.voice_pipeline.asr_provider = asr_provider

    tts_provider = getattr(request.app.state.audio_job_manager, "tts_provider", None)
    _update_tts_provider(tts_provider, settings, api_key=api_key)


@router.get("/provider-config/siliconflow")
def siliconflow_config_status(request: Request):
    _require_local_management(request)
    settings = request.app.state.settings
    env_values, _ = _read_env_lines(settings.project_root / ".env")
    base_url = (
        env_values.get("SILICONFLOW_BASE_URL")
        or getattr(settings.llm_fast, "base_url", "")
        or getattr(settings.llm, "base_url", "")
        or "https://api.siliconflow.cn/v1"
    )
    return {
        "ok": True,
        "provider": "siliconflow",
        "api_key_configured": bool(
            env_values.get("SILICONFLOW_API_KEY")
            or getattr(settings.llm_fast, "api_key", "")
            or getattr(settings.llm, "api_key", "")
        ),
        "base_url": base_url,
    }


@router.post("/provider-config/siliconflow")
def update_siliconflow_config(payload: SiliconFlowConfigRequest, request: Request):
    _require_local_management(request)
    api_key = payload.api_key.strip()
    if len(api_key) < 12:
        raise HTTPException(
            status_code=400,
            detail={"error": "api_key is too short", "error_class": "invalid_api_key"},
        )
    base_url = _clean_base_url(payload.base_url)
    settings = request.app.state.settings
    env_values = {"SILICONFLOW_API_KEY": api_key}
    if base_url:
        env_values["SILICONFLOW_BASE_URL"] = base_url
        env_values["ASR_BASE_URL"] = base_url
    _write_env_values(settings.project_root / ".env", env_values)
    _apply_provider_runtime_config(request, api_key=api_key, base_url=base_url)
    return {
        "ok": True,
        "provider": "siliconflow",
        "api_key_configured": True,
        "base_url": base_url or getattr(settings.llm_fast, "base_url", "") or settings.llm.base_url,
    }


def _tts_config_status(request: Request):
    provider = getattr(request.app.state.audio_job_manager, "tts_provider", None)
    if hasattr(provider, "status"):
        body = provider.status()
    else:
        body = {
            "ok": True,
            "mode": getattr(request.app.state.settings, "tts_mode", "siliconflow"),
            "active_provider": str(getattr(provider, "name", "tts")),
            "options": [],
            "configured": provider is not None,
            "last_primary_error": None,
        }
    body.setdefault("mode", getattr(request.app.state.settings, "tts_mode", "siliconflow"))
    body.setdefault("active_provider", str(getattr(provider, "name", "tts")))
    body.setdefault("options", [])
    body.setdefault("configured", provider is not None)
    body.setdefault("last_primary_error", None)
    body["ok"] = True
    return body


@router.get("/tts-config")
def tts_config_status(request: Request):
    _require_local_management(request)
    return _tts_config_status(request)


@router.post("/tts-config")
def update_tts_config(payload: TTSConfigRequest, request: Request):
    _require_local_management(request)
    mode = str(payload.mode or "").strip().lower()
    if mode not in {"siliconflow", "mimo", "weilin"}:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid TTS mode", "error_class": "invalid_tts_mode"},
        )
    provider = getattr(request.app.state.audio_job_manager, "tts_provider", None)
    if not hasattr(provider, "set_mode"):
        raise HTTPException(
            status_code=400,
            detail={"error": "TTS provider is not switchable", "error_class": "tts_not_switchable"},
        )
    try:
        provider.set_mode(mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": str(exc), "error_class": "tts_mode_not_configured"},
        ) from exc
    request.app.state.settings.tts_mode = mode
    _write_env_values(request.app.state.settings.project_root / ".env", {"PETAGENT_TTS_MODE": mode})
    return _tts_config_status(request)


def _restart_runtime_later(project_root: Path) -> None:
    time.sleep(0.8)
    env = os.environ.copy()
    env.setdefault("HOST", "0.0.0.0")
    env.setdefault("PORT", "8000")
    subprocess.Popen(
        ["sh", "-c", "sh scripts/stop.sh; sh scripts/start.sh"],
        cwd=str(project_root),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _schedule_runtime_restart(project_root: Path) -> None:
    threading.Thread(
        target=_restart_runtime_later,
        args=(project_root,),
        name="petagent-runtime-restart",
        daemon=True,
    ).start()


@router.post("/restart")
def restart_runtime(payload: RuntimeRestartRequest, request: Request):
    _require_local_management(request)
    if payload.confirm != "重启后端":
        raise HTTPException(
            status_code=400,
            detail={"error": "confirmation required", "error_class": "restart_confirmation_required"},
        )
    project_root = request.app.state.settings.project_root
    if not (project_root / "scripts" / "stop.sh").exists() or not (project_root / "scripts" / "start.sh").exists():
        raise HTTPException(
            status_code=500,
            detail={"error": "restart scripts are missing", "error_class": "restart_scripts_missing"},
        )
    _schedule_runtime_restart(project_root)
    return {
        "ok": True,
        "accepted": True,
        "message": "PetAgent runtime restart scheduled",
    }
