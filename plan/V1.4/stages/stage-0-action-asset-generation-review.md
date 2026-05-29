# Stage 0 Main-Agent Plan Review

**Date:** 2026-05-29

## Review Scope

Reviewed:

- `plan/V1.4/doudou-living-pet-and-memory-v1-spec.md`
- `plan/V1.4/stages/stage-0-action-asset-generation.md`
- existing generated `happy` experiment notes and outputs

## Findings

No blocker found.

The stage is safely scoped to `plan/V1.4` and does not touch runtime frontend or
backend code. This is appropriate because generated art quality and extraction
are not stable enough to ship directly.

The first batch should remain limited to:

```text
happy, greet, listen, speak, comfort, nap
```

Generating every proposed action before proving the workflow would produce too
many hard-to-review assets. After the first six have verdicts, continue with the
remaining actions.

Use single-frame reference, not the full atlas. The full atlas created noisy
edit behavior. Single-frame reference gave the first usable output.

Use chroma background in new prompts. White background damaged extraction
because 豆豆 is white.

Do not use Claude for plan review. Claude may execute narrow tasks, but the main
agent owns quality review and acceptance.

## Decision

Proceed to first-batch generation with ChatGPT web. Wait for each image to
finish in the browser and fetch the real generated `<img>` source. Do not trust
early files returned by `opencli chatgpt image`.

