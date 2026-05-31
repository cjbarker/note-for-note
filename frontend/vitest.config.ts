import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Unit tests only; the heavy OSMD/audio rendering paths are excluded.
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
