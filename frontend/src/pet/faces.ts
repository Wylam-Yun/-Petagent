import type { ExpressionKey, Mood } from "./types";

export const faceMap: Record<Mood, string[]> = {
  idle: ["(・ω・)", "(｡•̀ᴗ-)✧", "(๑•̀ㅂ•́)و✧"],
  happy: ["(^▽^)", "(≧▽≦)", "٩(ˊᗜˋ*)و"],
  sad: ["(´･_･`)", "(｡•́︿•̀｡)", "(╥﹏╥)"],
  sleepy: ["(-_-) zzz", "(￣o￣) . z Z", "(－_－) zzZ"],
  tired: ["(-_-)", "(￣o￣)", "(－_－)"],
  angry: ["(｀へ´)", "(╬ Ò﹏Ó)", "(ノಠ益ಠ)ノ"],
  shy: ["(//▽//)", "(*ﾉωﾉ)", "(⁄ ⁄•⁄ω⁄•⁄ ⁄)"],
  thinking: ["(・・?)", "(。ヘ°)", "(｡•̀ᴗ-)✧"],
  concerned: ["(´･_･`)", "(´・ω・`)", "(｡•́︿•̀｡)"],
  excited: ["٩(ˊᗜˋ*)و", "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧", "ヽ(>∀<☆)ノ"],
  lonely: ["(._.)", "(｡•́︿•̀｡)", "(´；ω；`)"]
};

export const expressionMap: Record<ExpressionKey, string> = {
  idle_soft: "(・ω・)",
  idle_wink: "(｡•̀ᴗ-)✧",
  happy: "(^▽^)",
  happy_big: "(≧▽≦)",
  excited: "٩(ˊᗜˋ*)و",
  shy: "(//▽//)",
  clingy: "(*ﾉωﾉ)",
  thinking: "(・・?)",
  confused: "(。ヘ°)",
  concerned: "(´・ω・)",
  sad: "(｡•́︿•̀｡)",
  crying: "(╥﹏╥)",
  sleepy: "(-_-) zzz",
  tired: "(￣o￣)",
  annoyed: "(｀へ´)",
  wronged: "(｡•́︿•̀｡)",
  proud: "(๑•̀ㅂ•́)و✧",
  playful: "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧",
  lonely: "(._.)",
  calm: "( ˘ω˘ )"
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
