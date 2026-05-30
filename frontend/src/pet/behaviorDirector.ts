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
export type DoudouIdleActivity =
  | "lazy_idle"
  | "nap"
  | "sneak_eat"
  | "watch_tv"
  | "self_groom"
  | "wander";

const TAP_WINDOW_MS = 600;
const OVERPOKE_THRESHOLD = 5;
const OVERPOKE_COOLDOWN_MS = 4000;
const AMBIENT_MIN_MS = 20000;
const AMBIENT_MAX_MS = 45000;
const IDLE_SHORT_ACTIVITY_MS = 60000;
const IDLE_LONG_ACTIVITY_MS = 300000;
export const FAST_ACTION_MIN_VISIBLE_MS = 600;

const SHORT_IDLE_ACTIVITIES: DoudouIdleActivity[] = [
  "lazy_idle",
  "self_groom",
  "wander",
];

const LONG_IDLE_ACTIVITIES: DoudouIdleActivity[] = [
  "nap",
  "sneak_eat",
  "watch_tv",
];

const IDLE_ACTIVITY_BUBBLES: Record<DoudouIdleActivity, (string | null)[]> = {
  lazy_idle: [
    null,
    "我刚刚没有偷懒。",
    "省一点电也很重要。",
  ],
  nap: [
    null,
    "豆豆眯一小会儿。",
  ],
  sneak_eat: [
    "我没有偷吃。",
    null,
  ],
  watch_tv: [
    "我在看家。",
    null,
  ],
  self_groom: [
    null,
    "豆豆把毛毛理顺。",
  ],
  wander: [
    null,
    "豆豆巡逻回来啦。",
  ],
};

const RETURN_REACTIONS: Record<DoudouIdleActivity, DirectorOutput> = {
  lazy_idle: { visibleAction: "lazy_idle", bubbleText: "我刚刚在看家。" },
  nap: { visibleAction: "confused", bubbleText: "唔，刚刚睡着了一小下。" },
  sneak_eat: { visibleAction: "tease", bubbleText: "我没有偷吃，是零食自己过来的。" },
  watch_tv: { visibleAction: "pretend_busy", bubbleText: "等下等下，豆豆刚看到关键地方。" },
  self_groom: { visibleAction: "happy", bubbleText: "豆豆刚把毛毛整理好。" },
  wander: { visibleAction: "greet", bubbleText: "你回来啦，豆豆刚巡逻完。" },
};

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
  listening: "listen",
  thinking: "think",
  waiting_voice: "think",
  speaking: "speak",
  audio_error: "confused",
  error: "confused",
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
  private heldFastAction: DoudouAction | null = null;
  private heldFastActionUntil = 0;
  private lastIdleActivity: DoudouIdleActivity | null = null;
  private lastIdleActivityAt = 0;

  isFastActionHoldActive(now = Date.now()): boolean {
    return !!this.heldFastAction && now < this.heldFastActionUntil;
  }

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

    if (this.lastIdleActivity) {
      const reaction = RETURN_REACTIONS[this.lastIdleActivity];
      this.lastIdleActivity = null;
      this.lastIdleActivityAt = 0;
      this.lastUserInteraction = now;
      return reaction;
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
    now = Date.now(),
  ): DirectorOutput {
    this.lastUserInteraction = now;
    this.lastIdleActivity = null;
    this.lastIdleActivityAt = 0;

    // Fast Reply: single action takes priority
    if (response.action && isValidDoudouAction(response.action)) {
      this.heldFastAction = response.action as DoudouAction;
      this.heldFastActionUntil = now + FAST_ACTION_MIN_VISIBLE_MS;
      return {
        visibleAction: this.heldFastAction,
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
  onPhaseChange(phase: PetUIPhase, now = Date.now()): DirectorOutput {
    // For audio playback phases, preserve the behavior plan queue
    // so advanceSlot can consume it at the right boundaries.
    if (phase === "waiting_voice") {
      if (this.isFastActionHoldActive(now)) {
        return {
          visibleAction: this.heldFastAction ?? "idle",
          bubbleText: null,
        };
      }
      this.heldFastAction = null;
      this.heldFastActionUntil = 0;
      return {
        visibleAction: PHASE_SPRITE_MAP[phase] ?? "idle",
        bubbleText: null,
      };
    }
    if (phase === "speaking") {
      if (this.isFastActionHoldActive(now)) {
        return {
          visibleAction: this.heldFastAction ?? "idle",
          bubbleText: null,
        };
      }
      this.heldFastAction = null;
      this.heldFastActionUntil = 0;
      return {
        visibleAction: PHASE_SPRITE_MAP[phase] ?? "idle",
        bubbleText: null,
      };
    }
    // For other protected/error phases, clear the queue
    if (PROTECTED_PHASES.has(phase) || phase === "audio_error" || phase === "error") {
      this.queuedSteps = [];
      this.currentSlot = null;
      this.heldFastAction = null;
      this.heldFastActionUntil = 0;
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
    if (this.lastUserInteraction === 0) {
      this.lastUserInteraction = now;
      return null;
    }
    const idleFor = this.lastUserInteraction > 0
      ? now - this.lastUserInteraction
      : 0;
    if (idleFor < IDLE_SHORT_ACTIVITY_MS) return null;
    if (now < this.nextAmbientAt) return null;

    // Schedule next ambient
    this.nextAmbientAt =
      now + AMBIENT_MIN_MS + Math.random() * (AMBIENT_MAX_MS - AMBIENT_MIN_MS);

    const activity = pick(
      idleFor >= IDLE_LONG_ACTIVITY_MS
        ? [...SHORT_IDLE_ACTIVITIES, ...LONG_IDLE_ACTIVITIES]
        : SHORT_IDLE_ACTIVITIES,
    );
    this.lastIdleActivity = activity;
    this.lastIdleActivityAt = now;

    return {
      visibleAction: activity,
      bubbleText: pick(IDLE_ACTIVITY_BUBBLES[activity]),
    };
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
    this.heldFastAction = null;
    this.heldFastActionUntil = 0;
    this.lastIdleActivity = null;
    this.lastIdleActivityAt = 0;
  }
}
