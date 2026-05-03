import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { expect, test } from "vitest";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("Vite build keeps a legacy bundle for Android 6 era browsers", () => {
  const config = readFileSync(join(__dirname, "vite.config.ts"), "utf-8");

  expect(config).toContain("@vitejs/plugin-legacy");
  expect(config).toContain("Android >= 6");
  expect(config).toContain("renderModernChunks: false");
  expect(config).toContain("renderLegacyChunks: true");
});
