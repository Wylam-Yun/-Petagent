# V1.4 Stage 0: Action Asset Generation Spike

**Date:** 2026-05-29
**Project:** `/Users/wylam/Documents/workspace/Petagent`

## Goal

Generate and evaluate new 豆豆 action sprite candidates with ChatGPT web before
touching production frontend code. This stage exists to prove the asset
pipeline, prompt quality, and acceptance checks for multi-frame actions.

## Scope

This stage writes only under:

```text
plan/V1.4/generated/
plan/V1.4/stages/
```

Do not replace production assets in `frontend/src/assets/` during this stage.
Do not change runtime code during this stage.

## Why Stage 0 First

The current sprite system expects strict atlas rows:

- cell size: `192x208`;
- current atlas: `1536x1872`;
- current rows: 8 columns x 9 rows;
- CSS background-position playback.

Generated images are unlikely to match this exactly on the first try. The right
order is:

1. generate visible action candidates;
2. fetch finished images from ChatGPT page, not early empty downloads;
3. inspect identity and frame continuity;
4. optionally repack into `192x208` test strips;
5. decide whether each action is usable, needs regeneration, or should be
   manually edited.

## Source Reference

Use the existing reference package:

```text
/Users/wylam/Downloads/daimaobatiao.codex-pet
```

Preferred input reference for ChatGPT:

```text
plan/V1.4/generated/reference_idle_frame_white.png
```

Reason: full atlas uploads encouraged ChatGPT to treat the prompt as a complex
edit and initially produced early empty downloads. A single-frame reference
worked better.

## ChatGPT Web Workflow

Use `opencli chatgpt image`, but do not trust the saved file immediately.
ChatGPT web image generation may take 3-5 minutes.

Required workflow for each action:

1. send image prompt with the single-frame reference;
2. wait patiently for the ChatGPT page to show a generated `<img>`;
3. inspect page state and find the generated image element;
4. fetch the generated `img.src` from browser context;
5. save as:

```text
plan/V1.4/generated/actions/<action>/<action>_chatgpt_web_actual.png
```

6. record prompt, ChatGPT conversation URL, dimensions, and verdict.

Do not classify an early transparent 21KB file as final. That is the known
early-download failure mode.

## First Batch

Generate the first six high-value actions:

| Action | Why first |
| --- | --- |
| `happy` | validates positive fast reply |
| `greet` | common wake/greeting path |
| `listen` | voice recording and emotional attention |
| `speak` | voice playback |
| `comfort` | highest UX safety action |
| `nap` | autonomous idle life |

After these pass or fail with clear evidence, expand to:

```text
lazy_idle
sneak_eat
watch_tv
tease
remember
confused
self_groom
wander
pretend_busy
deny
excited
```

## Prompt Template

Each prompt should ask for a six-frame action contact sheet, not final
transparent production art.

Important prompt constraints:

- use attached single-frame cat as strict reference;
- one horizontal row of six frames;
- solid chroma background, preferably `#ff00ff` or `#00ff00`;
- no text, labels, numbers, watermark, props unless the action explicitly
  needs a prop;
- consistent baseline and scale;
- six frames must be consecutive animation frames, not six unrelated cats;
- preserve: chubby white-gray kitten, huge glossy black eyes with yellow
  crescent highlights, pink inner ears, thick black outline, upright gray tail,
  tiny body, short legs.

Use chroma background instead of white because 豆豆 is white and white-key
removal damages the body.

## Per-Action Prompt Notes

### happy

Frame sequence:

1. neutral happy start;
2. slight squash;
3. bounce up;
4. peak happy pose with closed crescent eyes and pink cheeks;
5. soft landing;
6. returns near frame 1.

### greet

Frame sequence:

1. attentive front-facing;
2. one paw starts lifting;
3. paw raised;
4. small wave;
5. paw lowers;
6. back to friendly standing.

### listen

Frame sequence:

1. calm front-facing;
2. ears lift;
3. body leans forward slightly;
4. eyes focused, still and attentive;
5. small blink;
6. returns to attentive pose.

### speak

Frame sequence:

1. mouth closed;
2. small mouth open;
3. mouth wider open;
4. mouth closed with body bob;
5. small mouth open;
6. mouth closed, loop-ready.

### comfort

Frame sequence:

1. soft concerned look;
2. steps closer;
3. gentle paw forward;
4. warm closed-eye comfort pose;
5. eyes open softly;
6. calm supportive stance.

### nap

Frame sequence:

1. sitting sleepy;
2. eyes half closed;
3. curls down;
4. sleeping pose;
5. tiny breathing rise;
6. tiny breathing fall, loop-ready.

## Acceptance Checks

For every generated action:

- image file exists and is non-empty;
- image dimensions are recorded;
- alpha/bbox or RGB content check proves it is not blank;
- exactly six visually distinct frames are present;
- 豆豆 identity is close enough to reference;
- no extra characters, labels, numbers, or watermark;
- no severe cropping of ears/tail/body;
- action semantics are readable from a user's perspective;
- verdict recorded:
  - `accept_for_spike`;
  - `needs_regeneration`;
  - `reject`.

Optional repack check:

- slice into a `1152x208` strip;
- verify all six cells are nonblank;
- record if chroma removal damaged the white body.

## Main-Agent Review Gate

Before generating the batch, the main agent must review this stage plan for:

- whether the scope is safely limited to `plan/V1.4`;
- whether the actions and prompts match the V1.4 spec;
- whether acceptance checks are strong enough;
- whether any Nubia/runtime risk is accidentally introduced.

Claude is not used as a plan reviewer for this stage. Claude may be used only
as an execution worker for narrow tasks if needed. The main agent owns review,
quality judgment, and acceptance.

## Completion Criteria

Stage 0 is complete when:

- main-agent plan review is recorded;
- first-batch action generation is attempted;
- generated artifacts are saved under per-action folders;
- acceptance results are recorded in a completion document;
- no runtime code is changed;
- changes are committed and pushed.
