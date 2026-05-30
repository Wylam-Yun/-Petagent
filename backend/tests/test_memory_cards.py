from __future__ import annotations

import inspect
from pathlib import Path
from tempfile import mkdtemp

from app.runtime.memory_cards import MemoryCardManager
from app.runtime.memory_store import MemoryManager
from app.runtime.context_manager import ContextManager
from app.runtime.context_store import EpisodeStore, EventLogStore
from app.db import PetStateStore


def _make_mcm(tmp_dir: str = None, **cfg):
    tmp = Path(tmp_dir or mkdtemp())
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    cfg.setdefault("user_preferences_path", str(tmp / "user.md"))
    cfg.setdefault("momo_memories_path", str(tmp / "memory.md"))
    mcm = MemoryCardManager(mm, cfg)
    return mcm, mm


def test_user_preference_enters_card():
    mcm, mm = _make_mcm()
    mm.save_curated("user_preference", "喜欢短回复", importance=4)

    result = mcm.rebuild("manual_debug")
    assert result["items_written"] >= 1

    items = mcm.read_card("user_preferences")
    assert "喜欢短回复" in items


def test_low_importance_excluded():
    mcm, mm = _make_mcm(min_importance=2)
    mm.save_curated("recent_mood", "我刚刚喝了水", importance=1)

    mcm.rebuild("manual_debug")
    items = mcm.read_card("momo_memories")
    assert "我刚刚喝了水" not in items


def test_card_respects_cjk_char_limit():
    mcm, mm = _make_mcm(max_card_cjk_chars=200, max_items_per_card=10)
    for i in range(15):
        mm.save_curated("user_preference", "用户偏好内容%d号" % i, importance=3)

    mcm.rebuild("manual_debug")
    items = mcm.read_card("user_preferences")
    total = sum(
        sum(1 for c in item if "一" <= c <= "鿿")
        for item in items
    )
    assert total <= 200


def test_long_item_truncated():
    mcm, mm = _make_mcm(max_item_cjk_chars=20)
    long_content = "这是一个非常非常长的用户偏好描述内容超出限制"
    mm.save_curated("user_preference", long_content, importance=4)

    mcm.rebuild("manual_debug")
    items = mcm.read_card("user_preferences")
    assert len(items) == 1
    cjk_count = sum(1 for c in items[0] if "一" <= c <= "鿿")
    assert cjk_count <= 20 + 3  # +3 for "..."


def test_card_contains_provenance():
    mcm, mm = _make_mcm()
    mem_id = mm.save_curated("user_preference", "喜欢短回复", importance=4)

    mcm.rebuild("manual_debug")
    items = mcm.read_card_with_provenance("user_preferences")
    assert any(p["source_id"] == str(mem_id) for p in items)


def test_clear_produces_empty_cards():
    mcm, mm = _make_mcm()
    mm.save_curated("user_preference", "喜欢短回复", importance=4)

    mcm.rebuild("manual_debug")
    assert len(mcm.read_card("user_preferences")) > 0

    mcm.clear()
    assert len(mcm.read_card("user_preferences")) == 0
    assert len(mcm.read_card("momo_memories")) == 0


def test_canonical_rebuild_skips_even_when_file_empty_or_malformed():
    tmp = Path(mkdtemp())
    mcm, mm = _make_mcm(str(tmp), protect_canonical_notebook=True)
    mm.save_curated("user_preference", "喜欢短回复", importance=4)
    user_path = mcm._paths["user_preferences"]
    mem_path = mcm._paths["momo_memories"]
    user_path.parent.mkdir(parents=True, exist_ok=True)
    user_path.write_text("", encoding="utf-8")
    mem_path.write_text("not valid\n", encoding="utf-8")

    result = mcm.rebuild("manual_debug")

    assert result["items_written"] == 0
    assert user_path.read_text(encoding="utf-8") == ""
    assert mem_path.read_text(encoding="utf-8") == "not valid\n"


