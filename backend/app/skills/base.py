from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol


@dataclass
class SkillManifest:
    id: str
    name: str
    version: str
    description: str
    permissions: list
    timeout_ms: int = 3000


@dataclass
class SkillResult:
    skill_id: str
    ok: bool
    content: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    error: str = None


@dataclass
class SkillContext:
    device_store: Any = None
    network_client: Any = None
    config: Dict[str, Any] = field(default_factory=dict)


class Skill(Protocol):
    manifest: SkillManifest

    def run(self, payload: Dict[str, Any], context: SkillContext) -> SkillResult:
        ...
