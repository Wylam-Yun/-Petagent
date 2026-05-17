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


def test_effective_permissions_rejects_unknown_permission():
    class ShellSkill:
        manifest = SkillManifest(
            id="shell.run",
            name="Shell",
            version="0.1.0",
            description="shell",
            permissions=["device", "shell", "admin"],
        )

        def run(self, payload, context):
            pass

    registry = SkillRegistry()
    registry._skills["shell.run"] = ShellSkill()

    skills = registry.list_skills()
    shell = [s for s in skills if s["id"] == "shell.run"][0]
    assert "device" in shell["permissions"]
    assert "shell" not in shell["permissions"]
    assert "admin" not in shell["permissions"]


def test_list_skills_includes_input_schema():
    registry = SkillRegistry()
    skills = registry.list_skills()

    weather = [s for s in skills if s["id"] == "weather.current"][0]
    assert "input_schema" in weather
    assert "location" in weather["input_schema"]

    device = [s for s in skills if s["id"] == "device.info"][0]
    assert "input_schema" in device
    assert device["input_schema"] == {}