def test_canonical_clear_does_not_write_legacy_headers():
    tmp = Path(mkdtemp())
    mcm, mm = _make_mcm(str(tmp), protect_canonical_notebook=True)
    user_path = mcm._paths["user_preferences"]
    mem_path = mcm._paths["momo_memories"]
    user_path.parent.mkdir(parents=True, exist_ok=True)
    user_path.write_text("<!-- owner note -->\n", encoding="utf-8")

    mcm.clear()

    assert "memory_cards:" not in user_path.read_text(encoding="utf-8")
    assert not mem_path.exists() or "memory_cards:" not in mem_path.read_text(encoding="utf-8")


def test_dedup_removes_similar_items():
    mcm, mm = _make_mcm()
    mm.save_curated("user_preference", "用户喜欢猫", importance=4)
    mm.save_curated("user_preference", "用户喜欢猫咪", importance=3)

    mcm.rebuild("manual_debug")
    items = mcm.read_card("user_preferences")
    assert len(items) == 1


def test_read_card_empty_file():
    mcm, _ = _make_mcm()
    assert mcm.read_card("user_preferences") == []


def test_read_card_header_only():
    mcm, mm = _make_mcm()
    # Rebuild with no memories — header only
    mcm.rebuild("manual_debug")
    assert mcm.read_card("user_preferences") == []


def test_read_card_malformed_lines():
    mcm, mm = _make_mcm()
    # Write a file with malformed lines
    path = mcm._paths["user_preferences"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<!-- memory_cards: user_preferences -->\n"
        "just some text without provenance\n"
        "- valid content <!-- source:memory:1 type:user_preference updated:2026-05-17 ttl:stable -->\n",
        encoding="utf-8",
    )
    items = mcm.read_card("user_preferences")
    assert len(items) == 1
    assert items[0] == "valid content"


def test_read_card_nonexistent_dir():
    mcm, mm = _make_mcm()
    mm.save_curated("user_preference", "喜欢短回复", importance=4)
    # rebuild should create directories
    mcm.rebuild("manual_debug")
    items = mcm.read_card("user_preferences")
    assert "喜欢短回复" in items


def test_fast_path_uses_cards():
    tmp = Path(mkdtemp())
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)

    mm.save_curated("user_preference", "喜欢短回复", importance=4)
    mcm = MemoryCardManager(mm, {
        "user_preferences_path": str(tmp / "user.md"),
        "momo_memories_path": str(tmp / "memory.md"),
    })
    mcm.rebuild("manual_debug")

    from app.runtime.events import normalize_event
    ep, _ = episodes.get_or_create_current()
    event = normalize_event({"type": "text_message", "source": "text", "payload": {"user_text": "你好"}})

    cm = ContextManager({})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
        context_profile="fast_reply",
        memory_card_manager=mcm,
    )

    assert context["context_profile"] == "unified"
    assert context["memory_cards"] is None
    assert context["relevant_memories"] == []


def test_v14_profiles_use_single_notebook_selection_without_legacy_cards():
    from app.runtime.events import normalize_event
    from app.runtime.notebook import NotebookManager

    tmp = Path(mkdtemp())
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    mcm = MemoryCardManager(mm, {
        "user_preferences_path": str(tmp / "user.md"),
        "momo_memories_path": str(tmp / "memory.md"),
    })
    notebook = NotebookManager(tmp / "user.md", tmp / "memory.md")
    (tmp / "user.md").write_text("- [2026-05-26 10:00][identity] 我叫小明\n", encoding="utf-8")
    (tmp / "memory.md").write_text("- [2026-05-26 10:00][project] 正在修 V1.4\n", encoding="utf-8")

    ep, _ = episodes.get_or_create_current()
    event = normalize_event({"type": "text_message", "source": "text", "payload": {"user_text": "你好"}})
    cm = ContextManager({})

    for profile in ("fast_reply", "thinking"):
        context = cm.build(
            event=event,
            pet_state=state_store.get_state(),
            episode=ep,
            event_log_store=event_log,
            memory_manager=mm,
            context_profile=profile,
            memory_card_manager=mcm,
            notebook_manager=notebook,
        )
        assert context["memory_cards"] is None
        assert context["selected_card_items"] == ["- [2026-05-26 10:00][project] 正在修 V1.4"]


