# Stage 4 Completion: Doudou Naming, Persona, Activation, And Compatibility

## Summary
Stage 4 is complete. User-visible identity is now 豆豆. Backend schema extended with behavior_intent/behavior_plan. Guard sanitizes model behavior plans.

## Naming Audit Results

### Renamed to 豆豆 (user-visible)
- `config/app.yaml`: pet_name, initial state name, wake phrases (added 豆豆, kept old momo as aliases)
- `config/pet_persona.yaml`: name, species, system_prompt
- `backend/app/api/client_config.py`: progressive audio copy
- `backend/app/providers/proactive_rule.py`: all proactive reply copy
- `backend/app/pet/guard.py`: FALLBACK_ACTION reply
- `backend/app/pet/prompt_builder.py`: prompt references
- `backend/app/runtime/summary_manager.py`: summary prompt text
- `backend/app/runtime/interaction_catalog.py`: description text
- `backend/app/main.py`: FastAPI title, startup/shutdown logs
- `frontend/src/App.tsx`: all UI copy
- `frontend/src/components/PetBubble.tsx`: busy text
- `frontend/src/hooks/useClientConfig.ts`: default progressive copy, pet_name
- `frontend/src/pet/errorMessages.ts`: all error bubble text
- `frontend/src/pet/activation.ts`: added 豆豆 wake phrases

### Retained as compatibility (event ids, config keys, function names)
- `frontend/src/pet/types.ts`: `praise_momo`, `feed_momo`, `play_with_momo` event ids
- `frontend/src/pet/api.ts`: `wakeMomo()`, `exitMomo()` function names
- `config/app.yaml`: `momo_memories_path` config key, old momo wake phrases as aliases
- `backend/app/main.py`: `momo_memories` memory card key
- `backend/app/runtime/activation.py`: momo normalization alias

## Backend Schema Changes
- `actions.py`: Added `ALLOWED_BEHAVIOR_ACTIONS`, `ALLOWED_BEHAVIOR_SLOTS`, `ALLOWED_BEHAVIOR_INTENTS`, `BehaviorStep` model, `behavior_intent`/`behavior_plan` on `PetAction` and `PetResponse`
- `guard.py`: Added `_sanitize_behavior_plan()` and `_sanitize_behavior_intent()`, integrated into `guard_action()`
- `dispatcher.py`: Passes `behavior_intent`/`behavior_plan` from action to response
- `prompt_builder.py`: Updated `OUTPUT_SCHEMA_HINT` with behavior_intent/behavior_plan fields
- `pet_persona.yaml`: Added `behavior_intents`, `behavior_actions`, `behavior_slots` to allowed section

## Test Results
```
Frontend: 17 files, 119 tests — all passed
Frontend build: succeeded
Backend: 541 passed, 24 skipped
```
