import type { DoudouAction } from "./doudouSprites";
import { isValidDoudouAction } from "./doudouSprites";
import type { Mood, PetUIPhase } from "./types";
import {
  validateBehaviorPlan,
  fallbackBehaviorPlan,
  type DoudouBehaviorStep,
  type DoudouBehaviorSlot,
} from "./doudouBehaviorPlan";

export type DirectorOutput = {
  visibleAction: DoudouAction;
  bubbleText: string | null;
};

type TapKind = "single" | "repeated" | "overpoke";

const TAP_WINDOW_MS = 600;
const OVERPOKE_THRESHOLD = 5;
const OVERPOKE_COOLDOWN_MS = 4000;
const AMBIENT_MIN_MS = 20000;
const AMBIENT_MAX_MS = 45000;
const AMBIENT_COOLDOWN_MS = 15000;

const AMBIENT_ACTIONS: DoudouAction[] = [
  "idle",
  "waiting",
  "review",
  "idle",
  "waiting",
  "idle",
  "review",
  "waving",
];

const AMBIENT_BUBBLES = [
  null,
  null,
  null,
  null,
  "我刚刚没有偷懒。",
  null,
  "豆豆在看家。",
  "我在翻小本本。",
  null,
  "省一点电也很重要。",
];

const TAP_BUBBLES: Record<TapKind, string[]> = {
  single: ["摸到了。", "嗯~", "喵~", "在的在的。"],
  repeated: ["好痒！", "嘿嘿~", "豆豆很开心！", "够了够了~"],
  overpoke: ["哼！", "别戳了啦！", "豆豆生气了！", "呜…"],
};

const TAP_ACTIONS: Record<TapKind, DoudouAction> = {
  single: "waving",
  repeated: "jumping",
  overpoke: "failed",
};

const PROTECTED_PHASES: Set<string> = new Set([
  "listening",
  "waiting_voice",
  "speaking",
]);

const PHASE_SPRITE_MAP: Record<string, DoudouAction> = {
  idle: "idle",
  listening: "waiting",
  thinking: "review",
  waiting_voice: "review",
  speaking: "review",
  audio_error: "failed",
  error: "failed",
};

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

export class BehaviorDirector {
  private tapTimestamps: number[] = [];
  private overpokeUntil = 0;
  private lastUserInteraction = 0;
  private nextAmbientAt = 0;
  private queuedSteps: DoudouBehaviorStep[] = [];
  private currentSlot: DoudouBehaviorSlot | null = null;

  /** Handle a tap on Doudou. Returns immediate local reaction. */
  onTap(now: number, phase: PetUIPhase): DirectorOutput {
    this.tapTimestamps.push(now);
    this.lastUserInteraction = now;

    // Clean old timestamps
    this.tapTimestamps = this.tapTimestamps.filter(
      (t) => now - t < TAP_WINDOW_MS,
    );

    let kind: TapKind;
    if (now < this.overpokeUntil) {
      kind = "overpoke";
    } else if (this.tapTimestamps.length >= OVERPOKE_THRESHOLD) {
      kind = "overpoke";
      this.overpokeUntil = now + OVERPOKE_COOLDOWN_MS;
      this.tapTimestamps = [];
    } else if (this.tapTimestamps.length >= 3) {
      kind = "repeated";
    } else {
      kind = "single";
    }

    // During protected phases, only allow a tiny ack, don't replace the sprite
    if (PROTECTED_PHASES.has(phase)) {
      return {
        visibleAction: PHASE_SPRITE_MAP[phase] ?? "idle",
        bubbleText: kind === "overpoke" ? pick(TAP_BUBBLES.overpoke) : null,
      };
    }

    return {
      visibleAction: TAP_ACTIONS[kind],
      bubbleText: pick(TAP_BUBBLES[kind]),
    };
  }

  /** Process a backend response with optional behavior_plan. */
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

    const plan = validateBehaviorPlan(response.behavior_plan);
    const effectivePlan =
      plan ??
      fallbackBehaviorPlan(response.behavior_intent, response.mood, phase);

    this.queuedSteps = effectivePlan;
    this.currentSlot = null;

    // Return the first step's action for immediate display
    const first = effectivePlan[0];
    if (!first) {
      return { visibleAction: "idle", bubbleText: response.reply ?? null };
    }

    return {
      visibleAction: first.action,
      bubbleText: response.reply ?? null,
    };
  }

  /** Called when a phase transition occurs. */
  onPhaseChange(phase: PetUIPhase): DirectorOutput {
    // For audio playback phases, preserve the behavior plan queue
    // so advanceSlot can consume it at the right boundaries.
    if (phase === "waiting_voice" || phase === "speaking") {
      return {
        visibleAction: PHASE_SPRITE_MAP[phase] ?? "idle",
        bubbleText: null,
      };
    }
    // For other protected/error phases, clear the queue
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

  /** Advance the slot queue when a speech phase boundary is reached. */
  advanceSlot(slot: DoudouBehaviorSlot): DirectorOutput | null {
    // Find the next step matching this slot
    const idx = this.queuedSteps.findIndex((s) => s.slot === slot);
    if (idx === -1) return null;

    const step = this.queuedSteps[idx];
    // Remove only the consumed step
    this.queuedSteps = this.queuedSteps.filter((_, i) => i !== idx);
    this.currentSlot = slot;

    return {
      visibleAction: step.action,
      bubbleText: null,
    };
  }

  /** Ambient tick for idle life. Returns null if not time yet. */
  onAmbientTick(
    now: number,
    phase: PetUIPhase,
    busy: boolean,
    documentVisible: boolean,
  ): DirectorOutput | null {
    if (phase !== "idle") return null;
    if (busy) return null;
    if (!documentVisible) return null;
    if (now - this.lastUserInteraction < AMBIENT_COOLDOWN_MS) return null;
    if (now < this.nextAmbientAt) return null;

    // Schedule next ambient
    this.nextAmbientAt =
      now + AMBIENT_MIN_MS + Math.random() * (AMBIENT_MAX_MS - AMBIENT_MIN_MS);

    const action = pick(AMBIENT_ACTIONS);
    const bubble = pick(AMBIENT_BUBBLES);

    return { visibleAction: action, bubbleText: bubble };
  }

  /** Get the sprite action for a given phase (used for initial/default). */
  static phaseToAction(phase: PetUIPhase): DoudouAction {
    return PHASE_SPRITE_MAP[phase] ?? "idle";
  }

  /** Reset internal state. */
  reset(): void {
    this.tapTimestamps = [];
    this.overpokeUntil = 0;
    this.lastUserInteraction = 0;
    this.nextAmbientAt = 0;
    this.queuedSteps = [];
    this.currentSlot = null;
  }
}