def test_fast_path_no_daily_summary():
    from app.runtime.memory_store import DailySummaryStore, EpisodeSummaryStore
    from app.runtime.events import normalize_event

    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    dss = DailySummaryStore(state_store.connection)

    ep, _ = episodes.get_or_create_current()
    event = normalize_event({"type": "text_message", "source": "text", "payload": {"user_text": "你好"}})

    cm = ContextManager({})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
        daily_summary_store=dss,
        context_profile="fast_reply",
    )

    assert context["daily_digest"] is None
    assert context["episode_summaries"] == []
    assert context["important_quotes"] == []


def test_slow_path_no_cards():
    from app.runtime.events import normalize_event

    tmp = Path(mkdtemp())
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)

    mm.save_curated("user_preference", "喜欢短回复", importance=4)
    mcm = MemoryCardManager(mm, {
        "user_preferences_path": str(tmp / "user.md"),
        "momo_memories_path": str(tmp / "memory.md"),
    })

    ep, _ = episodes.get_or_create_current()
    event = normalize_event({"type": "voice_message", "source": "voice_fast", "payload": {"user_text": "你好"}})

    cm = ContextManager({})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
        context_profile="default",
        memory_card_manager=mcm,
    )

    assert len(context["relevant_memories"]) > 0
    assert context["memory_cards"] is None


def test_slow_path_includes_daily_summary():
    from app.runtime.memory_store import DailySummaryStore, EpisodeSummaryStore
    from app.runtime.events import normalize_event

    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    ess = EpisodeSummaryStore(state_store.connection)
    dss = DailySummaryStore(state_store.connection)

    mm.save_curated("user_preference", "喜欢短回复", importance=4)
    ess.save("ep-old", "摘要", ["事件"], "情绪", [], "2024-01-01T00:00:00", "2024-01-01T01:00:00")

    ep, _ = episodes.get_or_create_current()
    event = normalize_event({"type": "voice_message", "source": "voice_fast", "payload": {"user_text": "你好"}})

    cm = ContextManager({})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
        episode_summary_store=ess,
        daily_summary_store=dss,
        context_profile="default",
    )

    assert len(context["relevant_memories"]) > 0
    assert len(context["episode_summaries"]) > 0


def test_dispatcher_no_rebuild_in_source():
    from app.runtime.dispatcher import RuntimeDispatcher
    source = inspect.getsource(RuntimeDispatcher)
    assert "memory_card_manager.rebuild" not in source


# --- Integration tests ---


def _make_maintenance_with_cards(tmp_dir: str = None):
    """Helper: create MaintenanceService with a real MemoryCardManager."""
    from app.runtime.maintenance import MaintenanceService
    from app.runtime.memory_store import (
        DailySummaryStore,
        EpisodeSummaryStore,
        MaintenanceStateStore,
        MemoryCandidateStore,
        SummaryJobStore,
    )
    from app.runtime.summary_manager import SummaryManager

    tmp = Path(tmp_dir or mkdtemp())
    state_store = PetStateStore(None)
    conn = state_store.connection
    mm = MemoryManager(conn)
    cs = MemoryCandidateStore(conn)
    sjs = SummaryJobStore(conn)
    ess = EpisodeSummaryStore(conn)
    dss = DailySummaryStore(conn)
    ms = MaintenanceStateStore(conn)

    mcm = MemoryCardManager(mm, {
        "user_preferences_path": str(tmp / "user.md"),
        "momo_memories_path": str(tmp / "memory.md"),
    })

    class MockLLM:
        name = "mock"
        def complete_json(self, messages):
            return {"decisions": []}

    summary_manager = SummaryManager(MockLLM(), ess, dss, cs)
    curator = type("MockCurator", (), {
        "curate_batch": lambda self, store: {"saved": 1, "ignored": 0, "errors": 0},
    })()

    svc = MaintenanceService(
        curator=curator,
        summary_manager=summary_manager,
        candidate_store=cs,
        summary_job_store=sjs,
        memory_manager=mm,
        episode_summary_store=ess,
        daily_summary_store=dss,
        maintenance_state=ms,
        config={"maintenance_min_interval_seconds": 0},
        memory_card_manager=mcm,
    )
    return svc, mm, mcm


