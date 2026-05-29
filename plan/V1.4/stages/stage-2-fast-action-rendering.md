# V1.4 Stage 2: Fast Action Rendering And Speaking Phase

**Date:** 2026-05-29
**Project:** `/Users/wylam/Documents/workspace/Petagent`

## Goal

Make fast replies visibly move 豆豆 before voice-phase visuals can overwrite the
response action. This directly addresses the user-visible issue where quick mode
returns an action but the sprite appears unchanged because `waiting_voice` or
`speaking` immediately forces `review`.

## Scope

In scope:

- preserve a backend fast `action` for at least 600ms;
- keep text bubble visible immediately;
- do not delay audio job polling or TTS generation;
- default `listening` to `listen`;
- default `waiting_voice`/`thinking` to `think`;
- default `speaking` to `speak`;
- default audio/error states to `confused`;
- update protected tap behavior to use the same phase map;
- add focused tests for phase mapping and fast action preservation.

Out of scope:

- new sprite art;
- autonomous idle activities;
- memory/notebook changes;
- backend provider changes;
- changing voice recording UX beyond visual action mapping.

## Design

Add a small visual hold inside `BehaviorDirector`.

When `onBackendResponse()` receives a valid `response.action`, it records:

```text
heldAction = action
heldUntil = now + 600ms
```

`onPhaseChange("waiting_voice")` returns the held action if the hold is still
active. This preserves the reaction while audio polling starts immediately in
parallel.

`advanceSlot("speech")` may still override the held action if the backend
provided a more specific behavior plan slot. If no speech slot exists,
`App.playResponseAudio()` should use `BehaviorDirector.phaseToAction("speaking")`
which becomes `speak`.

## Edge Rules

- Holds are only for backend fast `action`, not for local taps.
- Holds end on error phases and reset.
- Holds must not block polling, playback, or state updates.
- If a new backend response arrives, it replaces the old held action.
- If no fast action exists, behavior plan and fallback logic work as before.

## Implementation Plan

1. Update `BehaviorDirector`.
   - Add `FAST_ACTION_MIN_VISIBLE_MS = 600`.
   - Store `heldFastActionUntil`.
   - Let `onBackendResponse()` accept optional `now`.
   - Preserve held action during `waiting_voice` phase.
   - Map phase defaults to product actions.

2. Update `App.tsx`.
   - Pass `Date.now()` into `onBackendResponse()`.
   - Replace hardcoded `review` fallbacks during speech with phase mapping.
   - Replace hardcoded audio error `failed` with phase mapping.

3. Update frontend tests.
   - Phase mapping expects `listen`, `think`, `speak`, `confused`.
   - Backend fast action remains visible when entering `waiting_voice` before
     the 600ms hold expires.
   - After the hold expires, `waiting_voice` maps to `think`.
   - `speaking` fallback maps to `speak`.

4. Verify.
   - Run focused frontend tests.
   - Run full frontend test suite.

## Acceptance Criteria

- Fast response with `action=happy` remains the visible action during immediate
  `waiting_voice`.
- Audio polling is still started immediately; no 600ms backend/audio delay is
  introduced.
- `speaking` fallback uses `speak`.
- `audio_error` and `error` use `confused`.
- Protected phase taps do not regress.
- Frontend tests pass.
