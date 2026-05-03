import { faceForType } from "./faces";

test("faceForType returns the first configured face for a mood", () => {
  expect(faceForType("happy")).toBe("(^▽^)");
});

test("faceForType falls back to idle for unknown mood", () => {
  expect(faceForType("unknown")).toBe("(・ω・)");
});
