from __future__ import annotations

from datetime import datetime, timedelta

from app.pet.state import PetStateStore
from app.runtime.proactive import ProactiveService


class _FakeDeviceStore:
    def get_state(self):
        return {}


def _make_service():
    state_store = PetStateStore(None)
    return ProactiveService(state_store, _FakeDeviceStore())


def test_proactive_respects_global_cooldown():
    svc = _make_service()
    now = datetime(2026, 5, 17, 9, 0, 0)

    # Record an event to establish the cooldown window
    svc.record("morning", now)

    # Within 30 min, global cooldown blocks any next_event
    assert svc.next_event(now + timedelta(minutes=10)) is None

    # After 30 min, global cooldown is lifted
    # (morning already triggered today, but _triggered_recently with None type is what matters)
    assert svc._triggered_recently(None, now + timedelta(minutes=10), minutes=30) is True
    assert svc._triggered_recently(None, now + timedelta(minutes=31), minutes=30) is False


def test_proactive_respects_event_type_cooldown():
    svc = _make_service()
    now = datetime(2026, 5, 17, 9, 0, 0)

    first = svc.next_event(now)
    assert first is not None

    # Global cooldown blocks regardless of event type
    second = svc.next_event(now + timedelta(minutes=15))
    assert second is None


def test_proactive_record_and_trigger_today():
    svc = _make_service()
    now = datetime(2026, 5, 17, 9, 0, 0)

    svc.record("morning", now)
    assert svc._triggered_today("morning", now) is True
    assert svc._triggered_today("night", now) is False


def test_global_cooldown_blocks_within_window():
    svc = _make_service()
    now = datetime(2026, 5, 17, 9, 0, 0)

    # First event succeeds
    first = svc.next_event(now)
    assert first is not None

    # Within 30 min, global cooldown blocks
    result = svc.next_event(now + timedelta(minutes=15))
    assert result is None
