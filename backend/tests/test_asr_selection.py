from types import SimpleNamespace

from app.config import ProviderConfig
from app.main import _select_asr_provider
from app.providers.asr_http import HttpASRProvider


def test_select_asr_provider_uses_http_protocol_for_any_vendor_name():
    config = ProviderConfig(
        name="future_vendor",
        model="fast-zh",
        base_url="https://asr.example",
        api_key_env="ASR_API_KEY",
        timeout_seconds=15,
        api_key="test-key",
        extra={"protocol": "http"},
    )

    provider = _select_asr_provider(SimpleNamespace(asr=config), testing=False)

    assert isinstance(provider, HttpASRProvider)
