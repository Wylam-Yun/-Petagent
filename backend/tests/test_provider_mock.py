from pathlib import Path

from app.config import ProviderConfig
from app.providers.llm_mimo import MockLLMProvider
from app.providers.llm_mimo import MiMoLLMProvider
from app.providers.tts_mimo import MockTTSProvider, build_voice_prompt
from app.pet.guard import guard_action


def test_mock_llm_provider_returns_valid_action():
    provider = MockLLMProvider()

    action = guard_action(provider.complete_json([]))

    assert action.reply
    assert action.mood == "happy"


def test_mock_llm_invalid_json_falls_back():
    action = guard_action("{broken json")

    assert action.reply == "嗯嗯，Momo 在这儿。"


def test_mimo_llm_provider_forwards_no_thinking_option(monkeypatch):
    captured = {}

    class DummySettings:
        api_key = None

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"reply":"好呀。","mood":"happy"}'
                        }
                    }
                ]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    config = ProviderConfig(
        name="mimo_fast",
        model="mimo-v2.5",
        base_url="https://mimo.example/v1",
        api_key_env="MIMO_API_KEY",
        timeout_seconds=20,
        api_key="test-key",
        extra={"chat_template_kwargs": {"enable_thinking": False}},
    )
    monkeypatch.setattr("app.providers.llm_mimo.requests.post", fake_post)

    result = MiMoLLMProvider(DummySettings(), config).complete_json([])

    assert result["reply"] == "好呀。"
    assert captured["json"]["model"] == "mimo-v2.5"
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_mock_tts_provider_returns_audio_url(tmp_path: Path):
    provider = MockTTSProvider(audio_dir=tmp_path)

    url = provider.synthesize("Momo 在呢。")

    assert url is not None
    assert url.startswith("/static/audio/")


def test_mock_tts_provider_can_return_none(tmp_path: Path):
    provider = MockTTSProvider(audio_dir=tmp_path, fail=True)

    assert provider.synthesize("Momo 在呢。") is None


def test_tts_voice_prompt_uses_speed_style():
    prompt = build_voice_prompt({"speed": "slightly_fast", "emotion": "warm"}, "happy")

    assert "语速稍快" in prompt
    assert "温暖" in prompt
    assert "开心" in prompt
