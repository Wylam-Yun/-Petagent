import spritesheetUrl from "../assets/spritesheet.webp";

export type DoudouAction =
  | "idle"
  | "waiting"
  | "review"
  | "waving"
  | "jumping"
  | "failed"
  | "running"
  | "running-left"
  | "running-right";

export const DOUDOU_ACTIONS: readonly DoudouAction[] = [
  "idle",
  "waiting",
  "review",
  "waving",
  "jumping",
  "failed",
  "running",
  "running-left",
  "running-right",
] as const;

export type DoudouAnimationType = "loop" | "one-shot";

export type DoudouAnimationDef = {
  row: number;
  frames: number;
  type: DoudouAnimationType;
  frameMs: number;
};

export type DoudouSpriteManifest = {
  imageUrl: string;
  atlasWidth: number;
  atlasHeight: number;
  cellWidth: number;
  cellHeight: number;
  columns: number;
  rows: number;
  animations: Record<DoudouAction, DoudouAnimationDef>;
};

const FRAME_MS = 180;

export const doudouManifest: DoudouSpriteManifest = {
  imageUrl: spritesheetUrl,
  atlasWidth: 1536,
  atlasHeight: 1872,
  cellWidth: 192,
  cellHeight: 208,
  columns: 8,
  rows: 9,
  animations: {
    idle: { row: 0, frames: 6, type: "loop", frameMs: FRAME_MS },
    "running-right": { row: 1, frames: 8, type: "loop", frameMs: FRAME_MS },
    "running-left": { row: 2, frames: 8, type: "loop", frameMs: FRAME_MS },
    waving: { row: 3, frames: 4, type: "one-shot", frameMs: FRAME_MS },
    jumping: { row: 4, frames: 5, type: "one-shot", frameMs: FRAME_MS },
    failed: { row: 5, frames: 8, type: "one-shot", frameMs: FRAME_MS },
    waiting: { row: 6, frames: 6, type: "loop", frameMs: FRAME_MS },
    running: { row: 7, frames: 6, type: "loop", frameMs: FRAME_MS },
    review: { row: 8, frames: 6, type: "loop", frameMs: FRAME_MS },
  },
};

export function isValidDoudouAction(action: string): action is DoudouAction {
  return (DOUDOU_ACTIONS as readonly string[]).includes(action);
}

export function getFramePosition(
  manifest: DoudouSpriteManifest,
  action: DoudouAction,
  frameIndex: number,
): { x: number; y: number } {
  const def = manifest.animations[action];
  const col = frameIndex % manifest.columns;
  const x = col * manifest.cellWidth;
  const y = def.row * manifest.cellHeight;
  return { x: x === 0 ? 0 : -x, y: y === 0 ? 0 : -y };
}
