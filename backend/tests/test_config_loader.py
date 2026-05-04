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
  pet_name: Momo
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
    (config_dir / "pet_persona.yaml").write_text("name: Momo\n", encoding="utf-8")
    (config_dir / "skills.yaml").write_text("skills: []\n", encoding="utf-8")
    (config_dir / "ui_theme.json").write_text("{}", encoding="utf-8")

    settings = load_settings(root=root, env={})

    assert settings.pet_name == "Momo"
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
  pet_name: Momo
voice:
  default_route: fast
  slow_fallback_enabled: true
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
    name: mimo_flash
    model: mimo-v2-flash
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 20
  audio_understanding:
    name: mimo
    model: mimo-v2-omni
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 60
  asr:
    name: nvidia_parakeet
    model: parakeet-ctc-0.6b-zh-cn
    base_url_env: NVIDIA_RIVA_SERVER
    api_key_env: NVIDIA_API_KEY
    timeout_seconds: 15
    function_id_env: NVIDIA_PARKEET_FUNCTION_ID
    language_code: zh-CN
  tts:
    name: mimo
    model: mimo-v2.5-tts
    voice: 冰糖
    format: wav
    base_url_env: MIMO_BASE_URL
    api_key_env: MIMO_API_KEY
    timeout_seconds: 120
""",
        encoding="utf-8",
    )
    (config_dir / "pet_persona.yaml").write_text("name: Momo\n", encoding="utf-8")
    (config_dir / "skills.yaml").write_text("skills: []\n", encoding="utf-8")
    (config_dir / "ui_theme.json").write_text("{}", encoding="utf-8")

    settings = load_settings(
        root=root,
        env={
            "MIMO_BASE_URL": "https://mimo.example/v1",
            "MIMO_API_KEY": "test-mimo-secret",
            "NVIDIA_RIVA_SERVER": "grpc.nvcf.nvidia.com:443",
            "NVIDIA_API_KEY": "test-nvidia-secret",
            "NVIDIA_PARKEET_FUNCTION_ID": "function-id",
        },
    )

    assert settings.llm_fast is not None
    assert settings.llm_fast.model == "mimo-v2-flash"
    assert settings.asr is not None
    assert settings.asr.model == "parakeet-ctc-0.6b-zh-cn"
    assert settings.asr.base_url == "grpc.nvcf.nvidia.com:443"
    assert settings.asr.extra["function_id"] == "function-id"
    assert settings.voice_routing["allowed_audio_types"] == ["audio/wav"]
    assert settings.voice_routing["max_audio_bytes"] == 4096
    rendered = repr(settings)
    assert "test-mimo-secret" not in rendered
    assert "test-nvidia-secret" not in rendered
