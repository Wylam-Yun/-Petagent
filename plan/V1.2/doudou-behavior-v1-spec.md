# PetAgent V1.2: Doudou Behavior v1 Spec

**Date:** 2026-05-24
**Project path:** `/Users/wylam/Documents/workspace/Petagent`
**Runtime target:** Nubia Android + Termux, FastAPI backend on `127.0.0.1:8000`,
React/Vite frontend served by backend.

## Goal

V1.2 turns the visible pet from a kaomoji-driven Momo UI into a sprite-based
cat named **豆豆**. The user-facing experience should feel like a small lazy,
clingy, cute cat living in the phone: fast to react, lightly autonomous, and
not presented as a customer-service assistant or a row of animation buttons.

The existing conversation/runtime chain remains the foundation:

```text
frontend gesture / voice / text
-> existing FastAPI API
-> RuntimeDispatcher / VoicePipeline / TextPipeline
-> AgentRun, memory/context, audio job
-> frontend audio playback + visible pet response
```

V1.2 must not discard the current voice, text, memory, audio job, proactive,
or AgentRun infrastructure. The main change is the user-facing behavior layer:
sprite animation, simplified controls, local instant reactions, and a Doudou
persona that maps existing events into natural pet scenes. For semantic
reactions, the model should be able to choose from Doudou's allowed atomic
sprite actions as if they were a small tool palette; the system validates that
plan and the frontend executes it with protected phase rules.

## Current Project Facts

Relevant current files and behavior:

- `frontend/src/App.tsx`
  - Uses `PetFace`, `PetBubble`, `TextInputBar`, `VoiceButton`,
    `VoiceModeToggle`, and `TouchArea`.
  - Maintains `phase`, `busy`, `faceType`, `animation`, `bubbleText`,
    `lastAudioJobId`.
  - Already supports `audio_job_id`, `waiting_voice`, `speaking`,
    `audio_error`, frontend heartbeat, proactive polling, text chat, voice chat.
  - Still hardcodes many `Momo` strings.

- `frontend/src/components/PetFace.tsx`
  - Renders kaomoji text from `faceForType`.
  - Uses CSS transform animations from `AnimationName`.

- `frontend/src/components/TouchArea.tsx`
  - Renders visible grouped action buttons for "养宠" and "陪伴".
  - These buttons expose pet actions too directly for the new UX.

- `frontend/src/pet/types.ts`
  - `Mood` and `AnimationName` are current backend/frontend contract enums.
  - `PetEventType` includes existing interaction events such as `pet_head`,
    `poke_face`, `hug`, `pet_pat`, `praise_momo`, `feed_momo`,
    `stay_with_me`, `comfort_me`, `encourage_me`, `listen_to_me`,
    `tuck_in`, `clean_face`, `quiet_company`, `take_a_break`,
    `play_with_momo`.

- `frontend/src/pet/animations.ts` and `frontend/src/pet/faces.ts`
  - Current mapping is mood -> CSS transform / kaomoji.
  - V1.2 should replace user-visible kaomoji rendering with sprite rendering,
    but can keep these mappings as compatibility or fallback during migration.

- `backend/app/runtime/interaction_catalog.py`
  - Defines existing button interaction events, labels, groups, default moods,
    default animations, and state semantics.
  - V1.2 should reuse this catalog as backend semantics, but stop exposing the
    full list as first-class user controls.

- `backend/app/runtime/events.py`
  - Allows interaction events and system events including `user_return`,
    `long_idle`, `night`, `battery_low`, `sleepy_time`, `voice_message`,
    `text_message`.

- `backend/app/pet/rules.py`
  - Applies deterministic state deltas for existing events.
  - V1.2 can add or adjust event semantics, but should be conservative and
    preserve existing state keys.

- `backend/app/runtime/dispatcher.py`
  - Already does snapshot -> slow work -> commit, AgentRun, context, tool,
    provider gate, audio job enqueue, event log, memory candidate collection.
  - Do not replace this chain for V1.2.

- `backend/app/runtime/actions.py`
  - Defines `PetAction` and `PetResponse`, plus allowed moods, animations,
    voice styles, vibrations, and state-affect enums.
  - V1.2 should extend this response contract conservatively with optional
    Doudou behavior-plan fields instead of replacing existing `mood`,
    `face_type`, or `animation`.

- `backend/app/pet/guard.py`
  - Sanitizes model JSON into a safe `PetAction`.
  - V1.2 must validate any model-suggested Doudou action plan here, because the
    model should never directly control arbitrary sprite frames or unbounded
    animation timing.

- `backend/app/pet/prompt_builder.py`
  - Current persona says Momo, kaomoji pet, and button interactions.
  - V1.2 must update prompt/persona to Doudou and sprite-cat behavior.

- `config/app.yaml` and `config/pet_persona.yaml`
  - Still use `Momo`.
  - Runtime `pet_name`, initial state name, wake phrases, progressive audio
    copy, and persona should be migrated to 豆豆.

## Asset Facts

Source package:

```text
/Users/wylam/Downloads/daimaobatiao.codex-pet
```

Recorded asset notes:

```text
/Users/wylam/Downloads/daimaobatiao.codex-pet/ASSET_NOTES.md
/Users/wylam/Downloads/daimaobatiao.codex-pet/animation-manifest.json
```

Codex Pets source:

```text
https://codex-pets.net/#/pets/daimaobatiao
```

Sprite facts:

| Property | Value |
| --- | --- |
| spritesheet | `spritesheet.webp` |
| atlas size | `1536x1872` |
| cell size | `192x208` |
| grid | 8 columns x 9 rows |
| package manifest | `pet.json` has no animation metadata |

Animation rows:

| Codex id | Row | Frames | User meaning |
| --- | ---: | ---: | --- |
| `idle` | 0 | 6 | stands, blinks, tail/body idle |
| `running-right` | 1 | 8 | runs right |
| `running-left` | 2 | 8 | runs left |
| `waving` | 3 | 4 | greets or responds |
| `jumping` | 4 | 5 | happy/excited |
| `failed` | 5 | 8 | upset/error/overwhelmed |
| `waiting` | 6 | 6 | listening/waiting |
| `running` | 7 | 6 | active movement |
| `review` | 8 | 6 | thinking/working/speaking approximation |

Site preview playback is roughly:

