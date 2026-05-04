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
