from __future__ import annotations

from typing import Any, Dict, List


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: List[Dict[str, Any]] = []

    def list_skills(self) -> List[Dict[str, Any]]:
        return list(self._skills)
