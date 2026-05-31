from __future__ import annotations

import pytest

from app.pet.guard import guard_fast_reply_action
from app.runtime.expressions import (
    EXPRESSION_KEYS,
    EXPRESSION_MAP,
    activity_recommendation,
    expression_for_mood,
)


def test_expression_catalog_contains_v16_keys():
    assert "idle_soft" in EXPRESSION_KEYS
    assert "playful" in EXPRESSION_KEYS
    assert "wronged" in EXPRESSION_KEYS
    assert EXPRESSION_MAP["idle_soft"] == "(・ω・)"


def test_expression_for_mood_fallbacks():
    assert expression_for_mood("happy") == "happy"
    assert expression_for_mood("angry") == "annoyed"
    assert expression_for_mood("bad-mood") == "idle_soft"
    assert expression_for_mood(None) == "idle_soft"


def test_activity_recommendations_have_valid_expression_and_action():
    rec = activity_recommendation("sneak_snack")
    assert rec.activity == "sneak_snack"
    assert "playful" in rec.expression_keys
    assert "sneak_eat" in rec.actions


def test_fast_reply_accepts_expression_key():
    action = guard_fast_reply_action(
        {
            "reply": "我来看看。",
            "mood": "thinking",
            "expression_key": "thinking",
            "action": "think",
            "voice_style": "soft",
        }
    )
    assert action.expression_key == "thinking"
    assert action.mood == "thinking"


def test_fast_reply_invalid_expression_falls_back_to_mood():
    action = guard_fast_reply_action(
        {
            "reply": "我在。",
            "mood": "angry",
            "expression_key": "not-real",
        }
    )
    assert action.expression_key == "annoyed"
    assert action.mood == "angry"


def test_fast_reply_invalid_expression_and_mood_defaults_idle_soft():
    action = guard_fast_reply_action(
        {
            "reply": "我在。",
            "mood": "furious",
            "expression_key": "not-real",
        }
    )
    assert action.mood == "idle"
    assert action.expression_key == "idle_soft"


def test_fast_reply_sanitizes_self_name_to_first_person():
    action = guard_fast_reply_action(
        {
            "reply": "豆豆来看看。",
            "mood": "happy",
            "expression_key": "happy",
        }
    )
    assert "豆豆" not in action.reply
    assert action.reply == "我来看看。"


def test_fast_reply_rejects_kaomoji_in_tts_reply():
    for reply in ["我来啦(^▽^)", "我在(´・ω・)", "我超开心(≧▽≦)"]:
        with pytest.raises(Exception) as exc_info:
            guard_fast_reply_action(
                {
                    "reply": reply,
                    "mood": "happy",
                    "expression_key": "happy",
                }
            )
        assert getattr(exc_info.value, "error_class", "") == "llm_invalid_output"
