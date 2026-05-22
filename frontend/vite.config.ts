import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import legacy from "@vitejs/plugin-legacy";
import { execSync } from "child_process";
import { writeFileSync } from "fs";
import { resolve } from "path";

function buildInfoPlugin() {
  return {
    name: "build-info",
    writeBundle() {
      let gitSha = "unknown";
      try {
        gitSha = execSync("git rev-parse --short HEAD", { encoding: "utf-8" }).trim();
      } catch { /* not in git repo */ }
      const info = {
        git_sha: gitSha,
        build_time: new Date().toISOString(),
      };
      writeFileSync(resolve(__dirname, "dist/build-info.json"), JSON.stringify(info, null, 2));
    },
  };
}

export default defineConfig({
  plugins: [
    react(),
    legacy({
      targets: ["Android >= 6", "Chrome >= 49"],
      modernPolyfills: true,
      renderModernChunks: false,
      renderLegacyChunks: true
    }),
    buildInfoPlugin(),
  ],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/static": "http://127.0.0.1:8000"
    },
    fs: {
      allow: [".."]
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true
  }
});
