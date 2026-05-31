import { expressionForKey, faceForType } from "./faces";

test("expressionForKey returns configured expression", () => {
  expect(expressionForKey("playful")).toBe("(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧");
});

test("expressionForKey falls back through mood", () => {
  expect(expressionForKey("unknown", "angry")).toBe("(｀へ´)");
  expect(expressionForKey("unknown")).toBe("(・ω・)");
});

test("faceForType returns the first configured face for a mood", () => {
  expect(faceForType("happy")).toBe("(^▽^)");
});

test("faceForType falls back to idle for unknown mood", () => {
  expect(faceForType("unknown")).toBe("(・ω・)");
});
