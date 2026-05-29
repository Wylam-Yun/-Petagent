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
  | "running-right"
  | "lazy_idle"
  | "nap"
  | "sneak_eat"
  | "watch_tv"
  | "self_groom"
  | "wander"
  | "greet"
  | "happy"
  | "tease"
  | "pretend_busy"
  | "listen"
  | "think"
  | "speak"
  | "remember"
  | "comfort"
  | "confused"
  | "deny"
  | "excited";

export type DoudouLegacyAction =
  | "idle"
  | "waiting"
  | "review"
  | "waving"
  | "jumping"
  | "failed"
  | "running"
  | "running-left"
  | "running-right";

export type DoudouProductAction = Exclude<DoudouAction, DoudouLegacyAction>;

export const DOUDOU_LEGACY_ACTIONS: readonly DoudouLegacyAction[] = [
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

export const DOUDOU_PRODUCT_ACTIONS: readonly DoudouProductAction[] = [
  "lazy_idle",
  "nap",
  "sneak_eat",
  "watch_tv",
  "self_groom",
  "wander",
  "greet",
  "happy",
  "tease",
  "pretend_busy",
  "listen",
  "think",
  "speak",
  "remember",
  "comfort",
  "confused",
  "deny",
  "excited",
] as const;

export const DOUDOU_ACTIONS: readonly DoudouAction[] = [
  ...DOUDOU_LEGACY_ACTIONS,
  ...DOUDOU_PRODUCT_ACTIONS,
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

const legacyAnimations: Record<DoudouLegacyAction, DoudouAnimationDef> = {
  idle: { row: 0, frames: 6, type: "loop", frameMs: FRAME_MS },
  "running-right": { row: 1, frames: 8, type: "loop", frameMs: FRAME_MS },
  "running-left": { row: 2, frames: 8, type: "loop", frameMs: FRAME_MS },
  waving: { row: 3, frames: 4, type: "one-shot", frameMs: FRAME_MS },
  jumping: { row: 4, frames: 5, type: "one-shot", frameMs: FRAME_MS },
  failed: { row: 5, frames: 8, type: "one-shot", frameMs: FRAME_MS },
  waiting: { row: 6, frames: 6, type: "loop", frameMs: FRAME_MS },
  running: { row: 7, frames: 6, type: "loop", frameMs: FRAME_MS },
  review: { row: 8, frames: 6, type: "loop", frameMs: FRAME_MS },
};

export const DOUDOU_ACTION_FALLBACKS: Record<
  DoudouProductAction,
  DoudouLegacyAction
> = {
  lazy_idle: "waiting",
  nap: "waiting",
  sneak_eat: "review",
  watch_tv: "review",
  self_groom: "idle",
  wander: "running",
  greet: "waving",
  happy: "waving",
  tease: "jumping",
  pretend_busy: "review",
  listen: "waiting",
  think: "review",
  speak: "review",
  remember: "review",
  comfort: "waving",
  confused: "failed",
  deny: "failed",
  excited: "jumping",
};

const productAnimations = Object.fromEntries(
  DOUDOU_PRODUCT_ACTIONS.map((action) => [
    action,
    legacyAnimations[DOUDOU_ACTION_FALLBACKS[action]],
  ]),
) as Record<DoudouProductAction, DoudouAnimationDef>;

export const doudouManifest: DoudouSpriteManifest = {
  imageUrl: spritesheetUrl,
  atlasWidth: 1536,
  atlasHeight: 1872,
  cellWidth: 192,
  cellHeight: 208,
  columns: 8,
  rows: 9,
  animations: {
    ...legacyAnimations,
    ...productAnimations,
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
