from __future__ import annotations

from app.config import Settings
from app.pet.state import PetStateStore


def create_state_store(settings: Settings, testing: bool = False) -> PetStateStore:
    if testing:
        return PetStateStore(None, pet_name=settings.pet_name)
    return PetStateStore(settings.data_dir / "pet.db", pet_name=settings.pet_name)
