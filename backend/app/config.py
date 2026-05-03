from __future__ import annotations

import json
import os
from dataclasses import dataclass
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
    voice: Optional[str] = None
    audio_format: Optional[str] = None
    style: Optional[Dict[str, Any]] = None


@dataclass
class Settings:
    project_root: Path
    config_dir: Path
    data_dir: Path
    audio_dir: Path
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
    tts: ProviderConfig
    api_key: Optional[str]


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


def _provider_config(raw: Dict[str, Any], env_values: Mapping[str, str]) -> ProviderConfig:
    base_url_env = raw.get("base_url_env", "MIMO_BASE_URL")
    return ProviderConfig(
        name=raw.get("name", "mimo"),
        model=raw.get("model", ""),
        base_url=env_values.get(base_url_env),
        api_key_env=raw.get("api_key_env", "MIMO_API_KEY"),
        timeout_seconds=int(raw.get("timeout_seconds", 60)),
        voice=raw.get("voice"),
        audio_format=raw.get("format"),
        style=raw.get("style") or {},
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
    frontend_dist = _resolve_path(
        root_path, paths.get("frontend_dist"), "frontend/dist"
    )

    providers = models_config.get("providers", {})
    llm = _provider_config(providers.get("llm", {}), env_values)
    tts = _provider_config(providers.get("tts", {}), env_values)
    api_key = env_values.get(tts.api_key_env) or env_values.get(llm.api_key_env)

    runtime = app_config.get("runtime", {})
    return Settings(
        project_root=root_path,
        config_dir=config_dir,
        data_dir=data_dir,
        audio_dir=audio_dir,
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
        tts=tts,
        api_key=api_key,
    )
