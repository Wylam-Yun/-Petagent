"""Stage 3.7: Memory policy migration tests."""
from app.runtime.memory_policy import SENSITIVE_MARKERS, infer_memory_type


def test_sensitive_markers_importable():
    """SENSITIVE_MARKERS should be importable from memory_policy."""
    assert "密码" in SENSITIVE_MARKERS
    assert "银行卡" in SENSITIVE_MARKERS
    assert "token" in SENSITIVE_MARKERS


def test_infer_memory_type_works():
    """infer_memory_type should classify content correctly."""
    assert infer_memory_type("我喜欢短回复") == "user_preference"
    assert infer_memory_type("以后叫我 William") == "relationship"
    assert infer_memory_type("明天有面试") == "important_event"
    assert infer_memory_type("我经常跑步") == "habit"
    assert infer_memory_type("今天好累") == "recent_mood"


def test_curator_imports_from_memory_policy():
    """memory_curator should import from memory_policy, not app.pet.memory."""
    import inspect
    from app.runtime import memory_curator
    source = inspect.getsource(memory_curator)
    assert "from app.runtime.memory_policy import" in source
    assert "from app.pet.memory import" not in source


def test_interaction_log_store_still_works():
    """InteractionLogStore should still be functional (deprecated but working)."""
    from app.pet.memory import InteractionLogStore
    from app.pet.state import PetStateStore

    state_store = PetStateStore(None)
    log = InteractionLogStore(state_store.connection)
    log.record("voice_message", "你好呀", "happy", user_text="你好")
    recent = log.recent_dialogue(limit=1)
    assert len(recent) == 1
    assert recent[0]["pet"] == "你好呀"


def test_pet_memory_reexports_policy():
    """app.pet.memory should re-export SENSITIVE_MARKERS and infer_memory_type."""
    from app.pet.memory import SENSITIVE_MARKERS as sm, infer_memory_type as fmt
    assert sm is SENSITIVE_MARKERS
    assert fmt is infer_memory_type
