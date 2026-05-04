import wave
from pathlib import Path

from app.config import ProviderConfig
from app.providers.asr_nvidia import (
    ASRInputError,
    NvidiaParakeetASRProvider,
    inspect_wav_for_asr,
)


def write_wav(path: Path, *, sample_rate: int, channels: int = 1, sample_width: int = 2):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x02" * (sample_rate // 20))


def provider_config() -> ProviderConfig:
    return ProviderConfig(
        name="nvidia_parakeet",
        model="parakeet-ctc-0.6b-zh-cn",
        base_url="grpc.nvcf.nvidia.com:443",
        api_key_env="NVIDIA_API_KEY",
        timeout_seconds=15,
        api_key="test-key",
        extra={"function_id": "function-id", "language_code": "zh-CN"},
    )


def test_inspect_wav_for_asr_accepts_48k_mono_pcm(tmp_path: Path):
    path = tmp_path / "voice.wav"
    write_wav(path, sample_rate=48_000)

    spec = inspect_wav_for_asr(path)

    assert spec.sample_rate == 48_000
    assert spec.channels == 1
    assert spec.sample_width == 2
    assert spec.pcm_bytes


def test_inspect_wav_for_asr_rejects_stereo_input(tmp_path: Path):
    path = tmp_path / "stereo.wav"
    write_wav(path, sample_rate=44_100, channels=2)

    try:
        inspect_wav_for_asr(path)
    except ASRInputError as exc:
        assert "mono" in str(exc)
    else:
        raise AssertionError("stereo WAV should be rejected")


def test_nvidia_provider_passes_real_sample_rate_to_riva_config(tmp_path: Path):
    path = tmp_path / "voice.wav"
    write_wav(path, sample_rate=44_100)
    captured = {}

    class FakeRiva:
        class client:
            class AudioEncoding:
                LINEAR_PCM = "linear_pcm"

            class RecognitionConfig:
                def __init__(self, **kwargs):
                    captured.update(kwargs)

            class Auth:
                def __init__(self, **kwargs):
                    captured["auth"] = kwargs

            class ASRService:
                def __init__(self, auth):
                    captured["service_auth"] = auth

                def offline_recognize(self, audio, config):
                    captured["audio_len"] = len(audio)

                    class Alternative:
                        transcript = "你好默默"
                        confidence = 0.88

                    class Result:
                        alternatives = [Alternative()]

                    class Response:
                        results = [Result()]

                    return Response()

    provider = NvidiaParakeetASRProvider(provider_config(), riva_module=FakeRiva)

    transcript = provider.transcribe(path, "audio/wav")

    assert captured["sample_rate_hertz"] == 44_100
    assert captured["language_code"] == "zh-CN"
    assert transcript.text == "你好默默"
    assert transcript.confidence == 0.88
