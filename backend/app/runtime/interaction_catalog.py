from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class InteractionDef:
    event_id: str
    label: str
    group: str  # "pet_care" | "emotional_companion" | "debug"
    default_mood: str
    default_animation: str
    description: str
    aliases: Tuple[str, ...] = ()
    state_semantics: Dict[str, str] = field(default_factory=dict)


INTERACTION_CATALOG: Dict[str, InteractionDef] = {
    # -- pet_care --
    "pet_head": InteractionDef(
        event_id="pet_head",
        label="摸摸头",
        group="pet_care",
        default_mood="shy",
        default_animation="wiggle",
        description="用户摸了你的头",
        state_semantics={"intimacy": "up", "loneliness": "down"},
    ),
    "poke_face": InteractionDef(
        event_id="poke_face",
        label="戳脸",
        group="pet_care",
        default_mood="angry",
        default_animation="shake",
        description="用户轻轻戳了你的脸",
    ),
    "hug": InteractionDef(
        event_id="hug",
        label="抱一下",
        group="pet_care",
        default_mood="happy",
        default_animation="bounce",
        description="用户抱了抱你",
        state_semantics={"intimacy": "up", "loneliness": "down"},
    ),
    "pet_pat": InteractionDef(
        event_id="pet_pat",
        label="拍拍",
        group="pet_care",
        default_mood="happy",
        default_animation="wiggle",
        description="用户轻轻拍拍你，像是在鼓励你",
        state_semantics={"intimacy": "up", "loneliness": "down"},
    ),
    "praise_momo": InteractionDef(
        event_id="praise_momo",
        label="夸夸",
        group="pet_care",
        default_mood="happy",
        default_animation="jump",
        description="用户夸夸了 Momo",
        state_semantics={"energy": "up", "intimacy": "up"},
    ),
    "feed_momo": InteractionDef(
        event_id="feed_momo",
        label="投喂",
        group="pet_care",
        default_mood="happy",
        default_animation="bounce",
        description="用户投喂了 Momo",
        state_semantics={"energy": "up", "hunger": "down"},
    ),
    "tuck_in": InteractionDef(
        event_id="tuck_in",
        label="哄睡",
        group="pet_care",
        default_mood="sleepy",
        default_animation="slowBlink",
        description="用户想哄你休息",
        state_semantics={"sleepiness": "up", "energy": "down"},
    ),
    "clean_face": InteractionDef(
        event_id="clean_face",
        label="擦擦脸",
        group="pet_care",
        default_mood="happy",
        default_animation="wiggle",
        description="用户帮你擦擦脸",
        state_semantics={"cleanliness": "up", "intimacy": "up"},
    ),
    # -- emotional_companion --
    "stay_with_me": InteractionDef(
        event_id="stay_with_me",
        label="陪我一下",
        group="emotional_companion",
        default_mood="happy",
        default_animation="breathing",
        description="用户希望你陪自己一下",
        state_semantics={"loneliness": "down", "intimacy": "up"},
    ),
    "comfort_me": InteractionDef(
        event_id="comfort_me",
        label="安慰我",
        group="emotional_companion",
        default_mood="concerned",
        default_animation="tilt",
        description="用户希望你安慰自己",
        state_semantics={"loneliness": "down", "intimacy": "up"},
    ),
    "encourage_me": InteractionDef(
        event_id="encourage_me",
        label="鼓励我",
        group="emotional_companion",
        default_mood="excited",
        default_animation="jump",
        description="用户希望你鼓励自己",
        state_semantics={"energy": "up", "intimacy": "up"},
    ),
    "listen_to_me": InteractionDef(
        event_id="listen_to_me",
        label="听我吐槽",
        group="emotional_companion",
        default_mood="thinking",
        default_animation="tilt",
        description="用户希望你听自己吐槽",
        state_semantics={"loneliness": "down", "intimacy": "up"},
    ),
    "quiet_company": InteractionDef(
        event_id="quiet_company",
        label="安静待着",
        group="emotional_companion",
        default_mood="idle",
        default_animation="breathing",
        description="用户希望你安静陪着",
        state_semantics={"loneliness": "down"},
    ),
    "take_a_break": InteractionDef(
        event_id="take_a_break",
        label="休息会儿",
        group="emotional_companion",
        default_mood="sleepy",
        default_animation="slowBlink",
        description="用户希望你休息会儿",
        state_semantics={"sleepiness": "up", "energy": "up"},
    ),
    # -- debug --
    "debug_happy": InteractionDef(
        event_id="debug_happy",
        label="开心",
        group="debug",
        default_mood="happy",
        default_animation="bounce",
        description="调试：开心",
    ),
    "debug_sleepy": InteractionDef(
        event_id="debug_sleepy",
        label="困了",
        group="debug",
        default_mood="sleepy",
        default_animation="slowBlink",
        description="调试：困了",
    ),
    "debug_angry": InteractionDef(
        event_id="debug_angry",
        label="小生气",
        group="debug",
        default_mood="angry",
        default_animation="shake",
        description="调试：小生气",
    ),
}


def get_interaction(event_id: str) -> Optional[InteractionDef]:
    return INTERACTION_CATALOG.get(event_id)


def all_event_ids() -> List[str]:
    return list(INTERACTION_CATALOG.keys())


def button_event_ids() -> List[str]:
    return [k for k, v in INTERACTION_CATALOG.items() if v.group != "debug"]


def event_ids_by_group(group: str) -> List[str]:
    return [k for k, v in INTERACTION_CATALOG.items() if v.group == group]


def event_label_map() -> Dict[str, str]:
    return {k: v.label for k, v in INTERACTION_CATALOG.items()}


def event_animation_map() -> Dict[str, str]:
    return {k: v.default_animation for k, v in INTERACTION_CATALOG.items()}


def event_description_map() -> Dict[str, str]:
    return {k: v.description for k, v in INTERACTION_CATALOG.items()}
