# PetAgent Desktop Cottage UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the PetAgent frontend into a light, restrained "desktop cottage" pet surface while preserving the existing browser/APK entries and chat/voice behavior.

**Architecture:** Keep the existing React component model and backend API usage. Make small semantic wrapper/class changes in `App.tsx`, then replace the CSS visual system with conservative WebView-55-safe styles. Tests focus on preserving behavior and required UI affordances; visual quality is verified through local browser/APK inspection.

**Tech Stack:** React 18, TypeScript, Vite, Vitest, Testing Library, CSS, lucide-react, Android WebView 55 compatibility constraints.

---

## File Structure

- Modify `frontend/src/App.tsx`
  - Add light semantic wrappers/classes for the top status area, pet stage, and control dock.
  - Preserve all state, API calls, voice flow, text flow, and interaction handlers.
- Modify `frontend/src/styles.css`
  - Replace the current dashboard-like white cards and gradient background with a light desktop-cottage visual system.
  - Keep old-WebView-safe CSS: grid/flex, borders, simple shadows, simple gradients only.
  - Remove stale selectors that are no longer used by the frontend.
- Modify `frontend/src/App.test.tsx`
  - Add assertions that the core UI regions and affordances still render after the wrapper/class changes.
  - Do not test exact colors.
- Modify `frontend/src/components/StatusBar.test.tsx`
  - Add a simple assertion for the status region label if needed after semantic wrapper changes.
- Do not modify backend files, Android shell runtime code, or generated `frontend/dist`.

## Task 1: Protect Existing UI Contract

**Files:**
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/components/StatusBar.test.tsx`

- [ ] **Step 1: Add App landmark/affordance assertions**

In `frontend/src/App.test.tsx`, update the test named `App renders 豆豆 and shows kaomoji face` so it verifies the page still exposes the main pet surface, status, text, voice, more interactions, and reset affordances.

Use this assertion block after the existing face assertion:

```tsx
expect(screen.getByRole("main")).toHaveClass("app-shell");
expect(screen.getByLabelText("豆豆状态")).toBeInTheDocument();
expect(screen.getByLabelText("豆豆当前心情 idle")).toBeInTheDocument();
expect(screen.getByRole("textbox", { name: "文字输入" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: "点一下说话" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: "更多互动" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: "重新认识" })).toBeInTheDocument();
```

- [ ] **Step 2: Add StatusBar region assertion**

In `frontend/src/components/StatusBar.test.tsx`, extend `shows only intimacy, energy, mood — no internal stats` with:

```tsx
expect(screen.getByLabelText("豆豆状态")).toBeInTheDocument();
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
cd frontend && npm test -- --run src/App.test.tsx src/components/StatusBar.test.tsx
```

Expected result: all selected tests pass before visual changes.

- [ ] **Step 4: Commit UI contract tests**

Run:

```bash
git add frontend/src/App.test.tsx frontend/src/components/StatusBar.test.tsx
git commit -m "test: protect pet ui shell affordances"
```

## Task 2: Add Desktop-Cottage Layout Hooks

**Files:**
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: Add lightweight layout containers**

In `frontend/src/App.tsx`, replace the current return block structure with this shape. Keep all existing props and handlers exactly as they are:

```tsx
return (
  <main className={`app-shell ${activeSession ? "is-active-session" : ""}`}>
    {!isOnline && (
      <div className="offline-banner" role="status">
        正在重新连接豆豆…
      </div>
    )}
    <div className="top-panel">
      <StatusBar state={petState} />
    </div>
    <section className="pet-stage" aria-label={`豆豆当前心情 ${titleMood}`}>
      <div className="pet-stage-room" aria-hidden="true">
        <span className="room-shelf" />
        <span className="room-dot room-dot-left" />
        <span className="room-dot room-dot-right" />
      </div>
      <div className="pet-title-row">
        <p className="pet-kicker">PetAgent</p>
        <h1>豆豆</h1>
      </div>
      <PetFace faceType={faceType} animation={animation} expressionKey={expressionKey} />
      <PetBubble text={bubbleText} busy={busy} />
    </section>
    <div className="control-deck" aria-label="豆豆互动控制">
      <TextInputBar
        disabled={isTextDisabled}
        onSubmit={handleTextSubmit}
        onActiveChange={setInputActiveState}
      />
      <VoiceButton
        disabled={isVoiceDisabled}
        phase={phase}
        onError={(message) => setBubbleText(message)}
        onInterrupt={interruptVoiceRun}
        onPhaseChange={handleVoicePhase}
        onVoiceResponse={handleVoiceResponse}
      />
      <button
        className="more-toggle-btn"
        type="button"
        onClick={() => setShowMoreMenu(!showMoreMenu)}
        aria-expanded={showMoreMenu}
      >
        {showMoreMenu ? "收起互动" : "更多互动"}
      </button>
      {showMoreMenu && (
        <div className="interaction-drawer">
          <TouchArea
            disabled={isTextDisabled || interactions.length === 0}
            interactions={interactions}
            onPetEvent={handlePetEvent}
          />
        </div>
      )}
    </div>
    <div className="secondary-actions">
      {phase === "audio_error" && lastAudioJobId && (
        <button
          className="retry-audio-btn"
          disabled={busy}
          onClick={handleRetryAudio}
        >
          重试发声
        </button>
      )}
      <button
        className="reset-btn"
        disabled={busy}
        onClick={handleResetRuntime}
      >
        重新认识
      </button>
    </div>
  </main>
);
```

- [ ] **Step 2: Keep the more-interactions test aligned**

In `frontend/src/App.test.tsx`, if the existing test `local more interaction updates kaomoji without backend post` queries the collapsed button by exact text, keep it querying the button by accessible name:

```tsx
fireEvent.click(screen.getByRole("button", { name: "更多互动" }));
```

The expanded state label changes to `收起互动`; no test needs to query it unless a new assertion is added.

- [ ] **Step 3: Run focused App tests**

Run:

```bash
cd frontend && npm test -- --run src/App.test.tsx
```

Expected result: App tests pass. No fetch call counts should change.

- [ ] **Step 4: Commit layout hooks**

Run:

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "refactor: add pet ui layout hooks"
```

