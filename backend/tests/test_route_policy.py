from __future__ import annotations

from app.runtime.route_policy import RouteDecision, decide_route


def test_button_event_fast_reply():
    d = decide_route("pet_head", "runtime", "")
    assert d.route == "fast_reply"
    assert d.context_profile == "fast_reply"
    assert d.provider_profile == "fast_llm"
    assert d.allow_tools is False


def test_recall_keyword_thinking_mode_goes_thinking():
    """Recall keywords with thinking_mode should route to thinking."""
    d = decide_route("text_message", "text_fast", "昨天说了什么", thinking_mode=True)
    assert d.route == "thinking"
    assert d.context_profile == "thinking"


def test_keywords_do_not_change_default_chat_route():
    for text in [
        "昨天我说了什么",
        "今天适合出门吗",
        "帮我写一个排序算法",
        "请详细分析一下",
    ]:
        d = decide_route("text_message", "text_fast", text)
        assert d.route == "fast_reply"
        assert d.context_profile == "fast_reply"
        assert d.provider_profile == "fast_llm"
        assert d.allow_tools is False
        assert d.max_tool_calls == 0
        assert d.reason == "default companionship"


def test_thinking_mode():
    d = decide_route("text_message", "text_fast", "你好", thinking_mode=True)
    assert d.route == "thinking"
    assert d.context_profile == "thinking"
    assert d.provider_profile == "slow_llm"
    assert d.allow_tools is False


def test_proactive_event():
    d = decide_route("morning", "proactive", "")
    assert d.route == "fast_reply"
    assert d.context_profile == "proactive"
    assert d.allow_tools is False


def test_normal_text_fast_reply():
    d = decide_route("text_message", "text_fast", "你好呀")
    assert d.route == "fast_reply"
    assert d.context_profile == "fast_reply"


def test_route_only_fast_reply_or_thinking():
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
        assert d.route in ("fast_reply", "thinking"), f"route={d.route} for {args}"


def test_all_decisions_have_required_fields():
    d = decide_route("text_message", "text_fast", "你好")
    assert isinstance(d, RouteDecision)
    assert d.route
    assert d.context_profile
    assert d.provider_profile
    assert d.brain in ("fast", "slow")
    assert isinstance(d.allow_tools, bool)
    assert isinstance(d.max_tool_calls, int)
    assert d.reason


def test_brain_field_matches_route():
    """brain field should be 'slow' when route is 'thinking', 'fast' otherwise."""
    cases = [
        ("text_message", "text_fast", "你好", False, "fast"),
        ("text_message", "text_fast", "你好", True, "slow"),
        ("text_message", "text_fast", "帮我写一个排序算法", False, "fast"),
        ("morning", "proactive", "", False, "fast"),
    ]
    for event_type, source, text, thinking, expected_brain in cases:
        d = decide_route(event_type, source, text, thinking_mode=thinking)
        assert d.brain == expected_brain, f"brain={d.brain} for {text!r}, expected {expected_brain}"
