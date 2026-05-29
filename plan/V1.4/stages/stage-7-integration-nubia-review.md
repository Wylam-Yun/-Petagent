# Stage 7 Main-Agent Plan Review

**Date:** 2026-05-29

## Review Scope

Reviewed:

- `plan/V1.4/doudou-living-pet-and-memory-v1-spec.md`
- `plan/V1.4/stages/stage-7-integration-nubia.md`
- `scripts/deploy_nubia.sh`
- `scripts/start.sh`
- `backend/tests/test_live_nubia.py`
- current Nubia ADB connection and runtime health.

## Findings

No blocker found.

The verification plan matches the V1.4 spec's strongest requirement: completion
requires Nubia live API success, not only local tests.

The deploy script intentionally excludes `plan/`, so documentation-only commits
after runtime deployment do not change the phone build hash. The authoritative
deployed code commit should therefore be recorded separately from final
documentation commits.

The main integration risk is preserved device data. The plan must inspect real
Nubia notebook files, not only API responses, because Stage 4/5 changed the
memory product model from split files to one canonical `memory.md`.

The second integration risk is the older relative-path behavior when uvicorn
runs from `backend/`. The completion review must verify that no active memory
source remains under `backend/backend/data/memory_cards`.

## Decision

Proceed with Stage 7 locally. Do not use Claude for review. Commit and push
after live checks and completion documentation pass.
