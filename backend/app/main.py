from __future__ import annotations

from dataclasses import replace

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import activation as activation_api
from app.api import context as context_api
from app.api import device as device_api
from app.api import memory as memory_api
from app.api import pet as pet_api
from app.api import runtime as runtime_api
from app.api import skills as skills_api
from app.api import voice as voice_api
from app.config import Settings, load_settings
from app.db import create_state_store
from app.pet.brain import PetBrain
from app.pet.memory import InteractionLogStore
from app.providers.audio_omni import (
    MiMoAudioUnderstandingProvider,
    MockAudioUnderstandingProvider,
)
from app.providers.asr_http import HttpASRProvider
from app.providers.asr_mock import MockASRProvider
from app.providers.asr_nvidia import NvidiaParakeetASRProvider
from app.providers.llm_mimo import FallbackLLMProvider, MiMoLLMProvider, MockLLMProvider
from app.providers.proactive_rule import ProactiveRuleProvider
from app.providers.tts_mimo import FallbackTTSProvider, MiMoTTSProvider, MockTTSProvider
from app.runtime.activation import ActivationManager
from app.runtime.context_manager import ContextManager
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.dispatcher import RuntimeDispatcher
from app.runtime.device import DeviceStateStore
from app.runtime.maintenance import MaintenanceService
from app.runtime.memory_curator import MemoryCurator
from app.runtime.memory_store import (
    DailySummaryStore,
    EpisodeSummaryStore,
    MaintenanceStateStore,
    MemoryCandidateStore,
    MemoryManager,
    SummaryJobStore,
)
from app.runtime.proactive import ProactiveService
from app.runtime.registry import SkillRegistry
from app.runtime.summary_manager import SummaryManager
from app.runtime.tick import TickService
from app.runtime.voice_pipeline import VoicePipeline


def _select_llm_provider(
    settings: Settings,
    testing: bool,
    provider_config=None,
    mock_name: str = "mock_llm",
    fallback_config=None,
):
    config = provider_config or settings.llm
    if testing or not config.api_key:
        return MockLLMProvider(mock_name)
    primary = MiMoLLMProvider(settings, config)
    if fallback_config is not None and fallback_config.api_key:
        return FallbackLLMProvider(primary, MiMoLLMProvider(settings, fallback_config))
    return primary


def _select_tts_provider(settings: Settings, testing: bool):
    if testing:
        return MockTTSProvider(settings.audio_dir)
    primary = MiMoTTSProvider(settings)
    if settings.tts_fallback is not None and settings.tts_fallback.api_key:
        fallback_settings = replace(
            settings,
            tts=settings.tts_fallback,
            api_key=settings.tts_fallback.api_key or settings.api_key,
        )
        return FallbackTTSProvider(primary, MiMoTTSProvider(fallback_settings))
    return primary


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
    interaction_log = InteractionLogStore(state_store.connection)
    device_store = DeviceStateStore(state_store.connection)
    tick_service = TickService(state_store, device_store)
    proactive_service = ProactiveService(state_store, device_store)
    registry = SkillRegistry(settings=settings, device_store=device_store)

    # Stage 3.5: Cognition Context stores
    episode_manager = EpisodeStore(state_store.connection)
    event_log_store = EventLogStore(state_store.connection)
    cc_config = settings.app_config.get("cognition_context", {})
    context_manager = ContextManager(cc_config)

    # Stage 3.6: Memory stores and managers
    memory_config = settings.app_config.get("memory", {})
    memory_manager = MemoryManager(state_store.connection, config=memory_config)
    memory_candidate_store = MemoryCandidateStore(state_store.connection)
    summary_job_store = SummaryJobStore(
        state_store.connection,
        max_attempts=int(memory_config.get("summary_job_max_attempts", 3)),
    )
    episode_summary_store = EpisodeSummaryStore(state_store.connection)
    daily_summary_store = DailySummaryStore(state_store.connection)
    maintenance_state = MaintenanceStateStore(state_store.connection)

    slow_llm_provider = _select_llm_provider(
        settings,
        testing,
        settings.llm,
        "mock_slow_llm",
        fallback_config=settings.llm_fallback,
    )
    fast_llm_provider = _select_llm_provider(
        settings,
        testing,
        settings.llm_fast or settings.llm,
        "mock_fast_llm",
        fallback_config=settings.llm_fast_fallback or settings.llm_fallback,
    )
    brain = PetBrain(settings, slow_llm_provider)
    fast_brain = PetBrain(settings, fast_llm_provider)
    proactive_brain = PetBrain(settings, ProactiveRuleProvider())

    memory_curator = MemoryCurator(
        brain_provider=slow_llm_provider,
        memory_manager=memory_manager,
        max_batch=memory_config.get("curator_batch_size", 8),
    )
    summary_manager = SummaryManager(
        brain_provider=slow_llm_provider,
        episode_summary_store=episode_summary_store,
        daily_summary_store=daily_summary_store,
        candidate_store=memory_candidate_store,
        timezone_name=cc_config.get("timezone", "Asia/Shanghai"),
    )
    maintenance_service = MaintenanceService(
        curator=memory_curator,
        summary_manager=summary_manager,
        candidate_store=memory_candidate_store,
        summary_job_store=summary_job_store,
        memory_manager=memory_manager,
        episode_summary_store=episode_summary_store,
        daily_summary_store=daily_summary_store,
        maintenance_state=maintenance_state,
        event_log_store=event_log_store,
        episode_store=episode_manager,
        config=memory_config,
    )

    audio_provider = _select_audio_provider(settings, testing)
    asr_provider = _select_asr_provider(settings, testing)
    activation_manager = ActivationManager(settings, state_store.connection)
    dispatcher = RuntimeDispatcher(
        state_store=state_store,
        brain=brain,
        tts_provider=_select_tts_provider(settings, testing),
        registry=registry,
        interaction_log=interaction_log,
        device_store=device_store,
        tick_service=tick_service,
        episode_manager=episode_manager,
        event_log_store=event_log_store,
        context_manager=context_manager,
        memory_candidate_store=memory_candidate_store,
        summary_job_store=summary_job_store,
        maintenance_service=maintenance_service,
        memory_manager=memory_manager,
        episode_summary_store=episode_summary_store,
        daily_summary_store=daily_summary_store,
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
        activation_manager=activation_manager,
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
    app.state.episode_manager = episode_manager
    app.state.event_log_store = event_log_store
    app.state.context_manager = context_manager
    app.state.memory_manager = memory_manager
    app.state.memory_candidate_store = memory_candidate_store
    app.state.summary_job_store = summary_job_store
    app.state.episode_summary_store = episode_summary_store
    app.state.daily_summary_store = daily_summary_store
    app.state.maintenance_state = maintenance_state
    app.state.memory_curator = memory_curator
    app.state.summary_manager = summary_manager
    app.state.maintenance_service = maintenance_service

    @app.get("/api/health")
    def health():
        return {"ok": True, "name": settings.pet_name}

    app.include_router(runtime_api.router)
    app.include_router(pet_api.router)
    app.include_router(voice_api.router)
    app.include_router(activation_api.router)
    app.include_router(device_api.router)
    app.include_router(skills_api.router)
    app.include_router(context_api.router)
    app.include_router(memory_api.router)

    static_root = settings.project_root / "backend" / "static"
    static_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_root)), name="static")
    if settings.frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(settings.frontend_dist), html=True))

    return app


app = create_app()
