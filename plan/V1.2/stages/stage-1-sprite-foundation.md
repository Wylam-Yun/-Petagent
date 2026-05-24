# Stage 1: Sprite Asset And Renderer Foundation

## Goal
- Copy sprite assets into frontend
- Add sprite manifest/types (`DoudouAction`, sprite animation definitions)
- Add `DoudouSprite` component with frame animation
- Render nonblank Doudou sprite with stable dimensions and fallback

## Files To Touch
- `frontend/src/assets/spritesheet.webp` (copy from source)
- `frontend/src/pet/doudouSprites.ts` (manifest, types, animation definitions)
- `frontend/src/components/DoudouSprite.tsx` (sprite renderer component)
- `frontend/src/components/DoudouSprite.test.tsx` (tests)
- `frontend/src/pet/doudouSprites.test.ts` (manifest tests)

## Behavior Goals
- `DoudouSprite` renders correct background-position frame from spritesheet
- Supports loop (idle, waiting, review, running*) and one-shot (waving, jumping, failed) animations
- One-shot returns to `idle` on completion
- `image-rendering: pixelated` for crisp pixel art
- Stable 192x208 aspect ratio dimensions
- Fallback if asset fails to load
- No conversation/runtime code changed

## Tests
- Manifest exposes 1536x1872, 192x208, 8 cols, 9 rows
- DoudouSprite renders correct background image, size, position, dimensions
- Asset-error fallback path
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

## Rollback
Delete the new files: `doudouSprites.ts`, `DoudouSprite.tsx`, asset copy, tests.

## Risks
- WebP support on old Android WebView (Vite legacy plugin targets Chrome 49+ which supports WebP)
- Spritesheet memory on low-end devices (~1.7MB WebP)
