from __future__ import annotations

from typing import Any, Dict

from app.skills.base import SkillContext, SkillManifest, SkillResult


class CurrentWeatherSkill:
    manifest = SkillManifest(
        id="weather.current",
        name="Current Weather",
        version="0.1.0",
        description="获取当前位置或指定城市的当前天气。",
        permissions=["network"],
        timeout_ms=8000,
    )

    def run(self, payload: Dict[str, Any], context: SkillContext) -> SkillResult:
        config = context.config or {}
        fallback = config.get("mock_weather")
        if fallback:
            return SkillResult(
                skill_id=self.manifest.id,
                ok=True,
                content=str(fallback.get("content", "当前天气信息可用。")),
                data=dict(fallback.get("data") or {}),
                confidence=float(fallback.get("confidence", 0.8)),
                error=None,
            )
        return SkillResult(
            skill_id=self.manifest.id,
            ok=False,
            content="",
            data={},
            confidence=0.0,
            error="weather provider unavailable",
        )
