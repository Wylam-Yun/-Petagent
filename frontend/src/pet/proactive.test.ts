import { describe, expect, test } from "vitest";

import { shouldApplyProactive } from "./proactive";
import type { PetUIPhase } from "./types";

describe("proactive UI guard", () => {
  test.each<PetUIPhase>(["listening", "thinking", "speaking"])(
    "does not apply proactive response while phase is %s",
    (phase) => {
      expect(shouldApplyProactive({ phase, busy: false })).toBe(false);
    }
  );

  test("allows proactive response only when UI is idle and not busy", () => {
    expect(shouldApplyProactive({ phase: "idle", busy: false })).toBe(true);
    expect(shouldApplyProactive({ phase: "idle", busy: true })).toBe(false);
  });
});
