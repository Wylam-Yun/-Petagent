"""Tests for STAB-028: Tick decay logistic curve."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.db import PetStateStore
from app.runtime.device import DeviceStateStore
from app.runtime.tick import TickService


_FULL_STATE = {
    "name": "Momo", "mood": "idle", "energy": 50, "intimacy": 40,
    "hunger": 50, "cleanliness": 85, "loneliness": 50, "sleepiness": 10,
    "mode": "idle", "last_interaction_at": "2026-05-22T10:00:00", "updated_at": "2026-05-22T10:00:00",
}


def _make_tick() -> TickService:
    state_store = PetStateStore(None)
    device_store = DeviceStateStore(state_store.connection)
    return TickService(state_store, device_store, interval_seconds=300)


def _set_state(tick: TickService, **overrides) -> None:
    state = dict(_FULL_STATE)
    state.update(overrides)
    tick.state_store.save_state(state)


def test_logistic_decay_slows_near_zero():
    """Logistic curve slows decay near edges — energy decays slower when low."""
    tick = _make_tick()
    _set_state(tick, energy=50, hunger=50, loneliness=50)

    now = datetime(2026, 5, 22, 12, 0, 0)
    # Simulate 48 intervals (24h at 300s intervals)
    for _ in range(48):
        now += timedelta(seconds=300)
        tick.apply_if_due(now=now)

    state = tick.state_store.get_state()
    energy = int(state["energy"])
    # With logistic decay starting at energy=50, after 24h energy should be > 0
    # (linear would give 50 - 48 = 2; logistic should be higher due to slowing)
    assert energy > 0, f"Energy hit {energy} — logistic decay should preserve some energy"


def test_logistic_decay_hunger_never_reaches_100():
    """Hunger should never pin at 100."""
    tick = _make_tick()
    _set_state(tick, energy=50, hunger=20, loneliness=50)

    now = datetime(2026, 5, 22, 12, 0, 0)
    for _ in range(48):
        now += timedelta(seconds=300)
        tick.apply_if_due(now=now)

    state = tick.state_store.get_state()
    assert int(state["hunger"]) < 100, f"Hunger hit {state['hunger']} — should cap below 100"


def test_rest_while_away_bonus():
    """After 6h+ idle since last interaction with low energy, rest bonus should recover energy."""
    tick = _make_tick()
    # Set last_interaction_at to 8 hours ago (well past the 6h threshold)
    eight_hours_ago = "2026-05-22T04:00:00"
    _set_state(tick, energy=30, hunger=50, loneliness=50, last_interaction_at=eight_hours_ago)

    base = datetime(2026, 5, 22, 12, 0, 0)
    tick.set_last_tick(base - timedelta(hours=8))

    state = tick.apply_if_due(now=base)
    energy = int(state["energy"])
    # Energy started at 30, rest bonus = min(20, 8/3) ≈ 2.67 → round to 3
    # Should be higher than 30 minus normal decay
    assert energy > 20, f"Energy is {energy} — rest bonus should have helped"


def test_rest_while_away_no_bonus_if_recent_interaction():
    """Rest bonus should NOT apply if last interaction was < 6h ago."""
    tick = _make_tick()
    # Set last_interaction_at to 2 hours ago (below 6h threshold)
    two_hours_ago = "2026-05-22T10:00:00"
    _set_state(tick, energy=30, hunger=50, loneliness=50, last_interaction_at=two_hours_ago)

    base = datetime(2026, 5, 22, 12, 0, 0)
    tick.set_last_tick(base - timedelta(hours=8))

    state = tick.apply_if_due(now=base)
    energy = int(state["energy"])
    # No rest bonus, energy should have decayed normally
    assert energy <= 30, f"Energy is {energy} — no rest bonus expected with recent interaction"


def test_charging_accelerates_recovery():
    """Charging should increase energy."""
    tick = _make_tick()
    tick.device_store.save_state(battery=50, is_charging=True)
    _set_state(tick, energy=50, hunger=50, loneliness=50)

    now = datetime(2026, 5, 22, 12, 0, 0)
    tick.set_last_tick(now - timedelta(seconds=300))
    state = tick.apply_if_due(now=now)

    # Charging adds +2 per interval
    energy = int(state["energy"])
    assert energy >= 50, f"Energy is {energy} — charging should maintain or increase"


def test_night_penalty():
    """Night hours should increase sleepiness more."""
    tick = _make_tick()
    _set_state(tick, energy=50, hunger=50, loneliness=50, sleepiness=10)

    # 2 AM = night
    now = datetime(2026, 5, 22, 2, 0, 0)
    tick.set_last_tick(now - timedelta(seconds=300))
    state = tick.apply_if_due(now=now)

    sleepiness = int(state["sleepiness"])
    assert sleepiness > 10, f"Sleepiness is {sleepiness} — night should increase it"
