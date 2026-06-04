from pathlib import Path

from app.config import load_settings


def test_config_loader_reads_model_config_without_api_key(tmp_path: Path):
    root = tmp_path
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "app.yaml").write_text(
        """
runtime:
  name: PetAgent
  pet_name: 豆豆
paths:
  data_dir: backend/data
  audio_dir: backend/static/audio
""",
        encoding="utf-8",
    )
    (config_dir / "models.yaml").write_text(
        """
providers:
  llm:
    name: mimo
    model: test-llm
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 3
  tts:
    name: mimo
    model: test-tts
    voice: 冰糖
    format: wav
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 3
""",
        encoding="utf-8",
    )
    (config_dir / "pet_persona.yaml").write_text("name: 豆豆\n", encoding="utf-8")
    (config_dir / "skills.yaml").write_text("skills: []\n", encoding="utf-8")
    (config_dir / "ui_theme.json").write_text("{}", encoding="utf-8")

    settings = load_settings(root=root, env={})

    assert settings.pet_name == "豆豆"
    assert settings.llm.model == "test-llm"
    assert settings.tts.model == "test-tts"
    assert settings.tts.voice == "冰糖"
    assert settings.api_key is None


def test_config_loader_reads_fast_voice_providers_without_leaking_secrets(tmp_path: Path):
    root = tmp_path
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "app.yaml").write_text(
        """
runtime:
  name: PetAgent
  pet_name: 豆豆
voice:
  default_route: fast
  allowed_audio_types:
    - audio/wav
  max_audio_bytes: 4096
""",
        encoding="utf-8",
    )
    (config_dir / "models.yaml").write_text(
        """
providers:
  llm:
    name: mimo
    model: mimo-v2-omni
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 60
  llm_fast:
    name: mimo_v25_fast
    model: mimo-v2.5
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 20
    chat_template_kwargs:
      enable_thinking: false
  asr:
    name: configurable_http_asr
    model: TeleAI/TeleSpeechASR
    base_url_env:
      - ASR_BASE_URL
      - NVIDIA_HTTP_ASR_BASE_URL
    api_key_env:
      - ASR_API_KEY
      - NVIDIA_API_KEY
    timeout_seconds: 15
    protocol: http
    endpoint: /v1/audio/transcriptions
    language_code: zh-CN
    auth_scheme: bearer
  asr_fallback:
    name: mimo_asr
    model: mimo-v2.5-asr
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 30
    protocol: mimo_chat
    endpoint: /chat/completions
    auth_scheme: api-key
    language: auto
  tts:
    name: mimo
    model: mimo-v2.5-tts
    voice: 冰糖
    format: wav
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 120
  llm_fallback:
    name: mimo
    model: mimo-v2-omni
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 60
  llm_fast_fallback:
    name: mimo
    model: mimo-v2-omni
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 60
  memory_summarizer:
    name: mimo_memory_summarizer
    model_env: MIMO_MEMORY_MODEL
    default_model: mimo-v2.5
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 30
    max_tokens: 600
  tts_fallback:
    name: mimo
    model_env: MIMO_TTS_MODEL
    default_model: mimo-v2.5-tts
    voice_env: MIMO_TTS_VOICE
    default_voice: 冰糖
    format_env: MIMO_TTS_FORMAT
    default_format: wav
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 120
""",
        encoding="utf-8",
    )
    (config_dir / "pet_persona.yaml").write_text("name: 豆豆\n", encoding="utf-8")
    (config_dir / "skills.yaml").write_text("skills: []\n", encoding="utf-8")
    (config_dir / "ui_theme.json").write_text("{}", encoding="utf-8")

    settings = load_settings(
        root=root,
        env={
            "MIMO_BASE_URL": "https://mimo.example/v1",
            "MIMO_API_KEY": "test-mimo-secret",
            "MIMO_MEMORY_MODEL": "mimo-test-memory",
            "MIMO_TTS_MODEL": "mimo-test-tts",
            "MIMO_TTS_VOICE": "冰糖测试",
            "MIMO_TTS_FORMAT": "mp3",
            "ASR_BASE_URL": "https://api.siliconflow.cn",
            "ASR_API_KEY": "test-asr-secret",
        },
    )

    assert settings.llm_fast is not None
    assert settings.llm_fast.name == "mimo_v25_fast"
    assert settings.llm_fast.model == "mimo-v2.5"
    assert settings.llm_fast.extra["chat_template_kwargs"] == {
        "enable_thinking": False
    }
    assert settings.asr is not None
    assert settings.asr.model == "TeleAI/TeleSpeechASR"
    assert settings.asr.name == "configurable_http_asr"
    assert settings.asr.base_url == "https://api.siliconflow.cn"
    assert settings.asr.api_key == "test-asr-secret"
    assert settings.asr.extra["protocol"] == "http"
    assert settings.asr.extra["endpoint"] == "/v1/audio/transcriptions"
    assert "proxy_url" not in settings.asr.extra
    assert settings.asr_fallback is not None
    assert settings.asr_fallback.name == "mimo_asr"
    assert settings.asr_fallback.model == "mimo-v2.5-asr"
    assert settings.asr_fallback.base_url == "https://mimo.example/v1"
    assert settings.asr_fallback.api_key == "test-mimo-secret"
    assert settings.asr_fallback.extra["protocol"] == "mimo_chat"
    assert settings.asr_fallback.extra["endpoint"] == "/chat/completions"
    assert settings.asr_fallback.extra["language"] == "auto"
    assert settings.llm_fallback is not None
    assert settings.llm_fallback.model == "mimo-v2-omni"
    assert settings.llm_fast_fallback is not None
    assert settings.memory_summarizer is not None
    assert settings.memory_summarizer.name == "mimo_memory_summarizer"
    assert settings.memory_summarizer.model == "mimo-test-memory"
    assert settings.memory_summarizer.extra["max_tokens"] == 600
    assert settings.tts_fallback is not None
    assert settings.tts_fallback.model == "mimo-test-tts"
    assert settings.tts_fallback.voice == "冰糖测试"
    assert settings.tts_fallback.audio_format == "mp3"
    assert settings.tts_mode == "siliconflow"
    assert settings.voice_routing["allowed_audio_types"] == ["audio/wav"]
    assert settings.voice_routing["max_audio_bytes"] == 4096
    rendered = repr(settings)
    assert "test-mimo-secret" not in rendered
    assert "test-asr-secret" not in rendered
