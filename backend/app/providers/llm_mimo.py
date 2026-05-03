from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Protocol

import requests

from app.config import Settings


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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if not self.settings.api_key:
            raise RuntimeError("MIMO_API_KEY is not configured")
        if not self.settings.llm.base_url:
            raise RuntimeError("MIMO_BASE_URL is not configured")

        response = requests.post(
            self.settings.llm.base_url.rstrip("/") + "/chat/completions",
            headers={
                "api-key": self.settings.api_key,
                "content-type": "application/json",
            },
            json={
                "model": self.settings.llm.model,
                "messages": messages,
                "temperature": 0.8,
            },
            timeout=self.settings.llm.timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, dict):
            return content
        return json.loads(_extract_json_text(str(content)))
