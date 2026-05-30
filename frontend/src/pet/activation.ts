export type ActivationConfig = {
  wakePhrases: string[];
  exitPhrases: string[];
  minConfidence: number;
};

export const defaultActivationConfig: ActivationConfig = {
  wakePhrases: ["豆豆", "嗨豆豆", "你好豆豆", "hi momo", "hey momo", "嗨 momo", "你好 momo"],
  exitPhrases: ["豆豆休息吧", "momo休息吧", "退出", "先这样", "不用陪了"],
  minConfidence: 0.75
};

export type ActivationIntent = "wake" | "exit" | "none";

export function matchesWakePhrase(text: string, config = defaultActivationConfig): boolean {
  return matchesAnyPhrase(text, config.wakePhrases);
}

export function matchesExitPhrase(text: string, config = defaultActivationConfig): boolean {
  return matchesAnyPhrase(text, config.exitPhrases);
}

export function detectActivationIntent(
  text: string,
  confidence: number,
  config = defaultActivationConfig
): ActivationIntent {
  if (confidence < config.minConfidence) {
    return "none";
  }
  if (matchesWakePhrase(text, config)) {
    return "wake";
  }
  if (matchesExitPhrase(text, config)) {
    return "exit";
  }
  return "none";
}

function matchesAnyPhrase(text: string, phrases: string[]): boolean {
  const normalizedText = normalizePhrase(text);
  return phrases.some((phrase) => normalizedText.includes(normalizePhrase(phrase)));
}

function normalizePhrase(text: string): string {
  return normalizePetName(text).toLowerCase().replace(/[\s，。,.!?！？、]/g, "");
}

export function normalizePetName(text: string): string {
  return text.replace(/默默|摸摸/g, "momo");
}
