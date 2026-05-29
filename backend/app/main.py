from __future__ import annotations

import logging
import tempfile
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from app.api import activation as activation_api
from app.api import client_config as client_config_api
from app.api import debug as debug_api
from app.api import audio as audio_api
from app.api import context as context_api
from app.api import frontend as frontend_api
from app.api import health as health_api
from app.api import interactions as interactions_api
from app.api import device as device_api
from app.api import memory as memory_api
from app.api import pet as pet_api
from app.api import runtime as runtime_api
from app.api import skills as skills_api
from app.api import text as text_api
from app.api import voice as voice_api
from app.api.auth import get_internal_token
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
from app.providers.probes import ProviderProbeManager
from app.runtime.activation import ActivationManager
from app.runtime.audio_job_store import AudioJobStore
from app.runtime.audio_jobs import AudioJobManager
from app.runtime.concurrency import AgentWorkExecutor, ProviderGate
from app.runtime.maintenance_worker import MaintenanceWorker
from app.runtime.proactive_scheduler import ProactiveScheduler
from app.runtime.context_manager import ContextManager
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.dispatcher import RuntimeDispatcher
from app.runtime.agent_run import AgentRunRegistry
from app.runtime.agent_run_store import AgentRunStore
from app.runtime.backup import DatabaseBackupManager
from app.runtime.incident import IncidentStore
from app.runtime.policy_guard import PolicyGuard
from app.runtime.device import DeviceStateStore
from app.runtime.maintenance import MaintenanceService
from app.runtime.memory_cards import MemoryCardManager
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
from app.runtime.text_pipeline import TextPipeline
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


def _select_memory_summarizer_provider(settings: Settings, testing: bool):
    config = settings.memory_summarizer or settings.llm_fallback or settings.llm
    return _select_llm_provider(
        settings,
        testing,
        config,
        "mock_memory_summarizer",
        fallback_config=None,
    )


