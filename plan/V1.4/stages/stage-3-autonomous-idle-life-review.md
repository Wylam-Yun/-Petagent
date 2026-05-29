# Stage 3 Main-Agent Plan Review

**Date:** 2026-05-29

## Review Scope

Reviewed:

- `plan/V1.4/doudou-living-pet-and-memory-v1-spec.md`
- `plan/V1.4/stages/stage-3-autonomous-idle-life.md`
- `frontend/src/pet/behaviorDirector.ts`
- `frontend/src/App.tsx`
- `frontend/src/pet/behaviorDirector.test.ts`

## Findings

No blocker found.

The plan keeps idle life frontend-local, which matches the spec's volatile
state direction and avoids unnecessary backend/storage work. It also keeps the
5s ambient tick, so there is no new high-frequency timer on Nubia.

The main edge risk is user return behavior conflicting with protected phases.
The plan keeps protected phase behavior first, so taps during listening,
waiting voice, or speaking remain non-interrupting.

The second edge risk is idle actions firing too soon after startup. The first
tick can still fire if no `lastUserInteraction` exists. The implementation
should initialize/schedule idle in a way that avoids an immediate life activity
on first render.

## Decision

Proceed with Stage 3 implementation in `BehaviorDirector` and frontend tests.
Do not persist idle activity or call backend APIs for idle life in this stage.
