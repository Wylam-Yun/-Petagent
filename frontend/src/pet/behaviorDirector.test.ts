import { describe, it, expect, beforeEach } from "vitest";
import {
  BehaviorDirector,
  FAST_ACTION_MIN_VISIBLE_MS,
} from "./behaviorDirector";

describe("BehaviorDirector", () => {
  let dir: BehaviorDirector;

  beforeEach(() => {
    dir = new BehaviorDirector();
  });

  describe("onTap", () => {
    it("returns waving for single tap", () => {
      const out = dir.onTap(1000, "idle");
      expect(out.visibleAction).toBe("waving");
    });

    it("returns jumping for repeated taps (3+)", () => {
      dir.onTap(1000, "idle");
      dir.onTap(1100, "idle");
      const out = dir.onTap(1200, "idle");
      expect(out.visibleAction).toBe("jumping");
    });

    it("returns failed for over-poke (5+ taps)", () => {
      for (let i = 0; i < 5; i++) {
        dir.onTap(1000 + i * 50, "idle");
      }
      const out = dir.onTap(1300, "idle");
      expect(out.visibleAction).toBe("failed");
    });

    it("stays failed during cooldown after over-poke", () => {
      for (let i = 0; i < 5; i++) {
        dir.onTap(1000 + i * 50, "idle");
      }
      dir.onTap(1300, "idle"); // triggers overpoke
      const out = dir.onTap(2000, "idle"); // within cooldown
      expect(out.visibleAction).toBe("failed");
    });

    it("does not interrupt protected listening phase", () => {
      const out = dir.onTap(1000, "listening");
      expect(out.visibleAction).toBe("listen"); // phase-mapped, not waving
    });

    it("does not interrupt speaking phase", () => {
      const out = dir.onTap(1000, "speaking");
      expect(out.visibleAction).toBe("speak");
    });

    it("allows overpoke bubble during protected phase", () => {
      for (let i = 0; i < 5; i++) {
        dir.onTap(1000 + i * 50, "listening");
      }
      const out = dir.onTap(1300, "listening");
      expect(out.bubbleText).toBeTruthy(); // overpoke complaint
    });

    it("returns a bubble text for single tap", () => {
      const out = dir.onTap(1000, "idle");
      expect(out.bubbleText).toBeTruthy();
    });

    it("resets tap window after TAP_WINDOW_MS", () => {
      dir.onTap(1000, "idle");
      dir.onTap(1100, "idle");
      // After 600ms window, taps reset
      const out = dir.onTap(2000, "idle");
      expect(out.visibleAction).toBe("waving"); // single tap again
    });
  });

  describe("onBackendResponse", () => {
    it("uses valid behavior_plan from model", () => {
      const out = dir.onBackendResponse(
        {
          behavior_plan: [
            { action: "failed", slot: "before_speech", duration_ms: 900 },
            { action: "waving", slot: "speech", duration_ms: 1200 },
          ],
          mood: "happy",
        },
        "idle",
      );
      expect(out.visibleAction).toBe("failed"); // first step
    });

    it("falls back to behavior_intent when plan is missing", () => {
      const out = dir.onBackendResponse(
        { behavior_intent: "clingy_happy", mood: "idle" },
        "idle",
      );
      expect(out.visibleAction).toBe("happy"); // first of clingy_happy fallback
    });

    it("falls back to mood when intent is missing", () => {
      const out = dir.onBackendResponse({ mood: "excited" }, "idle");
      expect(out.visibleAction).toBe("excited");
    });

    it("includes reply as bubble text", () => {
      const out = dir.onBackendResponse(
        { reply: "豆豆说你好", mood: "idle" },
        "idle",
      );
      expect(out.bubbleText).toBe("豆豆说你好");
    });

    it("prefers behavior_plan over single action when both are present", () => {
      const out = dir.onBackendResponse(
        {
          action: "speak",
          behavior_plan: [
            { action: "confused", slot: "before_speech", duration_ms: 900 },
            { action: "speak", slot: "speech", duration_ms: 1400 },
          ],
          mood: "thinking",
        },
        "idle",
      );

      expect(out.visibleAction).toBe("confused");
      expect(dir.advanceSlot("speech")?.visibleAction).toBe("speak");
    });
  });

  describe("onPhaseChange", () => {
    it("maps listening to waiting", () => {
      const out = dir.onPhaseChange("listening");
      expect(out.visibleAction).toBe("listen");
    });

    it("maps thinking to review", () => {
      const out = dir.onPhaseChange("thinking");
      expect(out.visibleAction).toBe("think");
    });

    it("maps error to failed", () => {
      const out = dir.onPhaseChange("error");
      expect(out.visibleAction).toBe("confused");
    });

    it("preserves fast action during immediate waiting_voice", () => {
      dir.onBackendResponse({ action: "happy", reply: "早呀" }, "idle", 1000);
      const out = dir.onPhaseChange("waiting_voice", 1001);
      expect(out.visibleAction).toBe("happy");
      expect(dir.isFastActionHoldActive(1000 + FAST_ACTION_MIN_VISIBLE_MS - 1)).toBe(true);
    });

    it("uses think after fast action hold expires", () => {
      dir.onBackendResponse({ action: "happy", reply: "早呀" }, "idle", 1000);
      expect(dir.isFastActionHoldActive(1000 + FAST_ACTION_MIN_VISIBLE_MS + 1)).toBe(false);
      const out = dir.onPhaseChange("waiting_voice", 1000 + FAST_ACTION_MIN_VISIBLE_MS + 1);
      expect(out.visibleAction).toBe("think");
    });

    it("clears queued steps on phase change", () => {
      dir.onBackendResponse(
        {
          behavior_plan: [
            { action: "waving", slot: "speech", duration_ms: 1200 },
          ],
        },
        "idle",
      );
      dir.onPhaseChange("listening");
      // After phase change, advanceSlot should find nothing
      const result = dir.advanceSlot("speech");
      expect(result).toBeNull();
    });
  });

  describe("advanceSlot", () => {
    it("returns the step matching the requested slot", () => {
      dir.onBackendResponse(
        {
          behavior_plan: [
            { action: "failed", slot: "before_speech", duration_ms: 900 },
            { action: "waving", slot: "speech", duration_ms: 1200 },
            { action: "jumping", slot: "after_speech", duration_ms: 1000 },
          ],
        },
        "idle",
      );

      const before = dir.advanceSlot("before_speech");
      expect(before?.visibleAction).toBe("failed");

      const speech = dir.advanceSlot("speech");
      expect(speech?.visibleAction).toBe("waving");

      const after = dir.advanceSlot("after_speech");
      expect(after?.visibleAction).toBe("jumping");
    });

    it("returns null when no matching slot", () => {
      dir.onBackendResponse(
        {
          behavior_plan: [
            { action: "waving", slot: "speech", duration_ms: 1200 },
          ],
        },
        "idle",
      );

      expect(dir.advanceSlot("before_speech")).toBeNull();
    });

    it("consumes the step (not reusable)", () => {
      dir.onBackendResponse(
        {
          behavior_plan: [
            { action: "waving", slot: "speech", duration_ms: 1200 },
          ],
        },
        "idle",
      );

      dir.advanceSlot("speech");
      expect(dir.advanceSlot("speech")).toBeNull();
    });
  });

  describe("phaseToAction", () => {
    it("maps phases to actions", () => {
      expect(BehaviorDirector.phaseToAction("idle")).toBe("idle");
      expect(BehaviorDirector.phaseToAction("listening")).toBe("listen");
      expect(BehaviorDirector.phaseToAction("thinking")).toBe("think");
      expect(BehaviorDirector.phaseToAction("waiting_voice")).toBe("think");
      expect(BehaviorDirector.phaseToAction("speaking")).toBe("speak");
      expect(BehaviorDirector.phaseToAction("error")).toBe("confused");
    });
  });

  describe("reset", () => {
    it("clears all state", () => {
      dir.onTap(1000, "idle");
      dir.onBackendResponse(
        {
          behavior_plan: [
            { action: "waving", slot: "speech", duration_ms: 1200 },
          ],
        },
        "idle",
      );
      dir.reset();
      // After reset, should behave as fresh
      const out = dir.onTap(50000, "idle");
      expect(out.visibleAction).toBe("waving"); // single tap, not overpoke
    });
  });
});