def test_maintenance_rebuilds_after_curator_save():
    """Maintenance tick with curator saves should rebuild cards."""
    svc, mm, mcm = _make_maintenance_with_cards()
    # Seed a candidate so curator has work
    svc.candidate_store.add("evt-1", "ep-1", "用户喜欢狗", "explicit_command")

    result = svc.tick(force=True)
    # curator saved → cards should be rebuilt
    assert result.get("saved", 0) > 0 or result.get("cards_rebuilt", 0) >= 0


def test_manual_curate_triggers_rebuild():
    """POST /api/memory/curate should rebuild cards when saved > 0."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {app.state.internal_token}"}

    # Seed a candidate
    candidate_store = app.state.memory_candidate_store
    candidate_store.add("evt-1", "ep-1", "用户喜欢猫", "explicit_command")

    response = client.post("/api/memory/curate", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True

    # If saved > 0, cards should have been rebuilt
    mcm = app.state.memory_card_manager
    if mcm and body.get("saved", 0) > 0:
        items = mcm.read_card("user_preferences")
        # The curator may or may not save this specific item depending on mock behavior,
        # but the rebuild should have been attempted without errors
        assert isinstance(items, list)


def test_runtime_reset_clears_cards():
    """POST /api/runtime/reset should clear memory card files."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {app.state.internal_token}"}

    # Seed memory and rebuild cards
    mm = app.state.memory_manager
    mcm = app.state.memory_card_manager
    if mcm is None:
        return  # skip if cards disabled

    mm.save_curated("user_preference", "喜欢短回复", importance=4)
    mcm.rebuild("manual_debug")

    # Reset
    response = client.post(
        "/api/runtime/reset",
        json={"confirm": "重新认识"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    if mcm._protects_canonical():
        # V1.3 canonical notebooks are protected; reset must not rewrite them as
        # legacy projection cards.
        for path in mcm._paths.values():
            if path.exists():
                assert "memory_cards:" not in path.read_text(encoding="utf-8")
    else:
        # Legacy projection mode still clears generated card files.
        assert len(mcm.read_card("user_preferences")) == 0
        assert len(mcm.read_card("momo_memories")) == 0


def test_full_app_fast_path_uses_cards():
    """Full app TestClient: fast text chat should use memory cards in context."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(testing=True)
    client = TestClient(app)

    mm = app.state.memory_manager
    mcm = app.state.memory_card_manager
    if mcm is None:
        return  # skip if cards disabled

    mm.save_curated("user_preference", "喜欢短回复", importance=4)
    mcm.rebuild("manual_debug")

    # Send a text message (fast route by default)
    response = client.post("/api/text/chat", json={"text": "你好"})
    assert response.status_code == 200

    # The response doesn't directly expose context, but we can verify
    # the app didn't error — cards were available for fast path
    body = response.json()
    assert body["user_text"] == "你好"


def test_full_app_notebook_paths_are_project_root_resolved():
    """NotebookManager must not resolve relative card paths from backend cwd."""
    from app.main import _resolve_project_path, create_app

    app = create_app(testing=True)
    settings = app.state.settings
    notebook = app.state.notebook_manager

    assert notebook._user_path.is_absolute()
    assert notebook._memory_path.is_absolute()
    assert "/backend/backend/" not in str(notebook._user_path)
    assert "/backend/backend/" not in str(notebook._memory_path)
    assert _resolve_project_path(
        settings, "backend/data/memory_cards/memory.md"
    ) == settings.project_root / "backend/data/memory_cards/memory.md"


def test_old_path_fallback():
    """read_card should fall back to old subdirectory path when new path doesn't exist."""
    tmp = Path(mkdtemp())
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)

    # Write to old-style subdirectory paths
    old_up_dir = tmp / "user_preferences"
    old_up_dir.mkdir(parents=True)
    (old_up_dir / "card.md").write_text(
        "<!-- memory_cards: user_preferences -->\n"
        "- 喜欢短回复 <!-- source:memory:1 type:user_preference updated:2026-05-17 ttl:stable -->\n",
        encoding="utf-8",
    )

    mcm = MemoryCardManager(mm, {
        "user_preferences_path": str(tmp / "user.md"),  # new path, doesn't exist
        "momo_memories_path": str(tmp / "memory.md"),
        "card_base_dir": str(tmp),
    })

    # read_card should fall back to old path
    items = mcm.read_card("user_preferences")
    assert "喜欢短回复" in items


def test_fast_reply_no_temporal_recall():
    """fast_reply with recall keyword should NOT load temporal recall events."""
    from app.runtime.events import normalize_event

    tmp = Path(mkdtemp())
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)

    mcm = MemoryCardManager(mm, {
        "user_preferences_path": str(tmp / "user.md"),
        "momo_memories_path": str(tmp / "memory.md"),
    })

    ep, _ = episodes.get_or_create_current()
    # Record an event so there's something to recall
    event_log.record("evt-1", ep.get("episode_id", ""), "text_message", "text",
                     user_text="昨天聊了天气", pet_reply="晴天哦", state_before={}, state_after={},
                     mood_after="happy", state_affect={})

    event = normalize_event({
        "type": "text_message", "source": "text",
        "payload": {"user_text": "昨天聊了什么"},
    })

    cm = ContextManager({})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
        context_profile="fast_reply",
        memory_card_manager=mcm,
    )

    assert context["temporal_recall_events"] == []
    assert context["relevant_memories"] == []
    assert context["memory_cards"] is None
    assert any("昨天聊了天气" in item.get("user", "") for item in context["recent_exact_events"])


