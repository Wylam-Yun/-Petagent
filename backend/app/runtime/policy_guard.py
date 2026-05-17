from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any, Dict, List, Optional

from app.skills.base import SkillResult


class PolicyGuard:
    """Unified policy layer for the agent loop.

    Validates tool plans, payloads, results, and memory candidates.
    """

    ALLOWED_PERMISSIONS = {"device", "network"}
    MAX_PAYLOAD_SIZE = 1024
    MAX_RESULT_CONTENT = 5000
    SECRET_PATTERNS = [
        "sk-", "tp-", "nvapi-", "Bearer ", "token=",
        "github_pat_", "ghp_", "AKIA",
    ]
    _SECRET_RE = re.compile(
        "|".join(re.escape(p) for p in SECRET_PATTERNS), re.IGNORECASE
    )

    def validate_skill_plan(
        self, skill_requests: list, registry
    ) -> List[tuple]:
        """Filter LLM skill plan: skill_id must exist in registry, payload must be dict."""
        valid: List[tuple] = []
        for item in skill_requests:
            if not isinstance(item, dict):
                continue
            skill_id = str(item.get("skill_id") or "")
            payload = item.get("payload")
            if not skill_id or not registry.has_skill(skill_id):
                continue
            if not isinstance(payload, dict):
                payload = {}
            valid.append((skill_id, payload))
        return valid

    def validate_skill_payload(
        self, skill_id: str, payload: dict, registry
    ) -> dict:
        """Validate payload size and explicitly required fields.

        Returns cleaned payload. Raises ValueError if invalid.
        """
        serialized = json.dumps(payload, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > self.MAX_PAYLOAD_SIZE:
            raise ValueError(
                f"payload too large: {len(serialized.encode('utf-8'))} bytes"
            )
        # Check only explicitly required fields. A flat input_schema such as
        # {"location": "string"} documents accepted fields, but does not make
        # them mandatory; weather.current can default to the configured/current
        # location when the LLM omits location.
        skill = registry._skills.get(skill_id)
        if skill is not None:
            schema = skill.manifest.input_schema or {}
            required = schema.get("required", []) if isinstance(schema, dict) else []
            for field_name in required:
                if field_name not in payload:
                    raise ValueError(
                        f"missing required field '{field_name}' for skill {skill_id}"
                    )
        return payload

    def sanitize_skill_result(self, result: SkillResult) -> SkillResult:
        """Truncate oversized content in skill result."""
        if result.content and len(result.content) > self.MAX_RESULT_CONTENT:
            return replace(
                result, content=result.content[: self.MAX_RESULT_CONTENT] + "..."
            )
        return result

    def filter_memory_candidate(self, text: str) -> Optional[str]:
        """Reject text containing secret-like patterns. Return None if rejected."""
        if self._SECRET_RE.search(text):
            return None
        return text

    def validate_permission(self, permission: str) -> bool:
        """Check permission is in ALLOWED_PERMISSIONS."""
        return permission in self.ALLOWED_PERMISSIONS

    def build_skill_catalog(self, registry) -> str:
        """Build dynamic skill list string for prompt."""
        skills = registry.list_skills()
        if not skills:
            return ""
        return ", ".join(
            f"{s['id']}({s['description']})" for s in skills
        )
