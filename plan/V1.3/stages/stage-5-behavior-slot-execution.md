# Stage 5: Behavior Slot Execution

**Date:** 2026-05-26
**Goal:** Wire Fast Reply `action` to sprite, wire Thinking `behavior_plan` slots to phase boundaries, remove unsafe casts, fix VoiceButton race, add protected-phase tests.

## Scope

Frontend behavior wiring + backend action validation. No LLM prompt changes.

### 1. Remove Unsafe Casts in applyPetResponse

**File:** `frontend/src/App.tsx` (modify)
- Replace `(response as Record<string, unknown>).behavior_intent` with `response.behavior_intent`
- Replace `(response as Record<string, unknown>).behavior_plan` with `response.behavior_plan`

### 2. Fix Frontend BehaviorStep Type

**Issue:** Frontend `BehaviorStep` has `target` but no `slot`. Backend sends `slot`.

**File:** `frontend/src/pet/types.ts` (modify)
- Replace `BehaviorStep` with `DoudouBehaviorStep` import from `doudouBehaviorPlan.ts`, or update the type to match backend:
```typescript
export type BehaviorStep = {
  action: string;
  slot?: string;
  duration_ms?: number;
};
```

### 3. Wire Fast Reply `action` to Sprite

**File:** `frontend/src/pet/behaviorDirector.ts` (modify)

Update `onBackendResponse` to accept optional `action` field. If present and valid (check against `PHASE_SPRITE_MAP` keys or use a simple whitelist), use it as immediate sprite action:

```typescript
onBackendResponse(
  response: {
    behavior_intent?: string | null;
    behavior_plan?: unknown;
    action?: string | null;
    mood?: Mood;
    reply?: string;
  },
  phase: PetUIPhase,
): DirectorOutput {
  // Fast Reply: single action takes priority
  if (response.action && isValidDoudouAction(response.action)) {
    return {
      visibleAction: response.action as DoudouAction,
      bubbleText: response.reply ?? null,
    };
  }
  // ... existing behavior plan logic
}
```

Note: `isValidAction` in `doudouBehaviorPlan.ts` is private. Use `isValidDoudouAction` from `doudouSprites.ts` or add a simple whitelist check.

**File:** `frontend/src/App.tsx` (modify)

Pass `action` to `onBackendResponse`:
```typescript
const out = directorRef.current.onBackendResponse(
  {
    behavior_intent: response.behavior_intent,
    behavior_plan: response.behavior_plan,
    mood: response.mood,
    reply: response.reply,
    action: response.action,
  },
  phase,
);
```

Note: For Thinking mode, `action` will be `undefined` — the `if` guard handles this.

### 4. Fix VoiceButton Race Condition

**Issue:** VoiceButton calls `changePhase("waiting_voice")` → `onPhaseChange` → clears `queuedSteps`, destroying the behavior plan before `advanceSlot("speech")` runs.

**File:** `frontend/src/pet/behaviorDirector.ts` (modify)

Change `onPhaseChange` to preserve `queuedSteps` for `waiting_voice` and `speaking` phases (audio playback phases where behavior plan should continue):

```typescript
onPhaseChange(phase: PetUIPhase): DirectorOutput {
  // For audio playback phases, preserve the behavior plan queue
  // (VoiceButton calls changePhase which triggers this, but we don't
  // want to destroy the plan that advanceSlot will consume)
  if (phase === "waiting_voice" || phase === "speaking") {
    return {
      visibleAction: PHASE_SPRITE_MAP[phase] ?? "idle",
      bubbleText: null,
    };
  }
  // For other protected phases, clear the queue
  if (PROTECTED_PHASES.has(phase) || phase === "audio_error" || phase === "error") {
    this.queuedSteps = [];
    this.currentSlot = null;
    return {
      visibleAction: PHASE_SPRITE_MAP[phase] ?? "idle",
      bubbleText: null,
    };
  }
  return {
    visibleAction: PHASE_SPRITE_MAP[phase] ?? "idle",
    bubbleText: null,
  };
}
```

### 5. Wire advanceSlot at Phase Boundaries

**File:** `frontend/src/App.tsx` (modify)

In `playResponseAudio`, replace hard-coded `setDoudouAction("review")` and `setDoudouAction("idle")` with `advanceSlot` calls:

```typescript
// When entering waiting_voice (audio starts):
setPhase("waiting_voice");
const beforeOut = directorRef.current.advanceSlot("before_speech");
if (beforeOut) setDoudouAction(beforeOut.visibleAction);

// When entering speaking:
setPhase("speaking");
const speechOut = directorRef.current.advanceSlot("speech");
if (speechOut) setDoudouAction(speechOut.visibleAction);
else setDoudouAction("review"); // fallback

// After speaking ends:
setPhase("idle");
const afterOut = directorRef.current.advanceSlot("after_speech");
if (afterOut) setDoudouAction(afterOut.visibleAction);
else setDoudouAction("idle"); // fallback
```

Note: Hard-coded fallbacks (`"review"`, `"idle"`) are kept as defaults when `advanceSlot` returns null (no matching step in plan).

### 6. Fix advanceSlot Comment

**File:** `frontend/src/pet/behaviorDirector.ts` (modify)

Fix misleading comment at line 180: "Remove consumed step and all before it for this slot" → only removes the single matched step. Update comment to match code.

### 7. Backend Tests

**File:** `backend/tests/test_stage5_behavior.py` (new)
- `test_fast_reply_includes_action`: Fast Reply response includes `action` field
- `test_fast_reply_action_is_whitelisted`: action value is valid DoudouAction
- `test_thinking_response_has_behavior_plan`: Thinking response includes behavior_plan
- `test_listening_phase_not_interrupted_by_tap`: tap during listening returns phase-mapped action
- `test_speaking_phase_not_interrupted_by_tap`: tap during speaking returns phase-mapped action

## Files Changed

| File | Change Type |
|---|---|
| `frontend/src/App.tsx` | Modify (remove unsafe casts, pass action, replace hard-coded setDoudouAction with advanceSlot) |
| `frontend/src/pet/behaviorDirector.ts` | Modify (accept action, fix onPhaseChange to preserve queue for audio phases, fix comment) |
| `frontend/src/pet/types.ts` | Modify (fix BehaviorStep type to match backend) |
| `backend/tests/test_stage5_behavior.py` | New (action, behavior_plan, protected phase tests) |

## Nubia Constraints

- Fast Reply `action` is a single sprite action (no multi-step plan)
- Thinking `behavior_plan` slots advance at real audio phase boundaries
- Protected phases remain authoritative for taps
- `advanceSlot` is purely local (no backend call)
- VoiceButton race fixed by preserving queue during audio phases
- Invalid `action` falls back to behavior plan or idle

## Acceptance Checks

1. Fast Reply `action` updates sprite immediately
2. Missing/invalid `action` falls back to behavior plan
3. Thinking `behavior_plan` advances through `before_speech`, `speech`, `after_speech`, `idle_after`
4. Protected phases remain authoritative for taps
5. No `Record<string, unknown>` casts for behavior fields
6. VoiceButton doesn't destroy behavior plan queue
7. Full test suite passes
