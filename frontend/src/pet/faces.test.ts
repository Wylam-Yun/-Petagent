import { expressionForKey, faceForType } from "./faces";

test("expressionForKey returns configured expression", () => {
  expect(expressionForKey("playful")).toBe("(^_~)");
});

test("expressionForKey falls back through mood", () => {
  expect(expressionForKey("unknown", "angry")).toBe("(>_<)");
  expect(expressionForKey("unknown")).toBe("(o.o)");
});

test("faceForType returns the first configured face for a mood", () => {
  expect(faceForType("happy")).toBe("(^_^)");
});

test("faceForType falls back to idle for unknown mood", () => {
  expect(faceForType("unknown")).toBe("(o.o)");
});
