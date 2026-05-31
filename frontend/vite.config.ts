import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import legacy from "@vitejs/plugin-legacy";
import { execSync } from "child_process";
import { createHash } from "crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "fs";
import { resolve } from "path";

function hashDirectory(path: string): string {
  const hash = createHash("sha256");
  const stack = [path];
  while (stack.length > 0) {
    const current = stack.pop()!;
    const stat = statSync(current);
    if (stat.isDirectory()) {
      for (const entry of readdirSync(current).sort().reverse()) {
        stack.push(resolve(current, entry));
      }
      continue;
    }
    hash.update(current.replace(__dirname, ""));
    hash.update(readFileSync(current));
  }
  return hash.digest("hex");
}

function buildInfoPlugin() {
  return {
    name: "build-info",
    writeBundle() {
      let gitSha = "unknown";
      try {
        gitSha = execSync("git rev-parse --short HEAD", { encoding: "utf-8" }).trim();
      } catch { /* not in git repo */ }
      const sourceHash = hashDirectory(resolve(__dirname, "src"));
      const info = {
        git_sha: gitSha,
        build_time: new Date().toISOString(),
        source_hash: sourceHash,
      };
      writeFileSync(resolve(__dirname, "dist/build-info.json"), JSON.stringify(info, null, 2));
      const indexPath = resolve(__dirname, "dist/index.html");
      const version = sourceHash.slice(0, 16);
      try {
        const html = readFileSync(indexPath, "utf-8").replace(
          /((?:src|data-src)="\/assets\/[^"?]+\.js)(?:\?v=[^"]*)?(")/g,
          `$1?v=${version}$2`,
        );
        writeFileSync(indexPath, html);
      } catch {
        // The dist index can be absent in non-standard build modes.
      }
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
