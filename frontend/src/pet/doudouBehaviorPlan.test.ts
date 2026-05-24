import { describe, it, expect } from "vitest";
import {
  validateBehaviorPlan,
  fallbackBehaviorPlan,
  isValidDoudouSlot,
  isValidDoudouIntent,
} from "./doudouBehaviorPlan";

describe("validateBehaviorPlan", () => {
  it("accepts a valid plan", () => {
    const plan = validateBehaviorPlan([
      { action: "waving", slot: "before_speech", duration_ms: 1200 },
      { action: "jumping", slot: "speech", duration_ms: 1000 },
    ]);
    expect(plan).toHaveLength(2);
    expect(plan![0]).toEqual({
      action: "waving",
      slot: "before_speech",
      duration_ms: 1200,
    });
  });

  it("drops unknown actions", () => {
    const plan = validateBehaviorPlan([
      { action: "sleep", slot: "speech", duration_ms: 1000 },
      { action: "waving", slot: "speech", duration_ms: 1200 },
    ]);
    expect(plan).toHaveLength(1);
    expect(plan![0].action).toBe("waving");
  });

  it("repairs unknown slots to speech", () => {
    const plan = validateBehaviorPlan([
      { action: "idle", slot: "invalid_slot", duration_ms: 1000 },
    ]);
    expect(plan).toHaveLength(1);
    expect(plan![0].slot).toBe("speech");
  });

  it("clamps duration to 600-2500ms", () => {
    const plan = validateBehaviorPlan([
      { action: "idle", slot: "speech", duration_ms: 100 },
      { action: "waving", slot: "speech", duration_ms: 9999 },
    ]);
    expect(plan![0].duration_ms).toBe(600);
    expect(plan![1].duration_ms).toBe(2500);
  });

  it("uses default duration when missing", () => {
    const plan = validateBehaviorPlan([
      { action: "failed", slot: "speech" },
      { action: "waving", slot: "speech" },
    ]);
    expect(plan![0].duration_ms).toBe(900);
    expect(plan![1].duration_ms).toBe(1200);
  });

  it("limits to 4 steps", () => {
    const plan = validateBehaviorPlan([
      { action: "idle", slot: "speech", duration_ms: 1000 },
      { action: "waving", slot: "speech", duration_ms: 1000 },
      { action: "jumping", slot: "speech", duration_ms: 1000 },
      { action: "failed", slot: "speech", duration_ms: 1000 },
      { action: "review", slot: "speech", duration_ms: 1000 },
    ]);
    expect(plan).toHaveLength(4);
  });

  it("caps total duration at 8000ms", () => {
    const plan = validateBehaviorPlan([
      { action: "idle", slot: "speech", duration_ms: 2500 },
      { action: "waving", slot: "speech", duration_ms: 2500 },
      { action: "jumping", slot: "speech", duration_ms: 2500 },
      { action: "failed", slot: "speech", duration_ms: 2500 },
    ]);
    const total = plan!.reduce((s, p) => s + p.duration_ms, 0);
    expect(total).toBeLessThanOrEqual(8000);
  });

  it("returns null for non-array input", () => {
    expect(validateBehaviorPlan(null)).toBeNull();
    expect(validateBehaviorPlan("string")).toBeNull();
    expect(validateBehaviorPlan(42)).toBeNull();
    expect(validateBehaviorPlan({})).toBeNull();
  });

  it("returns null for fully invalid plan", () => {
    expect(validateBehaviorPlan([{ action: "unknown" }])).toBeNull();
    expect(validateBehaviorPlan([null, 42, "x"])).toBeNull();
  });

  it("handles empty array", () => {
    expect(validateBehaviorPlan([])).toBeNull();
  });
});

describe("fallbackBehaviorPlan", () => {
  it("uses intent fallback when available", () => {
    const plan = fallbackBehaviorPlan("clingy_happy", "idle", "idle");
    const actions = plan.map((s) => s.action);
    expect(actions).toEqual(["waving", "jumping", "idle"]);
  });

  it("falls back to mood when intent is missing", () => {
    const plan = fallbackBehaviorPlan(null, "excited", "idle");
    const actions = plan.map((s) => s.action);
    expect(actions).toEqual(["jumping", "idle"]);
  });

  it("falls back to phase when mood is unknown", () => {
    const plan = fallbackBehaviorPlan(null, null, "listening");
    expect(plan).toHaveLength(1);
    expect(plan[0].action).toBe("waiting");
  });

  it("falls back to idle for unknown everything", () => {
    const plan = fallbackBehaviorPlan(null, null, null);
    expect(plan).toHaveLength(1);
    expect(plan[0].action).toBe("idle");
  });

  it("maps thinking phase to review", () => {
    const plan = fallbackBehaviorPlan(null, null, "thinking");
    expect(plan[0].action).toBe("review");
  });

  it("maps error phase to failed", () => {
    const plan = fallbackBehaviorPlan(null, null, "audio_error");
    expect(plan[0].action).toBe("failed");
  });
});

describe("isValidDoudouSlot", () => {
  it("accepts valid slots", () => {
    expect(isValidDoudouSlot("before_speech")).toBe(true);
    expect(isValidDoudouSlot("speech")).toBe(true);
    expect(isValidDoudouSlot("after_speech")).toBe(true);
    expect(isValidDoudouSlot("idle_after")).toBe(true);
  });

  it("rejects invalid slots", () => {
    expect(isValidDoudouSlot("invalid")).toBe(false);
    expect(isValidDoudouSlot("")).toBe(false);
  });
});

describe("isValidDoudouIntent", () => {
  it("accepts valid intents", () => {
    expect(isValidDoudouIntent("clingy_happy")).toBe(true);
    expect(isValidDoudouIntent("neutral_companion")).toBe(true);
  });

  it("rejects invalid intents", () => {
    expect(isValidDoudouIntent("unknown_intent")).toBe(false);
  });
});
