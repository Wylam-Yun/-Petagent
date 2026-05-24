# Stage 2: Behavior Director And Fast Tap Contract

## Goal
- Add local behavior director with fast tap, repeated tap, over-poke, protected phases, ambient life
- Add frontend behavior-plan types, validator, fallback mapping, slot queue
- Implement tap backend sync strategy (option 3: local-only tap for V1.2)

## Decision: Fast Tap Sync
**Chosen: Option 3 — local-only tap for V1.2.**
Ordinary taps stay local (no backend call). Voice/text/deliberate actions continue using existing full runtime. This avoids adding a new endpoint and keeps taps instant.

## Files To Create
- `frontend/src/pet/doudouBehaviorPlan.ts` — behavior plan types, validator, fallback mapping
- `frontend/src/pet/doudouBehaviorPlan.test.ts` — validator/fallback tests
- `frontend/src/pet/behaviorDirector.ts` — local director with tap/phase/ambient/model-plan logic
- `frontend/src/pet/behaviorDirector.test.ts` — director tests

## Files To Modify
- `frontend/src/pet/types.ts` — add Doudou behavior plan types to PetResponse

## Tests (minimum)
- Tap returns `waving` without network
- Repeated tap escalates to `jumping`
- Over-poke escalates to `failed` + cooldown
- Tap does not set `busy=true`
- Tap does not disable voice/text
- Protected phases not interrupted
- Ambient tick only during idle/not busy
- Valid model behavior_plan accepted and queued by slot
- Unknown actions/slots/durations sanitized
- Missing plan falls back through intent -> mood -> phase
