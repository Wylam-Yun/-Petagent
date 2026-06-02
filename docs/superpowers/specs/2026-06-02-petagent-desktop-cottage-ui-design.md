# PetAgent Desktop Cottage UI Design

Date: 2026-06-02
Status: Proposed

## Objective

Refresh the PetAgent frontend so it feels like DouDou lives in a calm, light-colored desktop corner rather than inside a generic dashboard. The redesign should make DouDou the visual focus, keep long-session use comfortable on the Nubia phone, and preserve the current browser and APK entry behavior.

## Product Direction

The chosen direction is a "desktop cottage" interface:

- Light, soft, and restrained.
- Warm enough to feel companion-like, but not toy-like or childish.
- No strange high-saturation colors, neon accents, heavy gradients, or purple-blue AI-style palettes.
- More like a quiet desk companion than a game screen or analytics panel.

The interface should feel stable and usable if it is left open for a long time.

## Scope

The UI work is limited to the existing React/Vite frontend:

- `frontend/src/styles.css` for the main visual system, layout, responsive behavior, and component states.
- `frontend/src/App.tsx` only if the current structure needs small wrapper or class changes for clearer layout.
- Existing component files only for small class, accessibility, or semantic refinements.

The redesign must keep the existing interaction model:

- Text chat remains available.
- Voice remains the primary mobile action.
- More interactions remain available behind the existing "more interactions" affordance.
- Reset remains visually low priority.

## Non-Goals

This redesign must not:

- Change backend APIs.
- Add a new voice endpoint.
- Change APK routing or fork separate APK/browser frontend paths.
- Move backend behavior into the APK.
- Add heavy animation or modern CSS that is risky on Android WebView 55.
- Commit generated `frontend/dist` output.

## Layout

The page remains a single-screen pet surface with three visual zones.

### Top Status Strip

The current status cards should become a lighter strip of small pet status indicators. These should support quick scanning without competing with DouDou.

Design requirements:

- Use compact pills or small inline modules rather than large cards.
- Keep labels readable on mobile.
- Avoid heavy shadows.
- Use low-contrast surfaces and restrained icons.
- Mood should read as a pet state, not as a dashboard metric.

### DouDou Stage

The stage becomes the main visual anchor. DouDou should appear to sit in a quiet desktop nook.

Design requirements:

- The face area should no longer look like a plain white card.
- Use a soft stage surface with stable dimensions.
- Keep the expression large and clear.
- Use subtle background structure, such as a shelf line, base panel, or quiet room-like surface.
- Avoid decorative blobs, loud gradients, or busy patterns.
- Maintain strong legibility for all ASCII-style expressions.

### Conversation Bubble

The bubble should feel like DouDou speaking from the stage.

Design requirements:

- Place it visually close to the pet face.
- Use a speech-bubble or note-like surface with a calm border.
- Preserve `aria-live="polite"`.
- Long Chinese text must wrap cleanly without overlapping controls.
- Busy text should stay visually consistent with normal dialogue.

### Control Dock

The bottom controls should feel like a small dock attached to the pet surface.

Design requirements:

- Voice remains the clearest primary action.
- Text input remains easy to access but visually secondary.
- More interactions can expand into a tidy drawer.
- The reset action stays quiet and low priority.
- Disabled, listening, thinking, speaking, and error states must remain obvious.

## Visual System

The palette should be light and familiar:

- Page base: off-white or very pale warm gray.
- Main surface: white or near-white.
- Text: soft ink or charcoal, not pure black.
- Primary action: muted teal or calm green-blue.
- Secondary warmth: soft coral only for active/emotional states.
- Borders: low-contrast warm gray.
- Error: muted red, used sparingly.

Avoid:

- Purple or blue gradient-dominant themes.
- Neon colors.
- Brown/orange-heavy themes.
- Overly beige or cream-only palettes.
- Large decorative color blobs.

Typography:

- Keep system font compatibility for old WebView.
- Improve hierarchy with weight, size, and spacing rather than custom web fonts.
- Do not scale fonts directly with viewport width.
- Use stable sizes for buttons and status labels.

