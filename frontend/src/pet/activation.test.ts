import { describe, expect, test } from "vitest";

import { detectActivationIntent, matchesExitPhrase, matchesWakePhrase } from "./activation";

const config = {
  wakePhrases: ["hi momo", "hey momo", "嗨 momo"],
  exitPhrases: ["momo休息吧", "退出", "先这样", "不用陪了"],
  minConfidence: 0.75
};

describe("activation phrase matching", () => {
  test("matches wake phrases without depending on exact spacing", () => {
    expect(matchesWakePhrase("hi momo", config)).toBe(true);
    expect(matchesWakePhrase("himomo", config)).toBe(true);
    expect(matchesWakePhrase("hello momo", config)).toBe(false);
  });

  test("matches exit phrases from config", () => {
    expect(matchesExitPhrase("momo休息吧", config)).toBe(true);
    expect(matchesExitPhrase("不用陪了", config)).toBe(true);
    expect(matchesExitPhrase("继续陪我", config)).toBe(false);
  });

  test("detects wake and exit intent only above confidence threshold", () => {
    expect(detectActivationIntent("hi momo", 0.9, config)).toBe("wake");
    expect(detectActivationIntent("momo休息吧", 0.9, config)).toBe("exit");
    expect(detectActivationIntent("hi momo", 0.2, config)).toBe("none");
  });
});