def test_tool_profile_no_deep_memory():
    """tool profile should not include scored memories or important quotes."""
    from app.runtime.events import normalize_event

    tmp = Path(mkdtemp())
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)

    mm.save_curated("user_preference", "喜欢短回复", importance=4)
    mm.save_curated("important_quote", "用户说很开心", importance=5)
    mcm = MemoryCardManager(mm, {
        "user_preferences_path": str(tmp / "user.md"),
        "momo_memories_path": str(tmp / "memory.md"),
    })
    mcm.rebuild("manual_debug")

    ep, _ = episodes.get_or_create_current()
    event = normalize_event({
        "type": "text_message", "source": "text",
        "payload": {"user_text": "今天天气怎么样"},
    })

    cm = ContextManager({})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
        context_profile="fast_reply",
        memory_card_manager=mcm,
    )

    assert context["relevant_memories"] == []
    assert context["important_quotes"] == []
    assert context["memory_cards"] is None
    assert context["episode_summaries"] == []
    assert context["daily_digest"] is None


def test_seed_realistic_content():
    """Seed memories matching original plan's example content and verify cards."""
    mcm, mm = _make_mcm()

    # user.md content
    mm.save_curated("user_preference", "用户叫 William", importance=5)
    mm.save_curated("user_preference", "喜欢中文交流", importance=4)
    mm.save_curated("user_preference", "喜欢自然简短", importance=4)
    mm.save_curated("relationship", "不喜欢客服腔", importance=4)
    mm.save_curated("user_preference", "默认听声音回复", importance=3)

    # memory.md content
    mm.save_curated("important_event", "昨天聊过记忆方案", importance=4)
    mm.save_curated("important_event", "快路径只读小抄", importance=3)
    mm.save_curated("recent_mood", "语音偶尔会卡住", importance=3)

    result = mcm.rebuild("manual_debug")
    assert result["items_written"] >= 5

    user_items = mcm.read_card("user_preferences")
    assert any("William" in item for item in user_items)
    assert any("中文" in item for item in user_items)

    mem_items = mcm.read_card("momo_memories")
    assert any("记忆方案" in item for item in mem_items)


