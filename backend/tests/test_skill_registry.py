from types import SimpleNamespace

from app.runtime.registry import SkillRegistry
from app.skills.base import SkillManifest


def test_empty_skill_registry_returns_empty_list():
    registry = SkillRegistry()

    assert {skill["id"] for skill in registry.list_skills()} == {
        "device.info",
        "weather.current",
    }


def test_skill_registry_returns_structured_timeout():
    class SlowSkill:
        manifest = SkillManifest(
            id="slow.skill",
            name="Slow Skill",
            version="0.1.0",
            description="slow",
            permissions=[],
            timeout_ms=1,
        )

        def run(self, payload, context):
            import time

            time.sleep(0.2)

    registry = SkillRegistry()
    registry._skills["slow.skill"] = SlowSkill()

    result = registry.run_skill("slow.skill", {})

    assert result.ok is False
    assert result.error == "skill timeout"


def test_skill_registry_respects_enabled_config_and_timeout():
    settings = SimpleNamespace(
        skills_config={
            "skills": [
                {
                    "id": "device.info",
                    "enabled": False,
                    "permissions": ["device"],
                },
                {
                    "id": "weather.current",
                    "enabled": True,
                    "permissions": ["network", "device"],
                    "timeout_ms": 6000,
                    "config": {"mock_weather": {"content": "晴", "confidence": 0.8}},
                },
            ],
            "limits": {"timeout_ms": 3000},
        }
    )

    registry = SkillRegistry(settings=settings)
    listed = registry.list_skills()

    assert [skill["id"] for skill in listed] == ["weather.current"]
    assert listed[0]["permissions"] == ["network"]
    assert listed[0]["timeout_ms"] == 3000
