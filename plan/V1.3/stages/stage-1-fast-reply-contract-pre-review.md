# Stage 1 Pre-Implementation Review

**Date:** 2026-05-26
**Result:** FIX (15 issues found)

## Issues Found

1. **brain.py hardcodes build_pet_messages()** — dispatcher cannot route fast reply to a different prompt builder without modifying brain.py
2. **guard.py has no fast reply guard path** — guard_action() returns full PetAction; FastReplyAction needs its own guard with sanitization, whitelist, fallback
3. **Dispatcher assumes PetAction fields** — state_delta, state_affect, voice_style, memory candidates all accessed unconditionally
4. **FastReplyAction missing voice_style** — spec says "voice_style: optional, default soft"; dispatcher needs it for TTS
5. **Context Manager doesn't recognize fast_reply/thinking profiles** — falls through to defaults with daily_digest, episode_summaries, important_quotes enabled
6. **Prompt Builder doesn't recognize fast_reply/thinking profile names** — no mode-specific instructions appended
7. **Four test files break from profile name changes** — test_agent_run.py, test_memory_cards.py, test_interaction_catalog.py, test_phase2_agent_run.py
8. **Voice Pipeline hardcodes "slow" in 6 places** — route name, source strings, requested_route validation
9. **Text Pipeline hardcodes "slow" route name** — source string construction, brain field comparison
10. **RouteDecision.brain field values unspecified** — plan renames route but doesn't specify if brain values change
11. **asr_failed_hint field not described in detail** — what value, how populated, relationship to fallback_reason
12. **Fast reply dispatcher must still persist state** — mood update, last_interaction_at, CAS save, event log
13. **build_thinking_messages() not mentioned** — spec lists 4 prompt builders; plan should note deferral
14. **local_reaction route absent** — spec includes it; plan should note deferral to Stage 4
15. **test_text_chat.py line 89 asserts skills_used for weather keyword** — test function name not listed explicitly

## Resolution

All issues addressed in updated plan (v2).