```text
duration = max(frames * 260ms, 1400ms)
```

GIF export in Codex Pets appears to use roughly `180ms` per frame.

V1.2 can ship with this asset. It does not yet include dedicated `sleep`,
`cry`, or mouth-flap `talk` rows. Those are future asset work, not required
for V1.2 completion.

## Product Positioning

The pet is now **豆豆**, not Momo.

Personality:

- Cute and clingy, but lightly lazy.
- Likes being noticed and touched.
- Can pretend to be busy.
- Can act sleepy or save energy.
- Can complain softly when over-poked.
- Is not a girlfriend,客服, generic assistant, or animation player.
- Does useful work through the existing model/runtime chain, but presents it
  as "豆豆在听 / 在想 / 在翻小本本 / 在说".

User-facing rule:

```text
The user should not see action buttons for every animation.
The user should mostly see Doudou, a short bubble, press-to-talk, optional text,
and a small more/settings surface.
```

Internal rule:

```text
The internal behavior table can stay rich.
External UI stays simple.
```

## User-Visible Entry Points

V1.2 normal user UI should prioritize:

1. **Doudou sprite**
   - Tap / pointer interaction is the primary "pet" gesture.
   - Long press may become voice entry if it can be implemented without
     conflicting with `VoiceButton`. Otherwise keep voice on the main button.

2. **Short bubble**
   - Shows short local reactions, thinking copy, audio progress, or Doudou's
     short utterance.
   - It should not become a full chat transcript by default.

3. **Press-to-talk**
   - Keep existing `VoiceButton` and phase chain.
   - Rename UI copy from Momo to 豆豆.

4. **Optional text input**
   - Keep current text path for situations where voice is inconvenient.
   - It must continue using `/api/text/chat` and the audio job path.

5. **More/debug**
   - Existing explicit pet-care/companion buttons should move out of the main
     surface. They may live in a collapsed "更多" or debug/developer panel.
   - The main user surface should not show all `TouchArea` actions as a grid.

## Fast Tap Contract

Tap/repeated-tap/over-poke must **not** use the current `/api/pet/event` slow
path as a blocking user interaction. Current `/api/pet/event` calls
`RuntimeDispatcher.handle_event()`, which can run LLM and enqueue TTS. That is
appropriate for deliberate semantic interactions, but it is too heavy for
basic touch feel.

V1.2 must implement tap as two separate paths:

```text
fast local reflection:
  pointer/tap -> behavior director -> sprite/bubble within 100ms

optional state sync:
  throttled/non-blocking event sync -> backend state/log update
```

Requirements:

- A single tap updates only local visible state first: sprite `waving`, local
  short bubble such as "摸到了。", optional light vibration.
- Repeated taps and over-poke are computed locally from recent tap timestamps.
- Tap handling must not set global `busy=true`.
- Tap handling must not disable voice/text input.
- Tap handling must not wait for LLM, TTS, audio job, or backend response.
- Backend sync for tap events must be fire-and-forget or low-priority.
- If backend sync fails, do not replace the local touch reaction with a scary
  error. At most show a quiet fallback after the local animation completes.

Acceptable implementation choices:

1. Add a lightweight endpoint such as `/api/pet/reaction` that applies
   deterministic event rules and records event/log data without LLM/TTS.
2. Extend `/api/pet/event` with an explicit option such as
   `{"local_reaction": true, "synthesize_voice": false, "skip_llm": true}`.
3. Keep `/api/pet/event` for deliberate actions only, and do not call it for
   ordinary taps in V1.2; taps stay local while voice/text continue to use the
   full runtime.

The implementation plan must pick one of these choices before coding. If it
chooses option 2, tests must prove that local-reaction events do not enqueue
audio jobs and do not call the LLM provider.

Suggested event mapping for optional sync:

| Local gesture | Optional backend event | Slow model? | TTS? |
| --- | --- | --- | --- |
| single tap | `pet_pat` or `pet_head` | no | no |
| repeated tap | `hug` or `praise_momo` | no | no |
| over-poke | `poke_face` | no | no |
| deliberate more-menu action | existing catalog event | yes, allowed | yes, allowed |

This resolves the product rule: ordinary touch feels alive immediately, while
the existing conversation chain remains available for deliberate interactions.

## Doudou Scene Table

These scenes are internal behavior design. They do not imply one visible button
per scene.

| Scene | Trigger | User feeling | Sprite action | Model involvement |
| --- | --- | --- | --- | --- |
| Open page | page load / foreground return | Doudou notices the user | `waving` or `jumping` | optional short greeting |
| Long absence return | last interaction exceeds threshold | Doudou is a little wronged but happy | `failed -> waving` | yes, based on absence duration |
| Ambient idle | no user operation | Doudou lives on its own | `idle`, occasional `waiting/review` | rare "little thought" |
| Tap pet | tap Doudou | Doudou was touched | `waving` | no, local copy |
| Repeated taps | several taps in a short window | Doudou enjoys attention | `jumping` | no |
| Over-poking | high-frequency taps | Doudou complains cutely | `failed`, then cooldown / idle | optional short complaint |
| Press-to-talk | hold voice / long press | Doudou listens seriously | `waiting` | no, must be instant |
| ASR processing | release after recording | Doudou waits for recognition | `waiting` | no |
| Thinking | LLM request in flight | Doudou pretends to work / flips notebook | `review` | yes, answer style/content |
| TTS speaking | audio playing | Doudou speaks | `review`; future `talk` row | yes, reply content |
| Answer done | audio ended | returns to companion mode | `waving` or `idle` | optional short tail copy |
| Error / unclear | ASR/LLM/TTS failure | Doudou is a bit wronged | `failed` | no, local fallback |
| Long idle proactive | idle threshold and proactive allowed | Doudou comes to nudge user | `running -> waving` or just `waving` | yes, low frequency |
| Night | time / user quiet mode | Doudou becomes lazy and quiet | `idle/waiting`; future `sleep` | optional, avoid interrupting |
| Battery low / phone busy | device state | Doudou saves energy | `idle`, lower animation rate | no |

## Sprite Mapping

The frontend should introduce a sprite behavior layer that maps existing backend
`Mood` / `AnimationName` / event phase into Codex Pet animations.

Initial mapping:

