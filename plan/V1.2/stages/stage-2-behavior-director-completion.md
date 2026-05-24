# Stage 2 Completion: Behavior Director And Fast Tap Contract

## Summary
Stage 2 is complete. Local behavior director and behavior plan validation are implemented.

## Files Created
- `frontend/src/pet/doudouBehaviorPlan.ts` — behavior plan types, validator (sanitize unknown actions/slots/durations, cap at 4 steps/8000ms), fallback mapping (intent -> mood -> phase)
- `frontend/src/pet/doudouBehaviorPlan.test.ts` — 16 tests for validator and fallback
- `frontend/src/pet/behaviorDirector.ts` — BehaviorDirector class: tap (single/repeated/overpoke), protected phases, ambient life, backend response handling, slot queue
- `frontend/src/pet/behaviorDirector.test.ts` — 25 tests for director

## Decision
Fast tap sync: **Option 3 (local-only tap for V1.2)**. Taps stay local, no backend call. Voice/text/deliberate actions use existing full runtime.

## Test Results
```
cd frontend && npm test -- --run
17 test files, 117 tests — all passed

cd frontend && npm run build
tsc && vite build — succeeded
```

## Spec Requirements Met
- Tap returns `waving` without network ✓
- Repeated tap escalates to `jumping` ✓
- Over-poke escalates to `failed` + cooldown ✓
- Tap does not set `busy=true` ✓ (director is stateless for busy)
- Tap does not disable voice/text ✓
- Protected phases not interrupted ✓
- Ambient tick only during idle/not busy/document visible ✓
- Valid model plan accepted, invalid sanitized ✓
- Fallback through intent -> mood -> phase ✓
- Nubia live verification: pending
