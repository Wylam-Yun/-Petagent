from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml
from dotenv import dotenv_values


@dataclass
class ProviderConfig:
    name: str
    model: str
    base_url: Optional[str]
    api_key_env: str
    timeout_seconds: int
    api_key: Optional[str] = field(default=None, repr=False)
    voice: Optional[str] = None
    audio_format: Optional[str] = None
    style: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Settings:
    project_root: Path
    config_dir: Path
    data_dir: Path
    audio_dir: Path
    upload_dir: Path
    frontend_dist: Path
    runtime_name: str
    pet_name: str
    schema_version: str
    app_config: Dict[str, Any]
    models_config: Dict[str, Any]
    persona_config: Dict[str, Any]
    skills_config: Dict[str, Any]
    ui_theme: Dict[str, Any]
    llm: ProviderConfig
    llm_fast: Optional[ProviderConfig]
    audio_understanding: ProviderConfig
    asr: Optional[ProviderConfig]
    tts: ProviderConfig
    voice_routing: Dict[str, Any]
    api_key: Optional[str] = field(default=None, repr=False)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_env(root: Path, env: Optional[Mapping[str, str]]) -> Dict[str, str]:
    if env is not None:
        return dict(env)
    values: Dict[str, str] = {}
    env_path = root / ".env"
    if env_path.exists():
        values.update(
            {
                key: value
                for key, value in dotenv_values(str(env_path)).items()
                if value is not None
            }
        )
    values.update(os.environ)
    return values


def _resolve_path(root: Path, value: Optional[str], default: str) -> Path:
    raw = value or default
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    return path


def _env_names(value: Any) -> list:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _env_name(value: Any) -> str:
    return _env_names(value)[0]


def _env_value(env_values: Mapping[str, str], value: Any) -> str:
    for name in _env_names(value):
        resolved = env_values.get(name)
        if resolved:
            return resolved
    return ""


def _provider_config(raw: Dict[str, Any], env_values: Mapping[str, str]) -> ProviderConfig:
    base_url_env = raw.get("base_url_env", "MIMO_BASE_URL")
    api_key_env = raw.get("api_key_env", "MIMO_API_KEY")
    extra: Dict[str, Any] = {}
    for key, value in raw.items():
        if key in {
            "name",
            "model",
            "base_url_env",
            "api_key_env",
            "timeout_seconds",
            "voice",
            "format",
            "style",
        }:
            continue
        if key.endswith("_env"):
            extra[key[:-4]] = _env_value(env_values, value)
        else:
            extra[key] = value
    return ProviderConfig(
        name=raw.get("name", "mimo"),
        model=raw.get("model", ""),
        base_url=_env_value(env_values, base_url_env),
        api_key_env=_env_name(api_key_env),
        timeout_seconds=int(raw.get("timeout_seconds", 60)),
        api_key=_env_value(env_values, api_key_env),
        voice=raw.get("voice"),
        audio_format=raw.get("format"),
        style=raw.get("style") or {},
        extra=extra,
    )


def load_settings(
    root: Optional[Path] = None, env: Optional[Mapping[str, str]] = None
) -> Settings:
    root_path = root or project_root()
    env_values = _load_env(root_path, env)
    config_dir = _resolve_path(
        root_path, env_values.get("PETAGENT_CONFIG_DIR"), "config"
    )

    app_config = _read_yaml(config_dir / "app.yaml")
    models_config = _read_yaml(config_dir / "models.yaml")
    persona_config = _read_yaml(config_dir / "pet_persona.yaml")
    skills_config = _read_yaml(config_dir / "skills.yaml")
    ui_theme = _read_json(config_dir / "ui_theme.json")

    paths = app_config.get("paths", {})
    data_dir = _resolve_path(
        root_path,
        env_values.get("PETAGENT_DATA_DIR") or paths.get("data_dir"),
        "backend/data",
    )
    audio_dir = _resolve_path(root_path, paths.get("audio_dir"), "backend/static/audio")
    upload_dir = _resolve_path(root_path, paths.get("upload_dir"), "backend/data/uploads")
    frontend_dist = _resolve_path(
        root_path, paths.get("frontend_dist"), "frontend/dist"
    )

    providers = models_config.get("providers", {})
    llm = _provider_config(providers.get("llm", {}), env_values)
    llm_fast_raw = providers.get("llm_fast")
    llm_fast = _provider_config(llm_fast_raw, env_values) if llm_fast_raw else None
    audio_understanding = _provider_config(
        providers.get("audio_understanding", providers.get("llm", {})), env_values
    )
    asr_raw = providers.get("asr")
    asr = _provider_config(asr_raw, env_values) if asr_raw else None
    tts = _provider_config(providers.get("tts", {}), env_values)
    api_key = env_values.get(tts.api_key_env) or env_values.get(llm.api_key_env)
    voice_routing = app_config.get("voice", {})

    runtime = app_config.get("runtime", {})
    return Settings(
        project_root=root_path,
        config_dir=config_dir,
        data_dir=data_dir,
        audio_dir=audio_dir,
        upload_dir=upload_dir,
        frontend_dist=frontend_dist,
        runtime_name=runtime.get("name", "PetAgent"),
        pet_name=runtime.get("pet_name", "Momo"),
        schema_version=runtime.get("schema_version", "0.1"),
        app_config=app_config,
        models_config=models_config,
        persona_config=persona_config,
        skills_config=skills_config,
        ui_theme=ui_theme,
        llm=llm,
        llm_fast=llm_fast,
        audio_understanding=audio_understanding,
        asr=asr,
        tts=tts,
        voice_routing=voice_routing,
        api_key=api_key,
    )