## Task 3: Replace the Visual System

**Files:**
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`
- Test: `frontend/src/components/*.test.tsx`

- [ ] **Step 1: Replace root tokens and page shell styles**

In `frontend/src/styles.css`, define the light desktop-cottage tokens at the top:

```css
:root {
  color: #26313d;
  background: #f7f5ef;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.3;
  --ink: #26313d;
  --muted: #687380;
  --soft-muted: #8a9480;
  --page: #f7f5ef;
  --surface: #fffdf8;
  --surface-strong: #ffffff;
  --line: rgba(73, 85, 99, 0.16);
  --line-soft: rgba(73, 85, 99, 0.1);
  --teal: #4a9f96;
  --teal-dark: #2f756f;
  --coral: #d98474;
  --coral-dark: #b96458;
  --danger: #b85f5a;
  --shadow-soft: 0 14px 34px rgba(75, 89, 105, 0.12);
  --shadow-small: 0 8px 18px rgba(75, 89, 105, 0.09);
}
```

Then replace `.app-shell` and `.app-shell.is-active-session` with a light background and stable single-screen layout:

```css
.app-shell {
  min-height: 100vh;
  min-height: 100dvh;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto auto;
  gap: 12px;
  padding: 14px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(247, 245, 239, 0) 38%),
    var(--page);
}

.app-shell.is-active-session {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(247, 245, 239, 0) 42%),
    #f5f4ed;
}
```

- [ ] **Step 2: Style the top status strip**

Replace `.status-bar`, `.status-item`, `.status-icon`, `.status-label`, and `.status-item strong` with compact status strip styles:

```css
.top-panel {
  width: min(920px, 100%);
  margin: 0 auto;
}

.status-bar {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.status-item {
  min-height: 42px;
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
  padding: 8px 10px;
  border: 1px solid var(--line-soft);
  border-radius: 999px;
  background: rgba(255, 253, 248, 0.82);
  color: var(--ink);
  box-shadow: none;
}

.status-icon svg {
  width: 18px;
  height: 18px;
  color: var(--teal-dark);
}

.status-label {
  min-width: 0;
  color: var(--muted);
  font-size: 0.78rem;
  white-space: nowrap;
}

.status-item strong {
  min-width: 24px;
  overflow: hidden;
  color: var(--ink);
  font-size: 0.86rem;
  font-weight: 760;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

- [ ] **Step 3: Style the main pet stage**

Replace `.pet-stage`, `.pet-stage h1`, `.pet-face`, and `.pet-bubble` styles. Include new styles for `.pet-stage-room`, `.pet-title-row`, `.pet-kicker`, `.room-shelf`, and `.room-dot`:

```css
.pet-stage {
  position: relative;
  width: min(920px, 100%);
  min-height: 0;
  margin: 0 auto;
  display: grid;
  grid-template-rows: auto minmax(180px, 1fr) auto;
  align-items: center;
  justify-items: center;
  gap: 10px;
  padding: 18px 14px 16px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 10px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(255, 253, 248, 0.92)),
    var(--surface);
  box-shadow: var(--shadow-soft);
}

.pet-stage-room {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.room-shelf {
  position: absolute;
  left: 10%;
  right: 10%;
  bottom: 24%;
  height: 1px;
  background: rgba(73, 85, 99, 0.12);
}

.room-dot {
  position: absolute;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: rgba(74, 159, 150, 0.18);
}

.room-dot-left {
  left: 18%;
  top: 26%;
}

.room-dot-right {
  right: 17%;
  top: 18%;
  background: rgba(217, 132, 116, 0.18);
}

.pet-title-row {
  position: relative;
  z-index: 1;
  display: grid;
  justify-items: center;
  gap: 2px;
}

.pet-kicker {
  margin: 0;
  color: var(--soft-muted);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0;
}

.pet-stage h1 {
  margin: 0;
  color: var(--ink);
  font-size: 1.85rem;
  font-weight: 820;
  letter-spacing: 0;
}

.pet-face {
  position: relative;
  z-index: 1;
  width: min(86vw, 620px);
  min-height: clamp(180px, 32vh, 300px);
  display: grid;
  place-items: center;
  padding: 14px 10px;
  border-radius: 8px;
  color: #1f2c37;
  font-family: ui-monospace, "SFMono-Regular", "Menlo", "Consolas", monospace;
  font-size: clamp(3rem, 13vw, 7.2rem);
  line-height: 1.04;
  text-align: center;
  white-space: normal;
  overflow-wrap: anywhere;
  background: rgba(255, 255, 255, 0.38);
  border: 1px solid rgba(73, 85, 99, 0.08);
}

.pet-bubble {
  position: relative;
  z-index: 1;
  width: min(680px, 100%);
  min-height: 56px;
  display: grid;
  place-items: center;
  padding: 12px 16px;
  border: 1px solid rgba(73, 85, 99, 0.14);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.88);
  color: var(--ink);
  font-size: 1rem;
  text-align: center;
  box-shadow: var(--shadow-small);
}
```

- [ ] **Step 4: Style the control dock**

Replace `.control-deck`, `.text-input-bar`, input/button styles, `.voice-control`, `.voice-button`, `.voice-cancel-button`, `.more-toggle-btn`, `.interaction-drawer`, `.touch-area`, `.touch-group`, `.touch-group-label`, `.touch-group-buttons`, `.touch-button`, `.secondary-actions`, `.retry-audio-btn`, and `.reset-btn`.

Use this structure:

```css
.control-deck {
  width: min(760px, 100%);
  margin: 0 auto;
  display: grid;
  gap: 9px;
  padding: 10px;
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  background: rgba(255, 253, 248, 0.78);
  box-shadow: var(--shadow-small);
}

.text-input-bar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.text-input-bar input {
  min-height: 44px;
  min-width: 0;
  padding: 8px 13px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-strong);
  color: var(--ink);
  font: inherit;
  font-size: 0.95rem;
  outline: none;
  transition: border-color 140ms ease, box-shadow 140ms ease;
}

.text-input-bar input:focus {
  border-color: rgba(74, 159, 150, 0.58);
  box-shadow: 0 0 0 3px rgba(74, 159, 150, 0.14);
}

.text-input-bar button,
.voice-button,
.voice-cancel-button,
.more-toggle-btn,
.touch-button,
.retry-audio-btn,
.reset-btn {
  -webkit-tap-highlight-color: transparent;
}

.text-input-bar button {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid rgba(74, 159, 150, 0.36);
  border-radius: 8px;
  background: #f2fbf8;
  color: var(--teal-dark);
  font-size: 0.9rem;
  font-weight: 720;
  cursor: pointer;
}

.voice-control {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.voice-button {
  min-height: 60px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  border: 1px solid rgba(47, 117, 111, 0.36);
  border-radius: 8px;
  background: var(--teal);
  color: #ffffff;
  box-shadow: 0 10px 22px rgba(47, 117, 111, 0.18);
  cursor: pointer;
  touch-action: none;
  user-select: none;
  transition: transform 120ms ease, box-shadow 120ms ease, opacity 120ms ease;
}

.voice-listening {
  background: var(--coral);
  border-color: var(--coral);
}

.voice-thinking,
.voice-waiting_voice,
.voice-speaking {
  background: #33414d;
  border-color: #33414d;
}

.voice-error,
.voice-audio_error {
  background: #fff8f6;
  border-color: rgba(184, 95, 90, 0.32);
  color: var(--danger);
}

.voice-cancel-button {
  min-width: 52px;
  min-height: 60px;
  border: 1px solid rgba(184, 95, 90, 0.26);
  border-radius: 8px;
  background: #fff8f6;
  color: var(--danger);
  cursor: pointer;
}

.more-toggle-btn {
  min-height: 40px;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.6);
  color: var(--muted);
  font-size: 0.84rem;
  cursor: pointer;
}

.interaction-drawer {
  border-top: 1px solid var(--line-soft);
  padding-top: 9px;
}

.touch-area {
  width: 100%;
  display: grid;
  gap: 10px;
}

.touch-group {
  display: grid;
  gap: 6px;
}

.touch-group-label {
  color: var(--soft-muted);
  font-size: 0.76rem;
  font-weight: 720;
}

.touch-group-buttons {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.touch-button {
  min-height: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 7px 9px;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: #ffffff;
  color: var(--ink);
  cursor: pointer;
}

.touch-button.compact {
  min-height: 42px;
  font-size: 0.82rem;
}

.secondary-actions {
  width: min(760px, 100%);
  margin: 0 auto;
  display: flex;
  justify-content: center;
  gap: 10px;
  padding-bottom: 4px;
}

.retry-audio-btn,
.reset-btn {
  min-height: 34px;
  padding: 6px 14px;
  border-radius: 999px;
  background: transparent;
  font-size: 0.8rem;
  cursor: pointer;
}

.retry-audio-btn {
  border: 1px solid rgba(74, 159, 150, 0.3);
  color: var(--teal-dark);
}

.reset-btn {
  border: 1px solid rgba(184, 95, 90, 0.22);
  color: rgba(184, 95, 90, 0.72);
}
```

Keep the existing disabled styles, icon sizing, error text, hover states, and offline banner behavior, but rewrite their colors to use the new tokens.

- [ ] **Step 5: Remove stale styles**

Delete selectors for currently unused controls:

```css
.voice-mode-toggle
.voice-mode-toggle.is-thinking
.voice-mode-label
.voice-mode-track
.voice-mode-thumb
.touch-primary
.touch-more
.context-refresh-btn
```

If `rg -n "voice-mode|touch-primary|touch-more|context-refresh" frontend/src` finds any real usage, do not delete that selector and instead inspect why it is still needed.

- [ ] **Step 6: Run frontend test suite**

Run:

```bash
cd frontend && npm test -- --run
```

Expected result: all frontend tests pass.

- [ ] **Step 7: Commit visual system**

Run:

```bash
git add frontend/src/styles.css
git commit -m "style: refresh pet ui desktop cottage theme"
```

## Task 4: Responsive and Compatibility Hardening

**Files:**
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`
- Optional manual validation: local browser at Vite dev server

- [ ] **Step 1: Add mobile portrait constraints**

In `frontend/src/styles.css`, replace the existing `@media (max-width: 680px)` block with:

```css
@media (max-width: 680px) {
  .app-shell {
    gap: 10px;
    padding: 10px;
  }

  .status-bar {
    gap: 6px;
  }

  .status-item {
    grid-template-columns: 18px minmax(0, 1fr);
    min-height: 40px;
    padding: 7px 8px;
  }

  .status-item strong {
    grid-column: 2;
    min-width: 0;
    text-align: left;
  }

  .pet-stage {
    grid-template-rows: auto minmax(170px, 1fr) auto;
    padding: 14px 10px;
  }

  .pet-stage h1 {
    font-size: 1.62rem;
  }

  .pet-face {
    width: 100%;
    min-height: 172px;
    font-size: clamp(2.8rem, 16vw, 5.2rem);
  }

  .pet-bubble {
    min-height: 52px;
    padding: 10px 12px;
    font-size: 0.96rem;
  }

  .control-deck {
    padding: 8px;
  }

  .text-input-bar button span {
    display: none;
  }

  .text-input-bar button {
    min-width: 46px;
    padding: 8px 10px;
  }

  .touch-group-buttons {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
```

- [ ] **Step 2: Add narrow-screen fallback**

Add this block after the mobile block:

```css
@media (max-width: 360px) {
  .status-label {
    font-size: 0.72rem;
  }

  .status-item strong {
    font-size: 0.78rem;
  }

  .voice-button {
    min-height: 56px;
    font-size: 0.92rem;
  }

  .touch-button {
    font-size: 0.82rem;
    padding-left: 6px;
    padding-right: 6px;
  }
}
```

- [ ] **Step 3: Replace landscape block**

Replace the existing `@media (orientation: landscape) and (max-height: 520px)` block with:

```css
@media (orientation: landscape) and (max-height: 520px) {
  .app-shell {
    grid-template-columns: 210px minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) auto;
    gap: 10px;
  }

  .top-panel {
    grid-row: 1 / 3;
    width: 100%;
    align-self: stretch;
    display: grid;
    align-items: center;
  }

  .status-bar {
    grid-template-columns: 1fr;
  }

  .pet-stage {
    width: 100%;
    min-height: 0;
    grid-template-rows: auto minmax(120px, 1fr) auto;
    padding: 10px;
  }

  .pet-face {
    min-height: 128px;
    font-size: clamp(2.6rem, 13vh, 4.6rem);
  }

  .pet-bubble {
    min-height: 46px;
    font-size: 0.92rem;
  }

  .control-deck {
    grid-column: 2;
    width: 100%;
  }

  .secondary-actions {
    grid-column: 2;
    width: 100%;
  }
}
```

- [ ] **Step 4: Verify CSS selectors are used**

Run:

```bash
rg -n "top-panel|pet-stage-room|pet-title-row|interaction-drawer|voice-mode|touch-primary|touch-more|context-refresh" frontend/src
```

Expected result:

- New selectors appear in `App.tsx` and/or `styles.css`.
- `voice-mode`, `touch-primary`, `touch-more`, and `context-refresh` do not appear unless there is an intentional remaining usage.

- [ ] **Step 5: Run tests and build**

Run:

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

Expected result: both commands pass.

- [ ] **Step 6: Confirm generated artifacts are not staged**

Run:

```bash
git status --short
git diff -- frontend/dist
```

Expected result:

- `frontend/dist` may exist or change locally after build, but it must not be staged or committed.
- Only source/test files should be staged in the next step.

- [ ] **Step 7: Commit responsive hardening**

Run:

```bash
git add frontend/src/styles.css
git commit -m "style: harden pet ui responsive layout"
```

## Task 5: Browser and APK Entry Validation

**Files:**
- No required source changes.
- Do not commit generated outputs.

- [ ] **Step 1: Check repo hygiene before manual validation**

Run:

```bash
git status --short
git ls-files frontend/dist backend/data backend/static/audio backend/secrets logs android-shell/app/build android-shell/.gradle android-shell/build android-shell/local.properties
```

Expected result:

- No forbidden generated/runtime files are tracked.
- Working tree is either clean or contains only expected local build output that will not be committed.

- [ ] **Step 2: Validate local browser build output**

Run:

```bash
cd frontend && npm run build
```

Expected result: build passes.

If a local browser screenshot is needed, run the Vite dev server:

```bash
cd frontend && npm run dev -- --host 127.0.0.1
```

Open the printed local URL and inspect:

- Desktop width.
- Narrow mobile emulation around 320px.
- Landscape-like short viewport.

Stop the dev server after inspection.

- [ ] **Step 3: Deploy frontend to Termux only if manual phone validation is requested**

Use the repository's existing deployment procedure if available. If no documented deploy command exists, do not invent a new phone deployment flow; report that source/build validation passed and ask for the preferred deployment command.

Before any phone validation, confirm the existing runtime:

```bash
adb devices -l
adb forward --list
adb forward tcp:18000 tcp:8000
adb forward tcp:18022 tcp:8022
ssh nubia-adb 'id; cd ~/Petagent && scripts/status.sh'
curl -fsS http://127.0.0.1:18000/api/health
curl -fsS http://127.0.0.1:18000/build-info.json
```

Stop if SSH `id` does not include `3003(inet)` or backend health fails.

- [ ] **Step 4: Validate browser entry after deployment**

Open:

```text
http://127.0.0.1:8000/
```

On the phone browser, verify:

- Light desktop-cottage visual direction is visible.
- DouDou is the dominant visual element.
- Text input submits one message.
- Voice button can enter listening state.
- More interactions drawer opens.

- [ ] **Step 5: Validate APK entry after deployment**

Run:

```bash
adb shell monkey -p com.petagent.shell 1
```

Verify in the APK WebView:

- Same frontend path and same redesigned UI.
- UI loads from phone loopback backend.
- No native unavailable screen appears while backend is healthy.
- Voice button remains visible and reachable.

This task does not require a full five-turn voice chain unless the user asks for a new V1.9 voice regression pass.

- [ ] **Step 6: Final hygiene**

Run:

```bash
git status --short
git ls-files frontend/dist backend/data backend/static/audio backend/secrets logs android-shell/app/build android-shell/.gradle android-shell/build android-shell/local.properties
```

Expected result:

- No forbidden artifacts are staged or tracked.
- Source commits from Tasks 1-4 are present.

## Self-Review Notes

- Spec coverage: The plan covers the light desktop-cottage visual direction, restrained colors, DouDou as the main visual element, status strip, conversation bubble, control dock, responsive behavior, accessibility preservation, WebView 55 caution, and no generated artifact commits.
- Scope check: The plan stays within the frontend. Backend, APK runtime, voice API paths, and deployment mechanics are not changed.
- Type consistency: No new TypeScript data types or API contracts are introduced. The only React structural changes are wrapper elements and class names.
