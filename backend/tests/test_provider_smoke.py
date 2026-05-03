import os

import pytest

from app.config import load_settings
from app.pet.guard import guard_action
from app.providers.llm_mimo import MiMoLLMProvider
from app.providers.tts_mimo import MiMoTTSProvider


pytestmark = pytest.mark.smoke


def test_mimo_llm_smoke_returns_guarded_pet_action():
    settings = load_settings()
    if not settings.api_key:
        pytest.skip("MIMO_API_KEY is not configured")

    provider = MiMoLLMProvider(settings)
    raw_action = provider.complete_json(
        [
            {
                "role": "system",
                "content": "只输出 JSON。reply 短一点，mood 必须是 happy。",
            },
            {
                "role": "user",
                "content": '{"event":"pet_head","pet_state":{"mood":"idle"}}',
            },
        ]
    )
    action = guard_action(raw_action)

    assert action.reply
    assert action.mood in {
        "idle",
        "happy",
        "sad",
        "sleepy",
        "angry",
        "shy",
        "thinking",
        "concerned",
        "excited",
        "lonely",
    }


def test_mimo_tts_smoke_generates_audio():
    settings = load_settings()
    if not settings.api_key:
        pytest.skip("MIMO_API_KEY is not configured")

    provider = MiMoTTSProvider(settings)
    url = provider.synthesize("嘿嘿，Momo 轻轻冒个泡。")

    assert url is not None
    path = settings.project_root / url.lstrip("/")
    if not path.exists():
        path = settings.project_root / "backend" / url.lstrip("/")
    assert path.exists()
    assert os.path.getsize(str(path)) > 1024
