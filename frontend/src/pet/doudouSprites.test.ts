import { describe, it, expect } from "vitest";
import {
  doudouManifest,
  DOUDOU_ACTIONS,
  getFramePosition,
  isValidDoudouAction,
} from "./doudouSprites";

describe("doudouManifest", () => {
  it("has correct atlas dimensions", () => {
    expect(doudouManifest.atlasWidth).toBe(1536);
    expect(doudouManifest.atlasHeight).toBe(1872);
  });

  it("has correct cell dimensions", () => {
    expect(doudouManifest.cellWidth).toBe(192);
    expect(doudouManifest.cellHeight).toBe(208);
  });

  it("has correct grid dimensions", () => {
    expect(doudouManifest.columns).toBe(8);
    expect(doudouManifest.rows).toBe(9);
  });

  it("defines all 9 animations", () => {
    expect(Object.keys(doudouManifest.animations)).toHaveLength(9);
  });

  it("has correct frame counts per animation", () => {
    const expected = {
      idle: 6,
      "running-right": 8,
      "running-left": 8,
      waving: 4,
      jumping: 5,
      failed: 8,
      waiting: 6,
      running: 6,
      review: 6,
    };
    for (const [action, frames] of Object.entries(expected)) {
      expect(
        doudouManifest.animations[action as keyof typeof doudouManifest.animations].frames,
      ).toBe(frames);
    }
  });

  it("marks loop vs one-shot correctly", () => {
    const loops = ["idle", "running-right", "running-left", "waiting", "running", "review"];
    const oneShots = ["waving", "jumping", "failed"];
    for (const a of loops) {
      expect(
        doudouManifest.animations[a as keyof typeof doudouManifest.animations].type,
      ).toBe("loop");
    }
    for (const a of oneShots) {
      expect(
        doudouManifest.animations[a as keyof typeof doudouManifest.animations].type,
      ).toBe("one-shot");
    }
  });
});

describe("isValidDoudouAction", () => {
  it("accepts all whitelisted actions", () => {
    for (const action of DOUDOU_ACTIONS) {
      expect(isValidDoudouAction(action)).toBe(true);
    }
  });

  it("rejects unknown actions", () => {
    expect(isValidDoudouAction("sleep")).toBe(false);
    expect(isValidDoudouAction("cry")).toBe(false);
    expect(isValidDoudouAction("")).toBe(false);
    expect(isValidDoudouAction("IDLE")).toBe(false);
  });
});

describe("getFramePosition", () => {
  it("returns correct position for first frame of idle (row 0, col 0)", () => {
    const pos = getFramePosition(doudouManifest, "idle", 0);
    expect(pos).toEqual({ x: 0, y: 0 });
  });

  it("returns correct position for second frame of idle (row 0, col 1)", () => {
    const pos = getFramePosition(doudouManifest, "idle", 1);
    expect(pos).toEqual({ x: -192, y: 0 });
  });

  it("returns correct position for first frame of waving (row 3, col 0)", () => {
    const pos = getFramePosition(doudouManifest, "waving", 0);
    expect(pos).toEqual({ x: 0, y: -624 });
  });

  it("returns correct position for frame 3 of failed (row 5, col 3)", () => {
    const pos = getFramePosition(doudouManifest, "failed", 3);
    expect(pos).toEqual({ x: -576, y: -1040 });
  });
});
