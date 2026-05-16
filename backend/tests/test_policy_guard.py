from __future__ import annotations


def test_policy_guard_importable():
    from app.runtime.policy_guard import PolicyGuard
    guard = PolicyGuard()
    assert guard is not None
