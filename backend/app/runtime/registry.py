from __future__ import annotations

import concurrent.futures
from dataclasses import asdict
from typing import Any, Dict, List

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
        self._skills = {
            skill_id: skill_class() for skill_id, skill_class in BUILTIN_SKILLS.items()
        }

    def list_skills(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": skill.manifest.id,
                "name": skill.manifest.name,
                "version": skill.manifest.version,
                "description": skill.manifest.description,
                "permissions": list(skill.manifest.permissions),
                "timeout_ms": skill.manifest.timeout_ms,
            }
            for skill in self._skills.values()
        ]

    def has_skill(self, skill_id: str) -> bool:
        return skill_id in self._skills

    def run_skill(self, skill_id: str, payload: Dict[str, Any]) -> SkillResult:
        skill = self._skills.get(skill_id)
        if skill is None:
            raise KeyError(skill_id)
        manifest = skill.manifest
        context = SkillContext(
            device_store=self.device_store if "device" in manifest.permissions else None,
            network_client=object() if "network" in manifest.permissions else None,
            config=self._skill_config(skill_id),
        )
        timeout = max(0.1, manifest.timeout_ms / 1000.0)
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
            executor.shutdown(wait=False, cancel_futures=True)

    def run_skill_dict(self, skill_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return asdict(self.run_skill(skill_id, payload))

    def _skill_config(self, skill_id: str) -> Dict[str, Any]:
        if not self.settings:
            return {}
        configured = self.settings.skills_config.get("skills") or []
        if isinstance(configured, dict):
            return dict(configured.get(skill_id) or {})
        for item in configured:
            if isinstance(item, dict) and item.get("id") == skill_id:
                return dict(item.get("config") or {})
        return {}