Shape and depth:

- Keep border radius consistent, around the existing 8px system unless a control needs a pill shape.
- Prefer borders and surface layering over heavy shadows.
- Avoid nested card-in-card composition.

Motion:

- Keep existing pet expression animations.
- Add only subtle CSS transitions for buttons and state changes.
- Avoid blur-heavy, filter-heavy, or scroll-triggered animation.

## Component-Level Changes

### `StatusBar`

The component can keep its current data contract. Styling should make it a quiet status strip.

Expected result:

- Smaller footprint.
- Better mobile wrapping.
- Icons and values aligned without looking like KPI cards.

### `PetFace`

The component can keep its current API. Styling should create the desktop-cottage stage.

Expected result:

- DouDou's expression feels like the main character.
- The face stays centered and stable through mood changes.
- Large expressions do not shift the layout.

### `PetBubble`

The component can keep its current API. Styling should make messages feel conversational.

Expected result:

- Message area is close to the face.
- Busy state does not visually fight with the actual response state.
- Text wraps well on narrow screens.

### `TextInputBar`

The component behavior should remain unchanged.

Expected result:

- Input and send button feel integrated into the dock.
- Send button can use its icon plus short label.
- Focus state is visible and accessible.

### `VoiceButton`

The component behavior must remain unchanged.

Expected result:

- Primary visual action on mobile.
- Listening state is clearly different from idle.
- Thinking, speaking, interrupt, and error states remain understandable.
- Cancel button remains reachable while recording.

### `TouchArea`

The grouped interaction model should remain.

Expected result:

- Expanded interactions feel like a drawer rather than a grid of unrelated cards.
- Pet care and companion groups are readable.
- Buttons remain easy to tap on the Nubia screen.

## Responsive Behavior

The page must be checked at:

- Narrow mobile width around 320px.
- Typical phone portrait.
- Phone landscape with limited height.
- Desktop browser width.

Requirements:

- The pet stage and controls must not overlap.
- Buttons must keep stable tap targets.
- Text inside buttons must not overflow.
- Landscape mode should preserve quick access to voice and text controls.
- The design should not rely on viewport-width font scaling.

## Accessibility

Accessibility behavior must be preserved or improved:

- Keep real `button` and `input` elements.
- Preserve existing aria labels.
- Preserve `aria-live="polite"` for DouDou's bubble.
- Provide visible focus states for keyboard and hardware input users.
- Do not communicate state using color alone.

## Compatibility

The design must be safe for:

- Android 6.0.1.
- WebView 55.
- Browser entry at `http://127.0.0.1:8000/`.
- APK WebView entry loading the same frontend.

Avoid risky dependencies or features:

- No new UI framework.
- No CSS features that are likely unsupported by WebView 55 without fallback.
- No font downloads required for the interface to look acceptable.

## Validation Plan

After implementation, run:

- Frontend tests: `cd frontend && npm test -- --run`
- Frontend build: `cd frontend && npm run build`

Manual validation:

- Open browser entry and confirm the redesigned page loads.
- Open APK entry and confirm the same redesigned page loads.
- Check voice button state transitions: idle, listening, thinking, speaking, error/retry if available.
- Check text input submit path.
- Expand more interactions and verify tap targets.
- Check portrait and landscape layouts.

Generated `frontend/dist` output must not be committed.

## Risks

The main risk is visual polish causing browser compatibility regressions on WebView 55. The mitigation is to keep the implementation mostly to conservative CSS, avoid heavy filters or modern layout tricks, and verify both browser and APK entries after building.

Another risk is over-softening the UI until controls become unclear. The mitigation is to keep primary actions visually distinct, use clear labels, and preserve obvious phase states for recording and playback.

## Acceptance Criteria

The redesign is acceptable when:

- The page reads as a light desktop-cottage pet surface.
- DouDou is the dominant visual element.
- The UI no longer feels like a generic dashboard.
- Colors are light, restrained, and not strange.
- All current chat, voice, interaction, and reset behavior remains intact.
- Browser and APK entries still use the same frontend path.
- No forbidden generated artifacts are committed.
