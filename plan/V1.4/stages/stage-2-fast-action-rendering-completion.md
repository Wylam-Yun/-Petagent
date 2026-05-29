# V1.4 Stage 2 Completion: Fast Action Rendering And Speaking Phase

**Date:** 2026-05-29
**Commit:** pending at time of writing

## Result

Stage 2 fixes the main fast-mode visual regression: backend fast actions are no
longer immediately erased by `waiting_voice` or `speaking` phase defaults.

When a fast reply includes an action such as `happy`, 豆豆 now keeps that action
visible for at least 600ms. Audio polling and playback still start immediately;
the hold is only a sprite rendering rule.

## Changed Files

- `frontend/src/pet/behaviorDirector.ts`
  - adds `FAST_ACTION_MIN_VISIBLE_MS = 600`;
  - records a temporary held fast action from backend `response.action`;
  - preserves the held action during immediate `waiting_voice` and `speaking`;
  - maps phase defaults to V1.4 product actions:
    - `listening` -> `listen`
    - `thinking`/`waiting_voice` -> `think`
    - `speaking` -> `speak`
    - `audio_error`/`error` -> `confused`.
- `frontend/src/App.tsx`
  - applies phase actions through `BehaviorDirector`;
  - uses a visual-only 600ms timer to release fast action to `think` or `speak`;
  - keeps audio polling/playback immediate;
  - replaces hardcoded `review`/`failed` audio fallbacks with product phase
    mapping.
- `frontend/src/components/DoudouSprite.tsx`
  - exposes `data-action` for reliable UI tests and debugging.
- frontend tests updated for fast-action hold and phase mappings.

## Verification

Focused frontend tests:

```bash
npm --prefix frontend test -- --run \
  src/pet/behaviorDirector.test.ts \
  src/pet/doudouBehaviorPlan.test.ts \
  src/components/DoudouSprite.test.tsx \
  src/App.test.tsx
```

Result:

```text
4 passed, 73 tests passed
```

Full frontend tests:

```bash
npm --prefix frontend test -- --run
```

Result:

```text
17 passed, 132 tests passed
```

Production frontend build:

```bash
npm --prefix frontend run build
```

Result:

```text
tsc && vite build passed
```

## Completion Review

No blocker found.

The Stage 2 fix is intentionally frontend-only. It does not change backend LLM
output, TTS enqueue, memory behavior, or generated art.

The new App-level test proves:

- `action=happy` is visible immediately after a fast reply with audio job;
- the audio job endpoint is polled before the 600ms visual hold expires;
- the sprite falls back to `think` after the hold while waiting for audio.

## Risks Carried Forward

- If a behavior plan includes a `speech` slot, that explicit slot still wins
  over the fast-action hold at playback start. This is intended because plans
  are more specific than a single fast action.
- Product actions still map to legacy atlas rows until final art integration.
- Voice recording button ergonomics and frontend layout are still separate
  design/implementation work.

## Acceptance Criteria Audit

- Fast response with `action=happy` remains visible during immediate
  `waiting_voice`: yes.
- Audio polling is not delayed by 600ms: yes, covered by App test.
- `speaking` fallback uses `speak`: yes.
- `audio_error` and `error` use `confused`: yes.
- Protected phase tap behavior remains guarded: yes, covered by director tests.
- Frontend tests and build pass: yes.
- Ready for stage commit and push: yes.
