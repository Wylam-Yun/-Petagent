import type { AnimationName, Mood } from "./types";

export const animationMap: Record<Mood, AnimationName> = {
  idle: "breathing",
  happy: "bounce",
  sad: "droop",
  sleepy: "slowBlink",
  tired: "slowBlink",
  angry: "shake",
  shy: "wiggle",
  thinking: "blink",
  concerned: "tilt",
  excited: "jump",
  lonely: "small"
};
