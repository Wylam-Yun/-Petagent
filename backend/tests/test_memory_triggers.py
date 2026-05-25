"""Tests for V1.3 memory trigger detection."""
from __future__ import annotations

from app.runtime.memory_triggers import detect_memory_triggers


def test_explicit_triggers_detected():
    assert "explicit" in detect_memory_triggers("记住这个")
    assert "explicit" in detect_memory_triggers("帮我记一下")


def test_preference_triggers_detected():
    assert "preference" in detect_memory_triggers("我喜欢咖啡")
    assert "preference" in detect_memory_triggers("我不喜欢下雨天")


def test_identity_triggers_detected():
    assert "identity" in detect_memory_triggers("我叫小明")
    assert "identity" in detect_memory_triggers("我的名字是豆豆")


def test_relationship_triggers_detected():
    assert "relationship" in detect_memory_triggers("今天我们去了公园")


def test_no_trigger_on_normal_text():
    assert detect_memory_triggers("你好") == []
    assert detect_memory_triggers("今天天气怎么样") == []


def test_multiple_triggers():
    result = detect_memory_triggers("我喜欢咖啡，记住这个")
    assert "preference" in result
    assert "explicit" in result


def test_empty_text():
    assert detect_memory_triggers("") == []
    assert detect_memory_triggers("   ") == []