| Backend/UI state | Doudou sprite |
| --- | --- |
| `idle` / `breathing` | `idle` |
| `happy` / `bounce` | `waving` or `jumping` depending on scene |
| `excited` / `jump` | `jumping` |
| `shy` / `wiggle` | `waving` |
| `thinking` / `blink` | `review` |
| `concerned` / `tilt` | `waiting` or `failed` depending on error |
| `sad` / `droop` | `failed` |
| `sleepy` / `slowBlink` | `idle` or `waiting` until sleep asset exists |
| `angry` / `shake` | `failed` |
| `lonely` / `small` | `waiting` or `failed` |
| `phase=listening` | `waiting` |
| `phase=waiting_voice` | `review` |
| `phase=speaking` | `review` |
| `phase=audio_error/error` | `failed` |

The renderer should support:

- loop actions: `idle`, `waiting`, `review`, `running*`;
- one-shot actions: `waving`, `jumping`, `failed`;
- one-shot completion fallback, usually back to `idle` unless the current phase
  is still `listening`, `thinking`, `waiting_voice`, or `speaking`;
- `image-rendering: pixelated`;
- stable dimensions based on `192 / 208` aspect ratio;
- no text overflow or layout shift caused by sprite frames.

## Model-Selected Atomic Action Plan

V1.2 should treat Doudou's sprite actions as a small, safe action toolbox.
The model can select and sequence these atomic actions to make a reply feel
performed, but it must not control frames, sprite rows, CSS, timing without
limits, or protected UI phases.

Atomic action whitelist:

| Action | Type | Intended meaning |
| --- | --- | --- |
| `idle` | loop | neutral companion / lazy standing |
| `waiting` | loop | listening, waiting, soft attention |
| `review` | loop | thinking, pretending busy, working |
| `waving` | one-shot | greeting, touched, gentle response |
| `jumping` | one-shot | happy, excited, clingy affection |
| `failed` | one-shot | wronged, unclear, error, over-poked |
| `running` | loop/brief | active approach / proactive movement |
| `running-left` | loop/brief | directional movement if UI uses it |
| `running-right` | loop/brief | directional movement if UI uses it |

Recommended response extension:

```json
{
  "reply": "哼，豆豆刚才才没有一直等你……只等了一小会儿。",
  "mood": "happy",
  "face_type": "happy",
  "animation": "bounce",
  "voice_style": "happy",
  "vibration": "light",
  "intent": "long_absence_return",
  "behavior_intent": "clingy_wronged_happy",
  "behavior_plan": [
    { "action": "failed", "slot": "before_speech", "duration_ms": 900 },
    { "action": "waving", "slot": "speech", "duration_ms": 1400 },
    { "action": "jumping", "slot": "after_speech", "duration_ms": 1000 }
  ],
  "state_delta": {},
  "state_affect": {},
  "memory_update": { "should_save": false, "content": "" }
}
```

The existing fields remain required for backward compatibility. The new fields
are optional:

- `behavior_intent`: a compact semantic label used for fallback mapping and
  debugging. Examples: `soft_comfort`, `clingy_happy`,
  `clingy_wronged_happy`, `lazy_busy`, `quiet_sleepy`, `playful_proud`,
  `confused_wronged`, `neutral_companion`.
- `behavior_plan`: a short list of atomic action calls.

Each `behavior_plan` item has:

| Field | Required | Allowed values / limits |
| --- | --- | --- |
| `action` | yes | one of the atomic action whitelist |
| `slot` | no | `before_speech`, `speech`, `after_speech`, `idle_after` |
| `duration_ms` | no | integer clamped to 600-2500 |
| `loop` | no | boolean hint; ignored if unsafe |

Validation requirements:

- Maximum 4 actions per plan.
- Maximum total duration 8000ms after clamping.
- Unknown actions are dropped.
- Unknown slots become `speech`.
- Invalid or missing durations use the default for the action:
  - `failed`: 900ms;
  - `waving`: 1200ms;
  - `jumping`: 1200ms;
  - `review`, `waiting`, `idle`, `running*`: 1400ms.
- Empty or fully invalid plans are replaced by a fallback plan based on
  `behavior_intent`, then `mood`, then current `phase`.
- The plan must not include frame indexes, row numbers, asset paths, CSS, or
  arbitrary scriptable behavior.
- The plan is advisory. Frontend protected phases can delay, skip, or replace
  actions when user input/audio safety requires it.

Fallback intent mapping:

| `behavior_intent` | Fallback Doudou plan |
| --- | --- |
| `soft_comfort` | `review -> waving -> waiting -> idle` |
| `clingy_happy` | `waving -> jumping -> idle` |
| `clingy_wronged_happy` | `failed -> waving -> jumping -> idle` |
| `lazy_busy` | `review -> idle` |
| `quiet_sleepy` | `waiting -> idle` |
| `playful_proud` | `jumping -> waving -> idle` |
| `confused_wronged` | `failed -> waiting -> idle` |
| `neutral_companion` | `waving -> idle` |

Fallback mood mapping when intent is absent:

| Backend mood | Fallback Doudou plan |
| --- | --- |
| `happy`, `shy` | `waving -> idle` |
| `excited` | `jumping -> idle` |
| `thinking` | `review -> idle` |
| `sad`, `angry`, `concerned`, `lonely` | `failed -> waiting -> idle` |
| `sleepy` | `waiting -> idle` |
| `idle` | `idle` |

Backend responsibilities:

- Extend `backend/app/runtime/actions.py` with typed behavior-plan models and
  optional fields on `PetAction` / `PetResponse`.
- Extend `backend/app/pet/guard.py` to sanitize `behavior_intent` and
  `behavior_plan`.
- Extend `backend/app/pet/prompt_builder.py` output schema so the model knows
  it may choose Doudou atomic actions.
- Extend `backend/app/runtime/dispatcher.py` to include the sanitized plan in
  API responses.
- Keep API compatibility: clients that ignore `behavior_plan` must still work
  using existing `reply`, `mood`, `face_type`, `animation`, `audio_job_id`.

Frontend responsibilities:

- Extend `frontend/src/pet/types.ts` with `DoudouAction`,
  `DoudouBehaviorSlot`, `DoudouBehaviorStep`, and optional
  `behavior_intent` / `behavior_plan` on response types.
