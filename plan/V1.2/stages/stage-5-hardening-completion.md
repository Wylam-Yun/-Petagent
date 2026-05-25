# Stage 5 Completion: Full Local Verification And Hardening

## Summary
Stage 5 is complete. All user-visible Momo references have been renamed to 豆豆 across the entire codebase. Remaining "momo" references are intentional compatibility (event IDs, function names, config keys, backward-compatible wake phrases).

## Test Results
```
Frontend: 17 files, 119 tests — all passed
Frontend build: succeeded (JS ~206KB, spritesheet 1.7MB)
Backend: 549 passed, 24 skipped
```

## Renames Completed in Stage 5

### Frontend production code
- `VoiceButton.tsx`: 5 error/status messages ("按住久一点，豆豆才听得到", "豆豆没太听清", "语音识别暂时不太灵，但豆豆还在听", "豆豆刚刚只听到一点点", "豆豆在说")
- `StatusBar.tsx`: aria-label "豆豆状态"
- `PetFace.tsx`: aria-label "豆豆表情"

### Backend production code
- `api/voice.py`: fallback error reply
- `api/text.py`: fallback error reply
- `api/activation.py`: fallback reply
- `api/memory.py`: reset greeting reply + comment
- `config.py`: default pet_name fallback
- `pet/state.py`: default_state() and PetStateStore.__init__() defaults
- `providers/llm_mimo.py`: MockLLMProvider reply
- `providers/tts_mimo.py`: VOICE_PROMPT text
- `providers/audio_omni.py`: build_audio_prompt() text
- `runtime/memory_curator.py`: CURATOR_SYSTEM_PROMPT text
- `runtime/proactive.py`: event description
- `runtime/proactive_scheduler.py`: offline message

### Test fixtures (15 backend + 5 frontend files)
All test data using "Momo" in reply strings, state names, descriptions, and assertions updated to "豆豆".

## Remaining Momo References (Intentional Compatibility)
- Event IDs: `praise_momo`, `feed_momo`, `play_with_momo` (types, rules, guard, interaction_catalog, TouchArea)
- Function names: `wakeMomo()`, `exitMomo()` (api.ts, App.tsx)
- Config keys: `momo_memories_path`, `momo_memories` (config.yaml, memory_cards.py, context_manager.py)
- Wake phrases: `hi momo`, `hey momo`, `momo休息吧` (activation.ts, config.yaml)
- ASR normalization: `默默|摸摸 → momo` (activation.py)
- `test_live_nubia.py`: runs against live phone, left as-is pending phone availability

## Security Audit
- No API keys, .env content, tokens, or database content in diff
- No secrets committed
