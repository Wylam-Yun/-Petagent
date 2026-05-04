from datetime import datetime, timedelta

from app.pet.state import PetStateStore
from app.runtime.device import DeviceStateStore
from app.runtime.tick import TickService


def test_device_state_tracks_previous_charging_state():
    state_store = PetStateStore(None)
    device = DeviceStateStore(state_store.connection)

    first = device.save_state(battery=76, is_charging=False)
    second = device.save_state(battery=78, is_charging=True)

    assert first["was_charging"] is None
    assert second["is_charging"] is True
    assert second["was_charging"] is False


def test_tick_update_raises_loneliness_after_long_idle():
    state_store = PetStateStore(None)
    device = DeviceStateStore(state_store.connection)
    tick = TickService(state_store, device, interval_seconds=300)
    state = state_store.get_state()
    two_hours_ago = datetime.utcnow() - timedelta(hours=2)
    state["last_interaction_at"] = two_hours_ago.isoformat()
    state["loneliness"] = 10
    state_store.save_state(state)
    tick.set_last_tick(two_hours_ago)

    updated = tick.apply_if_due(now=datetime.utcnow())

    assert updated["loneliness"] > 10
    assert 0 <= updated["loneliness"] <= 100


def test_tick_update_recovers_energy_while_charging():
    state_store = PetStateStore(None)
    device = DeviceStateStore(state_store.connection)
    device.save_state(battery=80, is_charging=True)
    tick = TickService(state_store, device, interval_seconds=300)
    state = state_store.get_state()
    state["energy"] = 40
    state["hunger"] = 40
    state_store.save_state(state)
    tick.set_last_tick(datetime.utcnow() - timedelta(minutes=10))

    updated = tick.apply_if_due(now=datetime.utcnow())

    assert updated["energy"] > 40
    assert updated["hunger"] < 40
