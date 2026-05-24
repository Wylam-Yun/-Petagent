from pathlib import Path

from app.config import ProviderConfig
from app.providers.llm_mimo import FallbackLLMProvider
from app.providers.llm_mimo import MockLLMProvider
from app.providers.llm_mimo import MiMoLLMProvider
from app.providers.tts_mimo import (
    FallbackTTSProvider,
    MockTTSProvider,
    MiMoTTSProvider,
    build_voice_prompt,
)
from app.pet.guard import guard_action


def test_mock_llm_provider_returns_valid_action():
    provider = MockLLMProvider()

    action = guard_action(provider.complete_json([]))

    assert action.reply
    assert action.mood == "happy"


def test_mock_llm_invalid_json_falls_back():
    action = guard_action("{broken json")

    assert action.reply == "嗯嗯，豆豆在这儿。"


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


def test_llm_provider_can_use_bearer_auth_for_siliconflow(monkeypatch):
    captured = {}

    class DummySettings:
        api_key = None

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {"message": {"content": '{"reply":"好呀。","mood":"happy"}'}}
                ]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    config = ProviderConfig(
        name="siliconflow",
        model="Qwen/Qwen3-30B-A3B-Instruct-2507",
        base_url="https://api.siliconflow.cn/v1",
        api_key_env="SILICONFLOW_API_KEY",
        timeout_seconds=20,
        api_key="sf-key",
        extra={"auth_scheme": "bearer", "proxy_url": "http://127.0.0.1:7897"},
    )
    monkeypatch.setattr("app.providers.llm_mimo.requests.post", fake_post)

    result = MiMoLLMProvider(DummySettings(), config).complete_json([])

    assert result["reply"] == "好呀。"
    assert captured["headers"]["Authorization"] == "Bearer sf-key"
    assert "api-key" not in captured["headers"]
    assert captured["proxies"] == {
        "http": "http://127.0.0.1:7897",
        "https": "http://127.0.0.1:7897",
    }


def test_fallback_llm_provider_uses_secondary_only_after_primary_failure():
    class FailingProvider:
        name = "primary"

        def complete_json(self, messages):
            raise RuntimeError("primary down")

    class SecondaryProvider:
        name = "fallback"

        def __init__(self):
            self.calls = 0

        def complete_json(self, messages):
            self.calls += 1
            return {"reply": "兜底好了。", "mood": "happy"}

    secondary = SecondaryProvider()
    provider = FallbackLLMProvider(FailingProvider(), secondary)

    assert provider.complete_json([])["reply"] == "兜底好了。"
    assert secondary.calls == 1


def test_mock_tts_provider_returns_audio_url(tmp_path: Path):
    provider = MockTTSProvider(audio_dir=tmp_path)

    url = provider.synthesize("豆豆在呢。")

    assert url is not None
    assert url.startswith("/static/audio/")


def test_mock_tts_provider_can_return_none(tmp_path: Path):
    provider = MockTTSProvider(audio_dir=tmp_path, fail=True)

    assert provider.synthesize("豆豆在呢。") is None


def test_tts_voice_prompt_uses_speed_style():
    prompt = build_voice_prompt({"speed": "slightly_fast", "emotion": "warm"}, "happy")

    assert "语速稍快" in prompt
    assert "温暖" in prompt
    assert "开心" in prompt


def test_tts_provider_can_use_openai_speech_binary_response(tmp_path: Path, monkeypatch):
    captured = {}

    class DummySettings:
        api_key = None
        audio_dir = tmp_path

    class Response:
        content = b"FAKEAUDIOBYTES"

        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    settings = DummySettings()
    settings.tts = ProviderConfig(
        name="siliconflow_tts",
        model="FunAudioLLM/CosyVoice2-0.5B",
        base_url="https://api.siliconflow.cn/v1",
        api_key_env="SILICONFLOW_API_KEY",
        timeout_seconds=60,
        api_key="sf-key",
        voice="FunAudioLLM/CosyVoice2-0.5B:claire",
        audio_format="mp3",
        style={"speed": "slightly_fast", "emotion": "warm"},
        extra={
            "api_style": "openai_speech",
            "auth_scheme": "bearer",
            "proxy_url": "http://127.0.0.1:7897",
        },
    )
    monkeypatch.setattr("app.providers.tts_mimo.requests.post", fake_post)

    url = MiMoTTSProvider(settings).synthesize("豆豆在呢。", "happy")

    assert url is not None
    assert url.endswith(".mp3")
    assert (tmp_path / url.removeprefix("/static/audio/")).read_bytes() == b"FAKEAUDIOBYTES"
    assert captured["url"] == "https://api.siliconflow.cn/v1/audio/speech"
    assert captured["headers"]["Authorization"] == "Bearer sf-key"
    assert "api-key" not in captured["headers"]
    assert captured["proxies"] == {
        "http": "http://127.0.0.1:7897",
        "https": "http://127.0.0.1:7897",
    }
    assert captured["json"]["model"] == "FunAudioLLM/CosyVoice2-0.5B"
    assert captured["json"]["voice"] == "FunAudioLLM/CosyVoice2-0.5B:claire"
    assert captured["json"]["response_format"] == "mp3"
    assert "豆豆在呢。" in captured["json"]["input"]


def test_fallback_tts_provider_uses_secondary_when_primary_returns_none(tmp_path: Path):
    primary = MockTTSProvider(audio_dir=tmp_path, fail=True)
    fallback = MockTTSProvider(audio_dir=tmp_path)
    provider = FallbackTTSProvider(primary, fallback)

    url = provider.synthesize("豆豆在呢。")

    assert url is not None
    assert url.startswith("/static/audio/")
