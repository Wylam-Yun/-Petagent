# Stage 3 Completion: Main UI Integration And Action Button Collapse

## Summary
Stage 3 is complete. DoudouSprite replaces PetFace in the main UI. Behavior director controls the visible sprite. TouchArea is collapsed behind a "更多互动" toggle button.

## Files Modified
- `frontend/src/App.tsx` — replaced PetFace with DoudouSprite, wired BehaviorDirector, added tap handler, ambient life loop, collapsed TouchArea behind toggle, renamed Momo->豆豆 in UI copy
- `frontend/src/styles.css` — added .doudou-sprite, .doudou-sprite--fallback, .more-toggle-btn styles
- `frontend/src/App.test.tsx` — updated tests for sprite-based UI, tap local reaction, more menu toggle

## Test Results
```
cd frontend && npm test -- --run
17 test files, 119 tests — all passed

cd frontend && npm run build
tsc && vite build — succeeded (spritesheet.webp now in dist)
```

## Preserved
- VoiceButton, TextInputBar, VoiceModeToggle all still functional
- Audio job polling, heartbeat, proactive behavior unchanged
- All existing API calls preserved
- TouchArea still accessible via "更多互动" toggle

## Spec Requirements Met
- Normal UI shows sprite-based Doudou, not kaomoji ✓
- Tap on sprite shows immediate local reaction ✓
- TouchArea grid collapsed behind toggle ✓
- Voice/text/audio paths preserved ✓
- Nubia live verification: pending
