# Happy Sprite Generation Notes

**Date:** 2026-05-28

## Goal

Generate a first `happy` multi-frame sprite strip to test whether ChatGPT web
image generation can extend the existing 豆豆 / 呆猫八条 sprite style.

Reference package:

```text
/Users/wylam/Downloads/daimaobatiao.codex-pet
```

Reference character:

- chubby white-gray kitten;
- huge glossy black eyes with yellow crescent highlights;
- pink inner ears;
- thick black outline;
- upright gray tail;
- simplified chibi / pixel desktop-pet style.

## Target Prompt Contract

Action: `happy`

Frame plan:

1. standing happy, eyes open, tiny smile, tail raised;
2. slight squash down, cheeks lift, tail begins wagging;
3. small upward bounce, front paws lift slightly;
4. peak happy pose, eyes closed as happy crescents, pink cheeks, tail wagging;
5. soft landing, eyes open, smile remains;
6. return near frame 1 for seamless loop.

Preferred sprite shape:

- 6 frames;
- one horizontal row;
- each frame `192x208`;
- total strip `1152x208`;
- transparent background preferred, or flat removable chroma key.

## ChatGPT Web Attempts

Tool path used:

```text
opencli chatgpt image
```

`opencli` was upgraded from `1.7.22` to `1.8.0` because the first attempt failed
inside the adapter with:

```text
page.evaluate string input does not accept args; use page.evaluate(fn, ...args) instead
```

After upgrade, ChatGPT image commands returned before the page image was fully
ready, so the initially saved PNGs were fully transparent/empty. This was a
timing issue: waiting for the browser page later showed that the image had
finished generating.

The first visible usable result came from the single-frame reference crop:

```text
plan/V1.4/generated/happy_chatgpt_web_actual.png
```

Properties:

- `2172x724`;
- RGB PNG;
- six-frame horizontal contact sheet;
- white background and visible cell dividers;
- generally close to the reference cat identity;
- not engineering-ready because it does not match `192x208` cells and includes
  background/grid/shadow artifacts.

An automatic crop/repack test was also created:

```text
plan/V1.4/generated/happy_chatgpt_web_strip_1152x208.png
```

This file is a rough `1152x208` six-frame strip. It proves the generated image
can be sliced into the existing sprite-row shape, but the current background
removal threshold is too aggressive and removes parts of the white body. Do not
use it as a final asset.

Empty early-download files:

- full atlas reference;
- visible gray/white background prompt;
- single-frame reference crop.

Generated empty files:

```text
plan/V1.4/generated/chatgpt_1779982250918.png
plan/V1.4/generated/chatgpt_1779982321916.png
plan/V1.4/generated/chatgpt_1779982503918.png
plan/V1.4/generated/chatgpt_1779982661913.png
```

Current conclusion: ChatGPT web generation is viable for concept/testing, but
`opencli chatgpt image` should not be trusted to download immediately. The
workflow should wait for the generated `<img>` to appear in the page, then fetch
that `img.src` from the browser context.

## Local Test Strip

To validate the frame contract, a local mechanical strip was created from the
existing idle frames:

```text
plan/V1.4/generated/happy_test_strip_local.png
```

This file is not a final generated asset. It is only a quick visual test for:

- six-frame horizontal strip;
- 192x208 cell rhythm;
- happy bounce sequence;
- rough blush / closed-eye peak frame.

Issues in this local strip:

- not newly drawn;
- frame 4 eye edit is rough;
- no true tail wag variation;
- shape is mechanically transformed from idle frames.

## Next Better Generation Strategy

For real asset generation, prefer one of:

1. generate each frame separately with a single-frame reference and then pack
   locally;
2. use an image API/CLI path with stronger image-output controls;
3. manually draw variants from the existing sprite frame for the first batch.

If continuing with ChatGPT web, try:

- use a single-frame reference crop, not the full atlas;
- one frame at a time or a six-frame row with strict white/green background;
- avoid transparency in generation, then remove background locally;
- wait for page completion and fetch the real `<img src=...>` before saving;
- ask for green/magenta chroma background if transparent extraction is needed,
  because white-body-on-white-background is hard to key cleanly.