def _resolve_project_path(settings: Settings, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return settings.project_root / path


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

    memory_cards_config = settings.app_config.get("memory_cards", {})
    if testing:
        test_memory_cards_dir = Path(tempfile.mkdtemp(prefix="petagent-memory-cards-"))
        memory_cards_config = dict(memory_cards_config)
        memory_cards_config["user_preferences_path"] = str(test_memory_cards_dir / "user.md")
        memory_cards_config["momo_memories_path"] = str(test_memory_cards_dir / "memory.md")
    memory_card_manager = None
    if memory_cards_config.get("enabled", True):
        # Resolve relative card paths against project_root (P1 fix)
        resolved_cards_config = dict(memory_cards_config)
        for key in ("user_preferences_path", "momo_memories_path"):
            raw = resolved_cards_config.get(key)
            if raw and not Path(raw).is_absolute():
                resolved_cards_config[key] = str(settings.project_root / raw)
        memory_card_manager = MemoryCardManager(
            memory_manager=memory_manager,
            config=resolved_cards_config,
        )
        # P4: On startup, ensure card files exist (rebuild if memories available, clear otherwise)
        if not testing:
            try:
                up_items = memory_card_manager.read_card("user_preferences")
                mm_items = memory_card_manager.read_card("momo_memories")
                if not up_items and not mm_items:
                    if memory_manager.count() > 0:
                        memory_card_manager.rebuild("runtime_reset")
                    else:
                        memory_card_manager.clear()
            except Exception:
                pass

    # V1.3: NotebookManager and MemoryJudgmentQueue
    from app.runtime.notebook import NotebookManager
    from app.runtime.memory_judgment import MemoryJudgmentQueue

    notebook_user_path = memory_cards_config.get(
        "user_preferences_path",
        str(settings.project_root / "backend/data/memory_cards/user.md"),
    )
    notebook_memory_path = memory_cards_config.get(
        "momo_memories_path",
        str(settings.project_root / "backend/data/memory_cards/memory.md"),
    )
    notebook_manager = NotebookManager(
        user_path=_resolve_project_path(settings, str(notebook_user_path)),
        memory_path=_resolve_project_path(settings, str(notebook_memory_path)),
    )
    # Run one-time migration on startup (non-testing)
    if not testing:
        try:
            notebook_manager.migrate_if_needed(memory_card_manager)
        except Exception:
            logger.warning("Notebook migration failed", exc_info=True)

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

    memory_judgment_queue = MemoryJudgmentQueue(
        provider=_select_memory_summarizer_provider(settings, testing),
        provider_gate=None,  # wired after provider_gate is created
        notebook_manager=notebook_manager,
    )

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
    backup_dir = settings.data_dir / "backups"
    backup_manager = DatabaseBackupManager(
        connection=state_store.connection,
        backup_dir=backup_dir,
    )
    # V1.3: Nightly cleanup runner (provider_gate wired after creation)
    from app.runtime.nightly_cleanup import NightlyCleanupRunner
    nightly_cleanup_runner = NightlyCleanupRunner(
        notebook_manager=notebook_manager,
        provider=slow_llm_provider,
        event_log_store=event_log_store,
        maintenance_state=maintenance_state,
        provider_gate=None,
        dispatcher=None,
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
        memory_card_manager=memory_card_manager,
        backup_manager=backup_manager,
        connection=state_store.connection,
        memory_judgment_queue=memory_judgment_queue,
        notebook_manager=notebook_manager,
        nightly_cleanup_runner=nightly_cleanup_runner,
    )

    audio_provider = _select_audio_provider(settings, testing)
    asr_provider = _select_asr_provider(settings, testing)
    activation_manager = ActivationManager(settings, state_store.connection)
    tts_provider = _select_tts_provider(settings, testing)
    agent_run_store = AgentRunStore(state_store.connection, max_rows=200)
    incident_store = IncidentStore(state_store.connection, max_rows=500)
    agent_run_registry = AgentRunRegistry(max_runs=50, store=agent_run_store)

    def _on_audio_complete(job_id: str, status: str, error) -> None:
        run = agent_run_registry.find_by_audio_job_id(job_id)
        if run:
            run.record(f"audio_{status}", {"job_id": job_id, "error": error})

    provider_gate = ProviderGate()
    # Wire provider_gate into judgment queue and nightly cleanup now that it exists
    memory_judgment_queue._provider_gate = provider_gate
    nightly_cleanup_runner._provider_gate = provider_gate
    audio_job_store = AudioJobStore(state_store.connection)
    audio_job_manager = AudioJobManager(
        tts_provider,
        ttl_seconds=int(settings.app_config.get("audio_jobs", {}).get("ttl_seconds", 900)),
        max_workers=2,
        provider_name=str(getattr(tts_provider, "name", "tts")),
        on_complete=_on_audio_complete,
        store=audio_job_store,
        provider_gate=provider_gate,
    )
    # Mark any jobs that were pending/running when the process last died
    audio_job_manager.mark_restart_failed()
    policy_guard = PolicyGuard()
    agent_work_executor = AgentWorkExecutor(max_workers=4, max_queue=8)
    proactive_scheduler = ProactiveScheduler()
    runtime_log_path = settings.data_dir / "logs" / "runtime.log"
    maintenance_worker = MaintenanceWorker(
        maintenance_service,
        log_path=runtime_log_path if runtime_log_path.parent.exists() else None,
    )
    probe_manager = ProviderProbeManager()

    dispatcher = RuntimeDispatcher(
        state_store=state_store,
        brain=brain,
        tts_provider=tts_provider,
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
        audio_job_manager=audio_job_manager,
        agent_run_registry=agent_run_registry,
        memory_card_manager=memory_card_manager,
        policy_guard=policy_guard,
        maintenance_worker=maintenance_worker,
        provider_gate=provider_gate,
        incident_store=incident_store,
        memory_judgment_queue=memory_judgment_queue,
        notebook_manager=notebook_manager,
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
        provider_gate=provider_gate,
    )
    text_pipeline = TextPipeline(
        dispatcher=dispatcher,
        fast_brain=fast_brain,
        slow_brain=brain,
        fast_brain_provider_name=str(getattr(fast_llm_provider, "name", "fast_llm")),
        slow_brain_provider_name=str(getattr(slow_llm_provider, "name", "slow_llm")),
        activation_manager=activation_manager,
    )

    # CORS: explicit origin allowlist instead of wildcard
    cors_config = settings.app_config.get("cors", {})
    allowed_origins = list(cors_config.get("allowed_origins", []))
    # Always allow loopback origins for local frontend
    for origin in ("http://127.0.0.1:8000", "http://localhost:8000"):
        if origin not in allowed_origins:
            allowed_origins.append(origin)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        import asyncio as _asyncio
        from contextlib import suppress as _suppress
        from time import perf_counter as _perf_counter

        # Startup — core stores are ready immediately
        app.state.shutdown_in_progress = False
        app.state.core_ready = True
        app.state.providers_ready = True
        # Low-cost event-loop heartbeat for watchdog. A quiet pet with no recent
        # interactions is healthy; this only grows stale when the loop itself is wedged.
        async def _event_loop_heartbeat() -> None:
            while True:
                dispatcher.event_loop_tick = _perf_counter()
                await _asyncio.sleep(1)

        heartbeat_task = _asyncio.create_task(_event_loop_heartbeat())
        # Start maintenance worker
        try:
            maintenance_worker.start()
        except Exception:
            logger.warning("Failed to start maintenance worker", exc_info=True)
        # Generate catch_up event for offline interval
        try:
            proactive_scheduler.catch_up_event()
        except Exception:
            logger.warning("Failed to generate catch_up event", exc_info=True)
        # Run provider probes in background (non-blocking)
        async def _run_probes() -> None:
            try:
                if not isinstance(slow_llm_provider, MockLLMProvider):
                    await probe_manager.probe_llm(slow_llm_provider)
                if not isinstance(tts_provider, MockTTSProvider):
                    await probe_manager.probe_tts(tts_provider)
            except Exception:
                logger.warning("Provider probes failed", exc_info=True)

        _asyncio.create_task(_run_probes())
        logger.info("PetAgent Doudou starting up (core_ready=True)")
        yield
        # Shutdown
        logger.info("PetAgent Doudou shutting down")
        app.state.shutdown_in_progress = True
        heartbeat_task.cancel()
        with _suppress(_asyncio.CancelledError):
            await heartbeat_task
        # Stop maintenance worker
        try:
            maintenance_worker.stop()
        except Exception:
            logger.warning("Failed to stop maintenance worker", exc_info=True)
        # Drain audio jobs
        shutdown_count = audio_job_manager.mark_shutdown_failed()
        if shutdown_count:
            logger.info("Marked %d audio jobs as failed_shutdown", shutdown_count)
        audio_job_manager.shutdown()
        # Close SQLite connections
        try:
            conn = getattr(state_store, "connection", None)
            if conn is not None:
                raw = getattr(conn, "_connection", conn)
                raw.close()
        except Exception:
            logger.warning("Failed to close state_store connection", exc_info=True)
        logger.info("PetAgent Doudou shutdown complete")

    app = FastAPI(title="PetAgent Doudou", version=settings.schema_version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Internal debug/management token (CC-0)
    internal_token = get_internal_token(settings)
    app.state.shutdown_in_progress = False
    app.state.core_ready = False
    app.state.providers_ready = False
    app.state.settings = settings
    app.state.internal_token = internal_token
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
    app.state.text_pipeline = text_pipeline
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
    app.state.audio_job_store = audio_job_store
    app.state.audio_job_manager = audio_job_manager
    app.state.agent_run_store = agent_run_store
    app.state.incident_store = incident_store
    app.state.agent_run_registry = agent_run_registry
    app.state.memory_card_manager = memory_card_manager
    app.state.notebook_manager = notebook_manager
    app.state.memory_judgment_queue = memory_judgment_queue
    app.state.policy_guard = policy_guard
    app.state.agent_work_executor = agent_work_executor
    app.state.proactive_scheduler = proactive_scheduler
    app.state.maintenance_worker = maintenance_worker
    app.state.provider_gate = provider_gate
    app.state.probe_manager = probe_manager
    app.state.nightly_cleanup_runner = nightly_cleanup_runner
    # Wire dispatcher into nightly cleanup runner now that it exists
    nightly_cleanup_runner._dispatcher = dispatcher

    # Read frontend build-info.json if present
    build_info: Dict[str, str] = {}
    build_info_path = settings.frontend_dist / "build-info.json"
    if build_info_path.exists():
        try:
            import json as _json
            build_info = _json.loads(build_info_path.read_text())
        except Exception:
            pass
    app.state.build_info = build_info

    # Health router registered first (light/watchdog/deep)
    app.include_router(health_api.router)
    app.include_router(frontend_api.router)
    app.include_router(client_config_api.router)
    app.include_router(runtime_api.router)
    app.include_router(pet_api.router)
    app.include_router(voice_api.router)
    app.include_router(audio_api.router)
    app.include_router(activation_api.router)
    app.include_router(device_api.router)
    app.include_router(skills_api.router)
    app.include_router(context_api.router)
    app.include_router(memory_api.router)
    app.include_router(text_api.router)
    app.include_router(interactions_api.router)
    app.include_router(debug_api.router)

    static_root = settings.project_root / "backend" / "static"
    static_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_root)), name="static")
    if settings.frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(settings.frontend_dist), html=True))

    return app


app = create_app()
