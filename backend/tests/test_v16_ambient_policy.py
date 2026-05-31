from __future__ import annotations

from app.pet.state import PetStateStore
from app.runtime.ambient_bubble import AmbientBubbleService, guard_ambient_bubble_output
from app.runtime.expressions import activity_recommendation


def make_service(tmp_path):
    state_store = PetStateStore(tmp_path / "state.db")
    return AmbientBubbleService(state_store.connection)


def test_guard_accepts_valid_llm_output():
    result = guard_ambient_bubble_output(
        {
            "bubble": "我刚刚没有偷懒。",
            "expression_key": "idle_wink",
            "action": "lazy_idle",
        }
    )
    assert result is not None
    assert result.bubble == "我刚刚没有偷懒。"
    assert result.expression_key == "idle_wink"
    assert result.action == "lazy_idle"


def test_guard_enforces_activity_recommended_expression_and_action():
    rec = activity_recommendation("stay_near")
    assert (
        guard_ambient_bubble_output(
            {
                "bubble": "我轻轻待着。",
                "expression_key": "idle_soft",
                "action": "idle",
            },
            rec,
        )
        is not None
    )
    assert (
        guard_ambient_bubble_output(
            {
                "bubble": "我轻轻待着。",
                "expression_key": "idle_wink",
                "action": "sneak_eat",
            },
            rec,
        )
        is None
    )


def test_guard_rejects_empty_or_not_first_person():
    assert guard_ambient_bubble_output({"bubble": ""}) is None
    assert guard_ambient_bubble_output({"bubble": "刚刚没有偷懒。"}) is None
    assert guard_ambient_bubble_output({"bubble": "豆豆没有偷懒。"}) is None


def test_guard_rejects_too_long_without_truncating():
    result = guard_ambient_bubble_output({"bubble": "我" + "很" * 30})
    assert result is None


def test_guard_rejects_kaomoji():
    assert guard_ambient_bubble_output({"bubble": "我在哦(^▽^)"}) is None


def test_daily_limit_and_activity_limits(tmp_path):
    svc = make_service(tmp_path)
    day = "2026-05-31"
    for i in range(10):
        event_id = f"evt-{i}"
        assert (
            svc.create_pending(
                local_date=day,
                event_id=event_id,
                activity="quiet_guard",
                activity_class="quiet",
                bubble="我在安静看家。",
                expression_key="calm",
                action="idle",
            )
            is True
        )
        assert svc.confirm_pending(event_id) is True
    assert svc.can_emit(day)["eligible"] is False
    assert svc.can_emit(day)["block_reason"] == "daily_limit"


def test_pending_does_not_advance_counters_until_confirmed(tmp_path):
    svc = make_service(tmp_path)
    day = "2026-05-31"
    before = svc.debug_state(day)
    assert (
        svc.create_pending(
            local_date=day,
            event_id="evt-pending",
            activity="sneak_snack",
            activity_class="mischief",
            bubble="我没有偷吃。",
            expression_key="playful",
            action="sneak_eat",
        )
        is True
    )
    middle = svc.debug_state(day)
    assert middle["daily_count"] == before["daily_count"]
    assert middle["backoff_step"] == before["backoff_step"]
    assert middle["pending_count"] == 1
    assert svc.confirm_pending("evt-pending") is True
    after = svc.debug_state(day)
    assert after["daily_count"] == before["daily_count"] + 1
    assert after["backoff_step"] == before["backoff_step"] + 1
    assert after["last_rendered_expression_key"] == "playful"


def test_failure_and_cancel_do_not_advance_counters(tmp_path):
    svc = make_service(tmp_path)
    day = "2026-05-31"
    before = svc.debug_state(day)
    svc.record_failure("validation_failed")
    after = svc.debug_state(day)
    assert after["daily_count"] == before["daily_count"]
    assert after["backoff_step"] == before["backoff_step"]
    svc.create_pending(
        local_date=day,
        event_id="evt-cancelled",
        activity="lazy_save_power",
        activity_class="lazy",
        bubble="我在省电。",
        expression_key="tired",
        action="lazy_idle",
    )
    assert svc.cancel_pending("evt-cancelled") is True
    cancelled = svc.debug_state(day)
    assert cancelled["daily_count"] == before["daily_count"]
    assert cancelled["backoff_step"] == before["backoff_step"]