- Add frontend validation too. Do not trust backend/model output blindly.
- The behavior director should accept sanitized model plans through
  `onBackendResponse(response, phase)`.
- Execute slots approximately:
  - `before_speech`: after text response arrives, before audio playback starts;
  - `speech`: while TTS audio is pending/playing;
  - `after_speech`: after audio ends or after text-only reply is displayed;
  - `idle_after`: final transition if no protected phase is active.
- V1.2 does not require phoneme or word-level sync. "Speaking with motion" is
  approximate slot-based playback.

Fast-path boundary:

- Tap, repeated tap, over-poke, press-to-talk start, release-to-thinking, and
  local error fallback still have deterministic local actions.
- The model action plan enhances semantic replies and proactive scenes; it must
  not be required for instant touch or voice feedback.

## Frontend Behavior Director

Add a local director layer instead of letting `App.tsx` directly map every
backend mood to a visible face.

Suggested shape:

```text
frontend/src/pet/doudouSprites.ts
frontend/src/pet/doudouBehaviorPlan.ts
frontend/src/pet/behaviorDirector.ts
frontend/src/components/DoudouSprite.tsx
```

Responsibilities:

- Maintain visible sprite action independent of raw backend mood.
- Apply instant local reaction before HTTP/model calls.
- Track tap count and over-poke cooldown.
- Track an ambient idle timer for "lazy / pretending busy / self-occupied"
  behavior.
- Decide whether a one-shot animation may interrupt the current phase.
- Keep `listening`, `speaking`, and `waiting_voice` protected from idle or
  proactive interruptions.
- Fall back to `idle` if an unknown state/action arrives.
- Keep old kaomoji rendering only as development/fallback path if needed.

Priority rules:

```text
listening > speaking > waiting_voice > audio_error/error > thinking > tap reaction > proactive > ambient > idle
```

Interrupt rules:

- Tap can interrupt `idle`, ambient `waiting`, and ambient `review`.
- During `listening`, `speaking`, or `waiting_voice`, tap may produce at most
  a tiny local acknowledgement if it does not change phase; it must not replace
  the protected sprite action.
- Proactive must not interrupt user voice/text/audio phases.
- `audio_error/error` can interrupt ordinary thinking/tap/proactive states,
  but must not cancel active recording. It should recover automatically.
- One-shot `waving`, `jumping`, `failed` returns to the protected phase action
  if a protected phase is still active; otherwise returns to `idle`.

State ownership:

| State | Owner | Notes |
| --- | --- | --- |
| `phase` | `App.tsx` / voice/audio pipeline | authoritative for voice/text/audio lifecycle |
| `busy` | only network/audio tasks that block user commands | tap reflection must not set it |
| `visibleSpriteAction` | behavior director | can differ from backend `animation` |
| `bubbleText` | App + director | local copy can be replaced by model/audio copy when appropriate |
| `petState` | backend response | local tap may not mutate persistent state without backend sync |
| tap counters/cooldowns | behavior director | local only, bounded in memory |

The director should expose explicit inputs/outputs, for example:

```text
director.onTap(now, phase) -> visible action + local bubble + optional sync event
director.onBackendResponse(response, phase) -> sanitized behavior plan + bubble policy
director.onPhaseChange(phase) -> protected action
director.onAmbientTick(now, phase, busy) -> optional ambient action
```

`App.tsx` should call the director instead of directly setting `faceType` and
`animation` for every user-visible transition. Backend `mood/animation` remains
stored for compatibility, but Doudou's visible sprite is director-controlled.
When a backend response includes `behavior_plan`, the director should enqueue
the allowed steps by slot. If no valid plan exists, it should derive a fallback
from `behavior_intent`, then mood/phase.

Fast reaction requirements:

| Trigger | Required visible response |
| --- | --- |
| tap Doudou | local sprite change within 100ms |
| repeated tap | local sprite change within 100ms |
| over-poke | local `failed` reaction within 100ms |
| press-to-talk starts | `waiting` within 100ms after recorder starts |
| release voice | `review`/thinking within 100ms after release |
| HTTP/model slow | keep local sprite/bubble active; do not freeze |
| audio starts | `review`/speaking within 100ms |
| audio ends | return to `idle` or `waving` promptly |

Voice button note:

The current `VoiceButton` intentionally uses a press-to-record arm delay. The
100ms target applies after recording actually starts and after release enters
thinking; V1.2 may keep the arm delay if tests and copy make the hold gesture
clear. If long-press on the sprite is implemented, it must share the same
recorder path and must not duplicate audio upload logic.

## Ambient Local Life

Doudou needs a small, local "life loop" so personality does not depend only on
LLM/proactive events.

Minimum V1.2 ambient behavior:

- Runs only when `phase=idle`, not `busy`, and the document is visible.
- Uses a low-frequency timer, e.g. every 20-45 seconds with jitter.
- Has a cooldown after any user interaction, e.g. no ambient action for 10-20
  seconds after tap/voice/text.
- Chooses from a small local set:
  - `idle`: do nothing / breathe;
  - `waiting`: Doudou looks around or waits;
  - `review`: Doudou pretends to be busy;
  - rare `waving`: Doudou notices the user.
- Bubble copy is optional and rare. Do not spam text.
- Does not call LLM/TTS by default.
- Does not call backend proactive by itself; existing proactive polling remains
  separate and lower priority than user work.

Example local copy pool:

```text
我刚刚没有偷懒。
豆豆在看家。
我在翻小本本。
省一点电也很重要。
```

Testing must prove ambient ticks do not fire during `listening`, `speaking`,
`waiting_voice`, or while `busy=true`.

## Main UI Changes

Required:

- Replace visible `PetFace` kaomoji with `DoudouSprite` for the normal UI.
- Keep `PetBubble`.
- Rename user-facing strings from Momo to 豆豆.
- Use `clientConfig.pet_name` where practical instead of hardcoded pet name.
- Remove or collapse the main `TouchArea` grid.
- Provide tap interaction on the sprite itself.
- Keep `VoiceButton` and `TextInputBar` functional.
- Keep `VoiceModeToggle` unless it is intentionally moved into more/settings.
- Keep secondary actions such as "换个话题" and "重新认识" only if they do not
  visually dominate the main pet experience. Wording should use 豆豆.

Recommended first-pass UI layout:

