# V1.4 Stage 3 Completion: Autonomous Idle Life

**Date:** 2026-05-29
**Commit:** pending at time of writing

## Result

Stage 3 adds frontend-local autonomous idle life for 豆豆. After the user has
left 豆豆 idle long enough, 豆豆 can now lounge, groom, wander, nap, sneak eat,
or watch TV. These states are volatile UI behavior only and are not written to
memory.

When the user taps 豆豆 after an idle activity, 豆豆 reacts according to what was
interrupted, for example sleepy after `nap`, guilty/playful after `sneak_eat`,
or pretend-busy after `watch_tv`.

## Changed Files

- `frontend/src/pet/behaviorDirector.ts`
  - adds idle activity vocabulary and short/long idle thresholds;
  - prevents immediate idle activity on first startup tick;
  - suppresses idle activities while non-idle, busy, or document hidden;
  - tracks volatile `lastIdleActivity`;
  - returns activity-specific interruption reactions on next tap.
- `frontend/src/pet/behaviorDirector.test.ts`
  - covers short idle threshold;
  - covers long idle activities;
  - covers protected/busy/non-visible guards;
  - covers return reactions and state clearing.

## Verification

Focused frontend tests:

```bash
npm --prefix frontend test -- --run \
  src/pet/behaviorDirector.test.ts \
  src/App.test.tsx
```

Result:

```text
2 passed, 43 tests passed
```

Full frontend tests:

```bash
npm --prefix frontend test -- --run
```

Result:

```text
17 passed, 136 tests passed
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

The implementation keeps Nubia overhead low: the existing 5s ambient interval
is reused, and no backend request, storage write, or new polling loop is added.

The implementation intentionally does not persist idle activity. This matches
the V1.4 spec because `last_idle_activity` is runtime color, not long-term
memory.

## Risks Carried Forward

- Product actions still render through legacy atlas fallback rows until final
  V1.4 art is integrated.
- Distress override for text/voice content is handled by response actions and
  behavior plans, not by the idle tick itself. Protected phases still prevent
  idle activities during active user interaction.

## Acceptance Criteria Audit

- No autonomous activity during listening/waiting/speaking/errors/busy: yes.
- No autonomous activity before 60s idle threshold: yes.
- Short idle activities after threshold: yes.
- Long idle activities after 5 minutes: yes.
- Return/tap reaction reflects interrupted idle activity: yes.
- Idle state clears after return reaction: yes.
- Frontend tests and build pass: yes.
- Ready for stage commit and push: yes.
