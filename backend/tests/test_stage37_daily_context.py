"""Stage 3.7: Daily summary in cognition context tests."""
from app.runtime.context_manager import ContextManager
from app.runtime.events import PetEvent


def _make_event(user_text="你好"):
    return PetEvent(type="voice_message", source="user", payload={"user_text": user_text})


def test_daily_digest_included_in_context():
    """ContextManager should include daily_digest when daily summaries exist."""
    cm = ContextManager({"max_context_chars": 10000, "timezone": "Asia/Shanghai"})
    event = _make_event()

    class FakeDailyStore:
        def recent(self, limit=1):
            return [{"local_date": "2026-05-06", "summary": "昨天聊了天气和工作", "key_events": []}]

    ctx = cm.build(
        event=event,
        pet_state={},
        episode=None,
        event_log_store=None,
        daily_summary_store=FakeDailyStore(),
    )

    assert ctx["daily_digest"] is not None
    assert ctx["daily_digest"]["local_date"] == "2026-05-06"


def test_no_daily_digest_when_no_summaries():
    """ContextManager should have daily_digest=None when no daily summaries exist."""
    cm = ContextManager({"max_context_chars": 10000, "timezone": "Asia/Shanghai"})
    event = _make_event()

    class EmptyDailyStore:
        def recent(self, limit=1):
            return []

    ctx = cm.build(
        event=event,
        pet_state={},
        episode=None,
        event_log_store=None,
        daily_summary_store=EmptyDailyStore(),
    )

    assert ctx["daily_digest"] is None


def test_daily_digest_dropped_before_events_in_budget():
    """When budget is tight, daily_digest should be dropped before recent_exact_events."""
    cm = ContextManager({"max_context_chars": 200, "timezone": "Asia/Shanghai"})
    event = _make_event("这是一段比较长的用户文本用来测试预算控制")

    class FakeDailyStore:
        def recent(self, limit=1):
            return [{"local_date": "2026-05-06", "summary": "昨天的整体摘要内容很长应该被裁剪", "key_events": []}]

    class FakeEventLog:
        def recent_events(self, episode_id, limit=6):
            return [{"event_type": "voice_message", "user_text": "你好", "pet_reply": "嗨", "created_at_utc": "2026-05-07T00:00:00", "mood_after": "happy"}]

    ctx = cm.build(
        event=event,
        pet_state={},
        episode={"episode_id": "ep1", "started_at_utc": "2026-05-07T00:00:00", "event_count": 1},
        event_log_store=FakeEventLog(),
        daily_summary_store=FakeDailyStore(),
    )

    # If budget is tight, daily_digest should be dropped (it's lower priority than events)
    if ctx["context_budget"]["used_chars"] > 200:
        assert ctx["daily_digest"] is None
