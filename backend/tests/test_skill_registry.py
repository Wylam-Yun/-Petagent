from app.runtime.registry import SkillRegistry


def test_empty_skill_registry_returns_empty_list():
    registry = SkillRegistry()

    assert registry.list_skills() == []
