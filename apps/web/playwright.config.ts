import { defineConfig } from "@playwright/test";

// Use an installed browser locally (PW_CHANNEL=msedge or chrome: no download). In CI run `npx playwright install chromium` and leave it unset.
const channel = process.env.PW_CHANNEL || undefined;
const FULL = "http://127.0.0.1:8110";      // API serving the built app (the full product)
const OFFLINE = "http://127.0.0.1:8111";   // static server, no backend (what a lab machine runs)

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [["list"]],
  use: { channel, headless: true, trace: "retain-on-failure", viewport: { width: 1280, height: 900 } },
  projects: [
    { name: "full", testMatch: /full\..*\.spec\.ts/, use: { baseURL: FULL } },
    { name: "offline", testMatch: /offline\..*\.spec\.ts/, use: { baseURL: OFFLINE } },
  ],
  webServer: [
    { command: "node e2e/start-full.mjs", url: `${FULL}/healthz`, timeout: 90_000, reuseExistingServer: false },
    { command: "node e2e/start-offline.mjs", url: `${OFFLINE}/`, timeout: 30_000, reuseExistingServer: false },
  ],
});