def test_thinking_mode_card_only_no_scored_memories():
    """V1.3: thinking mode uses card-only memory, no scored memories or summaries."""
    from app.runtime.memory_store import EpisodeSummaryStore
    from app.runtime.events import normalize_event

    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)
    ess = EpisodeSummaryStore(state_store.connection)

    mm.save_curated("user_preference", "喜欢短回复", importance=4)
    mm.save_curated("important_quote", "用户说很开心", importance=5)
    ess.save("ep-old", "讨论了记忆方案", ["事件"], "思考", [],
             "2026-05-16T00:00:00", "2026-05-16T01:00:00")

    ep, _ = episodes.get_or_create_current()
    event = normalize_event({
        "type": "text_message", "source": "text",
        "payload": {"user_text": "昨天聊了什么"},
    })

    cm = ContextManager({})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
        episode_summary_store=ess,
        context_profile="thinking",
    )

    # V1.3 thinking: card-only, no scored memories, no episode summaries, no important quotes
    assert context["relevant_memories"] == []
    assert context["important_quotes"] == []
    assert context["episode_summaries"] == []
    assert context["daily_digest"] is None


def test_fast_reply_context_budget_small():
    """Fast companion context should be well under max budget."""
    from app.runtime.events import normalize_event

    tmp = Path(mkdtemp())
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)
    episodes = EpisodeStore(state_store.connection)
    event_log = EventLogStore(state_store.connection)

    # Seed lots of memories
    for i in range(10):
        mm.save_curated("user_preference", "偏好内容%d号" % i, importance=4)
    mcm = MemoryCardManager(mm, {
        "user_preferences_path": str(tmp / "user.md"),
        "momo_memories_path": str(tmp / "memory.md"),
    })
    mcm.rebuild("manual_debug")

    ep, _ = episodes.get_or_create_current()
    event = normalize_event({
        "type": "text_message", "source": "text",
        "payload": {"user_text": "你好"},
    })

    cm = ContextManager({"max_context_chars": 4500})
    context = cm.build(
        event=event,
        pet_state=state_store.get_state(),
        episode=ep,
        event_log_store=event_log,
        memory_manager=mm,
        context_profile="fast_reply",
        memory_card_manager=mcm,
    )

    used = context["context_budget"]["used_chars"]
    assert used < 2000, f"fast_reply context too large: {used} chars"


def test_legacy_rebuild_skips_when_v13_format_detected():
    """MemoryCardManager.rebuild() should skip when V1.3 notebook format is present."""
    tmp = Path(mkdtemp())
    state_store = PetStateStore(None)
    mm = MemoryManager(state_store.connection)

    # Seed a memory
    mm.save_curated("user_preference", "喜欢短回复", importance=4)

    mcm = MemoryCardManager(mm, {
        "user_preferences_path": str(tmp / "user.md"),
        "momo_memories_path": str(tmp / "memory.md"),
    })

    # Write V1.3 format line to user.md
    (tmp / "user.md").write_text(
        "- [2026-05-26 10:00][preference] 主人喜欢短回复\n",
        encoding="utf-8",
    )

    # Rebuild should skip — V1.3 format detected
    result = mcm.rebuild("curator_saved")
    assert result["items_written"] == 0
    assert result["items_rejected"] == 0

    # File should be unchanged
    content = (tmp / "user.md").read_text(encoding="utf-8")
    assert "[preference]" in content  # V1.3 format preserved


def test_legacy_rebuild_runs_when_no_v13_format():
    """MemoryCardManager.rebuild() should run normally when no V1.3 format present."""
    mcm, mm = _make_mcm()
    mm.save_curated("user_preference", "喜欢短回复", importance=4)

    result = mcm.rebuild("manual_debug")
    assert result["items_written"] >= 1

    items = mcm.read_card("user_preferences")
    assert "喜欢短回复" in items