```text
StatusBar (can stay)
Doudou sprite
Bubble
TextInputBar (optional, compact)
VoiceModeToggle + VoiceButton
More button (collapsed tools/settings/debug)
```

Do not expose the full animation list to normal users. Debug controls may still
exist for development, but should be separated from the primary user path.

## Backend / Persona Changes

Required config/persona migration:

- `config/app.yaml`
  - `runtime.pet_name: 豆豆`
  - `state.initial.name: 豆豆`
  - activation wake phrases should include `豆豆`, e.g. `豆豆`, `嗨豆豆`,
    `你好豆豆`.
  - old Momo wake phrases may remain temporarily as aliases during migration,
    but user-visible copy should prefer 豆豆.

- `config/pet_persona.yaml`
  - `name: 豆豆`
  - `species` should describe a sprite cat / phone pet, not a kaomoji pet.
  - `system_prompt` should reflect Doudou's personality:
    cute, clingy, slightly lazy, can pretend to be busy, softly complains when
    over-poked, voice-first, no kaomoji output.
  - Keep JSON-only output contract and existing allowed moods/animations.
    The optional `behavior_intent` / `behavior_plan` fields are the intended
    V1.2 extension and must be guarded before reaching the frontend.

- `backend/app/pet/prompt_builder.py`
  - Update button interaction wording to scene/gesture wording where needed.
  - Avoid "按钮" as a user-facing concept in the prompt when the main UI no
    longer exposes a button grid. Use "互动事件" or "用户摸了/戳了/陪你".

- Public endpoint copy
  - `/api/runtime/client-config` progressive audio messages should say 豆豆.
  - Runtime logs can keep PetAgent wording, but user-visible UI copy should not
    say Momo after migration.

Required naming audit:

Before implementation finishes, run:

```bash
rg -n "Momo|momo" frontend/src backend/app config
```

Every hit must be classified into one of these categories:

1. **Must rename to 豆豆**
   - user-visible frontend copy;
   - aria labels and visible headings;
   - default client config copy;
   - public API fallback replies;
   - provider fallback replies;
   - persona and prompt text visible to the model as the pet identity;
   - proactive rule replies;
   - TTS voice prompt identity.

2. **May keep temporarily as compatibility**
   - TypeScript/Python function names such as `wakeMomo` / `exitMomo` if
     renaming them would create unnecessary churn;
   - event ids such as `feed_momo`, `praise_momo`, `play_with_momo`;
   - config key names such as `momo_memories_path`;
   - memory card internal names such as `momo_memories`;
   - tests that explicitly verify old wake aliases still work.

3. **Should rename later in a compatibility migration**
   - event ids and storage keys that include `momo` but are part of persisted
     contracts.

The implementation notes must include the final grep output summary: renamed
count, compatibility hits retained, and any deferred migration items.

Event and state rules:

- Keep existing `PetEventType` and `INTERACTION_CATALOG` for compatibility.
- Existing events may be triggered by gestures instead of visible buttons:
  - tap: `pet_head` or `pet_pat`;
  - repeated tap: `hug` or `praise_momo` during migration, eventually renamed;
  - over-poke: `poke_face`;
  - "quiet company" and "take a break" can live under a collapsed more menu.
- Do not remove existing event ids in V1.2 unless all tests and callers are
  migrated. Backward compatibility matters for current API tests and memory
  logs.

## Model Involvement Boundary

The model should not control sprite frames directly. It may select from the
atomic Doudou action toolbox through `behavior_intent` and `behavior_plan`.

Allowed model responsibilities:

- Generate Doudou's reply.
- Choose a short `behavior_intent`.
- Propose a short `behavior_plan` using only whitelisted atomic sprite actions.
- Generate short scene copy for long absence, proactive nudge, thinking tone,
  and complex emotional context.
- Use memory/context to make Doudou vary naturally.
- Choose allowed backend `mood`, `face_type`, `animation`, `voice_style`,
  `vibration`, and conservative `state_delta` through existing JSON schema.

Forbidden model responsibilities:

- Output arbitrary sprite row/frame numbers.
- Output arbitrary animation names outside the Doudou action whitelist.
- Output plans longer than the allowed system limits.
- Block tap/press feedback.
- Decide whether local UI should acknowledge a touch.
- Produce long chat transcript UI by default.
- Produce kaomoji.

Fallback rules:

- If `behavior_plan` is missing or invalid, use `behavior_intent` fallback.
- If `behavior_intent` is missing or invalid, use `mood` fallback.
- If model/provider is slow, Doudou keeps showing local thinking/review.
- If model/provider fails, Doudou shows local `failed` and a short error bubble.
- If TTS fails, keep retry audio behavior but copy should say 豆豆.
- If sprite asset fails to load, show a minimal fallback but do not crash the app.

## Asset Compatibility Requirements

The implementation must account for old Android/WebView behavior.

Requirements:

- Preload the sprite asset and expose an asset-loaded / asset-error state.
- If `spritesheet.webp` fails, fall back to a static PNG/WebP poster or a
  minimal non-crashing fallback.
- Do not rely only on modern CSS if avoidable. `aspect-ratio` may be used with
  explicit width/height fallback styles for old WebView.
- Avoid canvas unless necessary; CSS `background-position` is acceptable if
  tested. If canvas is used, add a nonblank pixel check.
- Keep memory low: one spritesheet, one optional poster/fallback image, no
  repeated large decoded copies.
- Set stable pixel dimensions and responsive max sizes so frame changes do not
  shift layout.
- Use `image-rendering: pixelated`, with safe fallback for browsers that ignore
  it.

Testing must include desktop/mobile viewport screenshots or equivalent DOM
assertions, and if the phone is reachable, an old-WebView live asset-load check.

## Conversation Chain Preservation

V1.2 must preserve:

- `/api/voice/chat`
- `/api/text/chat`
- `/api/pet/event`
- `/api/audio/jobs/{job_id}`
- `/api/frontend/heartbeat`
- `/api/pet/proactive` and `/api/pet/proactive/trigger`
- `RuntimeDispatcher` AgentRun/event-log/audio-job flow
- context/memory candidate collection
- activation flow, with Doudou wake phrases added

The old kaomoji display logic can be ignored for normal UI, but the underlying
conversation, state, audio, memory, and proactive chain must keep working.

