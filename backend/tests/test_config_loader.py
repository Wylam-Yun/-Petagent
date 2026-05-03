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
