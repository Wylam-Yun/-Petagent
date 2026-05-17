from __future__ import annotations

from typing import Any, Dict

from app.skills.base import SkillContext, SkillManifest, SkillResult


class DeviceInfoSkill:
    manifest = SkillManifest(
        id="device.info",
        name="Device Info",
        version="0.1.0",
        description="读取最近一次设备状态。",
        permissions=["device"],
        timeout_ms=1000,
        input_schema={},
    )

    def run(self, payload: Dict[str, Any], context: SkillContext) -> SkillResult:
        device = context.device_store.get_state() if context.device_store else {}
        return SkillResult(
            skill_id=self.manifest.id,
            ok=True,
            content="device state available",
            data=device,
            confidence=1.0,
            error=None,
        )