## Out Of Scope For V1.2

- Building the lightweight APK shell.
- Native Android/Termux service integration changes.
- Replacing FastAPI or SQLite.
- Reworking the whole agent runtime.
- Adding dedicated generated `sleep`, `talk`, `cry`, `grooming`, or `annoyed`
  sprite rows.
- Making every internal scene user-configurable.
- Deleting all old Momo event ids in one pass.

Future asset priority if image generation is used later:

1. `sleep`
2. `talk` mouth-flap, 2-3 frames
3. cute annoyed / over-poked
4. grooming / self-care
5. cry/sad

## Mandatory Stage Execution Protocol

V1.2 must be executed in stages. Do not implement the whole spec in one large
change. Each stage is a commit boundary and must finish with review, tests,
commit, and push.

For every stage:

1. **Write a stage plan before code changes.**
   - Save it under `plan/V1.2/stages/stage-N-<short-name>.md`.
   - The plan must list exact files to touch, behavior goals, tests to run,
     rollback notes, and known risks.
   - The stage plan must explicitly say how it preserves voice/text/audio job
     and existing runtime behavior.

2. **Run a pre-implementation subagent review.**
   - The subagent must review the stage plan against this spec and the current
     project code.
   - The review must return `PASS` or `FIX`.
   - If `FIX`, update the stage plan before editing implementation files.
   - Save the review notes under
     `plan/V1.2/stages/stage-N-<short-name>-pre-review.md`.

3. **Implement only the reviewed stage scope.**
   - Do not pull work from later stages unless the stage plan says it is a
     required dependency.
   - Preserve unrelated user changes.
   - Do not delete persisted data, secrets, `.env`, `backend/data/pet.db`, or
     git history.

4. **Run the stage tests.**
   - Each stage has minimum test goals listed below.
   - If a command cannot run, document why in the stage plan or completion note.

5. **Run a completion subagent review.**
   - The subagent must compare the diff to this spec, the stage plan, and
     current code.
   - It should check missing requirements, regressions, mobile/WebView risk,
     naming leaks, and weak tests.
   - If the review returns `FIX`, repair the code and rerun relevant tests.
   - Save the review notes under
     `plan/V1.2/stages/stage-N-<short-name>-completion-review.md`.

6. **Commit and push.**
   - Commit only the stage changes and its plan/review artifacts.
   - Push to GitHub after the commit.
   - If push fails due to network/proxy, document the failure and retry when
     network is available. The stage is not complete until pushed.

7. **Record test results.**
   - The final stage note must include commands run, pass/fail status, known
     skipped checks, and whether Nubia live verification is still pending.
   - Save the final stage note under
     `plan/V1.2/stages/stage-N-<short-name>-completion.md`.

## Stage Plan

V1.2 has **6 implementation stages**. Phone/Nubia live checks are included in
Stage 6 because the device may be unavailable during local development.

### Stage 1: Sprite Asset And Renderer Foundation

Goal:

- Bring `daimaobatiao` assets into the frontend.
- Add sprite manifest/types and `DoudouSprite`.
- Render nonblank Doudou sprite with stable dimensions and fallback.

Expected files:

- `frontend/src/assets/...` or equivalent asset path.
- `frontend/src/pet/doudouSprites.ts`
- `frontend/src/components/DoudouSprite.tsx`
- related CSS and tests.

Minimum tests:

- Unit test that the manifest exposes `1536x1872`, `192x208`, 8 columns, 9 rows.
- Unit/DOM test that `DoudouSprite` renders the correct background image,
  background size/position, dimensions, and accessibility label.
- Test asset-error fallback path if feasible.
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

Stage completion criteria:

- Doudou sprite can render without replacing the whole app yet.
- No conversation/runtime code changed.
- Commit and push completed.

### Stage 2: Behavior Director And Fast Tap Contract

Goal:

- Add local behavior director.
- Implement fast tap, repeated tap, over-poke, protected phases, and ambient
  local life.
- Add frontend behavior-plan types, validator, fallback mapping, and queue
  logic for model-selected atomic actions.
- Decide and implement tap backend sync strategy.

Required stage-plan decision:

- Choose one fast tap sync option from **Fast Tap Contract**:
  1. new lightweight endpoint;
  2. `/api/pet/event` skip-LLM/TTS option;
  3. local-only tap for V1.2.

Expected files:

- `frontend/src/pet/behaviorDirector.ts`
- `frontend/src/pet/doudouBehaviorPlan.ts` or equivalent focused helper.
- `frontend/src/pet/types.ts`
- tests for the director.
- optional backend API/runtime files only if endpoint/skip option is chosen.

Minimum tests:

- Tap returns visible `waving` action without awaiting network.
- Repeated tap escalates to `jumping`.
- Over-poke escalates to `failed` and enters cooldown.
- Tap does not set global `busy=true`.
- Tap does not disable voice/text controls.
- Protected phases are not interrupted.
- Ambient tick fires only during idle/not busy/document visible.
- Valid model `behavior_plan` is accepted and queued by slot.
- Unknown model actions, unknown slots, invalid durations, and overlong plans
  are sanitized or dropped.
- Missing/invalid plan falls back through `behavior_intent`, then mood, then
  phase without crashing.
- If backend sync exists, backend tests prove no LLM call and no audio job.
- Relevant frontend tests plus backend tests for any touched backend code.

Stage completion criteria:

- Fast touch feel is implemented and tested in isolation.
- Frontend can execute a sanitized behavior plan even before backend prompt
  output is wired.
- Voice/text/audio paths are not integrated yet unless the stage plan requires
  a minimal hook.
- Commit and push completed.

### Stage 3: Main UI Integration And Action Button Collapse

Goal:

- Replace normal `PetFace` usage with `DoudouSprite`.
- Wire `App.tsx` to behavior director for visible sprite and bubble policy.
- Wire backend `behavior_plan` slots into text/voice/audio phases so Doudou can
  perform before speech, during TTS, and after speech.
- Collapse or remove the full `TouchArea` grid from the primary UI.
- Preserve `VoiceButton`, `TextInputBar`, `VoiceModeToggle`, audio polling,
  heartbeat, and proactive behavior.

Expected files:

- `frontend/src/App.tsx`
- `frontend/src/components/TouchArea.tsx` or replacement/collapsed menu.
- `frontend/src/styles.css`
- affected tests.

