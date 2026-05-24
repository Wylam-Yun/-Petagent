# Stage 3: Main UI Integration And Action Button Collapse

## Goal
- Replace PetFace with DoudouSprite in main UI
- Wire App.tsx to BehaviorDirector for visible sprite and bubble policy
- Collapse TouchArea grid behind "更多互动" toggle
- Preserve VoiceButton, TextInputBar, VoiceModeToggle, audio polling, heartbeat, proactive

## Files To Modify
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/App.test.tsx`

## Tests
- App renders DoudouSprite, not kaomoji
- Tap on sprite shows immediate local reaction
- TouchArea not visible by default, accessible via toggle
- Text/voice/audio paths still work
- `npm test -- --run` passes
- `npm run build` passes
