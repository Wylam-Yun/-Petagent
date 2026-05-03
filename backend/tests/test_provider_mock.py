from pathlib import Path

from app.providers.llm_mimo import MockLLMProvider
from app.providers.tts_mimo import MockTTSProvider
from app.pet.guard import guard_action


def test_mock_llm_provider_returns_valid_action():
    provider = MockLLMProvider()

    action = guard_action(provider.complete_json([]))

    assert action.reply
    assert action.mood == "happy"


def test_mock_llm_invalid_json_falls_back():
    action = guard_action("{broken json")

    assert action.reply == "嗯嗯，Momo 在这儿。"


def test_mock_tts_provider_returns_audio_url(tmp_path: Path):
    provider = MockTTSProvider(audio_dir=tmp_path)

    url = provider.synthesize("Momo 在呢。")

    assert url is not None
    assert url.startswith("/static/audio/")


def test_mock_tts_provider_can_return_none(tmp_path: Path):
    provider = MockTTSProvider(audio_dir=tmp_path, fail=True)

    assert provider.synthesize("Momo 在呢。") is None
