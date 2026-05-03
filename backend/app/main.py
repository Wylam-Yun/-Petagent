from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import pet as pet_api
from app.api import runtime as runtime_api
from app.config import Settings, load_settings
from app.db import create_state_store
from app.pet.brain import PetBrain
from app.providers.llm_mimo import MiMoLLMProvider, MockLLMProvider
from app.providers.tts_mimo import MiMoTTSProvider, MockTTSProvider
from app.runtime.dispatcher import RuntimeDispatcher
from app.runtime.registry import SkillRegistry


def _select_llm_provider(settings: Settings, testing: bool):
    if testing or not settings.api_key:
        return MockLLMProvider()
    return MiMoLLMProvider(settings)


def _select_tts_provider(settings: Settings, testing: bool):
    if testing:
        return MockTTSProvider(settings.audio_dir)
    return MiMoTTSProvider(settings)


def create_app(testing: bool = False) -> FastAPI:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)

    state_store = create_state_store(settings, testing=testing)
    registry = SkillRegistry()
    brain = PetBrain(settings, _select_llm_provider(settings, testing))
    dispatcher = RuntimeDispatcher(
        state_store=state_store,
        brain=brain,
        tts_provider=_select_tts_provider(settings, testing),
        registry=registry,
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
    app.state.registry = registry
    app.state.dispatcher = dispatcher

    @app.get("/api/health")
    def health():
        return {"ok": True, "name": settings.pet_name}

    app.include_router(runtime_api.router)
    app.include_router(pet_api.router)

    static_root = settings.project_root / "backend" / "static"
    static_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_root)), name="static")
    if settings.frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(settings.frontend_dist), html=True))

    return app


app = create_app()
