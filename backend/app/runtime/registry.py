from __future__ import annotations

import concurrent.futures
from dataclasses import asdict
from typing import Any, Dict, List

import requests

from app.skills.base import SkillContext, SkillResult
from app.skills.builtin.device_info import DeviceInfoSkill
from app.skills.builtin.weather import CurrentWeatherSkill


BUILTIN_SKILLS = {
    "device.info": DeviceInfoSkill,
    "weather.current": CurrentWeatherSkill,
}


class SkillRegistry:
    def __init__(self, settings=None, device_store=None) -> None:
        self.settings = settings
        self.device_store = device_store
        self._skill_configs = self._configured_skills()
        self._skills = {}
        for skill_id, skill_class in BUILTIN_SKILLS.items():
            if self._skill_enabled(skill_id):
                self._skills[skill_id] = skill_class()

    def list_skills(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": skill.manifest.id,
                "name": skill.manifest.name,
                "version": skill.manifest.version,
                "description": skill.manifest.description,
                "permissions": self._effective_permissions(skill.manifest.id),
                "timeout_ms": self._effective_timeout_ms(skill.manifest.id),
                "input_schema": dict(skill.manifest.input_schema or {}),
            }
            for skill in self._skills.values()
        ]

    def max_calls_per_event(self) -> int:
        if not self.settings:
            return 2
        limits = self.settings.skills_config.get("limits") or {}
        return int(limits.get("max_skill_calls_per_event", 2))

    def has_skill(self, skill_id: str) -> bool:
        return skill_id in self._skills

    def run_skill(self, skill_id: str, payload: Dict[str, Any]) -> SkillResult:
        skill = self._skills.get(skill_id)
        if skill is None:
            raise KeyError(skill_id)
        manifest = skill.manifest
        permissions = self._effective_permissions(skill_id)
        context = SkillContext(
            device_store=self.device_store if "device" in permissions else None,
            network_client=requests.Session() if "network" in permissions else None,
            config=self._skill_config(skill_id),
        )
        timeout = max(0.1, self._effective_timeout_ms(skill_id) / 1000.0)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(skill.run, payload or {}, context)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return SkillResult(
                skill_id=skill_id,
                ok=False,
                content="",
                data={},
                confidence=0.0,
                error="skill timeout",
            )
        except Exception:
            return SkillResult(
                skill_id=skill_id,
                ok=False,
                content="",
                data={},
                confidence=0.0,
                error="skill failed",
            )
        finally:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                executor.shutdown(wait=False)

    def run_skill_dict(self, skill_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return asdict(self.run_skill(skill_id, payload))

    def _skill_config(self, skill_id: str) -> Dict[str, Any]:
        item = self._skill_configs.get(skill_id, {})
        return dict(item.get("config") or {})

    def _configured_skills(self) -> Dict[str, Dict[str, Any]]:
        if not self.settings:
            return {}
        configured = self.settings.skills_config.get("skills") or []
        if isinstance(configured, dict):
            return {
                str(skill_id): dict(value or {})
                for skill_id, value in configured.items()
                if isinstance(value, dict)
            }
        result: Dict[str, Dict[str, Any]] = {}
        for item in configured:
            if isinstance(item, dict) and item.get("id"):
                result[str(item["id"])] = dict(item)
        return result

    def _skill_enabled(self, skill_id: str) -> bool:
        if not self.settings:
            return True
        item = self._skill_configs.get(skill_id)
        if item is None:
            return False
        return bool(item.get("enabled", True))

    ALLOWED_PERMISSIONS = {"device", "network"}

    def _effective_permissions(self, skill_id: str) -> List[str]:
        skill = self._skills.get(skill_id)
        if skill is None:
            return []
        manifest_permissions = set(skill.manifest.permissions) & self.ALLOWED_PERMISSIONS
        configured = self._skill_configs.get(skill_id, {}).get("permissions")
        if configured is None:
            return sorted(manifest_permissions)
        requested = {str(item) for item in configured}
        return sorted(manifest_permissions.intersection(requested))

    def _effective_timeout_ms(self, skill_id: str) -> int:
        skill = self._skills.get(skill_id)
        if skill is None:
            return 3000
        global_timeout = int(
            (self.settings.skills_config.get("limits") or {}).get("timeout_ms", 0)
            if self.settings
            else 0
        )
        item_timeout = int(self._skill_configs.get(skill_id, {}).get("timeout_ms", 0) or 0)
        candidates = [
            value
            for value in (item_timeout, global_timeout, skill.manifest.timeout_ms)
            if value > 0
        ]
        return min(candidates) if candidates else skill.manifest.timeout_ms
