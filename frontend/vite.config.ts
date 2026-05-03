import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import legacy from "@vitejs/plugin-legacy";

export default defineConfig({
  plugins: [
    react(),
    legacy({
      targets: ["Android >= 6", "Chrome >= 49"],
      modernPolyfills: true,
      renderModernChunks: false,
      renderLegacyChunks: true
    })
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
