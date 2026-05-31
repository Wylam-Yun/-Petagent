import { expect, test } from "vitest";

import {
  ambientDelayMs,
  buildAmbientClientState,
  getLocalDateString,
  loadAmbientState,
  resetAmbientState,
  saveAmbientState,
  shouldRequestAmbient,
} from "./ambient";

test("ambient delay follows V1.6 backoff", () => {
  expect(ambientDelayMs(0)).toBe(5 * 60_000);
  expect(ambientDelayMs(1)).toBe(10 * 60_000);
  expect(ambientDelayMs(2)).toBe(20 * 60_000);
  expect(ambientDelayMs(3)).toBe(40 * 60_000);
  expect(ambientDelayMs(4)).toBe(90 * 60_000);
  expect(ambientDelayMs(9)).toBe(90 * 60_000);
});

test("shouldRequestAmbient blocks non-idle states", () => {
  expect(shouldRequestAmbient({
    now: 1000,
    idleAnchorAt: 0,
    idleStep: 0,
    visible: true,
    foreground: true,
    screenOn: true,
    phase: "idle",
    busy: false,
    inputActive: false,
    recording: false,
    waitingLlm: false,
    waitingTts: false,
    playingTts: false,
  })).toBe(false);

  expect(shouldRequestAmbient({
    now: 5 * 60_000,
    idleAnchorAt: 0,
    idleStep: 0,
    visible: true,
    foreground: true,
    screenOn: true,
    phase: "idle",
    busy: false,
    inputActive: false,
    recording: false,
    waitingLlm: false,
    waitingTts: false,
    playingTts: false,
  })).toBe(true);
});

test("client state maps UI blockers", () => {
  const state = buildAmbientClientState({
    visible: false,
    foreground: true,
    screenOn: true,
    phase: "speaking",
    busy: true,
    inputActive: true,
    recording: false,
    waitingLlm: false,
    waitingTts: false,
    playingTts: true,
  });
  expect(state.visible).toBe(false);
  expect(state.busy).toBe(true);
  expect(state.playing_tts).toBe(true);
});

test("getLocalDateString uses device local date instead of UTC", () => {
  const date = new Date(2026, 4, 31, 0, 30, 0);
  expect(getLocalDateString(date)).toBe("2026-05-31");
});

test("ambient state persists idle step and local date", () => {
  const storage = new Map<string, string>();
  const fakeStorage = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
    length: 0,
    clear: () => storage.clear(),
    key: () => null,
  } as Storage;
  saveAmbientState(fakeStorage, { idleAnchorAt: 1000, idleStep: 2, localDate: "2026-05-31" });
  expect(loadAmbientState(fakeStorage, "2026-05-31")).toEqual({
    idleAnchorAt: 1000,
    idleStep: 2,
    localDate: "2026-05-31",
  });
  expect(loadAmbientState(fakeStorage, "2026-06-01")?.idleStep).toBe(0);
});

test("resetAmbientState clears persisted idle state", () => {
  const storage = new Map<string, string>();
  const fakeStorage = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
    length: 0,
    clear: () => storage.clear(),
    key: () => null,
  } as Storage;
  saveAmbientState(fakeStorage, { idleAnchorAt: 1000, idleStep: 2, localDate: "2026-05-31" });
  resetAmbientState(fakeStorage);
  expect(loadAmbientState(fakeStorage, "2026-05-31")).toBeNull();
});
