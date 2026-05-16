from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


ALLOWED_MOODS = {
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

ALLOWED_ANIMATIONS = {
    "breathing",
    "bounce",
    "droop",
    "slowBlink",
    "shake",
    "wiggle",
    "blink",
    "tilt",
    "jump",
    "small",
}

ALLOWED_VIBRATIONS = {"none", "light", "medium"}
ALLOWED_VOICE_STYLES = {"soft", "normal", "happy", "sleepy", "shy"}

ALLOWED_INTERACTION_TONES = {
    "affectionate", "playful", "comforting", "encouraging",
    "demanding", "tiring", "quiet", "caregiving", "neutral",
}
ALLOWED_PET_EFFORTS = {"none", "low", "medium", "high"}
ALLOWED_EMOTIONAL_EFFECTS = {
    "happy", "comforted", "encouraged", "pressured",
    "annoyed", "sleepy", "calm", "lonely_relieved", "uncertain",
}

MOOD_ANIMATION_MAP = {
    "idle": "breathing",
    "happy": "bounce",
    "sad": "droop",
    "sleepy": "slowBlink",
    "angry": "shake",
    "shy": "wiggle",
    "thinking": "blink",
    "concerned": "tilt",
    "excited": "jump",
    "lonely": "small",
}

STATE_KEYS = ["energy", "intimacy", "hunger", "cleanliness", "loneliness", "sleepiness"]


class MemoryUpdate(BaseModel):
    should_save: bool = False
    content: str = ""


class StateAffect(BaseModel):
    interaction_tone: str = "neutral"
    pet_effort: str = "none"
    emotional_effect: str = "uncertain"
    reason: str = ""


class PetAction(BaseModel):
    schema_version: str = "0.1"
    reply: str
    mood: str = "idle"
    face_type: str = "idle"
    animation: str = "breathing"
    voice_style: str = "soft"
    vibration: str = "none"
    intent: str = "stage1_response"
    autonomy_notes: str = ""
    state_delta: Dict[str, int] = Field(default_factory=dict)
    state_affect: StateAffect = Field(default_factory=StateAffect)
    memory_update: MemoryUpdate = Field(default_factory=MemoryUpdate)


class PetResponse(BaseModel):
    schema_version: str = "0.1"
    reply: str
    mood: str
    face_type: str
    animation: str
    vibration: str
    pet_state: Dict[str, Any]
    runtime: Dict[str, Any]
    voice_url: Optional[str] = None
    audio_job_id: Optional[str] = None
    state_affect: Optional[Dict[str, Any]] = None
