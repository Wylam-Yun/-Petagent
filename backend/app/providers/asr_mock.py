from __future__ import annotations

from pathlib import Path

from app.runtime.voice_types import ASRTranscript


class MockASRProvider:
    def __init__(self, text: str = "我回来啦", fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.name = "mock_asr"

    def transcribe(self, audio_path: Path, content_type: str) -> ASRTranscript:
        if self.fail or not audio_path.exists():
            return ASRTranscript(text="", confidence=0.0, provider=self.name)
        return ASRTranscript(text=self.text, confidence=0.9, provider=self.name)
