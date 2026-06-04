import type { ExpressionKey, Mood } from "./types";

export const faceMap: Record<Mood, string[]> = {
  idle: ["(o.o)", "(^_-)", "(^-^)"],
  happy: ["(^_^)", "(^o^)", "(^-^)v"],
  sad: ["(T_T)", "(;_;)", "(u_u)"],
  sleepy: ["(-_-) zzz", "(-.-) zzz", "(-_-)"],
  tired: ["(-_-)", "(u_u)", "(-.-)"],
  angry: ["(>_<)", "(-_-#)", "(>_>)"],
  shy: ["(//_//)", "(._.)", "(^.^)"],
  thinking: ["(?.?)", "(o_o?)", "(._.?)"],
  concerned: ["(._.)", "(o_o)", "(._.?)"],
  excited: ["(^o^)/", "(^o^)", "(^-^)v"],
  lonely: ["(._.)", "(u_u)", "(;_;)"]
};

export const expressionMap: Record<ExpressionKey, string> = {
  idle_soft: "(o.o)",
  idle_wink: "(^_-)",
  happy: "(^_^)",
  happy_big: "(^o^)",
  excited: "(^o^)/",
  shy: "(//_//)",
  clingy: "(^.^)",
  thinking: "(?.?)",
  confused: "(._.?)",
  concerned: "(._.)",
  sad: "(T_T)",
  crying: "(;_;)",
  sleepy: "(-_-) zzz",
  tired: "(-_-)",
  annoyed: "(>_<)",
  wronged: "(u_u)",
  proud: "(^-^)v",
  playful: "(^_~)",
  lonely: "(._.)",
  calm: "(-.-)"
};

const moodExpressionFallback: Record<string, ExpressionKey> = {
  idle: "idle_soft",
  happy: "happy",
  sad: "sad",
  sleepy: "sleepy",
  tired: "tired",
  angry: "annoyed",
  shy: "shy",
  thinking: "thinking",
  concerned: "concerned",
  excited: "excited",
  lonely: "lonely"
};

export function expressionForKey(key?: string | null, mood?: Mood | string | null): string {
  if (key && key in expressionMap) return expressionMap[key as ExpressionKey];
  const fallback = moodExpressionFallback[String(mood || "idle")] ?? "idle_soft";
  return expressionMap[fallback];
}

export function faceForType(faceType: string, index = 0): string {
  const faces = faceMap[faceType as Mood] ?? faceMap.idle;
  return faces[index % faces.length];
}
