import { DOUDOU_ACTIONS } from "./doudouSprites";
import type { DoudouAction } from "./doudouSprites";
import type { Mood, PetUIPhase } from "./types";

export type DoudouBehaviorSlot =
  | "before_speech"
  | "speech"
  | "after_speech"
  | "idle_after";

export type DoudouBehaviorStep = {
  action: DoudouAction;
  slot: DoudouBehaviorSlot;
  duration_ms: number;
  loop?: boolean;
};

export type DoudouBehaviorIntent =
  | "soft_comfort"
  | "clingy_happy"
  | "clingy_wronged_happy"
  | "lazy_busy"
  | "quiet_sleepy"
  | "playful_proud"
  | "confused_wronged"
  | "neutral_companion";

const VALID_SLOTS: readonly DoudouBehaviorSlot[] = [
  "before_speech",
  "speech",
  "after_speech",
  "idle_after",
];

const VALID_INTENTS: readonly DoudouBehaviorIntent[] = [
  "soft_comfort",
  "clingy_happy",
  "clingy_wronged_happy",
  "lazy_busy",
  "quiet_sleepy",
  "playful_proud",
  "confused_wronged",
  "neutral_companion",
];

const DEFAULT_DURATIONS: Record<DoudouAction, number> = {
  idle: 1400,
  waiting: 1400,
  review: 1400,
  waving: 1200,
  jumping: 1200,
  failed: 900,
  running: 1400,
  "running-left": 1400,
  "running-right": 1400,
  lazy_idle: 1400,
  nap: 1600,
  sneak_eat: 1400,
  watch_tv: 1400,
  self_groom: 1400,
  wander: 1400,
  greet: 1200,
  happy: 1200,
  tease: 1200,
  pretend_busy: 1400,
  listen: 1400,
  think: 1400,
  speak: 1400,
  remember: 1400,
  comfort: 1400,
  confused: 900,
  deny: 900,
  excited: 1200,
};

const MAX_STEPS = 4;
const MAX_TOTAL_MS = 8000;
const MIN_DURATION_MS = 600;
const MAX_DURATION_MS = 2500;

const INTENT_FALLBACK: Record<DoudouBehaviorIntent, DoudouAction[]> = {
  soft_comfort: ["comfort", "listen", "idle"],
  clingy_happy: ["happy", "greet", "idle"],
  clingy_wronged_happy: ["deny", "happy", "idle"],
  lazy_busy: ["pretend_busy", "lazy_idle", "idle"],
  quiet_sleepy: ["nap", "idle"],
  playful_proud: ["tease", "happy", "idle"],
  confused_wronged: ["confused", "listen", "idle"],
  neutral_companion: ["greet", "idle"],
};

const MOOD_FALLBACK: Record<string, DoudouAction[]> = {
  happy: ["happy", "idle"],
  shy: ["happy", "idle"],
  excited: ["excited", "idle"],
  thinking: ["think", "idle"],
  sad: ["comfort", "listen", "idle"],
  angry: ["deny", "idle"],
  concerned: ["comfort", "listen", "idle"],
  lonely: ["failed", "waiting", "idle"],
  sleepy: ["nap", "idle"],
  idle: ["idle"],
};

export function isValidDoudouSlot(slot: string): slot is DoudouBehaviorSlot {
  return (VALID_SLOTS as readonly string[]).includes(slot);
}

export function isValidDoudouIntent(
  intent: string,
): intent is DoudouBehaviorIntent {
  return (VALID_INTENTS as readonly string[]).includes(intent);
}

function isValidAction(action: string): action is DoudouAction {
  return (DOUDOU_ACTIONS as readonly string[]).includes(action);
}

function clampDuration(action: DoudouAction, duration?: number): number {
  if (duration == null || !Number.isFinite(duration)) {
    return DEFAULT_DURATIONS[action];
  }
  return Math.min(MAX_DURATION_MS, Math.max(MIN_DURATION_MS, Math.round(duration)));
}

/**
 * Validates and sanitizes a raw behavior plan from model output.
 * Returns a cleaned array of steps, or null if the plan is empty/fully invalid.
 */
export function validateBehaviorPlan(
  raw: unknown,
): DoudouBehaviorStep[] | null {
  if (!Array.isArray(raw)) return null;

  const steps: DoudouBehaviorStep[] = [];
  for (const item of raw) {
    if (steps.length >= MAX_STEPS) break;
    if (!item || typeof item !== "object") continue;

    const rawAction = (item as Record<string, unknown>).action;
    if (typeof rawAction !== "string" || !isValidAction(rawAction)) continue;

    const rawSlot = (item as Record<string, unknown>).slot;
    const slot: DoudouBehaviorSlot =
      typeof rawSlot === "string" && isValidDoudouSlot(rawSlot)
        ? rawSlot
        : "speech";

    const duration_ms = clampDuration(
      rawAction,
      (item as Record<string, unknown>).duration_ms as number | undefined,
    );

    steps.push({ action: rawAction, slot, duration_ms });
  }

  if (steps.length === 0) return null;

  // Enforce total duration cap
  let total = 0;
  const capped: DoudouBehaviorStep[] = [];
  for (const step of steps) {
    if (total + step.duration_ms > MAX_TOTAL_MS) break;
    capped.push(step);
    total += step.duration_ms;
  }

  return capped.length > 0 ? capped : null;
}

/**
 * Derive a fallback plan from behavior_intent, then mood, then phase.
 */
export function fallbackBehaviorPlan(
  behaviorIntent?: string | null,
  mood?: Mood | string | null,
  phase?: PetUIPhase | string | null,
): DoudouBehaviorStep[] {
  // Try intent
  if (behaviorIntent && isValidDoudouIntent(behaviorIntent)) {
    return INTENT_FALLBACK[behaviorIntent].map((action) => ({
      action,
      slot: "speech" as DoudouBehaviorSlot,
      duration_ms: DEFAULT_DURATIONS[action],
    }));
  }

  // Try mood
  if (mood && MOOD_FALLBACK[mood]) {
    return MOOD_FALLBACK[mood].map((action) => ({
      action,
      slot: "speech" as DoudouBehaviorSlot,
      duration_ms: DEFAULT_DURATIONS[action],
    }));
  }

  // Phase-based
  if (phase === "listening") {
    return [{ action: "listen", slot: "speech", duration_ms: 1400 }];
  }
  if (phase === "thinking" || phase === "waiting_voice") {
    return [{ action: "think", slot: "speech", duration_ms: 1400 }];
  }
  if (phase === "speaking") {
    return [{ action: "speak", slot: "speech", duration_ms: 1400 }];
  }
  if (phase === "audio_error" || phase === "error") {
    return [{ action: "confused", slot: "speech", duration_ms: 900 }];
  }

  return [{ action: "idle", slot: "speech", duration_ms: 1400 }];
}

export { DEFAULT_DURATIONS };
