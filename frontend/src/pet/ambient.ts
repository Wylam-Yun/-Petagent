import type { PetUIPhase } from "./types";

const DELAYS = [5, 10, 20, 40, 90].map((minutes) => minutes * 60_000);
const AMBIENT_STORAGE_KEY = "petagent:v16:ambient-state";

export type AmbientPersistedState = {
  idleAnchorAt: number;
  idleStep: number;
  localDate: string;
};

export function ambientDelayMs(step: number): number {
  return DELAYS[Math.min(Math.max(0, step), DELAYS.length - 1)];
}

export function getLocalDateString(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function loadAmbientState(
  storage: Storage,
  localDate = getLocalDateString(),
): AmbientPersistedState | null {
  try {
    const raw = storage.getItem(AMBIENT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AmbientPersistedState>;
    if (parsed.localDate !== localDate) {
      return { idleAnchorAt: Date.now(), idleStep: 0, localDate };
    }
    if (!Number.isFinite(parsed.idleAnchorAt) || !Number.isFinite(parsed.idleStep)) {
      return null;
    }
    return {
      idleAnchorAt: Number(parsed.idleAnchorAt),
      idleStep: Math.max(0, Number(parsed.idleStep)),
      localDate,
    };
  } catch {
    return null;
  }
}

export function saveAmbientState(storage: Storage, state: AmbientPersistedState): void {
  try {
    storage.setItem(AMBIENT_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ambient bubbles are optional; private-mode storage failures should stay silent.
  }
}

export type AmbientEligibilityInput = {
  now: number;
  idleAnchorAt: number;
  idleStep: number;
  visible: boolean;
  foreground: boolean;
  screenOn: boolean;
  phase: PetUIPhase;
  busy: boolean;
  inputActive: boolean;
  recording: boolean;
  waitingLlm: boolean;
  waitingTts: boolean;
  playingTts: boolean;
};

export function shouldRequestAmbient(input: AmbientEligibilityInput): boolean {
  if (!input.visible || !input.foreground || !input.screenOn) return false;
  if (input.phase !== "idle" || input.busy) return false;
  if (input.inputActive || input.recording || input.waitingLlm || input.waitingTts || input.playingTts) {
    return false;
  }
  return input.now - input.idleAnchorAt >= ambientDelayMs(input.idleStep);
}

export function buildAmbientClientState(
  input: Omit<AmbientEligibilityInput, "now" | "idleAnchorAt" | "idleStep">,
) {
  return {
    visible: input.visible,
    foreground: input.foreground,
    screen_on: input.screenOn,
    idle: input.phase === "idle",
    busy: input.busy,
    input_active: input.inputActive,
    recording: input.recording,
    waiting_llm: input.waitingLlm,
    waiting_tts: input.waitingTts,
    playing_tts: input.playingTts,
  };
}
