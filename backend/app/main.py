from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import activation as activation_api
from app.api import device as device_api
from app.api import pet as pet_api
from app.api import runtime as runtime_api
from app.api import skills as skills_api
from app.api import voice as voice_api
from app.config import Settings, load_settings
from app.db import create_state_store
from app.pet.brain import PetBrain
from app.pet.memory import InteractionLogStore, MemoryStore
from app.providers.audio_omni import (
    MiMoAudioUnderstandingProvider,
    MockAudioUnderstandingProvider,
)
from app.providers.asr_http import HttpASRProvider
from app.providers.asr_mock import MockASRProvider
from app.providers.asr_nvidia import NvidiaParakeetASRProvider
from app.providers.llm_mimo import MiMoLLMProvider, MockLLMProvider
from app.providers.proactive_rule import ProactiveRuleProvider
from app.providers.tts_mimo import MiMoTTSProvider, MockTTSProvider
from app.runtime.activation import ActivationManager
from app.runtime.dispatcher import RuntimeDispatcher
from app.runtime.device import DeviceStateStore
from app.runtime.proactive import ProactiveService
from app.runtime.registry import SkillRegistry
from app.runtime.tick import TickService
from app.runtime.voice_pipeline import VoicePipeline


def _select_llm_provider(settings: Settings, testing: bool, provider_config=None, mock_name: str = "mock_llm"):
    config = provider_config or settings.llm
    if testing or not config.api_key:
        return MockLLMProvider(mock_name)
    return MiMoLLMProvider(settings, config)


def _select_tts_provider(settings: Settings, testing: bool):
    if testing:
        return MockTTSProvider(settings.audio_dir)
    return MiMoTTSProvider(settings)


def _select_audio_provider(settings: Settings, testing: bool):
    if testing:
        return MockAudioUnderstandingProvider()
    return MiMoAudioUnderstandingProvider(settings)


def _select_asr_provider(settings: Settings, testing: bool):
    if testing or settings.asr is None:
        return MockASRProvider()
    protocol = str(settings.asr.extra.get("protocol") or "").lower()
    if protocol == "http" or settings.asr.name in {"http_asr", "nvidia_http_asr"}:
        return HttpASRProvider(settings.asr)
    return NvidiaParakeetASRProvider(settings.asr)


def create_app(testing: bool = False) -> FastAPI:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    state_store = create_state_store(settings, testing=testing)
    memory_store = MemoryStore(state_store.connection)
    interaction_log = InteractionLogStore(state_store.connection)
    device_store = DeviceStateStore(state_store.connection)
    tick_service = TickService(state_store, device_store)
    proactive_service = ProactiveService(state_store, device_store)
    registry = SkillRegistry(settings=settings, device_store=device_store)
    slow_llm_provider = _select_llm_provider(
        settings, testing, settings.llm, "mock_slow_llm"
    )
    fast_llm_provider = _select_llm_provider(
        settings, testing, settings.llm_fast or settings.llm, "mock_fast_llm"
    )
    brain = PetBrain(settings, slow_llm_provider)
    fast_brain = PetBrain(settings, fast_llm_provider)
    proactive_brain = PetBrain(settings, ProactiveRuleProvider())
    audio_provider = _select_audio_provider(settings, testing)
    asr_provider = _select_asr_provider(settings, testing)
    activation_manager = ActivationManager(settings)
    dispatcher = RuntimeDispatcher(
        state_store=state_store,
        brain=brain,
        tts_provider=_select_tts_provider(settings, testing),
        registry=registry,
        memory_store=memory_store,
        interaction_log=interaction_log,
        device_store=device_store,
        tick_service=tick_service,
    )
    voice_pipeline = VoicePipeline(
        dispatcher=dispatcher,
        fast_brain=fast_brain,
        slow_brain=brain,
        asr_provider=asr_provider,
        audio_provider=audio_provider,
        slow_fallback_enabled=bool(
            settings.voice_routing.get("slow_fallback_enabled", True)
        ),
        asr_min_confidence=float(settings.voice_routing.get("asr_min_confidence", 0.0)),
        fast_brain_provider_name=str(getattr(fast_llm_provider, "name", "fast_llm")),
        slow_brain_provider_name=str(getattr(slow_llm_provider, "name", "slow_llm")),
    )

    app = FastAPI(title="PetAgent Momo", version=settings.schema_version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.state_store = state_store
    app.state.memory_store = memory_store
    app.state.interaction_log = interaction_log
    app.state.device_store = device_store
    app.state.tick_service = tick_service
    app.state.proactive_service = proactive_service
    app.state.registry = registry
    app.state.dispatcher = dispatcher
    app.state.audio_provider = audio_provider
    app.state.asr_provider = asr_provider
    app.state.voice_pipeline = voice_pipeline
    app.state.activation_manager = activation_manager
    app.state.proactive_brain = proactive_brain

    @app.get("/api/health")
    def health():
        return {"ok": True, "name": settings.pet_name}

    app.include_router(runtime_api.router)
    app.include_router(pet_api.router)
    app.include_router(voice_api.router)
    app.include_router(activation_api.router)
    app.include_router(device_api.router)
    app.include_router(skills_api.router)

    static_root = settings.project_root / "backend" / "static"
    static_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_root)), name="static")
    if settings.frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(settings.frontend_dist), html=True))

    return app


app = create_app()
