# V1.4 Stage 1: Action Contract And Safe Fallbacks

**Date:** 2026-05-29
**Project:** `/Users/wylam/Documents/workspace/Petagent`

## Goal

Introduce V1.4 product action names across the frontend and backend without
shipping new art yet. New actions must be accepted by guards and prompts, and
the frontend must render every accepted action through a safe fallback to the
existing atlas.

## Scope

In scope:

- define V1.4 product action vocabulary in frontend action types;
- map product actions to existing sprite rows so no action renders blank;
- allow product actions in backend behavior plans and fast replies;
- update prompt/persona action schema so LLM can emit the new action names;
- add focused tests for whitelists, fallback rendering, and guard behavior;
- record stage completion and commit/push after tests pass.

Out of scope:

- changing fast-action minimum visible duration;
- changing `waiting_voice` or `speaking` phase timing;
- replacing production sprite assets;
- adding autonomous idle life timing;
- changing memory/notebook behavior.

## Product Action Fallback Map

Until a production V1.4 atlas exists, product actions render through existing
V1.2 sprite rows:

| Product action | Runtime fallback row |
| --- | --- |
| `lazy_idle` | `waiting` |
| `nap` | `waiting` |
| `sneak_eat` | `review` |
| `watch_tv` | `review` |
| `self_groom` | `idle` |
| `wander` | `running` |
| `greet` | `waving` |
| `happy` | `waving` |
| `tease` | `jumping` |
| `pretend_busy` | `review` |
| `listen` | `waiting` |
| `think` | `review` |
| `speak` | `review` |
| `remember` | `review` |
| `comfort` | `waving` |
| `confused` | `failed` |
| `deny` | `failed` |
| `excited` | `jumping` |

Legacy actions remain valid:

```text
idle, waiting, review, waving, jumping, failed, running, running-left, running-right
```

## Implementation Plan

1. Update `frontend/src/pet/doudouSprites.ts`.
   - Add product actions to `DoudouAction`.
   - Export legacy/product action arrays.
   - Build `doudouManifest.animations` so every valid action has a real
     animation definition.
   - Keep atlas dimensions and existing row metadata unchanged.

2. Update frontend behavior plan validation.
   - Reuse `DOUDOU_ACTIONS` rather than a duplicated local whitelist.
   - Add product-action durations.
   - Update intent, mood, and phase fallbacks to product actions where this
     stage is safe.

3. Update backend action contract.
   - Expand `ALLOWED_BEHAVIOR_ACTIONS`.
   - Add default durations for product actions.
   - Update fast/thinking/full prompt schemas and `config/pet_persona.yaml`.

4. Add tests.
   - Frontend: product actions are valid and render through fallback rows.
   - Frontend: behavior plans accept product actions and reject unknown actions.
   - Backend: guards accept product actions and still reject unknown actions.

5. Verify.
   - Run focused frontend tests for sprite and behavior plan.
   - Run focused backend guard/fast-reply tests.

## Acceptance Criteria

- Product actions are documented and whitelisted in frontend and backend.
- Legacy actions remain valid.
- Invalid actions are rejected by guards/validators.
- Every valid frontend action resolves to a concrete sprite row.
- No runtime blank sprite is possible because of an accepted V1.4 action.
- Tests pass for changed contracts.
- Stage completion doc records changed files, tests, and risks.
