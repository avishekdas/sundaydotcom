import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: { globals: true, environment: "jsdom" },
  server: { proxy: { "/api": "http://localhost:8000", "/config.json": "http://localhost:8000",
                    "/ws": { target: "ws://localhost:8000", ws: true } } },
});
