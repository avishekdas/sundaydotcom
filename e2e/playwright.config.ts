import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 120_000,
  retries: 1, // TP-11 flake policy: one retry; the north-star spec is never quarantined
  reporter: [["list"]],
  use: { baseURL: process.env.BASE_URL, trace: "retain-on-failure" },
});
