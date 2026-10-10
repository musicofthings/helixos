import { defineConfig } from "vitest/config";

export default defineConfig({
  // tsconfig uses jsx: "preserve" for Next; tests need it compiled.
  esbuild: { jsx: "automatic" },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    restoreMocks: true
  }
});
