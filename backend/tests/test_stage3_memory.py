from app.pet.memory import MemoryStore
from app.pet.state import PetStateStore
from app.runtime.actions import MemoryUpdate


def test_memory_update_false_does_not_write_memory():
    state_store = PetStateStore(None)
    memory = MemoryStore(state_store.connection)

    saved = memory.save_from_update(MemoryUpdate(should_save=False, content="用户今天很累"))

    assert saved is False
    assert memory.recent_memory() == []


def test_memory_store_saves_short_companionship_memory():
    state_store = PetStateStore(None)
    memory = MemoryStore(state_store.connection)

    saved = memory.save_from_update(
        MemoryUpdate(should_save=True, content="用户今天很累，需要温柔陪伴。")
    )

    assert saved is True
    assert memory.recent_memory() == ["用户今天很累，需要温柔陪伴。"]


def test_memory_store_rejects_sensitive_or_too_long_content():
    state_store = PetStateStore(None)
    memory = MemoryStore(state_store.connection)

    assert (
        memory.save_from_update(
            MemoryUpdate(should_save=True, content="用户的身份证号码可能是 123456。")
        )
        is False
    )
    assert (
        memory.save_from_update(
            MemoryUpdate(should_save=True, content="用户今天说" + "很累" * 40)
        )
        is False
    )
    assert memory.recent_memory() == []
