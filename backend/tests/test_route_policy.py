from __future__ import annotations

from app.runtime.route_policy import RECALL_KEYWORDS, RouteDecision, decide_route


def test_button_event_fast_reply():
    d = decide_route("pet_head", "runtime", "")
    assert d.route == "unified"
    assert d.context_profile == "unified"
    assert d.provider_profile == "fast_llm"
    assert d.allow_tools is False


def test_recall_keyword_non_thinking_stays_fast_reply():
    """Recall keywords do not create a separate recall path."""
    d = decide_route("text_message", "text_fast", "昨天我说了什么")
    assert d.route == "unified"
    assert d.context_profile == "unified"
    assert d.provider_profile == "fast_llm"


def test_recall_keyword_thinking_mode_is_ignored():
    d = decide_route("text_message", "text_fast", "昨天说了什么", thinking_mode=True)
    assert d.route == "unified"
    assert d.context_profile == "unified"


def test_all_recall_keywords_non_thinking():
    """All RECALL_KEYWORDS should stay fast_reply when thinking_mode=False."""
    for kw in RECALL_KEYWORDS:
        d = decide_route("text_message", "text_fast", f"我们{kw}什么")
        assert d.route == "unified", f"keyword '{kw}' unexpectedly changed route"
        assert d.context_profile == "unified"


def test_weather_keyword_no_tools():
    """V1.3: tool keywords route to fast_reply with no tools."""
    d = decide_route("text_message", "text_fast", "今天适合出门吗")
    assert d.route == "unified"
    assert d.context_profile == "unified"
    assert d.allow_tools is False
    assert d.max_tool_calls == 0


def test_thinking_mode():
    d = decide_route("text_message", "text_fast", "你好", thinking_mode=True)
    assert d.route == "unified"
    assert d.context_profile == "unified"
    assert d.provider_profile == "fast_llm"
    assert d.allow_tools is False


def test_proactive_event():
    d = decide_route("morning", "proactive", "")
    assert d.route == "unified"
    assert d.context_profile == "unified"
    assert d.allow_tools is False


def test_normal_text_fast_reply():
    d = decide_route("text_message", "text_fast", "你好呀")
    assert d.route == "unified"
    assert d.context_profile == "unified"


def test_code_keyword_fast_reply():
    """V1.3: complex keywords route to fast_reply (suggest Thinking Mode in prompt)."""
    d = decide_route("text_message", "text_fast", "帮我写一个排序算法")
    assert d.route == "unified"
    assert d.context_profile == "unified"
    assert d.allow_tools is False


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
        assert d.route == "unified", f"route={d.route} for {args}"


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
    """Client thinking mode no longer changes provider choice."""
    cases = [
        ("text_message", "text_fast", "你好", False, "fast"),
        ("text_message", "text_fast", "你好", True, "fast"),
        ("text_message", "text_fast", "帮我写一个排序算法", False, "fast"),
        ("morning", "proactive", "", False, "fast"),
    ]
    for event_type, source, text, thinking, expected_brain in cases:
        d = decide_route(event_type, source, text, thinking_mode=thinking)
        assert d.brain == expected_brain, f"brain={d.brain} for {text!r}, expected {expected_brain}"
