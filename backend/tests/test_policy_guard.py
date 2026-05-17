from __future__ import annotations

import pytest

from app.runtime.policy_guard import PolicyGuard
from app.runtime.registry import SkillRegistry
from app.skills.base import SkillResult


def _registry():
    return SkillRegistry()


def test_validate_skill_plan_rejects_unknown_id():
    guard = PolicyGuard()
    registry = _registry()
    requests = [{"skill_id": "nonexistent.skill", "payload": {}}]
    assert guard.validate_skill_plan(requests, registry) == []


def test_validate_skill_plan_accepts_known_id():
    guard = PolicyGuard()
    registry = _registry()
    requests = [{"skill_id": "weather.current", "payload": {"location": "current"}}]
    result = guard.validate_skill_plan(requests, registry)
    assert len(result) == 1
    assert result[0][0] == "weather.current"


def test_validate_skill_plan_rejects_non_dict_item():
    guard = PolicyGuard()
    registry = _registry()
    requests = ["not_a_dict", 42]
    assert guard.validate_skill_plan(requests, registry) == []


def test_validate_skill_plan_normalizes_missing_payload():
    guard = PolicyGuard()
    registry = _registry()
    requests = [{"skill_id": "weather.current"}]
    result = guard.validate_skill_plan(requests, registry)
    assert len(result) == 1
    assert result[0][1] == {}


def test_validate_skill_payload_rejects_oversized():
    guard = PolicyGuard()
    registry = _registry()
    big_payload = {"location": "x" * 2000}
    with pytest.raises(ValueError, match="too large"):
        guard.validate_skill_payload("weather.current", big_payload, registry)


def test_validate_skill_payload_allows_optional_weather_location():
    guard = PolicyGuard()
    registry = _registry()
    assert guard.validate_skill_payload("weather.current", {}, registry) == {}


def test_validate_skill_payload_accepts_valid():
    guard = PolicyGuard()
    registry = _registry()
    payload = {"location": "Beijing"}
    result = guard.validate_skill_payload("weather.current", payload, registry)
    assert result == {"location": "Beijing"}


def test_sanitize_skill_result_truncates_long_content():
    guard = PolicyGuard()
    result = SkillResult(
        skill_id="test", ok=True, content="a" * 10000,
    )
    sanitized = guard.sanitize_skill_result(result)
    assert len(sanitized.content) <= guard.MAX_RESULT_CONTENT + 3  # +3 for "..."
    assert sanitized.content.endswith("...")


def test_sanitize_skill_result_preserves_short_content():
    guard = PolicyGuard()
    result = SkillResult(skill_id="test", ok=True, content="short")
    assert guard.sanitize_skill_result(result).content == "short"


def test_filter_memory_candidate_rejects_api_keys():
    guard = PolicyGuard()
    assert guard.filter_memory_candidate("my key is sk-abc123") is None
    assert guard.filter_memory_candidate("token=xyz") is None
    assert guard.filter_memory_candidate("Bearer eyJhbGci") is None
    assert guard.filter_memory_candidate("AKIAIOSFODNN7EXAMPLE") is None


def test_filter_memory_candidate_accepts_normal_text():
    guard = PolicyGuard()
    text = "用户喜欢晴天出门"
    assert guard.filter_memory_candidate(text) == text


def test_validate_permission_rejects_unknown():
    guard = PolicyGuard()
    assert guard.validate_permission("shell") is False
    assert guard.validate_permission("admin") is False
    assert guard.validate_permission("filesystem") is False


def test_validate_permission_accepts_known():
    guard = PolicyGuard()
    assert guard.validate_permission("device") is True
    assert guard.validate_permission("network") is True


def test_build_skill_catalog_lists_enabled_skills():
    guard = PolicyGuard()
    registry = _registry()
    catalog = guard.build_skill_catalog(registry)
    assert "weather.current" in catalog
    assert "device.info" in catalog


def test_build_skill_catalog_empty_when_no_skills():
    guard = PolicyGuard()
    registry = SkillRegistry.__new__(SkillRegistry)
    registry._skills = {}
    assert guard.build_skill_catalog(registry) == ""
