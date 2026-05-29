import { describe, it, expect, beforeEach } from "vitest";
import { BehaviorDirector } from "./behaviorDirector";

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
      expect(out.visibleAction).toBe("waiting"); // phase-mapped, not waving
    });

    it("does not interrupt speaking phase", () => {
      const out = dir.onTap(1000, "speaking");
      expect(out.visibleAction).toBe("review");
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
  });

  describe("onPhaseChange", () => {
    it("maps listening to waiting", () => {
      const out = dir.onPhaseChange("listening");
      expect(out.visibleAction).toBe("waiting");
    });

    it("maps thinking to review", () => {
      const out = dir.onPhaseChange("thinking");
      expect(out.visibleAction).toBe("review");
    });

    it("maps error to failed", () => {
      const out = dir.onPhaseChange("error");
      expect(out.visibleAction).toBe("failed");
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

  describe("onAmbientTick", () => {
    it("returns null during non-idle phase", () => {
      expect(dir.onAmbientTick(50000, "listening", false, true)).toBeNull();
    });

    it("returns null when busy", () => {
      expect(dir.onAmbientTick(50000, "idle", true, true)).toBeNull();
    });

    it("returns null when document not visible", () => {
      expect(dir.onAmbientTick(50000, "idle", false, false)).toBeNull();
    });

    it("returns null during cooldown after user interaction", () => {
      dir.onTap(1000, "idle");
      expect(dir.onAmbientTick(5000, "idle", false, true)).toBeNull();
    });

    it("fires after cooldown and scheduled time", () => {
      // No user interaction, so cooldown is 0
      const out = dir.onAmbientTick(50000, "idle", false, true);
      expect(out).not.toBeNull();
      expect(out!.visibleAction).toBeTruthy();
    });

    it("returns null before scheduled ambient time", () => {
      // First tick sets the schedule
      dir.onAmbientTick(50000, "idle", false, true);
      // Second tick immediately after should not fire
      expect(dir.onAmbientTick(50001, "idle", false, true)).toBeNull();
    });
  });

  describe("phaseToAction", () => {
    it("maps phases to actions", () => {
      expect(BehaviorDirector.phaseToAction("idle")).toBe("idle");
      expect(BehaviorDirector.phaseToAction("listening")).toBe("waiting");
      expect(BehaviorDirector.phaseToAction("thinking")).toBe("review");
      expect(BehaviorDirector.phaseToAction("speaking")).toBe("review");
      expect(BehaviorDirector.phaseToAction("error")).toBe("failed");
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
