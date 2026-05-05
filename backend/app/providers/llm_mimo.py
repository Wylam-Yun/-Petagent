from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Protocol

import requests

from app.config import ProviderConfig, Settings


class LLMProvider(Protocol):
    def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        ...


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.S)
    if fenced:
        return fenced.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        return stripped[start : end + 1]
    return stripped


class MockLLMProvider:
    def __init__(self, name: str = "mock_llm") -> None:
        self.name = name

    def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        return {
            "reply": "嘿嘿，Momo 在呢。",
            "mood": "happy",
            "face_type": "happy",
            "animation": "bounce",
            "voice_style": "happy",
            "vibration": "light",
            "intent": "affection_response",
            "autonomy_notes": "mock provider response",
            "state_delta": {
                "energy": 0,
                "intimacy": 0,
                "hunger": 0,
                "loneliness": -1,
                "sleepiness": 0,
            },
            "memory_update": {"should_save": False, "content": ""},
        }


class MiMoLLMProvider:
    def __init__(
        self, settings: Settings, provider_config: ProviderConfig = None
    ) -> None:
        self.settings = settings
        self.provider_config = provider_config or settings.llm
        self.name = self.provider_config.name

    def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        api_key = self.provider_config.api_key or self.settings.api_key
        if not api_key:
            raise RuntimeError("%s is not configured" % self.provider_config.api_key_env)
        if not self.provider_config.base_url:
            raise RuntimeError("MIMO_BASE_URL is not configured")

        payload = {
            "model": self.provider_config.model,
            "messages": messages,
            "temperature": self.provider_config.extra.get("temperature", 0.8),
        }
        for key in (
            "chat_template_kwargs",
            "max_tokens",
            "top_p",
            "response_format",
        ):
            if key in self.provider_config.extra:
                payload[key] = self.provider_config.extra[key]

        response = requests.post(
            self.provider_config.base_url.rstrip("/") + "/chat/completions",
            headers={
                "api-key": api_key,
                "content-type": "application/json",
            },
            json=payload,
            timeout=self.provider_config.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, dict):
            return content
        return json.loads(_extract_json_text(str(content)))