Minimum tests:

- App renders Doudou sprite, not kaomoji.
- Normal UI does not render full "养宠/陪伴" grid.
- Tap on sprite updates UI before unresolved backend request.
- Text submit still posts to `/api/text/chat`.
- Text response with `behavior_plan` executes allowed before/speech/after slots.
- Voice button still transitions listening -> thinking/waiting_voice.
- Voice response with `behavior_plan` does not interrupt active recording and
  executes only after the backend response is available.
- Audio job ready still reaches speaking and then idle.
- Audio end triggers `after_speech` or safe idle fallback.
- Proactive response does not interrupt protected voice/audio phases.
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

Stage completion criteria:

- Main user experience is sprite-first.
- Existing conversation chain still passes frontend tests.
- Commit and push completed.

### Stage 4: Doudou Naming, Persona, Activation, And Compatibility

Goal:

- Migrate user-visible identity from Momo to 豆豆.
- Update config/persona/client copy/provider fallback copy.
- Extend backend model output schema and guard so the LLM can choose Doudou
  atomic actions through `behavior_intent` and `behavior_plan`.
- Preserve compatibility event ids and old wake aliases where needed.

Expected files:

- `config/app.yaml`
- `config/pet_persona.yaml`
- `frontend/src/**`
- `backend/app/runtime/actions.py`
- `backend/app/pet/guard.py`
- `backend/app/pet/prompt_builder.py`
- `backend/app/runtime/dispatcher.py`
- other `backend/app/**` user-visible copy and prompt text.
- tests for activation/config/fallback copy.

Required audit:

```bash
rg -n "Momo|momo" frontend/src backend/app config
```

The stage completion note must classify every remaining hit as:

- renamed;
- retained compatibility function/id/key;
- deferred future migration.

Minimum tests:

- `client-config` returns `pet_name: 豆豆`.
- Doudou wake phrases work.
- Retained old Momo aliases work if kept.
- Normal UI has no visible `Momo`.
- Persona/config loads.
- Prompt output schema includes `behavior_intent` and `behavior_plan` with the
  atomic action whitelist.
- `guard_action()` keeps a valid behavior plan and removes/repairs invalid
  model plan fields.
- `PetResponse` includes sanitized optional behavior-plan fields while
  preserving the existing response shape.
- Existing event ids such as `feed_momo` still normalize.
- `cd backend && ../.venv/bin/python -m pytest -v`
- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

Stage completion criteria:

- User-visible identity is 豆豆.
- Compatibility ids are intentionally retained and documented.
- Commit and push completed.

### Stage 5: Full Local Verification And Hardening

Goal:

- Run the full local test plan.
- Add missing tests discovered in Stages 1-4.
- Verify fallback behavior and old WebView-safe assumptions locally as much as
  possible.

Minimum tests:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- --run
npm run build

cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest -v
```

Additional checks:

- Grep audit for Momo/momo repeated and documented.
- Manual or automated desktop/mobile viewport check.
- Sprite nonblank rendering check if Playwright/canvas/screenshot tooling is
  available.
- Confirm no API key, `.env`, token, or database content appears in diff/logs.

Stage completion criteria:

- Full local tests pass.
- Any skipped Nubia live tests are clearly marked as pending phone availability.
- Commit and push completed.

### Stage 6: Nubia Live Verification And Deployment

Goal:

- Verify V1.2 on the actual phone runtime once the phone is charged/reachable.
- Complete live smoke tests before final acceptance.

Minimum checks:

```bash
ssh nubia-home 'curl -fsS http://127.0.0.1:8000/api/health'
ssh nubia-home 'curl -fsS http://127.0.0.1:8000/api/runtime/client-config'
```

If deploying updated code/build to the phone is in scope for the stage plan,
the plan must specify exact sync/build/restart commands and rollback steps.

Phone browser/WebView checks:

- Visible pet name is 豆豆.
- Sprite loads on old Android/WebView and is nonblank.
- Tap reaction is immediate.
- Voice press-to-talk gives immediate listening feedback.
- Text path sends and audio job plays.
- Refresh preserves usability.
- Full action button grid is not the main UI.

Live API smoke test, when safe:

```bash
cd ~/Petagent/backend
PETAGENT_TEST_URL=http://127.0.0.1:8000 \
PETAGENT_INTERNAL_TOKEN_FILE=../backend/secrets/internal_token \
../.venv/bin/python -m pytest tests/test_live_nubia.py -q
```

Stage completion criteria:

- Live checks pass or failures are fixed and retested.
- Final stage review passes.
- Commit and push completed.
- V1.2 can be marked complete only after this stage, unless the user explicitly
  accepts local-only completion with Nubia verification deferred.

## Implementation Notes

Suggested implementation order:

1. Copy `spritesheet.webp` and `animation-manifest.json` into frontend assets,
   using a path that Vite can bundle or serve reliably.
2. Add `DoudouSprite` and sprite manifest types.
3. Add frontend Doudou behavior-plan types, validator, fallback mapping, and
   slot queue.
4. Add behavior director / sprite mapping with protected phase rules.
5. Decide and implement the fast tap sync strategy from **Fast Tap Contract**.
6. Replace `PetFace` usage in `App.tsx` with `DoudouSprite` for normal UI.
7. Make sprite tap trigger local fast reaction; optional backend sync must be
   non-blocking and must not enqueue audio/LLM.
8. Add minimum ambient local life loop.
9. Collapse or move `TouchArea` full grid out of the primary path.
10. Extend backend `PetAction` / `PetResponse`, guard, prompt schema, and
    dispatcher response to carry sanitized `behavior_intent` / `behavior_plan`.
11. Run the naming audit and rename visible Momo copy to 豆豆.
12. Update config/persona and activation phrases.
13. Adjust tests.
14. Build, backend tests, frontend tests, and live smoke plan.

Keep changes scoped. Do not refactor unrelated runtime code.

## Testing Plan

V1.2 cannot be accepted until this test plan is completed or explicitly waived
with a documented reason.

### Static / Unit Verification

Run from project root or relevant subdirectory:

```bash
cd /Users/wylam/Documents/workspace/Petagent/frontend
npm test -- --run
npm run build
```

Required frontend coverage:

- `DoudouSprite` renders a sprite frame with correct atlas dimensions.
- The idle animation loops and uses pixelated rendering.
- One-shot animation returns to the expected fallback.
- Doudou behavior-plan validator accepts only whitelisted atomic actions.
- Doudou behavior-plan validator clamps durations, limits plans to 4 steps,
  and limits total duration to 8000ms.
- Invalid or missing behavior plans fall back from `behavior_intent` to mood to
  phase.
- Slot execution supports `before_speech`, `speech`, `after_speech`, and
  `idle_after` without requiring word-level audio sync.
- Tap on Doudou causes immediate local reaction before `/api/pet/event`
  resolves.
- Tap on Doudou does not set global `busy=true`.
- Tap on Doudou does not disable voice/text controls.
- If backend sync is implemented for tap, it does not request LLM/TTS and does
  not enqueue `audio_job_id`.
- Repeated taps escalate to `jumping`.
- Over-poke escalates to `failed` and cooldown.
- Protected phases (`listening`, `waiting_voice`, `speaking`) are not
  interrupted by tap/proactive reactions.
- Ambient local life tick can show `waiting`/`review`, but never during
  protected phases or `busy=true`.
- Text chat still posts to `/api/text/chat` and plays audio job.
- Voice button still transitions through listening -> thinking/waiting_voice
  -> speaking or audio_error.
- UI visible copy uses 豆豆, not Momo, except compatibility/debug contexts
  explicitly documented in tests.
- Default main UI does not render the full "养宠/陪伴" action grid.
- Normal UI has no visible text `Momo`.

Backend tests:

```bash
cd /Users/wylam/Documents/workspace/Petagent/backend
../.venv/bin/python -m pytest -v
```

Required backend coverage:

- `client-config` returns `pet_name` as 豆豆 after config change.
- Activation accepts Doudou wake phrases.
- Existing Momo aliases, if retained, still work during migration.
- Existing `/api/pet/event` event ids still normalize.
- `guard_action()` preserves valid `behavior_intent` / `behavior_plan` fields.
- `guard_action()` drops unknown Doudou actions, repairs unknown slots, clamps
  duration, truncates overlong plans, and falls back safely on invalid plans.
- `build_pet_messages()` prompt payload/output schema tells the model to choose
  only whitelisted Doudou atomic actions.
- Runtime responses include optional sanitized `behavior_plan` without removing
  existing `mood`, `face_type`, `animation`, `voice_url`, or `audio_job_id`.
- Any new lightweight local-reaction endpoint or `/api/pet/event` option skips
  LLM/TTS and preserves deterministic state/log behavior.
- Persona/config loads successfully.
- No secret or API key is printed in test output.
- `rg -n "Momo|momo" frontend/src backend/app config` audit has documented
  remaining compatibility hits.

### Local Manual Browser Verification

If a local dev server is used, verify at least:

- Doudou appears as a sprite, not kaomoji.
- The sprite is not blank in desktop and mobile viewport sizes.
- Tap response is visible immediately even if network is delayed.
- Voice path still records, uploads, waits for audio, plays, and returns to idle.
- Text path still sends and speaks response.
- Audio timeout/error shows Doudou error state and retry copy.
- Main UI no longer shows the full action-button grid.
- Sprite asset failure fallback does not crash the UI.

Use Playwright or equivalent screenshot checks if available. For sprite/canvas
or CSS background rendering, include a nonblank-pixel check if the final
implementation uses canvas or background-position rendering.

### Nubia / Termux Live Verification

When the phone is reachable:

```bash
ssh nubia-home 'curl -fsS http://127.0.0.1:8000/api/health'
ssh nubia-home 'curl -fsS http://127.0.0.1:8000/api/runtime/client-config'
```

Then from the phone browser/WebView:

- Load PetAgent and confirm the visible name is 豆豆.
- Confirm the sprite asset loads on the old Android/WebView.
- Tap Doudou and confirm immediate reaction.
- Long press voice and confirm listening feedback.
- Send one text message and confirm audio job playback.
- Confirm the frontend remains usable after a refresh.

Live API smoke test, when safe:

```bash
cd ~/Petagent/backend
PETAGENT_TEST_URL=http://127.0.0.1:8000 \
PETAGENT_INTERNAL_TOKEN_FILE=../backend/secrets/internal_token \
../.venv/bin/python -m pytest tests/test_live_nubia.py -q
```

### Performance / Responsiveness Acceptance

Measured or manually verified targets:

| Interaction | Pass target |
| --- | ---: |
| tap visual reaction | under 100ms |
| press-to-talk visual reaction after recorder starts | under 100ms |
| release-to-thinking visual reaction | under 100ms |
| local fallback bubble | under 150ms |
| audio phase change after ready voice URL | under 100ms |
| no visible layout shift on sprite frame change | required |

### Regression Checks

Must not regress:

- `/api/health` remains light and responsive.
- `/api/voice/chat` and `/api/text/chat` still return compatible response
  shapes.
- `audio_job_id` polling still works.
- Frontend heartbeat still sends.
- Proactive trigger does not interrupt voice/audio phases.
- Runtime state values remain clamped.
- Existing event ids remain accepted.
- Tap local reaction must not create audio jobs or call the model.
- Main UI Momo text must not reappear in normal user flows.

## Acceptance Criteria

V1.2 passes only when:

1. User-visible pet name is 豆豆 across normal UI.
2. Normal UI shows sprite-based Doudou instead of kaomoji.
3. Full action-button grid is removed from the main path or collapsed away from
   the primary pet experience.
4. Tap/voice/text interactions all still use the existing backend runtime chain.
5. Tap and voice phase feedback are immediate and do not wait for LLM/TTS.
6. Doudou scenes map to existing sprite actions with safe fallbacks.
7. Existing conversation, memory, AgentRun, and audio job paths still work.
8. The full testing plan above is completed and results are recorded.

## Open Decisions

- Whether long-press on the sprite itself should start recording in V1.2 or
  whether the existing `VoiceButton` remains the only voice entry.
- Whether `TouchArea` becomes a collapsed user "more" menu or a debug-only panel.
- Whether old `praise_momo`, `feed_momo`, and related event ids should be
  renamed in a future compatibility migration. For V1.2, keep ids stable.
- Whether to keep a hidden kaomoji fallback for asset-load failure.
