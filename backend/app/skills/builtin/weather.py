from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote

from app.skills.base import SkillContext, SkillManifest, SkillResult


class CurrentWeatherSkill:
    manifest = SkillManifest(
        id="weather.current",
        name="Current Weather",
        version="0.1.0",
        description="获取当前位置或指定城市的当前天气。",
        permissions=["network"],
        timeout_ms=8000,
        input_schema={"location": "string"},
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
        if context.network_client is None:
            return self._failure("weather network permission unavailable")
        provider = str(config.get("provider") or "wttr_in")
        if provider != "wttr_in":
            return self._failure("weather provider unavailable")
        try:
            return self._run_wttr(payload, config, context.network_client)
        except Exception:
            return self._failure("weather provider unavailable")

    def _run_wttr(
        self, payload: Dict[str, Any], config: Dict[str, Any], network_client
    ) -> SkillResult:
        location = str(
            payload.get("location") or config.get("default_location") or "current"
        ).strip()
        endpoint = str(config.get("endpoint") or "https://wttr.in").rstrip("/")
        timeout = float(config.get("timeout_seconds") or 5)
        if not location or location == "current":
            url = endpoint + "/"
        else:
            url = endpoint + "/" + quote(location)
        response = network_client.get(url, params={"format": "j1"}, timeout=timeout)
        response.raise_for_status()
        body = response.json()
        current = (body.get("current_condition") or [{}])[0]
        temp = current.get("temp_C")
        feels_like = current.get("FeelsLikeC")
        humidity = current.get("humidity")
        wind = current.get("windspeedKmph")
        condition = self._condition_text(current)
        content = "当前%s，约 %s 度。" % (condition, temp or "未知")
        data = {
            "provider": "wttr_in",
            "location": location,
            "condition": condition,
            "temperature_c": self._int_or_none(temp),
            "feels_like_c": self._int_or_none(feels_like),
            "humidity": self._int_or_none(humidity),
            "wind_kmph": self._int_or_none(wind),
        }
        return SkillResult(
            skill_id=self.manifest.id,
            ok=True,
            content=content,
            data=data,
            confidence=0.82,
            error=None,
        )

    def _condition_text(self, current: Dict[str, Any]) -> str:
        for key in ("lang_zh", "lang_zh-CN", "weatherDesc"):
            values = current.get(key)
            if isinstance(values, list) and values:
                value = values[0].get("value") if isinstance(values[0], dict) else values[0]
                if value:
                    return str(value)
        return "天气信息可用"

    def _int_or_none(self, value: Any):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _failure(self, error: str) -> SkillResult:
        return SkillResult(
            skill_id=self.manifest.id,
            ok=False,
            content="",
            data={},
            confidence=0.0,
            error=error,
        )
