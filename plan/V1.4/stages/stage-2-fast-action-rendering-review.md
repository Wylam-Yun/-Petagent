# Stage 2 Main-Agent Plan Review

**Date:** 2026-05-29

## Review Scope

Reviewed:

- `plan/V1.4/doudou-living-pet-and-memory-v1-spec.md`
- `plan/V1.4/stages/stage-2-fast-action-rendering.md`
- `frontend/src/App.tsx`
- `frontend/src/pet/behaviorDirector.ts`
- `frontend/src/pet/behaviorDirector.test.ts`
- `frontend/src/App.test.tsx`

## Findings

No blocker found.

The key compatibility constraint is that the hold must be visual-only. Audio
polling and playback must continue immediately after the response arrives. The
plan satisfies this by putting the 600ms rule inside `BehaviorDirector` phase
selection rather than sleeping in `App.playResponseAudio()`.

The second risk is protected phases. The existing behavior prevents taps from
interrupting listening/waiting/speaking. Mapping those phases to product
actions does not change the protected-phase rule, only the sprite action chosen
while protected.

The third risk is behavior plans. Explicit behavior plan slots should still win
at speech boundaries. The plan keeps `advanceSlot()` semantics unchanged and
only replaces hardcoded `review` fallback with phase mapping.

## Decision

Proceed with Stage 2 implementation. Keep changes frontend-only unless tests
prove a backend contract adjustment is needed.
