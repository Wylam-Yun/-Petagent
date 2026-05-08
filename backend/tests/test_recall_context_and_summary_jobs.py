from datetime import datetime, timedelta

from app.pet.state import PetStateStore
from app.runtime.context_manager import ContextManager
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.runtime.events import PetEvent
from app.runtime.memory_store import SummaryJobStore


def test_recall_question_selects_recent_raw_events_from_previous_day():
    state_store = PetStateStore(None)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    cm = ContextManager(
        {
            "timezone": "Asia/Shanghai",
            "max_context_chars": 4500,
            "recall_event_limit": 6,
            "recall_lookback_hours": 48,
        }
    )

    yesterday_utc = datetime.utcnow() - timedelta(hours=20)
    old_episode, _ = episodes.get_or_create_current(now_utc=yesterday_utc.isoformat())
    event_log.record(
        event_id="evt-yesterday-weather",
        episode_id=old_episode["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="今天天气怎么样啊？",
        pet_reply="我看不到外面的天气呢。",
        created_at_utc=yesterday_utc.isoformat(),
        created_at_local=(yesterday_utc + timedelta(hours=8)).isoformat(),
    )
    event_log.record(
        event_id="evt-yesterday-story",
        episode_id=old_episode["episode_id"],
        event_type="voice_message",
        source="voice_fast",
        user_text="讲个故事给我听",
        pet_reply="从前有只小猫咪。",
        created_at_utc=(yesterday_utc + timedelta(minutes=5)).isoformat(),
        created_at_local=(yesterday_utc + timedelta(hours=8, minutes=5)).isoformat(),
    )

    # New current episode with no useful detail.
    new_episode, _ = episodes.get_or_create_current()
    event = PetEvent(
        type="voice_message",
        source="voice_fast",
        payload={"user_text": "昨天我们聊了啥？"},
    )
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=new_episode,
        event_log_store=event_log,
    )

    recalled = context.get("temporal_recall_events") or []
    assert any("天气" in item.get("user", "") for item in recalled)
    assert any("故事" in item.get("user", "") for item in recalled)
    assert context["context_budget"]["items_selected"] >= len(recalled)


def test_summary_job_records_error_and_is_retryable_until_attempt_limit():
    state_store = PetStateStore(None)
    jobs = SummaryJobStore(state_store.connection, max_attempts=2)
    job_id = jobs.enqueue("ep-failed")

    jobs.mark_failed(job_id, error_message="summary llm timeout")

    retryable = jobs.pending(limit=5)
    assert retryable[0]["id"] == job_id
    assert retryable[0]["attempt_count"] == 1
    assert retryable[0]["last_error"] == "summary llm timeout"

    jobs.mark_failed(job_id, error_message="summary llm timeout again")

    assert jobs.pending(limit=5) == []
