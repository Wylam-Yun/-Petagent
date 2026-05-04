import type { PetUIPhase } from "./types";

export function shouldApplyProactive({
  phase,
  busy
}: {
  phase: PetUIPhase;
  busy: boolean;
}): boolean {
  return phase === "idle" && !busy;
}
