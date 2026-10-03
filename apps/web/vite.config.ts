import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Absolute asset URLs + clean URLs: serve with SPA fallback (apps/web/serve.py or the API container).
  base: "/",
  server: { port: 5173, proxy: { "/api": "http://localhost:8100", "/healthz": "http://localhost:8100" } },
  build: { target: "es2022", chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", globals: true, setupFiles: ["src/test/setup.ts"], include: ["src/**/*.test.{ts,tsx}"] },
});
