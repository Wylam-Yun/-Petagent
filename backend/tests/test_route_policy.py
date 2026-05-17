from __future__ import annotations

from app.runtime.route_policy import RECALL_KEYWORDS, RouteDecision, decide_route


def test_button_event_fast_companion():
    d = decide_route("pet_head", "runtime", "")
    assert d.route == "fast"
    assert d.context_profile == "fast_companion"
    assert d.provider_profile == "fast_llm"
    assert d.allow_tools is False


def test_recall_keyword_non_thinking_stays_fast():
    """Recall keywords in non-thinking mode should stay on fast path."""
    d = decide_route("text_message", "text_fast", "昨天我说了什么")
    assert d.route == "fast"
    assert d.context_profile == "fast_companion"
    assert d.provider_profile == "fast_llm"


def test_recall_keyword_thinking_mode_goes_slow():
    """Recall keywords with thinking_mode should route to long_task."""
    d = decide_route("text_message", "text_fast", "昨天说了什么", thinking_mode=True)
    assert d.route == "slow"
    assert d.context_profile == "long_task"


def test_all_recall_keywords_non_thinking():
    """All RECALL_KEYWORDS should stay fast when thinking_mode=False."""
    for kw in RECALL_KEYWORDS:
        d = decide_route("text_message", "text_fast", f"我们{kw}什么")
        assert d.route == "fast", f"keyword '{kw}' unexpectedly routed to slow"
        assert d.context_profile == "fast_companion"


def test_weather_keyword():
    d = decide_route("text_message", "text_fast", "今天适合出门吗")
    assert d.route == "fast"
    assert d.context_profile == "tool"
    assert d.allow_tools is True
    assert d.max_tool_calls == 2


def test_thinking_mode_slow():
    d = decide_route("text_message", "text_fast", "你好", thinking_mode=True)
    assert d.route == "slow"
    assert d.context_profile == "long_task"
    assert d.provider_profile == "slow_llm"


def test_proactive_event():
    d = decide_route("morning", "proactive", "")
    assert d.route == "fast"
    assert d.context_profile == "proactive"
    assert d.allow_tools is False


def test_normal_text_fast_companion():
    d = decide_route("text_message", "text_fast", "你好呀")
    assert d.route == "fast"
    assert d.context_profile == "fast_companion"


def test_code_keyword_long_task():
    d = decide_route("text_message", "text_fast", "帮我写一个排序算法")
    assert d.route == "slow"
    assert d.context_profile == "long_task"
    assert d.allow_tools is True


def test_route_only_fast_or_slow():
    cases = [
        ("pet_head", "runtime", ""),
        ("text_message", "text_fast", "昨天说了什么"),
        ("text_message", "text_fast", "今天出门吗"),
        ("text_message", "text_fast", "你好", True),
        ("morning", "proactive", ""),
        ("text_message", "text_fast", "你好呀"),
        ("text_message", "text_fast", "帮我写一个排序"),
    ]
    for args in cases:
        d = decide_route(*args)
        assert d.route in ("fast", "slow"), f"route={d.route} for {args}"


def test_all_decisions_have_required_fields():
    d = decide_route("text_message", "text_fast", "你好")
    assert isinstance(d, RouteDecision)
    assert d.route
    assert d.context_profile
    assert d.provider_profile
    assert isinstance(d.allow_tools, bool)
    assert isinstance(d.max_tool_calls, int)
    assert d.reason
