import type { Mood } from "./types";

export const faceMap: Record<Mood, string[]> = {
  idle: ["(・ω・)", "(｡•̀ᴗ-)✧", "(๑•̀ㅂ•́)و✧"],
  happy: ["(^▽^)", "(≧▽≦)", "٩(ˊᗜˋ*)و"],
  sad: ["(´･_･`)", "(｡•́︿•̀｡)", "(╥﹏╥)"],
  sleepy: ["(-_-) zzz", "(￣o￣) . z Z", "(－_－) zzZ"],
  angry: ["(｀へ´)", "(╬ Ò﹏Ó)", "(ノಠ益ಠ)ノ"],
  shy: ["(//▽//)", "(*ﾉωﾉ)", "(⁄ ⁄•⁄ω⁄•⁄ ⁄)"],
  thinking: ["(・・?)", "(。ヘ°)", "(｡•̀ᴗ-)✧"],
  concerned: ["(´･_･`)", "(´・ω・`)", "(｡•́︿•̀｡)"],
  excited: ["٩(ˊᗜˋ*)و", "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧", "ヽ(>∀<☆)ノ"],
  lonely: ["(._.)", "(｡•́︿•̀｡)", "(´；ω；`)"]
};

export function faceForType(faceType: string, index = 0): string {
  const faces = faceMap[faceType as Mood] ?? faceMap.idle;
  return faces[index % faces.length];
}
