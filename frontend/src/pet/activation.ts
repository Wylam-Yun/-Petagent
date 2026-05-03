export type ActivationConfig = {
  wakePhrases: string[];
  exitPhrases: string[];
  minConfidence: number;
};

export const defaultActivationConfig: ActivationConfig = {
  wakePhrases: ["hi momo", "hey momo", "嗨 momo"],
  exitPhrases: ["momo休息吧", "退出", "先这样", "不用陪了"],
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
  return text.toLowerCase().replace(/[\s，。,.!?！？、]/g, "");
}
