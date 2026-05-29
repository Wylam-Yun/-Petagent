# V1.4 Stage 1 Completion: Action Contract And Safe Fallbacks

**Date:** 2026-05-29
**Commit:** `b3741cb`

## Result

Stage 1 introduced the V1.4 product action contract without replacing
production sprite art.

Every accepted frontend action now resolves to a concrete existing atlas row.
This means backend/LLM output such as `happy`, `comfort`, `listen`, `speak`,
`remember`, `confused`, `nap`, or `sneak_eat` will not produce a blank sprite
even though final V1.4 art is not integrated yet.

## Changed Files

- `frontend/src/pet/doudouSprites.ts`
  - added V1.4 product action names;
  - exported legacy/product action arrays;
  - added product-to-legacy fallback map;
  - made `doudouManifest.animations` exhaustive for all accepted actions.
- `frontend/src/pet/doudouBehaviorPlan.ts`
  - uses frontend action whitelist from `doudouSprites`;
  - accepts product actions in behavior plans;
  - updates intent/mood/phase fallbacks to product action names.
- `backend/app/runtime/actions.py`
  - expands `ALLOWED_BEHAVIOR_ACTIONS`.
- `backend/app/pet/guard.py`
  - adds default durations for product actions.
- `backend/app/pet/prompt_builder.py`
  - updates full, fast, and thinking response action schemas.
- `config/pet_persona.yaml`
  - adds product actions to allowed behavior actions.
- frontend/backend tests updated for product actions and fallback rows.

## Verification

Frontend:

```bash
npm --prefix frontend test -- --run
```

Result:

```text
17 passed, 129 tests passed
```

Backend:

```bash
pytest backend/tests/test_pet_guard.py \
  backend/tests/test_fast_reply_contract.py \
  backend/tests/test_stage5_behavior.py \
  backend/tests/test_thinking_prompt_contract.py
```

Result:

```text
53 passed
```

Focused Stage 1 assertions now prove:

- all accepted frontend actions have manifest definitions;
- product actions map to existing atlas rows;
- invalid actions are still rejected;
- backend guard accepts V1.4 product actions;
- fast reply guard accepts V1.4 product actions;
- prompt schemas expose the product action vocabulary.

## Completion Review

No blocker found.

Stage 1 intentionally does not make fast actions visible for a minimum duration.
`App.applyPetResponse()` can still move into `waiting_voice` quickly and
overwrite visible action timing. That is the Stage 2 problem and remains open
by design.

Stage 1 also intentionally does not ship generated action art. The runtime still
uses the existing `1536x1872` atlas, and product actions are semantic aliases
until final art passes repack and Nubia rendering checks.

## Risks Carried Forward

- `speaking` and `waiting_voice` still visually use old phase behavior until
  Stage 2 changes playback timing.
- Some product actions such as `watch_tv` and `sneak_eat` currently share
  generic fallback rows, so the semantic action may not yet be visually obvious.
- Generated art remains concept-only and should not enter production assets
  without a separate atlas acceptance pass.

## Acceptance Criteria Audit

- Product actions documented and whitelisted: yes.
- Legacy actions still valid: yes.
- Invalid actions rejected: yes.
- Every accepted frontend action resolves to a concrete sprite row: yes.
- No runtime blank sprite from accepted V1.4 action: yes, covered by manifest
  exhaustiveness tests.
- Tests pass: yes.
- Ready for stage commit and push: yes.
