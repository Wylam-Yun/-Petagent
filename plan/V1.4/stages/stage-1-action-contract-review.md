# Stage 1 Main-Agent Plan Review

**Date:** 2026-05-29

## Review Scope

Reviewed:

- `plan/V1.4/doudou-living-pet-and-memory-v1-spec.md`
- `plan/V1.4/stages/stage-1-action-contract.md`
- `frontend/src/pet/doudouSprites.ts`
- `frontend/src/pet/doudouBehaviorPlan.ts`
- `frontend/src/pet/behaviorDirector.ts`
- `backend/app/runtime/actions.py`
- `backend/app/pet/guard.py`
- `backend/app/pet/prompt_builder.py`
- `config/pet_persona.yaml`

## Findings

No blocker found.

The stage is correctly scoped as a contract and compatibility change. It does
not attempt to solve fast-action visibility, idle life timing, memory migration,
or production atlas replacement. That separation matters because the current
runtime still depends on a fixed `1536x1872` atlas with nine rows.

The main compatibility risk is accepting a product action in the backend while
the frontend has no animation definition for that action. The plan addresses
this by making frontend `doudouManifest.animations` exhaustive for every
accepted action.

The second risk is whitelist drift between frontend, backend guard, prompt
schema, and persona config. The implementation should keep tests focused on
new V1.4 actions such as `happy`, `comfort`, `listen`, `speak`, `remember`,
`confused`, `nap`, and `sneak_eat`.

## Decision

Proceed with Stage 1 implementation. Do not integrate generated art in this
stage. Use legacy atlas fallback rows until asset quality and Nubia rendering
are verified in a later stage.
